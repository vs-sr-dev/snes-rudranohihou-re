# Rudra no Hihō — text format reference

A structural description of the game's Japanese text encoding, as reverse-
engineered. This documents *how the bytes are interpreted by the engine*, not
the game's script. Hex values are **file offsets** of the clean Japanese cart
(headerless, HiROM, 32 Mbit).

> The complete code→glyph table is **generated locally** by
> `tools/rudra_text.py tbl` (it needs your own ROM). This page documents the
> *scheme*; a few glyphs are shown only as worked examples.

---

## 1. Cartridge / memory map

- HiROM + FastROM, 32 Mbit, 8 KB battery SRAM, Japan region.
- Reset stub jumps to the real entry at `$C00001` (= file offset `0x000001`).
- The text engine lives in bank `$C0` (file `0x3000–0x10000` area).
- Dialogue text regions (file offsets):
  - block A: `0x30A000–0x348000`  (`$F0:A000`)
  - block B: `~0x3A6000–0x3D5000` (`$FA:6000`)
- Data tables: name dictionary `0x31608`, **location-name table `0x31000–0x313xx`**,
  weapon/armor descriptions `~0x308000+`, magic descriptions `~0x309700+`.

## 2. Single-byte kana (gojūon-contiguous)

The kana are laid out in dictionary (gojūon) order on contiguous byte ranges.
This was the key that unlocked everything — once the base was found, an entire
syllabary fell out at once.

| Range start | Set |
|-------------|-----|
| `$2A` | hiragana あ–ん |
| `$58` | dakuten hiragana が–ぽ |
| `$71` | small kana ぁ–ぉ, っ |
| `$77` | yōon ゃゅょ |
| `$7A` | long vowel ー |
| `$7B` | katakana ア–ン |
| `$A9` | dakuten katakana ガ–ボ |
| `$BD` | handakuten katakana パ–ポ |
| `$C2` | small katakana ァィゥェォッャュョ |
| `$CB` | ヴ |

Punctuation: `$19`＝。 `$1A`＝、 `$1B`＝？ `$1C`＝！ `$1F`＝…

**Worked example.** The game's very first line begins
`12 11 1D | 2E 38 2B 41 7A | 1A | …` which decodes (kana only) to
`…「おそいねー、…` — i.e. *"…hey, you're slow…"*. Matching this against a
screenshot is what pinned the kana base at `$2A`.

> ⚠️ A first-pass guess had the hiragana base at `$4D` (off by 35). It was
> wrong; everything keyed off `$2A`. Validate kana bases against a known line.

## 3. Two-byte kanji

Kanji use a **lead byte `$01`, `$02`, or `$03`** followed by an index byte.
Codes are roughly ordered by frequency.

```
01 01            -> 言   (most frequent kanji; appears in 言う。 etc.)
01 24 01 59 01 64 -> 教団員  ("cult member")
```

Notes & gotchas:
- A message is `$00`-terminated, but **`$00` can be the *second* byte of a
  kanji** (e.g. `01 00`). Message-splitting must be kanji-aware.
- The glyph 言 has **two codes**: `01 01` (used as the kotodama "言霊" marker
  in magic-name wrappers) and `01 03` (the ordinary lexical 言, as in 言葉 /
  予言書). Both render 言.
- Namespaces don't overlap: a kanji code `01 F5` (文) is unrelated to a DTE
  code `17 F5` (流). Same number, different table — see §4.

## 4. The `$17` substring / DTE dictionary

`$17 XX` expands a common fragment. Expansions can be two kana, or even a whole
kanji:

```
17 1A -> かま   (so をつ17 1Aえた = つかまえた, "caught")
17 91 -> やり   (むり17 91 = むりやり; 17 91なおし = やりなおし)
17 F6 -> 死
17 F7 -> 浄     (so X が 17 F7 〔化〕される = 浄化される, "is purified")
```

Structurally important finding: **the expansion text is *not* stored in clear,
contiguous bytes anywhere in ROM** — the digrams かま/やり/うで never appear
co-located. The table is packed inside the bank-`$C0` text engine and would
require a CPU trace (e.g. Mesen + a disassembler) to dump in full. In practice
the entries were recovered by **context-cribbing** from grammar (see devlog).

## 5. Other engine codes

- **`$12 XX` — name dictionary.** Inserts a character/phrase from a
  *sequential* pool (the engine counts `$00` terminators; `$12 + n` = the n-th
  entry). Pool base `0x31608` (entry 0 = シオン).
- **`$23` — current location name.** A runtime code that expands to the active
  map's name, pulled from the location-name table at `0x31000`. e.g. a line
  stored as `「<$23>への挑戦…` displays as `「武人の塔への挑戦…`.
- **Inline furigana / gikun.** Full-width parentheses `（`=`01 CA`, `）`=`01 CB`
  gloss a kanji with a special reading: `運命（さだめ）` — write 運命, read
  *sadame*.
- Shared control codes (same as the English script): `$00` end, `$04` newline,
  `$06` control prefix, `$11` 「, `$12` name, `$18` line-start, etc.

## 6. Lessons / methodology notes

- **Screenshots are ground truth.** Rendered glyphs overruled two earlier
  inference errors (a sequence read as 汚染 was actually 修行; the top DTE
  guessed as 汚 was actually 浄).
- **Frequency is a sanity check.** A code claimed to be 人 had better be one of
  the most frequent in the dialogue blocks (it is: ~640×).
- **Anchor on the known.** Search a mixed byte-pattern of known kana + known
  kanji codes *around* an unknown code, read the surrounding grammar, then
  verify by frequency and a second occurrence.

For the narrative of how each piece was found, see [`../devlog/`](../devlog/).
