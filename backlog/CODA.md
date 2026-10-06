# La coda dei PBI

L'ordine in cui i PBI vanno lanciati, e i punti in cui la coda si ferma da sola.
La scrive **Francesco**, a mano. `asdlc-coda`, il tick, la esegue e non la modifica mai:
una voce è qui perché qualcuno ce l'ha messa, ed è quello il cancello (PBI-350).

**Come si legge una riga**

- `- PBI-337` — un PBI da lanciare. Il tick lo lancia quando il precedente è in `main`.
- `- ‖ testo` — una **barriera**: un gesto umano. Il tick ci arriva, lo scrive e si ferma.
  Si toglie la riga quando il gesto è fatto.

Tutto il resto è prosa e il tick non la guarda.

**Il tick non guarda più come si intitola una PR** (PBI-353): una voce si spegne quando una
PR mergiata nomina quel PBI — nel titolo `PBI-XXX: …` **oppure** nel ramo `pbi/pbi-XXX` — *e*
ha toccato qualcosa **fuori da `backlog/`**. Perché il titolo non distingue la PR che
*accoda* un PBI da quella che lo *fa*, e la prima arriva per prima: il 09/09 la #215 ha spento
la riga di PBI-352 nell'istante in cui la scriveva. Il prefisso nel titolo da solo non spegne
più niente — ma se la PR tocca anche un file fuori da `backlog/`, sì: una PR che nomina un PBI
nel titolo e scrive un ADR lo spegne lo stesso, ed è il limite dichiarato della regola.

**Mettere un PBI in coda è dichiarare che le sue domande sono chiuse**, ed è l'unico
cancello che ci sia: il tick non lo rifà, perché non può. Il carattere `❓` nel PBI non è la
prova né del contrario né a favore — in PBI-349 è una domanda aperta, in PBI-340 è un
protocollo di rifinitura già deciso, e i due si distinguono leggendoli. Il tick lo stampa
nel log come avviso e lancia lo stesso (`ADR-0008`).

Se una domanda si apre comunque a giro iniziato, il Builder chiama lo strumento `fermati`:
niente PR, niente merge, e la coda si ferma da sé senza che nessuno debba accorgersene. Lo
stesso fa un agente che non dichiara niente, e il giro chiude `senza esito` (`ADR-0027`).

## La coda

Vuota alla nascita del repository. I primi PBI sono quelli di `template/` (D5 del runbook
della Fase 5 di aDa), e si accodano dopo la `v0.1.0`.
