# Quanta autonomia dare all'agente, PBI per PBI

`tools/asdlc/runner.py` esegue i PBI in sequenza con `claude -p`, un contesto pulito per
PBI, e i **gate eseguiti dallo script** — non dichiarati dall'agente. Ma l'autonomia non è
una proprietà dello strumento: è una proprietà del **gate**. Dove il gate sa dire da solo
se il lavoro è giusto, l'agente può correre; dove non lo sa, correre significa solo
sbagliare prima.

## Il giro che fa il runner

```
                    ┌──────────── gate rossi ────────────┐
                    ↓                                    │
  PBI → [Builder]  →  Quality Gate      →  Review Gate  →  Acceptance Gate
        sessione     ① pytest · tsc        [Critic]        la PR
        nuova,          eslint · vitest    sessione        ✋ umano
        micro-commit    (E2E: la CI)       separata,
                     ② e quei test sono    sola lettura,
                        mai stati rossi?   modello diverso
                     ↑ li esegue lo             │
                       script, non              │
                       l'agente                 │
                    └────────── violazioni ─────┘
                     │
                     └→ ✋ fermato, con l'elenco dei commit
```

Sono **tre gate diversi** perché rispondono a tre domande diverse
(`.claude/skills/asdlc/patterns/context-gates.md`):
*compila e passa i test?* · *rispetta il contratto della spec?* · *è la cosa giusta?*
Il primo lo sa una macchina, il secondo un agente **che non ha scritto il codice**, il
terzo solo una persona. Un builder che rilegge il proprio lavoro nella stessa sessione
conferma le proprie premesse: è la ragione per cui il Critic è una sessione nuova, con un
modello diverso e senza permessi di scrittura.

**I gate, le soglie e i percorsi del runner stanno in `asdlc.toml`** (`PBI-358`), letto da
`tools/asdlc/config.py`: i quattro comandi con la loro cartella, il ramo di base, il
prefisso dei rami, i modelli dell'id e del nome file dei PBI, il registro, il venv, le tre
soglie. Il file porta il **valore**; la ragione di ogni soglia resta nel sorgente, accanto
alla riga che la legge. Due cose valgono la pena di sapere: un gate con `solo_se_tocca`
gira solo se il diff del branch tocca uno di quei percorsi (senza il campo è sempre
acceso); e `[gate_del_rosso].attivo = false` spegne la seconda domanda qui sotto **e lo
dichiara** — a schermo, nel rapporto e nella nota di `runs/tempi.csv` — per un progetto
il cui runner di test il gate non sa leggere. In aDa resta `true`: un gate che si
indebolisce in silenzio è la prima cosa che questa pagina vieta.

**Il Quality Gate ha due domande, non una** (`PBI-103`). La prima è *i test passano?*;
la seconda è *quei test sono mai stati rossi?*, e la sa una macchina come l'altra. Un test
nato verde non prova niente: può essere verde perché il codice è giusto, o perché non
guarda niente. Il gate cammina i commit da `origin/main` in avanti e per ogni commit che
introduce **test nuovi** lo estrae in un worktree usa e getta e ci gira dentro **soltanto
quei test**, aspettandosi il rosso. Un commit che porta test nuovi *e* file di produzione
insieme lo ferma senza eseguire niente: il rosso non può essere esistito in mezzo a un
commit solo, e basta il diff a dirlo.

L'esito si legge **test per test**, non dal totale del comando che li ha girati insieme.
Un `test(...) (RED)` porta quasi sempre più di un test, e il conteggio finale (`1 failed,
11 passed`) dice che *qualcosa* era rosso, non quale: in un commit che porta un test che
morde e uno nato verde, nell'elenco ci finisce il secondo.

**Un test nato verde passa se morde** (`PBI-105`, `ADR-0022`). «Nato verde» da solo ha
un falso positivo sistematico: la guardia che il Critic ordina su un comportamento che
c'è già nasce verde per forza, e su PBI-333 ha chiuso due giri su quattro. Prima di
fermare, il gate muta le righe di produzione che il branch ha cambiato fino a quel
commit — cancella la riga, scambia `===`/`!==`, `&&`/`||`, `true`/`false`, `<`/`<=` — e
rigira **quel test** un mutante alla volta: se almeno uno lo fa fallire **per asserzione**
il test passa e il rapporto dice quale; se nessuno, ferma con «nato verde e non morde».
Un mutante che rompe la compilazione non conta: fa fallire tutto, non il test.

Ferma vuol dire **`fermato`, subito** — non un rilievo da mandare al Builder. Il ciclo
mancato è *ex ante* e nessuna fix lo annulla: il giro si chiude con l'elenco (commit,
test, esito) e la lettura la fa una persona. È anche il modo per scoprire se esistono casi
in cui il rosso davvero non si può vedere — uno `skipif` a quel commit chiude con «rosso
non osservabile», che è una lettura diversa da «nato verde» — invece di deciderlo prima di
averne visto uno. Il divieto in `AGENTS.md` c'era già: due volte in tre giorni (`PBI-328`,
`PBI-330`) non ha fermato niente, perché **una frase in un prompt non è un vincolo** — è
un consiglio che l'agente pesa insieme agli altri. I gate sono l'unica cosa che lega.

**Sulla strada del rimedio il rosso non è disponibile, e si dichiara invece di
fabbricarlo.** Quando il Critic dice *«questo criterio non ha un test che lo misura»*, il
codice che il rilievo riguarda è già committato: qualunque test il Builder scriva al giro
dopo nasce verde. `PBI-332` lo ha misurato al primo lancio col gate in servizio — due
commit fermati su due, ed erano tutti e due risposte a un rilievo.

`PROMPT_RIMEDIO` ha detto **come** in due modi, e il primo era sbagliato. Fino al 02/09
ordinava di riportare il test davanti al codice con un `git rebase` e di verificarlo rosso
lì; il giro 6 di `PBI-333` si è chiuso `sospeso` proprio su quella domanda, e la
contraddizione era interna alla macchina — `ADR-0021` chiede il rosso prima, e il prompt
ordinava il gesto che lo fabbrica dopo. **Francesco ha deciso che il riordino non vale
come rosso osservato** (02/09/2026, misurato in `PBI-105` su un albero staccato identico
byte per byte).

Da lì il prompt distingue il rilievo: se manca la **guardia** su codice giusto, il test
resta in coda, si committa da solo in `TEST_ONLY` senza `--chiedi-impl`, e il messaggio
dichiara che nasce verde — poi sono i mutanti di `ADR-0022` a dire se morde, e se non
morde il difetto è nel test; se invece il **codice è sbagliato**, il rosso c'è davvero e
sono **due** commit, `test (RED)` e `fix`. Il prompt chiede, il gate verifica: da solo
nessuno dei due basta.

Un gate che **non ha potuto guardare** non ferma niente: `pytest` fuori dal `PATH`, `npm`
senza `node_modules`, un comando che torna un codice che né pytest né vitest usano. Lì il
giro chiude `rosso` con la ragione vera e non accusa nessun commit — «il rosso non si è
mai visto» e «il gate non è partito» sono due diagnosi opposte, e la prima è la più grave
che il runner sappia emettere. A mano il gate torna `2` invece di `1`.

```bash
python3 tools/asdlc/runner.py --gate-rosso pbi/pbi-330      # il solo gate, su un branch
python3 tools/asdlc/runner.py --gate-rosso d2c084c..pbi/pbi-330   # o su un intervallo
```

**I commit li fa il Builder, la PR la apre lo script, il merge no.** Micro-commit durante
il lavoro — 3-5 per PBI, ognuno un punto di ripristino: un commit unico finale non
ripristina niente. Nessun squash prima della validazione; al confine del merge ci pensa la
PR, ed è lì che la responsabilità torna umana
(`.claude/skills/asdlc/practices/micro-commits.md` §5).

⏳ **Rinviato, con la sua condizione: il Critic su un provider diverso.** Lo standard
chiede *il cambio di sessione* (obbligatorio, c'è) e *il cambio di modello* (consigliato,
c'è: `--model opus` contro il modello del Builder). Il **cambio di provider** è il livello
avanzato — serve a decorrelare i punti ciechi, perché due modelli della stessa famiglia
possono sbagliare d'accordo (`.claude/skills/asdlc/patterns/context-gates.md`,
*circular validation*). Oggi non si fa perché il runner passa dalla CLI di Claude, che dà
al Critic il filesystem e `git diff`; con un altro provider il diff andrebbe impacchettato
a mano e passato al gateway. **Scatta quando** il Critic comincia a dare PASS su cose che poi la PR respinge:
è il segnale che builder e giudice condividono l'errore. Da lì la strada è LiteLLM — già
in casa e già agnostico — ma prima conviene provare le **corsie di lente** (Architect ·
SecOps · QA: tre prompt diversi, stesso modello), che costano molto meno e catturano
classi di difetti diverse.

Il runner controlla anche **l'igiene**: se dopo un giro restano modifiche non committate,
rimanda l'agente a committarle — ciò che non è committato non esiste, non si giudica e non
si ripristina.

Le tre categorie qui sotto le separa sempre lo stesso criterio: **cosa deciderebbe la
differenza fra giusto e sbagliato, e chi ce l'ha in mano.**

## 🟢 Autonomi — il gate decide da solo

`PBI-201` `PBI-202` `PBI-203` `PBI-205` `PBI-207` `PBI-210` `PBI-214` `PBI-305` `PBI-306` `PBI-307` `PBI-308` `PBI-309` `PBI-332` `PBI-404` `PBI-406`

Sono i PBI il cui esito è **aritmetico o strutturale**: il golden test coincide al centesimo
o no; le corsie contano giusto o no; il guard test passa o no. Qui il ciclo
`agente → gate → correggi` converge, e l'umano interviene alla PR.

`PBI-201` è il caso perfetto: la specifica è verificata al centesimo, il motore è puro,
il test non ha bisogno di database. Se il numero non è 496,513, è rosso — e non c'è
opinione che possa dire il contrario.

`PBI-214` sta qui perché ogni sua verifica è un'uguaglianza: le due scomposizioni sommano
ai loro totali o no, `ricavo − costo` fa la differenza o no, la rotta risponde o dà 500, il
golden della riga 12 e le 662 pratiche di PBI-202 restano verdi o no. Non c'è niente da
guardare: quello che si guarda è il riquadro, ed è PBI-212.

⚠️ Con una riserva che il PBI dichiara: se l'identità delle tre colonne non regge
l'arrotondamento, la scelta fra emendare ADR-0014 e dichiararlo nella spec **non** è
dell'agente. Il protocollo di rifinitura glielo dice, e con una chiamata a `fermati` la
domanda arriva qui — che è il comportamento voluto, non un fallimento.

`PBI-332` sta qui perché il foglio filtrabile è una **somma**: le righe rese sommano ai
totali o no, `sotto_soglia=true` rende esattamente le righe marcate o no, `q` trova la stessa
pratica per numero, nome e targa o no, un `ordina` inventato è 422 o è un 500. Non c'è niente
da guardare: quello che si guarda è la pagina, ed è PBI-333.

`PBI-406` sta qui perché tutto ciò che il PBI promette è **strutturale**: l'override torna
dal database o no, la riga cancellata rimette in vigore il file o no, un salvataggio senza
`{perimetro}` è 400 o no, un `officina` sulle rotte è 403 o no. Ciò che nessun gate giudica
— se il prompt riscritto rende aDa più utile — non è lavoro dell'agente: è la ragione per
cui il PBI esiste, e resta in mano a chi scrive il prompt.

## 🟡 Assistiti — l'agente scrive, l'umano guarda prima del merge

`PBI-206` `PBI-208` `PBI-209` `PBI-211` `PBI-212` `PBI-301` `PBI-304` `PBI-310` `PBI-312` `PBI-333` `PBI-334` `PBI-401` `PBI-402` `PBI-403`

Il gate dice se **funziona**, non se è **giusto**. Una vista Analisi può passare tutti i
test ed essere illeggibile; dei tool di scrittura possono funzionare ed essere pericolosi
nel modo che ADR-0007 descrive. Falli girare col runner, ma leggi il diff prima del merge:
è l'Acceptance Gate, e non è delegabile allo strumento che ha prodotto il lavoro.

`PBI-403` merita una riga sua: è l'unico dove un errore **scrive nel database**. Falli
girare, ma su un database usa-e-getta.

`PBI-211` sta qui e non fra i 🟢 per metà: la rotta ha un esito aritmetico — o coincide col
motore o no — ma il riquadro no. Un margine mostrato in modo che Barbara non riconosce è
passato da tutti i gate e ha mancato lo scopo del PBI.

`PBI-212` sta qui per la stessa metà, ereditata da `PBI-211`: che la colonna delle
differenze sommi al margine totale lo dice un test; che la tabella si legga, no. La parte
verificabile però è più larga che nel 211 — le tre colonne, la somma a video, «Extra» fuori
dalla griglia — quindi il diff da leggere prima del merge è corto.

`PBI-312` sta qui e non fra i 🟢 nonostante i suoi criteri siano quasi tutti verificabili:
il PBI **abroga un criterio di un altro PBI** (`PBI-309`, sui due flag), e una revoca la
legge una persona. Il resto — dove compare un campo, che i due flag restino indipendenti,
che l'etichetta mostri l'aliquota viva — lo dice un test.

`PBI-333` e `PBI-334` stanno qui per la metà che nessun gate giudica, ed è la stessa di
PBI-208: che i totali vengano dal server lo dice un test, che la tabella si legga su uno
schermo da officina no. La parte verificabile è larga — i filtri nell'URL, il clic che apre
la pratica, le dodici barre in ordine, il gruppo senza mese dichiarato invece che messo in
oggi — quindi il diff da leggere prima del merge è corto. **Il resto lo dice Barbara**, e i
due PBI lo scrivono nel loro Protocollo di rifinitura invece di decidere al suo posto.

`PBI-310` gira sui **dati veri** di `data/`, che il runner su questa macchina ha e la CI no:
i suoi test si saltano quando il foglio manca, come il golden. Ciò che nessun gate giudica è
se i 354 nomi importati sono i clienti che Barbara riconosce — e quello si vede solo
guardandoli.

⚠️ ~~`PBI-301` porta un **cancello aperto**:~~ **chiuso il 23/08.** Resta vero che la migrazione tocca `clienti`, che ha dati sopra.
Va chiuso da Francesco *prima* di lanciarlo, come è stato fatto per `PBI-210` — altrimenti
l'agente si ferma sul CHIEDI, e fa bene.

## 🔴 Non automatizzabili — manca un pezzo che nessun agente può procurarsi

| PBI | Cosa manca davvero |
|---|---|
| `PBI-100` | I `data-testid` non esistono ancora nel frontend, e `.github/workflows/` lo pusha Francesco |
| ~~`PBI-204`~~ | ~~Una misura sul foglio~~ — **fatta il 22/08** (`tools/misura_incassato_categorie.py`, 301 righe su 422) e ADR-0002 è Accettata: esce da questo elenco |
| ~~`PBI-302`~~ | ~~Quanto sono compilati i telefoni~~ — **la chiave è stata scelta il 22/08 e non è il telefono: è P.IVA/codice fiscale.** Non esce da qui però: adesso manca lo *storico* di quel campo, che PBI-301 comincia a raccogliere. Resta fermo per scelta, non per misura |
| `PBI-303` | Il vincolo è *«veloce almeno quanto il foglio di carta»*: lo verifica una persona che ha visto Barbara lavorare |
| `PBI-311` | Stesso vincolo del 303, altra schermata: *«si legge in un colpo d'occhio»* non lo dice un gate. Va guardato con Barbara alla demo, e allora scende fra i 🟡 |
| ~~`PBI-308`~~ | ~~Aspetta la risposta su stato terminale o cancellazione~~ — **risposto il 22/08: resta.** Passa fra i 🟢: il suo esito è strutturale — `is_at_or_beyond` falso, nessun `forzata` spurio, esclusa dalle medie |
| `PBI-405` | Serve il **gateway vero** con le chiavi: un eval simulato non risponde alla domanda che l'eval esiste per porre |

Per questi il runner serve comunque — in `--dry-run`, per vedere il prompt — ma il PBI si
apre solo quando il pezzo mancante è arrivato. Il PBI stesso lo dice: sta nelle sue
Dipendenze e nel Protocollo di rifinitura.

## Come far girare la catena

```bash
cd ~/ada-run && git fetch -q origin && git switch -q --detach origin/main
~/ada_controller/.venv-asdlc/bin/asdlc-runner PBI-201

~/ada_controller/.venv-asdlc/bin/asdlc-runner PBI-201 --no-pr            # solo il branch locale
~/ada_controller/.venv-asdlc/bin/asdlc-runner PBI-201 PBI-203 PBI-207    # una tratta, in sequenza
```

Il runner è quello **installato** (sotto, *Il runner installato*): lanciato come
`python3 tools/asdlc/runner.py` su un PBI esce con «ambiente mancante», perché girerebbe
dalla copia di lavoro dell'albero. Il venv dei gate, `backend/.venv`, lo mette sul `PATH` da
sé.

Il runner si **stacca da sé** e scrive in `runs/<run>.log`, accanto al rapporto
`runs/<run>.json`; `--in-primo-piano` chiede il contrario.

⚠️ **Niente `--e2e`**: `npm run e2e` da un worktree punta a `localhost:8081`, cioè allo stack
del checkout principale, e dà un rosso che parla di un altro codice — 33 minuti su PBI-320.
Gli E2E li fa la **CI sulla PR**, che lo stack lo costruisce dal branch (`ADR-0009`). A mano,
sullo stack del branch: `e2e/README.md`.

Il runner si **ferma** al primo PBI rosso, respinto dal Critic, fermato o senza esito, e non
prosegue: i PBI hanno dipendenze dichiarate, e costruire su una base rossa costa più di
quanto risparmia. Se un agente si ferma con una domanda, quella domanda è il prodotto della
sessione — va nella spec o nell'ADR, non buttata riprovando con lo stesso prompt.

L'esito di un agente il runner non lo legge dal testo della risposta, ma dalla **chiamata a
strumento** con cui l'agente lo dichiara (`ADR-0027`): a ogni invocazione di Builder e Critic
genera in `runs/` una config MCP che accende il server dell'esito (`tools/asdlc/esito.py`)
con due strumenti, `fatto` e `fermati`, e il file in cui il server scrive la prima chiamata
valida. `fatto` del Builder porta il riepilogo, quello del Critic il verdetto — `pass` o
`non pronto` — e il rapporto; `fermati` porta la domanda, intera. Il testo della risposta
resta per le persone e non decide niente. Un agente che non chiama nessuno dei due — un
limite d'uso, un crash della CLI, un modello che ha scritto e basta — chiude il giro
**`senza esito`**, senza igiene e senza gate: stdout, stderr e codice d'uscita di
`claude -p` restano accanto al file d'esito, e il rapporto del giro ne porta i percorsi
insieme al log delle chiamate al server, dove si vedono anche quelle rifiutate.

## Quanto tempo ci mette — e quindi quanto costa

Ogni esecuzione appende una riga per PBI in **`runs/tempi.csv`**:

```
run · pbi · stato · iniziato · finito · durata_s · durata_hms
     builder_s · gate_s · critic_s · tentativi · revisioni · commit · pr · nota
```

```bash
python3 tools/asdlc/runner.py --riepilogo --tariffa 90
```

```
PBI        esec    totale    agente      gate      costo
-------------------------------------------------------
PBI-201       1   0:41:12   0:31:02   0:10:10     61.80€
PBI-205       2   1:03:00   0:46:20   0:16:40     94.50€
-------------------------------------------------------
TOTALE        4   2:06:42   1:34:52   0:31:50    190.05€
```

Quattro cose da sapere prima di mettere quel numero in fattura:

- **`durata` è tempo di parete, tentativi falliti compresi.** Un PBI rimasto rosso dopo tre
  giri ha una sua riga con `stato=rosso`: quel tempo è stato speso davvero, e toglierlo
  dal conto renderebbe il totale più bello e meno vero.
- **La colonna è scomposta apposta.** `agente` (builder + critic) è il tempo in cui lavora
  il modello; `gate` è tempo di macchina — pytest, build, Playwright — che scorrerebbe
  identico con un ingegnere umano al posto dell'agente. Tenerle separate è ciò che rende il
  numero difendibile davanti a un cliente che chiede *«e questi 31 minuti cosa sono?»*.
- **Rieseguire un PBI aggiunge una riga, non la sostituisce.** Il totale di progetto è la
  somma di tutte le righe, che è la domanda giusta: quanto è costato arrivarci, non quanto
  sarebbe costato sapendolo già.
- **Non c'è dentro il tempo umano** — leggere la PR, rispondere alle domande degli agenti,
  chiedere a Barbara, decidere. È la parte che decide se il lavoro è giusto, e va contata a
  parte: questo CSV misura la macchina, non il progetto.

`runs/tempi.csv` è **versionato** (è il registro della fatturazione, poche righe); i
`runs/*.json` no — contengono i rapporti del Critic e crescono. In `.gitignore`:
`runs/*.json`.

⚠️ **Il giro non scrive il CSV** (`ADR-0020`): scriverlo dal branch faceva uscire la PR
`CONFLICTING` su un file che il PBI non aveva toccato. Il giro lascia il suo rapporto, e le
righe entrano in `main` **dopo il merge**, da lì:

```bash
python3 tools/asdlc/runner.py --registra ~/ada-run/runs   # idempotente su (run, pbi)
git add runs/tempi.csv    # e una PR `chore(ci): registra i giri`
```

## Il runner installato

Il runner e il tick sono il pacchetto `asdlc`, in `tools/asdlc/` (`PBI-383`), e dal `PBI-384`
si **installano**: il runner che lavora è quello installato, mai la copia di lavoro che il
Builder sta cambiando (`ADR-0026`, decisione 3). Il venv è dedicato, `.venv-asdlc` nella
radice comune del repository — il checkout principale, lo stesso da ogni worktree — ed è
`asdlc.toml` a dichiararlo, `[ambiente].pacchetto`. L'installazione è **non editabile**:

```bash
cd ~/ada_controller
python3 -m venv .venv-asdlc
.venv-asdlc/bin/pip install --no-deps --force-reinstall ./tools
```

**Da dove si installa lo dice `asdlc.toml`, `[ambiente].installa`** (`PBI-395`): la stringa
che si passa a `pip install`, dalla radice del progetto. Due forme sole: una **cartella**
relativa alla radice (`"./tools"`, il valore di oggi in aDa), oppure un **URL git pinnato a
un tag**, `git+ssh://…@v<maggiore>.<minore>.<patch>[#subdirectory=…]`. Un URL senza `@v…`, su
un ramo, o un percorso assoluto o con `~` sono un errore di caricamento che nomina la chiave
(`ADR-0026` pinna a un tag, mai a un ramo). La chiave è obbligatoria quando c'è
`[ambiente].pacchetto`, e sta solo in `asdlc.toml`: in `asdlc.local.toml` è rifiutata, perché
il pin è del progetto e una macchina con un pin suo girerebbe una versione che nessun altro
ha. **Salire di tag è una PR che cambia il pin**, `@v0.1.0` → `@v0.2.0`: dopo il merge il tick
trova la firma diversa e reinstalla da sé.

Mette in `.venv-asdlc/bin/` quattro comandi: `asdlc-runner`, `asdlc-coda`, `asdlc-esito`, il
server dell'esito, e `asdlc-chiudi-giro` (`PBI-385`, qui sotto). Ogni comando che il runner lancia o fa lanciare — il tick, la config MCP,
la guardia di fase della sessione del Builder, il `pre-commit` — è `<pacchetto>/bin/…` per
percorso assoluto, mai il nome nudo: il cron ha il `PATH` minimo.

**Dopo ogni merge il tick allinea il suo checkout e reinstalla da sé** (`PBI-392`). Il tick
decide da `origin/main`, ma il runner che lancia è quello installato dal `HEAD` del checkout:
col `ff-only` a mano, saltato due volte su due merge, il 01/10 il giro 2 di `PBI-386` è
partito col runner di prima (difetto 75 di `PBI-102`). Ora, col lucchetto del tick preso e
dopo la prima lettura della pausa, il tick fa `git fetch origin` e `git merge --ff-only
origin/main` nel checkout. Il checkout deve stare su `main`: se non ci sta, se il `fetch`
fallisce o se `git` rifiuta il `ff-only`, scrive `non allineato: <la ragione>` ed esce con 0
senza decidere — non fa `reset`, `stash` né `switch` sul checkout di una persona.

Poi confronta la firma scritta in `.venv-asdlc/.installato-da` con quella del pin di
`[ambiente].installa` a `HEAD` (`PBI-395`): `"./tools <albero>"`, con l'albero da `git
rev-parse HEAD:tools`, oppure il solo pin quando `installa` è un URL git. Se è diversa, o manca, e il lucchetto del runner è libero, lo
tiene per tutto `.venv-asdlc/bin/pip install --no-deps --force-reinstall ./tools`, scrive la
firma nuova e la riga `reinstallato: <firma>`, ed esce senza decidere: il processo che gira è ancora la
versione di prima, e decide il tick dopo. Con un giro in corso non reinstalla, e `decidi()`
dice `occupato`; con `pip` fallito scrive `reinstallazione fallita: <uscita di pip>`, lascia
la firma com'era e non lancia. Lo stesso se `git rev-parse` non trova la cartella del pin a
`HEAD`: la riga è `reinstallazione fallita: la cartella <cartella> non c'è a HEAD — <uscita
di git>`, e `pip` non parte (difetto 79 di `PBI-102`). In pausa il tick non tocca il checkout. Il `--dry-run` non
allinea e non reinstalla: fa il `fetch`, e scrive prima della decisione una riga `dry-run:`
se il checkout è indietro, se la firma non è quella del pin (nominando le due), o se la
cartella del pin manca a `HEAD`.

Il comando a mano resta solo come riparazione, quando il tick scrive `non allineato:` o
`reinstallazione fallita:` e la causa è stata tolta:

```bash
cd ~/ada_controller && git merge --ff-only origin/main && .venv-asdlc/bin/pip install --no-deps --force-reinstall <installa>
```

Il runner e il tick verificano l'ambiente **prima di partire**, e senza non lanciano:
«ambiente mancante», con tutte le mancanze e dove le hanno cercate. Il runner deve girare dal
venv del pacchetto, gli hook devono trovare `<pacchetto>/bin/asdlc-runner`, e gli
`[ambiente].eseguibili` si devono trovare nel venv dei gate o sul `PATH`, alla versione di
`[ambiente].minimi`. Il tick guarda anche gli `[ambiente].prestiti` nella radice del
worktree: uno che non c'è è `ambiente mancante: il prestito <voce> non c'è in <worktree>`
(`PBI-395`), invece di un test che cade nell'albero usa-e-getta senza ragione leggibile. Il
tick, se manca qualcosa, scrive la riga in `runs/coda.log` e non fa nemmeno il pre-flight.

La riga di `crontab` sta fuori dal repository. Su un PC nuovo è questa, con il checkout
principale al posto di `<checkout>`:

```
*/10 * * * * cd <checkout> && <checkout>/.venv-asdlc/bin/asdlc-coda >> runs/cron.log 2>&1
```

Su questo PC la riga di questo repository è quella qui sopra, **sfalsata di cinque minuti**
(`5-59/10`) per non partire insieme a quella di aDa, accesa l'08/10/2026 al passo 4.2 del
runbook della Fase 5 di aDa. Il paragrafo che c'era qui parlava di `~/asdlc-tick.sh`, che è
dello script di aDa e non riguarda questo repository.

**Il worktree del runner si prepara a mano, una volta per macchina.** Il tick lancia il
runner dentro `[worktree].percorso` (`../ada_asdlc-run`), e i gate ci girano col venv di
`[ambiente].venv` (`.venv`, relativo a quell'albero): sotto cron `pytest` non è sul `PATH`, e
senza quel venv il giro non parte. Né il tick né il runner creano l'albero o il venv. L'08/10
non c'erano, e li ha creati una persona prima del primo tick:

```bash
cd <checkout> && git worktree add --detach ../ada_asdlc-run origin/main
cd ../ada_asdlc-run && python3 -m venv .venv && .venv/bin/pip install pytest
```

*Controllo:* `.venv-asdlc/bin/asdlc-coda --dry-run` dal checkout, con il `PATH` del cron
(`env -i HOME=$HOME PATH=/usr/bin:/bin …`), risponde `lancia: PBI-…` o «in coda non resta
niente», e non `ambiente mancante`. Che il tick lo prepari da sé è un lavoro del pacchetto,
non ancora un PBI.

## Spegnere il tick e chiudere un giro fermato

**Il tick non si spegne nel crontab** (`PBI-385`). Cron lancia dalla tabella che ha caricato,
non dal file: fra la modifica e il `RELOAD` il tick lancia con la riga vecchia, e il 30/09 ha
lanciato 384 nove minuti dopo che la riga era stata commentata (difetto 69 di `PBI-102`). Il
tick si spegne con un **file di pausa**, `~/asdlc-tick.pausa`, che legge lui stesso a ogni
passaggio: prima di decidere, e di nuovo subito prima di lanciare. Con il file esce con 0 e
scrive in `runs/coda.log` `in pausa: <la riga del file>`; un file che c'è ma non si legge è
pausa lo stesso, e `--dry-run` la rispetta come un tick vero. La pausa vale per ogni tick
dell'utente su quella macchina, di qualsiasi progetto.

```bash
echo "$(date '+%F %H:%M') la ragione" > ~/asdlc-tick.pausa   # spento
rm ~/asdlc-tick.pausa                                          # riacceso
```

Un giro **fermato** — un ramo su `origin` senza PR, che tiene la coda in `attende` — si chiude
con un comando, dal checkout del tick:

```bash
cd ~/ada_controller && .venv-asdlc/bin/asdlc-chiudi-giro PBI-XXX --dry-run   # i passi, coi valori
cd ~/ada_controller && .venv-asdlc/bin/asdlc-chiudi-giro PBI-XXX
```

Erano sette comandi a mano, e l'ordine contava. Il comando ne fa sei, in quest'ordine:

1. pausa: il file creato, con la riga `<data ora> asdlc-chiudi-giro PBI-XXX`;
2. tag `giro-fermato/<pbi>-giro<N>-<data>` sulla testa del giro — `N` dal nome del ramo, la
   data dal run del rapporto;
3. push del tag;
4. cancellazione del ramo su `origin`;
5. `fetch` e `merge --ff-only origin/main` del checkout del tick;
6. pausa tolta.

La testa la prende dal rapporto del giro, il campo `testa` di `runs/<run>.json`: l'ultimo
rapporto dell'albero del runner che nomina il PBI, o quello scelto con `--run <id>`.
**Rifiuta prima di toccare qualsiasi cosa**, e dice quale condizione e con quali valori, se:
il lucchetto del tick è tenuto; il lucchetto del runner è tenuto (lo stesso controllo del tick); il rapporto non c'è o non ha
`testa`; su `origin` non c'è esattamente un ramo del PBI, o quello che c'è non punta a
`testa`; il tag c'è già su `origin`; `origin` non risponde.

Un passo che fallisce ferma quelli dopo: il comando toglie la pausa, nomina il passo, elenca
i comandi che restano da fare a mano ed esce diverso da 0. Se all'avvio la pausa c'era già,
il comando non la riscrive e non la toglie, e alla fine dice che il tick resta in pausa e da
quando. Il PBI lo rilancia il tick, al primo passaggio dopo la pausa tolta.

**La pausa messa per scrivere una ripresa si toglie solo con la PR della ripresa `MERGED`**,
e lo si controlla, non lo si deduce da quello che dice chi ha mergiato:

```bash
[ "$(gh pr view <n> --json state -q .state)" = MERGED ] && rm ~/asdlc-tick.pausa
```

L'08/10 la pausa è stata tolta mentre la PR della ripresa di `PBI-500` era ancora aperta: il
comando guardava solo che `gh` rispondesse. La pausa è stata rimessa prima del tick
successivo, e non è partito niente. Ma un tick in quella finestra avrebbe rilanciato il PBI
col testo di prima della ripresa, cioè lo stesso giro che si era appena fermato. E la pausa
vale per tutti i progetti della macchina (difetto 95 di `PBI-102`): mentre c'è, è ferma anche
la coda di aDa.

**Il tick e il comando si escludono con un lucchetto del tick** (`PBI-392`): un `flock` su
`runs/.tick.lock` del checkout, del processo e non del file, come quello del runner — il file
resta su disco, e un file che nessuno tiene non ferma niente. Il tick lo prende prima della
prima lettura della pausa e lo tiene fino alla fine, quindi anche per il pre-flight, l'avvio
del runner e l'attesa del distacco; il runner staccato non lo eredita, e un giro in corso
tiene il lucchetto del runner, non questo. `asdlc-chiudi-giro` lo prende prima di ogni
rifiuto e di ogni `git` e lo tiene per tutti i sei passi, anche quando uno fallisce; il
`--dry-run` non lo prende. Nessuno dei due aspetta: il tick che lo trova tenuto scrive
`occupato: il lucchetto del tick è tenuto — un altro tick o asdlc-chiudi-giro` ed esce con
0, il comando rifiuta e dice di riprovare fra un minuto. Così non c'è più la finestra di
`PBI-385` (la sua decisione 8, il difetto 70 di `PBI-102`), in cui il tick lanciava fra la
seconda lettura della pausa e il `flock` del runner senza tenere niente, e il comando
faceva i suoi passi accanto al lancio.

I rapporti dei giri di prima di `PBI-385` non hanno `testa`, e per quelli il comando
rifiuta: si chiudono a mano come prima, con il file di pausa al posto del crontab. Un giro
che ha aperto una PR si chiude chiudendo la PR.

## La regola che regge tutto

**Il gate non si indebolisce mai per far passare la catena.** Un test disattivato, uno
`skip` aggiunto, una tolleranza allargata: sono i tre modi in cui una pipeline autonoma
smette di misurare e comincia a produrre. Se il gate è rosso e l'agente non riesce a
chiuderlo in tre tentativi, il PBI non era pronto — e il tempo si spende lì, non nel
quarto tentativo.
