# Economic Event Risk Filtering

## Normalizzazione
Port `calendar.events(asof, horizon)` restituisce solo record con known_at≤asof; ogni versione ha source, source_event_id, snapshot_id, scheduled_at UTC, original_timezone IANA, importance, affected currencies, status, known_at e ingested_at. Distinguere ora meeting e ora annuncio. Mai trasformare una data senza ora in mezzanotte certa: time_unknown→bloccare la sessione coinvolta finché risolta. Evento rinviato: conservare vecchia versione e valid_to, non sovrascrivere lo storico. Se la cancellazione è nota oggi non cancellare blackout di ieri nel replay.

Refresh ogni 15 minuti operativo, snapshot massimo 24h; all'inizio sessione conferma con fonte ufficiale per eventi high-impact del giorno. Errori calendar o coverage incompleta per le valute richieste→SKIP_CALENDAR_STALE/UNKNOWN. Calendario vuoto fresco è valido solo con attestazione coverage; la reference assume questa attestazione fornita dal chiamante. Quote e calendario non possono avere timestamp futuro.

## Routing eventi
|Categoria|Valute/mercati impattati|Priorità progettuale|Fonte primaria da acquisire|
|---|---|---|---|
|FOMC/Fed rate + press conference|USD, crypto, indici USA|3|Federal Reserve calendar; annuncio e conferenza eventi separati|
|CPI/Core CPI|USD, crypto, indici USA|3|BLS; eventi co-temporali uniti per blackout|
|NFP/Unemployment|USD, crypto, indici USA|3|BLS Employment Situation|
|PCE/Core PCE|USD, crypto, indici USA|3|BEA Personal Income and Outlays|
|GDP|USD, crypto, indici USA|3|BEA, distinguere advance/second/third ma nessuna revisione retroattiva|
|ISM Manufacturing/Services|USD, crypto, indici USA|3 prudenziale|ISM release schedule, integrazione non verificata in questo pacchetto|
|ECB rate + press conference|EUR e coppie EUR|3|ECB official calendar; adapter da verificare|
|BOE rate|GBP e coppie GBP|3|Bank of England calendar; adapter da verificare|
|BOJ rate/statement|JPY e coppie JPY|3|Bank of Japan calendar; se timing incerto bloccare intervallo pubblicato|
|Venue maintenance/halt/delisting|solo venue/simboli interessati|hard block|status feed e announcements ufficiali, availability da verificare|
|Crypto expiry/unlock|specifico strumento, non tutti i token automaticamente|sperimentale|solo evento con calendario verificabile e ipotesi documentata|

Per FX applicare unione eventi base/quote. BTC ed ETH includono macro USD anche quando quote EUR/IDR. Unione di blackout sovrapposti, non due decisioni contrastanti. Default [event−30m,event+30m], inclusivo; sensitività preregistrata 15/30/60 per lato, non scegliere per miglior risultato sul test.

## Ordini e posizioni
All'inizio blackout: cancellare pending e avviare exit delle posizioni aperte; stop nativo resta attivo fino exit confermata. L'exit può slittare ed è contabilizzata al prezzo effettivo. La policy close-all è conservativa proposta, da confrontare in ricerca con hold-with-stop a parità di rischio, ma non alternarle discrezionalmente trade per trade. Eventi multipli allungano l'unione. Riapertura solo dopo fine blackout, 3 quote consecutive valide, spread e volatilità sotto limiti e posizioni/ordini riconciliati. Nessun vecchio setup ripescato.

Shock non programmati: non possono essere esclusi preventivamente con calendario. Spread burst, price gap, halt e volume/depth anomalies attivano gate deterministici; notizie NLP possono solo aggiungere un blocco con TTL e audit, mai autorizzare un trade altrimenti vietato. Un LLM che interpreta una news non ha accesso all'execution port. TTL blocco NLP=60 minuti proposto, revisione esterna per estenderlo; nessun effetto sullo stop protettivo.

## Test di accettazione aggiuntivi
Eventi USA marzo con DST diverso da Europa; BOJ time_unknown; due eventi con blackout sovrapposto; calendario stale ma quote fresche; quote stale ma calendario fresco; revisioni note dopo il segnale; rinvio ricevuto durante blackout; fill mentre cancel news è in corsa; source outage; snapshot incompleto; halt senza timestamp di riapertura. Risultato atteso: blocco fail-closed per nuovi ingressi, registrazione di ogni ragione e nessuna eliminazione di esposizione dal ledger senza fill confermato.
