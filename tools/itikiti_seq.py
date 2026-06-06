#!/usr/bin/env python3
"""itikiti_seq.py - Decoder della sequenza musicale "ItikitiSnes" (driver Square
SNES di Rudra no Hihou). Tabella opcode verificata su VGMTrans + dati reali.

Modello (ARAM 64KB):
  - Comandi  $00-$2F : (vedi CMD) param a lunghezza fissa.
  - Note     $30-$EF : key_index = byte>>3 ; durIdx = byte&7.
  - Ties     $F0-$F7 : legatura (sostiene nota prec.).
  - Rests    $F8-$FF : pausa.
    durIdx 0-6 -> NOTELEN[durIdx] ; durIdx 7 -> leggi byte extra (durata custom).

I cursori live dei 8 canali stanno in zero-page $20-$2F (word, little-endian):
parsando da li' si ottiene bytecode valido a meta' brano.

Uso:
  python tools/itikiti_seq.py DUMP.dmp [--events N] [--from $ADDR]
  python tools/itikiti_seq.py --hist spc/dumps/*.dmp     # istogramma opcode su piu' brani
"""
import sys, glob
from pathlib import Path

NOTELEN = [0xC0, 0x60, 0x48, 0x30, 0x24, 0x18, 0x0C]   # durIdx 0-6 ; 7 = byte extra
NOTE = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
# opcode -> (nome, n_param)
CMD = {
 0x00:("END",0),0x01:("MASTER_VOL",1),0x02:("ECHO_VOL",1),0x03:("CHANNEL_VOL",1),
 0x04:("ECHO_FB_FIR",2),0x05:("UNKNOWN0",0),0x06:("TEMPO",1),0x07:("TEMPO_FADE",2),
 0x08:("NOISE_FREQ",1),0x09:("SEL_NOTELEN",2),0x0A:("CUSTOM_NOTELEN",7),0x0B:("NOTE_NUM_BASE",1),
 0x0C:("VOLUME",1),0x0D:("VOL_FADE",2),0x0E:("PAN",1),0x0F:("PAN_FADE",2),
 0x10:("PROGRAM_CHANGE",1),0x11:("TUNING",1),0x12:("ADSR_AR",1),0x13:("ADSR_DR",1),
 0x14:("ADSR_SL",1),0x15:("ADSR_SR",1),0x16:("ADSR_DEFAULT",0),0x17:("TRANSPOSE_ABS",1),
 0x18:("TRANSPOSE_REL",1),0x19:("VIBRATO_ON",3),0x1A:("VIBRATO_OFF",0),0x1B:("TREMOLO_ON",3),
 0x1C:("TREMOLO_OFF",0),0x1D:("PAN_LFO_ON",2),0x1E:("PAN_LFO_OFF",0),0x1F:("NOISE_ON",0),
 0x20:("NOISE_OFF",0),0x21:("PITCHMOD_ON",0),0x22:("PITCHMOD_OFF",0),0x23:("ECHO_ON",0),
 0x24:("ECHO_OFF",0),0x25:("PORTAMENTO_ON",1),0x26:("PORTAMENTO_OFF",0),0x27:("SPECIAL",1),
 0x28:("NOTE_RAND_OFF",0),0x29:("PITCH_SLIDE",2),0x2A:("LOOP_START",1),0x2B:("UNKNOWN2",2),
 0x2C:("GOTO",2),0x2D:("UNDEFINED",2),0x2E:("LOOP_END",0),0x2F:("LOOP_BREAK",3),
}

def decode_one(d, i):
    """Ritorna (nbytes, kind, desc, opcode_o_None). kind: cmd/note/tie/rest."""
    b = d[i]
    if b < 0x30:
        nm, pl = CMD[b]
        args = " ".join(f"{d[i+1+k]:02X}" for k in range(pl))
        extra = f"  (={d[i+1]})" if pl == 1 else ""
        return 1+pl, "cmd", f"{nm} {args}{extra}".rstrip(), b
    # nota / tie / rest
    dur = b & 7
    n = 2 if dur == 7 else 1
    durtxt = f"len[{dur}]={NOTELEN[dur]}" if dur < 7 else f"len=custom({d[i+1]})"
    if b < 0xF0:
        k = b >> 3
        return n, "note", f"NOTE k{k}({NOTE[k%12]}) {durtxt}", None
    if b < 0xF8:
        return n, "tie", f"TIE {durtxt}", None
    return n, "rest", f"REST {durtxt}", None

def channels(d):
    """8 cursori live da ZP $20-$2F."""
    return [d[0x20+2*c] | d[0x21+2*c] << 8 for c in range(8)]

def dump_song(path, events, frm):
    d = Path(path).read_bytes()
    print(f"\n=== {Path(path).name} ===")
    cur = channels(d)
    print("cursori live ZP $20-$2F:", " ".join(f"${p:04X}" for p in cur))
    starts = [frm] if frm else cur
    for ci, start in enumerate(starts):
        if not (0x200 <= start < 0xFF00):
            print(f"  ch{ci}: cursore ${start:04X} fuori range, salto"); continue
        i = start; out = []
        for _ in range(events):
            n, kind, desc, op = decode_one(d, i)
            out.append(f"${i:04X} {kind[0]}:{desc}")
            i += n
            if op == 0x00: break   # END
        print(f"  ch{ci} @${start:04X}: " + " | ".join(out[:events]))

def histogram(paths):
    from collections import Counter
    cnt = Counter()
    for path in paths:
        d = Path(path).read_bytes()
        for start in channels(d):
            if not (0x200 <= start < 0xFF00): continue
            i = start
            for _ in range(400):
                n, kind, desc, op = decode_one(d, i)
                if kind == "cmd": cnt[op] += 1
                i += n
                if op == 0x00: break
    print("Istogramma opcode-comando su tutti i brani (op: nome  conteggio):")
    for op in sorted(cnt):
        print(f"  ${op:02X} {CMD[op][0]:16s} {cnt[op]}")
    used = set(cnt); allc = set(CMD)
    print("  -- comandi MAI visti:", " ".join(f"${o:02X}({CMD[o][0]})" for o in sorted(allc-used)))

def main():
    args = sys.argv[1:]
    if "--hist" in args:
        args.remove("--hist")
        paths = []
        for a in args: paths += glob.glob(a)
        histogram(paths); return
    events = 30; frm = None; files = []
    it = iter(args)
    for a in it:
        if a == "--events": events = int(next(it))
        elif a == "--from": frm = int(next(it).lstrip("$"), 16)
        else: files.append(a)
    for f in files:
        dump_song(f, events, frm)

if __name__ == "__main__":
    main()
