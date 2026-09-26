# LeaderKit

Generatore per **DaVinci Resolve 20+** che crea leader, slate, countdown, 2-pop,
coda, marker di rullo e di break, taratura e burn-in delle copie di lavoro.
Ha preset per cinema/DCP, TV italiana ed europea, spot, streaming e copie di
lavoro. Tutto si adatta al **frame rate e alla risoluzione reali della
timeline**. I valori di riferimento sono in
[`docs/industry-standards.md`](docs/industry-standards.md).

Versioni e download: [Releases](https://github.com/Mecena-SRL/LeaderKit/releases)
(pre-release 0.x, testate su Resolve Studio 21.1 per macOS).

## Installazione

1. Scarica `LeaderKit-<versione>.drfx` dall'ultima release.
2. Aprilo con doppio clic: Resolve lo installa tra gli effetti. Non servono
   installer né Python.
3. Riavvia Resolve. Trovi i generatori in Effetti › Generators › LeaderKit:
   **LeaderKit** (testa), **LeaderKit Tail** (coda, la inserisce Genera) e
   **LeaderKit Burn-in**.

Per aggiornare, installa il nuovo `.drfx` sopra il vecchio (stessa cartella
LeaderKit tra i template). DaVinci Resolve per iPad non è supportato.

## Uso in quattro passi

1. Trascina **LeaderKit** dove deve iniziare il leader, anche **a timeline
   vuota**. La lunghezza non conta.
2. Nella scheda **Progetto** scegli lo **standard** e la **durata del
   programma**. Le voci che non riguardano lo standard vengono nascoste, e
   comunque Genera le ignora.
3. Premi **Genera sulla timeline**. Genera:
   - porta il blocco alla durata esatta dello standard e imposta lo start TC;
   - mette tono, 2-pop e sync audio;
   - crea il **contenitore**, anche senza montato;
   - inserisce la coda sulla stessa traccia, anche oltre la fine della timeline;
   - aggiunge i marker, crea la taratura e il burn-in, ricarica loghi e titolo in PNG;
   - chiude con un riepilogo di **controlli** (✓/⚠) che dice cosa fare. Quando qualcosa è
     fuori standard (frame rate, risoluzione, pallino finale…) Genera avvisa ma non blocca.
4. **Rimuovi elementi generati** cancella solo ciò che ha creato LeaderKit:
   marker, audio, coda, immagini e burn-in. Il blocco di testa resta.

Tracce create da Genera:

| Traccia | Contenuto |
|---|---|
| LeaderKit Pop (audio) | tono di line-up, 2-pop, sync, tail pop |
| LeaderKit Grafica | taratura sul countdown, quadranti degli stili Quadrante e Orologio |
| LeaderKit Burn-in | burn-in delle copie di lavoro |

Loghi, titolo in PNG, frame lines, safe area e pallino finale stanno **dentro il
generatore**: si vedono subito, senza tracce in più. Le tracce Logo della 0.10
vengono tolte da Genera e da Rimuovi.

Tutte le immagini (taratura, quadranti) vengono disegnate da Genera **pixel per
pixel alla risoluzione esatta della timeline**. Sono PNG con trasparenza,
salvati in `~/.leaderkit` e riusati se nulla cambia. Se Resolve accorcia le
immagini fisse alla durata standard, Genera le ripete fino a coprire tutto lo
spazio.

## Schede dell'Inspector

| Scheda | Contenuto |
|---|---|
| **Progetto** | standard, rullo, durata del programma, slot, break TV, marker, coda, **Genera** / **Rimuovi**, esito e timecode calcolati, durate personalizzate |
| **Dati** | *Produzione*: titolo, produzione, produttore, regia, cliente, agenzia, codice (Ad-ID/Clock/Auditel), episodio/rullo, lingua, data con bottone **Oggi** e spunta **Data sempre aggiornata**. *Post-produzione*: montaggio, assistente al montaggio, color, suono, VFX, versione, fase, stato dei reparti (TEMP/FINAL), note |
| **Aspetto** | stile della slate, titolo in PNG, logo e secondo logo con **Scegli…** (posizione, larghezza, anche sulla coda), **logo e dati sul countdown**, colori |
| **Guide** | frame lines (formato della timeline e 1.33–2.39), safe area 93% e 90%, dove mostrarle (slate, countdown), colore delle guide, **pallino sull'ultimo fotogramma** |
| **Tecnico** | spazio colore (letto dal progetto), formato audio, livello del pop, strumenti di taratura |

## Slate

Quattro stili (Aspetto › Slate):

| Stile | Impaginazione |
|---|---|
| **Pannelli** | titolo grande, "Directed by", filo nel colore evidenza. Sotto tre pannelli, **Production**, **Post** e **Technical**, a due sotto-colonne; poi lo stato dei reparti e i timecode |
| **Quadrante** | a sinistra una corona con i fotogrammi del secondo (00–23 a 24 fps, 00–24 a 25…) e una tacca che gira, con i secondi al FFOA al centro; a destra titolo, standard, dati e fotogrammi al FFOA |
| **Orologio** | a sinistra un cronometro con la lancetta sui secondi al FFOA; a destra il titolo nel colore evidenza e i dati |
| **Minimale** | titolo grande al centro, regia, una riga di dati essenziali, stato dei reparti |

- **Campi**: compaiono solo quelli compilati. I pannelli si accorciano quando i campi sono pochi e i testi lunghi si riducono, mai sotto l'80%.
- **Stato dei reparti** (color, suono, VFX, musica, titoli): badge a grandezza fissa, **FINAL** in verde e **TEMP** nel colore evidenza.
- **Titolo in PNG** (con trasparenza): **Scegli il titolo in PNG…** lo carica nel generatore e lo
  impagina subito nel riquadro del titolo dello stile scelto, con le proporzioni del file; il titolo
  di testo sparisce.
- **Loghi**: **Scegli il logo…** apre il selettore di Fusion; il logo compare subito nell'angolo
  scelto, largo la percentuale indicata del quadro, con margini esatti (3,5% / 4%). Il percorso si
  può anche incollare nel campo. PNG e JPG; Genera lo ricarica nel blocco e, se richiesto, nella coda,
  e segnala file mancanti o non leggibili.
- **Layout**: si adatta a 16:9, 2:1, DCI Flat/Scope e 4:3.

Slate, barre e countdown, i quattro stili tra loro e ogni elemento facoltativo
(guide, loghi, flash, pallino…) si accendono con nodi Dissolve: Fusion calcola
solo la parte visibile. I testi dei pannelli sono raccolti in pochi Text+ a più
righe (etichette e valori allineati riga per riga) e le forme dello stesso
colore usano un solo sfondo con le maschere in catena: sulla slate Pannelli
Fusion calcola 18 Text+ e 20 Merge invece di 58 e 69. I pannelli hanno altezza
fissa (6 righe; con più campi la colonna si riduce) e ogni tabella legge solo i
campi della sua colonna: per fotogramma le letture dei campi sono 287 invece di 713.

## Frame lines, safe area e pallino finale

Scheda **Guide**. Sono disegnate nel generatore, **sotto i testi** della slate e
sotto il countdown (e quindi sotto la taratura), e seguono dal vivo la timeline:
- **Formato della timeline** e formati 1.33, 1.66, 1.78, 1.85, 2.00, 2.20, 2.39:
  letterbox o pillarbox in automatico, area attiva a **pixel interi e pari**;
- ogni linea ha l'etichetta con **formato e risoluzione reale in quella
  timeline**, per esempio `2.39:1 · 1920 × 804` su 1920×1080, `1.85:1 · 3552 × 1920`
  su 2:1;
- safe action 93% e safe title 90%;
- spunte **Sulla slate** e **Sul countdown**. Di default nessuna guida è attiva;
- **colore delle guide** (bianco di default) per linee ed etichette; le etichette
  hanno un contorno nero, così si leggono anche sopra altre linee.

## Logo e dati sul countdown

Scheda **Aspetto › Countdown**, con spunte:
- **Logo sopra il countdown**: il logo principale, centrato sopra il cerchio
  (sulla linea verticale), nello spazio libero tra cerchio e bordo; dimensione
  regolabile;
- **Dati sotto il countdown**: titolo (e versione) sulla prima riga, poi i ruoli
  scelti due per riga (regia, produzione, montaggio, assistente al montaggio,
  color, suono, codice, data), presi dai campi già compilati, con contorno nero.

Restano dentro lo spazio libero su 16:9, 2:1, 4:3 e 2.39 e lontani dalle griglie
della taratura.

**Pallino sull'ultimo fotogramma**: il fotogramma prima del FFOA mostra un pallino
(in alto a destra come i cue mark della pellicola, al centro o in alto a sinistra;
diametro in % dell'altezza) per dire che il programma parte al fotogramma dopo.
Spento di default: per gli standard di consegna Genera ricorda che è previsto nero
fino al FFOA, ma lo lascia se lo vuoi.

## Countdown e taratura

Il countdown (8→2, Picture Start, braccio, 2-pop) è calcolato a ogni fotogramma
dal frame rate della timeline: 48 fotogrammi a 24/23.976, 50 a 25, 60 a 29.97 DF.

Gli strumenti di taratura sono ispirati al leader digitale SMPTE RP 428-6 e sono
un PNG statico sopra il countdown:
- **griglie di risoluzione** negli angoli, con righe da 1, 2, 3 e 4 px verticali
  e orizzontali: al 100% devono essere nette; se quelle da 1 px si impastano,
  l'immagine è morbida o è stata scalata;
- mirino centrale;
- scala di grigi a 11 gradini;
- patch RGBCMY;
- rampe continue B/N, R, G, B;
- verifica del blu (Wratten 47B);
- sfera sfumata per il contouring;
- bianco di picco e bianchi vicini al clip;
- neri (PLUGE 2/4/8%);
- etichette fps, risoluzione e formato.

Frame lines e safe area non sono più nel PNG: stanno nel generatore, sotto i
testi (vedi sopra).

## Standard inclusi

Fonte dei valori: `docs/industry-standards.md` (la sezione è indicata in ogni
preset di `fx/standards.json`).

Gli standard con \* non hanno una specifica tecnica pubblica. I loro valori
(barre 20" + clock 7" + nero 3", FFOA 10:00:00:00, coda 3") sono un riferimento
prudente, e Genera lo segnala nei controlli. Vanno sempre verificati con il
capitolato del committente.

| Categoria | Standard |
|---|---|
| Cinema | Cinema — DCP (container DCI Flat/Scope/Full 2K e 4K), Cinema — Doppiaggio / M&E |
| TV Italia | RAI (programmi)\*, Mediaset (programmi)\*, Sky Italia\* |
| TV Europa / UK | EBU (generico)\*, DPP (BBC, ITV, C4…), Sky UK |
| Spot | RAI, Publitalia / Mediaset, USA |
| Streaming | Netflix / IMF |
| Copia lavoro | Giornalieri / sync, Montaggio / review, Suono / mix / VO, VFX, Approvazione cliente |
| Altro | Videoclip / Live, Personalizzato / review |

Ogni standard ha la coda. Spot Publitalia e Spot USA non la prevedono: per loro
sono 2" di nero, disattivabili.

### Durata del programma

- **Libera**: il programma finisce con l'ultimo clip audio o video.
- **Slot** della categoria: Genera crea subito il **contenitore** (marker con
  durata, LFOA e coda alla fine esatta) e segnala di quanti fotogrammi il
  montato è più lungo o più corto.
- **TC di fine** o **personalizzata** (`HH:MM:SS:FF`).

| Categoria | Slot |
|---|---|
| Cinema | Corto 15'/30', Mediometraggio 60', Lungometraggio 90'/100'/120' |
| TV | Film TV 90'/100', Fiction/serie 50', Serie 25', TV 13' (parte), TV 26', TV 45', Documentario TV 52' |
| Spot | 10", 15", 20", 30", 45", 60", 90", 120" |
| Streaming | Episodio 25'/50', Documentario 52', Film 90'/100'/120' |

**Break TV** (solo standard TV):
- nessuno;
- automatici secondo la direttiva AVMSD (film, film TV e notiziari: al massimo
  un'interruzione ogni 30' programmati);
- da 1 a 6 break manuali.

Genera mette i marker e avvisa se il numero di break supera il limite AVMSD.

## Copie di lavoro e burn-in

Gli standard **Copia lavoro** creano un leader corto e un clip **LeaderKit
Burn-in** sulla sua traccia, sopra il montato, dal FFOA all'LFOA.
- **Inserimento**: Genera blocca per un attimo tutte le altre tracce, così il
  montato non viene toccato.
- **Se non riesce**: lo segnala. Basta trascinare il generatore a mano e premere
  **Aggiorna dai metadati**.

Il burn-in legge da Resolve, clip per clip:
- nome del file di camera (senza estensione);
- Start TC e punto d'ingresso (il Source TC che scorre);
- scena, shot, take e take cerchiata;
- camera e reel/roll;
- data di ripresa;
- sound roll e TC dell'audio sotto (per verificare il sync);
- spazio colore del progetto.

Impaginazione (convenzioni dailies e review: dati fuori dall'immagine attiva,
etichette esplicite `SRC TC` / `REC TC`, source a sinistra e record a destra come
in Avid):

| | Sinistra | Centro | Destra |
|---|---|---|---|
| **In alto** | nome file · reel e camera | titolo · versione, data | scena / take, formato · colore |
| **In basso** | `SRC TC`, `AUD TC` + sound roll | TC grande (suono, VO) | `REC TC`, contatore `FR` |

Watermark e destinatario stanno al centro. Tutti i blocchi hanno la stessa
grandezza (la più grande con cui ognuno sta nel suo spazio) e un **contorno nero**
(spunta e spessore nella scheda Aspetto, attivo di default), così il timecode si
legge anche sul bianco.

Record TC e contatore fotogrammi sono calcolati a ogni fotogramma. Il segmento del
fotogramma si trova con una **ricerca binaria** su un indice scritto da Aggiorna
(anche con migliaia di tagli ogni fotogramma legge una sola riga), in 4 Text+ (uno
per angolo). La **fase di
lavoro** sceglie i campi, che restano modificabili:

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

**Mascherino** (scheda Aspetto del burn-in). Di default **nessun mascherino e
nessuna banda**: i dati stanno ai bordi del quadro della timeline, qualunque sia
(16:9, 2:1, 4:3, DCI…).
- **Preset**: 1.33, 1.37 Academy, 1.43 IMAX, 1.66, 1.78, 1.85 Flat, 1.90, 2.00,
  2.20, 2.35, 2.39 Scope, 2.76, oppure un rapporto personalizzato con lo slider.
- **Sulla timeline vera**: il mascherino è calcolato sul rapporto reale della
  timeline, che Genera e Aggiorna scrivono nel burn-in, con l'area d'immagine a
  pixel interi e pari (es. 1920×804 per 2.39 su 1920×1080).
- **Letterbox**: se il formato è più largo della timeline, le bande stanno sopra
  e sotto. I dati vanno nelle bande nere, fuori dall'immagine attiva, come
  raccomanda Netflix (Dailies Best Practices). Se una banda è troppo bassa per
  due righe, i dati diventano una riga sola, ridotta quanto basta.
- **Pillarbox**: se il formato è più stretto (es. 1.33 su una timeline 2:1 o
  2.39), le bande stanno ai lati e i dati vanno lì.
- **Formato nativo**: senza mascherino, i dati stanno ai bordi o dentro
  l'immagine (safe 90%); le **bande semitrasparenti** dietro ai dati sono una
  spunta, spenta di default.

L'altezza del testo è una percentuale del quadro, quindi resta la stessa su
16:9, 2:1 e DCI. I dati sono **allineati ai bordi** (sinistra e destra). Se in
una versione di Resolve l'ancoraggio di Text+ non si comporta come previsto,
"Allineamento dei dati › Centrati nelle celle" li riporta al centro delle loro
celle. I dati si aggiornano con **Aggiorna dai metadati**, oppure con Genera.

## Aggiungere o modificare uno standard

Modifica `fx/standards.json` (sezioni `presets`, `categories`, `slots`) e
ricostruisci con `python3 tools/build_fx.py`. Ogni preset contiene:
- durate in secondi nominali;
- TC del FFOA;
- barre, slate/clock, countdown, sync e coda;
- righe della slate;
- frame rate e risoluzioni ammesse;
- note.

## Sviluppo

```
fx/standards.json     standard, categorie, slot
fx/engine_common.lua  motore dei bottoni, parte comune (Rimuovi incorpora solo questa)
fx/engine_burnin.lua  lettura dei metadati e indice del burn-in (Aggiorna, Genera)
fx/engine.lua         Genera
fx/image.lua          logo e titolo in PNG nei Loader (Scegli..., Genera)
fx/overlay.lua        immagini PNG (taratura, quadranti) in Lua puro
tools/build_fx.py     costruisce dist/LeaderKit-<versione>.drfx (generatori Fusion)
tools/preview_fx.py   anteprima approssimata di un fotogramma (Pillow)
tests/                pytest; espressioni e motore eseguiti in Lua 5.4 su comp e timeline simulati
docs/release-notes/   note di ogni versione
```

```bash
pip install pytest pyflakes pillow numpy      # e lua5.4
python3 -m pytest -q tests
python3 tools/build_fx.py
```

La CI esegue test e build a ogni push. Per pubblicare una release si usa
Actions › **Release** › Run workflow con la versione: il workflow controlla che
coincida con `src/leaderkit/__init__.py`, poi esegue i test, costruisce il
`.drfx` e crea tag e release (pre-release per le versioni 0.x).

La prima versione, uno script Python da Workspace › Scripts, è documentata in
[`docs/v0.1-script.md`](docs/v0.1-script.md).

## Da verificare in Resolve

Verificato in Resolve Studio 21.1 fino alla 0.8: resa, schede, Genera, bip,
taratura PNG a piena risoluzione e geometria su 2:1. Da confermare sul campo
(la 0.11 è testata solo su comp e timeline simulati):

1. Fluidità di slate, countdown e burn-in (Dissolve come interruttori, maschere
   in catena con l'ingresso EffectMask, elaborazione a 8 bit).
2. Logo e titolo in PNG nei nodi Loader (0.12: il bottone scrive nel pannello
   "LK" e mostra sempre l'esito): bottone **Scegli…** (selettore
   FileBrowse di Fusion), immagine tenuta per tutta la durata del clip,
   grandezza con il Size del Merge (pixel del file × Size).
3. Ancoraggio a sinistra e a destra dei testi Text+ (tabelle dei pannelli,
   etichette delle guide, burn-in) e interlinea dei testi a più righe.
4. Spessore dei contorni delle frame lines (BorderWidth dei RectangleMask) e
   contorno nero dei testi (elemento 2 di Text+: Enabled2, Thickness2).
5. Coda su timeline vuota con slot lunghi (es. DCP 90': coda a 02:30:08:00).
6. Burn-in: inserimento automatico con le altre tracce bloccate e nomi dei
   metadati delle varie camere (Scene, Take, Camera #, Reel Name, Sound Roll #…).
7. Voci nascoste in base allo standard e data automatica all'export.

Per la riproduzione in tempo reale di blocchi lunghi conviene anche la cache di
Resolve: Riproduzione › Render Cache › Smart.

## Roadmap

- Conferme in Resolve (vedi sopra) e ritocchi grafici.
- Installer Windows e Linux testati; `.drfx` firmato.
- Export dei marker in CSV/EDL.
