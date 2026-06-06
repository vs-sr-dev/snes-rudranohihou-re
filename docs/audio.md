# Rudra no Hihō — sound engine reference

A structural description of the game's audio system, as reverse-engineered. As
with [`encoding.md`](encoding.md) this documents *how the engine works*, not the
game's music. **No audio is contained or redistributed here** — only the format,
addresses, and method. Hex values are addresses on the clean Japanese cart
(headerless, HiROM); file offset = `((bank & $3F) << 16) | addr` for banks
`$C0–$FF`.

---

## 1. Engine identity

Rudra's driver is of the **AKAO** lineage (Minoru Akao, Square), specifically
the late variant VGMTrans calls **`ItikitiSnes`** — a sibling of the Romancing
SaGa 3 / Chrono Trigger branch (V4), distinct enough to have its own opcode
table. VGMTrans recognizes it natively, which is the easiest way to turn a
captured APU image into MIDI/SF2.

All SNES-side audio code lives in **bank `$EB`** (~`$EB:0000–$EB:0900`); the
song *data* lives in banks `$EC–$EF`.

## 2. Host audio API (65816 side)

The game requests audio through one entry point:

```
JSL $EB0372       ; the audio API wrapper
```

with a packed parameter in zero-page direct page:

| DP | meaning | sent to |
|----|---------|---------|
| `$00` | **command** (high 6 bits = category → `$E5`; low 2 = sub/priority → `$E6`) | APU port `$2140` (handshaked) |
| `$01` | **ID / data** (e.g. song id) | APU port `$2141` |
| `$02` | parameter (fade/volume) | APU port `$2142` |

- `$EB0372` is a priority wrapper. For categories `$44` / `$48` it *splits* one
  game call into **two** dispatches: it `ORA #$98`s the sub bits to emit a
  "play music" command in the **`$98–$9B`** family, then falls through to the
  original command. (Spying on the live game shows this as paired
  `cmd=$99 id=X` / `cmd=$45 id=X` log lines.)
- `$EB03BC` is the **real dispatcher** and the choke-point every sound passes
  through — the ideal place to hook when spying.

### APU handshake

The classic Square "doorbell" on port `$2140`:

```
$EB0942:  write $FF -> $2140 ; wait until it reads back $FF (SPC ack)
          write cmd -> $2140 ; wait until it reads back cmd
$EB0957:  write $00 -> $2140 ; wait until it reads back $00   (closes the transaction)
```

Data bytes (`$2141`/`$2142`) are placed *before* ringing the doorbell.

## 3. In-ROM song-pointer tables

"Play song *id*" does **not** just message the SPC — the host must first stream
that song's data from ROM into ARAM. The pointer is computed in `$EB0994`:

```
index = id * 3                      ; 3-byte entries = 24-bit pointers
table  = selected by the sub/type ($E6):
  type 0 -> $EB:2558
  type 1 -> $EB:266C   (BGM; entries in banks $EE/$EF)
  type 2 -> $EB:2969   (68 entries ≈ the ~66 tracks + a couple extras)
  type 3+ -> $7E:87FE  (a RAM table, 2-byte, not ROM)
entry  = little-endian 24-bit at  table + id*3   ->  $E7/$E8/$E9
```

### The ROM→ARAM copy is verbatim

A captured ARAM region (where a song's sequence sits, ~`$C900` in the SPC
address space) was found **byte-for-byte** inside the ROM in banks `$EE/$EF`.
That means the upload is a *plain copy* (no compression) — so the song data is
directly readable from ROM. (The table entry points at a small *header* that in
turn references the note streams, so a fully-static extractor still has to walk
that structure.)

### The loader

```
$EB040B -> $EB04CF :
  JSR $0994   ; set [$E7] = ROM pointer for this song
  LDA [$E7],Y ; read the song header
  ...
  JSL $EB022A ; stream ROM -> ARAM (NOT a memcpy: it translates up to 16 header
              ; blocks into SPC upload commands, using the HW multiplier and a
              ; table at $EB2A33, sending via $EB0067)
```

## 4. Sequence bytecode (Itikiti opcode table)

Once in ARAM the sequence is AKAO/Itikiti bytecode. Threshold:
**commands = `$00–$2F`**, **notes/durations = `$30–$FF`**.

- Notes `$30–$EF`: key = `byte >> 3`, duration index = `byte & 7`
  (0–6 index a note-length table `{C0,60,48,30,24,18,0C}`; 7 = read next byte as
  a custom length).
- Ties `$F0–$F7`, rests `$F8–$FF`.
- Commands (selected): `00`=END `01`=MASTER_VOL `03`=CHANNEL_VOL `06`=TEMPO
  `0C`=VOLUME `0D`=VOL_FADE `0E`=PAN `10`=PROGRAM_CHANGE `12–15`=ADSR
  `17/18`=TRANSPOSE `19`=VIBRATO_ON `2A`=LOOP_START `2C`=GOTO `2E`=LOOP_END
  `2F`=LOOP_BREAK. (Full table in `tools/itikiti_seq.py`.)

Validation: decoding a real song's header by hand (TEMPO byte = `$7D` = 125)
matched VGMTrans's MIDI export (125 BPM) exactly.

## 5. Turning a capture into a playable `.spc`

`emu.getState()`-style memory dumps give the 64 KB APU RAM but **not** the SPC
CPU/DSP registers. `tools/spc_wrap.py` wraps a user-captured RAM image in an
ID666 `.spc` header, seeding the missing state with values *read from the
driver's init code* (not guessed):

- `PC=$037D` (play-start entry), `SP=$FF`, `PSW=$00`.
- DSP `DIR($5D)=$1B`, `MVOL($0C/$1C)=$7F`, `FLG($6C)=$20`.
- Timer latches `$F1=$03`, `$FA=$27`, `$FB=$00` — a RAM dump reads these back as
  0, which would freeze the engine; re-seeding them is what makes the `.spc`
  actually progress.

## 6. Methodology note — an emulator-automation dead end

The tempting "rip everything automatically" route — drive the loader from a
Mesen2 Lua script (simulate the `JSL`, dump ARAM per id) — **was attempted and
abandoned.** It works for a *single* injection but not in a sequential sweep.
The walls, recorded so others don't repeat them:

- `emu.getState()/setState()` use a **flat, dotted-key** table (`s["cpu.pc"]`).
- A **partial** `setState` (a few keys) **zeroes the unlisted fields** — the
  silent root cause of a cascade of failures (SP→0, SPC registers wiped).
- A **full** `setState` reverts the SPC and desyncs the next handshake.
- `createSavestate`/`loadSavestate` may only be called **inside an exec memory
  callback**, not from a frame callback — so they can't easily reset state
  between iterations of a frame-driven sweep.

Net: there is no clean way (found so far) to reset the SPC between injections
without breaking it. The **reliable** routes are (a) capturing each song's APU
image during normal play and wrapping it, or (b) a fully *static* extractor that
reverses the multi-block uploader `$EB022A`.

> The `spy` mode of `tools/rudra_ripper.lua` (passive logging of every audio
> call) works perfectly and is how the `$00/$01/$02` encoding above was
> confirmed from the live game.
