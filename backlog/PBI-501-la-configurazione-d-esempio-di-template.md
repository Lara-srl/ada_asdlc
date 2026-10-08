# PBI-501: la configurazione d'esempio in `template/`, e un progetto che ne nasce la carica

## Direttiva

Secondo dei quattro PBI di `template/` (D5 di `SCAFFOLDING.md` di aDa). Entrano in
`template/` i file che fanno girare il runner in un progetto nuovo, scritti in modo che
**una copia di `template/` sia già un progetto che il pacchetto sa caricare**:

- `template/asdlc.toml` — la configurazione d'esempio, senza percorsi di macchina, con un
  gate solo e il pin del pacchetto;
- `template/asdlc-aggiunte/README.md` — la cartella delle aggiunte ai prompt, vuota di ruoli;
- `template/runs/tempi.csv` — il registro dei tempi con le sole colonne;
- `template/.gitignore` — le regole di `runs/`, del venv del pacchetto e di
  `asdlc.local.toml`;
- `template/.github/workflows/ci.yml` — lo scheletro della CI, che gira lo stesso comando del
  gate;
- ~~`template/.claude/settings.json` e `template/.claude/hooks/fase-tdd.sh` — la guardia di
  fase per le sessioni delle persone, identica a quella di questo repository.~~ Escono da
  questo PBI al giro 1: il Builder non può scrivere sotto `.claude/` (decisione 1 del giro 1).

Il criterio che li tiene insieme è la **nascita**: si copia `template/` in una cartella
temporanea, ci si fa `git init`, e il progetto che ne esce si comporta come deve. Il
contenuto dei file conta solo per quello che la nascita ne fa.

**Scope**
- I cinque file qui sopra che non sono barrati — nuovi.
- `tools/tests/test_asdlc_template.py` — i test dei criteri, accanto a quelli di `PBI-500`.
- `backlog/PBI-501-la-configurazione-d-esempio-di-template.md` — questo file, per la spunta.
- **Fuori scope:** `asdlc.toml`, `.gitignore`, `.github/workflows/ci.yml` e `.claude/` di
  questo repository, che non cambiano; la riga di cron, che sta in `backlog/AUTOMAZIONE.md`
  (`PBI-502`); `tools/asdlc/`, tutto.

~~**Un file di produzione solo: `template/.claude/hooks/fase-tdd.sh`** (`.sh` è in
`ESTENSIONI_CODICE`). Tutti gli altri si scrivono in `TEST_ONLY`. Per questo il criterio
dell'hook è **l'ultimo**, ed è l'unico per cui il giro chiama `--chiedi-impl`, **una volta
sola**, dopo il suo commit RED: il runner `0.1.0` installato ha il difetto 91 di `PBI-102`, e
un secondo `--chiedi-impl` nello stesso giro verrebbe rifiutato con «nessun test nuovo». Dopo
l'IMPL non si scrivono più test: il commit GREEN dell'hook porta la copia dei due file e la
spunta del criterio, e chiude il giro.~~

**Dal giro 2 il PBI non ha più file di produzione**: l'hook è uscito con il criterio 5. Il
giro resta in `TEST_ONLY` dall'inizio alla fine e **non chiama mai `--chiedi-impl`**.

Durante il giro il runner non lancia nessun file dello Scope: Claude Code legge gli hook dalla
`.claude/` della radice del progetto, e la guardia del Builder arriva con `--settings` dal
runner installato. `template/.claude/` non la legge nessuno, qui.

## ✅ Deciso, per non fermare il giro

1. **La nascita è una funzione d'aiuto, non una fixture**: copia `template/` in `tmp_path`
   con `shutil.copytree` (`symlinks=True`), fa `git init` e un commit iniziale con
   `--no-verify` (difetto 92), e torna la cartella. Non scrive niente fuori da `tmp_path`.
   Il test, **prima** di chiamarla, asserisce che il file del suo criterio c'è in
   `template/`: così su `main` il rosso è un fallimento per asserzione. Un'asserzione dentro
   una fixture pytest la riporta come errore di setup, non come fallimento, e
   `--chiedi-impl` e il gate del rosso vogliono il secondo.
2. **La configurazione si carica con il caricatore del pacchetto**, `asdlc_config.carica()`,
   sulla cartella nata: è lui che rifiuta i percorsi di macchina, controlla le aggiunte e
   risolve `pacchetto` e `worktree` dalla radice comune. Il test non riscrive quelle regole.
3. **Il pin del template è il pin di questo repository.** `[ambiente].installa` di
   `template/asdlc.toml` è uguale a quello di `asdlc.toml`: l'ultimo tag rilasciato. Quando
   il pin di qui sale (il passo 4.3, a `v0.2.0`), il test obbliga a salire anche quello del
   template, nella stessa PR.
4. **Il gate d'esempio è uno**: `nome = "test"`, `comando = ["python3", "-m", "pytest", "-q"]`,
   `cwd = "."`, senza `solo_se_tocca`. `eseguibili = ["git", "gh", "pytest"]`,
   `pacchetto = ".venv-asdlc"`, `[prompt].aggiunte = "asdlc-aggiunte"`,
   `[worktree].percorso` accanto al checkout (`"../<nome>-run"` scritto come valore vero,
   per esempio `"../progetto-run"`). Ogni chiave ha sopra il suo commento, come in
   `asdlc.toml` di qui; le ragioni restano nel sorgente.
5. **`.gitignore` si prova con `git check-ignore` nella cartella nata**, non in questo
   repository: qui `asdlc.local.toml` e `.venv-asdlc/` li ignora già la `.gitignore` della
   radice, e il test sarebbe verde su `main`.
6. **Lo scheletro della CI si legge come testo**, senza una libreria YAML (la CI installa solo
   `pytest`): per ogni gate di `template/asdlc.toml`, `" ".join(comando)` compare in una riga
   `run:`. Lo scheletro gira su `pull_request` e su `push` in `main`, come `ci.yml` di qui.
7. ~~**L'hook e le sue impostazioni sono copie identiche**, byte per byte, di
   `.claude/hooks/fase-tdd.sh` e `.claude/settings.json`, e l'hook è eseguibile. Una copia è
   una seconda fonte (`due-fonti`): il test è ciò che la tiene uguale, e una correzione
   all'hook di qui senza la copia diventa rossa.~~ Esce con il criterio 5 (giro 1).
8. **Lo scope dei commit è `template`** (`ADR-0028`).

## Il giro 1, e cosa si riprende (08/10/2026)

Il giro 1 è partito alle 23:05 col runner `0.1.0` e si è fermato alle 23:09 con
`domanda-del-builder`, dopo 9 commit. I criteri 1–4 sono fatti, ognuno con la sua coppia
RED→GREEN e la spunta. Il criterio 5 si è fermato **dopo** il suo RED (`7a47fda`): l'IMPL
era aperta, ma la sessione del Builder **non può scrivere sotto `.claude/`**. Claude Code
tratta ogni percorso `.claude/` come file sensibile, anche dentro `template/`, e chiede un
permesso che in un giro non presidiato nessuno concede. Il Builder non l'ha aggirato con una
scrittura da shell, e ha fatto bene. È il difetto 97 di `PBI-102`.

**Decisioni (Francesco, 08/10/2026):**

1. **Il criterio 5 esce da questo PBI.** I due file di `template/.claude/` li copia una
   persona, in una PR sua, con un test suo in un file a parte
   (`tools/tests/test_asdlc_template_guardia_di_fase.py`): così non tocca il file dei test di
   questo PBI né quello di `PBI-502`. Una barriera in `CODA.md` tiene fermo `PBI-503`, che
   nomina `.claude/` in `ZERO.md`, finché quella PR non è mergiata.
2. **Si riprendono gli 8 commit dei criteri 1–4** dal tag
   `giro-fermato/pbi-501-giro1-20261008`, in quest'ordine, con `git cherry-pick`: `b742e14`,
   `d8b2b9b`, `d021eef`, `8db18bf`, `a5378bf`, `8876cf6`, `aa7bf02`, `9ff998f`.
3. **Non si riprende `7a47fda`**, il RED del criterio 5: il suo test resterebbe rosso, e il
   test vero nasce nella PR della decisione 1. E dal giro 2 il giro non tocca `.claude/`.
4. **Il giro resta in `TEST_ONLY` e non chiama `--chiedi-impl`**: dopo gli 8 commit non c'è
   altro da scrivere che la chiusura. `python3 -m pytest -q tools/tests` si gira prima di
   dichiarare `fatto`.

## Dipendenze
- Bloccato da: `PBI-500` (nasce `template/` e il file dei test; e la guardia sui percorsi di
  macchina e sui nomi di aDa, che vale anche per questi file).

## Contesto
- `asdlc.toml` di questo repository — la forma, i commenti, le due ancore dei percorsi.
- `tools/asdlc/config.py` — `carica()`, `rifiuta_i_percorsi_di_macchina()`,
  `controlla_le_aggiunte()` (il `README.md` è ammesso, e nient'altro che `<ruolo>.md`).
- `tools/asdlc/runner.py` — `COLONNE_CSV`, le colonne del registro dei tempi.
- `asdlc-aggiunte/README.md` — da cui si scrive quello del template, senza ciò che è di qui.
- `.gitignore` di qui, la parte `# --- ASDLC`: le tre regole e le loro ragioni.
- `tools/tests/test_asdlc_config.py`, `test_guardia_l_asdlc_toml_del_progetto_ospite_regge` —
  come si carica la configurazione di un progetto ospite.
- ⚠️ `asdlc_config.radice()` cerca il primo `asdlc.toml` dalla cartella di lavoro in su: con
  `template/asdlc.toml` un comando lanciato da dentro `template/` troverebbe quello. I gate,
  il tick e il runner partono dalla radice, quindi non cambia niente; il commento in testa a
  `template/asdlc.toml` lo dice.

## Verifica
- [x] **Un progetto nato da `template/` carica la sua configurazione.** Sulla cartella nata,
      `asdlc_config.carica()` non alza; la configurazione ha almeno un gate, ogni `cwd` dei
      gate esiste nella cartella nata, `pacchetto` è `.venv-asdlc` sotto la radice comune, e
      `[ambiente].installa` è uguale a quello di `asdlc.toml` di questo repository.
- [x] **Il registro dei tempi del template ha le colonne del runner, e nessuna riga.**
      `template/runs/tempi.csv` è una riga sola, e i suoi campi sono `COLONNE_CSV`.
- [ ] **Un progetto nato da `template/` ignora i file effimeri e versiona il registro.** Nella
      cartella nata `git check-ignore` riconosce `asdlc.local.toml`, `runs/giro.log`,
      `runs/giro.json` e `.venv-asdlc/bin/asdlc-coda`, e non riconosce `runs/tempi.csv`. È un
      criterio solo con cinque esempi: un test parametrico, un id per percorso.
- [ ] **La CI del template gira i gate del template.** In
      `template/.github/workflows/ci.yml`, ogni comando dei gate di `template/asdlc.toml`
      compare in una riga `run:`, e il file nomina `pull_request` e `push`.
- ~~**La guardia di fase del template è quella di questo repository.**
      `template/.claude/hooks/fase-tdd.sh` e `template/.claude/settings.json` sono uguali
      byte per byte a `.claude/hooks/fase-tdd.sh` e `.claude/settings.json`, e l'hook ha il
      bit di esecuzione. **Ultimo criterio, e l'unico con `--chiedi-impl`.**~~ Esce da questo
      PBI al giro 1, senza casella: lo fa una persona, in una PR sua (decisione 1 del giro 1).

**Non regressione:**
- La guardia di `PBI-500` (nessun percorso di macchina, nessun nome di aDa, sotto
  `template/`) resta verde con i file nuovi.
- `python3 -m pytest -q tools/tests` resta verde: nessun test che c'è cambia.

## Protocollo di rifinitura
Un file di `template/` che copia un file di qui ha un test che lo tiene uguale, o un test che
dice perché è diverso. Un file che il pacchetto legge si prova facendolo leggere al pacchetto,
in una cartella nata dalla copia.
