# Quanta autonomia dare all'agente, PBI per PBI

`asdlc-runner` esegue i PBI in sequenza con `claude -p`, un contesto pulito per PBI, e i
**gate eseguiti dallo script** — non dichiarati dall'agente. Ma l'autonomia non è una
proprietà dello strumento: è una proprietà del **gate**. Dove il gate sa dire da solo se il
lavoro è giusto, l'agente può correre; dove non lo sa, correre significa solo sbagliare prima.

## Il giro che fa il runner

```
                    ┌──────────── gate rossi ────────────┐
                    ↓                                    │
  PBI → [Builder]  →  Quality Gate      →  Review Gate  →  Acceptance Gate
        sessione     ① i gate di           [Critic]        la PR
        nuova,          asdlc.toml         sessione        ✋ umano
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
Il primo lo sa una macchina, il secondo un agente **che non ha scritto il codice**, il terzo
solo una persona. Un builder che rilegge il proprio lavoro nella stessa sessione conferma le
proprie premesse: è la ragione per cui il Critic è una sessione nuova, con un modello diverso
e senza permessi di scrittura.

**I gate, le soglie e i percorsi del runner stanno in `asdlc.toml`**: i comandi dei gate con
la loro cartella, il ramo di base, il prefisso dei rami, i modelli dell'id e del nome file dei
PBI, il registro, il venv, le soglie. Il file porta il **valore**; la ragione di ogni soglia
resta nel sorgente del pacchetto, accanto alla riga che la legge. Due cose valgono la pena di
sapere: un gate con `solo_se_tocca` gira solo se il diff del branch tocca uno di quei
percorsi (senza il campo è sempre acceso); e `[gate_del_rosso].attivo = false` spegne la
seconda domanda qui sotto **e lo dichiara** — a schermo, nel rapporto e nella nota di
`runs/tempi.csv` — per un progetto il cui runner di test il gate non sa leggere. Un gate che
si indebolisce in silenzio è la prima cosa che questa pagina vieta.

**Il Quality Gate ha due domande, non una.** La prima è *i test passano?*; la seconda è
*quei test sono mai stati rossi?*, e la sa una macchina come l'altra. Un test nato verde non
prova niente: può essere verde perché il codice è giusto, o perché non guarda niente. Il gate
cammina i commit dalla base in avanti e per ogni commit che introduce **test nuovi** lo
estrae in un worktree usa e getta e ci gira dentro **soltanto quei test**, aspettandosi il
rosso. Un commit che porta test nuovi *e* file di produzione insieme lo ferma senza eseguire
niente: il rosso non può essere esistito in mezzo a un commit solo, e basta il diff a dirlo.

L'esito si legge **test per test**, non dal totale del comando che li ha girati insieme. Un
`test(...) (RED)` porta quasi sempre più di un test, e il conteggio finale (`1 failed, 11
passed`) dice che *qualcosa* era rosso, non quale: in un commit che porta un test che morde e
uno nato verde, nell'elenco ci finisce il secondo.

**Un test nato verde passa se morde** (`ADR-0022`). «Nato verde» da solo ha un falso positivo
sistematico: la guardia che il Critic ordina su un comportamento che c'è già nasce verde per
forza. Prima di fermare, il gate muta le righe di produzione che il branch ha cambiato fino a
quel commit — cancella la riga, scambia `===`/`!==`, `&&`/`||`, `true`/`false`, `<`/`<=` — e
rigira **quel test** un mutante alla volta: se almeno uno lo fa fallire **per asserzione** il
test passa e il rapporto dice quale; se nessuno, ferma con «nato verde e non morde». Un
mutante che rompe la compilazione non conta: fa fallire tutto, non il test. Se il
comportamento vive in una funzione che il branch non tocca, il commit la nomina con una riga
`Guardia-su: <percorso>::<funzione>`, e il gate la aggiunge ai mutanti.

Ferma vuol dire **`fermato`, subito** — non un rilievo da mandare al Builder. Il ciclo
mancato è *ex ante* e nessuna fix lo annulla: il giro si chiude con l'elenco (commit, test,
esito) e la lettura la fa una persona. Il divieto in `AGENTS.md` da solo non ferma niente,
perché **una frase in un prompt non è un vincolo** — è un consiglio che l'agente pesa
insieme agli altri. I gate sono l'unica cosa che lega.

**Sulla strada del rimedio il rosso non è disponibile, e si dichiara invece di
fabbricarlo.** Quando il Critic dice *«questo criterio non ha un test che lo misura»*, il
codice che il rilievo riguarda è già committato: qualunque test il Builder scriva al giro
dopo nasce verde. **Il riordino dei commit non vale come rosso osservato**: `ADR-0021` chiede
il rosso prima, e un `git rebase` che riporta il test davanti al codice è il gesto che lo
fabbrica dopo. Il prompt del rimedio distingue il rilievo: se manca la **guardia** su codice
giusto, il test si committa da solo in `TEST_ONLY` senza `--chiedi-impl`, e il messaggio
dichiara che nasce verde — poi sono i mutanti di `ADR-0022` a dire se morde, e se non morde il
difetto è nel test; se invece il **codice è sbagliato**, il rosso c'è davvero e sono **due**
commit, `test (RED)` e `fix`. Il prompt chiede, il gate verifica: da solo nessuno dei due
basta.

Un gate che **non ha potuto guardare** non ferma niente: `pytest` fuori dal `PATH`, `npm`
senza `node_modules`, un comando che torna un codice che né pytest né vitest usano. Lì il
giro chiude `rosso` con la ragione vera e non accusa nessun commit — «il rosso non si è mai
visto» e «il gate non è partito» sono due diagnosi opposte, e la prima è la più grave che il
runner sappia emettere. A mano il gate torna `2` invece di `1`:

```bash
<checkout>/.venv-asdlc/bin/asdlc-runner --gate-rosso pbi/pbi-12            # il solo gate, su un branch
<checkout>/.venv-asdlc/bin/asdlc-runner --gate-rosso d2c084c..pbi/pbi-12   # o su un intervallo
```

**I commit li fa il Builder, la PR la apre lo script, il merge no.** Micro-commit durante il
lavoro, una coppia RED→GREEN per criterio, ognuno un punto di ripristino: un commit unico
finale non ripristina niente. Nessun squash prima della validazione; al confine del merge ci
pensa la PR, ed è lì che la responsabilità torna umana
(`.claude/skills/asdlc/practices/micro-commits.md` §5).

Il runner controlla anche **l'igiene**: se dopo un giro restano modifiche non committate,
rimanda l'agente a committarle — ciò che non è committato non esiste, non si giudica e non si
ripristina.

L'esito di un agente il runner non lo legge dal testo della risposta, ma dalla **chiamata a
strumento** con cui l'agente lo dichiara (`ADR-0027`): a ogni invocazione di Builder e Critic
genera in `runs/` una config MCP che accende il server dell'esito con due strumenti, `fatto` e
`fermati`, e il file in cui il server scrive la prima chiamata valida. `fatto` del Builder
porta il riepilogo, quello del Critic il verdetto — `pass` o `non pronto` — e il rapporto;
`fermati` porta la domanda, intera. Un agente che non chiama nessuno dei due chiude il giro
**`senza esito`**, senza igiene e senza gate: stdout, stderr e codice d'uscita di `claude -p`
restano accanto al file d'esito, e il rapporto del giro ne porta i percorsi.

Le tre categorie qui sotto le separa sempre lo stesso criterio: **cosa deciderebbe la
differenza fra giusto e sbagliato, e chi ce l'ha in mano.**

## 🟢 Autonomi — il gate decide da solo

[I PBI il cui esito è **aritmetico o strutturale**: il golden test coincide o no, la rotta
risponde o dà 500, il 403 arriva o no. Qui il ciclo `agente → gate → correggi` converge, e
l'umano interviene alla PR. Un PBI per riga, con la frase che dice perché sta qui.]

## 🟡 Assistiti — l'agente scrive, l'umano guarda prima del merge

[I PBI in cui il gate dice se **funziona**, non se è **giusto**: una vista può passare tutti i
test ed essere illeggibile. Si fanno girare col runner, ma il diff si legge prima del merge:
è l'Acceptance Gate, e non è delegabile allo strumento che ha prodotto il lavoro.]

## 🔴 Non automatizzabili — manca un pezzo che nessun agente può procurarsi

[I PBI a cui manca un dato, una misura, una chiave o un giudizio che solo una persona può
dare: il runner serve comunque, in `--dry-run`, per vedere il prompt, ma il PBI si apre solo
quando il pezzo mancante è arrivato. Il PBI stesso lo dice, nelle Dipendenze e nel
Protocollo di rifinitura.]

## Quanto tempo ci mette — e quindi quanto costa

Ogni esecuzione appende una riga per PBI in **`runs/tempi.csv`**:

```
run · pbi · stato · iniziato · finito · durata_s · durata_hms
     builder_s · gate_s · critic_s · tentativi · revisioni · commit · pr · nota
```

```bash
<checkout>/.venv-asdlc/bin/asdlc-runner --riepilogo --tariffa 90
```

Quattro cose da sapere prima di mettere quel numero in fattura:

- **`durata` è tempo di parete, tentativi falliti compresi.** Un PBI rimasto rosso dopo tre
  giri ha una sua riga con `stato=rosso`: quel tempo è stato speso davvero, e toglierlo dal
  conto renderebbe il totale più bello e meno vero.
- **La colonna è scomposta apposta.** `agente` (builder + critic) è il tempo in cui lavora il
  modello; `gate` è tempo di macchina — pytest, build, Playwright — che scorrerebbe identico
  con un ingegnere umano al posto dell'agente.
- **Rieseguire un PBI aggiunge una riga, non la sostituisce.** Il totale di progetto è la
  somma di tutte le righe, che è la domanda giusta: quanto è costato arrivarci, non quanto
  sarebbe costato sapendolo già.
- **Non c'è dentro il tempo umano** — leggere la PR, rispondere alle domande degli agenti,
  decidere. È la parte che decide se il lavoro è giusto, e va contata a parte: questo CSV
  misura la macchina, non il progetto.

`runs/tempi.csv` è **versionato** (è il registro della fatturazione, poche righe); il resto
di `runs/` no: contiene i rapporti del Critic e cresce (`.gitignore`).

⚠️ **Il giro non scrive il CSV** (`ADR-0020`): scriverlo dal branch fa uscire la PR
`CONFLICTING` su un file che il PBI non ha toccato. Il giro lascia il suo rapporto,
`runs/<run>.json`, e le righe entrano in `main` **dopo il merge**, da lì:

```bash
<checkout>/.venv-asdlc/bin/asdlc-runner --registra <worktree>/runs   # idempotente su (run, pbi)
git add runs/tempi.csv    # e una PR `chore(ci): registra i giri`
```

## Il runner installato

Il runner e il tick sono il pacchetto `asdlc`, e si **installano**: il runner che lavora è
quello installato, mai una copia di lavoro (`ADR-0026`, decisione 3). Il venv è dedicato,
`.venv-asdlc` nella radice comune del repository — il checkout principale, lo stesso da ogni
worktree — ed è `asdlc.toml` a dichiararlo, `[ambiente].pacchetto`. L'installazione è **non
editabile**:

```bash
cd <checkout>
python3 -m venv .venv-asdlc
.venv-asdlc/bin/pip install --no-deps --force-reinstall "<installa>"
```

**Da dove si installa lo dice `asdlc.toml`, `[ambiente].installa`**: la stringa che si passa
a `pip install`. Due forme sole: una **cartella** relativa alla radice del progetto, oppure
un **URL git pinnato a un tag**, `git+ssh://…@v<maggiore>.<minore>.<patch>[#subdirectory=…]`.
Un URL senza `@v…`, su un ramo, o un percorso assoluto o con `~` sono un errore di
caricamento che nomina la chiave (`ADR-0026` pinna a un tag, mai a un ramo). La chiave è
obbligatoria quando c'è `[ambiente].pacchetto`, e sta solo in `asdlc.toml`: in
`asdlc.local.toml` è rifiutata, perché il pin è del progetto e una macchina con un pin suo
girerebbe una versione che nessun altro ha. **Salire di tag è una PR che cambia il pin**,
`@v0.1.0` → `@v0.2.0`: dopo il merge il tick trova la firma diversa e reinstalla da sé.

Mette in `.venv-asdlc/bin/` quattro comandi: `asdlc-runner`, `asdlc-coda` (il tick),
`asdlc-esito` (il server dell'esito) e `asdlc-chiudi-giro` (qui sotto). Ogni comando che il
runner lancia o fa lanciare — il tick, la config MCP, la guardia di fase della sessione del
Builder, il `pre-commit` — è `<pacchetto>/bin/…` per percorso assoluto, mai il nome nudo: il
cron ha il `PATH` minimo. Lanciato come script dalla copia di lavoro, il runner esce con
«ambiente mancante».

A mano, un PBI si lancia dal worktree del runner, `[worktree].percorso`, e non dal checkout
principale, che resta su `main`:

```bash
cd <worktree> && git fetch -q origin && git switch -q --detach origin/main
<checkout>/.venv-asdlc/bin/asdlc-runner PBI-12
<checkout>/.venv-asdlc/bin/asdlc-runner PBI-12 --no-pr           # solo il branch locale
<checkout>/.venv-asdlc/bin/asdlc-runner PBI-12 PBI-13 PBI-15     # una tratta, in sequenza
```

Il runner si **stacca da sé** e scrive in `runs/<run>.log`, accanto al rapporto
`runs/<run>.json`; `--in-primo-piano` chiede il contrario. Si **ferma** al primo PBI rosso,
respinto dal Critic, fermato o senza esito, e non prosegue: i PBI hanno dipendenze
dichiarate, e costruire su una base rossa costa più di quanto risparmia. Se un agente si
ferma con una domanda, quella domanda è il prodotto della sessione — va nella spec o
nell'ADR, non buttata riprovando con lo stesso prompt.

**Dopo ogni merge il tick allinea il suo checkout e reinstalla da sé.** Il tick decide da
`origin/main`, ma il runner che lancia è quello installato dal `HEAD` del checkout: col
lucchetto del tick preso e dopo la prima lettura della pausa, fa `git fetch origin` e
`git merge --ff-only origin/main` nel checkout. Il checkout deve stare su `main`: se non ci
sta, se il `fetch` fallisce o se `git` rifiuta il `ff-only`, scrive `non allineato: <la
ragione>` ed esce con 0 senza decidere — non fa `reset`, `stash` né `switch` sul checkout di
una persona.

Poi confronta la firma scritta in `.venv-asdlc/.installato-da` con quella del pin di
`[ambiente].installa` a `HEAD`. Se è diversa, o manca, e il lucchetto del runner è libero, lo
tiene per tutto `pip install`, scrive la firma nuova e la riga `reinstallato: <firma>`, ed
esce senza decidere: il processo che gira è ancora la versione di prima, e decide il tick
dopo. Con un giro in corso non reinstalla, e la decisione è `occupato`; con `pip` fallito
scrive `reinstallazione fallita: <uscita di pip>`, lascia la firma com'era e non lancia. In
pausa il tick non tocca il checkout. Il `--dry-run` non allinea e non reinstalla: fa il
`fetch`, e scrive prima della decisione una riga `dry-run:` se il checkout è indietro o se la
firma non è quella del pin.

Il comando a mano resta solo come riparazione, quando il tick scrive `non allineato:` o
`reinstallazione fallita:` e la causa è stata tolta:

```bash
cd <checkout> && git merge --ff-only origin/main && .venv-asdlc/bin/pip install --no-deps --force-reinstall "<installa>"
```

Il runner e il tick verificano l'ambiente **prima di partire**, e senza non lanciano:
«ambiente mancante», con tutte le mancanze e dove le hanno cercate. Il runner deve girare dal
venv del pacchetto, gli hook devono trovare `<pacchetto>/bin/asdlc-runner`, e gli
`[ambiente].eseguibili` si devono trovare nel venv dei gate o sul `PATH`, alla versione di
`[ambiente].minimi`. Il tick guarda anche gli `[ambiente].prestiti` nella radice del
worktree. Se manca qualcosa, scrive la riga in `runs/coda.log` e non fa nemmeno il
pre-flight.

La riga di `crontab` sta fuori dal repository. Su un PC nuovo è questa, con il checkout
principale al posto di `<checkout>`, ed è il solo gesto di installazione del tick:

```
*/10 * * * * cd <checkout> && <checkout>/.venv-asdlc/bin/asdlc-coda >> runs/cron.log 2>&1
```

## Spegnere il tick e chiudere un giro fermato

**Il tick non si spegne nel crontab.** Cron lancia dalla tabella che ha caricato, non dal
file: fra la modifica e il `RELOAD` il tick lancia con la riga vecchia. Il tick si spegne con
un **file di pausa**, `asdlc-tick.pausa` nella home dell'utente, che legge lui stesso a ogni
passaggio: prima di decidere, e di nuovo subito prima di lanciare. Con il file esce con 0 e
scrive in `runs/coda.log` `in pausa: <la riga del file>`; un file che c'è ma non si legge è
pausa lo stesso, e `--dry-run` la rispetta come un tick vero. La pausa vale per ogni tick
dell'utente su quella macchina, di qualsiasi progetto.

```bash
echo "$(date '+%F %H:%M') la ragione" > "$HOME/asdlc-tick.pausa"   # spento
rm "$HOME/asdlc-tick.pausa"                                          # riacceso
```

Un giro **fermato** — un ramo su `origin` senza PR, che tiene la coda in `attende` — si chiude
con un comando, dal checkout del tick:

```bash
cd <checkout> && .venv-asdlc/bin/asdlc-chiudi-giro PBI-12 --dry-run   # i passi, coi valori
cd <checkout> && .venv-asdlc/bin/asdlc-chiudi-giro PBI-12
```

Il comando fa sei passi, in quest'ordine:

1. pausa: il file creato, con la riga `<data ora> asdlc-chiudi-giro PBI-12`;
2. tag `giro-fermato/<pbi>-giro<N>-<data>` sulla testa del giro — `N` dal nome del ramo, la
   data dal run del rapporto;
3. push del tag;
4. cancellazione del ramo su `origin`;
5. `fetch` e `merge --ff-only origin/main` del checkout del tick;
6. pausa tolta.

La testa la prende dal rapporto del giro, il campo `testa` di `runs/<run>.json`: l'ultimo
rapporto dell'albero del runner che nomina il PBI, o quello scelto con `--run <id>`.
**Rifiuta prima di toccare qualsiasi cosa**, e dice quale condizione e con quali valori, se:
il lucchetto del tick è tenuto; il lucchetto del runner è tenuto; il rapporto non c'è o non
ha `testa`; su `origin` non c'è esattamente un ramo del PBI, o quello che c'è non punta a
`testa`; il tag c'è già su `origin`; `origin` non risponde.

Un passo che fallisce ferma quelli dopo: il comando toglie la pausa, nomina il passo, elenca
i comandi che restano da fare a mano ed esce diverso da 0. Se all'avvio la pausa c'era già,
il comando non la riscrive e non la toglie, e alla fine dice che il tick resta in pausa e da
quando. Il PBI lo rilancia il tick, al primo passaggio dopo la pausa tolta. Un giro che ha
aperto una PR si chiude chiudendo la PR.

**Il tick e il comando si escludono con un lucchetto del tick**: un `flock` su
`runs/.tick.lock` del checkout, del processo e non del file, come quello del runner — il file
resta su disco, e un file che nessuno tiene non ferma niente. Il tick lo prende prima della
prima lettura della pausa e lo tiene fino alla fine; `asdlc-chiudi-giro` lo prende prima di
ogni rifiuto e di ogni `git` e lo tiene per tutti i sei passi. Nessuno dei due aspetta: il
tick che lo trova tenuto scrive `occupato: il lucchetto del tick è tenuto` ed esce con 0, il
comando rifiuta e dice di riprovare fra un minuto.

## La regola che regge tutto

**Il gate non si indebolisce mai per far passare la catena.** Un test disattivato, uno
`skip` aggiunto, una tolleranza allargata: sono i tre modi in cui una pipeline autonoma
smette di misurare e comincia a produrre. Se il gate è rosso e l'agente non riesce a
chiuderlo in tre tentativi, il PBI non era pronto — e il tempo si spende lì, non nel quarto
tentativo.
