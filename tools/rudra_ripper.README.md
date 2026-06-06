# Ripper OST di Rudra (Mesen2 Lua)

`rudra_ripper.lua` estrae l'intera colonna sonora pilotando il motore audio del
gioco dall'esterno, **senza scaricare set altrui** e senza giocare ogni brano.

## Come si carica in Mesen2
1. Apri la ROM `jap/Rudra no Hihou (Japan).sfc` in `Mesen/Mesen.exe`.
2. Menu **Debug → Script Window** (oppure Tools → Script).
3. Apri `lua/rudra_ripper.lua` e premi **Run** (▶).
4. Guarda l'output nel riquadro **Log** in basso nella finestra script.

Lo script all'avvio stampa i `emu.memType` disponibili e auto-rileva ARAM/WRAM.
Se vedi `ARAM type non trovato`, copia il nome giusto dalla lista in
`CONFIG.aramType`.

## Le tre modalita' (imposta `CONFIG.mode` in cima al file)

### 1. `spy`  — FALLA PER PRIMA
Passiva: aggancia `$EB03BC` (il choke-point di tutte le chiamate audio) e logga
`cmd=$00`, `$01`, `$02` ogni volta che il gioco suona qualcosa.
- Avvia in `spy`, poi **gioca** o usa un eventuale sound-test.
- Cammina tra mappe, entra in battaglia, apri menu: ogni nuovo evento audio
  compare nel log come `<-- NUOVO`.
- Cosi' impariamo **dal vivo** quale `cmd` significa "play BGM" e quali valori di
  `$01` (ID brano) usa davvero il gioco. Questo dato pilota lo sweep.

### 2. `probe` — calibrazione
Inietta un singolo `(CONFIG.probeCmd, CONFIG.probeId)` e traccia per ~4s il byte
voci-attive `$ED90` e un fingerprint della regione dati-sequenza `$C000-$DFFF`.
- Serve a confermare che l'iniezione pilota davvero l'audio.
- Serve a vedere come si comporta il segnale (`$ED90` ≠ 0 = suona; fingerprint
  che cambia = brano nuovo caricato).
- Per trovare il **comando di STOP**: prova diversi `probeCmd` e guarda quale
  riporta `$ED90` a 0.

### 3. `sweep` — il ripper vero
Per ogni `id` in `[idStart, idEnd]`: invia `stopCmd` → attende → baseline →
invia `playCmd,id` → attende `dwellFrames` → se `$ED90≠0` **e** i dati-sequenza
sono cambiati (e non gia' visti) considera l'id valido e **dumpa 64KB di ARAM**
in `spc/dumps/auto_id<NN>.dmp`. Deduplica per fingerprint.
- Prima di lanciarlo, imposta `playCmd`/`stopCmd` con quanto imparato in spy/probe.
- Falla partire da uno schermo tranquillo (titolo o stanza senza SFX) per non
  litigare con le chiamate audio del gioco sulle porte APU.

## Dopo lo sweep
```
python tools/wrap_auto_dumps.py     # auto_id*.dmp -> spc/rudra-auto-id*.spc
```
Apri gli `.spc` in VGMTrans → esporta MIDI/SF2. Fine: OST tua. 🏆

## Note tecniche
- L'iniezione replica l'handshake `$EB0942`+`$EB0957` su `$2140-$2142` con una
  macchina-a-stati per-frame (solo read/write, niente chirurgia su PC/stack/flag).
- Encoding parametro (lato dispatch `$EB03BC`): `$00` = comando (i 2 bit bassi =
  sotto-tipo/priorita' → `$E6`; i 6 alti = categoria → `$E5`), `$01` = dato/ID
  → `$2141`, `$02` = parametro → `$2142`. Famiglia musica = `$98-$9B`.
