# asdlc

Il runner ASDLC come pacchetto Python: fa girare i PBI di un progetto uno per volta con
`claude -p`, un contesto pulito per PBI, i **gate eseguiti dallo script** e il permesso di
scrivere produzione dato dal rosso osservato. Comandi installati:

| Comando | Cosa fa |
|---|---|
| `asdlc-runner` | un giro su un PBI, la guardia di fase (`--guardia-fase`) per l'hook `PreToolUse`, e la pre-verifica di un PBI prima della coda (`PBI-N --preverifica`: rapporto in `runs/<run>-<PBI>-preverifica.json`, esce 1 con un rilievo di forma, gli avvisi non contano; `PBI-520`; con `--lettore` legge anche il Lettore, `PBI-521`) |
| `asdlc-coda` | il tick: legge `backlog/CODA.md` e lancia il PBI successivo quando il precedente è in `main` |
| `asdlc-chiudi-giro` | chiude un giro fermato: tag `giro-fermato/…`, ramo tolto |
| `asdlc-stato` | lo stato dei PBI, in sola lettura: per un progetto, ciò che il tick deciderebbe adesso (`PBI-534`, *Lo stato a comando*) |
| `asdlc-esito` | il server MCP dell'esito, da cui gli agenti dichiarano com'è andata (`ADR-0027`) |

## Da dove viene

Estratto da [aDa Controller](https://github.com/Lara-srl/ada_controller) al commit
**`683e2dd79d4a53fd39904b8e3e4bba66b5e47236`** (il commit `E` del runbook della Fase 5),
con `git filter-repo` e la storia dei nomi di prima dei traslochi: i messaggi dei commit
sono la documentazione dei difetti, e `backlog/PBI-102-…` è il loro registro.

## Come si usa in un progetto nuovo

Il runner non si scarica: ogni progetto lo installa da un tag git (`ADR-0026`). Di questo
repository un progetto nuovo prende solo `template/`.

**Prerequisiti:** `git`, `gh` (autenticato), la CLI `claude`, e l'accesso SSH a questo
repository, perché l'installazione usa `git+ssh`.

1. **Crea il repo del progetto** su GitHub e clonalo.
2. **Copia il template**, dotfile compresi (`.claude`, `.github`, `.gitignore`):
   ```
   cp -a /percorso/di/ada_asdlc/template/. /percorso/del/progetto/
   ```
   `template/ZERO.md` elenca cosa si copia e cosa no, per chi adotta il metodo senza runner.
3. **Adatta due file.**
   - `AGENTS.md`: scrivi `## Dominio` (cos'è il progetto, toolchain, scope dei commit);
     `## Metodo` resta identica.
   - `asdlc.toml`: il pin, il percorso del worktree e i gate.
     ```toml
     [ambiente]
     venv = ".venv"               # i gate lanciano da qui pytest e simili
     pacchetto = ".venv-asdlc"    # qui vive il runner
     installa = "git+ssh://git@github.com/Lara-srl/ada_asdlc@v0.2.0#subdirectory=tools"

     [worktree]
     percorso = "../mio-progetto-run"   # accanto al checkout principale

     [[gate]]
     nome = "test"
     comando = ["python3", "-m", "pytest", "-q"]
     cwd = "."
     ```
   Il pin è sempre un tag, mai un ramo. Salire di versione è una PR che cambia quella riga,
   e il tick reinstalla da solo quando la riga cambia.
4. **Crea i due venv** nel checkout principale: `.venv` con gli strumenti dei gate (per
   esempio `pytest`) e `.venv-asdlc` con il runner:
   ```
   python3 -m venv .venv && .venv/bin/pip install pytest
   python3 -m venv .venv-asdlc
   .venv-asdlc/bin/pip install --no-deps "git+ssh://git@github.com/Lara-srl/ada_asdlc@v0.2.0#subdirectory=tools"
   ```
5. **Scrivi un PBI.** Parti da `backlog/TEMPLATE.md`, salva in `backlog/PBI-001-<slug>.md`,
   aggiungi la riga `- PBI-001` a `backlog/CODA.md` e mergia con una PR. Mettere un PBI in
   coda è dichiarare che le sue domande sono chiuse: il tick non lo ricontrolla.
6. **Accendi il tick** con una riga di cron, sfalsata di qualche minuto dagli altri
   progetti (la riga di riferimento è in [`backlog/AUTOMAZIONE.md`](backlog/AUTOMAZIONE.md)):
   ```
   2-59/10 * * * * cd /percorso/del/progetto && .venv-asdlc/bin/asdlc-coda >> runs/cron.log 2>&1
   ```

### Cosa succede dopo

1. Il tick legge `backlog/CODA.md` e lancia `asdlc-runner` sul primo PBI quando il
   precedente è in `main`.
2. Il **Builder** (sessione `claude -p` pulita) scrive a micro-commit, una coppia
   RED→GREEN per criterio.
3. Il **Quality Gate** esegue lo script, non l'agente: i gate di `asdlc.toml` e la verifica
   che i test nuovi siano mai stati rossi.
4. Il **Critic** (sessione separata, sola lettura) rilegge il lavoro.
5. Si apre una PR. Il tick la mergia da solo se passa le condizioni di `ADR-0033`
   (rapporto `fatto` col Critic, CI verde, criteri spuntati, file dentro lo Scope); altrimenti
   **il merge è tuo**, e il log dice quale condizione manca. Dello Scope contano i file in
   testa alle voci, anche in radice (`README.md`), e quelli con una `/`, fino alla voce
   «Fuori scope», esclusa.
6. La voce in coda si spegne quando una PR mergiata nomina il PBI e tocca file fuori da
   `backlog/`.

Se una domanda si apre a giro iniziato, il Builder chiama `fermati` e la coda si blocca da
sé. Un giro fermato si chiude con `asdlc-chiudi-giro`, che mette il tag `giro-fermato/…` e
toglie il ramo. Il rapporto e i log dei giri stanno in `runs/`.

### Il Solver, il terzo ruolo

Dopo un giro fermato — il `fermati` del Builder, una domanda bloccante del Critic, un agente
`senza esito` — il runner lancia il **Solver** (sola lettura: `Read`, `Grep`, `Glob`). Non lo
lancia su un `senza esito` per il limite d'uso dell'account con l'ora del reset leggibile
(`riprendi_dopo` nel rapporto): lì non c'è niente da decidere, e dopo il reset il tick
riprende il PBI con `asdlc-runner PBI-N --riprendi` (`PBI-519`). Smista il blocco con uno di tre strumenti, che il server dell'esito valida:

- `risolvi(risposta, evidenza)` — `evidenza` è un file dell'albero, `percorso` o
  `percorso:riga`;
- `segnala_limite_runner(causa, comando, output, commit)` — la `causa` è una di
  `[solver].cause`, `commit` esiste, `comando` e `output` non sono vuoti;
- `chiedi_a_francesco(domanda)` — l'esito `intento`.

Il Solver legge `asdlc.toml` prima di segnalare un limite e `backlog/PRECEDENTI.md` prima di
chiedere. Il tetto è `[solver].giri_massimi` (3) giri per PBI, contati nel rapporto
`runs/<run>.json` (`giri_solver`): oltre, o a `chiedi_a_francesco`, il giro si ferma con un
avviso nella nota. Il modello è `[solver].modello` (`opus`). Dopo un `fermati` del Builder il
Solver parte dentro il giro, e con `risolto` il Builder riprende nello stesso giro (`PBI-517`,
quante volte lo dice `riprese_solver` nel rapporto);
gli altri blocchi il Solver li smista alla chiusura, senza riprese. A `segnala_limite_runner` (che porta anche `pbi`, il testo
del PBI a monte scritto dal Solver) apre un ramo su un fork di `asdlc` e una PR da lì verso
`main` (mai una scrittura su `main`), col PBI numerato al successivo libero di `backlog/` del
clone `[rilascio].clone` (senza la chiave la PR non si apre e il Solver riceve l'errore); con la
stessa causa già in un PBI o in una PR aperta non ne apre un'altra. Poi scrive nel PBI fermo
`attende: <repo>#<PBI>`, la committa sul ramo del PBI fermo e crea `~/asdlc-tick.pausa`
(`PBI-512`).

```toml
[solver]
giri_massimi = 3
cause = ["runner-non-legge-junit"]   # allineate a backlog/README.md di asdlc
modello = "opus"
```

### Il Lettore, il quarto ruolo

`asdlc-runner PBI-N --preverifica --lettore` aggiunge al controllo di `PBI-520` il
**Lettore** (`PBI-521`, `ADR-0031`): un agente che legge il PBI contro la base e risponde alle
sette domande (`R F T A E D N`). Lavora in un albero usa e getta alla base, fuori dal
checkout, con `Read`, `Grep`, `Glob`, `Write` ed `Edit` e senza `Bash`; l'albero si smonta
comunque vada. Dichiara ciò che trova con tre strumenti, che il server dell'esito valida:

- `rilievo(domanda, criterio, testo, evidenza)` — solo ciò che fermerebbe il giro, con la
  prova: `evidenza` è un file dell'albero, `percorso` o `percorso:riga`;
- `sonda(criterio, file, nome)` — il test RED di un criterio, scritto nell'albero;
- `letto(riepilogo)` — chiude la lettura.

Dopo `letto` il **runner** esegue le sonde sulla base con gli strumenti di `--chiedi-impl`:
una sonda che non è rossa diventa un rilievo `R` col testo di quel rifiuto («nato verde»;
`nessuno` per un file che non è un test o un nome che il file non ha), mentre un gate guasto è
l'avviso `sonda del criterio N: gate guasto` e la sonda ha esito `guasto`. Un
criterio senza sonda è un avviso, `criterio N senza sonda`, non un rilievo; un criterio che
si dichiara guardia (il suo testo dice «guardia» o «nato verde») non ha sonda né avviso. Il
rapporto aggiunge `lettore` (`letto`, `senza esito`, oppure `null` senza `--lettore`) e
`sonde` (criterio, file, nome, esito); i rilievi del Lettore e delle sonde stanno nella stessa
lista `rilievi`. Il modello e il tetto della chiamata stanno nella sezione `[lettore]`:

```toml
[lettore]
modello = "opus"   # il default, come [solver]
minuti = 30        # il tetto della chiamata del Lettore
```

Senza `letto` la lettura è `senza esito`: i rilievi già registrati entrano
nel rapporto marcati `"lettore": "senza esito"`, e le sonde non si eseguono. Il comando esce 1
con un rilievo, oppure con `senza esito`.

### La pre-verifica nel giro

Con `[preverifica] attiva = true` la pre-verifica gira anche dentro il giro (`PBI-522`,
`ADR-0031` decisione 4): dopo il controllo dell'albero pulito, e prima dell'inventario e del
ramo, sul PBI alla base. Scrive lo stesso rapporto di `--preverifica`,
`runs/<run>-<PBI>-preverifica.json`, e con `lettore` (il default) legge anche il Lettore,
prima del Builder. Con almeno un rilievo, del codice, del Lettore o delle sue sonde, il giro
chiude `fermato` col motivo `preverifica`, e la nota dice quanti rilievi e dove sta il
rapporto: non nascono ramo, commit né PR, e il Solver non parte. L'esito porta `sha_pbi`, lo sha del blob del file del PBI letto,
e `rilievi_preverifica`. Un Lettore che non chiama `letto`, per un tetto scaduto o per il
limite d'uso, chiude invece `senza esito` col motivo `lettore-senza-esito`, anche coi rilievi
accumulati: non è un PBI da correggere, il Solver non parte e, col limite d'uso e l'ora del
reset leggibile, l'esito porta `riprendi_dopo` come il Builder (`PBI-519`): il tick aspetta
quell'ora e poi rilancia il PBI. Senza rilievi il giro va avanti come prima. La lettura si
paga una volta per versione del PBI: se fra i rapporti `runs/*-<PBI>-preverifica.json` ce n'è
uno con lo stesso `sha_pbi`, senza rilievi e, col Lettore, con `lettore` uguale a `letto`, il
giro non la rifà e prosegue. Il tick non rilancia un PBI fermo col motivo `preverifica` finché
il suo file non cambia su `main`, e intanto scrive `attende: preverifica PBI-N — <n> rilievi,
correggi il PBI`. `--riprendi` non la
rifà. Senza la sezione la pre-verifica è spenta.

**I guasti del Lettore** (`PBI-523`). La pre-verifica gira prima dell'inventario d'inizio
del giro, ma dopo che il giro ha fotografato il conto degli alberi usa e getta. Nel caso
normale non cambia niente: il Lettore lavora nel suo albero, che si smonta, e il rapporto sta
in `runs/`. Un suo albero che `git worktree remove` non smonta compare fra i «residui dei giri
prima» nel log, ed entra anche nel conto: la nota del giro dice «1 albero usa e getta montato
e non smontato». Un file che il Lettore scrivesse nel worktree del giro arriva dopo il
primo controllo dell'albero pulito: per questo, quando la pre-verifica ha girato, il giro
ricontrolla l'albero dopo la lettura, e con l'albero sporco chiude `fermato` col motivo
`albero-sporco-all-ingresso`, senza Builder, ramo, commit, PR né Solver. Il rapporto della
lettura resta, e al giro dopo la stessa versione del PBI letta pronta non si rilegge.

```toml
[preverifica]
attiva = true    # il default è false
lettore = true   # il default
```

### Il rilascio a tick

Dopo il merge di un PBI a monte, due passi del tick sostituiscono i cinque gesti a mano
(`specs/solver-e-rilascio/spec.md`, R8-R11). Il merge delle PR dei giri che passano
le condizioni di `ADR-0033` è del tick, che lo fa prima del rilascio; `rilascia()` e `pin()`
non emettono mai `gh pr merge`.

- **In `asdlc`:** per ogni PR di PBI mergiata il cui PBI dichiara `rilascia: patch|minor|major`
  (una riga sotto il titolo), con la CI di `main` verde e il merge non ancora in un tag, il
  tick mette il tag successivo (`v0.3.0` → `v0.3.1` con `patch`, `v0.4.0` con `minor`, `v1.0.0` con `major`).
  `--registra` e il tag girano in un worktree usa-e-getta fuori dal checkout, che resta pulito.
- **Nel progetto:** per ogni PBI fermo (ramo su `origin`, nessun merge) con
  `attende: <repo>#<PBI>` (letta anche dai rami `pbi/*` su `origin` non ancora in `main`, nei soli file di `backlog/` che il ramo cambia, non solo da `main`), a PR a monte `MERGED` (`gh pr view`) e tag che la contiene il tick
  apre la PR che cambia solo `[ambiente].installa`; a PR del pin `MERGED` toglie
  `~/asdlc-tick.pausa`. Il pin gira anche con il tick in pausa, il rilascio no.

```toml
[rilascio]
remote_fork = "fork"   # il remote del fork di asdlc da cui il Solver apre la PR a monte
clone = "/percorso/di/asdlc"   # la copia di asdlc su disco; senza, la PR a monte non si apre
prefisso_tag = "v"
```

Un progetto che parte senza runner (il «livello zero») e sale a `mvp` con un ADR segue
`template/ZERO.md`.

### La pausa del tick, globale e del progetto

Il tick si ferma con due file di pausa, che si sommano: basta uno dei due (`PBI-535`).

- **La pausa globale**, `~/asdlc-tick.pausa`, ferma il tick di **tutti** i progetti della
  macchina: la mettono `asdlc-chiudi-giro` e il runner che aspetta un PBI a monte, la toglie
  il pin a PR `MERGED` o `asdlc-chiudi-giro`.
- **La pausa del progetto**, `<[registro].cartella>/pausa` nel checkout (`runs/pausa`),
  ferma solo il tick di quel progetto; gli altri lavorano. Si mette e si toglie con
  `asdlc-coda`, dal checkout del progetto, senza scrivere il file a mano:

  ```bash
  cd /percorso/del/progetto
  .venv-asdlc/bin/asdlc-coda --pausa "chiudo a mano il giro di PBI-7"
  .venv-asdlc/bin/asdlc-coda --togli-pausa
  ```

  Il file è una riga: data, ora e motivo; a capo e spazi in fila nel motivo diventano uno
  spazio solo. I due flag non fanno altro: non decidono e non lanciano. `--togli-pausa` senza file esce
  0, e non tocca mai la pausa globale. Prendono il lucchetto del tick, come
  `asdlc-chiudi-giro`: con un tick in corso escono 2 e il file non cambia.

Il tick in pausa scrive in `runs/coda.log` `in pausa: <riga>` per la globale e
`in pausa: (progetto) <riga>` per quella del progetto; con tutte e due, una riga sola, la
globale. Lo stesso testo va nell'evento `pausa` su Slack e in `asdlc-stato`.

### Il battito del tick e il recupero dopo lo spegnimento

Il tick è un cron su un PC: se il PC si spegne o si sospende, la coda si ferma in silenzio
(`PBI-510`, `ADR-0030` decisione 5). **Il limite resta: il PC spento ferma la coda**, che
riprende da sola alla ripartenza.

- **Il battito:** a ogni passaggio — anche in pausa, anche a coda finita — il tick scrive
  l'ora in ISO su una riga in `~/asdlc-tick.battito`, accanto a `~/asdlc-tick.pausa`. Al
  passaggio dopo legge il battito precedente: se il distacco supera
  `[tick].soglia_battito_minuti` (default 30) scrive un avviso a schermo e in `runs/coda.log`,
  poi prosegue (`ADR-0008`: avviso, non blocco). Un file che manca è «mai partito», non un
  avviso. L'avviso resta nel log: un canale fuori dal log (mail, notifica) è un altro PBI.
- **Il recupero:** un timer di systemd (utente) rilancia il tick all'avvio e a ogni ora piena
  mancata durante lo spegnimento, senza aspettare il passaggio del cron. È una ricetta che si
  installa a mano, come il crontab: il codice non la installa.

```toml
[tick]
soglia_battito_minuti = 30
```

`~/.config/systemd/user/asdlc-tick.service`:

```ini
[Unit]
Description=Un passaggio del tick ASDLC

[Service]
Type=oneshot
WorkingDirectory=/percorso/del/progetto
ExecStart=/percorso/del/progetto/.venv-asdlc/bin/asdlc-coda
```

`~/.config/systemd/user/asdlc-tick.timer`:

```ini
[Unit]
Description=Recupera il tick ASDLC dopo lo spegnimento

[Timer]
OnBootSec=2min
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload && systemctl --user enable --now asdlc-tick.timer
```

Il lucchetto del tick rende innocuo il doppio passaggio con il cron: il secondo scrive
`occupato:` e esce.

### Le notifiche del tick su Slack

Il tick manda un messaggio su Slack quando la sua decisione **cambia** verso uno stato che
chiede una persona, o che una persona vuole sapere (`PBI-533`). Un messaggio per cambio, non
uno ogni dieci minuti: l'ultimo evento mandato sta in `runs/notifiche.json` del checkout, e
lo stesso evento — stesso tipo, stesso PBI, stesso motivo — non si rimanda. Il messaggio porta
il nome del progetto, cioè la cartella del checkout (`ada_nlt`, `ada_asdlc`, …).

| Evento | Quando |
|---|---|
| `fermo` | un PBI col ramo e senza PR, col motivo e la domanda del rapporto; o fermo in pre-verifica |
| `non-lanciato` | il lancio dello stesso PBI non parte per due tick di fila |
| `pronto` | una PR che il tick non mergia e aspetta una persona, con la condizione che manca |
| `rilascio` | il tick taglia un tag |
| `barriera` | una barriera scritta in `CODA.md` |
| `finita` | la coda è finita |
| `guasto` | il tick non riesce a decidere (`gh` che non risponde, la coda che non si legge) per tre tick di fila |
| `non-allineato` | il checkout del tick non è su `main` o non si allinea |
| `reinstallazione` | la reinstallazione del pacchetto è fallita |
| `pausa` | il tick è in pausa, con la riga del file di pausa: la globale, o `(progetto) <riga>` per la sola pausa del progetto |

**Il webhook, una volta per macchina:**

1. Su <https://api.slack.com/apps> si crea un'app (*From scratch*) nello spazio di lavoro, si
   apre *Incoming Webhooks*, si accende e si fa *Add New Webhook to Workspace* sul canale
   scelto. Slack dà un URL `https://hooks.slack.com/services/…`.
2. L'URL è un segreto, e va in un file fuori dai repository, letto da tutti i progetti della
   macchina:

   ```bash
   mkdir -p ~/.config/asdlc
   printf '%s\n' 'https://hooks.slack.com/services/…' > ~/.config/asdlc/slack-webhook
   chmod 600 ~/.config/asdlc/slack-webhook
   ```

   Non sta in `asdlc.toml`, che è versionato e non porta percorsi di macchina.

**In ogni progetto,** in `asdlc.toml`:

```toml
[notifiche]
attive = true
eventi = ["fermo", "non-lanciato", "pronto", "rilascio", "barriera", "finita", "guasto",
          "non-allineato", "reinstallazione", "pausa"]
```

`eventi` sceglie quali mandare; senza la chiave, tutti. Senza la sezione, o con
`attive = false`, il tick non manda niente e non lo dice. Il template la porta spenta.
Una chiave diversa da `attive` ed `eventi` (un `attiva = true`, per dire) è un errore
che la nomina, come in ogni altra sezione: un refuso non spegne le notifiche in silenzio.
Lo stesso vale per un nome in `eventi` che non è uno dei dieci qui sopra (`"non_lanciato"`,
`"fermi"`): l'errore lo nomina invece di lasciare che quell'evento non parta mai.
Un `asdlc-tick --dry-run` non manda niente nemmeno con le notifiche accese, e lascia
`runs/notifiche.json` com'era: il tick vero dopo trova ciò che avrebbe trovato senza.

Una notifica che fallisce non ferma niente: una `POST` sola per evento, con un tetto di
10 secondi, poi una riga `notifica non inviata: <esito>` in `runs/coda.log` («HTTP 500»,
«scaduto dopo 10 s») e il tick prosegue; il tick dopo ci riprova. Con il file del webhook
assente la riga dice `file del webhook assente`, una volta per evento. L'indirizzo del
webhook non compare mai, né nel log né a schermo. `runs/notifiche.json` è una cache: se non
ha la sua forma vale come vuoto, e se non si scrive (disco pieno, permessi) la riga dice
`notifica non inviata: <funzione> ha alzato <errore>` e il tick decide e lancia come sempre.

### Lo stato a comando

`asdlc-stato` dice, senza cercarlo nei log, ciò che il tick vede adesso (`PBI-534`). È di
**sola lettura**: non prende il lucchetto del tick, non allinea il checkout e non scrive il
log né il registro. La decisione non è una seconda verità: è quella di `decidi()`, con le
parole di `racconta()`, le stesse che il tick scrive in `runs/coda.log`. Prima, nell'ordine
del tick, vengono la pausa (`in pausa: <riga>` per la globale, `in pausa: (progetto) <riga>`
per quella del progetto) e il ramo del checkout: fuori dal ramo di
`[git].base` la decisione è `non allineato: …`, la frase del tick, e il checkout resta dov'è.

L'elenco dei progetti è di macchina, come la pausa, e sta fuori dai repository, in
`~/.config/asdlc/progetti.toml`:

```toml
checkout = ["/percorso/del/progetto", "/percorso/di/un/altro"]
```

Il nome di un progetto è il nome della cartella del suo checkout.

```bash
asdlc-stato                                # tutti i progetti, nell'ordine del file
asdlc-stato progetto                       # solo quello
asdlc-stato --repo /percorso/del/progetto  # uno, senza passare dall'elenco
asdlc-stato --json                         # un oggetto JSON per progetto
```

Il file che manca o non si legge, e un nome che non c'è, sono un messaggio su stderr e
l'uscita 2. Un progetto che non si legge invece non ferma gli altri (`ADR-0008`): la sua
riga è `<nome> · non raggiungibile — <motivo>`, e l'uscita resta 0.

Ogni progetto è una riga: il nome, la decisione, la voce della coda — il PBI o il testo
della barriera —, lo stato e il motivo dell'ultimo esito del runner (o `-`), e le PR aperte
sul ramo del PBI (`PR ?` se `gh` non risponde, `PR -` se non ce ne sono), e
`pin <tag> installato <tag>`: il tag di `[ambiente].installa` e quello della firma
dell'ultima installazione (`-` se non c'è). Con un `installa` cartella si mostra la cartella
per tutti e due, e senza `[ambiente].pacchetto` un trattino per tutti e due; una firma che
non si calcola, o una firma scritta che non si legge, è `pin ? (<motivo>)`. Con `--json` gli
oggetti hanno le chiavi `progetto`, `decisione`, `voce`, `esito`, `pr`, `pausa`,
`allineato`, `installato` e `pin`.

## Linguaggi e stack

Il runner non è legato a un linguaggio: esegue i comandi che il progetto dichiara in
`[[gate]]` e guarda se escono verdi. Backend e frontend stanno nello stesso progetto come
gate diversi, ciascuno col suo `cwd`, e `solo_se_tocca` accende un gate solo se il diff del
branch tocca certi percorsi:

```toml
[[gate]]
nome = "backend"
comando = ["python3", "-m", "pytest", "-q"]
cwd = "backend"
solo_se_tocca = ["backend/"]

[[gate]]
nome = "tsc"
comando = ["npx", "tsc", "--noEmit"]
cwd = "frontend"
solo_se_tocca = ["frontend/"]

[[gate]]
nome = "vitest"
comando = ["npx", "vitest", "run"]
cwd = "frontend"
solo_se_tocca = ["frontend/"]
```

Lo stack con cui il runner è nato (aDa) è Python per il backend e TypeScript/React per il
frontend, con `pytest`, `tsc`, `eslint` e `vitest`; il repo di prova `ada_test_asdlc` ha
solo un backend Python. Quello che il runner **riconosce davvero** è questo:

| Cosa | Riconosciuto |
|---|---|
| Gate | qualunque comando, in qualunque linguaggio |
| Test per il gate del rosso | `pytest` (Python) e `vitest` (JS/TS) |
| Test per il lucchetto di fase | `pytest`, `vitest` e JUnit (Java, Maven): il comando che lancia JUnit lo dichiara il progetto in `[junit]` (vedi sotto) |
| File di test | cartelle `tests/` e `__tests__/`, `test_*.py`, `*_test.py`, `*.test.*` e `*.spec.*` con estensione `ts` `tsx` `js` `jsx`, e la sequenza `src/test/` di Maven (`.java`) |
| File di produzione | estensioni `.py` `.ts` `.tsx` `.js` `.jsx` `.mjs` `.cjs` `.sql` `.sh` `.java`, fuori da `src/test/`: lì sotto un file che non è un test è supporto dei test, e si scrive in `TEST_ONLY` (`PBI-515`) |
| E2E | fuori dal runner: stanno nella CI (`ADR-0009`, l'esempio è Playwright) |

Il gate del rosso e il lucchetto di fase (`TEST_ONLY` / `IMPL`) usano proprio queste regole.
In `TEST_ONLY` il `pre-commit` lascia passare uno **scheletro vuoto** di produzione, un file
fatto solo di righe bianche e commenti: si committa da solo, prima del RED (`PBI-515`). Il
commento è quello del linguaggio: `#` per `.sh` e `.py`, `--` per `.sql`, `//` e `/* … */` per
`.java` e JS/TS; un `#` in un `.sql` è codice.
Un progetto in un altro linguaggio (Go, Rust, PHP…) ha comunque i suoi gate
deterministici, il Critic, la coda e la PR. Per quel progetto il gate del rosso non sa leggere i test:
si spegne con `[gate_del_rosso].attivo = false`, e il giro lo dichiara nel rapporto. Non l'ho
provato su uno stack diverso da Python e TypeScript, quindi va verificato sul primo PBI.

**Java (JUnit).** Il lucchetto di fase legge i test JUnit (`PBI-505`): un metodo con `@Test`,
`@ParameterizedTest` o `@RepeatedTest` in un file sotto `src/test/` è un test, e si chiama
`Classe#metodo`. L'annotazione vale anche se il commit non la cambia: un metodo rinominato
sotto un `@ParameterizedTest` rimasto com'era nasce col nome nuovo (`PBI-514`). Un test
riscritto con lo stesso nome invece non nasce. Il runner non conosce Maven: il comando che lancia i test isolati lo
dichiara il progetto, con `{test}` al posto dei test (`Classe#m1+m2,Altra#m3`, la sintassi
di `-Dtest=`), e l'esito lo legge dai `TEST-*.xml` di `target/surefire-reports` e
`target/failsafe-reports`:

```toml
[junit]
comando = ["./mvnw", "-B", "verify", "-Dtest={test}", "-Dit.test={test}",
           "-Dsurefire.failIfNoSpecifiedTests=false", "-Dfailsafe.failIfNoSpecifiedTests=false"]
```

Senza `[junit]` un test JUnit non si isola e `--chiedi-impl` non apre `IMPL`. Un errore di
compilazione vale rosso. Il gate del rosso e i mutanti **non** leggono JUnit: un progetto
Java li tiene spenti con `[gate_del_rosso].attivo = false`.

### Le specifiche

Le specifiche sono in Markdown e non dipendono dal linguaggio:

- `specs/<dominio>/spec.md`, una cartella per dominio, dal modello `specs/TEMPLATE.md`. Ha
  un **Blueprint** (contesto, architettura, vincoli) e un **Contratto** (Definition of
  Done, guardie di regressione, scenari, domande aperte).
- Gli scenari sono in Gherkin, marcati col livello che li verifica: `[unit]` `[api]`
  `[e2e]`. Il Critic giudica il diff contro il Contratto.
- I PBI (`backlog/PBI-XXX-*.md`, dal modello `backlog/TEMPLATE.md`) descrivono il
  **delta**: Direttiva con Scope, decisioni, dipendenze, criteri di Verifica e protocollo
  di rifinitura. Puntano alle spec e non le copiano.
- Gli ADR (`decisions/ADR-XXXX-*.md`) fissano le scelte con le alternative scartate.
- La spec si aggiorna nello **stesso commit** del codice che ne cambia il comportamento.

## Sviluppo

```
python3 -m venv .venv && . .venv/bin/activate && pip install pytest
python3 -m pytest -q tools/tests
```

Il runner che lavora su questo repository è quello installato dall'ultimo tag, non la copia
di lavoro (`AGENTS.md`, `## Dominio`).
