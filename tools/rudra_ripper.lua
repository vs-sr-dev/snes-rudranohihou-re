--------------------------------------------------------------------------------
-- rudra_ripper.lua  -  Ripper OST di Rudra no Hihou per Mesen2 (v2.1.x)
--------------------------------------------------------------------------------
-- Obiettivo: estrarre da soli l'intera colonna sonora (dump ARAM -> .spc ->
-- VGMTrans -> MIDI), SENZA scaricare set altrui e SENZA giocare ogni brano.
--
-- LEZIONE SESS.6: NON basta dire all'SPC "suona". Il dato del brano va prima
-- caricato da ROM ad ARAM dal codice host 65816. Catena RE:
--   $EB0372  wrapper API (priorita'); il gioco chiama JSL $EB0372 con il
--            parametro impacchettato in $00=comando, $01=ID, $02=param.
--   $EB03BC  DISPATCH. Per la famiglia musica ($98-$9B) invia solo i comandi
--            all'SPC (= "play", NON carica). Per le categorie $44/$48/$B0
--            salta a $EB040B.
--   $EB040B -> $EB04CF  CARICATORE VERO: $0994 imposta [$E7]=ptr ROM del brano,
--            poi JSL $EB022A streama i dati ROM->ARAM, infine play.
--
-- Quindi per caricare+suonare il brano id da fuori dobbiamo FAR GIRARE il codice
-- host: simuliamo un JSL a $EB03BC con $00 nella famiglia $44/$48 (push del
-- return su stack + redirect di PC/flag), lasciamo che il gioco faccia l'upload,
-- e al RTL ripristiniamo lo stato CPU salvato. Niente replica di handshake: e'
-- il codice originale a girare.
--
-- RILEVAMENTO: un brano nuovo riscrive ~73% della regione dati-sequenza
-- $C000-$DFFF; il rumore del motore vivo e' ~9%. Soglia a 25% li separa netto.
--
-- TRE MODALITA' (CONFIG.mode):
--   "spy"   : passiva. Logga $00/$01/$02 ad ogni chiamata audio del gioco.
--   "probe" : esegue UNA chiamata-caricamento (loadCmd,probeId) e mostra di
--             quanto cambia la regione dati-sequenza (valida l'approccio).
--   "sweep" : per ogni id, chiama il caricatore, attende, e se i dati-sequenza
--             sono cambiati oltre soglia (e non gia' visti) dumpa l'ARAM.
--------------------------------------------------------------------------------

local CONFIG = {
  mode = "sweep",                     -- "inspect" | "spy" | "probe" | "sweep"

  ----------------------------------------------------------------------------
  -- Indirizzi (dal RE).
  ----------------------------------------------------------------------------
  dispatchAddr = 0xEB03BC,            -- entry del dispatch (lo chiamiamo noi)
  spyAddr      = 0xEB03BC,            -- choke-point per la spia
  landingAddr  = 0xEB0372,            -- pad di ritorno per il JSL simulato

  -- Comando "carica+suona": famiglia $44 con priorita' 1 (come fa il gioco).
  -- (cat=$44 -> path caricatore $EB040B). $48 e' l'altra categoria possibile.
  loadCmd   = 0x45,                   -- $44|1
  loadParam = 0x18,                   -- $02 tipico osservato nella spia

  -- ARAM: regione dati-sequenza (fingerprint del brano).
  seqLo = 0xC000, seqHi = 0xE000,     -- [lo, hi)
  voiceMaskAddr = 0xED90,             -- maschera voci attive (diagnostica)
  changeThresh = 0.20,                -- frazione campioni che deve cambiare (rumore~9%, load~41%)

  ----------------------------------------------------------------------------
  -- Tipi di memoria Mesen2 (auto-rilevati; override se serve).
  ----------------------------------------------------------------------------
  aramType = nil, wramType = nil,

  ----------------------------------------------------------------------------
  -- PROBE
  ----------------------------------------------------------------------------
  probeId = 0x3F,                     -- un id da validare (preso dalla spia)
  probeFrames = 180,
  probeEvery  = 15,

  ----------------------------------------------------------------------------
  -- SWEEP
  ----------------------------------------------------------------------------
  idStart = 0x00,
  idEnd   = 0xFF,
  dwellFrames = 8,                    -- frame dopo il parcheggio (upload gia' completo)
  dumpDir = "spc_dumps",              -- IMPOSTA un percorso scrivibile assoluto sul TUO sistema
}

--------------------------------------------------------------------------------
-- Utilita'
--------------------------------------------------------------------------------
local function log(s) emu.log(s) end
local function hud(s) emu.displayMessage("Ripper", s) end

local function pickMemTypes()
  local keys = {}
  for k,_ in pairs(emu.memType) do keys[#keys+1] = k end
  table.sort(keys)
  local function find(pats)
    for _,p in ipairs(pats) do for _,k in ipairs(keys) do
      if k:lower() == p then return emu.memType[k] end end end
    for _,p in ipairs(pats) do for _,k in ipairs(keys) do
      if k:lower():find(p,1,true) then return emu.memType[k] end end end
  end
  CONFIG.aramType = CONFIG.aramType or find({"spcram","spc"})
  CONFIG.wramType = CONFIG.wramType or find({"snesworkram","workram"})
  log(string.format("ARAM=%s WRAM=%s", tostring(CONFIG.aramType), tostring(CONFIG.wramType)))
end

local function rdAram(addr) return emu.read(addr, CONFIG.aramType) end
local function rdWram(addr) return emu.read(addr, CONFIG.wramType) end

-- Campiona la regione dati-sequenza: ritorna una tabella di byte (1 ogni 32).
local function sampleSeq()
  local t, n = {}, 1
  for a = CONFIG.seqLo, CONFIG.seqHi - 1, 32 do t[n] = rdAram(a); n = n + 1 end
  return t
end
-- Frazione di campioni differenti tra due sample.
local function sampleDiff(a, b)
  local d = 0
  for i = 1, #a do if a[i] ~= b[i] then d = d + 1 end end
  return d / #a
end
local function sampleKey(a) return table.concat(a, ",") end

--------------------------------------------------------------------------------
-- CHIAMATA AL CARICATORE (JSL simulato verso $EB03BC)
-- callBegin(cmd,id,param): arma la chiamata. Restituisce dopo che il codice host
-- ha eseguito (upload+play) e lo stato CPU e' stato ripristinato.
-- Stato: "idle" -> (callBegin) "armed" -> [il codice gira] -> hook al return
-- ripristina -> "done".
--------------------------------------------------------------------------------
local call = { state = "idle", saved = nil, hookRef = nil }

-- Scrive l'albero completo di emu.getState() su file (niente scroll perso).
local function inspectState()
  local ok, st = pcall(emu.getState)
  if not ok or type(st) ~= "table" then
    log("!! getState() non e' una tabella: " .. tostring(st)); return
  end
  local lines = {}
  local function walk(t, prefix)
    local keys = {}
    for k,_ in pairs(t) do keys[#keys+1] = k end
    table.sort(keys, function(a,b) return tostring(a) < tostring(b) end)
    for _,k in ipairs(keys) do
      local v = t[k]
      local path = prefix .. tostring(k)
      if type(v) == "table" then
        walk(v, path .. ".")
      else
        lines[#lines+1] = string.format("%s = %s", path, tostring(v))
      end
    end
  end
  walk(st, "")
  local top = {}
  for k,_ in pairs(st) do top[#top+1] = k end
  table.sort(top)
  log("getState() top-level: " .. table.concat(top, ", "))
  local path = "state_dump.txt"     -- relativo alla CWD di Mesen; cambialo se serve
  local f = io.open(path, "w")
  if f then
    f:write(table.concat(lines, "\n")); f:close()
    log("Albero stato scritto in " .. path .. "  (" .. #lines .. " righe)")
  else
    log("!! non riesco a scrivere " .. path)
  end
end

-- STRATEGIA "PARCHEGGIO": non ripristiniamo NULLA. Scriviamo un loop infinito
-- (BRA -2 = $80 $FE) in WRAM alta a $7E:FFFE. La chiamata simulata fa RTL li':
-- la CPU host si parcheggia nel loop, ferma e innocua, finche' non re-iniettiamo.
-- L'SPC NON viene MAI toccato -> resta sano -> ogni handshake di caricamento ok.
-- (Il problema dei run precedenti era proprio riavvolgere l'SPC.)
local PARK = 0x7EFFFE                 -- indirizzo del loop di parcheggio (bank $7E)

local function setupPark()
  emu.write(0xFFFE, 0x80, CONFIG.wramType)   -- $7E:FFFE = BRA ...
  emu.write(0xFFFF, 0xFE, CONFIG.wramType)   -- ... -2  (loop su se stesso)
end

-- Il hook scatta al RITORNO in ROM ($EB0372, affidabile). Lì PARCHEGGIAMO la CPU
-- nel loop WRAM (setState parziale: solo pc+k) cosi' non rigira il codice del
-- gioco mentre misuriamo/dumpiamo. L'SPC NON viene toccato.
-- IMPORTANTE: NON facciamo setState qui. Un setState PARZIALE azzera i campi non
-- elencati (sp, registri SPC...) -> rompe tutto. Un setState PIENO riverte l'SPC.
-- Quindi al ritorno NON tocchiamo nulla: la CPU rientra nel gioco (che resta idle
-- e non risovrascrive il brano - provato dalla probe: stabile 180 frame).
local function onReturnHook()
  if call.state ~= "armed" then return end   -- gia' fatto / chiamata legittima
  call.state = "done"
end

-- Rete di sicurezza: se il ritorno non scatta entro N frame, prosegui comunque.
local function callPending()
  if call.state ~= "armed" then return false end
  call.waited = (call.waited or 0) + 1
  if call.waited > 30 then
    call.state = "done"
    log("!! ritorno non scattato entro 30 frame")
    return false
  end
  return true
end

local function callBegin(cmd, id, param)
  emu.write(0x00, cmd,   CONFIG.wramType)
  emu.write(0x01, id,    CONFIG.wramType)
  emu.write(0x02, param, CONFIG.wramType)
  -- NB: getState() di Mesen2 e' PIATTO con chiavi puntate: s["cpu.pc"], non s.cpu.pc
  -- simula un JSL: push del return (PARK-1) come PBR:PCH:PCL sullo stack
  local s = emu.getState()
  local sp = s["cpu.sp"]
  if sp < 0x10 then            -- stack non inizializzato (gioco al boot): salta
    call.state = "done"
    log("!! SP=$"..string.format("%X",sp).." troppo basso: gioco non pronto, id saltato")
    return
  end
  local ret = (CONFIG.landingAddr - 1) & 0xFFFFFF  -- RTL -> $EB0372 (hook ROM affidabile)
  emu.write(sp,     (ret >> 16) & 0xFF, emu.memType.snesMemory)  -- PBR
  emu.write(sp - 1, (ret >> 8)  & 0xFF, emu.memType.snesMemory)  -- PCH
  emu.write(sp - 2,  ret        & 0xFF, emu.memType.snesMemory)  -- PCL
  s["cpu.sp"]  = (sp - 3) & 0xFFFF
  s["cpu.pc"]  = CONFIG.dispatchAddr & 0xFFFF
  s["cpu.k"]   = (CONFIG.dispatchAddr >> 16) & 0xFF  -- program bank = $EB
  s["cpu.dbr"] = 0x00                                -- data bank 0 -> $2140-$2142 = porte APU
  s["cpu.d"]   = 0x00                                -- direct page 0
  s["cpu.ps"]  = (s["cpu.ps"] | 0x20) & 0xEF         -- M=1 (A 8-bit), X=0 (idx 16-bit)
  if s["cpu.emulationMode"] ~= nil then s["cpu.emulationMode"] = false end
  emu.setState(s)
  call.state = "armed"; call.waited = 0
end

--------------------------------------------------------------------------------
-- SPY
--------------------------------------------------------------------------------
local spy = { count = 0, seen = {} }
local function onDispatch()
  local c, d1, d2 = rdWram(0x00), rdWram(0x01), rdWram(0x02)
  local key = string.format("%02X:%02X:%02X", c, d1, d2)
  spy.count = spy.count + 1
  if not spy.seen[key] then
    spy.seen[key] = true
    log(string.format("[spy #%d] cmd=$%02X (cat=$%02X sub=%d) $01=$%02X $02=$%02X  <-- NUOVO",
        spy.count, c, c & 0xFC, c & 3, d1, d2))
  end
end

--------------------------------------------------------------------------------
-- PROBE: una chiamata-caricamento, poi osserva il cambiamento dei dati.
--------------------------------------------------------------------------------
local probe = { frame = 0, phase = "init", base = nil, ref = nil }
local function onFrameProbe()
  if callPending() then return end                  -- aspetta che la chiamata finisca
  probe.frame = probe.frame + 1
  if probe.phase == "init" then
    probe.base = sampleSeq()
    log(string.format("[probe] chiamo loader cmd=$%02X id=$%02X param=$%02X ...",
        CONFIG.loadCmd, CONFIG.probeId, CONFIG.loadParam))
    callBegin(CONFIG.loadCmd, CONFIG.probeId, CONFIG.loadParam)
    probe.phase = "watch"; probe.frame = 0
  elseif probe.phase == "watch" then
    if (probe.frame % CONFIG.probeEvery) == 0 then
      local cur = sampleSeq()
      log(string.format("[probe] f=%4d  diff-vs-base=%.0f%%  $%04X=$%02X",
          probe.frame, 100 * sampleDiff(cur, probe.base), CONFIG.voiceMaskAddr,
          rdAram(CONFIG.voiceMaskAddr)))
    end
    if probe.frame >= CONFIG.probeFrames then
      local final = 100 * sampleDiff(sampleSeq(), probe.base)
      log(string.format("[probe] FINE. cambiamento totale dati-sequenza = %.0f%%", final))
      log(final >= 100*CONFIG.changeThresh
          and "  -> SUPERA soglia: la chiamata CARICA un brano. Passa a sweep!"
          or  "  -> sotto soglia: id muto/uguale, o loadCmd/param da rivedere.")
      emu.removeEventCallback(probe.ref, emu.eventType.endFrame)
    end
  end
end

--------------------------------------------------------------------------------
-- SWEEP
--------------------------------------------------------------------------------
local sweep = { id = nil, phase = "init", waited = 0, ref = nil, found = 0,
                seen = {}, baseSample = nil, clean = nil, cbref = nil }

local function dumpAram(path)
  local f = io.open(path, "wb")
  if not f then log("!! apertura fallita: " .. path); return false end
  local chunk = {}
  for a = 0, 0xFFFF do
    chunk[#chunk+1] = string.char(rdAram(a))
    if #chunk == 4096 then f:write(table.concat(chunk)); chunk = {} end
  end
  if #chunk > 0 then f:write(table.concat(chunk)) end
  f:close(); return true
end

local function onFrameSweep()
  if callPending() then return end                  -- aspetta la chiamata in corso

  if sweep.phase == "init" then
    -- snapshot dei REGISTRI puliti (CPU+SPC) catturato UNA volta; lo ripristiniamo
    -- prima di ogni id per resettare l'SPC (i savestate veri qui non sono permessi).
    sweep.clean = emu.getState()
    sweep.baseSample = sampleSeq()         -- riferimento "pulito" (brano residente)
    sweep.id = CONFIG.idStart
    sweep.phase = "load"
    log(string.format("[sweep] snapshot ok. id $%02X..$%02X, loadCmd=$%02X, soglia=%.0f%%",
        CONFIG.idStart, CONFIG.idEnd, CONFIG.loadCmd, 100*CONFIG.changeThresh))

  elseif sweep.phase == "load" then
    callBegin(CONFIG.loadCmd, sweep.id, CONFIG.loadParam)
    sweep.phase = "dwell"; sweep.waited = 0

  elseif sweep.phase == "dwell" then
    sweep.waited = sweep.waited + 1
    if sweep.waited >= CONFIG.dwellFrames then
      local cur = sampleSeq()
      local diff = sampleDiff(cur, sweep.baseSample)   -- confronto vs PULITO (costante)
      local key = sampleKey(cur)
      if diff >= CONFIG.changeThresh and not sweep.seen[key] then
        sweep.seen[key] = true
        sweep.found = sweep.found + 1
        local path = string.format("%s/auto_id%02X.dmp", CONFIG.dumpDir, sweep.id)
        local ok = dumpAram(path)
        log(string.format("[sweep] id $%02X  BRANO NUOVO (diff=%.0f%%) -> %s %s",
            sweep.id, 100*diff, path, ok and "OK" or "FAIL"))
        hud(string.format("trovato $%02X (#%d)", sweep.id, sweep.found))
      else
        log(string.format("[sweep] id $%02X  no (diff=%.0f%%%s)",
            sweep.id, 100*diff, sweep.seen[key] and ", duplicato" or ""))
      end
      sweep.id = sweep.id + 1
      if sweep.id > CONFIG.idEnd then
        log(string.format("[sweep] FINE. Brani unici: %d. Ora: python tools/wrap_auto_dumps.py",
            sweep.found))
        emu.removeEventCallback(sweep.cbref, emu.eventType.endFrame)
      else
        sweep.phase = "load"
      end
    end
  end
end

--------------------------------------------------------------------------------
-- AVVIO
--------------------------------------------------------------------------------
pickMemTypes()
log("=== Rudra OST ripper === modalita': " .. CONFIG.mode)

if CONFIG.mode == "inspect" then
  inspectState()
  log("Copiami queste righe: cerchiamo i campi tipo pc/sp/k(bank)/d/dbr/ps/flag.")

elseif CONFIG.mode == "spy" then
  emu.addMemoryCallback(onDispatch, emu.callbackType.exec, CONFIG.spyAddr, CONFIG.spyAddr)
  log("Spia attiva. Gioca / usa il sound-test.")
  hud("SPY attivo")

elseif CONFIG.mode == "probe" or CONFIG.mode == "sweep" then
  setupPark()                                 -- scrive il loop di parcheggio in WRAM
  -- hook quando la routine fa RTL in ROM a $EB0372 (= caricamento finito)
  call.hookRef = emu.addMemoryCallback(onReturnHook, emu.callbackType.exec,
                                       CONFIG.landingAddr, CONFIG.landingAddr)
  log(string.format("Hook ritorno a $%06X; parcheggio a $%06X.", CONFIG.landingAddr, PARK))
  if CONFIG.mode == "probe" then
    probe.ref = emu.addEventCallback(onFrameProbe, emu.eventType.endFrame)
    hud(string.format("PROBE id=$%02X", CONFIG.probeId))
  else
    sweep.cbref = emu.addEventCallback(onFrameSweep, emu.eventType.endFrame)
    hud("SWEEP in corso...")
  end

else
  log("!! CONFIG.mode sconosciuto: " .. tostring(CONFIG.mode))
end
