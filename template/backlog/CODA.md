# La coda dei PBI

L'ordine in cui i PBI vanno lanciati, e i punti in cui la coda si ferma da sola.
La scrive **una persona**, a mano. `asdlc-coda`, il tick, la esegue e non la modifica mai:
una voce è qui perché qualcuno ce l'ha messa, ed è quello il cancello.

**Come si legge una riga**

- `- PBI-12` — un PBI da lanciare. Il tick lo lancia quando il precedente è in `main`.
- `- ‖ testo` — una **barriera**: un gesto umano. Il tick ci arriva, lo scrive e si ferma.
  Si toglie la riga quando il gesto è fatto.

Tutto il resto è prosa e il tick non la guarda. La forma dell'id è il modello `[backlog].id`
di `asdlc.toml`.

**Una voce si spegne quando una PR mergiata nomina quel PBI** — nel titolo `PBI-XXX: …`
**oppure** nel ramo `pbi/pbi-XXX` — *e* ha toccato qualcosa **fuori da `backlog/`**. Il titolo
da solo non distingue la PR che *accoda* un PBI da quella che lo *fa*, e la prima arriva per
prima: una PR che scrive solo il file del PBI e la sua riga qui non spegne niente. Se tocca
anche un file fuori da `backlog/`, per esempio un ADR, lo spegne lo stesso: è il limite
dichiarato della regola.

**Mettere un PBI in coda è dichiarare che le sue domande sono chiuse**, ed è l'unico
cancello che ci sia: il tick non lo rifà, perché non può. Il carattere `❓` nel PBI non è la
prova né del contrario né a favore: può essere una domanda aperta o un protocollo di
rifinitura già deciso, e i due si distinguono leggendoli. Il tick lo stampa nel log come
avviso e lancia lo stesso (`ADR-0008`).

Se una domanda si apre comunque a giro iniziato, il Builder chiama lo strumento `fermati`:
niente PR, niente merge, e la coda si ferma da sé senza che nessuno debba accorgersene. Lo
stesso fa un agente che non dichiara niente, e il giro chiude `senza esito` (`ADR-0027`). Un
giro fermato lascia un ramo su `origin` senza PR, la voce resta in `attende`, e lo chiude
una persona (`AUTOMAZIONE.md`, *Spegnere il tick e chiudere un giro fermato*).

## La coda

Vuota alla nascita del progetto. Il primo PBI va qui sotto, una riga per PBI, nell'ordine in
cui devono entrare in `main`.
