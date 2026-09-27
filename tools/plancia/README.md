# Plancia ASDLC — cruscotto del processo

> Una web app per vedere **in un posto solo** tutto il processo ASDLC di aDa Controller:
> la coda dei PBI, i giri del runner con esiti/gate/tempi, i rilievi del Critic, lo stato
> del mondo (rami, lucchetto, tick di cron, PR), e — più avanti — per **agire** (pulire il
> worktree, togliere rami/lucchetti stantii, rilanciare un giro, modificare la coda e i PBI).
>
> **Non è aDa Controller** (il gestionale della carrozzeria): è un tool di *processo*, e
> vive in `tools/plancia/` dentro questo repo. Gira in locale, accanto al runner.

## Perché

Oggi il lavoro di sorveglianza del runner è manuale e sparso: parsare i `runs/*.json`,
leggere i `runs/*.log`, inseguire rami e lucchetti stantii, guardare `cron.log`, tenere
pulito il worktree, spuntare i criteri dei PBI. La plancia rende tutto questo **visibile e
azionabile** in un posto. (Origine: conversazione del 07/09/2026, mentre si babysittavano
PBI-337 e PBI-338.)

## Decisioni (07/09/2026)

- **MVP solo-lettura** prima. Le **azioni** (pulisci worktree, togli ramo/lucchetto, rilancia)
  e l'**editing** (modifica/aggiungi PBI, riordina coda) vengono dopo, a fasi.
- **Vive in `ada_controller`**, `tools/plancia/`. Non è un PBI di prodotto: **la scaffolda
  Claude direttamente**, non il runner. I pezzi complessi eventualmente si staccano in PBI.
- **Stack:** backend **FastAPI** che legge filesystem + `git` + `gh` (niente Postgres — il
  dato *sono* i file e git). Frontend: **SPA minimale** (per l'MVP basta una pagina HTML+JS
  servita da FastAPI, nessun build step; se cresce, si passa a Vite/React come aDa).
- **Riusa le funzioni di `tools/asdlc_coda.py`** invece di reimplementare la logica di stato:
  la plancia deve dire *esattamente* ciò che vede il tick, non una seconda verità.

## Le sorgenti-dato (dove vive cosa) — mappa reale, misurata il 07/09/2026

Tutto ciò che serve all'MVP è già su disco / in git / in `gh`. Percorsi relativi al repo,
tranne il worktree del runner che è **`/home/laisdev/ada-run`** (albero usa-e-getta su
`origin/main`, vedi `e2e/README.md` §«Da un worktree»).

### `backlog/CODA.md` — la coda
Prosa + righe-voce. Solo due forme contano (le altre righe il tick le ignora):
- `- PBI-337` → un PBI da lanciare (regex `^-\s+(PBI-\d+)\s*$`).
- `- ‖ <testo>` → una **barriera**: gesto umano, il tick ci si ferma (regex `^-\s+‖\s*(.+?)\s*$`).

Parser pronto: `asdlc_coda.leggi_voci(testo) -> list[Voce]` (`VocePbi` | `VoceBarriera`).

### `backlog/PBI-*.md` — i PBI
Markdown: `# PBI-XXX: titolo`, sezioni `## Direttiva`, `**Scope**`, `## ✅ Deciso`,
`## Dipendenze`, `## Contesto`, `## Verifica` (checklist `- [ ]` / `- [x]`),
`## Protocollo di rifinitura`. Una sezione con `❓` nel titolo = domande; il tick le segnala
ma lancia lo stesso (ADR-0008) — vedi `asdlc_coda.avviso_domande`.

### `runs/tempi.csv` — il registro dei giri (versionato, è il dato su cui si fattura)
Colonne: `run,pbi,stato,iniziato,finito,durata_s,durata_hms,builder_s,gate_s,critic_s,tentativi,revisioni,commit,pr,nota`.
Una riga per giro. `stato` ∈ {`fermato`, `non convergente`, `mergiabile`/verde, …};
`nota` porta il motivo dello STOP o l'esito.

### `runs/<run>.json` — il rapporto del giro
- **Mentre è in corso: uno STUB** → chiavi `{run, stato:"in-corso", iniziato, pbi}` (~120 byte).
  ⚠️ **I rilievi del Critic NON ci sono finché il giro non chiude.**
- **A giro chiuso: completo** → `{run, stato:"finito", finito, esiti:[…]}`. Ogni voce di
  `esiti[]` porta:
  - `rapporti_critic` — **un puntatore per revisione del Critic**, in ordine:
    `{revisione, verdetto, percorso}`, con `revisione` che parte da 0 come `revisioni`. Il
    testo **non** sta nel JSON: sta intero nel file `percorso`, ed è lì che sta il «perché
    NON PRONTO / PASS» (PBI-371). Fino a PBI-371 c'era `rapporto_critic`, il testo tagliato
    agli ultimi 6000 caratteri e riscritto a ogni revisione: i giri passati restano così.
  - `inventario` — **ciò che stava intorno al giro**, `{inizio, fine}` (PBI-363): ognuno ha
    `rami: {locali, origin}` (i `pbi/pbi-*`, quelli di `origin` letti con `ls-remote`),
    `alberi` (i percorsi di `git worktree list`, compresi gli usa e getta `ada-rosso-*`) e
    `file` (i non tracciati, gli ignorati e i tracciati modificati, contati per cartella:
    `{"data": 1, "runs": 12}`). Accanto, `usa_e_getta: {montati, smontati}` conta gli alberi
    `ada-rosso-*` che il giro ha montato e smontato; se i montati sono di più, la nota lo
    dice («1 albero usa e getta montato e non smontato»). Una voce che `git` non ha saputo
    leggere, o su cui è scaduto, vale `{"errore": …}`. `fine` si scrive quando il giro
    chiude; un esito `saltato` non ha inventario. Ciò che `fine` ha in più di `inizio`,
    fuori da ciò che è suo per contratto (il suo ramo, i suoi file in `runs/`), il giro lo
    scrive nel log e in coda alla `nota`: «il giro lascia: albero …, ramo … (origin), file
    data +2». All'avvio, prima del Builder, il log nomina i residui dei giri
    prima che `inizio` contiene — alberi `ada-rosso-*`, rami dello stesso PBI, file fuori da
    `runs/` — con «residui dei giri prima (non li tocco): …»; il giro non li tocca.
  - `base` — **lo sha da cui discende il giro** (PBI-374): il commit di `origin/main` preso
    una volta all'inizio, con un solo `fetch`. È quello su cui si è letto il PBI, da cui è
    nato il ramo e contro cui si contano i commit e si legge il diff del Critic. Se il
    `fetch` non ha risposto è lo sha dell'`origin/main` che c'era, e la `nota` lo dice. I
    giri prima di PBI-374 non ce l'hanno.
  - `critic_saltato` (bool), `tempi.{builder,gate,critic}` (secondi), ecc.

### `runs/<run>-<PBI>-critic-<n>.md` — il rapporto di una revisione del Critic
Uno per revisione, scritto appena il Critic ha parlato, quindi **anche a giro in corso**. In
testa `# Critic — revisione n — verdetto` e l'ora (ISO), poi il rapporto **intero**: il
`riepilogo` della chiamata `fatto`, o per un `sospeso` la domanda con sotto il testo finale
del Critic come contesto. La plancia li legge dai `percorso` di `esiti[].rapporti_critic`.

### `runs/<run>.log` — il log del giro (incrementale, **live**)
Aggiornato **a ogni fase**, quindi ottimo per il tempo reale:
```
=== PBI-338 — PBI-338-il-foglio-apre-la-pratica-senza-cambiare-pagina.md
  builder — giro 1
    gate pytest … verde (0:02:31)
    gate tsc … verde (0:00:05)
    gate eslint … verde (0:00:03)
    gate vitest … verde (0:00:07)
    gate del rosso … verde (0:00:29)
    ── <sha> test(...): … (nato verde) ──   # dettaglio del gate-del-rosso (mutanti)
    critic … NON PRONTO
  builder — giro 2
    …
  → fermato (domanda dell'agente: …)        # oppure: → fermato (albero di lavoro sporco: …)
```
Nota: durante una fase builder il log può restare **vuoto** finché la fase non chiude — non
è un blocco, è normale.

### `runs/<run>-*_builder_prompt.txt` / `*_critic_prompt.txt` — i prompt (effimeri)
I prompt *inviati* agli agenti (input), **gitignored** da `.gitignore` (`runs/*_prompt.txt`,
PR #195, 07/09). ⚠️ Sono **input, non output**: contengono la boilerplate TDD e, per il
Critic, cosa deve controllare — ma **non** i rilievi del Critic. I `PBI-105/103/324/335` che
vi compaiono sono *esempi* nella boilerplate, non il PBI in esecuzione (quello vero è nel
titolo del `.log` e nel `critic_prompt` sotto «## Contratti da caricare»).

### `runs/.runner.lock` — il lucchetto
File (spesso **vuoto**, 0 byte) su cui il runner tiene un **`flock`**. Il file **sopravvive**
a ogni giro: si legge se è *tenuto* (flock), non se esiste. Vedi `asdlc_coda.giro_in_corso`.

### `runs/cron.log` — le decisioni del tick
Una riga per tick (`asdlc_coda.racconta`): `lancia: PBI-XXX` · `attende: … ha un ramo su
origin e non è in main — tocca a un umano` · `occupato: un giro è già in corso` ·
`finita: in coda non resta niente` · `non lanciato: <guasto>`.

### Il crontab — il tick
`*/10 * * * * cd /home/laisdev/ada_controller && /usr/bin/python3 tools/asdlc_coda.py >> runs/cron.log 2>&1`
con davanti una riga `PATH=/home/laisdev/.nvm/versions/node/v20.20.2/bin:/usr/bin:/bin`
(⚠️ path Node **pinnato**, aggiungere il 07/09 — vedi «Vincoli» sotto).

## Come si deriva lo stato — **riusa `tools/asdlc_coda.py`**

Non reimplementare: importa. Funzioni pronte (misurate/lette il 07/09):
- `leggi_voci(testo)` → le voci della coda.
- `pbi_mergiati(repo) -> set[str]` → i PBI **in main**: quelli che una PR mergiata **nomina e
  ha implementato** (`gh pr list --state merged --json title,headRefName,files`). Nomina =
  titolo `^\s*(PBI-\d+)\s*:` **oppure** ramo `^pbi/pbi-(\d+)`; ha implementato = ha toccato
  qualcosa fuori da `backlog/` (PBI-353: il titolo da solo non distingue la PR che *accoda*
  un PBI da quella che lo *fa*). Finestra `LIMITE_PR=1000`; se piena, **alza un `Guasto`**
  invece di rischiare un rilancio (non indovina). L'elenco dei file è tagliato a
  `LIMITE_FILE=100` da `gh`: vuoto, assente o al limite conta come **speso**.
- `pbi_con_ramo(repo) -> set[str]` → i PBI con un ramo su origin (`git ls-remote --heads
  origin refs/heads/pbi/*`, regex `refs/heads/pbi/pbi-(\d+)`).
- `giro_in_corso(worktree) -> bool` → `flock` sul lucchetto **+** `runner_vivo`.
- `runner_vivo(worktree) -> bool` → scandisce `/proc`: un processo con **cwd nel worktree**
  **e** `asdlc_runner` nella cmdline. (⚠️ vedi «Vincoli».)
- `prossimo(voci, mergiati, rami, occupato) -> Decisione` → la logica del tick.
- Tipi `Decisione`: `Occupato` · `Finita` · `Barriera(testo)` · `Attende(pbi)` · `Lancia(pbi)`.

Lo **stato di un PBI** nella coda si legge combinando questi: *in main* (`mergiati`) → fatto;
*ha un ramo e non è in main* (`rami`) → attende un umano (merge o chiusura del ramo);
*in corso* (`giro_in_corso`) → sta girando; altrimenti → in coda.

## Tempo reale: cosa è gratis, cosa richiede una modifica al runner

**Live senza toccare il runner** (l'MVP li dà tutti):
- Progresso del giro corrente: fase, numero di giro builder, gate con esiti e tempi, motivo
  dello STOP — dal `.log` incrementale.
- Coda, PBI, rami su origin, lucchetto, tick di cron, PR aperte/verdi.
- Per i giri **chiusi**: il **rapporto integrale di ogni revisione del Critic** (i file
  puntati da `esiti[].rapporti_critic`), tempi, tentativi, revisioni, note (dal `.json`
  finito e da `tempi.csv`).

**Live da PBI-371:** i **rilievi del Critic mentre il giro è ancora aperto** (il «perché NON
PRONTO» in diretta). Il `.json` resta uno stub `in-corso` fino a fine giro, ma ogni revisione
scrive subito il suo `runs/<run>-<PBI>-critic-<n>.md`: la plancia li trova per nome, senza
aspettare i puntatori.

## Vincoli operativi che la plancia deve rispettare

La plancia sorveglia il runner: **non deve diventarne un ostacolo.** Due trappole viste dal
vivo il 07/09 (dettaglio in memoria `tick-cron-blocchi`):

1. ⚠️ **Non diventare un falso runner.** `runner_vivo()` considera «runner al lavoro»
   qualsiasi processo con **cwd dentro `/home/laisdev/ada-run`** *e* la stringa
   `asdlc_runner` nella cmdline. Un comando di monitoraggio che fa `cd ada-run` + `pgrep -af
   asdlc_runner` fa scattare `occupato` e **blocca il tick**. La plancia deve derivare la
   liveness **riusando `runner_vivo`/leggendo `/proc`**, e i suoi eventuali sottoprocessi
   **non** devono girare con cwd nel worktree portandosi dietro quella stringa. (Il backend
   della plancia gira in `ada_controller`, non in `ada-run`: già così è al sicuro.)
2. **I blocchi del tick che la plancia deve *mostrare* (ed eventualmente aiutare a
   sciogliere, in fase «azioni»):**
   - **Ramo stantio** su origin (`pbi/pbi-XXX*` senza merge, anche se punta a un commit già
     in main) → `attende`. Si scioglie con `git push origin --delete …`.
   - **Albero sporco** nel worktree: un giro che si **ferma** lascia il lavoro non committato
     del Builder; il tick dopo dice `fermato (albero di lavoro sporco)`. Il cron **non pulisce**
     fra un giro e l'altro → gesto umano.
   - **Lucchetto tenuto** / **runner morto ma processo-sosia vivo** (vedi punto 1).
   - **Node sotto cron**: il crontab senza `PATH` prende `/usr/bin/node` (v18); il progetto
     vuole ≥20 (nvm). Risolto il 07/09 con la riga `PATH=…nvm…v20.20.2…` (pinnata).

## Architettura MVP (read-only)

- **Backend** `tools/plancia/app.py` (FastAPI). Importa `tools/asdlc_coda` per lo stato.
  Legge `backlog/`, `runs/`, e shell-out a `git`/`gh`. Nessuna scrittura, nessun Postgres.
  Config: percorso repo (`/home/laisdev/ada_controller`) e worktree (`/home/laisdev/ada-run`).
- **Frontend** `tools/plancia/static/index.html` — una pagina, `fetch` sugli endpoint,
  auto-refresh (polling) per il «tempo reale» del giro in corso.
- **Avvio**: `uvicorn` col venv di `backend/.venv` (ha già FastAPI). ⚠️ avviare **da
  `ada_controller`**, mai con cwd nel worktree del runner (vincolo 1).

### Endpoint proposti (MVP)
- `GET /api/coda` → voci della coda con stato derivato (in-main / ha-ramo / in-corso / in-coda).
- `GET /api/pbi/{id}` → il markdown del PBI + checklist di verifica + eventuali `❓`.
- `GET /api/giri` → timeline da `tempi.csv` + `runs/*.json` (esiti, tempi, tentativi, note).
- `GET /api/giri/{run}` → dettaglio di un giro, inclusi i rapporti del Critic letti dai file
  di `rapporti_critic` se chiuso.
- `GET /api/giro-corrente` → il `.log` live del giro in corso + stato lucchetto/runner.
- `GET /api/stato` → rami su origin, lucchetto (tenuto?), ultimo tick di cron, PR aperte.

## Roadmap
1. **MVP read-only** (sopra) — zero modifiche al runner.
2. **Azioni**: pulisci worktree · togli ramo/lucchetto stantio · rilancia un giro (anche su
   un worktree nuovo, in parallelo) · merge della PR verde.
3. **Editing**: modifica/aggiungi PBI, riordina la coda (poi commit/PR).
4. **Rilievi del Critic in diretta**: PBI sul runner per persistere l'output del Critic per giro.

## Riferimenti
- `tools/asdlc_coda.py` (logica del tick, riusata), `tools/asdlc_runner.py` (il runner).
- `AGENTS.md` (confini), `e2e/README.md` §«Da un worktree» (lo stack del branch).
- Memoria di sessione: `tick-cron-blocchi`, `plancia-asdlc-cruscotto`, `scaletta-lancio-runner`.
