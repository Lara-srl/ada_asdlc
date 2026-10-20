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

- PBI-500
- PBI-501
- PBI-502
- PBI-503
- PBI-504
- PBI-505
- PBI-506
- PBI-507
- PBI-508
- PBI-509
- PBI-512
- PBI-510
- PBI-511
- PBI-513
- PBI-518
- PBI-519
- PBI-517
- PBI-514
- PBI-515

**`PBI-506`–`PBI-510`, il Solver e il rilascio a catena** (`ADR-0030`, 16/10). Il 507 legge i file del 506,
il 508 i rapporti del 507 e il 509 gli strumenti del 507: per questo vanno in fila. Il 510
tocca `coda.py` come il 509 e viene dopo. **`PBI-512`** (la PR a monte del Solver, R5 e R6) esce dal 509 per decisione di Francesco del 16/10 e va subito dopo, perché legge `attende:` e il pin. **`PBI-509`** è stato accodato da Francesco il 16/10
con la sua proposta di formato (`rilascia:`, `attende:`) presa come decisione; il Critic può
chiedere di dividerlo. **`PBI-511`** (la traccia delle sessioni e il controllo R4) nasce dal giro 1
del 508 e va dopo il 510; legge la guardia del 508 e accende la sua riga R4. Accodato da
Francesco il 16/10, con i tre punti decisi.

**I quattro di `template/` sono il passo 4.2 del runbook della Fase 5 di aDa** (Francesco,
08/10). Vanno in fila perché scrivono tutti in `template/` e nello stesso file di test, e
ognuno legge i file del precedente. I numeri partono da 500 (Francesco, 08/10): sono fuori
dalla serie di aDa, e «PBI-500» non si confonde con un PBI dell'altro repository. Il primo
giro deve chiudere `fatto` col runner `0.1.0` installato, e la PR aprirsi qui. Il PBI del
layout (difetto 90) e il tag `v0.2.0` sono il passo 4.3, dopo questi.

**La barriera prima di 503** (Francesco, 08/10). Il giro 1 di `PBI-501` non ha potuto scrivere
sotto `.claude/` (difetto 97 di `PBI-102`): il criterio 5 è uscito dal PBI, e i due file li
copia una persona. `PBI-503` nomina `.claude/` in `ZERO.md`, e senza quella cartella il suo
primo criterio cade. Per questo aspettava la PR che la copia, che ha tolto la barriera
(`test/template-guardia-di-fase`, 08/10).

**`PBI-504`, il layout dai gate, è il passo 4.3** (Francesco, 09/10): il difetto 90 e la radice
dei test di D3, prima del tag `v0.2.0`.

**`PBI-505`, il lucchetto di fase che legge JUnit** (Francesco, 15/10): il difetto 3 di
`ada_planning`, che ha fermato il PBI-002 al primo criterio. Dopo il merge servono il tag, il
pin in `ada_planning` e la sezione `[junit]` del suo `asdlc.toml`: sono gesti umani e non
stanno in coda.
