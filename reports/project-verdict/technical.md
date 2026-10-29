# Affidabilità essenziale del bot — valutazione indipendente A

**Verdetto tecnico: utilizzabile per esperimenti locali circoscritti; NON pronto al paper trading continuo della strategia BTC 4h.** La distanza non è una latenza teorica da perfezionare: manca la dimostrazione di una catena operativa 4h realmente eseguita. Non esprimo un verdetto economico e non ho letto i risultati dell'agente B.

## Che cosa funziona davvero

- Il feed pubblico Binance ha fornito prezzi reali. Il journal contiene **un solo BUY e un solo SELL simulati localmente**, più un recupero con posizione aperta. Quotazioni, commissioni e saldo si riconciliano esattamente; non esiste alcuna conferma d'ordine da Binance. L'uscita effettivamente registrata è **temporale**, non un test di stop eseguito presso un broker.
- Il runtime riusa Risk Engine, stato delle posizioni e journal SQLite transazionale. I test esistenti su stop, kill, quotazioni obsolete e rollback sono **fixture**, non prove di tutte queste anomalie durante una posizione economica 4h reale.
- Nel controllo post-riavvio di **300,098 secondi**: **0 superamenti dei 250 ms**, massimo ricezione→elaborazione **5,345 ms**, event loop **29,864 ms**. È un miglioramento locale verificato per quella finestra, non una certificazione di continuità. La causa unica delle pause precedenti non è stata dimostrata.
- Il vecchio overflow della coda WebSocket è distinto dall'overflow del worker I/O non critico, che aveva fermato l'observer completo. Non li considero lo stesso difetto risolto.

## La strategia 4h non è attualmente una strategia operativa attiva

`SpotConfig` dichiara `btcusdt_technical_once`, con un roundtrip massimo e scadenza di 60 secondi. Il ciclo operativo chiama `submit_technical`, non la strategia breakout 4h.

La strategia congelata esiste nel simulatore offline. Il suo collector forward osserva soltanto le condizioni del segnale: **non costruisce Runtime, conto, Risk admission, portafoglio o ordini**; ogni uscita è `actionable=false` con blocchi di stabilità/news. Non è quindi corretto presentare il collector come un bot 4h già collegato all'esecuzione.

La cronologia corrente contiene **75 risposte di candele 4h**, cinque avvii di contesto e 70 fetch successivi; tutte le sottosequenze di 256 barre chiuse sono accettate dal validatore originale, senza revisioni OHLCV osservate. Ma contiene **zero osservazioni di segnale 4h** e 199 eventi di blocco. Prima di emettere la condizione, il collector richiede lo status della dashboard locale: se l'observer è spento, solleva un errore e non registra il segnale.

## Quali anomalie incidono materialmente

| Aspetto | Evidenza | Incidenza concreta |
|---|---|---|
| Pause locali sub-secondo | Test post-riavvio senza violazioni 250 ms | Non giustificano altro hardening indefinito; non dimostrano però ripetibilità continua. |
| Freschezza a 2 secondi | 13 campioni book e 67 trade non freschi dopo inizializzazione; 13 iniziali sconosciuti | Se il gate è rispettato, l'ingresso viene rifiutato. Non è provato quale trade 4h avrebbe perso: non esistono decisioni prospettiche ammesse. |
| REST disponibile prima di WS | 40 trade con ID/prezzo/quantità/T identici, massimo 1,437 s tra disponibilità osservate monotone | Prova una differenza di disponibilità in quel campione, non attribuisce la latenza a Binance, rete o client. Non basta a dichiarare inutilizzabile ogni strategia 4h. |
| Candela chiusa e disponibile | Per la barra finita il 27/10 alle **20:00 UTC**, prima risposta completa registrata alle **20:15:22,497649 UTC** | L'ingresso all'apertura delle 20:00 ipotizzato dal backtest non è riproducibile con quei dati disponibili solo dopo. Sono ritardo osservato del nostro percorso, polling/errori inclusi, **non** tempo di pubblicazione provato dell'exchange. |
| Lettura del corpo HTTP 4h | `response.content.read(1000001)` singolo, poi `json.loads` | Difetto concreto del contratto di lettura: una risposta JSON valida in due chunk può essere letta incompleta. Correggibile puntualmente, ma il file è tra i protetti e non è stato modificato. |
| Stop e interruzioni | Stop esclusivamente virtuale nello stesso processo; per chiudere serve una quota fresca | Il blocco delle nuove aperture non assicura la chiusura di una posizione esistente. Senza processo/feed, l'uscita rimane pendente; nessuna protezione server-side è stata provata. L'orizzonte 4h non elimina questo rischio. |
| Riavvio e gap | Ultimo ID persistito precedente alla nuova sessione; blocco su gap >1000 | Correttamente non si inventano eventi. Il gap iniziale non prova perdite nella finestra registrata, ma impedisce la certificazione operativa finché non è riconciliato. |

Le fasi native del backtest leggono la barra 4h completata e usano l'apertura oraria successiva, allo stesso confine temporale. Questo non è, da solo, un errore di ordinamento del codice; è un'**ipotesi di disponibilità/esecuzione** ancora da collegare a `available_at` e a una quotazione effettivamente negoziabile. Non converto questa discrepanza in una perdita economica inventata.

## Verifica mirata eseguita, senza nuova rete

Con `aiohttp` installato 3.14.5, uno StreamReader reale alimentato con un JSON valido di 34 byte in due chunk restituisce **10 byte** al primo `read(1000001)`; il parsing fallisce. Assemblando tutti i chunk il JSON è valido. La prima lettura impiega circa 0,074 ms e il corpo completo arriva circa 11,128 ms dopo l'inizio nella fixture. I primi due tentativi di preparazione della fixture avevano un protocollo fittizio incompleto, documentato nel JSON; nessun codice di progetto o libreria è stato cambiato.

Nei log reali alle 20:00 il controllo `/time` è completo, poi arriva `JSONDecodeError` **prima** che sia registrata una risposta 4h. È coerente con il difetto riprodotto, ma i byte della risposta fallita non sono stati conservati: **non attribuisco ogni errore storico alla stessa causa**. I successivi errori di connessione allo status locale sono invece spiegati direttamente dall'ordine del codice.

Non ho aperto due nuovi client WebSocket: quel confronto non potrebbe dimostrare la catena mancante tra segnale 4h e portafoglio. Un altro soak non cambierebbe il verdetto tecnico attuale.

## Distanza essenziale, non una lista infinita di sviluppo

Se il valore economico giustificasse proseguire, basta fissare **una milestone operativa verificabile**: candela 4h chiusa → corpo completo e istante di disponibilità → quota fresca → decisione/veto del Risk Engine → fill paper locale e gestione di protezione/riavvio. Il collector non deve dipendere dalla dashboard per registrare una condizione, e il prezzo di fill non può precedere la disponibilità reale. Le soglie restano 250 ms e 2 s; il calendario rigoroso resta bloccante. Non servono nuove architetture, provider o modelli.

Prima di denaro reale, il simulatore locale non basterebbe: servirebbero una strategia validata indipendentemente e prove separate di esecuzione, protezioni e riconciliazione nell'ambiente effettivamente scelto. Le vecchie prove IBKR/Capital.com non certificano Binance e questo adapter pubblico non può inviare ordini per costruzione. Non è un'attivazione da effettuare adesso.

## Stato e riferimenti

Verifica corrente in sola lettura: journal `quick_check=ok`, flat/spent, un BUY/un SELL, saldo virtuale 999,76609237980375 USDT; porta 8767 senza listener. Nessun servizio è stato avviato in questa analisi. **179 file protetti invariati**, nessuna chiamata Databento, privata, Docker o di rete; nessuna nuova posizione.

Le prove, con percorsi assoluti, righe, hash e distinzione dati reali/fixture/sorgente, sono in [technical.json](/Users/locoframe/Desktop/TRADING%20BOT/reports/project-verdict/technical.json). Riferimenti principali:

- `src/mnq_local/binance_spot.py`:34–56,164–224,238–284 — modalità tecnica, ammissione, stop e gate.
- `src/mnq_local/binance_app.py`:245–275 — ciclo operativo tecnico.
- `reports/binance-spot/forward-signals/recorder.py`:1–34,55–77 — osservazione soltanto, lettura HTTP e dipendenza dallo status.
- `reports/binance-spot/breakout-4h/runner.py`:108–132 — cronologia delle entrate simulate.
- `data/binance-spot/forward-signals/events.jsonl`:708–709 — prima risposta completa della barra 20:00 e successivo blocco status.

Forza dell'evidenza **alta** per assenza della catena operativa 4h/protezioni remote e per gli stati verificati; **limitata** per la causa ultima delle pause e per l'impatto monetario degli ingressi rifiutati. Nessuna conclusione sulla redditività viene dedotta dalla qualità del software.
