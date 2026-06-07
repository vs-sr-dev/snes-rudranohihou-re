# 001 — Cracking Rudra's Japanese text

*How a custom 2-byte kanji encoding (plus a substring dictionary, a name
dictionary, a location code and inline furigana) was decoded — and the two
mistakes that taught the most.*

This is a methodology log. It documents how the **format** works and how each
piece was *found and verified*; it does not reproduce the game's script. Short
fragments appear only as worked examples.

---

## Starting point

The English fan-translation's text was already a solved problem: a simple
monoalphabetic substitution on contiguous byte ranges. The Japanese original is
the hard part, because it is **multi-byte** and lightly **compressed**.

Two facts made it tractable:

1. The Japanese build shares the **same control codes** as the English one
   (`$00` end-of-message, `$04` newline, `$06` prefix, …). So the *message
   structure* is identical across languages — only the character encoding
   differs.
2. The game is **table-encoded**, not ASCII. That means there is a fixed
   code→glyph mapping to recover, exactly the kind of thing a `.tbl` file
   describes.

## Step 1 — Find the kana base, and an entire syllabary falls out

Japanese scripts (hiragana/katakana) have a canonical order: the *gojūon*. If a
game stores kana contiguously in that order, you don't crack 100 characters —
you crack **one** (the base offset) and the rest follow.

The unlock was a **single screenshot** of the game's opening line. Reading the
on-screen kana and lining them up against the raw bytes of the first message
gave the base: hiragana あ at `$2A`. From there the whole table dropped out:

```
$2A  hiragana あ–ん
$58  dakuten が–ぽ
$71  small kana / っ
$7B  katakana ア–ン
$A9  dakuten katakana …
```

> **Mistake #1 (cheap):** an initial guess put あ at `$4D` — off by 35. It
> produced gibberish. Lesson: *always* calibrate the kana base against a line
> you can read from a screenshot before trusting anything downstream.

Validation was easy: decode a few hundred messages and watch function words
appear at sane frequencies (だった, ない, ました, でした…). When the
particles and copulas come out right, the kana table is right.

## Step 2 — The kanji are 2-byte, frequency-ordered

Kanji use a **lead byte `$01/$02/$03`** plus an index. `$0101` is the single
most frequent code in the dialogue blocks — and it's 言 ("say/word"), which is
exactly what you'd expect to top the list in a text-heavy RPG.

The catch: because a kanji's second byte can be `$00`, message-splitting has to
be **kanji-aware** (don't treat the `$00` inside `01 00` as end-of-message).

There are ~730 kanji codes. You don't get those from one screenshot. Which led
to the method that did most of the work.

## Step 3 — The screenshot-crib method (the workhorse)

The loop that cracked hundreds of kanji:

1. The player sends a **screenshot** of a line and roughly where they are.
2. Locate that line in the ROM by searching for a **mixed byte-pattern**: the
   *known* kana of the sentence interleaved with *known* kanji codes, wrapped
   around the unknown one.
3. The unknown kanji is now pinned by position — read it straight off the
   screenshot.
4. **Verify** two ways: it should appear at a believable frequency, and it
   should make sense in a second, independent occurrence.

Worked example (a few words, fair use): a line shown on screen as
`…教団員をつかまえた…` ("…caught a cult member…") sits in ROM as
`〔教〕〔団〕〔員〕を つ 〔17 1A〕 え た`. The known kanji 教団員 and the kana
frame the `17 1A` code, and the screenshot tells us it expands to かま — so
つ + かま + えた = つかまえた. One screenshot, one dictionary entry nailed.

This is slow per-kanji but extremely reliable, and it scales: a single dense
cutscene can yield 10–20 codes at once.

## Step 4 — Compression: the `$17` substring dictionary

`$17 XX` expands a common fragment. Sometimes two kana, sometimes a whole
kanji:

```
17 1A -> かま      17 91 -> やり      17 F6 -> 死      17 F7 -> 浄
```

The structurally interesting result: **the expansion text is not stored in
clear, contiguous bytes anywhere**. The digrams かま/やり/うで never appear
co-located in the ROM (this was checked exhaustively — no pointer table, no
fixed 2-byte table, no co-location within a wide window). The dictionary is
**packed inside the bank-`$C0` text engine** and would need a CPU trace to dump
in full. Until then, entries are recovered by context-cribbing like everything
else.

## Step 5 — Two corrections (why screenshots beat inference)

Two confident-but-wrong readings were later overturned **by a screenshot**:

- A byte sequence `02 39 01 04`, earlier inferred as 汚染 ("pollution"), turned
  out to render **修行** ("ascetic training") on screen — the hero had been
  *training*, not *polluting*. So `0239`=修, `0104`=行. (Frequency agreed: the
  "行" code is enormous — 行く, 行う, 修行… — which fits 行, not the rarer 染.)
- The top DTE `17 F7`, briefly guessed as 汚, was actually **浄** — the line
  `汚染を 17 F7〔化〕しようと` reads *"…to **purify** the pollution…"*. The real
  pair is 浄化 = `17 F7` + `0132`.

The payoff: the game's whole environmental axis became readable —
**汚染 (pollute) ⇄ 浄化 (purify)** — and the single most frequent two-kanji
compound resolved to **言霊 (kotodama)**, the literal name of the magic system.

> Takeaway: inference gets you a hypothesis; a rendered glyph is ground truth.
> When they disagree, the screen wins — and you go back and fix the map.

## Step 6 — The non-character codes

Beyond kana and kanji, the engine has a small zoo of insertion codes:

- **`$12 XX` — name dictionary.** A *sequential* pool (the engine counts `$00`
  terminators), so `$12 + n` is the n-th stored name/phrase.
- **`$23` — current location name.** A runtime code: a line stored as
  `「<$23>への挑戦…` displays as `「武人の塔への挑戦…`, with the dungeon name
  pulled from the location table at `0x31000`.
- **Inline furigana.** Full-width parentheses (`（`=`01CA`, `）`=`01CB`) gloss a
  kanji with a non-standard reading: 運命（さだめ） — *write* 運命, *read*
  sadame. A nice touch for poetic/dramatic lines.

## Where things stand

**~286 of ~730 kanji codes** identified, plus the kana table, the
control/insertion codes, the furigana mechanism, the location table, and a
partial DTE dictionary. The fastest path to the rest is more
screenshot-cribbing; the "complete" path to the `$17` table is a bank-`$C0`
engine trace.

Recent batches kept proving the method: a town-NPC pass finally finished the
four compass directions (北 was the long-missing one), and a bar/cocktail line
*corrected* an earlier reading — `$025B` is 色 (*colour*), not 味 (*taste*). In
hindsight every one of its ~13 contexts is "the colour of the sky/water/sea
changed", squarely on the game's pollution theme. Ground truth wins again.

See [`../docs/encoding.md`](../docs/encoding.md) for the structural reference.
