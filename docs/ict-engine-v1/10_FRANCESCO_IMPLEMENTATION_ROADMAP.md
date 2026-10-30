# Roadmap e promozioni
|Stage|Obiettivo e requisito|Campione / durata minima proposta|Promozione|Rollback|
|---|---|---|---|---|
|1 Research|contratto, ipotesi e default congelati|1 sprint di specifica e QA; durata non prova edge|tutti i test causali e metadata passano|ambiguità regole→revisione v1.x|
|2 Historical validation|data as-of, cost replay|36 mesi target; train/validation 24 mesi|nessun bug causale, strategia congelata|missing quotes→solo discovery|
|3 OOS|holdout 12 mesi mai visto|≥200 trade, ≥60 active days|gate PAPER del protocollo|CI≤0→RESEARCH/REJECT senza rituning test|
|4 Forward paper|feed live, zero ordini reali|≥60 giorni e ≥100 simulated fills|parità segnali/replay, rischio e telemetry conformi|drift/gap/ghost fill→sospensione|
|5 Shadow|segnali registrati senza invio, confronto con quote eseguibili|≥20 giorni, sovrapposizione finale paper consentita e dichiarata|latenza e prezzi riscontrati; approvazione eligibility|non fillable intents→rivedere fill model|
|6 Limited live|rischio 0,25%, mai oltre 1%; approvazione umana firmata e capitale minimo sostenibile|≥60 giorni e ≥50 fill prima di considerare scale|esecuzione coerente, DD≤limite, nessun incident grave|qualsiasi duplicato/orphan/protezione assente→halt; costi fuori CI→paper|
|7 Controlled scaling|capitale +25% per step, stesso risk rate o inferiore|≥30 giorni e 30 trade dopo ogni step|capacity/slippage stabili e revisione umana|perdita liquidità/cost drift→ultimo sizing validato|

Durate minime non sostituiscono significatività o condizioni di mercato comparabili. Live non inizia automaticamente a scadenza. Aumentare capitale non risolve strategia senza edge. Promozione richiede artifact di approvazione contenente versioni/hash/dataset/limiti/persona/data; runner production verifica separatamente l'autorizzazione e non eredita permessi dalla reference.

## Ordine operativo per Francesco
1. Eseguire unit test e demo synthetic; leggere coverage manifest.
2. Mappare DTO del contratto alla pipeline attuale senza cambiare backtester esistente.
3. Implementare decoder metadata e gate account eligibility; congelare una venue e un solo simbolo.
4. Acquisire dati, QA e calendario as-of; salvare config e data hashes.
5. Portare A1 e dimostrare parità su fixture + prefix invariance.
6. Sviluppare execution replay realistico e ledger; solo dopo eseguire protocollo scientifico.
7. Se supera criteri, paper/shadow; live resta escluso fino approvazione esplicita.
