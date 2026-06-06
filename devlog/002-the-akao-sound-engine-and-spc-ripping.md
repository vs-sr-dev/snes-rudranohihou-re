# 002 — The AKAO sound engine, and an honest SPC-ripping dead end

*How Rudra's audio API was reverse-engineered from the 65816 side — the song
pointer tables, a verbatim ROM→ARAM copy — and why "just automate the rip in the
emulator" turned into the most instructive failure of the session.*

This is a methodology log. It documents how the **engine** works and how each
piece was found and verified; it reproduces **no music**. See
[`../docs/audio.md`](../docs/audio.md) for the condensed reference.

---

## Starting point: an ear, then a name

The hunch came from listening — Rudra "sounds closer to Chrono Trigger than to
FF6." That turned out to be literally true: the driver is an **AKAO**-family
engine (Square's Minoru Akao), the late `ItikitiSnes` variant that shares the
Romancing SaGa 3 / Chrono Trigger opcode branch. VGMTrans recognizes it
natively, which sets the finish line: get a faithful APU RAM image, and the rest
(MIDI/SF2) is a known-good export.

All SNES-side audio code sits in **bank `$EB`**.

## Step 1 — Find the one API call

Tracing port writes (`$2140–$2143`) led to a single entry point the whole game
uses: `JSL $EB0372`. Disassembling it (and the real dispatcher it falls into,
`$EB03BC`) revealed the parameter packing:

```
$00 = command   (high 6 bits = category, low 2 = sub/priority)
$01 = id / data
$02 = parameter
```

with the classic Square "doorbell" handshake on `$2140` (`$EB0942`/`$EB0957`).

## Step 2 — Spy instead of guess

Rather than guess which command means "play BGM," the cleanest move was a
**passive Mesen2 Lua hook** on `$EB03BC` that logs `$00/$01/$02` on every audio
call. Playing the game for a minute produced ground truth: BGM plays via the
**`$98`-family** command with `$01` = song id. A neat tell — one game call shows
up as a *pair* of dispatches (`cmd=$99 id=X` then `cmd=$45 id=X`), which is
exactly the `ORA #$98` "split" the wrapper does in the disassembly. Reading
matched listening.

> The spy is the part of the tooling that worked flawlessly end to end.

## Step 3 — The song tables, and a verbatim copy

A reader's question — *"can't we just read the songs out of the ROM?"* — pointed
the right way. `$EB0994` computes the song pointer: `id * 3` indexes a table of
**24-bit pointers** (3 bytes each), with a different table per type
(`$EB:2558` / `$EB:266C` / `$EB:2969`). The pointers land in banks `$EE/$EF`.

The clincher: a chunk of a captured song's ARAM data was found **byte-for-byte
in the ROM**. The ROM→ARAM upload is a **plain copy** — the music data is right
there, uncompressed. (The table entry points at a small *header* that references
the note streams, so a fully static dumper still has to walk that structure; the
uploader `$EB022A` is not a memcpy — it expands up to 16 header blocks into SPC
commands via the hardware multiplier and a table at `$EB2A33`.)

## Step 4 — Making a capture playable

A memory dump gives the 64 KB APU RAM but not the SPC's CPU/DSP registers. A
small wrapper (`tools/spc_wrap.py`) rebuilds an ID666 `.spc`, seeding the missing
state with values **read from the driver's init code**, not guessed — most
importantly the timer latches (`$F1/$FA/$FB`), which a RAM dump reads back as 0,
which would otherwise freeze the engine. With those re-seeded, captured songs
play and export cleanly.

## The dead end: automating the rip

The obvious dream: a Lua sweep that, for every id, simulates the `JSL`, lets the
game's own loader stream the song into ARAM, dumps it, repeats. A **single**
injection worked beautifully (a controlled load changed the sequence region by
~40%, stable). The **sequential sweep never did.** Several rounds of debugging
peeled back the reasons, each worth recording:

1. **`emu.getState()` is a flat, dotted-key table** (`s["cpu.pc"]`, not
   `s.cpu.pc`). Easy to discover, easy to get wrong first.
2. **A partial `setState` zeroes the fields you didn't list.** This was the
   silent killer: "park the CPU" by setting just `pc`/`k` quietly wiped `sp`
   (→ "address must be >= 0") and the **SPC registers** (→ dead engine). It
   masqueraded as a dozen unrelated bugs across several attempts.
3. **A full `setState` reverts the SPC**, desyncing the *next* upload handshake —
   so restoring "cleanly" between songs corrupts the run after a handful of ids.
4. **Savestates are the right tool but can't be used here:**
   `createSavestate`/`loadSavestate` may only be called **inside an exec memory
   callback**, not from the frame callback that drives the sweep.

The honest conclusion: with these constraints there is no clean way (found so
far) to reset the SPC between injections without breaking it. We stopped.

## What actually works

- **Capture-during-play** + `spc_wrap.py`: 100% reliable, one song per dump.
- **A fully static extractor** that reverses the multi-block uploader `$EB022A`
  and reconstructs each song from the ROM tables — more work, but deterministic
  and emulator-free. (Foundations are in place: tables found, copy proven, loader
  mapped.)

## Lessons

- **Listen first.** The genre/era guess ("CT, not FF6") named the engine before
  any disassembly.
- **Spy before brute force.** A passive log of the real API beat guessing the
  command encoding outright.
- **A reader's naïve question can be the best lead.** "Read it from the ROM"
  reframed the whole problem and produced the pointer tables.
- **Know your tools' invariants.** Half the failures here were not about the
  *game* at all but about undocumented emulator-scripting semantics
  (partial-`setState` zeroing, savestate callback context). When an automation
  fights you at every turn, suspect the harness, not just the target.
