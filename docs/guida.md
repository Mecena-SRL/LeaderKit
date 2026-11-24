# Guida d'uso di LeaderKit

Guida pratica per chi monta, fa color o consegna. Per i dettagli tecnici di ogni modulo vedi il
[README](../README.md); per i valori delle norme [`industry-standards.md`](industry-standards.md).

## Indice

1. [Cosa fa](#1-cosa-fa)
2. [Installazione e aggiornamento](#2-installazione-e-aggiornamento)
3. [Il primo leader in cinque minuti](#3-il-primo-leader-in-cinque-minuti)
4. [Quale standard scegliere](#4-quale-standard-scegliere)
5. [Dati e slate](#5-dati-e-slate)
6. [Countdown, taratura e guide](#6-countdown-taratura-e-guide)
7. [Burn-in delle copie di lavoro](#7-burn-in-delle-copie-di-lavoro)
8. [Ricette pronte](#8-ricette-pronte)
9. [Problemi frequenti](#9-problemi-frequenti)

---

## 1. Cosa fa

LeaderKit è un pacchetto di generatori Fusion per DaVinci Resolve 20 o successivo. Crea in un clic:

- **testa**: barre, tono, slate, countdown con 2-pop, nero fino al primo fotogramma (FFOA);
- **coda**: nero, tail pop, eventuale slate di coda;
- **marker** di rullo e di break, contenitore con durata esatta;
- **taratura** (leader SMPTE RP 428-6) e **guide** (frame lines, safe area);
- **burn-in** per giornalieri, montaggio, VFX, color, suono e approvazione cliente.

Tutto si adatta da solo al frame rate e alla risoluzione della timeline.

## 2. Installazione e aggiornamento

1. Scarica `LeaderKit-<versione>.drfx` dalle [Releases](https://github.com/Mecena-SRL/LeaderKit/releases).
2. Doppio clic sul file: Resolve lo installa. Riavvia Resolve.
3. In **Effetti › Generators › LeaderKit** trovi *LeaderKit*, *LeaderKit Tail* e *LeaderKit Burn-in*.

Per aggiornare installa il nuovo `.drfx` sopra il vecchio. I clip già sulla timeline tengono i loro
valori: premi **Genera** (o **Aggiorna dai metadati** sul burn-in) per applicare le novità.

## 3. Il primo leader in cinque minuti

1. Trascina **LeaderKit** sulla traccia video nel punto dove deve iniziare il leader. Va bene anche
   una timeline vuota; la lunghezza del clip non conta.
2. Scheda **Progetto**: scegli lo **standard** (vedi sotto) e la **durata del programma**
   (*Libera* = fino all'ultimo clip; *Slot* = durata fissa della categoria).
3. Scheda **Dati**: compila titolo, produzione, regia e i campi che ti servono. Quelli vuoti non
   compaiono.
4. Premi **Genera sulla timeline**. Leggi i **controlli** nell'esito: ✓ va bene, ⚠ c'è qualcosa da
   verificare (frame rate, risoluzione, durata). Genera avvisa ma non blocca.
5. Fai play sul leader. Se cambi standard, stile, tema o taratura, premi di nuovo **Genera**.

**Rimuovi elementi generati** cancella solo quello che ha creato LeaderKit (marker, audio, coda,
immagini, burn-in). Il blocco di testa resta.

## 4. Quale standard scegliere

| Devi consegnare… | Standard | Note |
|---|---|---|
| un film al cinema (DCP) | Cinema — DCP | container Flat/Scope 2K e 4K |
| la versione per il doppiaggio o le M&E | Cinema — Doppiaggio / M&E | |
| un programma a RAI, Mediaset, Sky Italia | TV Italia › … | \* valori prudenziali: verifica il capitolato |
| a BBC, ITV, Channel 4 | DPP | barre 100%, niente barre SMPTE |
| uno spot | Spot › RAI, Publitalia, USA | barre EBU 75% in Italia |
| a Netflix o a una piattaforma IMF | Streaming — Netflix / IMF | |
| un giornaliero, una review, un mix | Copia lavoro › … | crea anche il burn-in |

Gli standard con \* non hanno una specifica pubblica: LeaderKit usa valori di riferimento e lo dice nei
controlli. **Il capitolato del committente vince sempre.**

## 5. Dati e slate

- **Stile della slate** (scheda Slate): *Pannelli* per i dati completi, *Quadrante* e *Orologio* con un
  contatore grafico, *Minimale* per spot e review, *Testa SMPTE Universal* per il cinema.
- **Titolo in PNG** e **loghi**: premi **Scegli…** e prendi il file. Compaiono subito; Genera li ricarica
  anche nella coda se lo chiedi.
- **Stato dei reparti**: per color, suono, VFX, musica e titoli scegli TEMP o FINAL. Sulla slate FINAL è
  verde, TEMP è nel colore evidenza.
- **Data sempre aggiornata**: mette la data del giorno del render.
- I testi lunghi della slate si riducono per stare nel loro riquadro e, se non basta, finiscono con "…".

## 6. Countdown, taratura e guide

- **Countdown › Stile**: *Standard* (leader SMPTE), *Pannelli* (leader classico), *Quadrante* (ghiera con i
  valori). **Tema**: nero, grigio medio, bianco, grigio scuro o personalizzato.
- **Taratura**: accendi *Strumenti di taratura* e scegli i moduli. Genera li disegna alla risoluzione
  esatta della timeline. Servono per fuoco, formato, livelli e gamma; non sostituiscono una sonda.
- **Guide**: frame lines (1.33 → 2.39 e formato della timeline), safe action 93% e safe title 90%, con un
  colore per ogni linea. Si mostrano sulla slate e/o sul countdown.
- **Pallino sull'ultimo fotogramma**: dice che il programma parte al fotogramma dopo. Spento di default
  perché le consegne vogliono nero fino al FFOA.

## 7. Burn-in delle copie di lavoro

### Come si crea

- Con uno standard **Copia lavoro**, Genera mette il clip **LeaderKit Burn-in** sulla sua traccia, sopra
  il montato, dal FFOA all'LFOA.
- In alternativa trascina *LeaderKit Burn-in* sopra il montato a mano e premi **Aggiorna dai metadati**.

**Importante:** i dati (nomi dei clip, TC, scena, take…) si leggono solo quando premi **Aggiorna dai
metadati** (o Genera). Dopo aver cambiato montaggio, canali o metadati, premilo di nuovo. Record TC e
contatore invece scorrono da soli.

### Fase di lavoro

La **fase** accende i campi giusti; poi puoi cambiarli a mano nella scheda Campi.

| Fase | Cosa mostra |
|---|---|
| Scarico / verifica DIT | source TC, clip, reel, camera, data, formato, colore |
| Sync audio-video | source TC, TC audio e sound roll, formato audio, clip, scena/take, camera, reel |
| Giornalieri | source TC, clip, scena/take, camera, reel, data, titolo, watermark |
| Montaggio / offline review | record e source TC, clip, titolo, versione, data, watermark |
| VFX | source TC, contatore da 1001, clip, reel, versione, formato |
| Color review | record e source TC, clip, versione, colore, formato |
| Suono / mix / VO | record TC anche grande, contatore, formato audio, titolo, versione |
| Approvazione cliente | record TC, titolo, versione, data, watermark con destinatario |

### Dove stanno i dati

| | Sinistra | Centro | Destra |
|---|---|---|---|
| **In alto** | nome file · reel e camera | titolo · versione, data | scena / take, formato · colore |
| **In basso** | `SRC TC`, `AUD TC` + sound roll | TC grande (se acceso) | `REC TC`, contatore `FR` |

Source a sinistra e record a destra, come in Avid; etichette esplicite, come nelle linee guida dailies.

### Grandezza dei dati: la regola

Dalla versione 1.3 la grandezza è **quella che scegli, sempre**:

- *Piccolo* 1,3%, *Medio* 1,8% (default), *Grande* 2,6% del **lato corto** del quadro, oppure *Cursore*
  da 1 a 5%. Il lato corto rende la grandezza uguale su 16:9, 2:1, DCI e sui verticali.
- **Mai sotto 10 px** di maiuscole, anche a 720p e 480p.
- Tutti i blocchi hanno la stessa grandezza per tutto il programma.

| Timeline | Piccolo | Medio | Grande |
|---|---|---|---|
| 1280×720 | 10 px | 13 px | 19 px |
| 1920×1080, 1080×1920 | 14 px | 19 px | 28 px |
| 3840×2160 | 28 px | 39 px | 56 px |

(altezza delle maiuscole)

Prima della 1.3 la grandezza poteva scendere da sola: bastava un nome di file lungo in un punto qualsiasi
del programma, o una banda del mascherino bassa (per esempio 1.85 su 16:9, 22 px), e tutti i dati
diventavano piccoli, anche con *Grande*. Ora succede questo:

| Situazione | Con *Grandezza fissa* (default) | Con *Riduci i testi lunghi* |
|---|---|---|
| riga troppo lunga per il suo spazio | si tronca con "…" | si riduce fino al 70%, poi si tronca |
| banda del mascherino troppo bassa | i dati vanno dentro l'immagine | si riducono fino al 70%, poi vanno dentro l'immagine |
| bande laterali (pillarbox) strette | i dati vanno ai bordi del quadro | si riducono fino al 70%, poi vanno ai bordi |

La scelta è in **Aspetto › Testi lunghi e bande strette**. Se i nomi dei file vengono troncati e li vuoi
interi, scegli *Riduci* oppure una grandezza più piccola.

### Mascherino e posizione

- **Mascherino** (Aspetto): nessuno di default. Con un formato più largo della timeline (letterbox) i dati
  stanno nelle bande nere, fuori dall'immagine, se ci stanno alla grandezza scelta. Con un formato più
  stretto (pillarbox) vanno nelle bande laterali, una voce per riga.
- **Posizione dei dati**: *Ai bordi* (default) o *Dentro l'immagine* (safe title 90%, utile se il player
  del cliente taglia i bordi).
- **Bande semitrasparenti**: una fascia scura dietro ai dati, utile su immagini chiare senza mascherino.
- **Contorno nero**: acceso di default, rende leggibili i dati anche sul bianco.

### TC grande, watermark, canali

- **TC grande** (suono, VO, doppiaggio): ha grandezza, posizione e colore suoi.
- **Watermark**: fino a tre, in alto, al centro o in basso, con testi pronti in italiano e inglese. Il
  **destinatario** (screener) va sotto il watermark 1.
- **Canali**: scegli da quali tracce video (V1-V8) e audio (A1-A8) leggere i dati. I dati principali
  vengono dalla traccia video più alta tra quelle scelte, il TC audio dalla più bassa. *Mostra l'elenco
  dei canali letti* aggiunge una riga per ogni traccia.

## 8. Ricette pronte

**Giornalieri per la regia**
Standard *Copia lavoro › Giornalieri*, fase *Giornalieri*, mascherino del formato di ripresa (es. 2.39),
watermark *CONFIDENZIALE* in basso, grandezza *Medio*.

**Review del montaggio con il cliente**
Fase *Approvazione cliente*, watermark *SOLO PER REVISIONE* al centro con opacità 0.15, destinatario con
il nome del cliente, *Dentro l'immagine* se lo guarda sul telefono.

**Turnover al suono**
Fase *Suono / mix / VO*, TC grande *Più in basso*, contatore *Programma da 0*, formato audio acceso.

**Pull VFX**
Fase *VFX*, contatore *Per clip da 1001*, nome clip e reel accesi, nessun watermark.

**Spot per la TV italiana**
Standard *Spot › RAI* o *Publitalia*, slot della durata (15", 30"…), slate *Minimale*, barre *Dallo
standard* (EBU 75%).

## 9. Problemi frequenti

**I dati del burn-in sono piccoli.**
Dalla 1.3 la grandezza è quella scelta in *Aspetto*. Se un burn-in creato con una versione precedente è
ancora piccolo, controlla *Dimensione dei dati ai lati* e *Testi lunghi e bande strette*, poi premi
**Aggiorna dai metadati**: scrive la risoluzione della timeline nel burn-in.

**I nomi dei file finiscono con "…".**
Non c'è spazio alla grandezza scelta. Scegli *Riduci i testi lunghi*, una grandezza più piccola, o spegni
campi che non servono (reel, camera) per lasciare spazio.

**Il burn-in mostra dati vecchi o vuoti.**
Premi **Aggiorna dai metadati**. Controlla nella scheda Canali che la traccia del montato sia spuntata.

**Scena, take o camera non compaiono.**
LeaderKit legge i metadati del media pool (Scene, Take, Camera #, Reel Name, Sound Roll #…). Se la camera
li scrive con altri nomi, compilali nel media pool o con un Metadata preset.

**Il logo non si vede.**
Usa PNG o JPG; ripremi **Scegli…** o Genera. L'esito dice se il file manca o non è leggibile.

**Il playback del leader scatta.**
Attiva *Riproduzione › Render Cache › Smart*: Genera accende la cache dell'uscita Fusion su testa e coda.

**Genera mostra un ⚠.**
Leggi la riga: di solito frame rate o risoluzione fuori standard, o il montato più lungo dello slot. È un
avviso, non un errore.
