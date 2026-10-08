# backlog/ — il delta

Un PBI è **il cambiamento**, non il dominio: transitorio, chiuso col merge. Lo stato del
sistema sta in `specs/`, e il PBI ci **punta** invece di copiarlo: una copia diventa obsoleta
il giorno dopo.

**Il modello è [`TEMPLATE.md`](TEMPLATE.md)**: si copia in `PBI-XXX-titolo-in-kebab.md` e si
riempie. Le sezioni sono Direttiva (con lo **Scope**) · ✅ Deciso · Il giro N, e cosa si
riprende · Dipendenze · Contesto (puntatori) · Verifica (spuntabile) · Protocollo di
rifinitura.

**Lo Scope contiene sempre il file del PBI stesso**, perché i suoi criteri si spuntano nel
giro che li chiude. Il Builder resta dentro lo Scope, e un PBI che non si nomina arriva in
`main` con la *Verifica* tutta a `[ ]`.
**Un PBI che tocca un file che il runner lancia durante il giro** (il server dell'esito, un
hook) lo dichiara nella *Direttiva*, e dice come il giro ci sopravvive.
**La risposta a un giro fermato nomina sempre il tag e i commit da riprendere**: il tag
`giro-fermato/…` del giro chiuso, e gli sha da riprendere in ordine con `git cherry-pick`, con
quelli da lasciare e perché. Il runner non riprende niente: crea un ramo nuovo dalla base, e
il Builder legge la ripresa nel PBI, nella sezione *Il giro N, e cosa si riprende*.
**Una decisione non chiede mai di cambiare un test nel GREEN.** In `IMPL` i test sono in sola
lettura (la guardia di fase di `ADR-0021`), quindi un test cambia nel commit RED, dichiarato
nel messaggio, o in `TEST_ONLY`.
Regole d'oro: **atomico** (o atterra tutto o niente), **auto-verificabile** (i suoi test
passano senza aspettare un altro PBI), **isolato** (non tocca i file di un PBI concorrente).

**Un criterio è un comportamento, non un esempio.** Criteri che la stessa modifica minima
rende verdi sono **un criterio solo con più esempi** — un test parametrico, con un id
esplicito per caso — perché il gate chiede un rosso per criterio, e un verde che ne chiude
tre lascia gli altri due nati verdi. E un criterio che dichiara un rosso lo si verifica
**caso per caso sulla base** prima di accodarlo: ogni input deve fallire da solo, per
asserzione, contro `main`. Un caso verde su `main` non è un criterio, è una **guardia**, e
va nella non regressione dichiarata come tale (`ADR-0022`).

## Eseguirli con un agente

Il runner (`asdlc-runner`) fa girare i PBI uno per volta con `claude -p`, contesto pulito
per PBI e **gate eseguiti dallo script**; il tick (`asdlc-coda`) li lancia nell'ordine di
[CODA.md](CODA.md). Girano sempre **installati dal tag** di `[ambiente].installa` in
`asdlc.toml`, mai dalla copia di lavoro (`ADR-0026`). Come si lancia la catena, e quanta
autonomia dare a un PBI, sta in [AUTOMAZIONE.md](AUTOMAZIONE.md).

## I difetti e le loro cause

Vale per il registro dei difetti del progetto, e per ogni elenco di difetti che verrà.

**Ogni difetto porta una riga `**Causa:** <slug>`**, subito sotto il testo, con uno slug
preso dalla tabella qui sotto. Il vocabolario è **chiuso**: se una causa non c'è, si aggiunge
una riga alla tabella nello stesso commit che la usa per la prima volta, e lo si dichiara nel
messaggio.

**Alla terza occorrenza della stessa causa si apre un PBI di approccio**, non un'altra
correzione locale. Tre difetti con la stessa causa sono un modo di lavorare, non tre
incidenti. Il PBI di approccio si scrive nella colonna della tabella, e da lì in poi i difetti
di quella causa vanno a lui. Il conto lo fa a mano chi scrive il difetto.

**Al merge, le note del Critic diventano difetti** quando nominano un presupposto o un ramo
senza test. Il rapporto del Critic chiude con `## Note per chi mergia`, e lì finiscono anche
le cose che oggi reggono per un'ipotesi che nessun test fissa: «funziona perché non c'è un
file X», «dipende dall'ordine delle due chiamate», «quel ramo non ha un test». Chi mergia le
registra nel registro dei difetti, con la loro `**Causa:**`, prima del merge o nella PR di
documentazione che lo segue. Così entrano nei conteggi della tabella, e la terza occorrenza
di una causa la vede qualcuno.

Non diventano difetti le note che descrivono una scelta dichiarata dal PBI (una sua
decisione), né quelle di forma, come un soggetto di commit impreciso o un commento. Resta un
giudizio di chi mergia, perché il runner non ricava una decisione dal testo del Critic
(`ADR-0027`).

| Slug | Cosa vuol dire | PBI di approccio |
|---|---|---|
| `esito-da-testo-libero` | il codice ricava un esito o una decisione dal testo libero di un modello | |
| `strumento-letto-come-testo` | l'output di un programma, esterno o nostro, letto come testo dove esiste o si può fare un formato strutturato: `gh`, vitest, pytest, la CLI, e anche lo stdout del runner letto da un suo test invece del valore che la funzione restituisce. La correzione è il formato, non la validazione | |
| `codice-letto-come-testo` | il gate ricava qualcosa di un programma (un test, una riga, un titolo) leggendone il sorgente come righe di testo, invece che col suo parser o col suo runner | |
| `ingresso-non-validato` | un dato che arriva da fuori al server dell'esito (dal modello, dall'ambiente) si usa senza controllarne la forma, e un valore inatteso fa cadere il processo o produce una diagnosi falsa | |
| `due-fonti` | il giro legge una cosa da una fonte e agisce su un'altra (l'albero e `origin`, il ref e `HEAD`, il remoto e il locale), e le due divergono | |
| `diagnosi-confusa` | due situazioni diverse finiscono nello stesso stato o nella stessa nota, e chi legge non le distingue | |
| `chiusura-saltata` | una strada d'uscita del giro non passa dalla chiusura: il ramo non si pubblica, i commit non si contano, l'uscita si perde | |
| `residuo-di-un-giro` | un giro trova ciò che un giro precedente ha lasciato (un ramo, un albero, un file) e non lo prevede, o lo lascia lui in silenzio | |
| `processo-per-euristica` | un processo si riconosce da dove sta e da come si chiama (`/proc/<pid>/cwd`, `pgrep -f`) invece che da un segnale che tiene solo lui, come un `flock` | |
| `concorrenza-non-esclusa` | due processi o due giri scrivono la stessa cosa e niente lo impedisce | |
| `test-senza-isolamento` | un test scrive o legge fuori dalla sua cartella temporanea, nello stato vero del repository o della macchina | |
| `scrittura-non-ignorata` | il runner scrive nell'albero un file che `.gitignore` non conosce, e rende sporco il giro che lo sta scrivendo | |
| `ambiente-non-dichiarato` | il comportamento dipende da qualcosa dell'ambiente di lancio (la sessione, il `PATH`, i pacchetti) che nessun file dichiara | |
| `percorso-di-macchina` | un file versionato porta un percorso che vale su una macchina sola, assoluto o con `~`, invece di un percorso con un'ancora nel repository | |
| `regola-non-scritta` | una regola del processo vive nell'abitudine di chi scrive o di chi lavora, e nessun documento che l'agente legge la dice | |
| `default-implicito` | una chiamata cambia e il suo valore di default prende il posto di quello che il codice di prima dava senza dirlo: permessi, codifica, fuso, ordinamento | |
| `traccia-persa` | il giro conosce il perché di un esito, ma non lo scrive dove qualcuno lo legge | |
| `modifica-senza-righe` | un cambiamento che non lascia righe nel diff (un rename, l'attraversamento di un confine, i permessi) e che i controlli fatti sulle righe non vedono | |
| `decisione-senza-verifica` | una decisione del PBI che nessun caso della Verifica esercita | |
| `soglia-non-misurata` | un tetto o una soglia fissati su un'ipotesi invece che su una misura | |
| `caso-scoperto` | una regola del gate vale per i casi che il PBI nomina, e un caso vicino che nessuno ha nominato le sfugge, anche se la rete che la regola si è data potrebbe coprirlo | |

**La colonna «PBI di approccio» c'è per ogni causa**, anche vuota: da segnalare è una causa
con tre occorrenze o più **e la colonna vuota**, non ogni causa arrivata a tre. Alla nascita
del progetto la colonna è vuota in ogni riga: i PBI di approccio sono del progetto che li
apre.
