# Preset "Prova di proiezione" — appunti (da progettare)

Idea: un blocco lungo (1–3 minuti) da mettere in un DCP o in un file di prova per verificare
in sala o in regia sync, suono, immagine e mascherini. Nessuna specifica unica: i test DCP
commerciali e quelli degli integratori mettono insieme le stesse prove.

## Contenuto proposto

| Parte | Durata | Cosa verifica | Come |
|---|---|---|---|
| Taratura LeaderKit | 20" | fuoco, formato, livelli, colore, overscan | la schermata del countdown (SMPTE RP 428-6) ferma |
| Sync a pallina | 30" | ritardo audio/video, frame per frame | una pallina rimbalza su una linea; all'impatto flash bianco e bip 1 kHz dello stesso fotogramma; accanto il contatore dei fotogrammi e una scala ±10 fotogrammi: se il bip arriva prima/dopo si legge di quanti fotogrammi |
| Sync ogni secondo | 20" | deriva del sync nel tempo | flash e bip a ogni secondo, numerati |
| Identificazione canali | 5.1: 30", 7.1: 40" | cablaggio e mappa dei canali | voce e nome del canale a schermo (L, C, R, Ls, Rs, LFE…), un canale per volta |
| Rumore rosa per canale | 10" a canale | livelli dei diffusori | rumore rosa -20 dBFS RMS (in sala ≈ 85 dBC per i canali frontali, curva X ISO 2969 / SMPTE ST 202) |
| Panoramiche | 20" | judder e cadenza (24/25/48 fps) | barre verticali e un reticolo che scorrono a velocità note |
| Contatore | per tutta la durata | fotogrammi persi o doppi | contatore grande e timecode bruciati |

## Note tecniche per LeaderKit

- Si può fare come nuovo standard ("Prova di proiezione") con durate personalizzate: il motore
  genera già tono, pop e flash e sa disegnare PNG alla risoluzione della timeline.
- La pallina e il contatore stanno bene nel generatore (maschere + Transform con espressioni sul
  tempo); il bip dell'impatto lo mette Genera sulla traccia Pop, come il 2-pop.
- Canali e rumore rosa richiedono tracce audio multicanale: da verificare cosa permette l'API di
  Resolve (AppendToTimeline su tracce 5.1/7.1).

## Riferimenti

- Test DCP commerciali (immagine, 5.1/7.1, sync): [CinemaNext test DCP](https://www.cinemanext.com/dcp),
  [DCPready — prova in sala](https://dcpready.com/en/dcp-cinema-screen-test/).
- Clip di sync flash + bip a vari frame rate: [PhotoJoseph, A/V sync tests](https://photojoseph.com/tips/2021/3/30/downloadable-audiovideo-sync-tests-2398-24-25-2997-50-5994).
- SMPTE RP 428-6 (D-Cinema leader), ISO 2969 / SMPTE ST 202 (curva X e livelli di sala).
