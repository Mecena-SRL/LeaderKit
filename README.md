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
   - aggiunge i marker e crea taratura, loghi, titolo e burn-in;
   - chiude con un riepilogo di **controlli** (✓/⚠) che dice cosa fare.
4. **Rimuovi elementi generati** cancella solo ciò che ha creato LeaderKit:
   marker, audio, coda, immagini e burn-in. Il blocco di testa resta.
5. **Aggiorna solo le immagini** (nelle schede Tecnico, Aspetto e Taratura)
   rifà taratura, frame lines, slate fissa, titolo e loghi dopo aver cambiato
   quelle impostazioni. Non tocca blocco, coda, audio, marker, timecode e
   burn-in.

Se una parte non riesce (per esempio un logo in un formato che Resolve non
importa), le altre vengono fatte lo stesso e il riepilogo dice cosa è andato
storto e perché.

Tracce create da Genera:

| Traccia | Contenuto |
|---|---|
| LeaderKit Pop (audio) | tono di line-up, 2-pop, sync, tail pop |
| LeaderKit Grafica | taratura e frame lines sul countdown, quadranti degli stili Quadrante e Orologio |
| LeaderKit Logo, Logo 2, Logo Titolo | logo di produzione, secondo logo, titolo in PNG |
| LeaderKit Slate | la slate come immagine fissa (con titolo e loghi già dentro) |
| LeaderKit Burn-in | burn-in delle copie di lavoro |

**Fluidità**:
- **Slate fissa**: la slate è testo fermo, quindi Genera la fa esportare da
  Resolve una volta, alla risoluzione della timeline, e la mette come immagine
  sulla traccia LeaderKit Slate. Nel blocco la slate non viene più calcolata.
  Con l'orologio TV (o lo stile Orologio) crea un'immagine per ogni secondo.
  Lo stile Quadrante resta in tempo reale, perché la tacca si muove a ogni
  fotogramma. Si può spegnere in Aspetto › Slate come immagine fissa.
  Se cambi testi, stile o loghi, premi **Aggiorna solo le immagini**.
- **Espressioni leggere**: Genera scrive nei generatori risoluzione e frame rate
  della timeline, così i testi non li richiedono a ogni fotogramma. Se cambi la
  risoluzione della timeline, premi di nuovo Genera (o Aggiorna dai metadati
  per il burn-in).
- **Cache Fusion**: attivata su testa e coda ("Render Cache Fusion Output" su
  On; serve Playback › Render Cache su Smart o User).

Tutte le immagini (taratura, quadranti) vengono disegnate da Genera **pixel per
pixel alla risoluzione esatta della timeline**. Sono PNG con trasparenza,
salvati in `~/.leaderkit` e riusati se nulla cambia. Se Resolve accorcia le
immagini fisse alla durata standard, Genera le ripete fino a coprire tutto lo
spazio.

## Schede dell'Inspector

| Scheda | Contenuto |
|---|---|
| **Progetto** | standard, rullo, durata del programma, slot, break TV, marker, coda, **Genera** / **Rimuovi**, guida timecode e timecode calcolati |
| **Produzione** | titolo, produzione, produttore, regia, cliente, agenzia, codice (Ad-ID/Clock/Auditel), episodio/rullo, lingua, data con bottone **Oggi** e spunta **Data sempre aggiornata** (vale a ogni render) |
| **Post** | montaggio, color, suono, VFX, versione, fase di lavorazione, stato dei reparti (TEMP/FINAL), note |
| **Tecnico** | frame lines 1.33–2.39 e safe area 93% / 90% (sul countdown, si aggiornano con Genera), spazio colore (letto dal progetto), **audio**: canali, campionamento e loudness da preset più note libere, livello del pop |
| **Aspetto** | stile della slate, titolo in PNG, colori (testo, sfondo, grafica, evidenza), logo di produzione e secondo logo (file, posizione, dimensione, anche sulla coda) |
| **Taratura** | strumenti sul countdown (vedi sotto) |

### Audio

Nella scheda Tecnico:
- **Canali**: mono, stereo, 5.1 (L R C LFE Ls Rs), 5.1 + stereo 7-8, 7.1, 7.1 + 5.1 + stereo, Atmos + 5.1 + stereo, M&E 5.1 + M&E stereo, stem DX/MX/FX, 8 mono con stereo su 1-2 (RAI spot), stereo 1-2 duplicato su 3-4 (Publitalia).
- **Campionamento**: 48 kHz 24 bit, 48 kHz 16 bit, 96 kHz 24 bit.
- **Loudness**: il target dello standard scelto, oppure uno tra EBU R128 (−23 LUFS / −1 dBTP), R128 s1 per gli spot, RAI spot (−23 LUFS ±0,2 / −2 dBTP), AGCOM / Publitalia (−24 LKFS ±0,5), ATSC A/85 (−24 LKFS / −2 dBTP), Netflix (−27 LKFS dialogue-gated / −2 dBTP), web (−14 LUFS). I valori vengono da `docs/industry-standards.md`.
- **Note audio**: testo libero che si aggiunge a quanto sopra.

Sulla slate compaiono i campi AUDIO e LOUDNESS. LeaderKit non misura il loudness: lo riporta come target.

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
- **Titolo in PNG** (con trasparenza): Genera lo impagina nel riquadro del titolo dello stile scelto, leggendo le proporzioni dal file, e il titolo di testo sparisce.
- **Loghi**: logo di produzione e secondo logo vanno negli angoli scelti, con margini esatti. Si scelgono con il selettore di file (anche se l'immagine è già nel Media Pool), oppure mettendo l'immagine nei bin "LeaderKit Logo" / "LeaderKit Logo 2" del Media Pool. Se non c'è nessun logo, il riepilogo di Genera lo dice.
- **Layout**: si adatta a 16:9, 2:1, DCI Flat/Scope e 4:3.

Slate, barre e countdown, e i quattro stili tra loro, si alternano con nodi
Dissolve: Fusion calcola solo la parte visibile.

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
- etichette fps, risoluzione e formato;
- frame lines dei formati scelti e safe area.

Gli strumenti usano tutta la timeline e stanno **sopra** le frame lines: le
frame lines si riferiscono ai formati, la taratura alla timeline. Si possono
attivare tutte le frame lines insieme.

**Ultimo fotogramma prima del programma** (Taratura): nero come da standard,
pallino di cue in alto a destra, pallino al centro, cartello PROGRAM START con
il timecode del FFOA, oppure flash bianco. Compare solo sul fotogramma che
precede il FFOA (per esempio 00:59:59:23 con FFOA a 01:00:00:00).

Sotto il cerchio del countdown c'è una riga con **titolo, produzione, regia e
montaggio** e il **logo di produzione** in piccolo (Taratura › Dati del progetto
nel countdown / Logo della produzione nel countdown).

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
- nome del clip;
- Start TC e punto d'ingresso (il Source TC che scorre);
- scena, shot, take e take cerchiata;
- camera e reel/roll;
- data di ripresa;
- sound roll e TC dell'audio sotto (per verificare il sync);
- spazio colore del progetto.

Record TC e contatore fotogrammi sono calcolati a ogni fotogramma, con una
ricerca veloce nella tabella dei clip (la riproduzione non rallenta). Tutti i
testi hanno un contorno nero, leggibile anche sul bianco. La **fase di
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

**Mascherino** (scheda Aspetto del burn-in):
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
- **Formato nativo** ("Nessuno"): nessuna banda. I dati stanno ai bordi,
  sull'immagine, con il contorno nero. In alternativa si possono mettere dentro
  l'immagine (safe 90%) o in bande proprie semitrasparenti (Posizione dei dati).

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
fx/engine.lua         motore dei bottoni (Genera, Rimuovi, Aggiorna burn-in)
fx/overlay.lua        immagini PNG (taratura, frame lines, quadranti) in Lua puro
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
taratura PNG a piena risoluzione e geometria su 2:1. Da confermare sul campo:

1. Slate fissa: esportazione con ExportCurrentFrameAsStill (API di Resolve
   18.5+) e riproduzione fluida di slate e burn-in.
2. Ancoraggio a sinistra e a destra dei testi Text+ (burn-in, stili Quadrante e
   Orologio).
3. Loghi e titolo PNG: posizione e durata sulla slate e sulla coda.
4. Coda su timeline vuota con slot lunghi (es. DCP 90': coda a 02:30:08:00).
5. Burn-in: inserimento automatico con le altre tracce bloccate e nomi dei
   metadati delle varie camere (Scene, Take, Camera #, Reel Name, Sound Roll #…).
6. Voci nascoste in base allo standard e data automatica all'export.

## Roadmap

- Conferme in Resolve (vedi sopra) e ritocchi grafici.
- Installer Windows e Linux testati; `.drfx` firmato.
- Export dei marker in CSV/EDL.
