# backlog/ — il delta

Un PBI è **il cambiamento**, non il dominio: transitorio, chiuso col merge. Lo stato del
sistema sta in `specs/`, e il PBI ci **punta** invece di copiarlo — una copia diventa
obsoleta il giorno dopo.

Formato: `PBI-XXX-titolo-in-kebab.md`. Sezioni: Direttiva (con lo **scope**) · Dipendenze ·
Contesto (puntatori) · Verifica (spuntabile) · Protocollo di rifinitura.
**Lo Scope contiene sempre il file del PBI stesso**, perché i suoi criteri si spuntano nel
giro che li chiude. Il Builder resta dentro lo Scope, e un PBI che non si nomina arriva in
`main` con la *Verifica* tutta a `[ ]` (difetto 43 di `PBI-102`, su 366 e 367).
**Un PBI che tocca un file che il runner lancia durante il giro** (il server dell'esito, un
hook) lo dichiara nella *Direttiva*, e dice come il giro ci sopravvive (difetto 66 di
`PBI-102`, su 383).
**La risposta a un giro fermato nomina sempre il tag e i commit da riprendere**: il tag
`giro-fermato/…` del giro chiuso, e gli sha da riprendere in ordine con `git cherry-pick`, con
quelli da lasciare e perché. Il runner non riprende niente (fra un giro e l'altro; dentro il giro, dopo `risolto`, il Builder riprende: `PBI-517`) (dopo il limite d'uso il tick riprende il PBI: `PBI-519`): crea un ramo nuovo da
`origin/main` (`nome_libero()`). L'unica ripresa che si è vista è quella del Builder che legge
il tag nel PBI (382 al giro 2; 388, che non lo nominava, è ripartito da zero). Vale finché il
repository `asdlc` non avrà una ripresa vera (`SCAFFOLDING.md`, §I PBI che si spostano).
Francesco, 30/09/2026.
**Una decisione non chiede mai di cambiare un test nel GREEN.** In `IMPL` i test sono in sola
lettura (la guardia di fase di `ADR-0021`), quindi un test cambia nel commit RED, dichiarato
nel messaggio, o in `TEST_ONLY`. La decisione 4 di `PBI-389` chiedeva il contrario, e il
Builder ha spostato il cambio nel RED dichiarandolo (nota 1 del Critic sulla #327; Francesco,
01/10/2026).
Regole d'oro: **atomico** (o atterra tutto o niente), **auto-verificabile** (i suoi test
passano senza aspettare un altro PBI), **isolato** (non tocca i file di un PBI concorrente).

**Un criterio è un comportamento, non un esempio.** Criteri che la stessa modifica minima
rende verdi sono **un criterio solo con più esempi** — un test parametrico, con un id
esplicito per caso — perché il gate chiede un rosso per criterio, e un verde che ne chiude
tre lascia gli altri due nati verdi. E un criterio che dichiara un rosso lo si verifica
**caso per caso sulla base** prima di accodarlo: ogni input deve fallire da solo, per
asserzione, contro `main`. Un caso verde su `main` non è un criterio, è una **guardia**, e
va nella non regressione dichiarata come tale (`ADR-0022`, nota del 23/09; misurato sul
primo giro di PBI-364).

**Una PR che accoda o scrive un PBI non si intitola `PBI-XXX:` e non nasce da un ramo `pbi/`**:
il tick la leggerebbe come la PR che lo *fa*. La coda si difende (`tocca_codice()`) e, da `PBI-528`,
anche il rilascio (attivo dal tag che lo contiene; il runner che lavora è quello installato): il 25/10 la #93, `PBI-525: …`, di soli file in `backlog/`, ha fatto
taggare `v0.8.0` senza il codice di 525. Si intitola «Accoda PBI-XXX…» o «PBI-XXX, bozza: …» (la
virgola basta: il titolo che il tick riconosce è `PBI-XXX:` con i due punti).

**Prima di accodare, rileggi** (le sette domande di `ADR-0031`; la forma e lo Scope li
controlla `asdlc-runner PBI-XXX --preverifica`, `PBI-520`):
- **R** — ogni criterio può nascere rosso su `main`?
- **F** — il GREEN è scrivibile nella fase?
- **T** — un test esistente contraddice una decisione?
- **A** — qualcosa sporca l'albero o scrive fuori?
- **E** — un RED che non termina, flag doppi, nomi in conflitto?
- **D** — una decisione è lasciata al Builder, o manca una dipendenza?
- **N** — i nomi e i fatti citati sono veri nel codice?

## Eseguirli con un agente

Il runner (`asdlc-runner`) fa girare i PBI uno per volta con `claude -p`, contesto pulito
per PBI e **gate eseguiti dallo script**; il tick (`asdlc-coda`) li lancia nell'ordine di
[CODA.md](CODA.md). Qui girano sempre **installati dall'ultimo tag**, mai dalla copia di
lavoro (`ADR-0026`). Quali PBI reggono l'autonomia e quali no sta in
[AUTOMAZIONE.md](AUTOMAZIONE.md).

## I difetti e le loro cause

Vale per `PBI-102` e per ogni elenco di difetti che verrà. Deciso da Francesco il 24/09/2026.

**Ogni difetto porta una riga `**Causa:** <slug>`**, subito sotto il testo, con uno slug
preso dalla tabella qui sotto. Il vocabolario è **chiuso**: se una causa non c'è, si aggiunge
una riga alla tabella nello stesso commit che la usa per la prima volta, e lo si dichiara nel
messaggio.

**Alla terza occorrenza della stessa causa si apre un PBI di approccio**, non un'altra
correzione locale. Tre difetti con la stessa causa sono un modo di lavorare, non tre
incidenti. Il PBI di approccio si scrive nella colonna della tabella, e da lì in poi i difetti
di quella causa vanno a lui.

Il conto lo fa a mano chi scrive il difetto. Farlo fare al tick è `PBI-368`, spostato al
repository `asdlc` il 25/09 insieme al tick (`ADR-0026`). Fino ad allora il conto resta a
mano. La classificazione all'indietro dei difetti 1-35 è fatta (sotto la tabella).

**Al merge, le note del Critic diventano difetti** quando nominano un presupposto o un ramo
senza test. Il rapporto del Critic chiude con `## Note per chi mergia`, e lì finiscono anche
le cose che oggi reggono per un'ipotesi che nessun test fissa: «funziona perché non c'è un
file X», «dipende dall'ordine delle due chiamate», «quel ramo non ha un test». Chi mergia le
registra in `PBI-102` come difetti, con la loro `**Causa:**`, prima del merge o nella PR di
documentazione che lo segue. Così entrano nei conteggi della tabella, e la terza occorrenza
di una causa la vede qualcuno. Deciso da Francesco il 30/09/2026: la nota 2 del Critic sulla
#308 diceva che `caso_junit()` presuppone il rootdir di pytest. È rimasta nel rapporto, e il
giorno dopo ha fermato il giro 1 di `PBI-384` (difetto 67).

Non diventano difetti le note che descrivono una scelta dichiarata dal PBI (una sua
decisione), né quelle di forma, come un soggetto di commit impreciso o un commento. Resta un
giudizio di chi mergia, perché il runner non ricava una decisione dal testo del Critic
(`ADR-0027`).

| Slug | Cosa vuol dire | PBI di approccio |
|---|---|---|
| `esito-da-testo-libero` | il codice ricava un esito o una decisione dal testo libero di un modello | `PBI-366`, `PBI-367` (`ADR-0027`) |
| `strumento-letto-come-testo` | l'output di un programma, esterno o nostro, letto come testo dove esiste o si può fare un formato strutturato: `gh`, vitest, pytest, la CLI, e anche lo stdout del runner letto da un suo test invece del valore che la funzione restituisce. La correzione è il formato, non la validazione. Allargata il 01/10/2026 (Francesco, difetto **77**): prima diceva «uno strumento deterministico» e «dove esiste» | `PBI-376` ✅: l'URL della PR creata viene dal JSON di `gh pr list`; l'esito di un test di vitest viene solo dalla sua voce nel rapporto JSON, i totali del comando non decidono per un test, e un rapporto che manca — anche perché vitest è scaduto — è un guasto del gate. `PBI-390` per pytest, alla terza occorrenza (difetto **65**, 29/09): l'identità di un test e il tipo del suo fallimento si leggono dal rapporto JUnit (`--junitxml`) e non più dallo schermo. Un id con uno spazio non combaciava con `RE_ESITO_PYTEST` né con `RE_RIEPILOGO_PYTEST` |
| `codice-letto-come-testo` | il gate ricava qualcosa di un programma (un test, una riga, un titolo) leggendone il sorgente come righe di testo, invece che col suo parser o col suo runner | `PBI-378` per il gate del rosso, cioè il perimetro dei mutanti dall'AST e le docstring (Francesco, 26/09); il resto va al primo PBI del repository `asdlc` (`ADR-0026`), insieme all'approccio di `default-implicito`: un lanciatore unico per ogni strumento esterno, con il criterio sull'AST (Francesco, 30/09); **`PBI-396`** per la nascita di un test Python, che si decide dalla collezione di `pytest --collect-only` sulla base e sul ramo e non più dal diff. Chiude per Python il difetto **31** e il **81** (03/10), la quinta occorrenza con il 26, il 31, il 33 e il 53. La metà vitest resta al repository `asdlc` (Francesco, 03/10) |
| `ingresso-non-validato` | un dato che arriva da fuori al server dell'esito (dal modello, dall'ambiente) si usa senza controllarne la forma, e un valore inatteso fa cadere il processo o produce una diagnosi falsa | `PBI-372`; per `--chiedi-impl`, che apre IMPL senza guardare lo Scope (difetto **89**, 04/10), un **PBI piccolo del repository `asdlc`**: `SCAFFOLDING.md`, §I PBI che si spostano |
| `due-fonti` | il giro legge una cosa da una fonte e agisce su un'altra (l'albero e `origin`, il ref e `HEAD`, il remoto e il locale), e le due divergono | `PBI-374`; `PBI-384` per il runner caricato all'avvio e i file che lancia dall'albero vivo (server dell'esito, hook), che il Builder può cambiare durante il giro (difetto **66**, 30/09); `PBI-385` per il tick spento nel crontab e ancora acceso nella tabella di cron: il tick si mette in pausa con un file, `~/asdlc-tick.pausa`, che legge a ogni passaggio (difetto **69**, 30/09); `PBI-392` per il checkout del tick, che decide da `origin/main` e installa il runner dal suo `HEAD`: il tick allinea il checkout con `ff-only` prima di decidere, e reinstalla se la firma cambia (difetto **75**, 01/10); `PBI-396` per il plugin della collezione, che importava l'`asdlc` installato invece di quello dell'albero esaminato: il plugin sta fuori dal nome `asdlc` (difetto **84**, 03/10); `PBI-397` per la collezione tenuta in cache sotto `HEAD` invece che sotto lo sha, come il ref del difetto 30: le chiavi di cache sono sha risolti con `git rev-parse`, mai riferimenti (difetto **91**, 05/10) |
| `diagnosi-confusa` | due situazioni diverse finiscono nello stesso stato o nella stessa nota, e chi legge non le distingue | `PBI-375` |
| `chiusura-saltata` | una strada d'uscita del giro non passa dalla chiusura: il ramo non si pubblica, i commit non si contano, l'uscita si perde | `PBI-369`, che però non copre un'eccezione **dopo** `chiudi()` (difetto 50): quella va a `PBI-377` |
| `residuo-di-un-giro` | un giro trova ciò che un giro precedente ha lasciato (un ramo, un albero, un file) e non lo prevede, o lo lascia lui in silenzio | `PBI-363`, allargato all'inventario di inizio e fine giro |
| `processo-per-euristica` | un processo si riconosce da dove sta e da come si chiama (`/proc/<pid>/cwd`, `pgrep -f`) invece che da un segnale che tiene solo lui, come un `flock`. Tre occorrenze al 25/09: il poller di Claude che fa dire `occupato` al tick (07/09); il Monitor che col suo `pgrep -f` trova sé stesso e non finisce mai (25/09); lo stesso Monitor che fa dire `occupato` al tick (25/09, difetto 47) | `PBI-373` |
| `concorrenza-non-esclusa` | due processi o due giri scrivono la stessa cosa e niente lo impedisce | `PBI-373`: il lucchetto come unica prova chiude anche il 9; **`PBI-392`** per il tick, alla terza occorrenza con il 9 e il 19 (difetto **70**, 30/09): il tick prende un lucchetto suo e lo tiene fino al distacco del runner, e `asdlc-chiudi-giro` prende lo stesso per tutti i sei passi. È il PBI di approccio della causa, come 373 lo è stato per il runner (Francesco, 30/09) |
| `test-senza-isolamento` | un test scrive o legge fuori dalla sua cartella temporanea, nello stato vero del repository o della macchina | **PBI del repository `asdlc`, fra i primi** (Francesco, 03/10), alla quarta occorrenza col difetto **83**, dopo il 38, il 45 e il 72. Tre regole: ogni test ha un progetto suo, cioè una fixture che copia il progetto di prova in `tmp_path`; la rete è spenta per default, e un marcatore la accende per il test che ne ha bisogno; un hook di fine sessione di pytest fa fallire la suite se l'albero del repository è cambiato. Quinta occorrenza il 05/10 col difetto **92**: il pre-commit che `apri_la_fase()` installa nel repo di prova lancia il runner vero della macchina, e il test dà un esito in CI e un altro sulla macchina del runner. Una quarta regola (Francesco, 05/10): i commit di preparazione nei test saltano gli hook, e un test che vuole l'hook lo installa apposta con un runner finto. `SCAFFOLDING.md`, §I PBI che si spostano **Coperta in forma ridotta da `PBI-518`** (20/10): il finto agente dei test del tetto scrive l'esito accanto alla config di `--mcp-config` e non più in `tools/tests/dati/progetto/`, il lucchetto del tick dei test va in `tmp_path`, e la guardia di fine suite `tools/tests/guardia_dei_dati.py` fa uscire rossa la suite, nominandoli, se in `tools/tests/dati/` restano file o cartelle nuovi, anche ignorati da git. La copia del progetto per ogni test e la rete spenta restano un PBI a parte, se la guardia ne mostra ancora. |
| `scrittura-non-ignorata` | il runner scrive nell'albero un file che `.gitignore` non conosce, e rende sporco il giro che lo sta scrivendo | la regola rovesciata in `.gitignore` (25/09): `runs/*` tranne `tempi.csv`, senza PBI |
| `ambiente-non-dichiarato` | il comportamento dipende da qualcosa dell'ambiente di lancio (la sessione, il `PATH`, i pacchetti) che nessun file dichiara | **`PBI-384`** (`SCAFFOLDING.md`, fase 5a): l'ambiente si dichiara in `[ambiente]` di `asdlc.toml` — `pacchetto`, `eseguibili`, `minimi` — e si verifica all'avvio del runner, del tick e dei test, con un errore esplicito «ambiente mancante». Terza occorrenza il 27/09: difetti 15, 21 e 60 (Francesco). Quarta il 03/10 col difetto **82**, la sonda di `PBI-394` che usa `sys.executable`: registrata e non corretta ora (Francesco, 03/10) |
| `percorso-di-macchina` | un file versionato porta un percorso che vale su una macchina sola, assoluto o con `~`, invece di un percorso con un'ancora nel repository | `PBI-384`: i percorsi di `asdlc.toml` si risolvono dalla radice del progetto o dalla radice comune del repository, e uno assoluto è un errore di configurazione (difetto 62, Francesco 28/09) |
| `regola-non-scritta` | una regola del processo vive nell'abitudine di chi scrive o di chi lavora, e nessun documento che l'agente legge la dice || **il modello degli ADR** (`decisions/README.md`): ogni regola di gate o di giro risponde a quattro domande obbligatorie, cioè cosa si controlla, quando, cosa conta come prova e cosa succede se manca. Terza occorrenza con il 43, il 59 e il 74 (01/10): `ADR-0022` non diceva quando si giudica il morso. È una PR di documentazione, non un PBI. Gli ADR esistenti si rileggono al trasloco nel repository `asdlc` (Francesco, 01/10). Quarta occorrenza il 04/10 col difetto **85**, il Builder che chiude il turno con un comando in background: lì la regola la fa rispettare una macchina, con un **PBI del repository `asdlc`** (la guardia di fase rifiuta `Bash` con `run_in_background`, e la regola entra nel prompt del Builder). `SCAFFOLDING.md`, §I PBI che si spostano |
| `default-implicito` | una chiamata cambia e il suo valore di default prende il posto di quello che il codice di prima dava senza dirlo: permessi, codifica, fuso, ordinamento | `PBI-387` per il rename detection: una lettura di git con un solo pathspec, o un elenco `--name-only`, vede un solo lato di un rename. Chiude il meccanismo dei difetti **61** e **31**: il 31 resta classificato `codice-letto-come-testo`, e `PBI-361` ne aveva chiuso solo il sintomo (Francesco, 28/09); `PBI-389` per i due buchi rimasti, l'elenco dei file con `--name-only` (difetto **64**, 29/09); `PBI-391` per il rootdir di pytest, che il gate scrive nel comando invece di lasciarlo ricavare dai file di configurazione (difetto **67**, 30/09). Al 30/09 le occorrenze sono quattro (46, 61, 64, 67), e ogni PBI della colonna corregge un meccanismo solo. **Approccio** (Francesco, 30/09): la regola di 387 e 391 si generalizza. Ogni strumento esterno (git, pytest, gh, vitest) si lancia da una funzione sola, che scrive nel comando i predefiniti da cui il runner dipende, e un criterio sull'AST vieta le chiamate dirette. È un PBI del repository `asdlc`, insieme a `codice-letto-come-testo` (`SCAFFOLDING.md`, §I PBI che si spostano). In aDa si apre un PBI di approccio solo alla quinta occorrenza. Quinta occorrenza il 04/10 col difetto **90**, `dove_gira()` che ha scritte a mano le cartelle di aDa: un PBI suo, fra i primi del repository `asdlc` e prima di `v0.2.0`, insieme al `Path(__file__).parents[2]` di D3 (Francesco, 04/10) |
| `traccia-persa` | il giro conosce il perché di un esito, ma non lo scrive dove qualcuno lo legge | Terza e quarta occorrenza il 04/10, coi difetti **86** e **88**, dopo il 14 e il 58: la colonna è ancora vuota (04/10) |
| `modifica-senza-righe` | un cambiamento che non lascia righe nel diff (un rename, l'attraversamento di un confine, i permessi) e che i controlli fatti sulle righe non vedono | `PBI-389` per il difetto **63**, la prima occorrenza (29/09): un rename che entra in produzione da fuori conta come tutte righe aggiunte |
| `decisione-senza-verifica` | una decisione del PBI che nessun caso della Verifica esercita. Nata il 01/10/2026 col difetto **80** (Francesco) | |
| `soglia-non-misurata` | un tetto o una soglia fissati su un'ipotesi invece che su una misura | |
| `caso-scoperto` | una regola del gate vale per i casi che il PBI nomina, e un caso vicino che nessuno ha nominato le sfugge, anche se la rete che la regola si è data potrebbe coprirlo. Nata il 04/10/2026 col difetto **87** (Francesco) | |
| `test-per-il-motivo-sbagliato` | un test è verde per una proprietà dei dati o della prosa che non è quella che il suo nome dichiara, e diventerebbe rosso, o resterebbe verde, per la ragione sbagliata. Nata il 09/10/2026 col difetto **98** (Francesco) | |

**La colonna «PBI di approccio» c'è per ogni causa**, anche vuota: è quella che `PBI-368`
legge. Il tick segnala una causa con tre occorrenze o più **e la colonna vuota**, non ogni
causa arrivata a tre.

**Classificati all'indietro il 25/09/2026** i difetti 1-35 di `PBI-102` (Francesco e Claude:
la proposta riga per riga e le correzioni sui disaccordi). Da lì sono nati nove slug. Il
conto a quel giorno: `due-fonti` 8, `chiusura-saltata` 6, `ingresso-non-validato` 4,
`diagnosi-confusa` 4, `esito-da-testo-libero` 4, `codice-letto-come-testo` 3,
`residuo-di-un-giro` 3, `processo-per-euristica` 3, e sotto tre tutte le altre. I PBI di
approccio si scrivono in quest'ordine: 374, 375, e la riga di 369 e l'allargamento di 363, poi
376, tutti prima dei PBI di impacchettamento di `ADR-0026`. `codice-letto-come-testo` va al
repository `asdlc`.

## Le cause `runner-*`

Uno slug che comincia per `runner-` è una causa **del runner** e di nessun altro: indica un
limite di `asdlc`, che si corregge con un PBI in `asdlc` e non a mano nel progetto. L'elenco è
**chiuso** e si allarga con un ADR. Il Solver (`specs/solver-e-rilascio/spec.md`, R3) non apre
mai un PBI a monte per una causa fuori da questo elenco. I progetti lo citano con un URL
pinnato al tag e tengono solo le proprie cause.

| Slug | Cosa vuol dire | PBI |
|---|---|---|
| `runner-non-legge-junit` | il runner decide l'esito di un test senza leggere il rapporto JUnit, o ne legge uno incompleto (difetto 3 di `ada_planning`) | `PBI-505` |
