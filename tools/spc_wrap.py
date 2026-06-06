#!/usr/bin/env python3
"""
spc_wrap.py - Avvolge l'immagine RAM dell'APU (64KB) di Rudra in un file .spc
(formato ID666 v0.30) riproducibile in qualunque player SPC / VGMTrans.

L'input e' la RAM SPC catturata mentre la musica suonava (dump Mesen) oppure
la ricostruzione statica. Quel dump NON contiene i registri DSP ne' lo stato
CPU SPC700: li seminiamo qui con valori RICAVATI DAL CODICE DEL DRIVER, non
indovinati:

  PC  = $03A5  testa del loop principale del motore AKAO (re-entrante: carica
               A da $F4, non dipende da A/X/Y in ingresso). Vedi disasm.
  SP  = $EF    stack in pagina 1, ampio; il loop bilancia PUSH/POP/CALL.
  PSW = $00    P=0 (il boot fa CLRP), cosi' $F4/$FD = porte I/O in $00xx.

  DSP DIR  ($5D) = $1B   directory campioni BRR a $1B00 (init immediato @E02D)
  DSP MVOL ($0C/$1C)=$7F volume principale L/R (init immediato @E066/E06C)
  DSP FLG  ($6C) = $20   echo-write disabilitato al primo frame (anti-garbage)
  Gli altri registri DSP (KON/KOF/EON/PMON/NON/EVOL e i per-voce) vengono
  riscritti ogni frame dall'update-loop ($03CC) -> si auto-riparano.

Uso:
  python tools/spc_wrap.py [input.bin|input.dmp] [output.spc]
  default: spc/rudra-spc700.bin -> spc/rudra.spc
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- parametri ricavati dal disasm (vedi docstring) ---
# $037D = entry di avvio-riproduzione: MOV X,#$FF / MOV SP,X / JMP $03AC.
# Imposta SP da solo E scrive $CE in $1F80 (flag "musica attiva") prima del
# loop timer -> ripartenza robusta. (Entrare da $03A5 saltava la scrittura di
# $1F80 e la musica si fermava dopo un tick.)
PC  = 0x037D
SP  = 0xFF
REG_A = REG_X = REG_Y = 0x00
PSW = 0x00
DSP = {0x0C: 0x7F, 0x1C: 0x7F, 0x5D: 0x1B, 0x6C: 0x20}

# Registri timer/controllo SMP ($F0-$FF): NON sono RAM vera, un dump-memoria li
# rilegge come 0 -> i timer restano spenti e il loop a $03B1 (che aspetta $FD)
# non avanza mai = silenzio. Valori reali ricavati dall'init del driver @E005-E00E:
#   MOV $F1,#$F0 ; MOV $FA,#$27 ; MOV $FB,#$00 ; MOV $F1,#$03 (abilita T0+T1)
TIMER = {0xF1: 0x03, 0xFA: 0x27, 0xFB: 0x00}

MAGIC = b"SNES-SPC700 Sound File Data v0.30"

def _txt(s: str, n: int) -> bytes:
    b = s.encode("ascii", "replace")[:n]
    return b + b"\x00" * (n - len(b))

def build_spc(ram: bytes) -> bytes:
    if len(ram) != 0x10000:
        raise ValueError(f"RAM deve essere 64KB, trovati {len(ram)} byte")

    ram = bytearray(ram)
    for addr, val in TIMER.items():       # ripristina lo stato timer reale
        ram[addr] = val

    hdr = bytearray(0x100)
    hdr[0x00:0x21] = MAGIC                 # 33 byte
    hdr[0x21] = 0x1A; hdr[0x22] = 0x1A
    hdr[0x23] = 0x1A                       # 26 = contiene tag ID666
    hdr[0x24] = 30                         # versione minore
    hdr[0x25] = PC & 0xFF; hdr[0x26] = (PC >> 8) & 0xFF
    hdr[0x27] = REG_A; hdr[0x28] = REG_X; hdr[0x29] = REG_Y
    hdr[0x2A] = PSW;   hdr[0x2B] = SP
    # tag ID666 testuale
    hdr[0x2E:0x4E] = _txt("Rudra no Hihou", 32)         # titolo brano
    hdr[0x4E:0x6E] = _txt("Treasure of the Rudras", 32) # titolo gioco
    hdr[0x6E:0x7E] = _txt("snes-rnh-disasm", 16)        # dumper
    hdr[0x7E:0x9E] = _txt("AKAO V4 (ramo RS3/CT)", 32)  # commenti
    hdr[0xA9:0xAC] = _txt("120", 3)                     # secondi prima del fade
    hdr[0xAC:0xB1] = _txt("10000", 5)                   # fade ms
    hdr[0xB1:0xD1] = _txt("Ryuji Sasai", 32)            # artista/compositore

    dsp = bytearray(0x80)
    for reg, val in DSP.items():
        dsp[reg] = val

    out = bytearray()
    out += hdr
    out += ram                # 0x100 : 64KB RAM
    out += dsp                # 0x10100 : 128 byte registri DSP
    out += b"\x00" * 0x40     # 0x10180 : inutilizzato
    out += b"\x00" * 0x40     # 0x101C0 : regione IPL ROM
    assert len(out) == 0x10200, len(out)
    return bytes(out)

def main():
    inp = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "spc" / "rudra-spc700.bin"
    outp = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "spc" / "rudra.spc"
    ram = inp.read_bytes()
    spc = build_spc(ram)
    outp.write_bytes(spc)
    print(f"OK: {outp}  ({len(spc)} byte)")
    print(f"  PC=${PC:04X} SP=${SP:02X} PSW=${PSW:02X}")
    print(f"  DSP: " + " ".join(f"[{r:02X}]=${v:02X}" for r, v in sorted(DSP.items())))
    print(f"  TIMER: " + " ".join(f"${r:02X}=${v:02X}" for r, v in sorted(TIMER.items())))

if __name__ == "__main__":
    main()
