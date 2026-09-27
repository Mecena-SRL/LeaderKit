# Dev Queue

Stato del backlog aggiornato a ogni weekly release readiness. Le note sotto
ogni voce riassumono l'ultimo controllo; i dettagli restano nell'issue.

## Stato del repository (2026-09-27)

- `main` pulito, CI verde, ultima release **v0.12.0** (pre-release) pubblicata
  manualmente da `ivan-94m` il 2026-09-26.
- Versione in `src/leaderkit/__init__.py` coerente con l'ultimo tag.
- 62 test pytest indipendenti da Lua passano; i test che richiedono `lua5.4`
  girano solo in CI (non disponibile in questo ambiente di controllo) — CI li
  dà verdi (124 test alla 0.11/0.12).
- `pyflakes` pulito, `tools/build_fx.py` produce il `.drfx`.
- 2 PR aperte da sessioni precedenti (#10, #11) chiuse in questo giro: erano
  in conflitto con `main` e il loro contenuto è stato superato dalle release
  0.9–0.12 effettivamente unite.

## Issue aperte

| # | Titolo | Priorità | Cosa manca davvero |
|---|---|---|---|
| [#6](https://github.com/Mecena-SRL/LeaderKit/issues/6) | Film Leader (logo, prestazioni, mascherino 2:1) | High | Conferma pratica in Resolve: il codice è stato riscritto (0.9–0.12) ma non testato sul progetto reale che ha originato la issue |
| [#7](https://github.com/Mecena-SRL/LeaderKit/issues/7) | Scheda tecnica e film leader | Medium | Pallino finale fatto (0.11); restano solo 4 stili di slate su un'idea di "fino a 7" — da decidere se servono altri 3 |
| [#8](https://github.com/Mecena-SRL/LeaderKit/issues/8) | Standard per il film leader | Low | Standard e adattamento al formato fatti; resta solo un eventuale watermark grafico discreto separato dal logo |

## Priorità tecniche per la settimana prossima

1. **Verifica hands-on in Resolve di #6** — logo nei Loader, fluidità dello
   stile Pannelli su UHD, contorno nero dei testi. È l'unico item che blocca
   davvero un utente reale; tutto il resto è rifinitura.
2. **Decidere lo scope di #7** (altri stili di slate sì/no) prima di
   sviluppare — evitare di costruire 3 preset in più se i 4 attuali bastano.
3. **Copertura test per il ramo Lua** in locale: il repo passa da CI per i
   912+ test che usano `lua5.4`, ma non è verificabile senza l'interprete;
   vale la pena documentare in `README`/`CONTRIBUTING` come installarlo
   rapidamente per chi sviluppa senza CI a portata di mano.
