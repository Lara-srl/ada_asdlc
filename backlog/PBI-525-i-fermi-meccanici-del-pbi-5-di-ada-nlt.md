# PBI-525: i fermi meccanici del PBI-5 di ada_nlt, cinque difetti in un solo caso
rilascia: minor

**Stato:** letto il 25/10 (in fondo); le due domande hanno una **proposta** del 25/10 (*Deciso*, punti 4 e 6),
che il merge della PR che accoda ratifica. Dopo `PBI-524`.

## Direttiva

Osservato su `ada_nlt`, `PBI-5`, due giri (asdlc `v0.7.0`, sha `eabbf15`): giro 1
(`20261025-085406`) e giro 2 (`20261025-212406`). Il giro 1 chiude `non convergente / revisioni-esaurite` dopo 5 passaggi del Critic, e il tick tiene la coda in
`attende` (`ramo su origin, nessuna PR`) da oltre 10 ore, scrivendo la stessa riga ogni 10 minuti.
Il codice in HEAD era giusto. In più il giro 2, ripartito dopo due fermi di pre-verifica che erano
errori veri del PBI (non meccanici, già corretti), si è fermato su un quarto difetto, sotto. Dei 5 rilievi del Critic, 3 passaggi su 5 sono **meccanici**, non di merito.

1. **Il Critic ordina un rimedio che il Builder non può eseguire.** `tools/asdlc/prompt/critic.md:38`
   chiede di chiudere l'igiene dei commit «con un rebase»; il prompt del Builder vuole un commit per
   rimedio e non riscrive la storia di un ramo pubblicato (`ADR-0022`). Revisioni 0 e 1 del giro:
   rilievi di sola storia (`f6773bf` GREEN con suite rossa; deroga allo Scope dichiarata un commit
   dopo, `ADR-0015`) il cui «Rimedio» è un rebase, e la stessa chiusa di `critic-1` dice «i due
   rilievi si chiudono con un rebase, senza cambiare HEAD». Il Builder si è fermato con una `domanda`
   (un commit nuovo non rende verde un commit vecchio); il Solver ha risposto «strada (b), niente
   rebase, si dichiara nelle note per chi mergia, **non sono rilievi bloccanti** (`ADR-0008`)». Ma il
   verdetto del Critic era già `non pronto` e ha consumato due revisioni su quattro.
2. **Il Critic riporta un'istanza per passaggio, non la classe.** Anche nel giro 2: `critic-0` trova
   `economia` come padre e `Infinity` nella PUT, `critic-1` un importo finito ma enorme
   (`decimal.InvalidOperation`). Giro 1: `critic-3`: un preventivo senza numero
   d'offerta fa `POST /preventivi` → 500. `critic-4`: una durata ≤ 0 fa `PUT …/comparazione` → 500.
   Stessa classe («un dato utente non valido torna 4xx», `Deciso 3` del PBI); il Builder chiude il
   caso nominato e il Critic scopre il prossimo al giro dopo, a tetto raggiunto.
3. **`--chiedi-impl` apre `IMPL` anche con un test non committato, e da `IMPL` non si torna.**
   Giro 2, revisione 1 (`20261025-212406`, run chiuso `fermato / domanda-del-builder`): il Builder
   ha scritto i 5 test RED, li ha visti rossi, ha lanciato `--chiedi-impl` **prima** di committarli.
   Il comando ha letto i test dall'albero e ha aperto la fase `IMPL`; il `pre-commit` ha poi rifiutato
   il commit del test («è un test e il giro è in IMPL»). Il Builder non poteva né tornare a
   `TEST_ONLY` né aggirare il lucchetto, e ha chiamato `fermati`. Il prompt (`builder.md` righe
   16-24 e 73) dice l'ordine giusto: è uno scivolone del modello che il runner trasforma in un
   fermo. È la terza volta (`PBI-3` giri 3 e 4, `PBI-5` giro 2). `PBI-524` decisione 6 sistema solo
   il **messaggio** del rifiuto quando i test sono già committati; qui il comando **accetta** un
   albero sporco di test e apre la fase sbagliata, ed è un altro caso.
4. **Il worktree del runner resta sporco dopo un giro fermato, e il giro dopo non parte.**
   Giro 3 di `PBI-5` (25/10, 22:14): dopo `asdlc-chiudi-giro PBI-5` il worktree `../ada_nlt-run` aveva
   ancora il test non committato del giro 2 in stage (`M  tests/test_servizio.py`, 21 righe). Il
   tick ha provato il pre-flight e si è fermato su `git switch --detach origin/main` (uscita 1:
   «Le tue modifiche locali […] sarebbero sovrascritte»), scrivendo `non lanciato`. Il comando
   (`tools/asdlc/chiudi_giro.py`) fa i sei passi su `origin` e sul checkout del tick, ma non guarda il
   worktree del runner. Un'altra persona è dovuta intervenire a mano (`git stash`); il lancio è
   ripartito al tick dopo, ~10 minuti persi.
5. **Il fermo è muto.** Un giro `non convergente` non avvisa nessuno: la coda attende per ore.
   Obiettivo di `PBI-519` (20/10): zero fermi meccanici, e se si ferma, si ferma con una domanda vera
   e lo si viene a sapere.

**Scope**
- `tools/asdlc/prompt/critic.md` — l'igiene dei commit su un ramo già pubblicato: il Critic la scrive
  tra le note per chi mergia e non la usa come motivo di `non pronto`; il rimedio non è un rebase.
  Per un rilievo di correttezza, il Critic esamina l'intera classe e riporta tutti i casi che trova.
- `tools/asdlc/runner.py` — `--chiedi-impl` legge i test nuovi dai **commit** `base..HEAD`, non
  dall'albero; con un file di test modificato e non committato rifiuta («committa prima il RED, poi
  richiedi la fase») e la fase resta `TEST_ONLY`. Il verdetto sui rilievi di storia **non** passa dal
  codice: sta nel prompt (decisione 1).
- `tools/asdlc/prompt/critic.md` e `tools/tests/dati/prompt/critic.txt` — il golden nello stesso commit.
- `tools/tests/test_asdlc_runner.py`, `test_asdlc_prompt.py`, `test_asdlc_chiudi_giro.py`,
  `test_asdlc_coda.py` — i test dei criteri, e i test esistenti che le decisioni 2 e 3 cambiano **nel
  commit RED**.
- ~~`tools/asdlc/chiudi_giro.py` — un settimo passo: se il worktree del runner ha modifiche non
  committate, le mette in `git stash` con un messaggio che nomina il PBI e il giro (mai
  `reset --hard`: il lavoro si recupera), e lo dice nel resoconto.~~ *Barrato il 26/10 (Francesco): sostituito da `PBI-532`, che archivia il lavoro non committato in un `.patch` e pulisce l'albero alla fine del giro, in `chiudi()` del runner (decisioni 1, 2 e 8 di quel PBI). Si rivede se `PBI-532` non entra.*
- `tools/asdlc/coda.py` — l'avviso quando la coda resta in `attende` per un `non convergente`.
- `tools/tests/` — i test dei criteri.
- `backlog/PBI-525-…md` — questo file, per la spunta.
- **Fuori scope:** il tetto `[soglie].revisioni` (alzarlo nasconde il difetto).

## ✅ Deciso (25/10, dopo la lettura)

1. **Un rilievo di sola storia lo governa il prompt, non il codice.** Il runner non può sapere che
   un rilievo è «di storia» senza leggere il testo del Critic (`ADR-0027`), e un campo nuovo in
   `fatto` non è in Scope. `critic.md` dice: un rilievo che riguarda solo la storia dei commit (un
   GREEN con suite rossa, una deroga dichiarata un commit dopo, un messaggio che allude) va sotto
   «Note per chi mergia», non fa `non pronto`, e il rimedio non è mai un rebase. Il criterio 1 è un
   criterio sul prompt e sul golden, come quelli di `PBI-524`.
2. **`--chiedi-impl` legge i test nuovi dai commit, non dall'albero.** È l'ordine che il prompt
   prescrive (committa il RED, poi chiedi la fase) e l'unico che il lucchetto di `ADR-0021` permette:
   un test osservato prima del commit e poi committato in `IMPL` è rifiutato. I test della classe di
   `test_apre_la_fase_quando_il_test_nuovo_e_rosso` (`test_asdlc_runner.py:5651`) e il loro docstring
   dicono il contrario e cambiano **nel commit RED**: la fixture committa il test prima di chiamare il
   comando. `test_nuovi_dellalbero()` resta per la sola diagnosi dell'albero sporco.
3. ~~**Il settimo passo di `chiudi-giro` sta dopo il quinto e prima di togliere la pausa.** Nel
   worktree del runner: `git status --porcelain`; se non è vuoto, `git stash push -u -m "PBI-N giro R:
   lavoro del giro fermato"`, con `cwd` il worktree. Il dry-run lo stampa. I test
   `test_un_giro_fermato_si_chiude_coi_sei_passi_in_ordine` e quello del dry-run
   (`test_asdlc_chiudi_giro.py:167`, `:361`) cambiano **nel commit RED** per attendere il passo in più
   col suo `cwd`.~~
   *Barrato il 26/10 (Francesco): sostituito da `PBI-532`, che archivia il lavoro non committato in un `.patch` e pulisce l'albero alla fine del giro, in `chiudi()` del runner (decisioni 1, 2 e 8 di quel PBI). Si rivede se `PBI-532` non entra.*
4. **Proposta per la domanda 1: un rilievo di storia non è mai bloccante dentro il giro**, prima o dopo la
   pubblicazione del ramo. Il Builder non riscrive la storia e lo squash, se serve, è al merge
   (`AGENTS.md`, micro-commit). Distinguere i due momenti chiederebbe al Critic di sapere se il ramo è
   su `origin`, e darebbe due regole per lo stesso rilievo.
5. **Il Critic riporta la classe, non l'istanza** (criterio 3): è prompt, nello stesso paragrafo della
   decisione 1, e il golden lo segue.
6. **Proposta per la domanda 2: l'avviso è una issue di GitHub nel repository del progetto**, aperta dal tick con
   `gh issue create`, titolo «fermo: PBI-N — <motivo>», corpo con la riga di `attende` e il percorso del
   rapporto. Una sola: prima di aprirla il tick cerca con `gh issue list --search` una issue aperta con
   quel titolo, e se c'è non fa niente. La chiude chi riprende il PBI. Scartati: un file nella home
   (nessuno lo legge), `PushNotification` (non c'è in un cron). La issue sta dove stanno le PR e si legge
   da ovunque: è lo stesso canale che servirà per il resoconto dei merge, quando il merge non sarà più a
   mano.

## Verifica

- [x] **Il prompt del Critic governa i rilievi di storia e non nomina il rebase.** Un test
      parametrizzato su `critic.md`: (a) contiene «Note per chi mergia» e «storia» nella stessa regola
      (o la formula equivalente scelta nel RED, dichiarata nel commit); (b) non contiene «rebase»;
      (c) dice che un rilievo di correttezza su un dato utente elenca l'intera classe verificata
      («classe», o formula equivalente). Il golden `critic.txt` segue nello stesso commit. Su `main`:
      (a) e (c) mancano, (b) c'è il rebase a riga 38.
- [x] **`--chiedi-impl` con un test modificato e non committato non apre `IMPL`.** Fase `TEST_ONLY`,
      un test committato nel RED e un secondo file di test modificato nell'albero: il comando esce 1,
      stampa «committa prima il RED» e la fase resta `TEST_ONLY`. Con l'albero pulito e il test
      committato, apre `IMPL` come oggi. Rosso su `main`: oggi apre `IMPL` leggendo l'albero.
- ~~**`asdlc-chiudi-giro` lascia il worktree del runner pulito.** Con un file in stage nel
      worktree, dopo il comando `git status --porcelain` è vuoto, `git stash list` nomina il PBI e
      il giro, il passo sta dopo il `merge --ff-only` e prima che la pausa sia tolta, e il dry-run lo
      stampa senza eseguirlo. Rosso su `main`: oggi il file resta.~~
      *Barrato il 26/10 (Francesco): sostituito da `PBI-532`, che archivia il lavoro non committato in un `.patch` e pulisce l'albero alla fine del giro, in `chiudi()` del runner (decisioni 1, 2 e 8 di quel PBI). Si rivede se `PBI-532` non entra.*
- [x] **Un tick che trova un `non convergente` apre una issue, una sola.** Con un `gh` finto: al primo
      passaggio il tick chiama `gh issue create` col titolo «fermo: PBI-N — non convergente»; al secondo
      passaggio, con `gh issue list` che la restituisce aperta, non chiama `create`. Rosso su `main`:
      oggi il tick scrive solo `attende`.

**Non regressione:**
- Un rilievo di correttezza o di test-first resta `non pronto`.
- La suite dei test resta verde.

## La lettura del 25/10

`asdlc-runner PBI-525 --preverifica --lettore` (runner `v0.7.0`), su `main` `8e472eb`: quattro
rilievi, tutti recepiti nel *Deciso*. **D** sul criterio 1 (il runner non può classificare un rilievo
senza leggerne il testo): decisione 1. **D** sul criterio 6 (il canale non era scelto): decisione 6.
**T** sul criterio 2 (`test_apre_la_fase_quando_il_test_nuovo_e_rosso` dice il contrario): decisione 2.
**T** sul criterio 5 (il test dei sei passi vuole esattamente cinque `git` con `cwd == repo`):
decisione 3. I vecchi criteri 1 e 4 erano la stessa modifica minima e sono un criterio solo. Le tre
sonde sono uscite `guasto` (gate guasto nell'albero usa e getta): il rosso resta dichiarato, non
provato, e il guasto è da capire a parte.

