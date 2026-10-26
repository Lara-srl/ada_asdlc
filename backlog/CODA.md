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
- PBI-520
- PBI-521
- PBI-522
- PBI-523
- PBI-516
- PBI-524
- PBI-525
- ‖ tag `v0.9.0` e pin in `ada_nlt`, `ada_dispense`, `ada_unical`; poi i PBI letti e accodati per la `v0.10.0`

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

**`PBI-520`–`PBI-522`, la pre-verifica dei PBI prima del giro** (`ADR-0031`, Francesco, 20/10).
Vanno in fila: il 521 usa il comando, il rapporto e i testi dei criteri del 520, e il 522 mette
nel giro le funzioni di tutti e due. Ognuno è passato da una lettura avversariale prima di
entrare qui (la sezione in fondo al PBI). La barriera dopo il 522 è il rilascio: finché il tag
e il pin non ci sono, il tick lavora con la `v0.5.0` e la pre-verifica non è accesa.

**`PBI-523`, la pre-verifica dentro il conto del giro** (Francesco, 21/10): le due correzioni che il
Builder ha proposto nel giro 1 del 522, che lì restano un limite dichiarato. Va nel rilascio dopo la
`v0.6.0`, ed è passato da una lettura avversariale su `main` (la sezione in fondo al PBI).

**`PBI-516`, i token di ogni giro nel rapporto** (Francesco, 21/10): dopo il 523, perché tocca gli
stessi file, e riletto su `main` prima di entrare (la sezione in fondo al PBI). Dopo il 516 il
rilascio `v0.7.0` e la pausa del tick: la coda si ferma lì.

**`PBI-524` e `PBI-525`, i fermi meccanici dei tre progetti** (Francesco, 25/10): letti il 25/10 col
Lettore (le sezioni in fondo ai PBI), 524 prima perché 525 tocca gli stessi punti di `builder.md` e del
gate. Il 525 dichiara `rilascia: minor`: dopo il suo merge il tick taglia la `v0.9.0`, e la barriera è
il pin nei tre progetti. ~~la `v0.8.0`~~: *corretto il 26/10.* La `v0.8.0` esiste già ed è un tag
fantasma: il tick l'ha tagliata il 25/10 sul merge della #98, che accodava 524 e 525 e toccava solo
`backlog/` (il difetto di `PBI-528`). Il codice di quel tag è quello della `v0.7.0`; non si cancella,
perché il tick lo rifarebbe, e `prossimo_tag()` dà la `v0.9.0`. `PBI-526` (il verde per costruzione su
SQL) e `PBI-527` (i criteri a vista) vengono dopo, nella `v0.10.0`, prima che parta `ada_nlt` `PBI-6`.

