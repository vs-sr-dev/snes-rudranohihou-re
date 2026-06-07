# snes-rudranohihou-re

A **reverse-engineering devlog** documenting how the Japanese text system of
**Rudra no Hihō / Treasure of the Rudras** (SNES, Square, 1996) was decoded —
its custom 2-byte kanji encoding, its compression tricks, and the methodology
used to crack them.

> **This is a documentation & methodology project, not a romhack.**
> It contains **no ROM, no game graphics/audio, no bulk extracted script** —
> only original tooling and notes about *how the text format works*.
> See [DISCLAIMER.md](DISCLAIMER.md).

---

## What's inside

| Path | What it is |
|------|------------|
| [`devlog/`](devlog/) | The "captain's log": chronological write-ups of the cracking process |
| [`docs/encoding.md`](docs/encoding.md) | Technical reference of the discovered **text** format |
| [`docs/audio.md`](docs/audio.md) | Technical reference of the **sound engine** (host API, song tables) |
| [`tools/rudra_text.py`](tools/rudra_text.py) | Original Python tool: encoding table + message extractor |
| [`tools/spc_wrap.py`](tools/spc_wrap.py) | Wrap a *user-captured* APU RAM image into a playable `.spc` |
| [`tools/rudra_rip_static.py`](tools/rudra_rip_static.py) | Reconstruct any song's APU image **from the ROM tables alone** — emulator-free static rip |
| [`tools/itikiti_seq.py`](tools/itikiti_seq.py) | Decode the AKAO/Itikiti sequence bytecode (opcode table) |
| [`tools/rudra_ripper.lua`](tools/rudra_ripper.lua) | Mesen2 Lua: spy on the audio API / drive the loader |
| `rom/` | **Empty.** Where *you* place *your own* legally-owned ROM (git-ignored) |

## Why this exists

RE knowledge tends to die with abandoned projects. Even if the full
disassembly is never published, this repo preserves the *method* — useful to
anyone studying Square's SNES text engine, kanji-table encodings, or DTE-style
compression. It's a learning log first, a reference second.

## The short version of what was found

- **Single-byte kana** on a contiguous gojūon layout (hiragana base `$2A`).
- **Two-byte kanji** with lead bytes `$01/$02/$03` + index, roughly ordered by
  frequency (`$0101` = 言, the most common).
- **Control codes** shared with the (already-cracked) English script, so the
  message *structure* is identical across languages.
- A **substring/DTE dictionary** (`$17 XX`) that expands common fragments and
  even whole kanji.
- A **name dictionary** (`$12 XX`) and a runtime **location-name code** (`$23`).
- **Inline furigana** via full-width parentheses for special readings
  (e.g. 運命 read *sadame*).

Full details and the story of how each was found live in [`devlog/`](devlog/).

## Using the tool

The tool reads a ROM **you provide** (it is never bundled here):

```bash
# point it at your own legal copy
export RUDRA_ROM="/path/to/Rudra no Hihou (Japan).sfc"   # or put it in ./rom/

python tools/rudra_text.py tbl                 # write the encoding table (.tbl)
python tools/rudra_text.py dump 30A000 30A100  # decode messages in a range
python tools/rudra_text.py find "おそい"        # locate a kana string, decode its message
```

## Credits & prior work

- Original game © Square (1996). All trademarks belong to their owners.
- The English fan-translation referenced for cross-checking was made by
  **Aeon Genesis** (Gideon Zhi). The translation-philosophy notes ("Two notes
  on the translation…") are © **Haeleth** — *linked, not redistributed here*.
- This devlog and tooling: see [LICENSE](LICENSE).

## Status

🚧 Ongoing, hobby-paced. **~286 of the game's ~730 kanji codes** identified so
far, plus the structural pieces above. The project has also grown a second
track — the **AKAO-family sound engine** (see [`docs/audio.md`](docs/audio.md)
and [devlog 002](devlog/002-the-akao-sound-engine-and-spc-ripping.md)):
the host audio API, the in-ROM song-pointer tables, an honest account of an
emulator-automation dead end — and the **fully static extractor** that won,
reconstructing every song's APU image from the ROM tables alone (no emulator),
ready for VGMTrans. Contributions/corrections welcome via issues.
