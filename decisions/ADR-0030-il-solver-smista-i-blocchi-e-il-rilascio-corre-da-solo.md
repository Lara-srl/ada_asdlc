# ADR-0030: il Solver smista i blocchi, e il rilascio del runner corre da solo fino al merge

**Stato:** **Proposta** · **Data:** 2026-10-15 · **Ratifica:** Francesco, con il merge
(`ADR-0012`, `ADR-0029`). Non cambia la costituzione: nessuna riga di `AGENTS.md` si
aggiunge o si abroga.

## Contesto

Il 15/10 il giro del PBI-002 di `ada_planning` si è fermato su un limite del runner: il
lucchetto di fase non leggeva i test JUnit (difetto 3, causa `runner-non-legge-junit`). Ciò
che ha sbloccato il giro è stato interamente manuale:

1. la sessione Claude di `ada_planning` ha registrato il difetto e ha chiesto a Francesco se
   correggere il runner o lavorare a mano;
2. su sua scelta, la stessa sessione ha scritto il `PBI-505` in questo repository, lo ha
   messo in coda e gli ha dato il comando;
3. il runner ha eseguito il PBI e ha aperto la #24; Francesco l'ha mergiata;
4. restano, a mano, cinque passi: portare il checkout su `main`, registrare il giro con
   `--registra`, mettere il tag, aprire la PR del nuovo pin in `ada_planning` (con `[junit]`),
   rilanciare il PBI-002.

Con N progetti che usano il runner, questa catena si ripete a ogni limite. Ogni anello è un
fatto verificabile (una PR `MERGED`, un tag, un pin) tranne due: capire che il blocco è del
runner e non del progetto, e scrivere il PBI a monte. Il resto è un tick che non c'è.

L'esperimento MOLT Sinai di Cockroach Labs ha la stessa forma: un builder, un critic distinto,
un ciclo che torna indietro, l'umano solo sul merge. Dà tre lezioni che qui contano. I cicli
non convergono da soli (11 giri su una riga) e vogliono un tetto. Le decisioni umane che fanno
precedente vanno scritte e consultate prima di escalare. Un agente che controlla il processo
costa molto e sbaglia in modo burocratico (un refuso che blocca una PR senza difetti); i
controlli di processo verificabili stanno meglio nel codice.

## Decisione

1. **Un terzo ruolo, il Solver.** Accanto al Builder e al Critic, riceve un giro fermato o una
   domanda bloccante del Critic e la smista con un esito strutturato, in tre sole forme:
   `risolto`, `limite-del-runner`, `intento`. L'esito passa per una chiamata a strumento con
   campi validati dallo strumento (`ADR-0027`); un Solver che non ne chiama nessuno chiude il
   giro `senza esito`.
2. **Il Solver scrive a monte solo per le cause `runner-*`.** È un sottoinsieme chiuso del
   vocabolario delle cause di ogni progetto; si allarga con un ADR, dopo qualche caso reale.
   Il PBI a monte arriva come **PR** nel repository `asdlc`, con il PBI e la sua riga in
   `backlog/CODA.md`: il Solver non scrive mai su `main`. Il merge di Francesco è il cancello
   che `CODA.md` chiede («mettere un PBI in coda è dichiarare che le sue domande sono
   chiuse»); la regola non cambia, cambia chi apre la PR.
3. **Il rilascio è un tick, non una checklist.** Dopo il merge del PBI a monte il tick di
   `asdlc` porta `main` allineato, registra il giro, e mette il tag **solo se il PBI dichiara
   `rilascia: patch|minor`** e la CI di `main` è verde. Il progetto che aspetta lo dice nel
   PBI fermo (`attende:`); il suo tick, quando il tag c'è, apre la PR del nuovo pin e, a
   merge verificato con `gh pr view`, toglie la pausa. I merge restano sempre di Francesco.
4. ~~**Niente quarto agente.**~~ (ristretta da `ADR-0031`, 20/10: il Lettore della
   pre-verifica è un quarto agente; la decisione resta per ciò che dice del Solver.) La conformità del Solver alle direttive si controlla con una
   guardia di codice (le righe «cosa conta come prova» della spec). Il giudizio sulla diagnosi
   resta al Critic, che rilegge anche l'output del Solver.
5. **Il tick è sempre attivo per quanto può esserlo un cron su un PC.** Un timer che recupera
   i giri persi, e un file di battito che il tick scrive a ogni giro; se tace oltre una
   soglia, un avviso. Il limite («il PC spento ferma la coda») è dichiarato nella spec.
6. **Un tetto ai giri.** Il ciclo ha un massimo di giri Solver↔Builder; oltre, o a ogni
   esito `intento`, si ferma con un avviso a Francesco (`ADR-0008`: avviso, non blocco). Le
   decisioni di Francesco che fanno precedente si scrivono in un registro che il Solver
   consulta prima di chiedere.

7. **Le cinque domande aperte, chiuse da Francesco il 16/10:** tetto di 3 giri; soglia del
   battito di 30 minuti; registro dei precedenti in `backlog/PRECEDENTI.md`; la PR a monte
   si apre da un fork di `asdlc`, senza permessi di scrittura sul repository; l'elenco delle
   cause `runner-*` sta in `backlog/README.md` di `asdlc`.

Le quattro domande (`decisions/README.md`) stanno nella spec, regola per regola
(`specs/solver-e-rilascio/spec.md`).

## Conseguenze

- **Positive:** il giro fermato per un limite del runner non aspetta più una sessione che
  ricordi i cinque passi; ogni limite diventa un PBI motivato, riprodotto e tracciato.
- **Negative:** il Solver è una nuova via di fuga («è colpa del runner») per un blocco
  difficile; la difesa è nella prova obbligatoria e nell'ordine degli esiti (`risolto` prima).
  Il tag automatico, una volta messo, vale per tutti i progetti che si agganciano.
- **Neutre:** `ADR-0012`, `ADR-0026` e `ADR-0027` non cambiano. Il costo del Solver si paga
  solo quando c'è un blocco.

## Alternative considerate

- **Tutto manuale, con una checklist.** Scartata: è lo stato di oggi, e i cinque passi dipendono
  dalla memoria di chi li fa.
- **Un quarto agente che controlla il processo** (il Discharge Nurse di MOLT Sinai). Scartata:
  i controlli di processo sono fatti verificabili, e l'agente costa contesto a ogni giro
  (circa 29.000 token) e introduce errori burocratici. Si riesamina se il Critic non regge il
  carico, con i costi misurati.
- **Push da `asdlc` verso i progetti** (il runner conosce i consumatori e apre le PR). Scartata:
  serve un registro dei progetti e un permesso di scrittura ovunque; col modello pull ogni
  progetto sa da sé cosa aspetta.
- **Una GitHub Action sul merge.** Scartata: reazione immediata ma permessi su più repository
  e un secondo posto in cui vive il rilascio, oltre al tick.
- **Il Solver scrive a monte per ogni causa.** Scartata per ora: troppo spazio per attribuire
  al runner un errore del progetto; si parte dalle `runner-*`.
