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
  type 0 -> $EB:2558   (the map themes / long songs — the heart of the OST)
  type 1 -> $EB:266C   (short jingles/BGM; entries in banks $EE/$EF)
  type 2 -> $EB:2969   (SFX — a different, non-music payload)
  type 3+ -> $7E:87FE  (a RAM table, 2-byte, not ROM)
entry  = little-endian 24-bit at  table + id*3   ->  $E7/$E8/$E9   (bank via &$3F|$C0)
```

> Earlier notes had type 1 as "the BGM" — wrong. The full songs (incl. the boss
> themes) are **type 0**; see §7.

### The ROM→ARAM copy is verbatim

A captured ARAM region (where a song's sequence sits, ~`$C900` in the SPC
address space) was found **byte-for-byte** inside the ROM in banks `$EE/$EF`.
That means the upload is a *plain copy* (no compression) — so the song data is
directly readable from ROM. The table entry points at a small *header* whose
format is fully decoded in §7 — enough to reconstruct any song from the ROM
alone.

### The loader

```
$EB040B -> $EB04CF :
  JSR $0994   ; set [$E7] = ROM pointer for this song
  LDA [$E7],Y ; read the song header
  ...
  JSL $EB022A ; configure the song's instruments (NOT a raw streamer): it reads
              ; the per-song instrument-id list and, with the HW multiplier and
              ; the global tables, builds the DSP sample directory + ADSR/tuning
              ; (sent via $EB0067). The header/track relocation happens SPC-side.
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
image during normal play and wrapping it, or (b) a fully *static* extractor —
which is what §7 documents, and what won.

> The `spy` mode of `tools/rudra_ripper.lua` (passive logging of every audio
> call) works perfectly and is how the `$00/$01/$02` encoding above was
> confirmed from the live game.

---

## 7. The fully static extractor

The static route was completed: **every song reconstructs from the ROM alone**,
byte-for-byte, with no emulator in the loop. The template only supplies the
*shared* state (engine code + boot samples, identical across all songs); the
per-song content is built from the ROM tables below. Tool:
[`rudra_rip_static.py`](../tools/rudra_rip_static.py) (`build` one id, `batch`
them all).

### 7.1 Song header → load address

A type-0 table entry points at a header:

```
[size_word : 2]              ; LE; these 2 bytes are consumed, NOT loaded
[payload   : size]           ; streamed verbatim to ARAM
   payload = [04][N = track count][N × 2-byte track pointers][Itikiti bytecode…]
```

The relocation key is dead simple: **every song ends at `$CD00`**, so

```
dest = $CD00 − size
```

The track pointers in the payload are bank-relative (e.g. `$250D` → payload + `$12`);
the engine resolves them to `dest + (ptr − payload_start)` at play time. (The
`$C9xx`-style addresses one sees in a *live* capture are the running play
cursors in zero-page `$20–$2F`, not the track starts.)

### 7.2 Instruments — a global sample pool, four parallel tables

The 16 bytes **immediately before** the header are the song's instrument-id list
(0-terminated, ≤ 16; the loader does `$E7 = header − $0F`). Each id indexes four
global tables (`N = 66` instruments):

| table | addr | width | meaning |
|-------|------|-------|---------|
| source | `$EB:296C` | 24-bit | ROM pointer to `[size:2][BRR:size]` |
| loop   | `$EB:2A33` | 16-bit LE | loop offset (`loop_aram = sample_start + this`) |
| tuning | `$EB:2AB7` | 16-bit **BE** | pitch (this is VGMTrans's `getShortBE`) |
| ADSR   | `$EB:2B3B` | 2 bytes | envelope |

BRR data (`rom[src+2 : src+2+size]`) is packed sequentially into ARAM from
`$25E6`, in list order, using **DSP directory indices from 32 up**.

### 7.3 The three InstrSet tables VGMTrans reads

For each per-song instrument *i* (dir index `32 + i`):

```
$1B00 + (32+i)*4 : sample DIR entry   [start:2][loop:2]
$1D40 + (32+i)*2 : tuning  (BE)       = tuning_table[id]
$1E60 + (32+i)*2 : ADSR                = adsr_table[id]
```

These are exactly VGMTrans's `ItikitiSnesInstrSet(file, 0x1d40, 0x1e60, 0x1b00)`
— tuning, ADSR, dir. Miss the tuning table and the pitch comes out flat and
inconsistent between instruments (a good "you forgot a table" smell-test).

### 7.4 The pointer that makes VGMTrans open the file

`ItikitiSnesScanner` finds the engine signature, reads `readShort(code+6)` → the
direct address **`$ED80`**, then `header_end = readShort($ED80)` and back-tracks
the track count. So a reconstructed image must set

```
$ED80 (2 bytes) = header_end = dest + 2 + N*2
```

or VGMTrans won't recognise the song at all.

### 7.5 Result

`batch` walks the type-0 table and writes one `.spc` per valid song. The only
guard that matters is *samples must not overrun the sequence* (`sample_end ≤
dest`); there is **no lower bound on `dest`** — the longest songs (the boss
themes) load well below `$C000`, and an earlier `dest ≥ $C000` filter wrongly
dropped exactly those. Output goes straight into VGMTrans for MIDI/SF2.
