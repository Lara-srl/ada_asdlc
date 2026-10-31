# ADR-0034: si lavora a sprint, e ogni sprint finisce con una cosa da far vedere

**Stato:** **Proposta** · **Data:** 2026-10-31 · **Ratifica:** Francesco, con il merge
(`ADR-0012`, `ADR-0029`). **Cambia la costituzione:** aggiunge una riga a `## Metodo` di
`AGENTS.md` (e della sua copia in `template/AGENTS.md`, che deve restare identica). Non ne
abroga nessuna. Chi la propone è una sessione con Francesco, che non ne beneficia: la ratifica è
il suo merge.

## Contesto

Il runner va da solo: con la `v1.1.0` lancia, mergia e rilascia senza una persona davanti, e in
una notte chiude cinque PBI (`ada_asdlc` 533 → 534 → 537, 30-31/10). Quello che manca non è
velocità, è **il momento in cui qualcuno guarda il risultato**. La coda oggi è una fila sola: un
progetto può fare dieci PBI di fila e scoprire solo alla fine che il prodotto non andava.

`ada_dispense` ha già trovato la risposta a mano. Il 31/10 Francesco e Jona hanno deciso di
lavorare a sprint (`backlog/PIANO-SPECIFICHE.md` §8 di quel repository): un risultato da mostrare
scritto prima, pochi PBI, e una barriera di revisione in `CODA.md` alla fine. Il tick si ferma da
solo sulla barriera, e i PBI dello sprint dopo si scrivono dopo la revisione. La richiesta di
Francesco del 31/10 è farne la regola di ogni progetto: «organizzare sempre i PBI in sprint,
facendo sviluppo, verifica, modifica e ripresa, e non sviluppare mai troppo senza far vedere
artefatti al cliente».

## Decisione

1. **Ogni progetto lavora a sprint.** Uno sprint è un gruppo di PBI della coda con **un risultato
   da mostrare**, scritto prima di cominciare: una cosa che una persona guarda o usa (un PDF, un
   comando che gira, una pagina, una risposta dell'agente), non una descrizione del codice.
2. **Uno sprint ha da 1 a 5 PBI**, solo quelli che servono al suo risultato. Si misura in PBI e
   non in giorni (scelta di Francesco, 31/10): il runner ne può chiudere cinque in una notte, e un
   tetto di giorni non lo fermerebbe mai.
3. **In `CODA.md` uno sprint si scrive così** (le righe `- PBI` e `- ‖` sono quelle di sempre;
   l'intestazione è prosa per il tick fino a `PBI-539`):

   ```markdown
   ### Sprint N — <risultato da mostrare>

   - PBI-XXX
   - PBI-YYY
   - ‖ revisione dello sprint N con <chi>: <risultato da mostrare>
   ```

   La barriera di revisione è l'ultima voce dello sprint. È il meccanismo di sempre (`PBI-350`):
   il tick ci arriva, lo scrive e si ferma.
4. **La revisione la fanno Francesco e il referente del progetto** (scelta di Francesco, 31/10),
   nominato nella barriera: guardano il risultato, dicono cosa va, cosa cambia e quale sprint viene
   dopo. Si scrive nel repository, nella sezione dello sprint o nel piano del progetto, e poi si
   toglie la riga della barriera.
5. **Lo sprint dopo si scrive dopo la revisione.** Ciò che la revisione chiede di cambiare diventa
   i PBI dello sprint successivo — è la *ripresa* — e prima della revisione l'elenco degli sprint
   futuri è una proposta, non un impegno. Così il ciclo è sviluppo (i giri), verifica (gate, Critic,
   CI), revisione (le persone) e ripresa (lo sprint dopo).
6. **Il runner segnala, non blocca** (`ADR-0008`). `PBI-539` gli insegna a leggere gli sprint:
   avvisa **nel log**, sulla riga del lancio del primo PBI dello sprint, se lo sprint ha più di 5 PBI,
   se non dice il risultato o se non finisce con la sua barriera di revisione; quando arriva alla
   barriera manda la revisione **su Slack** col risultato e i PBI fatti. Una coda senza sprint
   funziona come oggi.
7. **Questo ADR non si copia nel `template/`.** Gli ADR di metodo del template sono numerati come
   qui (0008…0027) e un progetto conta i suoi dal 0028 (`template/decisions/README.md`): un ADR di
   metodo nuovo, numerato dopo, collide con quelli dei progetti (`ada_unical` ne ha dieci fra 0030 e
   0039). La riga di `## Metodo` lo cita come «`ADR-0034` del pacchetto `asdlc`», e la grammatica
   dello sprint la mostra il `template/backlog/CODA.md` (`PBI-539`). Si rivede se gli ADR di metodo
   avranno una numerazione loro.

Le quattro domande, per la regola del punto 6:

1. **cosa si controlla:** le intestazioni `### Sprint N — …` di `CODA.md`, le voci che seguono e
   la barriera `‖ revisione dello sprint N` che le chiude;
2. **quando:** quando il tick lancia il primo PBI di uno sprint (gli avvisi) e quando arriva alla
   sua barriera (la revisione);
3. **cosa conta come prova:** il conto delle righe `- PBI` fra un'intestazione e la barriera, il
   testo dopo `—`, la presenza della barriera prima dell'intestazione seguente;
4. **cosa succede se manca:** un `avviso, …` in coda alla riga del lancio nel log, e il lancio
   procede; nessun esito cambia.

## Conseguenze

- **Positive:** al massimo cinque PBI fra due momenti in cui una persona guarda; il cliente vede
  un artefatto a ogni sprint; i PBI si scrivono con quello che si è visto, non con quello che si
  immaginava un mese prima.
- **Negative:** il tick si ferma più spesso, e ogni fermo aspetta una revisione con due persone;
  scrivere il risultato da mostrare prima costa un pensiero in più per ogni sprint.
- **Neutre:** `CODA.md` resta l'unico cancello e la scrive Francesco; i progetti di oggi si
  convertono alla prossima scrittura della loro coda, senza fretta. La riga di `## Metodo` arriva
  negli `AGENTS.md` degli altri progetti con una PR ciascuno, dopo la ratifica.

## Alternative considerate

- **Sprint a tempo (una settimana):** scartata da Francesco il 31/10, vedi decisione 2.
- **La barriera messa dal tick alla fine dello sprint:** scartata. Il tick non scrive `CODA.md`
  (`PBI-350`): la barriera la scrive chi scrive lo sprint, e il tick avvisa se manca.
- **Lasciarlo per progetto, come in `ada_dispense`:** scartata. Funziona dove qualcuno se ne
  ricorda; la richiesta è che valga sempre, anche nei progetti futuri dal `template/`.
