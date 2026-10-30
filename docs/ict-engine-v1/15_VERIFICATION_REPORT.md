# Verifiche eseguite — 30 ottobre 2026

## Esito
- **33 unit/integration test superati**, inclusa pipeline sintetica end-to-end LONG e SHORT speculare: sweep → MSS/displacement → FVG → sizing → simulazione entry e target.
- Verificati ritardo pivot, pareggi, no same-bar fill, no TP sulla barra entry, stop-first, gap oltre stop, expiry, cancel, idempotenza/conflicting ID, dati NaN, news as-of, DST, budget €500/€5000 e short spot vietato.
- Prefix invariance verificata su stream sintetico: estendere il futuro non modifica decisioni già emesse.
- Demo sintetica eseguita e output registrato. Il suo PnL è una conseguenza dei prezzi costruiti, non un risultato di mercato.
- Tutti i file Python compilano; YAML JSON-subset leggibile con standard library, due copie config identiche, 115 righe complete nel dizionario CSV.
- Contratto JSON e fixture parsati; struttura ispezionata e include 8 payload con required/additionalProperties false, decimal strings, envelope version e discriminante event_type.

## Limiti delle verifiche
Il validatore esterno JSON Schema draft 2020-12 non è disponibile in questo ambiente; **non è stata eseguita la validazione con un motore standard**. M0 deve eseguire metaschema validation e fixture positive/negative con il validatore già disponibile nell'infrastruttura. Il parsing JSON riuscito non equivale a conformità semantica dei payload. La reference usa oggetti Python interni, non questo wire schema.

Nessun dataset di mercato fornito/acquisito: nessuna statistica di rendimento, robustezza OOS, validazione delle fee correnti o stima slippage reale è stata calcolata. I test non coprono partial fill, crash recovery, auto news/session exit, broker order capabilities, ledger MTM o risk reservation atomica perché tali componenti sono specificati ma non implementati nella reference.

Report dettagliato dei test: `reference/test_results.txt`. Output demo: `reference/demo_output.json`. Gli invarianti non ancora eseguiti sono elencati in M0–M7 del handoff. Stato corretto: **RESEARCH**, non PAPER TRADE approvato e non LIVE ELIGIBLE.
