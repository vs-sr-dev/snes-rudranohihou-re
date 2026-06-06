# Devlog

Chronological write-ups of the reverse-engineering process — the "captain's
log". Each entry focuses on *method*: what was tried, what failed, what the
evidence was, and how a finding was verified.

| # | Entry | Topic |
|---|-------|-------|
| 001 | [Cracking Rudra's Japanese text](001-cracking-rudras-japanese-text.md) | Kana base, 2-byte kanji, DTE, the screenshot-crib method, and two instructive mistakes |
| 002 | [The AKAO sound engine, and an honest SPC-ripping dead end](002-the-akao-sound-engine-and-spc-ripping.md) | Audio API, in-ROM song-pointer tables, verbatim ROM→ARAM copy, and why emulator automation failed |

Kanji cracking continues alongside the audio work (now ~271/~730 codes mapped);
the running table lives in [`../tools/rudra_text.py`](../tools/rudra_text.py).

> Reminder: these are methodology notes. They describe how the *format* works,
> not the game's script. See [../DISCLAIMER.md](../DISCLAIMER.md).
