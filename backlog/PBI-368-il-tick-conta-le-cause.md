# PBI-368: il tick conta le cause dei difetti e segnala la terza

> **Spostato al repository `asdlc` il 25/09/2026** (Francesco). Il contatore vive nel tick,
> e il tick entra nel pacchetto (`ADR-0026`): scritto qui dovrebbe traslocare subito dopo.
> Intanto la regola è in `backlog/README.md`, e il conto si fa a mano. Il testo resta com'è,
> e si riscrive nel repository `asdlc` con i percorsi del pacchetto. **Non è in coda.**

## Direttiva

La regola sta in `backlog/README.md` §I difetti e le loro cause, scritta a mano il 24/09 e
fuori dalla coda: ogni difetto porta una riga `**Causa:** <slug>` presa da un vocabolario
chiuso, e **alla terza occorrenza della stessa causa si apre un PBI di approccio** invece di
un'altra correzione locale.

Una regola che si ricorda a memoria non regge: i difetti 32, 34 e 35 facevano già tre
occorrenze della stessa causa il 23/09, e il PBI di approccio (`PBI-366`, `PBI-367`,
`ADR-0027`) è arrivato un giorno dopo, per una proposta a voce. Questo PBI fa sì che il tick
la conti e la segnali da solo.

**Scope**

- `tools/asdlc_coda.py` — il conteggio e la riga nel log.
- `tools/tests/test_asdlc_coda.py` — i test nuovi.
- `backlog/PBI-368-il-tick-conta-le-cause.md` — i criteri della *Verifica* si
  spuntano nei commit che li chiudono.

**Fuori scope**

- **La classificazione**: le cause dei difetti 1-35 le assegnano a mano Francesco e Claude
  (è un giudizio), prima di questo PBI. In coda c'è una barriera apposta.
- **Aprire il PBI di approccio**: il tick segnala, non scrive nel backlog.

## ✅ Deciso, per non fermare il giro

1. **Il tick segnala e non blocca** (`ADR-0008`). La riga va in `runs/coda.log` insieme alla
   decisione del tick, e la decisione non cambia.
2. **Si leggono le righe `**Causa:** <slug>`** in tutti i file di `backlog/`. Lo slug si
   confronta con la tabella del vocabolario in `backlog/README.md`.
3. **Si segnala una causa con tre occorrenze o più e la colonna «PBI di approccio» vuota.**
   Una causa che un PBI di approccio lo ha già avuto non si segnala più: la cura c'è, e il
   segnale ripetuto a ogni tick diventerebbe rumore.
4. **Uno slug fuori vocabolario si segnala anche lui**, con il file e la riga. Il vocabolario
   è chiuso: aggiungere uno slug è un commit su `README.md`, e uno slug scritto solo nel
   difetto è un refuso o una causa nuova non dichiarata.
5. **Il segnale si ripete a ogni tick finché la condizione dura.** Il tick non ha memoria fra
   un giro e l'altro, e non deve averne.

## Dipendenze

- **La barriera in coda**: la classificazione all'indietro dei difetti 1-35 fatta a mano.
  Senza, il contatore conta quasi niente e il suo primo segnale sarebbe falso.
- Nessun PBI in ingresso.

## Contesto

- `backlog/README.md` §I difetti e le loro cause — la regola e il vocabolario.
- `backlog/PBI-102-soglia-di-revisione-del-runner.md` — l'elenco dei difetti.
- `tools/asdlc_coda.py` — `prossimo()`, e come il tick scrive nel log.

## Verifica

Su `main` il tick non legge le cause, quindi ogni criterio è un **rosso atteso**. Si rilegge
caso per caso su `main` quando la barriera cade.

- [ ] **Una causa arrivata a tre occorrenze senza PBI di approccio si segnala** nel log del
      tick, con lo slug e i difetti che la portano (pytest).
- [ ] **Una causa con il PBI di approccio non si segnala**, anche con tre occorrenze o più
      (pytest).
- [ ] **Uno slug fuori vocabolario si segnala** con file e riga (pytest).
- [ ] **La decisione del tick non cambia**: lo stesso mondo, con o senza il segnale, dà la
      stessa decisione — guardia dichiarata, verde su `main` (pytest).

## Protocollo di rifinitura

Se il formato della riga `**Causa:**` scelto nella classificazione si rivela ambiguo da
leggere — più cause per difetto, uno slug dentro una frase — non si allarga la regola di
lettura: ci si ferma e si corregge il formato in `README.md`, perché il vocabolario lo
scrivono le persone e il tick lo legge.
