# Spec: il Solver e il rilascio a catena

Lo **stato** voluto del sistema (come funziona). Le decisioni e le alternative stanno in
`decisions/ADR-0030-il-solver-smista-i-blocchi-e-il-rilascio-corre-da-solo.md`; ciò che
cambia, PBI per PBI, sta in `backlog/`.

> **Stato di costruzione: R1-R4 e R13 esistono (`PBI-506`–`PBI-508`, la traccia di R4 in `PBI-511`); R8-R11 esistono
> (`PBI-509`); la PR a monte del Solver (R5-R6, la sua apertura) esiste (`PBI-512`); la ripresa del
> Builder dopo `risolto` esiste (`PBI-517`).** La spec descrive il
> comportamento a cui i PBI devono arrivare. Oggi la catena è manuale (v. l'ADR, Contesto).

## Il ciclo

```
giro fermato / domanda bloccante del Critic
        │
        ▼
     Solver ──risolto──────────► il Builder riprende con la risposta
        │
        ├─limite-del-runner────► PR in asdlc (PBI + riga di coda) ──► merge di Francesco
        │                                                                   │
        │                           tick di asdlc: main allineato, --registra, tag
        │                                                                   │
        │                           tick del progetto: PR del nuovo pin ──► merge di Francesco
        │                                                                   │
        │                                                  pausa tolta, il PBI fermo riparte
        └─intento──────────────► avviso a Francesco; il giro resta fermo
```

### La ripresa dopo `risolto` (`PBI-517`)

Il `fermati` del Builder va al Solver dentro il giro, non alla sua chiusura. Se il Solver
risponde `risolto` il Builder riprende nello stesso giro, e il giro prosegue fino al suo esito
(gate, Critic, `fatto` o un'altra uscita); un secondo `fermati` torna al Solver. Ogni altro
esito del Solver (`limite-del-runner`, `intento`, nessuna chiamata) e un Solver che non parte
o si guasta chiudono il giro `fermato` come prima.

Il Builder riprende dalla **sua** sessione: `--resume <sessione>` con la sessione
dell'invocazione che ha chiamato `fermati` (il campo `sessione` del rapporto), e non `-c`, che
continuerebbe l'ultima sessione dell'albero, cioè quella del Solver. `--fork-session` e il
`--session-id` nuovo li aggiunge il runner a ogni invocazione (`PBI-511`, `PBI-513`). La ripresa
non conta come tentativo sui gate; i rilanci dopo un gate rosso tornano a `-c`.

Il prompt della ripresa è `tools/asdlc/prompt/ripresa-dopo-risolto.md`: la domanda del Builder,
la risposta del Solver con la sua `evidenza` in un blocco **da valutare**, e la frase «riprendi
da dove ti sei fermato, nella fase in cui sei» (la fase sta su disco e la ripresa non la
cambia). Domanda e risposta entrano come valori di `.format()`, mai nel template. La risposta
non annulla lo Scope né i gate.

Si riprende con `--resume` solo se la traccia della sessione c'è (`traccia` non `None` nel
rapporto): `sessione` c'è sempre, e un `--resume` su una sessione assente fallirebbe. Senza
traccia il Builder riparte da una sessione nuova (né `--resume` né `-c`) con un prompt che porta
il PBI, la domanda e la risposta, e il giro lo dichiara con un avviso nella nota (`ADR-0008`). Il
prompt dice dove rileggere il lavoro fatto e i rilievi del Critic: `git log` e il rapporto del
Critic in `runs/`.

La guardia di processo (R13) gira alla chiusura di ogni giro in cui il Solver ha scritto, qualunque
sia il motivo finale: dopo una ripresa può essere `fatto`, `gate-rossi` o `revisioni-esaurite`.

Il tetto delle riprese è quello dei giri del Solver (R12, `[solver].giri_massimi`). Il contatore
`giri_solver` si legge dai rapporti su disco alla prima chiamata del Solver nel giro e da lì
cresce in memoria a ogni invocazione: il rapporto del giro in corso non ha esiti, e rileggerlo
non vedrebbe i giri appena fatti. Conta le invocazioni del Solver, non le riprese: un Solver
senza esito o `intento` consuma un giro senza riprendere. Raggiunto il tetto il Solver non
parte e il giro chiude `fermato` con l'avviso.

Il rapporto del giro porta `riprese_solver`, le riprese del Builder dopo un `risolto`, accanto a
`giri_solver`; le invocazioni di ogni ripresa stanno in `invocazioni` come le altre. Gli altri blocchi (`builder-senza-esito`,
`domanda-del-critic`, `critic-senza-esito`) si smistano una volta, alla chiusura, e non
riprendono.

Fa eccezione il `senza esito` per il limite d'uso con l'ora del reset leggibile: non passa
dal Solver. Il tick aspetta `riprendi_dopo` e rilancia il PBI con `--riprendi`, fino a tre
riprese; dopo la terza il PBI attende una persona (`PBI-519`).

Non passa dal Solver nemmeno il `fermato` della pre-verifica, motivo `preverifica`
(`PBI-522`): arriva prima del ramo, e il suo rimedio è correggere il PBI.

## Regole

Ogni regola risponde alle quattro domande: **cosa si controlla · quando · cosa conta come
prova · cosa succede se manca**. Se manca, si segnala e il flusso va avanti (`ADR-0008`),
salvo dove è scritto che il giro chiude `senza esito`.

### R1 — Il Solver esce con una chiamata a strumento

- **Cosa:** l'esito del Solver (`risolto`, `limite-del-runner`, `intento`).
- **Quando:** alla fine di ogni chiamata del Solver.
- **Prova:** una chiamata a uno dei tre strumenti nel rapporto del giro; la prima è definitiva.
- **Se manca:** il giro chiude `senza esito`, con l'uscita grezza allegata. Mai ripiego sul
  testo (`ADR-0027`).

### R2 — `risolto` porta la fonte

- **Cosa:** la risposta a una domanda fattuale o tecnica.
- **Quando:** alla chiamata di `risolvi`.
- **Prova:** il campo `evidenza` nomina un file (codice, spec o ADR) che esiste nell'albero.
- **Se manca:** lo strumento rifiuta la chiamata; il Solver vede l'errore e risponde di nuovo.

### R3 — `limite-del-runner` vale solo per una causa `runner-*`, con riproduzione

- **Cosa:** la causa, il comando, l'output e il commit che mostrano il comportamento sbagliato.
- **Quando:** alla chiamata di `segnala_limite_runner`.
- **Prova:** `causa` è nell'elenco chiuso delle `runner-*` del progetto; `comando` e `output`
  non sono vuoti; `commit` esiste nell'albero; la riproduzione è un caso minimo che il PBI
  porterà come test rosso nel repository `asdlc`.
- **Se manca:** lo strumento rifiuta la chiamata. Una causa fuori elenco non apre mai un PBI
  a monte.

### R4 — La configurazione del progetto si esclude prima

- **Cosa:** che il blocco non venga da una chiave sbagliata del progetto (per esempio
  `[gate_del_rosso]` o `[ambiente].eseguibili`).
- **Quando:** prima di `segnala_limite_runner`; l'ordine è `risolto`, poi `limite-del-runner`.
- **Prova:** la traccia della sessione del Solver (v. «La traccia delle sessioni») ha un `Read`
  di `asdlc.toml` prima della chiamata a `segnala_limite_runner`. La guardia la legge dalle
  chiamate a strumento, nell'ordine in cui sono avvenute, mai dal testo delle risposte.
- **Se manca:** la guardia (R13) scrive `violata` se la lettura manca o viene dopo la
  segnalazione, e `non eseguita` se la traccia non c'è, non si legge o non segnala alcun limite.
  Il Critic lo vede nella rilettura.

### R5 — A monte si scrive solo con una PR

- **Cosa:** dove atterrano il PBI e la riga di `backlog/CODA.md`.
- **Quando:** all'apertura del PBI a monte.
- **Prova:** un ramo su un fork di `asdlc` e una PR da lì verso `asdlc`; nessuna scrittura su `main`, su
  `AGENTS.md` o sui file di `decisions/` esistenti.
- **Se manca:** la guardia di processo (v. sotto) lo segnala. Il merge di Francesco resta il
  cancello della coda.

### Dopo la PR: l'attesa (`PBI-512`)

A un `segnala_limite_runner`, `smista_il_blocco` apre il PBI a monte (R5-R6), scrive nel PBI
fermo la riga `attende: <repo>#<PBI>` (formato di R8), la committa sul ramo del PBI fermo (il
worktree del runner resta pulito e il ramo si pubblica alla chiusura del giro) e crea la pausa `~/asdlc-tick.pausa`;
a tornare in marcia ci pensa il pin (R10-R11). Con una causa già a monte la riga nomina il PBI
esistente (per una PR, quello del suo titolo o del suo ramo). Un passo che fallisce è un avviso del Solver
(`ADR-0008`) e non scrive né la riga né la pausa.

### R6 — Un solo PBI a monte per causa

- **Cosa:** i duplicati.
- **Quando:** prima di aprire la PR.
- **Prova:** nessun PBI in `backlog/` né PR aperta in `asdlc` con la stessa `causa`.
- **Oggi (`PBI-512`):** `apri_pr_a_monte` cerca la `causa` a parola intera nei PBI di `backlog/`
  di `origin/main` del clone e nelle PR aperte; se la trova non apre né ramo né PR e rende il
  PBI (URL vuoto) o `PR #N` con il suo URL.
- **Se manca:** si cita il PBI o la PR esistente e il progetto si mette in attesa di quello.

### R7 — Il PBI a monte cambia solo il runner

- **Cosa:** la parte a valle (per esempio la sezione `[junit]` di `asdlc.toml` del progetto)
  resta fuori dallo scope del PBI a monte e diventa un PBI del progetto, con `attende:`.
- **Quando:** alla scrittura del PBI.
- **Prova:** lo Scope del PBI a monte non elenca file del progetto; la sezione *Dipendenze*
  del PBI a valle nomina il tag atteso. Il `PBI-505` è la forma di riferimento.
- **Se manca:** il Critic lo segnala come scope largo (`ADR-0015`).

### R8 — Il tag solo per i PBI che lo dichiarano

- **Cosa:** il rilascio dopo il merge a monte.
- **Quando:** a ogni tick di `asdlc`, per ogni PR di PBI `MERGED`.
- **Prova:** il PBI ha `rilascia: patch` o `rilascia: minor`; la CI su `main` è verde; il tag
  non esiste già.
- **Se manca:** nessun tag; un PBI senza `rilascia:` non produce rilascio, ed è il caso dei
  PBI di documentazione.

- **Dove sta:** `coda.rilascia()`, chiamata dal tick dopo `allinea()` (non con `--dry-run`).
  Cerca le PR mergiate (`gh pr list`), legge `rilascia:` dal PBI nel checkout, chiede la CI
  (`gh run list`) e salta il PBI il cui merge è già contenuto in un tag (`git tag --contains`).
  Il tag è `[rilascio].prefisso_tag` + `X.Y.Z`, successivo all'ultimo: `patch` alza Z, `minor`
  alza Y e azzera Z. Senza `rilascia:` in nessun PBI non chiede niente al mondo.
  Un errore del passo (un worktree che non si crea, un JSON di `gh` illeggibile) non esce dal
  tick: `rilascia()` rende una riga `rilascio: avviso, …` e il tick prosegue (`ADR-0008`).
  Un `git tag` o un `git push` del tag che esce ≠ 0 non è un rilascio: la riga è
  `rilascio: avviso, …` e non `rilascio: <PBI> → <tag>`, e il tag locale si toglie (`git tag -d`),
  perché i ref sono del checkout e un tag rimasto farebbe saltare il PBI al tick dopo, con
  `origin` senza tag.

### R9 — Il giro del tag lavora in un worktree usa-e-getta

- **Cosa:** `--registra` e il tag.
- **Quando:** al rilascio.
- **Prova:** i comandi girano in un worktree separato dal checkout del tick; il checkout
  del tick resta pulito.
- **Se manca:** il tick si ferma con un avviso (un albero sporco ferma già il tick).

- **Dove sta:** `runner.worktree_di_rilascio()`, un worktree staccato in una cartella
  temporanea fuori dal checkout, tolto anche se il corpo alza. `--registra` legge i rapporti
  del checkout; le righe che scrive restano nel worktree e spariscono con lui.

### R10 — Il progetto vede il tag e propone il pin

- **Cosa:** i PBI fermi con `attende: <repo>#<PBI>`.
- **Quando:** a ogni tick del progetto.
- **Prova:** la PR a monte è `MERGED` (verificato con `gh pr view`, mai sulla parola) e
  il tag che la contiene esiste.
- **Se manca:** il progetto resta in attesa. Quando c'è, apre una PR che cambia solo la riga
  `[ambiente].installa` di `asdlc.toml`; la parte specifica del progetto è del PBI a valle.

- **Dove sta:** `coda.pin()`, chiamata prima della pausa (non con `--dry-run`). `coda.attese()` legge la riga `attende:` da `backlog/` del checkout e dai
  rami `pbi/*` su `origin`, perché il runner la committa sul ramo del PBI fermo e non in `main`.
  Dei rami legge solo quelli non ancora in `origin/main` (`for-each-ref --no-merged`) e, di
  ciascuno, solo i file di `backlog/` che il ramo cambia rispetto a `main`
  (`git diff --name-only main...<ramo>`, poi `git show origin/<ramo>:<file>`): le copie ferme
  di altri PBI riporterebbero bersagli superati. Si conta una volta la stessa riga, cioè la
  terna (file, repo a monte, PBI a monte); se lo stesso PBI ha in `main` e sul ramo due righe
  con bersagli diversi, si contano entrambe. Considera solo
  i PBI fermi: ramo su `origin` e nessun merge, perché il file con `attende:` resta in
  `backlog/`. Il tag è il primo di `gh api repos/<repo>/tags` che contiene il merge
  (`compare`: `ahead` o `identical`). Il ramo è `pin/asdlc-<tag>`; con una PR già su quel
  ramo, in qualunque stato, non se ne apre un'altra. Un errore del passo (un JSON di `gh`
  illeggibile) non esce dal tick: `pin()` rende una riga `pin: avviso, …` e il tick prosegue
  con gli altri passi e gli altri progetti (`ADR-0008`).
  Un passo della PR (`git switch -c`, `git commit`, `git push`, `gh pr create`) che esce ≠ 0 dà
  `pin: avviso, …` e non «PR del pin a <tag>»; il ramo, locale e su `origin`, si toglie, così il
  tick dopo riparte da zero.

### R11 — La pausa si toglie solo a pin mergiato

- **Cosa:** la ripartenza del PBI fermo.
- **Quando:** a ogni tick del progetto, dopo R10.
- **Prova:** la PR del pin è `MERGED`, verificata con `gh pr view`.
- **Se manca:** la pausa resta.

- **Dove sta:** `coda.stato_del_pin()`, che chiede lo stato a `gh pr view`. Solo `MERGED` toglie
  `~/asdlc-tick.pausa`; `OPEN`, `CLOSED` o un `gh` muto la lasciano.
- **Il merge non è del tick:** né `rilascia()` né `pin()` emettono mai `gh pr merge`. Lo prova un
  test che li esegue davvero con un finto `gh` e guarda i comandi emessi (R10-R11).

### R12 — Il ciclo ha un tetto, e Francesco è l'ultimo

- **Cosa:** i giri Solver↔Builder per lo stesso blocco (massimo 3), e gli esiti `intento`.
- **Quando:** a ogni giro del Solver.
- **Prova:** un contatore nel rapporto del giro; l'esito `intento`.
- **Se manca / si supera:** il giro si ferma con un avviso a Francesco (`ADR-0008`). Una
  decisione che fa precedente si scrive nel registro dei precedenti (`backlog/PRECEDENTI.md`), che il Solver legge
  prima di chiedere.

### La traccia delle sessioni (`PBI-511`)

Il runner lancia Builder, Critic e Solver con `claude -p --session-id <uuid>`, un uuid per
invocazione, e lo scrive nel rapporto del giro. A fine invocazione copia il `.jsonl` che Claude
Code ha scritto per quella sessione in `runs/`, accanto agli altri file del giro: la cartella di
Claude Code è fuori dal repository e può essere ripulita. Il rapporto dice, per ogni invocazione,
quante chiamate a strumento, risposte e blocchi `thinking` la traccia contiene, così che una
traccia senza ragionamenti si veda subito. Se il file non c'è, il rapporto lo dice e il giro non
si ferma (`ADR-0008`).

### R13 — La guardia di processo è codice

- **Cosa:** che R1-R12 siano state rispettate.
- **Quando:** alla chiusura del giro e a ogni tick.
- **Prova:** letta da campi del rapporto, da git e da `gh`; mai da un modello.
- **Se manca:** si segnala nel rapporto e nell'avviso; il flusso non si blocca. Il giudizio
  sulla diagnosi del Solver non è nella guardia: lo dà il Critic.
- **Dove sta:** `guardia_del_solver()` scrive in `Esito.guardia` la sezione `## Guardia di
  processo`, una riga per regola (`ok`, `violata`, `non eseguita`). Un giro senza Solver non
  ha la sezione. R4 si legge dalla traccia del Solver (v. «La traccia delle sessioni»); R5-R7
  leggono la PR a monte (git e `gh`) e sono `non eseguita` senza PR o se `gh` o git non
  rispondono, scadono o rendono un'uscita illeggibile. R5 vuole anche che la testa della PR
  stia su un fork: se sta in `asdlc` è `violata`, se il fatto manca è `non eseguita`. R5 non
  segue le rinomine: spostare `AGENTS.md` o un ADR esistente lo cancella dal suo posto ed è
  `violata`. R6 confronta la `causa` a parola intera (`runner-xy` non è `runner-x`) e chiede
  a `gh` fino a 1000 PR aperte: se la lista torna piena non ha visto tutto ed è `non eseguita (lista troncata)`. R7 legge tutti i percorsi di
  ogni riga dello Scope e riconosce un file del progetto dai fatti: un percorso dello Scope che non sta nell'albero di `asdlc` al ramo
  della PR, né nella sua prima cartella, oltre alla dicitura «del progetto» per `asdlc.toml`.
  Ogni riga `violata` o `non eseguita` è anche un avviso nella nota del giro. Il Critic
  rilegge l'output del Solver e non rifà questi controlli.

## Il tick è sempre attivo

- **Meccanismo:** un cron per progetto, come oggi (`asdlc-coda`), più un timer che recupera i
  tick persi quando il PC riparte.
- **Battito:** a ogni passaggio — anche in pausa, anche senza lanciare niente — il tick scrive
  l'ora in ISO su una riga in `~/asdlc-tick.battito`, accanto a `~/asdlc-tick.pausa`; se il file
  è più vecchio di una soglia (`[tick].soglia_battito_minuti`, default 30), l'avviso parte: al passaggio dopo, il tick legge il
  battito precedente e, se il distacco supera la soglia, scrive l'avviso a schermo e in
  `coda.log` prima di fare altro. Il passaggio prosegue (`ADR-0008`).
- **Limite dichiarato:** se il PC è spento o in sospensione, la coda si ferma e riprende da
  sola alla ripartenza. Un server sempre acceso è un'alternativa da rivalutare se i progetti
  crescono.

## Decisioni di Francesco (16/10/2026)

Le cinque domande aperte dell'ADR sono chiuse così.

1. **Tetto dei giri:** 3 giri Solver↔Builder per lo stesso blocco (R12). Al quarto, o a ogni
   esito `intento`, il giro si ferma con un avviso.
2. **Soglia del battito:** 30 minuti senza che il tick scriva il file.
3. **Registro dei precedenti:** `backlog/PRECEDENTI.md`, append-only, una riga per decisione
   (data, causa, sentenza). Il Solver lo legge prima di chiedere.
4. **Permesso:** il Solver spinge su un fork di `asdlc` e apre la PR dal fork, con la
   credenziale `gh` del proprietario. Nessun permesso di scrittura su `asdlc` (R5). Il merge
   resta di Francesco.
5. **Cause `runner-*`:** l'elenco unico vive in `backlog/README.md` di `asdlc`, che possiede
   il runner. I progetti lo citano (URL pinnato al tag) e tengono solo le proprie cause. Si
   allarga con un ADR (`ADR-0030` §2).
