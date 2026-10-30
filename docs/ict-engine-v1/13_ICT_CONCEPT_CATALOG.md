# Glossario quantitativo e test dei concetti

Tutte le formalizzazioni numeriche sono proposte P. I concetti opzionali non entrano nel motore A1 automaticamente. Ogni riga definisce input, calcolo, esempio, ambiguità, invalidazione e test; dipendenze generali OHLC chiusi, ATR lagged, tick e timestamp as-of.

## Swing high/low
- Origine/stato: P per conferma, O concetto.
- Definizione operativa e formula: H_i>max(H vicini L/R); low simmetrico; noto i+R.
- Esempio sintetico: [10,12,15,12,10], L=R=2 → high15 noto index4.
- Ambiguità/falsi segnali: pari massimi esclusi; non repaint; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: break oltre livello consuma pool.
- Test verificabile: pivot delay sensitivity 1/2/3; prefix invariance; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Internal/external structure
- Origine/stato: C/P.
- Definizione operativa e formula: internal pivot M5 2+2; external H1 2+2; internal se low_range<p<high_range.
- Esempio sintetico: H1 [90,110], M5 high105 interno.
- Ambiguità/falsi segnali: TF e range congelati, non reinterpretare ex post; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: close fuori dealing range.
- Test verificabile: ablation H1 alignment e confronto M5 only; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## BOS/CHoCH/MSS
- Origine/stato: C/P; MSS O.
- Definizione operativa e formula: BOS close rompe pivot nella direzione trend; CHoCH prima rottura contraria; MSS=rottura post sweep + displacement.
- Esempio sintetico: trend down, high100; close101 con impulso → MSS long.
- Ambiguità/falsi segnali: CHoCH non sinonimo necessario MSS; trend0 non BOS; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: estremo sweep rotto o TTL.
- Test verificabile: confronto close vs wick e displacement off; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Displacement
- Origine/stato: O/P.
- Definizione operativa e formula: body_d/A>=1; body_d/range>=.65; dist_close_extremo/range<=.2.
- Esempio sintetico: O100 H102.1 L99.9 C102 valido A1.
- Ambiguità/falsi segnali: doji e range0 rifiutati; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: se non coincide MSS A1 non valido.
- Test verificabile: impulso vs random matched vol; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Trend continuation/reversal
- Origine/stato: P/H.
- Definizione operativa e formula: continuation d=trend_H1; reversal sweep opposto con MSS indipendente da H1.
- Esempio sintetico: H1 up, long pullback continuation; SSL sweep reversal possibile in trend0.
- Ambiguità/falsi segnali: non usare regime futuro per chiamare reversal; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: violazione origine pullback o sweep.
- Test verificabile: B1 vs A1 stessi costi; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## HTF/Daily bias
- Origine/stato: O/P.
- Definizione operativa e formula: H1 ultimi due high/low entrambi crescenti →+1; daily=sign(CprevD-OprevD).
- Esempio sintetico: H1 highs100,102 lows95,97 → up.
- Ambiguità/falsi segnali: daily proxy semplice non ICT completo; doji neutro; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: bias nuovo vale solo futuro.
- Test verificabile: ablation filter on/off su holdout; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## BSL/SSL
- Origine/stato: O/P/H.
- Definizione operativa e formula: pool high = proxy BSL, low=proxy SSL, già confermato e intatto.
- Esempio sintetico: high105 presumibile riferimento, non stop osservato.
- Ambiguità/falsi segnali: nessuna inferenza intenzioni/order inventory; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: primo touch consuma A1.
- Test verificabile: event study returns post-touch matched controls; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Equal highs/lows
- Origine/stato: O/P.
- Definizione operativa e formula: >=2 pivot same-side distanti >=3 barre; max-min<=max(2tick,.05A); livello max highs/min lows.
- Esempio sintetico: 100 e100.02 con tick.01 → equal.
- Ambiguità/falsi segnali: cluster greedily temporal order; freeze prima sweep, nessun merging retroattivo; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: touch/rottura pool congelato.
- Test verificabile: near-equal vs single pivot; tolerance sensitivity; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## PDH/PDL/PWH/PWL
- Origine/stato: O/P.
- Definizione operativa e formula: max/min periodo interamente chiuso calendario prodotto.
- Esempio sintetico: ieri high110 low100 → livelli oggi.
- Ambiguità/falsi segnali: crypto UTC vs FX17NY non equivalenti; week holiday; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: touch dopo publish consuma.
- Test verificabile: test day/week levels vs random level distance; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Asian/London range
- Origine/stato: O/P.
- Definizione operativa e formula: max/min barre sessione completa; Asia20-00 NY, London02-05 NY proxy.
- Esempio sintetico: Asia highs100,102 → high102 noto00.
- Ambiguità/falsi segnali: mai usare high finale prima fine range; DST locale; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: touch o sessione successiva sostituisce.
- Test verificabile: shift placebo finestre e preregistro; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Sweep/grab/stop run
- Origine/stato: O/C/P/H.
- Definizione operativa e formula: p-L in [.05,.5]A e close>=p+tick; short simmetrico.
- Esempio sintetico: p100 low99.8 close100.1 A1.
- Ambiguità/falsi segnali: sweep e grab stessa regola qui; nessuna prova stop run reale; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: nuovo estremo o no MSS entro6.
- Test verificabile: matched breakout no recovery; return distribution; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Draw on liquidity
- Origine/stato: O/P/H.
- Definizione operativa e formula: pool opposto intatto più vicino davanti a entry.
- Esempio sintetico: entry100.6 highs103,105 → target102.99.
- Ambiguità/falsi segnali: non è previsione certa della destinazione; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: pool già consumato o netRR<1.5.
- Test verificabile: liquidity target vs fixed2R; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## FVG
- Origine/stato: O/P.
- Definizione operativa e formula: bull L3>H1, bear H3<L1; width .1..1ATR; middle=MSS.
- Esempio sintetico: H1=100,L3=100.5 → [100,100.5].
- Ambiguità/falsi segnali: wick overlap/no gap →null; tick equality no gap; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: close oltre bordo distante o TTL; A1 stop gestisce posizione.
- Test verificabile: FVG vs market-after-MSS, cost matched; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Inverse FVG
- Origine/stato: O/P sperimentale.
- Definizione operativa e formula: bull gap[a,b] diventa bear solo close<a; retest dal basso a midpoint entro6 barre.
- Esempio sintetico: [100,101], close99.9, retest100.5.
- Ambiguità/falsi segnali: nessuna conversione intrabar; due close separati; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: close>b o 6 barre.
- Test verificabile: compare retest inverted vs random resistance; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Balanced price range
- Origine/stato: O/P sperimentale.
- Definizione operativa e formula: intersezione positiva tra ultimo bull e bear FVG entro20 barre: [max(lo),min(hi)].
- Esempio sintetico: [100,102]∩[101,103]=[101,102].
- Ambiguità/falsi segnali: se width<=0 nessun BPR; quale gap: più recente; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: close fuori range o20 barre.
- Test verificabile: incremental value over FVG age/width; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Order block
- Origine/stato: O/P proxy.
- Definizione operativa e formula: ultima candela contro d nelle5 barre precedenti displacement che rompe pivot; zona intera [L,H].
- Esempio sintetico: bear candle O101 C100 L99.8 H101.2 prima impulso long.
- Ambiguità/falsi segnali: zone body-only altra variante; niente istituzioni inferite; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: close oltre distal edge o20 barre.
- Test verificabile: OB vs FVG e placebo candela precedente; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Breaker block
- Origine/stato: O/P proxy.
- Definizione operativa e formula: OB invalidato da close distal e MSS opposto; stessa zona retest nella nuova direzione entro6.
- Esempio sintetico: bull OB[100,101], close99.8+MSSshort → retest100.5.
- Ambiguità/falsi segnali: serve MSS noto, non etichettare prima; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: close oltre lato opposto oTTL.
- Test verificabile: failed OB retest vs generic breakout retest; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Mitigation block
- Origine/stato: O/P proxy.
- Definizione operativa e formula: ultima candela contro d prima MSS senza sweep qualificante, zona[L,H], retest entro6.
- Esempio sintetico: bear candle[100,101] prima breakout102 senza raid.
- Ambiguità/falsi segnali: definizioni variabili community; escluso baseline; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: close distal/TTL.
- Test verificabile: confronto con OB e no-sweep baseline; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Consequent encroachment
- Origine/stato: O/P.
- Definizione operativa e formula: midpoint(a,b)=(a+b)/2.
- Esempio sintetico: [100,101] →100.5.
- Ambiguità/falsi segnali: midpoint quantizzato conservativamente; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: zona invalida.
- Test verificabile: entry 0/.5/1, fill rate e PnL; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Premium/discount arrays
- Origine/stato: O/P.
- Definizione operativa e formula: z=(C-low)/(high-low), premium>.5 discount<.5; array=zone registrate as-of.
- Esempio sintetico: range90..110, prezzo98 → z.4 discount.
- Ambiguità/falsi segnali: range zero null; z fuori[0,1] range invalidato; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: close fuori range congelato.
- Test verificabile: PD filter off/on, range sensitivity; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## OTE
- Origine/stato: O/P sperimentale.
- Definizione operativa e formula: long impulse low a→high b: retracement r=(b-P)/(b-a) in[.62,.79]; entry r=.705.
- Esempio sintetico: a100,b110 → entry102.95.
- Ambiguità/falsi segnali: finestra impulsi congelata a MSS; numeri convenzione da verificare vs corpus; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: P<a o6 barre.
- Test verificabile: compare .5 vs .705 vs random retracement; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Killzones/London close
- Origine/stato: O/P.
- Definizione operativa e formula: finestra timezone-aware [start,end); London02-05, NY07-10, LC10-12 NY proxy.
- Esempio sintetico: 08NY ammessa NY, 10NY esclusa NY e inclusa LC.
- Ambiguità/falsi segnali: finestre community diverse, non orario London civil; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: session end cancella entry.
- Test verificabile: shift time placebo + multiple testing; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Midnight/New York midnight/session open
- Origine/stato: O/P.
- Definizione operativa e formula: open prima barra che inizia00NY, separato da00UTC; session_open prima barra prevista valida.
- Esempio sintetico: 00NY gennaio=05UTC; luglio=04UTC.
- Ambiguità/falsi segnali: barra end timestamp non scambiare con start; missing open→null; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: solo riferimento giorno corrente.
- Test verificabile: distance to open predictive ablation; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Opening range
- Origine/stato: P.
- Definizione operativa e formula: max/min primi30m dall apertura scelta; disponibile solo dopo30m.
- Esempio sintetico: NY07:00–07:30 high102 low100.
- Ambiguità/falsi segnali: non assimilare arbitrariamente a apertura cash index09:30; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: nuovo giorno reset.
- Test verificabile: range breakout vs sweep in medesimi slot; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## Day-of-week/DST
- Origine/stato: P.
- Definizione operativa e formula: weekday da timezone locale; UTC conversion IANA senza offset fisso.
- Esempio sintetico: NY08=13UTC inverno,12UTC estate.
- Ambiguità/falsi segnali: settimane DST USA/Europa discordanti; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: calendar version change richiede replay.
- Test verificabile: test marzo/ottobre/novembre e festivi; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.

## ICT 2022 / Silver Bullet
- Origine/stato: O/P/H.
- Definizione operativa e formula: A1 proxy2022; D1 FVG+structure solo10-11NY senza sweep obbligatorio.
- Esempio sintetico: signal10:30NY valido D1 se bias e gap.
- Ambiguità/falsi segnali: non si è verificato intero corpus; niente promessa setup quotidiano; trend persistenti, spread e salti possono imitare il pattern senza generare reversal.
- Invalidazione: regole A1/C1/D1 e cutoffs.
- Test verificabile: holdout separato e family adjustment; unit test su confini e falsificazione OOS dopo costi, non solo riconoscimento visivo.
