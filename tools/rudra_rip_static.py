#!/usr/bin/env python3
"""
rudra_rip_static.py - Estrattore audio 100% STATICO di Rudra no Hihou.

Ricostruisce l'immagine APU (ARAM 64KB) di OGNI brano leggendo SOLO la ROM +
le tabelle del sound driver. Niente emulatore, niente cattura live: dato il
template condiviso (un qualunque dump APU del gioco, per le parti comuni a tutti
i brani) e la ROM, sforna un .spc per ogni brano. Output -> VGMTrans -> MIDI/SF2.

NB ETICO: la ROM NON e' inclusa (vedi DISCLAIMER.md): forniscila tu via env
RUDRA_ROM o ./rom/. Il "template" e' un dump APU che catturi TU dalla tua copia.
Nessun dato audio del gioco e' contenuto qui: solo il formato e il metodo.

--- FORMATO STATICO (reverse-engineered, validato byte-per-byte) -------------
1. Liste brani: 3 tabelle di puntatori 24-bit (id*3, banco via &$3F|$C0):
   type0 $EB2558 = map-theme / brani lunghi (il cuore dell'OST);
   type1 $EB266C = jingle brevi; type2 $EB2969 = SFX (formato diverso).
2. Header brano @ table[id]: [size_word LE:2][payload di `size` byte].
   dest ARAM = $CD00 - size  (TUTTI i brani finiscono a $CD00). Payload =
   [04][N=n.tracce][N x 2-byte track-ptr bank-relative][bytecode Itikiti inline].
3. Lista strumenti = i 16 byte SUBITO PRIMA dell'header (0-terminata, max 16 id).
4. Campioni (pool globale, 4 tabelle parallele per id, N=66):
   source  $EB296C (24-bit) -> punta a [size:2][BRR:size] in ROM;
   loop    $EB2A33 (16-bit LE)        -> loop_aram = sample_start + questo;
   tuning  $EB2AB7 (16-bit BIG-ENDIAN, e' la getShortBE di VGMTrans);
   adsr    $EB2B3B (2 byte).
   I BRR (= rom[src+2 : src+2+size]) si impacchettano in ARAM da $25E6, in
   ordine di lista; usano dir-index da 32 in su.
5. Sample-directory DSP @ $1B00 (4 byte/voce: [start:2][loop:2]); tabella tuning
   @ $1D40 e ADSR @ $1E60 (2 byte/voce) -> sono i 3 parametri InstrSet di
   VGMTrans (0x1d40, 0x1e60, 0x1b00).
6. Puntatore-brano che VGMTrans legge: la sua signature engine porta a $ED80,
   dove sta header_end = dest + 2 + N*2. Va scritto o VGMTrans non apre il file.

Uso:
  python tools/rudra_rip_static.py blocks   <dump.dmp>        # mappa-blocchi empirica
  python tools/rudra_rip_static.py coverage <dump.dmp>        # quanto e' verbatim da ROM
  python tools/rudra_rip_static.py build <id_hex> <template.dmp> <out.spc>
  python tools/rudra_rip_static.py batch <template.dmp> <out_dir>   # tutti i type0
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# La ROM NON e' inclusa nel repo. Fornisci la TUA copia:
#   RUDRA_ROM=/percorso/Rudra no Hihou (Japan).sfc   oppure   ./rom/<file>.sfc
ROM = Path(
    os.environ.get(
        "RUDRA_ROM",
        ROOT / "rom" / "Rudra no Hihou (Japan).sfc",
    )
)

# Regione dati per-brano nell'ARAM (sotto: engine condiviso; sopra: echo/IO).
DATA_LO = 0x1B00
DATA_HI = 0xCD20
MIN_BLOCK = 12          # run piu' corti = falsi positivi casuali


def snes_addr(fileoff):
    """file offset HiROM -> stringa $BB:AAAA."""
    return "$%02X:%04X" % (0xC0 + (fileoff >> 16), fileoff & 0xFFFF)


def discover_blocks(rom, aram, lo=DATA_LO, hi=DATA_HI):
    """Segmenta [lo,hi) dell'ARAM in run verbatim trovati nella ROM.
    Ritorna lista di (dest_aram, length, src_fileoff)."""
    blocks = []
    o = lo
    while o < hi:
        if aram[o] == 0:                       # salta zero-fill
            while o < hi and aram[o] == 0:
                o += 1
            continue
        if o + 16 > len(aram):
            break
        L, src = _longest_match(rom, aram, o)
        if src < 0 or L < MIN_BLOCK:
            o += 1
            continue
        blocks.append((o, L, src))
        o += L
    return blocks


def _longest_match(rom, aram, off, seedlen=16, max_tries=200):
    """Trova dove aram[off:off+seedlen] appare in ROM, scegliendo
    l'occorrenza che si estende piu' a lungo. Ritorna (length, src)."""
    seed = aram[off:off + seedlen]
    best = (0, -1)
    i = rom.find(seed)
    tries = 0
    while i >= 0 and tries < max_tries:
        L = seedlen
        while off + L < len(aram) and i + L < len(rom) and aram[off + L] == rom[i + L]:
            L += 1
        if L > best[0]:
            best = (L, i)
        i = rom.find(seed, i + 1)
        tries += 1
    return best


def cmd_blocks(dump_path):
    rom = ROM.read_bytes()
    aram = Path(dump_path).read_bytes()
    blocks = discover_blocks(rom, aram)
    print("# Mappa-blocchi VERBATIM di %s" % Path(dump_path).name)
    print("# %-12s %-7s %s" % ("dest_ARAM", "len", "src_ROM"))
    tot = 0
    for d, L, s in blocks:
        tot += L
        print("  $%04X        %5d   %06X (%s)" % (d, L, s, snes_addr(s)))
    print("# %d blocchi, %d byte verbatim" % (len(blocks), tot))


def cmd_coverage(dump_path):
    rom = ROM.read_bytes()
    aram = Path(dump_path).read_bytes()
    blocks = discover_blocks(rom, aram)
    recon = bytearray(DATA_HI)
    covered = bytearray(DATA_HI)
    for d, L, s in blocks:
        recon[d:d + L] = rom[s:s + L]
        for i in range(d, d + L):
            covered[i] = 1
    mism = uncov = 0
    runs = []
    i = DATA_LO
    while i < DATA_HI:
        if covered[i]:
            if recon[i] != aram[i]:
                mism += 1
            i += 1
        elif aram[i] != 0:
            start = i
            while i < DATA_HI and not covered[i] and aram[i] != 0:
                i += 1
            uncov += i - start
            runs.append((start, i - start))
        else:
            i += 1
    print("blocchi: %d   byte verbatim: %d" % (len(blocks), sum(L for _, L, _ in blocks)))
    print("mismatch su byte coperti: %d   (atteso 0)" % mism)
    print("byte non-zero NON coperti (calcolati dal loader): %d" % uncov)
    print("cluster non-coperti principali (regione sample-dir/strumenti):")
    for s, l in sorted(runs, key=lambda x: -x[1])[:10]:
        print("   $%04X len %4d  %s" % (s, l, aram[s:s + min(l, 8)].hex()))


# ============================================================================
# RICOSTRUZIONE 100% DA ROM (formato statico craccato)
# ============================================================================
# Tabelle globali (file offset HiROM), N=66 strumenti, indicizzate per id:
TBL_TYPE0 = 0xEB2558   # lista brani map-theme/lunghi (ptr 24-bit, id*3)
TBL_SRC   = 0xEB296C   # source BRR 24-bit -> [size:2][BRR:size] in ROM
TBL_LOOP  = 0xEB2A33   # loop-offset 16-bit (loop_aram = start + questo)
TBL_TUNE  = 0xEB2AB7   # tuning/pitch 16-bit BIG-ENDIAN (VGMTrans: getShortBE)
TBL_ADSR  = 0xEB2B3B   # ADSR 2 byte
SMP_BASE  = 0x25E6     # ARAM: inizio campioni per-brano (impacchettati)
DIR_BASE  = 0x1B00     # ARAM: sample-directory DSP (4 byte/voce)
TUNE_ARAM = 0x1D40     # ARAM: tabella tuning (2 byte/voce, InstrSet param 1)
ADSR_ARAM = 0x1E60     # ARAM: tabella ADSR (2 byte/voce, InstrSet param 2)
TOP       = 0xCD00     # ARAM: tutti i brani finiscono qui (dest = TOP - size)
PERSONG_DIR0 = 32      # i sample per-brano partono da dir-index 32


def _rom(): return ROM.read_bytes()
def _f(p): return ((p >> 16 & 0x3F) << 16) | (p & 0xFFFF)
def _r24(b, o): return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)
def _r16(b, o): return b[o] | (b[o + 1] << 8)


def reconstruct(rom, song_id, template):
    """Ricostruisce l'ARAM 64KB di un brano (type0 song_id) da ROM, usando
    `template` (un dump ARAM) per le parti CONDIVISE (engine, boot, costanti).
    Ritorna (aram bytearray, info dict)."""
    aram = bytearray(template)
    hdr = _f(_r24(rom, _f(TBL_TYPE0) + song_id * 3))
    size = _r16(rom, hdr)
    payload = rom[hdr + 2:hdr + 2 + size]
    dest = TOP - size
    # lista strumenti = 16 byte prima dell'header, 0-terminata
    ilist = []
    for b in rom[hdr - 16:hdr]:
        if b == 0:
            break
        ilist.append(b)
    # --- pulisci le regioni per-brano del template ---
    for a, b in [(SMP_BASE, TOP - 0x0100), (0xC000, TOP)]:   # campioni + sequenza
        aram[a:b] = b"\x00" * (b - a)
    # --- campioni + dir + tuning + ADSR ---
    a = SMP_BASE
    for i, idv in enumerate(ilist):
        src = _f(_r24(rom, _f(TBL_SRC) + idv * 3))
        ssize = _r16(rom, src)                       # size = parola in testa al blocco
        aram[a:a + ssize] = rom[src + 2:src + 2 + ssize]
        di = DIR_BASE + (PERSONG_DIR0 + i) * 4
        loop = a + _r16(rom, _f(TBL_LOOP) + idv * 2)
        aram[di:di + 4] = bytes([a & 0xFF, a >> 8, loop & 0xFF, loop >> 8])
        ai = ADSR_ARAM + (PERSONG_DIR0 + i) * 2
        aram[ai:ai + 2] = rom[_f(TBL_ADSR) + idv * 2:_f(TBL_ADSR) + idv * 2 + 2]
        ti = TUNE_ARAM + (PERSONG_DIR0 + i) * 2       # tuning (BE, copia verbatim)
        aram[ti:ti + 2] = rom[_f(TBL_TUNE) + idv * 2:_f(TBL_TUNE) + idv * 2 + 2]
        a += ssize
    # --- sequenza ---
    aram[dest:dest + size] = payload
    # --- puntatore-brano che VGMTrans legge: $ED80 = header_end = dest+2+N*2 ---
    # (ItikitiSnesScanner: header_ptr=readShort(code+6)=$ED80; header_end=readShort($ED80))
    ntracks = payload[1]
    header_end = dest + 2 + ntracks * 2
    aram[0xED80] = header_end & 0xFF
    aram[0xED81] = header_end >> 8
    info = dict(song_id=song_id, header=hdr, size=size, dest=dest,
                instruments=ilist, smp_end=a, ntracks=ntracks, header_end=header_end)
    return aram, info


def _load_spc_wrap():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sw", str(ROOT / "tools" / "spc_wrap.py"))
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    return sw


def cmd_build(song_id_hex, template_path, out_spc):
    rom = _rom()
    template = Path(template_path).read_bytes()
    sid = int(song_id_hex, 16)
    aram, info = reconstruct(rom, sid, template)
    print("type0 id$%02X: hdr $%06X size %d dest $%04X | %d strumenti=%s"
          % (sid, info["header"], info["size"], info["dest"],
             len(info["instruments"]), " ".join("%02X" % b for b in info["instruments"])))
    # sanity: se il template e' lo STESSO brano, le regioni RICOSTRUITE devono
    # combaciare (le altre = SFX/residui non modellati, attesi diversi).
    rebuilt = sum(1 for i in range(SMP_BASE, info["smp_end"]) if aram[i] != template[i])
    rebuilt += sum(1 for i in range(info["dest"], TOP) if aram[i] != template[i])
    for i in range(len(info["instruments"])):
        d = DIR_BASE + (PERSONG_DIR0 + i) * 4
        rebuilt += sum(1 for k in range(4) if aram[d + k] != template[d + k])
    print("regione campioni $%04X-$%04X (%d byte) + sequenza + dir + ADSR"
          % (SMP_BASE, info["smp_end"], info["smp_end"] - SMP_BASE))
    print("diff regioni-ricostruite vs template stesso-brano: %d byte (atteso 0)" % rebuilt)
    Path(out_spc).write_bytes(_load_spc_wrap().build_spc(bytes(aram)))
    print("scritto %s" % out_spc)


def _valid_song(rom, table, sid):
    """Heuristica: la voce (table, sid) sembra un brano valido?
    NB: nessun lower-bound su dest — i brani lunghi (boss-theme!) caricano sotto
    $C000, e' normale. L'unico vincolo reale (campioni che non invadano la
    sequenza) e' verificato a build-time nel batch (overlap)."""
    h = _f(_r24(rom, _f(table) + sid * 3))
    if h + 3 >= len(rom):
        return None
    size = _r16(rom, h)
    if not (8 <= size <= 0x2000):
        return None
    n = rom[h + 3]
    if not (1 <= n <= 8):
        return None
    il = []
    for b in rom[h - 16:h]:
        if b == 0:
            break
        il.append(b)
    if len(il) > 16:
        return None
    return dict(size=size, ntracks=n, ninstr=len(il))


def cmd_batch(template_path, out_dir):
    """Rippa TUTTI i brani type0 validi -> .spc in out_dir (da sola ROM)."""
    rom = _rom()
    template = Path(template_path).read_bytes()
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)
    sw = _load_spc_wrap()
    done = warn = 0
    for sid in range(96):
        if not _valid_song(rom, TBL_TYPE0, sid):
            continue
        aram, info = reconstruct(rom, sid, template)
        overlap = info["smp_end"] > info["dest"]      # campioni invadono la sequenza?
        name = "t0_%02X.spc" % sid
        (outp / name).write_bytes(sw.build_spc(bytes(aram)))
        flag = "  ** SAMPLE/SEQ OVERLAP" if overlap else ""
        print("  %s  size %4d  %d tracce  %2d strum  campioni->$%04X  dest $%04X%s"
              % (name, info["size"], info["ntracks"], len(info["instruments"]),
                 info["smp_end"], info["dest"], flag))
        done += 1
        warn += 1 if overlap else 0
    print("\n%d brani type0 scritti in %s  (%d con overlap da rivedere)" % (done, out_dir, warn))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "blocks":
        cmd_blocks(sys.argv[2])
    elif cmd == "coverage":
        cmd_coverage(sys.argv[2])
    elif cmd == "build":               # build <id_hex> <template.dmp> <out.spc>
        cmd_build(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "batch":               # batch <template.dmp> <out_dir>
        cmd_batch(sys.argv[2], sys.argv[3])
    else:
        print("comando ignoto:", cmd)
        print(__doc__)


if __name__ == "__main__":
    main()
