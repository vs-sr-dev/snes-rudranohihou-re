#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rudra_text.py — tabella di codifica + estrattore testo per
Rudra no Hihou / Treasure of the Rudras (SNES, Square).

Mappa ricavata in reverse (sessione 2): sillabario JP completo,
validato su screenshot + sito JP + tabelle dati. Vedi memoria
kanji-cracking-progress.

Uso:
  python rudra_text.py tbl                 -> scrive docs/rudra-jap.tbl
  python rudra_text.py dump START END      -> dumpa messaggi (offset hex)
  python rudra_text.py find "かな..."        -> cerca una stringa kana e dumpa il messaggio
Regioni testo note (file offset):
  dialoghi A: 0x30A000-0x348000   ($F0:A000)
  dialoghi B: ~0x3A6000-0x3D5000  ($FA:6000)
  menu/sistema: ~0x32E00 / descr.magie ~0x309700 / località ~0x31248

NOTA: la ROM NON è inclusa in questo repo (vedi DISCLAIMER.md). Procurati la
tua copia legale e indicala via env var RUDRA_ROM o mettila in ./rom/.
"""
import os
import sys
from pathlib import Path

# La ROM NON è inclusa nel repo. Fornisci la TUA copia:
#   RUDRA_ROM=/percorso/Rudra no Hihou (Japan).sfc   oppure   ./rom/<file>.sfc
ROM_PATH = Path(
    os.environ.get(
        "RUDRA_ROM",
        Path(__file__).resolve().parent.parent / "rom" / "Rudra no Hihou (Japan).sfc",
    )
)

# ---------------------------------------------------------------- sillabario
HIRA  = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"  # $2A
DHIRA = "がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽ"                                    # $58
SMALL = "ぁぃぅぇぉっ"                                                                  # $71
YOUON = "ゃゅょ"                                                                       # $77
KATA  = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"  # $7B
DKAT  = "ガギグゲゴザジズゼゾダヂヅデドバビブベボ"                                            # $A9
HKAT  = "パピプペポ"                                                                    # $BD
SKAT  = "ァィゥェォッャュョ"                                                              # $C2

def build_charmap():
    m = {}
    for i, c in enumerate(HIRA):  m[0x2A + i] = c
    for i, c in enumerate(DHIRA): m[0x58 + i] = c
    for i, c in enumerate(SMALL): m[0x71 + i] = c
    for i, c in enumerate(YOUON): m[0x77 + i] = c
    m[0x7A] = "ー"
    for i, c in enumerate(KATA):  m[0x7B + i] = c
    for i, c in enumerate(DKAT):  m[0xA9 + i] = c
    for i, c in enumerate(HKAT):  m[0xBD + i] = c
    for i, c in enumerate(SKAT):  m[0xC2 + i] = c
    m[0xCB] = "ヴ"   # katakana vu (da ·CBァド = ヴァド, sess.3)
    m.update({0x19: "。", 0x1A: "、", 0x1B: "？", 0x1C: "！", 0x1F: "…"})
    return m

CHARS = build_charmap()

# 2-byte kanji: chiave = (lead, idx) -> glifo.  Lead $01/$02/$03.
KANJI = {
    (1,0x01):"言",(2,0x39):"修",(1,0x04):"行",(1,0x24):"教",(1,0x59):"団",(1,0x64):"員",
    (1,0x53):"奴",(2,0xD1):"野",(3,0x1D):"郎",(1,0x29):"来",(1,0x69):"帰",(1,0x09):"様",
    (1,0xC3):"門",(2,0x33):"旅",(1,0xFE):"立",(1,0x44):"日",(1,0x33):"属",(1,0x31):"性",
    (2,0x06):"与",(1,0x62):"火",(1,0x28):"水",(1,0xD3):"雷",(1,0xC0):"風",(1,0xEB):"陽",
    (2,0x1A):"陰",(1,0x4F):"無",(1,0x46):"遺",(1,0x4A):"跡",(1,0x21):"聖",(1,0x5D):"域",
    (1,0xE5):"砂",(2,0x4A):"漠",(1,0x16):"地",(2,0x7E):"面",(1,0x20):"時",(2,0x12):"計",
    (1,0x37):"塔",(2,0xC8):"呪",(2,0x85):"術",(1,0x42):"師",(2,0xF3):"樹",(1,0x34):"海",
    (1,0x6E):"家",(1,0xD1):"東",(1,0x08):"大",(1,0x72):"陸",(1,0xE6):"金",(1,0x19):"持",
    (1,0x45):"王",(2,0xB2):"父",(1,0x2F):"知",(1,0x6B):"合",
    # --- sessione 3 (screenshot Sion/Foxy, 武人の塔) ---
    (1,0x02):"人",(1,0x0F):"戦",(1,0x86):"挑",(1,0x1C):"生",(1,0x15):"神",
    (1,0x8B):"次",(2,0x13):"代",(1,0xF8):"信",(3,0x92):"仰",
    # --- sessione 3 (screenshot soldato + bauli) ---
    (1,0x6C):"場",(1,0x3D):"所",(1,0x10):"私",(1,0x79):"剣",(2,0x69):"腕",
    (1,0x35):"前",(1,0x9B):"宝",(1,0xBA):"箱",(1,0xB5):"開",(1,0x0A):"見",
    # --- sessione 3 (scena re Kryuune: udienza Sion) ---
    (1,0x07):"者",(1,0x7E):"伝",(1,0x93):"取",(1,0xDC):"調",(2,0x90):"説",
    (1,0x81):"明",(1,0x12):"間",(1,0x55):"先",(2,0x71):"室",(1,0xD0):"急",
    (2,0x18):"逃",(1,0xF3):"臣",
    # --- sessione 3 (Sion sfida + allarme cultista) ---
    # NB: 0239=修 0104=行 sono CORREZIONI (sess.2 li diceva 汚/染, ERRATO):
    # screenshot mostra 修行 (shugyou) a quei byte; conferma 修行をつむ/修行場.
    (1,0x92):"隊",(1,0x23):"長",(2,0x28):"負",(1,0x63):"勝",(1,0x5C):"自",
    (1,0x51):"変",(2,0xEB):"脱",(3,0x59):"走",
    # --- sessione 3 (tabella-localita + volantino + battaglia + Torre Giganti) ---
    (1,0x2C):"武",(1,0x52):"巨",(1,0x1F):"力",(1,0x5E):"山",(1,0x9C):"城",
    (1,0x11):"町",(1,0x1B):"今",(1,0x98):"後",(2,0x1F):"追",(2,0x07):"勇",
    (2,0x5D):"番",(2,0xA1):"弟",(1,0x38):"子",(1,0x0E):"出",(2,0x3A):"身",
    (1,0x17):"手",(1,0x82):"乗",(2,0x99):"込",
    # 汚染 RISOLTO: 汚=013C (汚れた/汚染の海), 染=014B (汚染される). NON 0239/0104!
    (1,0x3C):"汚",(1,0x4B):"染",
    # --- sessione 3 (overlay TRAMA Torre Giganti + monologo cultista; stesso banco @0x33E028) ---
    (1,0x4C):"種",(1,0x0C):"族",(1,0x2E):"滅",(1,0xBC):"破",(1,0xF4):"壊",
    (2,0x34):"始",(2,0x23):"祖",(3,0x00):"周",(1,0xA0):"期",(1,0xAC):"現",
    (3,0x1F):"静",(1,0x56):"光",(2,0x54):"数",(1,0x7F):"博",(1,0x3A):"士",
    (1,0x25):"石",(1,0xA3):"発",(2,0x0E):"敵",(2,0x01):"飛",(1,0x90):"作",
    (3,0x5E):"図",(1,0xA8):"当",(1,0x27):"入",(1,0xC8):"同",(1,0xA9):"然",
    (1,0x8A):"我",(1,0x76):"年",  # 年=0176 (4000年/数年前/年前から)
    # --- sessione 3 (scena boss スルト / culto) ---
    (1,0x43):"一",(1,0x05):"何",(1,0xD5):"運",(1,0x5A):"命",(1,0x3B):"待",
    (2,0x2E):"違",
    # --- sessione 3 (cutscene Torre Giganti: Rostam/Huey/Sion) ---
    (1,0x39):"屋",(1,0x22):"上",(1,0xCC):"以",(1,0x6A):"外",(1,0x0B):"気",
    (1,0xD2):"配",(1,0xAB):"感",(1,0xA7):"仲",(1,0x99):"落",(1,0xAA):"復",
    (1,0xEC):"活",(1,0x65):"老",(1,0x1E):"空",
    # 〔011E〕〔010B〕=空気 (tema inquinamento: 空気・水・海が汚染される)
    (1,0x61):"目",  # 目=0161 (目を/目がーっ; anche 目に見えない nel baule sigillato)
    # --- sessione 3 (scenario RIZA, scena iniziale con ゼクウ) ---
    (1,0x13):"世",(1,0x1D):"界",(1,0xF0):"終",(1,0xB1):"近",(1,0x60):"全",
    (1,0x4D):"救",(2,0xEC):"求",(2,0x44):"声",(1,0x57):"聞",(1,0x48):"使",
    (1,0x3E):"星",(2,0x5F):"美",(2,0x6E):"昔",
    # furigana/gikun inline: 運命（さだめ） -> 01CA=（ 01CB=） (parentesi full-width)
    (1,0xCA):"（",(1,0xCB):"）",
    # --- sessione 3 (RIZA: discorso ゼクウ + profezia dei 3 eletti) ---
    (1,0xDA):"実",(1,0xF7):"母",(3,0x1A):"親",(2,0x41):"村",(1,0xB2):"印",
    (2,0x67):"埋",(1,0xFB):"導",(1,0x36):"主",(3,0x3D):"証",(1,0xCE):"闇",
    (1,0x54):"底",(1,0x2D):"中",(2,0x3D):"青",
    # --- sessione 3 (RIZA: monologo ゜ゼクウ + profezia-libro + magia) ---
    (1,0x32):"化",(1,0xC9):"再",(2,0x9E):"覚",(2,0x9C):"絶",(1,0x8F):"亡",
    (1,0x2A):"体",(1,0x9E):"宿",(2,0x00):"選",(1,0x71):"道",(1,0x26):"方",
    (2,0xC2):"単",(1,0x68):"話",(1,0x78):"予",(1,0x40):"書",(1,0x58):"最",
    (2,0x37):"葉",(1,0x03):"言",  # 0103=言 (2° codice, lessicale; 0101=言 kotodama-marker)
    # 浄化=〔$17 F7=浄〕+〔0132=化〕; 汚染⇄浄化 risolti
    # --- sessione 3 (NPC città カーン di Riza) ---
    (2,0xCF):"僧",(3,0x63):"侶",(2,0x0C):"理",(1,0x30):"魔",(1,0x14):"物",
    (2,0xAD):"森",(1,0x7C):"南",
    # --- sessione 3 (SURLENT: scena iniziale ラゴウ石研究所, ミュンヒ博士) ---
    (3,0x11):"表",(1,0xFD):"呼",(2,0x47):"君",(1,0x41):"思",(1,0x7A):"強",
    (1,0xE8):"確",(2,0xC5):"特",(2,0x09):"玉",(1,0x18):"事",(2,0x74):"側",
    (2,0x0D):"古",(1,0xF5):"文",(2,0x6B):"字",(1,0xAF):"研",(1,0xAD):"究",
    (2,0xC9):"危",(3,0x03):"険",(2,0x14):"考",(1,0x4E):"殿",(2,0x88):"借",
    # NB: 文=01F5 (kanji) ≠ DTE $17 F5=流 (namespace diversi)
    # --- sessione 3 (SURLENT: seguito scena research lab) ---
    (2,0x57):"掘",(2,0xE8):"千",(2,0x9D):"万",(1,0xF6):"関",(2,0x66):"係",
    (3,0x3A):"環",(3,0x21):"境",(1,0x96):"受",(1,0x9F):"通",(1,0x80):"杯",
    # NB: 関=01F6 (kanji) ≠ DTE $17 F6=死
    # --- sessione 3 (SURLENT: 竜神の遺跡 ->洋館エレミア) ---
    (2,0xD3):"竜",(2,0xA4):"洋",(2,0x24):"館",(1,0xE7):"西",(1,0xF2):"住",
    (1,0x50):"船",(2,0xCC):"紋",(2,0xA5):"章",(1,0x89):"虫",(1,0x85):"類",
    # --- sessione 3 (SURLENT: menu equip, descrizioni) ---
    (1,0xAE):"両",(1,0x49):"帯",(1,0xB7):"片",(1,0x0D):"霊",(1,0x5B):"用",
    (2,0x5A):"衣",  # 〔0103〕〔010D〕=言霊 (kotodama!) = top compound 210×
    # --- sessione 6 (animali parlanti + negozio armi + volantino じょうかやく) ---
    (1,0xB9):"動",  # 動物 (お話ができる動物) - cane parlante
    (1,0xBE):"器",(1,0xC1):"防",(1,0x97):"具",  # 武器屋 / 防具 (negozio armi); 具 anche 道具
    (2,0x0F):"真",(2,0xE9):"黒",  # 真っ黒 (volantino: 体が真っ黒で)
    (3,0x2F):"品",  # 品うす(品薄) = scorte basse
    (2,0xB5):"治",  # 治る (じょうかやく=浄化薬で治る)
    (2,0xB9):"安",(1,0x8D):"心",  # ご安心を; 心=018D freq 372
    (1,0xA5):"装",(1,0xA1):"備",  # 装備 (陰属性の防具を装備しておくと)
    (2,0x5B):"味",  # 水の味がかわった (tema 汚染↔浄化: acqua tornata buona)
    (1,0xE9):"引",  # 引き出しの中に… (cassetto)
    (3,0xA7):"厳",  # tentativo: 道のりは厳しいものになる (unico contesto; vs 難/苦)
}
# NB: alcune (lead,idx) collidono fra tabelle diverse del gioco (es. 0133 sia 旅/属):
# qui il dizionario tiene l'ultima; per il dump distinguiamo via lead reale dei byte.

# ---- dizionario $12 (pool sequenziale, NO pointer-table) ----
# Il motore conta i terminatori $00: 〖XX〗 = la XX-esima stringa del pool,
# che parte da 0x31608 (シオン=0).  Nomi personaggi + frasi comuni.
# NB CALIBRAZIONE: enumerazione kanji-aware -> i NOMI sono esatti (ダグ=0x11,
# エレミア=0x1E...); le FRASI vicine alle voci 〔0100〕…言 possono slittare di ~1
# (es. じゃない reale=0x44, qui 0x43) per come il motore conta i $00 dentro $01$00.
DICT12_BASE = 0x31608

def build_dict12(data):
    d = {}; o = DICT12_BASE; idx = 0
    while idx < 0x70 and o < 0x31c80:
        while o < len(data) and data[o] == 0: o += 1
        s = o
        while o < len(data) and data[o] != 0:
            o += 2 if data[o] in (1, 2, 3) else 1
        if o > s: d[idx] = decode(data, s, o); idx += 1
        o += 1
    return d

_DICT12 = None

# ---- dizionario $17 (DTE / macro sotto-stringhe) ----
# $17 XX espande una sotto-stringa comune (1 codice -> ~2 char di testo,
# anche kanji interi).  La tabella NON e' in chiaro nella ROM (le espansioni
# non compaiono come kana-code contigui): vive impacchettata nel motore testo
# (banco $C0) e va letta via trace.  Questi valori sono CRIB-da-grammatica
# (sessione 3), confermati su piu' occorrenze:
DICT17 = {
    0x1A: "かま",   # 教団員のなかま / つかまえた / つかまえなければ
    0x91: "やり",   # むりやり(無理矢理) / やりなおし / させて~たい
    0x43: "うで",   # そ~す = そうです / そうですね / そうですよ
    0xF6: "死",     # 死ぬ / 死んだ / 死なん / 死ねーっ
    0xF7: "浄",     # 〔dte:F7〕化される = 浄化される (RISOLTO sess.3: 浄, NON 汚!). 化=0132
    # (0xF7=浄 definito sopra; 浄化される. 126× = top DTE, RISOLTO sess.3)
    0xDD: "殺",     # 奴らを殺ってから / 殺られたら / 殺る！ (slang yakuza)
    0xF5: "流",     # 水の流れ / 流れていく / 洗い流して / 水が流れてて
}

# control / macro codes (1 byte; alcuni consumano 1 byte-argomento)
CTRL = {
    0x00:("END",   0), 0x04:("\n",    0), 0x06:("",     0), 0x18:("",   0),
    0x1D:("",      0), 0x1E:("",      0), 0x11:("「",    0), 0x05:(" / ", 0),
    0x08:("",      0),
    0x12:("〖名:%02X〗", 1),   # codice nome (+1 byte indice)
    0x17:("〔dte:%02X〕", 1),   # dizionario sotto-stringhe / DTE (+1 byte)
}

def decode(data, start, end):
    """Decodifica data[start:end] in testo leggibile."""
    out = []
    i = start
    while i < end:
        b = data[i]
        if b in (1, 2, 3) and i + 1 < end:        # kanji 2-byte
            out.append(KANJI.get((b, data[i+1]), f"〔{b:02X}{data[i+1]:02X}〕"))
            i += 2
        elif b == 0x12 and i + 1 < end:          # dizionario $12 -> nome/frase
            a = data[i+1]
            if _DICT12 is not None and a in _DICT12:
                out.append("《%s》" % _DICT12[a])
            else:
                out.append("〖%02X〗" % a)
            i += 2
        elif b == 0x17 and i + 1 < end:          # DTE / macro sotto-stringhe
            a = data[i+1]
            out.append(DICT17.get(a, "〔dte:%02X〕" % a))
            i += 2
        elif b in CTRL:
            label, arg = CTRL[b]
            if arg:
                a = data[i+1] if i+1 < end else 0
                out.append(label % a); i += 2
            else:
                out.append(label); i += 1
        else:
            out.append(CHARS.get(b, f"·{b:02X}"))
            i += 1
    return "".join(out)

def msg_at(data, off):
    """Estrae il messaggio (delimitato da $00, kanji-aware) attorno a off."""
    s = off
    while s > 0 and data[s-1] != 0x00:
        s -= 1
    e = off
    while e < len(data) and data[e] != 0x00:
        if data[e] in (1, 2, 3):   # salta il 2° byte del kanji (può essere $00)
            e += 2
        else:
            e += 1
    return s, decode(data, s, e)

def write_tbl(path):
    lines = ["# Rudra no Hihou - tabella codifica JP (reverse sessione 2)"]
    for code in sorted(CHARS):
        lines.append(f"{code:02X}={CHARS[code]}")
    for (lead, idx), g in sorted(KANJI.items()):
        lines.append(f"{lead:02X}{idx:02X}={g}")
    for code, (lab, arg) in sorted(CTRL.items()):
        nm = {0x00:"<END>",0x04:"<NL>",0x12:"<NAME>",0x17:"<DTE>",0x11:"<QUOTE>",0x05:"<SEP>"}.get(code, f"<ctrl{code:02X}>")
        lines.append(f"/{code:02X}={nm}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"scritto {path}  ({len(CHARS)} kana + {len(KANJI)} kanji + {len(CTRL)} ctrl)")

def enc_kana(s):
    rev = {v: k for k, v in CHARS.items()}
    return bytes(rev[c] for c in s)

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    rom = ROM_PATH.read_bytes()
    global _DICT12
    _DICT12 = build_dict12(rom)        # carica il dizionario nomi/frasi $12
    cmd = sys.argv[1]
    if cmd == "tbl":
        out = Path(__file__).resolve().parent.parent / "docs" / "rudra-jap.tbl"
        out.parent.mkdir(exist_ok=True)
        write_tbl(out)
    elif cmd == "dump":
        a, b = int(sys.argv[2], 16), int(sys.argv[3], 16)
        i = a
        while i < b:
            if rom[i] == 0: i += 1; continue
            s, m = msg_at(rom, i)
            if m.strip(): print(f"{s:06X}: {m}")
            # avanza oltre il messaggio
            while i < b and rom[i] != 0:
                i += 2 if rom[i] in (1,2,3) else 1
            i += 1
    elif cmd == "find":
        pat = enc_kana(sys.argv[2])
        i = rom.find(pat)
        if i < 0: print("non trovato"); return
        s, m = msg_at(rom, i)
        print(f"{s:06X}: {m}")
    else:
        print(__doc__)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
