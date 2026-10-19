# PBI-509: il rilascio a tick, dal merge a monte al pin nel progetto

## Direttiva

Quarto PBI di `ADR-0030`, decisioni 2 e 3. I cinque passi che oggi si fanno a mano dopo il
merge di un PBI a monte (`PBI-505`: checkout su `main`, `--registra`, tag, PR del pin, rilancio)
diventano un tick. Il PBI ha due metà, che si provano separate ma si rilasciano insieme (la PR a monte del Solver, R5 e R6, è passata a `PBI-512`, 16/10):

- **Lato `asdlc`:** il tick vede una PR di PBI `MERGED`; se il PBI dichiara `rilascia:
  patch|minor` e la CI di `main` è verde, allinea `main`, registra il giro e mette il tag, in
  un worktree usa-e-getta (R8, R9).
- **Lato progetto:** il tick vede i PBI fermi con `attende:`; a PR a monte `MERGED` (verificato
  con `gh pr view`) e tag esistente apre la PR che cambia solo `[ambiente].installa`; a PR del
  pin `MERGED` toglie la pausa (R10, R11).

I merge restano sempre di Francesco.

**Scope**

- `tools/asdlc/coda.py` — il passo di rilascio, la lettura di `rilascia:` e di `attende:`, il
  passo del pin e la pausa.
- `tools/asdlc/runner.py` — il worktree usa-e-getta.
- `tools/asdlc/config.py` — la sezione `[rilascio]` (nome del remote del fork, del tag
  prefisso).
- `tools/tests/test_asdlc_rilascio.py` — nuovo: i test dei criteri.
- `README.md`, `backlog/AUTOMAZIONE.md`, `backlog/CODA.md` — la sezione e la riga di coda.
- `backlog/PBI-509-il-rilascio-a-tick.md` — questo file, per la spunta.

**Fuori scope**

- La PR a monte del Solver, R5 e R6 (`PBI-512`).
- Il merge: mai automatico. Un `gh pr merge` nel codice è una violazione di R10-R11.
- Il battito e il timer dei tick persi (`PBI-510`).
- Il pin dei progetti che non dichiarano `attende:`.

## ✅ Via libera di Francesco (16/10)

Francesco ha accodato il PBI con il formato di `rilascia:` e `attende:` qui sotto così come
proposto: valgono come decisioni. Il PBI è largo (due metà e una PR): se il Critic lo giudica
tale, la divisione in due è lecita e si dichiara (`ADR-0015`).

## ✅ Deciso

1. **`rilascia: patch|minor`** è una riga dell'intestazione del PBI, subito sotto il titolo,
   accanto a `Direttiva`. Senza, nessun tag (R8). Un PBI di documentazione non lo dichiara.
2. **`attende: <repo>#<PBI>`** è una riga analoga nel PBI fermo del progetto, per esempio
   `attende: Lara-srl/ada_asdlc#PBI-505`. La pausa del progetto è `~/asdlc-tick.pausa`
   (già esistente, `PBI-385`).
3. **Il tag è `vX.Y.Z`**, con il numero successivo secondo `patch` o `minor`; non esiste già;
   la CI di `main` è verde (`gh run list`).
4. **Il worktree usa-e-getta** è creato fuori dal checkout del tick, che resta pulito (R9);
   `--registra` e il tag girano là dentro; il worktree si toglie a fine passo.
5. **La PR del pin cambia una sola riga**, `[ambiente].installa` di `asdlc.toml`. La parte
   specifica del progetto (per esempio `[junit]`) è del suo PBI a valle.
6. **Credenziali:** il fork usa il `gh` del proprietario. Nessun permesso di scrittura su
   `asdlc` (R5).
7. **Lo scope dei commit è `coda` e `runner`.**

## Dipendenze

- Bloccato da: `PBI-506` (il vocabolario), `PBI-507` (lo strumento che apre la PR a monte).
- Sblocca: la chiusura automatica del ciclo di `ADR-0030`.

## Contesto

- `specs/solver-e-rilascio/spec.md`, R5-R11 e il disegno del ciclo.
- `PBI-505`, «Dipendenze»: i cinque passi manuali da automatizzare.
- `ADR-0026`: il tag è la release.

## Verifica

Su `main` non c'è rilascio: ogni criterio è un **rosso atteso**. `gh` e `git remote` sono
sostituiti da finti; nessun test usa la rete.

- [x] **Un PBI con `rilascia: patch` mergiato e CI verde produce il tag.** Da `v0.3.0` a
      `v0.3.1`; con `minor`, `v0.4.0` (R8).
- [x] **Senza `rilascia:` non c'è tag.** Lo stesso scenario, nessun tag (R8).
- [x] **CI rossa o tag già esistente: nessun tag.** Due casi (R8).
- [x] **Il rilascio gira in un worktree separato e il checkout del tick resta pulito.** Il test
      verifica lo stato del checkout prima e dopo, e che il worktree sia tolto (R9).
- [x] **Un PBI fermo con `attende:` e PR a monte `MERGED` con tag apre la PR del pin.** La PR
      cambia solo `[ambiente].installa` (R10).
- [x] **La PR a monte non `MERGED` non apre niente.** Il progetto resta in attesa (R10).
- [x] **La pausa si toglie solo a PR del pin `MERGED`,** verificata con `gh pr view`; con la
      PR aperta o chiusa senza merge la pausa resta (R11, due casi).
- [x] **Un errore in `rilascia()` o in `pin()` non ferma il tick.** Un JSON illeggibile (`pin`)
      e un worktree che non si crea (`rilascia`) diventano un avviso e il tick va avanti
      con gli altri passi e gli altri progetti (`ADR-0008`).
- [x] **Nessun `gh pr merge` esce dal tick.** Un test che esegue davvero `rilascia()` e `pin()`
      con un finto `gh` e controlla che nessuna chiamata sia `pr merge`, in uno scenario che
      rilascia e in uno che apre il pin (R10-R11). Deve poter fallire: aggiungere una chiamata
      `gh pr merge` in uno dei due passi lo rende rosso. Un test che legge i sorgenti con l'AST
      non lo è: nasce verde e non morde (il gate del rosso lo ferma, giro 4).

**Non regressione:** il tick di un progetto senza `attende:` e senza `rilascia:` fa quello di
prima; `python3 -m pytest -q tools/tests` resta verde.

## Il giro 3, e cosa si riprende

Il giro 2 (16/10) si è fermato con otto criteri su dieci e una domanda su R5 e R6. Francesco ha
deciso: la PR a monte del Solver esce e diventa `PBI-512`; qui restano rilascio, pin e pausa,
più la guardia sulle eccezioni. Il giro 3 ha ripreso i 24 commit, ma ha perso il criterio
della guardia nel conflitto sul file di questo PBI e si è fermato a chiederlo (22:27).

**Si riprende il tag `giro-fermato/pbi-509-giro3-20261016`:** è il codice completo, gate verde
(1004 test), con tutti gli sha del giro 2 già dentro. Si crea il ramo da quel tag e non si
cherry-picka niente. Sul file di questo PBI vale la versione di `main`, che ha già le otto
spunte `[x]` e il criterio nuovo, scritto sopra: `git checkout origin/main --
backlog/PBI-509-il-rilascio-a-tick.md` e un commit. Niente da lasciare.

**Resta da fare un solo criterio, quello sulle eccezioni** («Un errore in `rilascia()` o in
`pin()` non ferma il tick»), in `tools/asdlc/coda.py`, nelle due funzioni `rilascia()` e
`pin()`. Esito atteso: un avviso (`ADR-0008`) e il tick che prosegue con gli altri passi e
gli altri progetti; nessuna eccezione esce da `tick()`. Casi: JSON illeggibile (`pin`),
worktree che non si crea (`rilascia`). RED prima, poi GREEN; alla fine si spunta la riga e
si aggiorna la spec nello stesso commit.

## Il giro 5, e cosa si riprende

Il giro 4 (16/10) ha fatto il criterio sulle eccezioni (RED `552daf2`, GREEN `2d68306`) e si
è fermato a `rosso-mai-visto` su due test del giro 2 che nascono verdi e non mordono.
Francesco ha scelto di tenere il criterio sul merge, ma con un test che morde (scelta «b»).

**Si riprende il tag `giro-fermato/pbi-509-giro4-20261016`:** ramo da quel tag, niente
cherry-pick; il file di questo PBI si prende da `main` (`git checkout origin/main --
backlog/PBI-509-il-rilascio-a-tick.md`) e poi si spunta la riga del criterio sulle eccezioni (in
`main` è `[ ]`, ma il codice e i test ci sono già). Niente da lasciare.

**Da fare, due cose:**

1. **`0fb1cea`, il test del `--dry-run`** («il tick non rilascia e non apre il pin»). Tutti i
   173 mutanti di `coda.py::passaggio` lo lasciano verde: il test non dipende dalla riga
   `a.dry_run`. Va riscritto perché fallisca se quel controllo si toglie: un finto `rilascia`
   e un finto `pin` che registrano la chiamata, e `tick("--dry-run")` che non deve chiamarli
   mentre `tick()` senza opzione sì (un solo test con i due casi, così il verde è la
   differenza e non l'assenza).
2. **`6a874a0`, il test dell'AST sul `gh pr merge`.** Si sostituisce con il test del criterio
   scritto sopra (finto `gh`, `rilascia()` e `pin()` eseguiti davvero), e si toglie l'helper
   `chiamate_che_uniscono_una_pr` con il suo test, che non guardano codice di produzione.

Il rosso si osserva come sempre: il test nuovo prima fallisce contro una versione del passo
che chiama `gh pr merge` (o senza il controllo del dry-run), poi passa. Spec, README e
`AUTOMAZIONE.md` nello stesso commit, dove nominano il test dell'AST.

## Il giro 6, e cosa si riprende

Il giro 5 (16/10) ha riscritto il test del `--dry-run` e quello sul `gh pr merge`, e si è
fermato di nuovo a `rosso-mai-visto`. Non per il lavoro del giro, ma per la storia: `0fb1cea`
e `6a874a0` stanno sotto il tag del giro 4, quindi ogni ramo che ne parte li porta con sé, e la
guardia li rilegge anche se alla punta quei test non ci sono più. Il test nuovo del dry-run
(`dcfcb9d`) è nato verde per la stessa ragione di `0fb1cea`: i controlli `a.dry_run` in
`tick()` c'erano già, e un test scritto dopo il codice non può essere rosso (`ADR-0021`: il
ciclo mancato è ex ante e nessuna fix lo annulla). `06f9a69` (il gh finto) non è stato
contestato.

**Si riprende il tag `ripresa/pbi-509-giro6`** (non un `giro-fermato/…`): è la storia del giro 4
senza `0fb1cea`, `6a874a0` e il fix dell'AST `5793d74`, più un commit `b502a52` che toglie a
mano i due controlli `a.dry_run` su `pin()` e `rilascia()` in `tick()` (`coda.py`, funzione
`passaggio`), così il test del dry-run può nascere rosso. Gate verde sul tag (1003 test). Ramo
da quel tag, niente cherry-pick e niente rebase: la storia è già pulita. Il file di questo PBI
si prende da `main` (`git checkout origin/main -- backlog/PBI-509-il-rilascio-a-tick.md`), un
commit. Non c'è conflitto da risolvere: il tag ha il file di `main` com'era al giro 4, e se
`git` ne vede uno sul file di questo PBI vale sempre la versione di `main`.

**Da fare, in quest'ordine:**

1. **Il test del `--dry-run`, RED.** Un solo test con i due casi: finti `rilascia` e `pin` che
   registrano la chiamata; con `tick("--dry-run")` non sono chiamati, con `tick()` senza
   opzione sì. Contro il tag fallisce (i due controlli non ci sono): quello è il rosso, e va
   in un commit `test(coda): …(RED)` da solo.
2. **GREEN.** Si rimettono i due controlli in `passaggio` — `for riga in () if a.dry_run else
   pin(a.repo):` e `for riga in () if a.dry_run else rilascia(a.repo):` — e il test passa. Un
   commit `feat(coda): …` con il solo codice che lo fa passare.
3. **Il criterio sul `gh pr merge`.** Un test che esegue `rilascia()` e `pin()` con un finto
   `gh` (come `06f9a69` nel giro 5, che la guardia non ha contestato): nessuna chiamata è
   `pr merge`, e iniettarne una in uno dei due passi lo fa fallire. Qui il codice di produzione
   non va toccato: il test nasce verde contro un codice che non fa mai quel merge, e morde
   perché un mutante che lo aggiunge lo rende rosso. Spec, README e `AUTOMAZIONE.md` smettono
   di nominare il test dell'AST.
4. Si spuntano le due righe aperte (eccezioni e `gh pr merge`) e si aggiorna la spec nello stesso
   commit.

**Non si fa:** non si rimettono `0fb1cea`, `6a874a0`, `dcfcb9d`, `06f9a69` né `80d35d2` (stanno
sul ramo del giro 5, non su questo tag), e non si tocca il commit `b502a52`: il GREEN del punto
2 lo annulla con un commit nuovo, non lo riscrive.

## Il giro 7, e cosa si riprende

Il giro 6 (18/10) ha fatto tutti e quattro i punti della sezione sopra e si è fermato prima del
Critic, **non per il lavoro**: il Builder ha chiuso `fatto` e il gate del rosso è passato anche
sull'ultimo test (`a39e4f3`, «nato verde, ma morde»: la riga di `coda.py` cancellata lo uccide
per asserzione). Poi il Critic è uscito dopo due secondi, senza nessuna chiamata: il limite
d'uso dell'account (`critic-senza-esito`, reset alle 2:10). Nessun rilievo, nessun verdetto:
il lavoro non è mai stato letto.

**Si riprende il tag `giro-fermato/pbi-509-giro6-20261018`** (17572a3): è la punta del giro 6,
discendente di `ripresa/pbi-509-giro6`, con RED `df13958`, GREEN `27500a3`, il test del
`gh pr merge` `a39e4f3` e le spunte con la spec `17572a3`. Ramo da quel tag, niente
cherry-pick e niente rebase. Il file di questo PBI si prende da `main`
(`git checkout origin/main -- backlog/PBI-509-il-rilascio-a-tick.md`), un commit, e poi si
spuntano le due righe aperte (eccezioni e `gh pr merge`), che in `main` sono `[ ]`. Se `git`
vede un conflitto su questo file vale sempre la versione di `main`.

**Da fare:** niente codice nuovo. Il Builder rilancia il gate sul ramo (deve essere verde),
controlla che i quattro punti del giro 6 siano in piedi e chiama `fatto`, perché il Critic
legga ciò che il giro 6 non ha potuto fargli leggere. Se il gate è rosso o un punto manca, è
un fatto nuovo: `fermati` con la domanda, non una riscrittura.

**Non si fa:** non si riscrive la storia del tag, non si rifanno RED e GREEN (il rosso è già
stato osservato dal gate nel giro 6) e non si tocca la spec oltre alle spunte.
