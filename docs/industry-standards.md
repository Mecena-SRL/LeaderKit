# Censimento degli standard per leader, slate, countdown, sync pop, coda e marker di break — base di progetto per un plugin DaVinci Resolve a preset

Non esiste un unico standard universale: esistono tre famiglie di layout di testa, tra loro incompatibili, e il plugin deve modellarle come preset distinti. La prima è quella cinema/sound post (leader Academy/SMPTE da 8 secondi, 2-pop a 48 fotogrammi dal primo fotogramma d'azione, FFOA). La seconda è quella broadcast europea DPP/EBU (barre 20", ident clock ≥7", sync opzionale, nero, programma a 10:00:00:00). La terza è quella streaming/spot "a file pulito" (niente barre, slate o countdown; solo 1 secondo di nero o nessun pre-roll). Il vero valore differenziante del plugin non è disegnare un countdown: sono i template di layout parametrici a timecode assoluto e la generazione automatica di marker di rullo/break.

## TL;DR

- **Cinema e post audio**: leader di 8" (countdown 8→2, 2-pop di 1 fotogramma a −2" dal FFOA, tail pop simmetrico). Timecode tipico: Picture Start 01:00:00:00, pop 01:00:06:00, FFOA 01:00:08:00. Per le consegne DCP le specifiche Deluxe richiedono leader Academy di 8" in testa e in coda su ogni rullo, pop "matching the audio" e almeno 1 fotogramma di nero in testa e in coda.
- **Broadcast**: il riferimento pubblico più preciso è il layout DPP (BBC, ITV, Channel 4, Sky, ecc.): 09:59:30:00 barre 100% + tono per 20"; 09:59:50:00 ident clock/slate ≥7" in silenzio; sync opzionale a 09:59:57:06; nero; programma a 10:00:00:00; loudness EBU R128 −23 LUFS. In Italia l'unica specifica RAI pubblica riguarda gli spot. Prevede: ident ≥5", 3" di nero, spot a 10:00:00:00, 3" di nero in coda; −23 LUFS ±0,2, max short-term −18 LUFS, true peak −2 dBTP. Publitalia/Mediaset chiede invece −24 ±0,5 LKFS.
- **Streaming e piattaforme**: Netflix vuole esattamente 1" di nero e silenzio in testa e in coda al programma IMF, a −27 LKFS dialogue-gated. Amazon vuole il file "trimmed to only contain the program material", senza barre, toni o slate. Quindi, per lo streaming, il plugin deve saper generare leader e slate *e anche toglierli*, tenendoli su tracce o versioni separate. Per il marker automatico l'API Resolve offre `Timeline.AddMarker(frameId, color, name, note, duration, customData)` e la lettura di framerate e risoluzione via `GetSetting`.

## Key Findings

1. **Il 2-pop è l'unico elemento davvero universale.** È 1 fotogramma di picture (il "2") più 1 fotogramma di tono a 1 kHz, 2 secondi prima del FFOA. Varia però il riferimento timecode: nel broadcast USA il pop è a 00:59:58:00 con FFOA a 01:00:00:00, nel UK a 10:00:00:00. Nella post cinema il leader parte a 01:00:00:00, il pop è a 01:00:06:00 e il FFOA a 01:00:08:00.
2. **Il DPP UK non usa un "2-pop" classico, ma un sync opzionale diverso**: 2 fotogrammi di bianco ≥50% con 1 fotogramma di tono 1 kHz sul primo bianco, a 09:59:57:06 e non oltre 09:59:57:08. SVT lo raddoppia in 50p (4 fotogrammi di bianco, 2 di tono); Sky lo mette a 09:59:57:00 con 1 fotogramma. Un unico "pop a −2 s" hard-coded fallirebbe il QC su queste specifiche.
3. **La slate "ricca" (regista, montatore, colorista, versione) è una pratica di review e post, non un requisito delle piattaforme.** Netflix la standardizza solo per i VFX: 1 fotogramma, primo fotogramma, dentro l'area immagine finale. Amazon la vieta nel master. Il plugin deve quindi distinguere il "leader di lavorazione" (ricco) dal "leader di consegna" (minimo, conforme).
4. **I marker di cambio rullo hanno oggi due usi reali**: la suddivisione in rulli per il mix audio e il DCP (Deluxe numera i rulli a 01:00:00:00, 02:00:00:00, 03:00:00:00…) e i part/break broadcast. Il DPP richiede per ogni break 5" di freeze o living hold, poi ≥1" di nero, poi clock opzionale al minuto intero −10", poi 3" di nero prima della parte successiva.
5. **Il loudness è il parametro con più varianti**:
   - EBU R128: −23 LUFS ±0,5 LU, −1 dBTP;
   - R128 s1 (spot): −23 LUFS, max short-term −18 LUFS;
   - ATSC A/85/CALM: −24 LKFS ±2 LU, −2 dBTP;
   - Netflix: −27 LKFS ±2 LU dialogue-gated, −2 dBTP;
   - RAI spot: −23 ±0,2 LUFS, −2 dBTP;
   - Publitalia: −24 ±0,5 LKFS.

   Il plugin non misura il loudness, ma deve riportare il target nella slate e nei metadati del preset.

## Details

### A) Cinema

**Academy Leader e SMPTE Universal/Television Leader**
- *Academy Leader* (SMPTE 301): conta in piedi, da 11 a 3. Il beep cade sul "3" ed è muto sulle copie di proiezione 35mm, per non essere udito in sala. Lo standard definisce anche la posizione dei cue mark di fine rullo.
- *SMPTE Universal Leader* (ANSI/SMPTE 55, anni '60): conta in secondi, da 8 a 2, con numeri al centro di un bersaglio a due cerchi e un braccio rotante (lo "sweep"). Prima del countdown compaiono "16 SOUND START", "35 SOUND START" e poi "PICTURE START". Durante il "4" appaiono le lettere "C C F F" (control frames). Sul "2" c'è il beep ("2-pop"). Tra il 1992 e il 2000 il nome è cambiato in "Television Leader".
- *Struttura frame-accurate da replicare*: Picture Start, poi 6 secondi di countdown (8, 7, 6, 5, 4, 3). Il "2" dura 1 solo fotogramma con tono sincronizzato, seguito da nero e silenzio fino al FFOA. Il sync mark resta a 48 fotogrammi dal FFOA indipendentemente dalla velocità (nota di Terburg Leaders). Se un leader a 24 fps viene usato in una timeline a 25, il pop cade a un timecode diverso da "−2:00": il plugin deve ricalcolare il countdown nativo per ciascun framerate.
- *Tail pop*: la pratica documentata da CalArts è un elemento di 4 secondi, con pop a 2 secondi, posto dopo l'ultimo fotogramma. CalArts consiglia di impostare lo start timecode della sequenza a 00:58:30:00, in modo che 01:00:00:00 sia il primo fotogramma di programma.
- *Nota di design*: Terburg ha ridisegnato il clock centrale perché stia dentro un mascherino Scope 2.39:1. Gli elementi grafici del leader vanno quindi dimensionati sull'area attiva più stretta prevista, non sul raster.

**Cue mark di cambio rullo (pellicola).** SMPTE 55/301 definiscono posizione e forma dei cue mark di fine rullo. Nella pratica consolidata sono due, come cerchio in alto a destra: secondo SMPTE 301 (come riportato da Wikipedia, "Cue mark") la sequenza è 4 fotogrammi di motor cue, 172 di immagine, 4 di changeover cue e 18 di immagine, cioè motor cue ai fotogrammi 198–195 dalla fine e changeover cue ai fotogrammi 21–19; SMPTE 55 (Universal) prevede invece 4+168+4+24, con motor cue ai fotogrammi 200–197 e changeover ai 28–25. Questi valori vanno verificati sul testo SMPTE prima di codificarli come default. Per la conversione durata/rullo: il 35mm 4-perf ha 16 fotogrammi per piede, cioè 90 piedi al minuto a 24 fps. Un rullo da 1000 piedi dura nominalmente al massimo 11,11 minuti e una "bobina doppia" da 2000 piedi 22,22 minuti, con un massimo editoriale abituale di 9–10 o 18–20 minuti (Wikipedia, "Cue mark"). Sono buoni default per il generatore "fine rullo N".

**DCP — requisiti di sorgente e di pacchetto**
- *Leader e nero (Deluxe, Specifications for Digital Cinema Source and DCP Content Delivery v5.11, 14/03/2022)*: "Image shall be provided on all reels with (8) second Academy head and tail leader, with 2-pop and tail-pop matching the audio". Serve inoltre almeno 1 fotogramma di nero in testa e in coda al runtime completo, perché in sala il contenuto viene "parcheggiato in pausa" prima della proiezione.
- *Numerazione dei rulli (Deluxe)*: 01:00:00:00 è il Picture Start del rullo 1 e 01:00:08:00 il suo FFOA; 02:00:00:00 è il Picture Start del rullo 2 e 02:00:08:00 il suo FFOA; e così via. Ne deriva il preset "Reel = ora TC".
- *Container DCI*: Flat 1.85 = 1998×1080 (2K) / 3996×2160 (4K); Scope 2.39 = 2048×858 / 4096×1716. Il Full container 2048×1080 / 4096×2160 viene ridimensionato o ritagliato.
- *Padding (tabella Deluxe)*:
  - HD 1.78 dentro Flat → 1920×1080 / 3840×2160;
  - Scope dentro Flat → 1998×836;
  - Flat dentro Scope → 1588×858;
  - 1.90 dentro Flat → 1998×1051;
  - 2.35 dentro Scope → 2016×858.
- *Framerate*: le frequenze drop (23,976, 29,97) non sono supportate dal digital cinema e vengono convertite. Il plugin dovrebbe segnalarlo quando il preset "DCP" viene applicato a una timeline a 23,976.
- *Immagine (DCI DCSS)*: XYZ con gamma 2,6, 12 bit, JPEG 2000 con massimo 250 Mbit/s. Il 2K ammette 24 o 48 fps, il 4K 24 fps. Audio PCM Broadcast Wave a 48 o 96 kHz, 24 bit, fino a 16 canali, in rulli corrispondenti ai rulli immagine.
- *Netflix DCP*: di default Interop, SMPTE dove richiesto. Interop solo a 24 fps. SMPTE a 24/25/30 fps in 2K/4K e a 48/50/60 fps in 2K. Container 4K 3996×2160 o 4096×1716, bitrate 250 Mb/s (500 per HDR/HFR). Le MXF audio devono avere un numero pari di tracce.

**Mascherini di ripresa e di proiezione.** Nel digitale la "proiezione" coincide con il container DCI o con il raster di consegna. Il plugin dovrebbe quindi offrire due livelli di guide:
- *camera/extraction guide*: area sensore e frame line di ripresa;
- *projection/delivery guide*: 1.85, 2.39, 1.78, 1.90, 1.43 IMAX, 1.37 Academy, 2.00, 2.20, più le protezioni 14:9 e 4:3 del broadcast.

Per la pellicola 35mm, i valori classici della letteratura (SMPTE 59/195, American Cinematographer Manual) sono:
- camera aperture Academy 0,866×0,630 in; projection aperture Academy 0,825×0,602 in;
- 1.85 proiettato 0,825×0,446 in;
- Scope anamorfico proiettato 0,825×0,690 in (desqueeze 2×);
- Full/Super 35 camera 0,980×0,735 in.

Questi valori non li ho verificati sui testi SMPTE in questa ricerca: vanno controllati prima di trasformarli in preset. La lezione progettuale è che la projection aperture è sempre leggermente più piccola della camera aperture. Il mascherino di proiezione va quindi disegnato come margine di sicurezza interno, non coincidente.

### B) Broadcast internazionale

**UK DPP (AS-11 UK DPP) — il template più preciso disponibile pubblicamente.** Il layout è condiviso da BBC, BT Sport, Channel 4, Channel 5, ITV, Sky, STV e TG4. Quello che segue è il testo Channel 4 v5.2 / DPP File v5.0:

| Timecode | Durata | Immagine | Audio |
|---|---|---|---|
| 09:59:30:00 | 20" | Barre 100% (100/0/100/0), BT.2100 per UHD | Line-up tone |
| 09:59:50:00 | ≥7" | Ident clock o slate | Silenzio |
| 09:59:57:06 (opz.) | 2 fr | ≥50% bianco | 1 fr di 1 kHz sul primo bianco (non oltre 09:59:57:08) |
| — | ≥2"18fr | Nero | Silenzio |
| 10:00:00:00 | — | Programma | Programma |
| Fine parte | 5" | Freeze o "living hold" | Fade o taglio a silenzio entro fine parte |
| Fine parte +5" | ≥1" | Nero | Silenzio |
| Minuto intero successivo −10" (opz.) | 7" | Ident clock/slate parte successiva | Silenzio |
| Inizio parte −3" | 3" | Nero | Silenzio |

Dettagli collegati:
- *Barre*: le barre SMPTE "non sono accettabili"; servono barre 100% a pieno raster 16:9.
- *Video HD*: 1080i/25 top field first, BT.709, 4:2:2. Range 10 bit atteso 64–940, "preferred min/max" 20–984.
- *Variante SVT (v5.1)*: sync di 4 fotogrammi di bianco e 2 di tono in 50p; 2 e 1 in 25i.
- *Variante Sky*: 09:59:50:00 slate "Asset Info" di 7", sync plop opzionale a 09:59:57:00 (1 fotogramma di bianco, tono su tutte le tracce), 3" di nero, FFOA. In coda: 3" di "End of Programme Card", 2" di holding frame, 10" di nero prima dei textless.
- *NRK*: "There must be no audio tone or ident over the clock".
- *Metadati AS-11*: il file porta una traccia di segmentazione che distingue programma e "non-programme content (black, ident, clock)". È il motivo per cui in Premiere gli utenti usano marker per Line-up, Clock e parti. Un plugin Resolve può esportare questi timecode come marker e come CSV/XML per il tool di metadati DPP.

**BBC (documento storico, Technical Standards for Network Television Programme Delivery v1.3, 2002).** Ancora utile per le regole grafiche:
- programma a 10:00:00:00; 10" di freeze o living hold a fine programma;
- rullo 2 preferibilmente a 13:00:00:00;
- tono stereo EBU con identificazione del solo canale sinistro tramite interruzioni del tono 1 kHz di 250 ms ogni 3 secondi (EBU R49, citata in EBU Tech 3304); riferimento digitale −18 dBFS (EBU R68);
- lip-sync entro 10 ms;
- tabella delle safe area (16:9 protetto UK: action 93%×93%, caption 80%×90%; 14:9 protetto: action 80%, caption 70% della larghezza attiva).

Sul clock BBC le fonti sono secondarie (Creative COW, spec dei broadcaster di area Imago). Riportano un clock circolare di almeno 20" con lancetta a scatti di 1", un campo testo per i dettagli del programma, taglio a nero a −3", e almeno 15" di nero e silenzio tra la fine di un programma e il clock del successivo.

**EBU**
- *R128 (v5.0, novembre 2023)*: −23 LUFS, tolleranza ±0,5 LU (±1 LU per il live), max true peak −1 dBTP. LRA sconsigliata sotto il minuto.
- *R128 s1 (short-form, spot e promo)*: −23 LUFS, Maximum Short-term Loudness ≤ −18 LUFS (+5 LU).
- *EBU R95*: safe area. *EBU R103*: gamut (RGB −5/105%, luma −1/103%).
- *EBU Tech 3304 (BLITS, per 5.1)*: toni a −18 dBFS (L/R 880 Hz, C 1320 Hz, LFE 82,5 Hz, Ls/Rs 660 Hz); poi 1 kHz con il sinistro interrotto 4 volte; poi 2 kHz a −24 dBFS su tutti i canali. Secondo EBU Tech 3304 (maggio 2009) la sequenza completa dura esattamente 13,40": ident 5.1 da 0,00 a 4,80", stereo 1 kHz da 4,80 a 10,20", fase 2 kHz da 10,20 a 13,40".

Il plugin può includere generatori di tono EBU stereo, GLITS e BLITS come asset audio.

**USA (reti e spot)**
- *ATSC A/85, reso vincolante dal CALM Act dal 13/12/2012*: −24 LKFS ±2 LU, −2 dBTP. Gli short-form si misurano sul mix intero.
- *Ad-ID*: ha sostituito l'ISCI, che era composto da 8 caratteri (4 lettere più 4 cifre), era in uso dal 1970 ed è stato ritirato nel 2007. Il codice Ad-ID ha 11 caratteri: prefisso inserzionista di 4 più 7. Il 12° carattere opzionale è "H" per HD o "D" per 3D. Il contratto SAG-AFTRA di aprile 2013 lo impone come unico identificativo.
- *Layout spot*: un esempio riportato su un forum Adobe (fonte secondaria) prevede 5" di slate (frame 0–149), 2" di nero (150–209) e spot dal frame 210 a 29,97 fps, senza nero in coda.
- *Act break delle reti*: non ho trovato specifiche pubbliche primarie di NBC, ABC, CBS o FOX su durata del nero e timing degli act break. Il preset "US network" va trattato come configurabile, con default prudenziali.

**News.** Non esistono standard pubblici codificati per bug, lower third e timing dei segmenti. Le uniche regole documentate sono le safe area e le zone riservate ai loghi di rete (vedi RAI e Publitalia sotto). Per le news il plugin dovrebbe offrire soprattutto guide di safe area e zone bug, non leader.

### C) Italia

**RAI — "Specifiche tecniche per la fornitura di spot pubblicitari televisivi in formato HD" (febbraio 2021).** È l'unica specifica RAI di consegna file pubblica trovata. Il testo è stato letto su un mirror di terze parti e va verificato su controllopubblicita.rai.it.
- *Formati*: MXF OP-1a XDCAM HD422 1080i25 (MPEG-2 Long GOP 50 Mbit/s, 4:2:2, 8 bit) oppure MOV ProRes 422 HQ 1080i25 (upper field, 10 bit). Audio "8 canali mono PCM, 48KHz, 24 bit": stereo su 1–2, silenzio su 3–8.
- *Loudness*: Program Loudness −23,0 LUFS ±0,2 LU; Max Short Term −18,0 LUFS ±0,2; Max True Peak −2,0 dBTP ±0,3. La misura parte "dal primo fotogramma escludendo i segnali tecnici di testa e di coda".
- *Code di inizio e di fine (§8.2)*: ≥5" di "coda di identificazione" (identificazione visiva, audio di identificazione o silenzio); 3" di nero e silenzio; spot; ≥3" di nero e silenzio in coda. Il LTC deve "preferenzialmente segnare 10:00:00:00 all'inizio dello Spot" ed essere continuo. RAI usa il nero delle code per il trimming con 5 fotogrammi di separazione tra gli inserti.
- *Altri requisiti*: niente barre né countdown; un solo spot per file; safe area EBU R95; evitare grafiche nelle zone del logo di canale e del logo "pubblicità".
- *Programmi*: non ho trovato una specifica RAI pubblica per la consegna di programmi (barre, tono, slate, countdown, TC di partenza). Probabilmente sta negli allegati contrattuali di produzione, ma è un'inferenza. Non vanno trasposti i valori degli spot ai programmi.

**Publitalia '80 (Mediaset) — "Specifiche tecniche", Ufficio Filmati.**
- *HD*: consegna "solo tramite le Digital Delivery, con le modalità da loro indicate". Nessun layout di testa HD è pubblicato.
- *SD Betacam (storico)*: 30" di barre EBU con 1 kHz al livello di riferimento, 20" di immagine identificativa del prodotto, 10" "comprensivi di countdown e 2 secondi di nero video e silenzio audio".
- *Audio*: allineamento −18 dBFS; picchi ≤ −9 dBFS su QPPM; loudness "−24 ± 0,5 LKFS". Canali 1–2 duplicati su 3–4. Consegna 4 giorni lavorativi prima della messa in onda.
- *Safe area HD*: action 3,5%, graphics 10%.
- *Formati addressable/CTV*: "Non sono richiesti pre o post roll quali: clock/testata, barre video, nero o toni test audio".

**Pratica italiana degli spot (fonti secondarie, vendor di delivery).** Adstream Italia indica 5" di barre 75% con tono a −18 dBFS, poi 7" di slate (Cliente, Prodotto, Agenzia, Casa di produzione, Post-produzione, Clock Number, Titolo, Durata HH:MM:SS:FF, Formato; countdown opzionale), poi 3" di nero. IMD Italia indica slate a 09:59:50:00, nero a 09:59:57:00, spot da 10:00:00:00 a 10:00:29:24 per un 30". È questo il template che conviene usare come preset "Spot IT".

**AGCOM.** Le delibere 34/09/CSP e 219/09/CSP regolano il livello sonoro della pubblicità. Secondo fonti secondarie (Youlean), il preset AGCOM 219/09/CSP usa un gate relativo di −8 dB invece dei −10 della BS.1770 attuale. È questo che spiega la convivenza tra −24 LKFS (Publitalia, prassi AGCOM) e −23 LUFS (RAI 2021, EBU).

**Doppiaggio.** Non ho trovato documenti pubblici AGIS, ANICA o delle sale romane sui leader di sincronizzazione. L'unico riferimento documentato è internazionale. Netflix ammette che printmaster, M&E e stem "may include standard 8 second Academy leader and 2-pops". Richiede però che i file Atmos doppiati corrispondano esattamente alla lunghezza dell'IMF, con "Leader and sync pop shall be removed". Il preset "Doppiaggio/M&E" dovrebbe quindi usare il leader Academy di 8" con 2-pop e tail pop, esportabile anche senza leader.

### D) Streaming

**Netflix**
- *Master*: IMF App #2E (SMPTE ST 2067-21:2016/2020/2023), frame rate nativo, nessun pulldown. "one (1) second of format black and silence at the head and tail of the program". Nel caso 29,97/59,94, il numero di fotogrammi per segmento CPL deve essere divisibile per 5.
- *Audio*: −27 LKFS ±2 LU dialogue-gated (BS.1770-1), true peak ≤ −2 dBFS. Per il mix Atmos originale "Leader and sync pop are preferred but not required".
- *Slate VFX*: 1 fotogramma, primo fotogramma del media, stessa risoluzione, dentro l'area immagine finale, con guida dell'area finale e thumbnail.
- *Specifiche legacy (non-Originals, fonte secondaria)*: da 1 fotogramma a 1" di nero in testa e in coda; nero commerciale ridotto a ≤2".

**Amazon Prime Video (Video Central, aggiornato il 21/08/2026)**
- *Contenuto*: il file deve essere "trimmed to only contain the program material". Vanno rimossi barre e tono, test pattern, slate di produzione, textless, e i neri commerciali più lunghi di 1–2" non dovuti a scelta creativa. Niente loghi di studio o di rete.
- *Formato*: frame rate costante; DAR ammessi 4:3, 1.66, 16:9, 1.85, 2:1, 2.20, 2.35, 2.39, 2.40.
- *Audio*: 5.1 in ordine L-R-C-LFE-Ls-Rs, stereo sui canali 7–8.
- *Loudness*: non ho trovato una fonte primaria e le fonti secondarie divergono: Carbonarc Media indica "-24 to -26 LKFS", mentre Tools for Film cita una "Amazon Prime Video Delivery Specification v2.2" a −24 LUFS integrati (±1 LU) e −2 dBTP. Il valore resta da verificare con Amazon.

**Disney+, Apple TV+, HBO Max.** Non ho trovato specifiche pubbliche equivalenti. Sono tipicamente accessibili solo ai partner sotto NDA.

**Differenza chiave rispetto al broadcast.** Il broadcast vuole il leader *nel file* (barre, clock, nero a timecode fissi). Lo streaming lo vuole *fuori dal file*, tranne 1" di nero, e sposta le informazioni in metadati e manifest (IMF CPL, MMC). Il plugin deve quindi generare il leader su traccia separata o in una timeline "delivery" derivata, con un comando "strip leader".

### E) Spot pubblicitari

- *Durate*: in Italia i formati 15", 20" e 30" sono standard (Mediafriends chiede "durata esatta di 30 secondi"). La tolleranza pratica è zero fotogrammi: RAI e Publitalia vogliono la durata esatta, e Publitalia scrive "non sono ammessi frames in eccedenza". Il plugin deve imporre la durata come vincolo rigido e mostrare lo scarto in fotogrammi rispetto alla durata target.
- *Identificativi*: negli USA si usa l'Ad-ID (11 o 12 caratteri). In Italia RAI assegna tramite portale un "codice identificativo di invio" e l'eventuale codice di tracciamento Auditel. Nel Regno Unito è in uso il "Clock Number", già presente nelle slate Adstream.
- *Campi di slate*: Cliente/Inserzionista, Prodotto, Titolo, Agenzia, Casa di produzione, Post-produzione, Codice (Ad-ID/Clock/Auditel), Durata, Formato, Data, Versione/Lingua, Loudness target.

### F) Videoclip e concerti

Non ho trovato specifiche pubbliche di consegna delle etichette discografiche. Per il multicam live la pratica consolidata è:
- LTC distribuito o jam-sync su tutte le camere e i registratori;
- ciak con timecode a vista o ciak digitale (clap/flash) come fallback;
- genlock dove necessario.

Nel plugin il preset "Videoclip/Concerto" dovrebbe includere:
- un "digital clap" di 1 fotogramma bianco più 1 fotogramma di tono 1 kHz, in testa e in coda, per verificare la deriva, sullo schema tail pop di CalArts;
- una slate con artista, brano, etichetta, ISRC (campo libero), versione (clean/explicit), framerate e TC di partenza;
- per le camere, la generazione di un clip-slate a schermo con TC burnt-in da riprendere in apertura.

### G) Architettura in DaVinci Resolve

**API di scripting (Python/Lua, README ufficiale in Help > Documentation > Developer)**
- *Lettura dei parametri di timeline*: `Project.GetSetting('timelineFrameRate')` restituisce il framerate (per il drop frame si usa il suffisso "DF", es. "29.97 DF"). `timelineResolutionWidth/Height` restituiscono la risoluzione. Anche `Timeline.GetSetting()` accetta chiavi specifiche; chiamata senza parametri restituisce un dizionario completo, utile per scoprire le chiavi di color science e colorspace.
- *Marker*: `Timeline.AddMarker(frameId, color, name, note, duration, customData)` crea i marker, `GetMarkers()` li legge, `DeleteMarkerAtFrame()` li rimuove. Quindi i marker "Fine rullo N", "Break N" e "Slot adv" si generano con un semplice ciclo su intervalli configurabili. Il frameId è un offset rispetto all'inizio della timeline, da verificare sulla propria versione: conviene sempre convertire da timecode assoluto sottraendo lo start timecode. Il campo `customData` permette di taggare i marker creati dal plugin per rigenerarli o cancellarli senza toccare quelli manuali.
- *Lua*: si usano i due punti (`timeline:AddMarker(...)`).

**Fusion.** I generator e i title template (.setting impacchettati in .drfx) espongono controlli nell'Inspector. Il modificatore Text+ "Countdown Timer" ha problemi di timing segnalati sul forum Blackmagic. Il countdown frame-accurate conviene quindi farlo con espressioni o con un modificatore custom che legge il tempo della comp, oppure generarlo via script a fotogrammi calcolati.

**Concorrenza esistente**
- *Slate4DVR* (GitHub, GPL v3): .drfx con Slate Generator e Countdown Leader con sync beep nei Fusion Generators. Consiglia circa 10" totali tra slate e countdown e di spostare manualmente lo start TC.
- *EditingTools.io*: slate generator .drfx gratuito con registrazione.
- Template countdown su Motion Array.
- Leader in clip scaricabili: Terburg (Academy e Universal per framerate, End of Reel, clock di 40" per master broadcast), CalArts.

Nessuno di questi strumenti, per quanto trovato, fa layout a timecode assoluto per specifica (DPP, RAI, Netflix), marker automatici di rullo o break, o adattamento automatico a framerate e aspect ratio. È lì lo spazio di differenziazione.

## Recommendations — preset del plugin

| Preset | Start TC / FFOA | Testa | Sync | Coda | Loudness in slate | Marker auto |
|---|---|---|---|---|---|---|
| **Cinema/DCP** | Rullo N a N:00:00:00, FFOA N:00:08:00 | Academy/Universal 8"; slate prima del Picture Start | 2-pop 1 fr a FFOA −48 fr (−2") | Tail leader 8" con tail pop; ≥1 fr nero | Nessuno (85 dB SPL theatrical) | "Fine rullo N" a 11,11 o 22,22 min max (editoriale 9–10 / 18–20 min), o alla durata scelta |
| **Broadcast UK/DPP** | 10:00:00:00 | 09:59:30 barre 100% 20" + tono; 09:59:50 clock ≥7" | 2 fr bianco + 1 fr tono a 09:59:57:06 (variante 50p: 4+2) | 5" hold + ≥1" nero; clock al minuto −10" per le parti | −23 LUFS / −1 dBTP | Parti/break con catena DPP |
| **Spot Italia (RAI)** | 10:00:00:00 | Ident ≥5" + 3" nero | Nessuno | ≥3" nero | −23 LUFS ±0,2 / −18 ST / −2 dBTP | Nessuno; durata rigida |
| **Spot Italia (Publitalia, prassi vendor)** | 10:00:00:00 | Slate 7" (09:59:50) + 3" nero; barre opzionali | Nessuno | Nessuno | −24 LKFS ±0,5 | Nessuno; durata rigida |
| **Spot USA** | Frame 210 a 29,97 (o 01:00:00:00) | 5" slate con Ad-ID + 2" nero | Opz. | Nessuno | −24 LKFS / −2 dBTP | Nessuno |
| **Netflix/IMF** | Libero (spesso 00:59:59:00 → 01:00:00:00) | Solo 1" nero e silenzio nel master; leader e slate su timeline "work" | Pop solo su stem e printmaster | 1" nero | −27 LKFS dialogue-gated / −2 dBTP | Act-break e REM come metadati o marker |
| **Amazon** | Libero | Nessun pre-roll (≤1–2" di nero) | No | No | Da spec partner | Break come metadati |
| **Doppiaggio/M&E** | 01:00:00:00 leader, FFOA 01:00:08:00 | Academy 8" | 2-pop + tail pop | Tail leader | Target del cliente | Rulli |
| **Videoclip/Live** | 01:00:00:00 o TC di ripresa | Slate clip + digital clap | Clap bianco + tono testa/coda | Clap coda | −14 LUFS (piattaforme web, da configurare) | Sezioni brano |
| **Review/Work-in-progress** | Qualsiasi | Slate ricca: titolo, regista, montatore, colorista, versione, data, stato VFX/colore/mix, colorspace, fps, risoluzione, durata | 2-pop | Tail pop + "END OF REEL/PROGRAM" | Opz. | Rulli per il mix |

**Regole di implementazione consigliate**
1. Esprimere ogni preset come lista di eventi `{TC relativo al FFOA, durata, video, audio}`, ricalcolata in fotogrammi sul framerate reale della timeline, con logica drop-frame per 29,97 e 59,94. Il countdown deve essere nativo per ogni fps, non un clip a 24 fps riusato.
2. Le guide (mascherini) vanno su uno strato separato e disattivabile, con camera guide e projection guide distinte e safe area per EBU R95/DPP (action 93%, graphics 90%/80%).
3. I marker vanno taggati via `customData`, con colori per tipo (per esempio Rosso = fine rullo, Giallo = act break, Verde = slot pubblicitario, Blu = FFOA/LFOA), e resi esportabili in CSV/EDL per i moduli di consegna.
4. Per il vincolo di durata: la coda deve mostrare LFOA, durata effettiva, durata target e scarto in fotogrammi. Per gli spot il preset deve bloccare l'export se lo scarto è diverso da 0.

## Caveats

- La specifica RAI spot 2021 è stata letta su un mirror non ufficiale. I PDF Publitalia non sono datati e descrivono il layout di testa dell'era tape SD. Non esistono specifiche RAI pubbliche per i programmi.
- Il testo BBC 2002 è storico: il layout attuale BBC è quello DPP. I dettagli sul clock BBC (≥20", lancetta a scatti) vengono da forum e da documenti di broadcaster terzi.
- Le dimensioni delle aperture 35mm e le posizioni dei cue mark sono valori di letteratura non verificati sul testo SMPTE. Gli standard SMPTE 55, 59, 195 e 301 sono a pagamento e vanno consultati prima di fissare i default.
- Non ho trovato fonti primarie pubbliche per gli act break delle reti USA, per Disney+, Apple TV+ e HBO Max, per le etichette discografiche e per le prassi di doppiaggio italiane: i relativi preset vanno lasciati configurabili.
- Le specifiche delle piattaforme cambiano spesso (la pagina Amazon è aggiornata al 21/08/2026; Netflix ha più versioni di IMF). Il plugin dovrebbe caricare i preset da file JSON versionati e aggiornabili, non codificarli nel sorgente.