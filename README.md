# asdlc

Il runner ASDLC come pacchetto Python: fa girare i PBI di un progetto uno per volta con
`claude -p`, un contesto pulito per PBI, i **gate eseguiti dallo script** e il permesso di
scrivere produzione dato dal rosso osservato. Comandi installati:

| Comando | Cosa fa |
|---|---|
| `asdlc-runner` | un giro su un PBI, e la guardia di fase (`--guardia-fase`) per l'hook `PreToolUse` |
| `asdlc-coda` | il tick: legge `backlog/CODA.md` e lancia il PBI successivo quando il precedente è in `main` |
| `asdlc-chiudi-giro` | chiude un giro fermato: tag `giro-fermato/…`, ramo tolto |
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
5. Si apre una PR. **Il merge è tuo**: è l'Acceptance Gate umano.
6. La voce in coda si spegne quando una PR mergiata nomina il PBI e tocca file fuori da
   `backlog/`.

Se una domanda si apre a giro iniziato, il Builder chiama `fermati` e la coda si blocca da
sé. Un giro fermato si chiude con `asdlc-chiudi-giro`, che mette il tag `giro-fermato/…` e
toglie il ramo. Il rapporto e i log dei giri stanno in `runs/`.

### Il Solver, il terzo ruolo

Dopo un giro fermato — il `fermati` del Builder, una domanda bloccante del Critic, un agente
`senza esito` — il runner lancia il **Solver** (sola lettura: `Read`, `Grep`, `Glob`). Non lo
lancia su un `senza esito` per il limite d'uso dell'account con l'ora del reset leggibile
(`riprendi_dopo` nel rapporto): lì non c'è niente da decidere, si aspetta il reset (`PBI-519`). Smista il blocco con uno di tre strumenti, che il server dell'esito valida:

- `risolvi(risposta, evidenza)` — `evidenza` è un file dell'albero, `percorso` o
  `percorso:riga`;
- `segnala_limite_runner(causa, comando, output, commit)` — la `causa` è una di
  `[solver].cause`, `commit` esiste, `comando` e `output` non sono vuoti;
- `chiedi_a_francesco(domanda)` — l'esito `intento`.

Il Solver legge `asdlc.toml` prima di segnalare un limite e `backlog/PRECEDENTI.md` prima di
chiedere. Il tetto è `[solver].giri_massimi` (3) giri per PBI, contati nel rapporto
`runs/<run>.json` (`giri_solver`): oltre, o a `chiedi_a_francesco`, il giro si ferma con un
avviso nella nota. Il modello è `[solver].modello` (`opus`). Per ora il Solver è invocato e
registrato e non rilancia il Builder. A `segnala_limite_runner` (che porta anche `pbi`, il testo
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

### Il rilascio a tick

Dopo il merge di un PBI a monte, due passi del tick sostituiscono i cinque gesti a mano
(`specs/solver-e-rilascio/spec.md`, R8-R11). Il merge resta sempre di una persona: nel
pacchetto non c'è nessun `gh pr merge`.

- **In `asdlc`:** per ogni PR di PBI mergiata il cui PBI dichiara `rilascia: patch|minor`
  (una riga sotto il titolo), con la CI di `main` verde e il merge non ancora in un tag, il
  tick mette il tag successivo (`v0.3.0` → `v0.3.1` con `patch`, `v0.4.0` con `minor`).
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
| File di produzione | estensioni `.py` `.ts` `.tsx` `.js` `.jsx` `.mjs` `.cjs` `.sql` `.sh` `.java` |
| E2E | fuori dal runner: stanno nella CI (`ADR-0009`, l'esempio è Playwright) |

Il gate del rosso e il lucchetto di fase (`TEST_ONLY` / `IMPL`) usano proprio queste regole.
Un progetto in un altro linguaggio (Go, Rust, PHP…) ha comunque i suoi gate
deterministici, il Critic, la coda e la PR. Per quel progetto il gate del rosso non sa leggere i test:
si spegne con `[gate_del_rosso].attivo = false`, e il giro lo dichiara nel rapporto. Non l'ho
provato su uno stack diverso da Python e TypeScript, quindi va verificato sul primo PBI.

**Java (JUnit).** Il lucchetto di fase legge i test JUnit (`PBI-505`): un metodo con `@Test`,
`@ParameterizedTest` o `@RepeatedTest` in un file sotto `src/test/` è un test, e si chiama
`Classe#metodo`. Il runner non conosce Maven: il comando che lancia i test isolati lo
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
