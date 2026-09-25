# LeaderKit

Plugin per **DaVinci Resolve 20+** che genera leader, slate, countdown, sync
pop, coda e marker di rullo/break, con preset per contesto (cinema/DCP, spot
RAI, …). Tutto si adatta al **frame rate e alla risoluzione reali della
timeline**. Valori di riferimento: [`docs/industry-standards.md`](docs/industry-standards.md).

## Generatore nella libreria Effetti (consigliato)

Si installa solo con **`LeaderKit-<versione>.drfx`** (doppio clic): niente installer, niente Python.

1. Effetti › Generators › **LeaderKit** (un solo generatore): trascinalo dove
   deve iniziare il leader, anche **a timeline vuota**. La lunghezza non conta.
2. Nella scheda **Progetto** scegli lo **standard** e la **durata del
   programma** (libera, slot della categoria dello standard, TC di fine, o
   personalizzata). Le voci che non riguardano lo standard scelto vengono
   nascoste e comunque ignorate da Genera; negli standard fissi le durate del
   leader non si possono modificare (solo "Personalizzato / review").
3. **Genera sulla timeline**: porta il blocco alla durata esatta dello standard,
   imposta lo start TC, mette tono/pop/sync audio, crea il **contenitore**
   (anche senza montato), inserisce la coda (**LeaderKit Tail**) sulla stessa
   traccia anche oltre la fine della timeline, aggiunge marker di rullo o break
   e mostra un riepilogo con i **controlli** (✓/⚠) e cosa fare.
4. **Rimuovi elementi generati** cancella solo marker, audio, taratura, logo e coda di LeaderKit.

Tracce create da Genera: **LeaderKit Pop** (audio), **LeaderKit Grafica**
(taratura e frame lines) e **LeaderKit Logo**. Ogni standard ha la coda (per
Spot Publitalia e Spot USA, che non la prevedono, 2" di nero disattivabili).

Slot per categoria:

| Categoria | Slot |
|---|---|
| Cinema | Corto 15'/30', Mediometraggio 60', Lungometraggio 90'/100'/120' |
| TV | Film TV 90'/100', Fiction/serie 50', Serie 25', TV 13' (parte), TV 26', TV 45', Documentario TV 52' |
| Spot | 10", 15", 20", 30", 45", 60", 90", 120" |
| Streaming | Episodio 25'/50', Documentario 52', Film 90'/100'/120' |

**Break TV** (solo standard TV): nessuno, automatici secondo la direttiva
AVMSD (film, film TV e notiziari: al massimo un'interruzione ogni 30 minuti
programmati) o da 1 a 6 break manuali; Genera mette i marker e avvisa se il
numero supera il limite AVMSD.

**Data**: il bottone **Oggi** scrive la data odierna; la spunta **Data
automatica** la aggiorna a ogni render/export, così la slate ha sempre la data
corretta.

### Copie di lavoro e burn-in

Gli standard **Copia lavoro** (giornalieri / sync, montaggio / review, suono /
mix / VO, VFX, approvazione cliente) creano un leader corto e, con Genera, un
clip **LeaderKit Burn-in** su una traccia sua ("LeaderKit Burn-in") sopra il
montato, dal FFOA all'LFOA. Per inserirlo Genera blocca per un attimo tutte le
altre tracce, così il montato non può essere toccato; se la versione di Resolve
non lo permette, lo dice e basta trascinare il generatore a mano e premere
**Aggiorna dai metadati**.

Il burn-in legge da Resolve, clip per clip: nome, Start TC e punto d'ingresso
(Source TC che scorre), scena/shot/take e take cerchiata, camera, reel/roll,
data di ripresa, sound roll e TC dell'audio sotto (per verificare il sync),
spazio colore del progetto. Record TC e contatore fotogrammi sono calcolati a
ogni fotogramma. La **fase di lavoro** sceglie i campi (poi modificabili):

| Fase | Campi |
|---|---|
| Scarico / verifica DIT | Source TC, clip, reel, camera, data, formato, colore |
| Sync audio-video | Source TC, TC audio + sound roll, clip, scena/take, camera, reel |
| Giornalieri | Source TC, clip, scena/take, camera, reel, data, titolo, watermark |
| Montaggio / offline review | Record TC, Source TC, clip, titolo, versione, data, watermark |
| VFX | Source TC, contatore da 1001, clip, reel, versione, formato |
| Color review | Record TC, Source TC, clip, versione, colore, formato |
| Suono / mix / VO / doppiaggio | Record TC anche grande, contatore del programma, titolo, versione |
| Approvazione cliente | Record TC, titolo, versione, data, watermark con destinatario |

**Mascherino** (scheda Aspetto): preset 1.33, 1.37 Academy, 1.43 IMAX, 1.66,
1.78, 1.85 Flat, 1.90, 2.00, 2.20, 2.35, 2.39 Scope, 2.76 oppure un rapporto
personalizzato con lo slider. È sempre calcolato sul rapporto reale della
timeline: se il formato è più largo diventa letterbox (bande sopra e sotto,
dove vanno i dati: la prassi delle grandi produzioni, "fuori dall'immagine
attiva"), se è più stretto diventa pillarbox (bande laterali, es. 1.33 su una
timeline 2:1 o 2.39), se coincide non si vede. Senza mascherino i dati stanno in
bande proprie semitrasparenti o dentro l'immagine (safe 90%). L'altezza del
testo è in percentuale del quadro, quindi resta uguale su 16:9, 2:1 o DCI.
I dati sono **allineati ai bordi** (sinistra / destra); se in una versione di
Resolve l'ancoraggio di Text+ non si comporta come previsto, "Allineamento dei
dati › Centrati nelle celle" li riporta al centro delle loro celle. I dati si
aggiornano con **Aggiorna dai metadati** (o con Genera) dopo modifiche al
montaggio o ai metadati.

### Schede dell'Inspector

| Scheda | Contenuto |
|---|---|
| **Progetto** | standard, rullo, durata del programma, marker, coda, **Genera** / **Rimuovi**, guida timecode e timecode calcolati |
| **Produzione** | titolo, produzione, produttore, regia, cliente, agenzia, codice (Ad-ID/Clock/Auditel), episodio/rullo, lingua, data |
| **Post** | montaggio, color, suono, VFX, versione, fase di lavorazione, stato color/suono/VFX/musica/titoli (TEMP/FINAL), note |
| **Tecnico** | frame lines 1.33 / 1.66 / 1.78 / 1.85 / 2.00 / 2.20 / 2.39, safe area 93% e 90%, spazio colore (letto dal progetto), formato audio, livello pop |
| **Aspetto** | colori di testo, sfondo e grafica; logo scelto con **selettore file** (posizione, dimensione, anche sulla coda) |
| **Taratura** | strumenti sul countdown, ispirati al leader digitale SMPTE RP 428-6: griglie di risoluzione pixel-esatte (righe verticali e orizzontali da 1, 2, 3, 4 px: se quelle da 1 px si impastano, l'immagine è morbida o è stata scalata), mirino centrale, scala di grigi a 11 gradini, patch RGBCMY, rampe continue B/N-R-G-B, verifica del blu (Wratten 47B), sfera sfumata per il contouring, bianco di picco e neri (PLUGE 2/4/8%), etichette fps/risoluzione/formato |

**Stili della slate** (scheda Aspetto › Slate):

| Stile | Impaginazione |
|---|---|
| Pannelli | titolo, regia e tre pannelli Production / Post / Technical |
| Quadrante | a sinistra un quadrante con i fotogrammi del secondo (00–23 a 24 fps, 00–24 a 25…) e la tacca che gira, secondi al FFOA al centro; a destra titolo, standard, dati allineati a sinistra e fotogrammi al FFOA |
| Orologio | a sinistra un cronometro con i secondi al FFOA; a destra titolo nel colore evidenza e dati allineati a sinistra |
| Minimale | titolo grande al centro, regia, una riga di dati essenziali |

Il **titolo può essere un PNG** (con trasparenza): Genera lo mette nel riquadro
del titolo dello stile scelto, leggendo le proporzioni dal file, e il titolo di
testo sparisce. Il **logo della produzione** e un secondo logo vanno negli
angoli scelti, con i margini esatti. I quadranti degli stili Quadrante e
Orologio sono PNG creati da Genera alla risoluzione della timeline, con i
numeri dei fotogrammi del frame rate reale.

**Slate a pannelli**: titolo grande (si riduce da solo se è lungo), "Directed by", filo
nel colore evidenza e tre pannelli: **Production** (produzione, produttore,
cliente, agenzia, codice, episodio, lingua, data), **Post** (montaggio, color,
suono, VFX, versione, fase, stato TEMP/FINAL) e **Technical** (durata, formato e
rapporto, frame rate, spazio colore di uscita, audio). Ogni pannello ha due
sotto-colonne; i campi vuoti non lasciano buchi e i pannelli si accorciano; in
basso i timecode calcolati. Due loghi (produzione e cliente) negli angoli.
Slate, barre e countdown si alternano con nodi Dissolve, così Fusion calcola
solo la parte visibile.

**Taratura e frame lines sono immagini statiche**: Genera le disegna pixel per
pixel alla **risoluzione esatta della timeline** (PNG con trasparenza, in
`~/.leaderkit`, riusato se nulla cambia) e le mette sulla traccia "LeaderKit
Grafica" sopra il countdown (e sulla slate, se richiesto). Il generatore Fusion
disegna solo sfondo, testi, cerchi, braccio e cifre: resta leggero in
riproduzione. Il logo va sulla traccia "LeaderKit Logo" sopra la slate (e sulla
coda, se richiesto); se Resolve accorcia le immagini fisse alla durata standard,
Genera le ripete fino a coprire tutto lo spazio.

### Standard inclusi

Fonte dei valori: `docs/industry-standards.md` (sezione indicata in ogni
preset di `fx/standards.json`). Gli standard contrassegnati con * non hanno una
specifica tecnica pubblica: i valori (barre 20" + clock 7" + nero 3", FFOA
10:00:00:00, coda 3") sono un riferimento prudente e Genera lo segnala nei
controlli. Vanno sempre verificati con il capitolato del committente.

| Categoria | Standard |
|---|---|
| Cinema | Cinema — DCP (container DCI Flat/Scope/Full 2K e 4K), Cinema — Doppiaggio / M&E |
| TV Italia | RAI (programmi)\*, Mediaset (programmi)\*, Sky Italia\* |
| TV Europa / UK | EBU (generico)\*, DPP (BBC, ITV, C4…), Sky UK |
| Spot | RAI, Publitalia / Mediaset, USA |
| Streaming | Netflix / IMF |
| Copia lavoro | Giornalieri / sync, Montaggio / review, Suono / mix / VO, VFX, Approvazione cliente |
| Altro | Videoclip / Live, Personalizzato / review |

### Durata del programma

- **Libera**: il programma finisce con l'ultimo clip audio o video.
- **Slot standard** della categoria (tabella sopra): Genera crea subito il
  **contenitore** (marker con durata, LFOA e coda alla fine esatta) e avvisa di
  quanti fotogrammi il montato è più lungo o più corto.
- **TC di fine programma** o **personalizzata** (`HH:MM:SS:FF`).

### Aggiungere o modificare uno standard

Modifica `fx/standards.json` (sezioni `presets`, `categories`, `slots`) (durate in secondi nominali, TC del FFOA, barre,
slate/clock, countdown, sync, coda, righe della slate, frame rate e risoluzioni
ammesse, note) e ricostruisci con `python3 tools/build_fx.py`.

Il countdown non è pre-renderizzato: cifre, Picture Start, braccio e 2-pop sono
calcolati a ogni fotogramma dal frame rate della timeline (48 fotogrammi a
24/23.976, 50 a 25, 60 a 29.97 DF). Build: `python3 tools/build_fx.py`; motore
dei bottoni in `fx/engine.lua`. Test: `tests/test_fx.py` (espressioni e motore
eseguiti in Lua su comp e timeline simulati).

La v0.1 (script Python da Workspace › Scripts, descritta sotto) resta nel repo
come riferimento del motore di calcolo.

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

Generatore 0.8 (verificato in Resolve Studio 21.1: resa, schede, Genera, bip;
da confermare sul campo):

1. Immagini PNG di taratura importate con la trasparenza e alla durata del
   countdown (altrimenti Genera le ripete a pezzi).
2. Coda su timeline vuota con slot lunghi (es. DCP 90': coda a 02:30:08:00).
3. Voci nascoste in base allo standard (`INPB_IC_Visible`), selettore file del
   logo e data automatica all'export.
4. Burn-in: inserimento automatico sulla traccia "LeaderKit Burn-in" con le
   altre tracce bloccate, allineamento dei testi agli angoli, nomi dei metadati
   (Scene, Take, Camera #, Reel Name, Sound Roll #…) nelle varie camere.

Versione 0.1 (script Python):

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
