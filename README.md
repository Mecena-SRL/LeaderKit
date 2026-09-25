# LeaderKit

Plugin per **DaVinci Resolve 20+** che genera automaticamente leader, slate,
countdown, sync pop, coda e marker di rullo/break, con preset per contesto
(cinema/DCP, spot RAI, …). Tutto viene ricalcolato sul **frame rate e sulla
risoluzione reali della timeline**: niente countdown pre-renderizzati.

La fonte di verità per i valori dei preset è
[`docs/industry-standards.md`](docs/industry-standards.md).

> **Stato: v0.1.0 (MVP).** Il motore di calcolo, i template Fusion generati e
> il flusso verso l'API di Resolve sono coperti da test automatici su un
> Resolve simulato. **Non è ancora stato provato dentro DaVinci Resolve
> reale**: vedi [Da verificare in Resolve](#da-verificare-in-resolve).

## Cosa fa (v1)

| Funzione | Dettaglio |
|---|---|
| Head leader | Countdown Universal 8→3 con braccio rotante, frame PICTURE START, **2-pop di 1 fotogramma a FFOA −2"** (48 fotogrammi a 24/23.976, 50 a 25, 60 a 29.97 DF…) con tono 1 kHz |
| Slate | Titolo, regia, montaggio, color, data, versione + **durata, fps e risoluzione calcolati** + righe del preset (TC di FFOA/pop/LFOA, loudness target) |
| Tail leader | Tail pop simmetrico (LFOA +2") + card END OF PROGRAM + nero fino alla durata di coda del preset |
| Marker | FFOA/LFOA, pop, **fine rullo N / break N** a intervalli configurabili; tutti con `customData = "leaderkit:…"` |
| Preset | `Cinema / DCP` e `Spot RAI`, in file JSON separati |
| Controlli | Avvisi su frame rate NTSC per DCP, fps/risoluzione non previsti dal preset, scarto in fotogrammi dalla durata target (spot) |

### Preset inclusi

**Cinema / DCP** (docs §A, Deluxe v5.11): slate 00:59:50:00 (8"), Picture Start
01:00:00:00, countdown 8→3, 2-pop 01:00:06:00, FFOA 01:00:08:00. Coda di 8"
con tail pop a LFOA +2" e card END OF PROGRAM. Rullo N → ora N
(Picture Start N:00:00:00, FFOA N:00:08:00). Marker "Fine rullo" ogni 20'.

**Spot RAI** (docs §C, specifica spot HD feb. 2021): ident/slate ≥5" a
09:59:52:00, 3" di nero, spot a 10:00:00:00, 3" di nero in coda. Niente
barre né countdown. Durata target 15/20/30/45/60" con scarto in fotogrammi.
Loudness target in slate (−23 LUFS ±0,2, −18 LUFS short-term, −2 dBTP).

## Requisiti

- DaVinci Resolve **20** o successivo (free o Studio), macOS / Windows / Linux.
- **Python 3** installato nel sistema: Resolve lo richiede per eseguire script
  Python (su macOS: installer da python.org).
- DaVinci Resolve per **iPad non è supportato**: non esegue script né
  template Fusion di terze parti.

## Installazione

### macOS (.dmg)

1. Apri `LeaderKit-0.1.0-macOS.dmg`.
2. Doppio clic su **Installa LeaderKit.command**. Se macOS lo blocca
   (sviluppatore non identificato): tasto destro → Apri, oppure da Terminale
   `bash "/Volumes/LeaderKit/Installa LeaderKit.command"`.
3. Riavvia Resolve → **Workspace › Scripts › LeaderKit**.

### Linux / Windows (.zip)

Estrai `LeaderKit-0.1.0.zip`, poi `bash install.sh` (Linux) o doppio clic su
`install.bat` (Windows, non ancora testato).

### Cosa viene installato

Tutto nella cartella utente di Fusion, senza privilegi di amministratore:

| macOS: `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/` | |
|---|---|
| `Scripts/Utility/LeaderKit.py` | voce di menu Workspace › Scripts |
| `LeaderKit/leaderkit/` | libreria Python |
| `LeaderKit/presets/` | preset di fabbrica (sovrascritti dagli aggiornamenti) |
| `LeaderKit/presets-user/` | **i tuoi preset** (mai toccati dagli aggiornamenti) |
| `Templates/LeaderKit.drfx` | title template Edit › Titles › LeaderKit (slate e end card da usare anche a mano) |

Windows: `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\` —
Linux: `~/.local/share/DaVinciResolve/Fusion/`.

**Perché non basta il .drfx?** Un bundle `.drfx` installa template Fusion
(titoli, generatori), non script: il motore che legge la timeline, calcola i
fotogrammi e crea clip e marker è uno script Python, e va copiato in
`Scripts/`. Per questo c'è l'installer. Il `.drfx` è incluso ed è anche
installabile da solo con doppio clic, ma dà solo i template manuali.

Disinstallazione: `Disinstalla LeaderKit.command` (macOS) o
`install.sh --uninstall`.

## Uso

1. Apri la timeline del programma (un rullo, uno spot…).
2. Workspace › Scripts › **LeaderKit**.
3. Scegli il preset, compila i campi slate, eventualmente marker e durata target.
4. Scegli la modalità:
   - **Nuova timeline di consegna** (consigliata): crea
     `<timeline> — LeaderKit <preset>` con le stesse impostazioni, imposta lo
     start TC del preset, annida il programma a FFOA e ci costruisce intorno
     testa e coda. La timeline originale non viene toccata.
   - **Timeline corrente**: serve spazio vuoto prima del primo clip, almeno
     quanto la testa del preset (es. 18" per Cinema/DCP). Lo start TC della
     timeline viene spostato in modo che il primo clip cada sul FFOA del preset.
5. **Genera**. Il log riporta TC di FFOA, pop, LFOA e gli avvisi.

**Rimuovi LeaderKit dalla timeline** cancella solo ciò che ha creato il
plugin: marker con `customData` che inizia con `leaderkit`, clip sulle tracce
`LeaderKit` / `LeaderKit Pop` o provenienti dai media `LeaderKit_*`. I marker
e i clip dell'utente non vengono toccati. Rigenerare in modalità "timeline
corrente" fa prima questa pulizia, quindi non crea doppioni.

## Come funziona

```
preset JSON ─┐
             ├─► layout.build_plan() ──► Plan (elementi, audio, marker al fotogramma)
timeline ────┘        (puro Python, testato)          │
 fps/DF/risoluzione                                   ▼
 via GetSetting()                           resolve_ops.generate()
                                            ├─ sequenza PNG nera → AppendToTimeline (recordFrame esatto)
                                            ├─ composizione Fusion generata → ImportFusionComp
                                            ├─ WAV 1 kHz → rifilato a N fotogrammi sulla traccia audio
                                            └─ AddMarker(..., customData="leaderkit:…")
```

- **Frame rate e risoluzione** si leggono con `Timeline.GetSetting()`
  (`timelineFrameRate`, `timelineDropFrameTimecode`,
  `timelineResolutionWidth/Height`), con ripiego su `Project.GetSetting()`.
- **Timecode**: tutto è in fotogrammi interi; i "secondi" dei leader sono
  nominali (24 fotogrammi a 23.976, 30 a 29.97), come da convenzione.
  Drop-frame 29.97/59.94 gestito secondo SMPTE 12M (`timecode.py`).
- **Posizionamento al fotogramma**: l'API di Resolve posiziona con precisione
  solo clip del Media Pool, quindi ogni elemento del leader è un tratto di una
  sequenza PNG nera generata alla risoluzione della timeline (hard link: pesa
  quanto un fotogramma) su cui viene importata la composizione Fusion.
  Ogni clip viene verificato con `GetStart()/GetDuration()`; se una versione
  di Resolve interpreta `endFrame`/`recordFrame` con un offset diverso, il
  primo clip lo misura, viene rifatto e l'offset vale per il resto.
- **Grafica Fusion**: le composizioni sono generate per ogni elemento con la
  risoluzione reale e dimensioni normalizzate (1.0 = larghezza immagine),
  quindi lo stesso disegno in HD, UHD o DCI; il cerchio del countdown sta
  dentro un mascherino Scope 2.39. Il braccio rotante fa un giro per secondo
  nominale al frame rate della timeline.
- **Audio del pop**: WAV mono 48 kHz/24 bit, tono 1 kHz al livello del preset
  (−20 dBFS per Cinema), rifilato a 1 fotogramma esatto sulla timeline.

## Aggiungere un preset

Copia un file di `presets/` in **`presets-user/`** (vedi percorsi sopra),
cambia `id` e `name` e modifica i valori. Al prossimo avvio del pannello il
preset compare nell'elenco; un preset utente con lo stesso `id` di uno di
fabbrica lo sostituisce. Se il JSON non è valido, il pannello lo segnala nel
log e lo ignora.

Durate e offset accettano: fotogrammi interi (`48`), secondi nominali
(`"8s"`, `"-2s"`), minuti (`"20m"`), combinazioni (`"5s+12f"`, `"-1s-1f"`)
o un timecode (`"00:00:08:00"`).

```jsonc
{
  "schema": 1,
  "id": "mio_preset",                  // univoco
  "name": "Il mio preset",             // mostrato nel pannello
  "description": "…",
  "sources": ["docs/industry-standards.md §…"],
  "ffoa_tc": "10:00:00:00",            // primo fotogramma di programma
  "ffoa_hour_per_reel": false,         // true: rullo N → ora N (01:, 02:, …)

  // Testa: offset relativi al FFOA (negativi). I buchi diventano nero.
  "head": [
    {"type": "slate", "start": "-18s", "duration": "8s"},
    {"type": "countdown", "from": 8, "to": 3, "picture_start_frames": 1, "sweep": true},
    {"type": "pop", "at": "-2s", "frames": 1, "video": "two",   // "two" | "white"
     "tone_hz": 1000, "level_dbfs": -20},                      // tone_hz 0 = niente audio
    {"type": "card", "text": "TESTO", "start": "-30s", "duration": "5s"},
    {"type": "black", "start": "-40s", "duration": "10s"}
  ],

  // Coda: offset relativi al LFOA (ultimo fotogramma di programma).
  "tail_duration": "8s",               // la coda occupa LFOA+1 … LFOA+tail_duration
  "tail": [
    {"type": "pop", "at": "+2s", "frames": 1, "video": "two", "tone_hz": 1000, "level_dbfs": -20},
    {"type": "card", "text": "END OF PROGRAM", "start": "+4s", "duration": "3s"}
  ],

  "markers": {
    "ffoa_lfoa": {"enabled": true, "color": "Blue"},
    "sync":      {"enabled": true, "color": "Cyan"},
    "interval":  {"enabled": true, "kind": "reel", "every": "20m", "color": "Red"}  // kind: reel | break
  },
  "target_durations": ["15s", "30s"],  // opzionale, menu "Durata target"
  "slate": {
    "heading": "INTESTAZIONE",
    "fields": ["title", "director", "editor", "colorist", "date", "version",
               "duration", "fps", "resolution"],
    // segnaposto: {ffoa_tc} {lfoa_tc} {pop_tc} {start_tc} {preset}
    "extra_lines": ["FFOA {ffoa_tc}  ·  2-POP {pop_tc}"]
  },
  "checks": {
    "warn_drop_frame": "Messaggio se la timeline è 23.976/29.97/…",
    "expected_rates": ["25"],
    "expected_resolutions": [[1920, 1080]],
    "rate_hint": "Testo aggiunto all'avviso di frame rate",
    "strict_duration": true
  }
}
```
(I commenti `//` sono solo illustrativi: nel file vero il JSON non li ammette.)

Colori marker validi: Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia,
Rose, Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream.

## Sviluppo

```
src/LeaderKit.py          script d'ingresso (Workspace › Scripts)
src/leaderkit/            timecode, presets, layout, media, fusion (puri) + resolve_ops, ui
presets/                  preset di fabbrica
tests/                    pytest, con un Resolve simulato (tests/fake_resolve.py)
tools/build.py            dist/: LeaderKit.drfx, LeaderKit-<ver>.zip, LeaderKit-<ver>-macOS.dmg
installer/                install.sh (macOS/Linux, anche .command nel dmg), windows/install.bat
```

```bash
pip install pytest
python3 -m pytest -q tests        # i test Fusion usano lua5.4 se presente
python3 tools/build.py
```

Il `.dmg` si crea con `hdiutil` su macOS (UDZO) o con `genisoimage` su Linux
(immagine ISO9660 + Rock Ridge, che macOS monta come disco conservando i
permessi di esecuzione). La CI GitHub esegue test e build a ogni push; il
.dmg compresso su runner macOS si lancia a mano (workflow_dispatch).

Compatibilità codice: Python 3.6+ (nessuna dipendenza esterna).

## Da verificare in Resolve

Il codice usa solo API documentate di Resolve (README "Developer" di
Resolve), ma questi punti vanno confermati sul campo prima dell'uso in
produzione:

1. **ImportFusionComp** su un clip di sequenza PNG: la composizione generata
   (formato `.comp`) viene accettata e renderizzata.
2. **Resa grafica**: proporzioni di cerchi e testi (unità normalizzate di
   Fusion) su 16:9, 1.85 DCI e 2.39; font "Open Sans".
3. **Braccio rotante**: l'espressione usa `comp.RenderStart`; se non gira,
   il countdown resta corretto (le cifre sono statiche per clip).
4. **Marker**: `AddMarker` usa frameId relativi all'inizio timeline (come
   indicato in docs §G).
5. **Timeline annidata**: `Timeline.GetMediaPoolItem()` e il rilevamento
   della durata del programma annidato.
6. **UIManager** nella versione free di Resolve (in assenza, lo script usa gli
   ultimi valori salvati senza pannello).

Il test consigliato: stesso preset su una timeline 24p 1920×1080 e su una
25p 3840×2160, controllando nel viewer i TC di Picture Start, 2-pop, FFOA,
tail pop e la forma d'onda del pop (1 fotogramma).

## Roadmap

- Verifica in Resolve 20 (vedi sopra) e ritocchi grafici.
- Installer Windows e Linux testati; .dmg firmato/notarizzato (serve un
  Apple Developer ID).
- Preset successivi da docs: Broadcast UK/DPP (barre + clock + sync 2 fr),
  Netflix/IMF (1" nero, strip leader), Spot Publitalia, Doppiaggio/M&E.
- Barre e toni EBU, guide di safe area/mascherini, export marker CSV/EDL.
