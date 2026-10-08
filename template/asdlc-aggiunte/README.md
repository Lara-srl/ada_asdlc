# Le aggiunte del progetto ai prompt del runner

I prompt dei cinque ruoli del runner ASDLC — `builder`, `igiene`, `riprova`, `critic`,
`rimedio` — sono dati del pacchetto `asdlc`, in `asdlc/prompt/<ruolo>.md`, e arrivano con
l'installazione.

Questa cartella è dove il progetto li **estende**. `asdlc.toml` la dichiara in
`[prompt].aggiunte`, e il runner:

- accoda il file `<ruolo>.md` di qui al prompt di quel ruolo, dopo una riga
  `## Aggiunte del progetto`;
- a un ruolo senza file non aggiunge niente;
- il testo lo passa così com'è: le graffe non sono segnaposto.

**Un'aggiunta non sostituisce niente.** Il prompt del pacchetto resta intero, e l'aggiunta
gli sta in coda: le istruzioni che portano i difetti imparati non spariscono senza che
nessuno lo decida. Una chiave di `[prompt]` diversa da `aggiunte` è un errore di
configurazione, e non esiste un modo di rimpiazzare un prompt da qui.

Oltre a questo `README.md`, qui stanno solo file `<ruolo>.md`: un nome che non è un ruolo
(`bulder.md`, `critic.txt`) ferma il runner all'avvio, perché un refuso non diventi
un'aggiunta persa in silenzio.

Un progetto appena nato non ha aggiunte: si scrive un `<ruolo>.md` quando un ruolo ha
bisogno di sapere qualcosa che è solo di questo progetto.
