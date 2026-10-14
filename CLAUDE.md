# LeaderKit

Generatori Fusion per DaVinci Resolve 20+ (leader, slate, countdown, barre, taratura, burn-in).
Lingua del progetto: italiano (codice, commenti, README, commit).

## Struttura
- `fx/standards.json`: standard, categorie, slot (fonte dei valori: `docs/industry-standards.md`).
- `fx/engine_common.lua`, `fx/engine.lua` (Genera), `fx/engine_burnin.lua`, `fx/image.lua`: script dei bottoni.
- `fx/overlay.lua`: PNG disegnati in Lua puro (taratura, quadranti, barre SMPTE). Deve girare in LuaJIT e Lua 5.4.
- `tools/build_fx.py`: costruisce i `.setting` e `dist/LeaderKit-<versione>.drfx`.
- `tests/`: pytest; espressioni e motore eseguiti in `lua5.4` su comp e timeline simulati
  (`tests/lua_harness.lua`, `tests/lua_dump.lua`, `tests/engine_harness.lua`).

## Comandi
```bash
python3 -m pytest -q tests        # ~4 min; serve lua5.4 (l'hook di avvio lo installa)
pyflakes tools src tests
python3 tools/build_fx.py
```

## Regole
- Ogni nuovo input del pannello va in `head_inputs()` (ordine dell'Inspector) e in `values`.
- Le immagini di Genera passano da `genImage` + Loader (`GEN_IMAGES`); la cache dipende da `LK_DRAW`.
- Il generatore lavora a 8 bit 0-1 (livelli video in uscita): niente sub-black / super-white.
- La release si fa solo da Actions › Release, con la versione di `src/leaderkit/__init__.py`.
- PR in bozza; test e pyflakes verdi prima del push.
