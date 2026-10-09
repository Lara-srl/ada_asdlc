# PBI-102: il runner distingue «respinto» da «non convergente»

## Direttiva

`tools/asdlc_runner.py` ha `MAX_REVISIONI = 2`: oltre due giri di Critic, il PBI si chiude
`respinto` con la nota *«il PBI non era pronto»*. La soglia era un'ipotesi, e ora c'è una
misura che la smentisce.

**Il dato.** PBI-201 ha richiesto **sei** revisioni, e ognuna ha trovato una classe di
difetto che la precedente non poteva vedere:

| giro | rilievi | il più grosso |
|---|---|---|
| 1 | 3 | dati veri committati, con la casella «nessun dato reale» spuntata |
| 2 | 6 | un contratto che nessun test presidiava: un rename lasciava la suite verde e rompeva il margine su ogni pratica |
| 3 | 6 | la costituzione emendata dentro il PBI che ne beneficiava |
| 4 | 4 | **il criterio centrale del PBI si skippava su ogni runner** |
| 5 | 4 | una decisione autocertificata da chi ne traeva vantaggio |
| 6 | 5 | la regola contro l'autocertificazione, autocertificata |

Con `MAX_REVISIONI = 2` il runner avrebbe chiuso al terzo giro, cioè **con il golden che
non girava in CI e una regola cambiata di nascosto** — e avrebbe scritto «il PBI non era
pronto», che è vero ma dice la cosa sbagliata: il PBI era scritto bene, era il lavoro a
non essere finito.

**Due cambiamenti, e il secondo conta più del primo:**

1. **`MAX_REVISIONI = 4`.** Un tetto più alto, tarato sulla misura invece che sull'ipotesi.

    **Causa:** `soglia-non-misurata`

2. **Uno stato `non convergente`, distinto da `respinto`.** Sono due diagnosi diverse:
   *respinto* = il PBI non era pronto a partire; *non convergente* = serve una persona, e i
   rilievi rimasti sono questi. Oggi il runner li confonde, e chi legge `runs/tempi.csv`
   non distingue un PBI scritto male da uno difficile.

    **Causa:** `diagnosi-confusa`

**Altri due difetti dello stesso strumento**, misurati la notte del 20→21/08 e senza i
quali il tetto più alto serve a poco:

3. **Un rilievo indirizzato all'umano deve sospendere, non consumare revisioni.** Il runner
   ha già il ramo giusto — *«fermato: domanda dell'agente»* — ma può attivarlo solo il
   **builder**. Quando è il **Critic** a produrre un rilievo che nessuna fix può chiudere,
   perché la risposta è di una persona, il builder non ha vie d'uscita: rende il rilievo più
   visibile, il runner conta un giro e riparte. È successo a PBI-203 sul `CHIEDI` mancato
   della migrazione `0011` — violazione *ex ante*, quindi non annullabile da chi l'ha
   commessa: **cinque giri, 1h26m, 22 commit, per finire dove si era al primo.** Il PBI era
   completo e verde già allora. Chiudere `non convergente` è meglio di `respinto`, ma la
   diagnosi giusta è una terza: *sospeso, aspetta una persona* — la stessa che il ramo del
   builder produce già, raggiunta dall'altro lato.

    **Causa:** `diagnosi-confusa`

4. **`git switch -c` parte da dove si trova e non torna su `main`.** In un'unica invocazione
   con più PBI il secondo nasce dal branch del primo, e le PR si impilano. Il difetto è noto
   da prima della run — è la ragione per cui `ada-notte.sh` esiste come ciclo esterno invece
   di passare i quattro PBI al runner in un colpo — ma finora è stato scritto solo nei
   commenti di quello script, cioè in nessun posto che il repository conosca. Questo PBI lo
   dà per noto senza nominarlo: adesso è nominato.

    **Causa:** `due-fonti`

**Un quinto difetto, misurato il 23→24/08 su PBI-207**, che i primi quattro non coprono
perché non riguarda *come si giudica* un giro ma *cosa sopravvive* a un giro:

5. **Il lavoro diventa durevole solo per la via del successo.** `git push` esiste in un
   posto solo — la prima riga di `apri_pr` — e `apri_pr` si chiama solo su `fatto`. Ogni
   altro esito (`non convergente`, `sospeso`, `fermato`, `rosso`) lascia il branch **solo
   locale**, dentro il worktree `ada-run`. Sono anche gli esiti in cui il lavoro vale di
   più, perché nessuno l'ha ancora guardato: **7 righe su 9** del registro sono di quel
   tipo. PBI-207 l'ha mostrato in scala — 2h21m, 37 commit, tutti i gate verdi a ogni giro
   — esistiti su un disco solo finché non li si è pushati a mano il mattino dopo. Una
   pulizia del worktree, e sarebbero stati la spesa più cara mai buttata dal runner.

   **Stessa radice per il registro.** `scrivi_tempi` fa un append e nessuno committa: in
   tutto il file non c'è un `git("add")`. La riga resta appesa non committata al branch del
   PBI, e il giro dopo riparte da `origin/main`. Le righe di PBI-211, PBI-309 e della
   seconda run di PBI-207 sono finite su un branch di servizio invece che nel registro; la
   riga della terza run era ancora non committata il mattino dopo. Il registro su `main` ne
   conta **sei su nove**, e la run di PBI-211 del 23/08 non ha una riga da nessuna parte:
   ne resta solo il rapporto JSON, fuori dal repository. Il registro è la misura su cui
   questo stesso PBI si legge.

   **Le cinque righe perse sono state ricostruite il 24/08** dai rapporti JSON di
   `~/ada-rapporti`, che portano gli stessi campi del CSV. Ricostruibili **finché quella
   cartella esiste**: è fuori dal repository, e non è un backup — è l'ultima copia. La
   ricostruzione non chiude questo punto, lo misura: un registro che va rifatto a mano
   dopo ogni notte non è un registro.

   Le due cose hanno lo stesso rimedio: **il runner non può avere il salvataggio agganciato
   al ramo del successo**. Il `push` esce da `apri_pr` e si fa a fine PBI qualunque sia
   l'esito; il commit del CSV si fa a fine invocazione, sul branch dell'ultimo PBI o su uno
   di servizio, purché finisca da qualche parte che non sia un disco solo.

    **Causa:** `chiusura-saltata`

**Un sesto difetto, misurato il 24/08 su PBI-208** — e questo non costa giri, costa il
PBI intero:

6. **Un giro speso a chiedere un commit conta come un gate rosso.** Sono due cose opposte:
   un gate rosso dice *«hai sbagliato una riga»*, un albero sporco dice *«il lavoro c'è ma
   non è durevole»*. Il runner li somma su `MAX_TENTATIVI`, e su PBI-208 il conto è
   finito così: il Builder aveva committato con `git commit -am` — che i file **non
   tracciati non li prende** — e `AnalisiPage.tsx`, la pagina intera, 840 righe, è rimasta
   fuori da ogni commit. Tre giri consumati sul controllo d'igiene, **zero gate eseguiti**,
   e il PBI chiuso `rosso` in dieci minuti con la nota *«gate ancora rossi dopo i tentativi
   previsti»* e `gate_rossi` vuoto: una diagnosi falsa, che manda a cercare il guasto dove
   non è. Il file era ancora nel worktree il mattino dopo, a un `git add` dal non esistere;
   la catena si è fermata lì, e PBI-204 è stato saltato dall'igiene di `ada-notte.sh` per
   quello stesso file.

   Tre rimedi, uno per anello: i giri d'igiene hanno un tetto **loro** (`MAX_IGIENE`) e non
   toccano quello dei gate; l'esito di un albero che resta sporco è `fermato` con la nota
   che dice *cosa* è rimasto fuori, perché una nota falsa è peggio di nessuna nota; e il
   prompt che chiede il commit nomina il `git add`, visto che è esattamente lì che il
   Builder si è perso. Il controllo dentro il giro esclude `runs/` come già fa quello
   d'ingresso — nella catena, il secondo PBI si sentiva chiedere di committare la
   contabilità del runner dentro il proprio branch.

    **Causa:** `diagnosi-confusa`

**Un settimo e un ottavo difetto, misurati il 24/08 su PBI-209 e PBI-214.** Non costano
giri né PBI: costano il **lancio**, cioè arrivano prima che il Builder parta.

7. **Il runner cerca il PBI nell'albero estratto, e poi ramifica da `origin/main`.** Sono due
   fonti diverse, e la prima è quella vecchia. Il worktree `ada-run` era rimasto su un branch
   di ieri; `PBI-214` era su `main` da mezz'ora, ed è stato liquidato con *«saltato (PBI
   inesistente in `backlog/`)»* — una diagnosi che manda a cercare un file mancante invece
   che un albero indietro. Il rimedio è leggere il PBI **da dove si ramifica**, non da dove
   ci si trova: `git show origin/main:backlog/PBI-XXX-*.md`, oppure il controllo d'esistenza
   spostato **dopo** `crea_branch`. È lo stesso errore di categoria del difetto n°1 — il
   runner che si fida di dove sta l'albero — e infatti la fix di quello (`switch -c` da
   `origin/main`) l'ha spostato qui invece di eliminarlo.

   🔁 **Rimisurato il 27/08/2026 su PBI-325, identico.** `ada-run` era fermo su
   `pbi/pbi-321` — cioè dove il giro precedente l'aveva lasciato, che è il caso **normale**,
   non una svista — e PBI-325 era su `main` da un'ora. Stessa riga: *«saltato (PBI
   inesistente in `backlog/`)»*. Tre giorni e due lanci bruciati sullo stesso difetto,
   e la seconda volta ha una circostanza che la prima non aveva: **esce con codice 0**.
   Il riepilogo dice *«1 PBI · tempo totale 0:00:00»*, scrive il rapporto JSON e la riga
   in `runs/tempi.csv`, cioè un giro andato a vuoto è indistinguibile da un giro riuscito
   per chiunque legga l'exit code invece dell'output — un `&&` in una catena, un cron, o
   chi lancia e torna dopo mezz'ora. Un `saltato` per albero indietro non è un esito: è il
   lancio che non è avvenuto.
   Il rimedio non cambia (leggere il PBI da dove si ramifica), e va con un exit code che
   distingua *«il PBI non esiste»* da *«non l'hai ancora tirato giù»*.

    **Causa:** `due-fonti`

8. **Un PBI fermato lascia il suo branch, e al rilancio il runner muore sopra.**
   `git switch -c pbi/pbi-209 origin/main` → *«esiste già un ramo denominato
   'pbi/pbi-209'»*, `RuntimeError`, e la catena si ferma prima del primo PBI. Chi rilancia
   dopo un `fermato` — che è il caso **normale**: si risponde alla domanda e si riparte —
   trova lo strumento rotto per una ragione che non c'entra col PBI. Due cose da decidere
   insieme, perché la seconda è quella che morde:
   - il nome del branch si disambigua (`-giro-2`) o il branch esistente si riusa, e il
     runner dice quale delle due sta facendo;
   - ⚠️ **quel branch non è vuoto.** Su PBI-209 conteneva **8 commit e 2.174 righe** — la
     rotta, il modulo di scenario, il pannello, i test — e non era **mai stato pushato**:
     era a un `git branch -D` dalla sparizione, esattamente come PBI-205 il 21/08. Un
     `fermato` deve **pushare il branch** prima di uscire, anche senza aprire la PR: il
     lavoro che non è su `origin` non esiste, e il runner oggi lo lascia dove nessuno lo
     cerca. Questo vale più della disambiguazione del nome.

    **Causa:** `residuo-di-un-giro`

**Un nono difetto, misurato il 25/08 su PBI-212 — ✅ già chiuso, e sta scritto qui perché
il registro dei difetti valga come registro.** Non costa giri e non costa il lancio: costa
l'*integrità dell'albero*, che è la cosa più cara delle tre.

9. **Il worktree non aveva un lucchetto.** Il builder del runner (PID 797788) e un agente
   avviato a mano un minuto prima (PID 797078) sono finiti sullo stesso `ada-run` sullo
   stesso branch `pbi/pbi-212`, e il secondo ha committato in `bb602b8` due modifiche non
   committate del primo. Il runner **se n'è accorto e si è fermato** — `fermato` in 7:23,
   con la domanda giusta — ma se n'è accorto *guardando i file*: niente glielo aveva
   impedito. Due processi che scrivono lo stesso albero si sovrascrivono a vicenda e i
   commit escono mescolati; qui il danno è stato nullo per fortuna, non per costruzione.
   Il rimedio è doppio perché i casi sono due, e il controllo ovvio copre quello che **non**
   è successo:
   - un `flock` sul worktree tiene fuori un **secondo runner**. Del processo e non del file:
     un PID su disco dopo un `kill -9` resta a bloccare il lancio dopo, e cancellarlo a mano
     è il gesto che diventa automatico e disinnesca il controllo;
   - `agenti_estranei()` guarda `/proc/<pid>/cwd` e tiene fuori il caso **vero**, che è
     l'altro: una sessione avviata a mano, che di un lucchetto del runner non sa niente.
     L'unico segnale comune ai due processi è dove lavorano.

   ⚠️ Il controllo d'ingresso sull'albero sporco c'era già e **non ha visto niente**: al
   momento del lancio l'altro agente non aveva ancora scritto. Un controllo sullo *stato*
   dei file non può cogliere un processo che sta per scriverli — serviva guardare i
   processi, non l'albero. È la stessa differenza fra il difetto n°6 e questo.

    **Causa:** `concorrenza-non-esclusa`

**Un decimo, un undicesimo e un dodicesimo difetto, misurati il 25/08 lanciando quattro PBI
di fila.** Nessuno dei tre costa un giro: costano la **traccia** di quel giro — cioè la cosa
che il registro esiste per tenere.

10. **Un `fermato` dichiara sempre `commit = 0`.** `Esito.commit` si calcola dopo il ciclo dei
    gate (`git rev-list --count origin/main..HEAD`), e un `fermato` del Builder esce **prima**
    di arrivarci. Su PBI-315 il registro ha scritto `0` mentre sul branch c'erano **10 commit**
    — modello, migrazione, `PATCH`, riquadro, contratto E2E, spec. È la stessa famiglia del
    difetto n°8 — *«un fermato non vuol dire a mani vuote»* — ma più insidiosa: al branch uno
    ci va a guardare, al CSV crede. Il conteggio va fatto **prima** di ogni uscita, non dopo
    i gate.

    **Causa:** `chiusura-saltata`

11. **Un gate che non trova il suo strumento fa esplodere il processo.** `esegui()` non
    intercetta `FileNotFoundError`: lanciato senza `backend/.venv` sul `PATH`, il giro è morto
    con un traceback su `pytest` — **nessuna riga in `runs/tempi.csv`, nessuna PR**, e il
    lavoro del Builder rimasto su un branch **locale**. Un gate rosso è un risultato; questo è
    un guasto dello strumento, e deve somigliare a un guasto: catturarlo, chiudere `rosso` con
    la diagnosi giusta, e **scrivere comunque la riga del registro**. Un giro senza traccia è
    un giro che non è mai esistito.

    ⚠️ **Ma il rimedio vero è a monte: il venv se lo mette il runner.** `backend/.venv/bin` sta
    a un percorso noto rispetto a `REPO`, che il runner già calcola da sé. Metterlo in testa al
    `PATH` dei sottoprocessi è una riga, e toglie di mezzo la classe intera invece di
    diagnosticarla meglio. Oggi quella riga vive **fuori dal repository**, dentro
    `/home/laisdev/ada-notte.sh` (`export PATH="$WT/backend/.venv/bin:$PATH"`) — ed è il motivo
    per cui le run notturne non l'hanno mai incontrato e un lancio diretto sì: **lo stesso
    runner si comporta in due modi a seconda di come lo si chiama**, che è la cosa da togliere.

    **Causa:** `chiusura-saltata`

12. **L'URL della PR si legge per posizione.** `apri_pr` prende `out.strip().splitlines()[-1]`,
    cioè l'ultima riga di `gh pr create`. Su PBI-316 `gh` ha stampato un warning **dopo**
    l'indirizzo e nel registro è finito `Warning: 1 uncommitted change` al posto dell'URL: la
    PR esisteva (#82), per il registro no. Si estrae **per forma** — la riga che comincia con
    `https://github.com/` — non per posizione.

    ⚠️ **Rivisto il 26/08: non è che `gh` stampi il warning «dopo».** L'URL esce su stdout e
    gli avvisi su stderr, e l'ordine con cui si mescolano nella cattura **non è garantito**.
    Nella stessa invocazione del 26/08 il registro ha preso l'URL giusto su PBI-317 e il
    warning su PBI-318 e PBI-319 — stesso runner, stesso albero, stesso minuto. Aprendo la
    PR #94 a mano l'ordine era di nuovo l'altro, col warning **prima** dell'indirizzo. Quindi
    non c'è una posizione «di solito giusta» da cui leggere: l'estrazione per forma non è un
    irrobustimento, è l'unica lettura corretta.

    ⚠️ **E il warning lo causa il runner stesso.** `runs/tempi.csv` resta non committato dopo
    ogni invocazione: `gh` avvisa che ci sono modifiche pendenti, e alla successiva quel file
    blocca perfino il cambio di branch (*«le tue modifiche locali sarebbero sovrascritte»*).
    Recuperato a mano **tre volte** il 25/08.

    **Il rimedio, deciso da Francesco il 25/08: il registro esce dall'albero di lavoro.** Il
    runner scrive in append su un percorso **fuori dal repository** — resta un CSV, che si
    legge e si diffa — e `runs/tempi.csv` versionato diventa una **copia che aggiorna
    Francesco a mano quando serve**. Il commit smette di essere l'effetto collaterale di un
    giro e torna a essere un gesto di una persona.

    Perché non «committarlo sul branch del PBI», che era il rimedio scritto qui prima: quella
    riga è **contabilità**, non prodotto, e finirebbe dentro il diff di una feature — o su un
    branch abbandonato, se il giro chiude `fermato`. Su `main` non si può committare
    direttamente (ruleset), quindi non esiste un posto giusto **dentro** git che il runner
    possa scegliere da solo.

    ⚠️ Anche questo esiste già fuori dal repository: `ada-notte.sh` porta il registro in
    `~/ada-tempi-notte.csv` e i rapporti del Critic in `~/ada-rapporti/`. Vale la stessa
    diagnosi del difetto 11 — **la logica del runner sta in due posti, e uno dei due non è
    versionato**. Rientra nel runner, che è dove Francesco vuole che stia tutta.

    **Causa:** `strumento-letto-come-testo`

**Un tredicesimo e un quattordicesimo difetto, misurati il 26/08 su PBI-320.** Il primo fa
fallire un PBI che non ha niente che non va; il secondo impedisce di capire perché.

13. **Il gate e2e, da un worktree, prova un altro checkout.** `Gate("e2e", ["npm", "run",
    "e2e"], cwd="e2e")` lancia Playwright, che punta a `localhost:8081` — e da un `git
    worktree` quello è lo stack del **checkout principale**, non del branch. Su PBI-320 il
    gate è caduto tre volte su «element(s) not found» per campi che sul branch c'erano
    eccome: la suite stava provando `main`. Tre tentativi consumati, `rosso`, e **il Critic
    mai chiamato** — perché il Review Gate vive dopo i gate deterministici, quindi un gate
    che non *può* diventare verde impedisce la revisione avversariale di tutto il lavoro.
    Costo misurato: 33:16 per un PBI il cui codice era sostanzialmente buono.

    Il Builder l'ha diagnosticato da sé e ha reso il prefisso dei container una variabile
    (`ADA_STACK`, commit `3f61923` sul branch di 320), che è la condizione necessaria: con
    `container_name` fissi Docker rifiuta il secondo stack anche cambiando progetto e porte.
    Ma **non basta**, ed è il punto: lo stack va ricostruito **a ogni giro del Builder**,
    perché a ogni giro il codice cambia. Un `E2E_BASE_URL` diverso passato una volta sola
    darebbe un gate verde su una build vecchia — che è peggio di un gate rosso.

    Le uscite sono due, e vanno scelte, non lasciate implicite:
    - il runner alza e **ricostruisce** lo stack del branch prima di ogni giro del gate
      (`ADA_STACK` + `COMPOSE_PROJECT_NAME` + due porte derivate dal nome del PBI), e lo
      smonta all'uscita, `down -v` compreso — costa minuti di build per giro;
    - oppure **e2e non è un gate del runner**: resta il job della CI, che lo stack lo
      costruisce dal branch per definizione, e `--e2e` sparisce dalla riga di comando invece
      di restare una trappola armata.

    ⚠️ Oggi `--e2e` esiste e non dice niente di tutto questo. Chi lo accende ragionando che
    «più gate è più sicuro» ottiene l'opposto: un rosso che non parla del branch. Finché la
    scelta non è fatta, la documentazione del flag deve dirlo — un flag che si può solo
    usare male è un difetto anche prima di essere riparato.

    **Causa:** `due-fonti`

14. **L'output di un gate rosso non finisce da nessuna parte.** `gira_gate()` raccoglie
    `(nome, out[-3000:])` in `rossi` e lo passa **solo al Builder**; nel log resta la sola
    parola `ROSSO` col tempo. Su PBI-320 il log dice `gate e2e … ROSSO (0:00:01)` tre volte
    e nient'altro: la causa — che era la più interessante delle due cose successe quel
    giorno — ho dovuto ricostruirla da fuori, confrontando i browser installati, il parse
    dei file di spec e il timestamp di `e2e/storage/master.json`. Il Critic, che avrebbe
    letto quell'output volentieri, non l'ha mai visto perché non è mai stato chiamato.

    Vale la stessa regola già scritta per il transcript del Builder: di un giro fallito
    deve restare **la ragione**, non il verdetto. La coda dell'output di ogni gate rosso va
    nel log e nel rapporto JSON — che è già il posto dove i rilievi del Critic sopravvivono
    a un `non convergente`.

    **Causa:** `traccia-persa`

15. **Il runner non sa staccarsi dalla sessione che lo lancia.** Nessun `setsid`, nessun
    `start_new_session=True`: il processo resta figlio del terminale, e chiudere quel
    terminale lo uccide a metà giro. Misurato il 26/08 su PBI-322, alla revisione 2: la
    catena era `python3 → bash → claude`, con `SID` della shell chiamante e non suo. Otto
    commit buoni salvati a mano su un branch prima di chiudere, perché il runner non li
    aveva pushati (difetto n°8) e non sarebbe sopravvissuto.

    Chi lo lancia deve saperlo e ricordarsene ogni volta. `ada-notte.sh` lo sa
    (`setsid nohup … < /dev/null &`); chi lancia il runner a mano no. È la stessa forma dei
    difetti 11 e 12 — **lo stesso runner si comporta in due modi a seconda di come lo si
    chiama** — e la stessa cura: se ne occupa lui, con un flag esplicito per il caso in cui
    si voglia il contrario (`--in-primo-piano`, per il debug e per la CI).

    **Causa:** `ambiente-non-dichiarato`

**Un sedicesimo e un diciassettesimo difetto, misurati la notte del 26→27/08 sulla
sequenza `PBI-322 PBI-323`.** Il primo butta via un PBI riuscito; il secondo butta via la
memoria di tutto quello che era successo prima.

16. **Il branch del PBI ha un nome fisso, e un giro fallito lo lascia occupato su `origin`.**
    `crea_branch` scrive `branch = f"pbi/{pbi.lower()}"` (`asdlc_runner.py:516`) e del remoto
    non chiede niente. Il 26/08 alle 21:25 PBI-323 si è chiuso `sospeso` **dopo** aver
    pushato `pbi/pbi-323`; alle 00:22 il giro buono — Critic **PASS** al primo tentativo, 4
    commit — è arrivato ad `apri_pr`, che comincia con `git push -u origin branch` (`:469`),
    e si è preso un `! [rejected] (non-fast-forward)`: stesso nome, storia diversa. `git()`
    alza, e nessuno la cattura: la `RuntimeError` è salita da `esegui_pbi` fino a `main`,
    cioè **traceback e processo morto**.

    Il costo non è il push mancato, è quello che il push si porta dietro: `apri_pr` pusha
    *prima* di chiamare `gh`, quindi di un PBI passato non resta niente sul remoto — nessun
    branch, nessuna PR, e i 4 commit solo nel worktree. Li ho pushati a mano il 27/08 su
    `pbi/pbi-323-giro2` ([PR #102](https://github.com/Lara-srl/ada_controller/pull/102)).

    È il difetto n°8 visto dall'altro lato — là il `fermato` non pushava, qui il `sospeso`
    pusha e non si toglie di mezzo — e la cura è la stessa riga già scritta lì: il nome si
    disambigua al rilancio. Quello che il difetto 8 non copre è il secondo pezzo: **un
    errore su un PBI non deve poter uccidere la sequenza.** Quando fermarsi è già una
    decisione dichiarata (`STATI_CHE_INTERROMPONO`); un traceback la scavalca senza
    prenderla.

    ⚠️ Nella stessa sequenza PBI-322 ha chiuso `non convergente`, e anche i suoi 11 commit
    sono rimasti nel solo worktree. Il difetto 8 nomina il `fermato`, ma la regola che serve
    è più larga: **ogni uscita che lascia commit dietro di sé li pusha**, qualunque sia lo
    stato con cui esce.

    **Causa:** `residuo-di-un-giro`

17. **Il rapporto JSON e il registro si scrivono solo alla fine, quindi un'eccezione li porta
    via tutti e due.** `scrivi_tempi(run, esiti)` e la scrittura di `runs/{run}.json` stanno
    **dopo** il `for` dei PBI (`asdlc_runner.py:822-825`), fuori da qualsiasi `try`. La morte
    del difetto 16 è arrivata sull'**ultimo** PBI della sequenza e si è portata via il primo:
    di 1:13:02 su PBI-322 — cinque giri, cinque rapporti del Critic — in `runs/` non c'è
    niente, e in `runs/tempi.csv` nemmeno la riga.

    Il log dice `→ non convergente (5 revisioni senza convergere — ultimi rilievi del Critic
    nel rapporto JSON. Serve una lettura umana.)`, e manda a leggere un file che non è mai
    stato scritto. La frase è quella giusta — è il difetto n°14 già capito, *di un giro
    fallito deve restare la ragione* — ma sotto non c'è la garanzia che la regge.

    I cinque rapporti li ho recuperati dai transcript in `~/.claude/projects/`: è una
    fortuna, non un piano di ripristino. Sono file di sessione dell'agente, non del runner,
    nessuno ha promesso che restino e nessuna riga di codice li cerca. **Ogni PBI scrive la
    sua riga e il suo rapporto quando finisce lui**, non quando finisce l'invocazione: il
    JSON si riscrive per intero a ogni PBI concluso, `runs/tempi.csv` è già in append.

    **Causa:** `chiusura-saltata`

18. **Il branch si pubblica a metà sequenza e poi si riscrive, quindi il push finale muore e
    in `main` entra il primo giro col nome del PBI intero.** È il difetto n°16 con il segno
    rovesciato: là il push non era mai riuscito e del PBI non restava niente sul remoto; qui
    il push a metà **era** riuscito, e ciò che è arrivato su `main` è un PBI a un quinto.

    PBI-324, il 27/08, un'invocazione sola (`runs/ada-324.log`), letta dal reflog del branch:
    17:47 `branch: Created from origin/main`; 17:50-17:55 i tre commit del giro 1; **17:58 la
    PR [#110](https://github.com/Lara-srl/ada_controller/pull/110) è aperta** con dentro
    quei tre, mentre il runner sta lavorando il giro 2 — `apri_pr` non è ancora stata
    chiamata, a pushare è stato il Builder dentro il giro. Alle 18:07 il branch fa `reset:
    moving to origin/main` e si ricostruisce a cherry-pick e `commit (amend)` — lo scope dei
    messaggi passa da `chiusura` a `officina` — cioè **si riscrive una storia già
    pubblicata**. Dalle 18:09 alle 18:49 arrivano altri dieci commit, il Critic dà **PASS**
    al giro 5 con 13 commit sul branch, e alle 18:59 `apri_pr` fa `git push -u origin
    pbi/pbi-324` e si prende `! [rejected] (non-fast-forward)`: `git()` alza, nessuno la
    cattura, traceback e processo morto. Identica all'ultima riga del difetto 16, e per la
    stessa ragione.

    Il costo, però, è nuovo. La #110 è stata **mergiata** alle 20:58 con i soli tre commit
    del giro 1, e i quattro giri che il Critic ha chiesto sono rimasti nel worktree: in
    `main` è entrato un PBI-324 che toglie la casella del N° preventivo dalla sezione di
    costi e ricavi ma lascia la riga di aiuto sotto a dire *«Il preventivo mandato
    all'assicurazione si scrive qui»* — dentro la sezione dove quel campo non esiste più.
    Non è lavoro invisibile come al 16: è lavoro **parziale che si presenta come intero**,
    con la sua checklist spuntata, e nessuno che lo guardi da GitHub può accorgersene. I
    dieci commit li ho rimessi a mano su `pbi/pbi-324-coda`
    ([PR #111](https://github.com/Lara-srl/ada_controller/pull/111)).

    Le cause sono due e vanno separate. La prima: **il branch di un PBI si pubblica una
    volta sola, quando il PBI è finito**, e a pubblicarlo è il runner (`apri_pr`), non il
    Builder dentro un giro — un branch pushato a metà è una promessa fatta su lavoro che il
    Critic non ha ancora accettato, e qui la promessa è stata riscossa. La seconda: finché
    riscrivere il proprio branch fra un giro e l'altro resta lecito — ed è utile, era una
    correzione di scope nei messaggi — il push finale del **proprio** branch va fatto con
    `--force-with-lease`, e comunque non deve poter uccidere la sequenza (difetto 16, seconda
    parte).

    **Causa:** `due-fonti`

19. **Il registro versionato confligge per costruzione, e il conflitto arriva sul PBI
    sbagliato.** `runs/tempi.csv` è append-only e sta in git: due run che finiscono a cavallo
    di un merge scrivono **la stessa ultima riga del file**, e git non ha modo di saperlo.

    Il 27/08 il branch di PBI-326 è nato da un `origin/main` che non aveva ancora il merge
    della riga di PBI-321: al momento del merge la PR [#118](https://github.com/Lara-srl/ada_controller/pull/118)
    si è presentata `CONFLICTING` su `runs/tempi.csv` — un conflitto che non c'entra niente
    col PBI, su un file che nessuno dei due lavori ha davvero toccato. Risolto a mano tenendo
    le due righe in ordine di `iniziato`.

    Non è il difetto 12 (*il registro si committa a fine invocazione*): quello lo salverebbe
    dalla sparizione, non dal conflitto. Anzi, committarlo **peggiora** la frequenza — ogni
    run porterebbe la sua riga dentro la PR del PBI, e ogni PBI mergiato dopo un altro
    troverebbe la coda occupata.

    Le strade sono due, e vanno decise insieme al 12: **un file per run** — `runs/<run>.csv`,
    o il JSON che già esiste ma è gitignored — con il CSV ricostruito da uno script quando
    serve leggerlo; oppure il registro **fuori dai branch dei PBI**, scritto su `main` da un
    commit suo dopo il merge. La prima toglie il conflitto, la seconda lo sposta dove non
    blocca una PR di lavoro.

    ⚠️ Finché nessuna delle due c'è, chi lancia il runner deve sapere che **il registro è la
    cosa che conflitterà**, e che risolverlo vuol dire tenere tutte le righe: una riga persa
    in un conflitto è un run che non è mai esistito.

    **Causa:** `concorrenza-non-esclusa`

**Un ventesimo e un ventunesimo difetto, misurati la sera del 28/08 su `PBI-329` e sul
worktree nuovo di `PBI-310`.** Il primo è un giro intero che nel registro non esiste; il
secondo è un albero che nasce senza il gate più importante.

20. **Il registro non sa che un giro è cominciato, quindi un giro che muore non è mai
    esistito.** `scrivi_tempi` gira **in fondo** a `main()`: fino a quel momento
    `runs/tempi.csv` non ha nessuna riga per il PBI in corso, e il rapporto JSON nemmeno.
    Un giro che non arriva in fondo — comunque non ci arrivi — non lascia niente dietro di
    sé, e chi guarda il registro il giorno dopo vede solo un buco fra due orari.

    Misurato su **PBI-329**, il 28/08. Il ramo `pbi/pbi-329` nasce da `origin/main` alle
    17:49 (reflog), riceve **diciassette commit** fino alle 18:33 — coppie RED/GREEN
    regolari, e in fondo il commit che spunta la Verifica **5 su 5** — e poi si ferma.
    Niente push, nessuna PR, **nessuna riga in `runs/tempi.csv`** (l'ultima è PBI-328
    `sospeso` delle 17:47) e **nessun `runs/ada-329.log`**: un'ora di lavoro buono che dal
    registro non è mai avvenuta, e che è stata trovata solo cercando i rami locali.

    Perché sia morto non lo dice nessun file, ed è esattamente il punto. L'ipotesi che
    regge le prove è il **difetto 15**: lanciato a mano da un terminale, senza redirezione
    e senza `setsid`, il processo se n'è andato con la sessione — il che spiega anche
    l'assenza del log, che in quel caso era il terminale. Ma resta un'ipotesi, e un
    registro che permette di doverla fare è il difetto vero.

    La cura non è il difetto 12 (*il registro si committa a fine invocazione*): quello
    salva una riga che comunque non è stata scritta. La riga va aperta **all'inizio**, con
    lo stato `in-corso`, e chiusa alla fine — e per non peggiorare il difetto 19 l'apertura
    va nel rapporto per-run (`runs/<run>.json`, già gitignored), non nel CSV condiviso. Un
    giro morto lascia così un JSON senza `finito`, che è tutto ciò che serve per sapere che
    è esistito.

    **Causa:** `chiusura-saltata`

21. **Un albero nuovo nasce senza `pytest`, e niente lo dice prima del lancio.**
    `backend/requirements.txt` è il file del **runtime**: fastapi, sqlalchemy, alembic,
    litellm. `pytest` non c'è, e nessun altro file lo dichiara. Il venv di `~/ada-run` ce
    l'ha perché qualcuno gliel'ha installato a mano, e quella conoscenza non sta da nessuna
    parte.

    Misurato il 28/08 creando `~/ada-run-310` per far girare PBI-310 in parallelo: venv
    nuovo da `requirements.txt`, `npm ci` per il frontend, e il primo gate del runner
    sarebbe morto su `pytest: command not found` **dopo** che il Builder aveva già
    lavorato. È la forma del difetto 11 — *lo stesso runner si comporta in due modi a
    seconda dell'ambiente che lo ospita* — e la cura ha due metà: le dipendenze di test si
    **dichiarano** (`backend/requirements-dev.txt`, o un extra di progetto), e il runner
    **controlla che i comandi dei suoi gate esistano** prima del primo PBI, dove già stanno
    il lucchetto e il censimento degli agenti. Un gate che non può girare va detto in tre
    secondi, non in mezz'ora.

    **Causa:** `ambiente-non-dichiarato`

**Un ventiduesimo difetto, misurato il 29/08 al primo lancio vero dopo le correzioni** —
e non è un difetto ereditato: **l'hanno creato le correzioni stesse**, incontrandosi.

22. **Il runner scrive il proprio log nell'albero, poi si ferma perché l'albero è sporco.**
    Due cose giuste, messe insieme, si annullano. `stacca()` (difetto 15) scrive
    `runs/<run>.log` **prima** di leggere il PBI; il controllo dell'albero sporco guarda
    *tutto* senza eccezioni, perché `ADR-0020` aveva tolto la ragione per cui `runs/` era
    escluso. Ma `.gitignore` ignorava `runs/*.json` e `runs/.runner.lock` — **non**
    `runs/*.log`, che prima di `stacca()` non esisteva. Risultato: ogni giro nasce sporco di
    sé, e si ferma su `albero di lavoro sporco: committa o pulisci prima` **in sei secondi**,
    prima di aver letto una riga del PBI.

    Misurato su **PBI-330** alle 22:52 del 29/08 — `runs/20260829-225259.json`, `fermato`,
    tempo totale `0:00:00`. Non è una fermata rara: è **ogni** giro, per sempre, su qualunque
    PBI e in qualunque worktree. Il runner era inutilizzabile dal merge di `#138`, e nessuno
    dei suoi 83 test lo diceva perché il difetto non vive nel codice — vive fra il codice e
    `.gitignore`, cioè in un file che i test del runner non guardano.

    La cura è una riga: `runs/*.log` nel `.gitignore`, accanto al rapporto JSON di cui è il
    gemello effimero. Ma la lezione è più grande della riga, ed è la stessa del difetto 11:
    **due correzioni verdi ciascuna possono essere rosse insieme**, e l'unica prova che
    l'assenza di quel rosso la dà è un giro vero. Le 21 correzioni erano verdi sui test da
    otto ore; ci è voluto un lancio di sei secondi per trovare la ventiduesima.

    **Causa:** `scrittura-non-ignorata`

23. **`nome_libero()` chiede i nomi occupati a `origin`, e il branch locale non lo sente.**
    Il difetto 16 aveva tolto il nome fisso: `rami_su_origin()` fa `git ls-remote` e il giro
    successivo prende `-giro2`. Ma guarda **solo** il remoto, e la sua docstring dice perché
    — *«il worktree del runner è appena stato creato, e di un giro fallito tre giorni fa non
    sa niente»*. Vale per il worktree; non vale per il **repository**, che i worktree si
    dividono: un branch locale creato in `ada_controller` esiste anche in `ada-run`, e
    `git switch -c` lo trova quando `ls-remote` non l'ha visto.

    Misurato su **PBI-103** alle 23:59 del 30/08 — `runs/20260830-235934.json`, `rosso`,
    `0:00:00`, `tentativi: 0`. Il branch `pbi/pbi-103` era nato in un altro worktree per
    scrivere il PBI, era stato pushato, e GitHub l'aveva **cancellato al merge**: dal lato
    di `origin` il nome risultava libero, dal lato locale era occupato. È la combinazione
    normale — si scrive il PBI su un branch, lo si mergia, si lancia il runner su quel PBI —
    quindi capiterà a ogni PBI che nasce così.

    La cura è dire a `nome_libero()` anche i rami locali: `git branch --list "pbi/{pbi}*"`
    accanto a `ls-remote`, unione dei due insiemi. Vale anche il verso opposto — un branch
    locale che nessuno ha pushato non deve essere sovrascritto, ed è lo stesso lavoro perso
    del difetto 8. La lezione è quella di sempre qui dentro: **il runner ha due nozioni di
    «occupato» e ne consulta una**, e la prova che le due coincidano non c'è mai stata.

    **Causa:** `due-fonti`

**Un ventiquattresimo difetto, misurato la notte del 30→31/08 sullo stesso `PBI-103` del
ventitreesimo, e con la stessa radice dal lato opposto:** il ramo che GitHub cancella al
merge. Il 23 impediva al giro di **cominciare**; questo gli impedisce di **lasciare
qualcosa**.

24. **`pubblica()` usa un lease che il remoto non può più onorare, e il giro muore muto.**
    `pubblica()` fa `git push --force-with-lease -u origin <branch>` senza valore: il lease
    implicito è il remote-tracking locale, `refs/remotes/origin/pbi/<pbi>`. Se quel ramo su
    `origin` è stato **cancellato al merge**, il ref locale resta lì a puntare al vecchio
    commit — `git fetch origin main` non lo tocca, e senza `--prune` nessun fetch lo
    toglierebbe comunque. Il lease pretende allora un valore che sul remoto non esiste più,
    e il push si rifiuta con `! [rejected] (stale info)`.

    Misurato su **PBI-103** all'1:33 del 31/08 — `runs/20260831-001458.json`, `sospeso`,
    1h18m, **22 commit**. Il Critic aveva chiuso con una domanda di costituzione, quindi la
    strada era quella giusta: `chiudi()` chiama `pubblica(branch)` proprio perché *«un giro
    che si ferma ha comunque prodotto commit, e lasciarli solo nel worktree vuol dire non
    farli guardare a nessuno»* (difetto 8). Il push è morto, e i 22 commit sono rimasti nel
    worktree — l'esatta situazione che il difetto 8 esisteva per non far succedere più.
    `git push -u origin pbi/pbi-103` a mano ha risposto `* [new branch]` senza obiezioni: il
    remoto era libero, era il **lease** a essere fermo a tre ore prima.

    Non è raro né sfortunato: è la stessa combinazione normale del difetto 23 — si scrive il
    PBI su un branch, lo si mergia, si lancia il runner su quel PBI — vista dopo un giro
    invece che prima. Capiterà a ogni PBI che nasce così **e** si ferma.

    La cura sta dove il runner sa già la verità: `rami_su_origin()` fa `ls-remote` e vede il
    remoto com'è adesso. Se il ramo lì non c'è, il push è una creazione e va fatto semplice;
    se c'è, il lease va scritto **esplicito** col `sha` che `ls-remote` ha appena dato
    (`--force-with-lease=<branch>:<sha>`), che è anche più stretto dell'implicito. In nessuno
    dei due casi si passa a `--force` cieco: la protezione del difetto 18 — *«se qualcun
    altro ha scritto su quel ramo il push si rifiuta lo stesso»* — resta intera, ed è la sola
    cosa che il lease deve difendere.

    E la lezione è **letteralmente** quella del difetto 23, una riga più su: il runner ha due
    nozioni dello stato di `origin` — `ls-remote`, che è viva, e i remote-tracking, che sono
    di quando è stato fatto l'ultimo fetch di quel ramo — e ne consulta una per decidere e
    l'altra per agire. Finché le due non si parlano, ogni ramo cancellato sul remoto è una
    trappola che scatta una volta prima del giro e una volta dopo.

    **Causa:** `due-fonti`

**Un venticinquesimo e un ventiseiesimo difetto, misurati il 31/08 su `PBI-333`, e
diversi in natura da tutti quelli sopra:** qui il Builder non ha sbagliato niente. Cinque
commit, `test (RED)` → `feat` → `test (RED)` → `feat` → `test(e2e)`, coppie perfette: il
ciclo TDD fatto da manuale. Il gate ha fermato **tutti e due i RED**, per due ragioni
diverse, e la radice comune è una sola: **il gate legge il frontend con gli strumenti del
backend**, e dove i due non coincidono legge male invece di dire che non sa leggere.

Misurati su `runs/20260831-173623.json` — `PBI-333`, `fermato`, 16m43s, 5 commit, gate
2m33s, **critic 0:00:00**. Quest'ultimo numero è la parte che costa: il `fermato` scatta
*prima* del Critic, quindi rilanciare lo stesso PBI lo ferma di nuovo allo stesso punto e
il lavoro non arriva mai a essere giudicato. Finché i due difetti stanno in piedi, **ogni
PBI di frontend fatto bene è bloccato** — 333 e 334 compresi.

25. **Un file di test che non si carica è il RED più comune del frontend, e il gate lo
    legge `nessuno`.** A `bb7e562` esiste `FoglioPage.test.tsx` e non esiste
    `FoglioPage.tsx`: il test-first alla lettera. Vitest fallisce il file **prima** dei
    test, quindi nel json non c'è nessun `assertionResult` — `esiti_di_vitest` torna `{}` —
    e col `--reporter=json` nemmeno un conteggio a schermo, quindi `leggi_esito` non trova
    né `passed` né `failed` e conclude `nessuno`. Sedici test nati rossi, letti «rosso non
    isolabile».

    Il gemello in Python è trattato **all'opposto, e di proposito**: `leggi_esito` lo
    scrive in chiaro — *«un errore conta come rosso: il caso più comune di test-first in
    Python è un `from app.x import y` che a quel commit non esiste ancora»*. È
    letteralmente lo stesso caso, e in TypeScript era illeggibile.

    La cura sta dove la verità è scritta: nel json il file compare `failed` con zero
    `assertionResults`, e quella coppia vuol dire «non si è caricato» — cioè rosso. Solo
    quella coppia, però: un file `passed` con zero test è il caso del difetto 26 — il
    filtro che non ha matchato — e leggerlo verde darebbe per girato un test mai partito,
    che è il solo modo in cui questo gate può fare danno invece che rumore.
    ✅ `esito_dei_file_di_vitest()`.

    **Causa:** `strumento-letto-come-testo`

26. **Il filtro `-t` non matcha mai un titolo che nel sorgente porta un escape.** A
    `bbebb07` il Builder aggiunge tre test e il gate ne segnala **uno solo**. Quell'uno è
    scritto così:

    ```ts
    it('non compare all\u2019officina: sono i conti economici dell\u2019azienda', …)
    ```

    Il gate estrae il titolo dal **testo** del file — `all\u2019officina` — e lo passa a
    `-t`, che vitest matcha sulla stringa **valutata**, `all’officina`. Non matcha: zero
    test girati, `nessuno`, ferma. Gli altri due, senza escape, sono stati letti benissimo,
    ed è la controprova. Vale per ogni escape (`\u2019`, `\'`, `\n`), e la stessa chiave
    serviva anche a rileggere il json, dove il titolo è già valutato.

    Sotto ce n'era una seconda metà, che nessun giro aveva ancora incontrato: `RE_TEST_JS`
    si fermava all'apice **scappato**, e di `it('l\'officina…')` leggeva `l\` — non il
    titolo di nessun test.

    La cura è decodificare gli escape **dove il nome nasce**, così che il filtro, le
    etichette del rapporto e la lettura del json restino d'accordo — e non `unicode_escape`
    della stdlib, che decodifica in latin-1 e farebbe mojibake delle accentate che nel
    sorgente stanno in chiaro, qui la norma. ✅ `decodifica_escape()`.

    Scartata la cura più larga — togliere `-t` e girare il file intero, pescando dal json i
    soli test chiesti. Elimina la classe di bug invece di tamponarla, ma gira anche test che
    il gate non ha chiesto, e «gira **soltanto** quei test» è una proprietà dichiarata di
    questo PBI: cambiarla è una deroga allo scope, non una fix (Francesco, 31/08).

    **Causa:** `codice-letto-come-testo`

27. **Il limite d'uso dell'account Claude si legge come un albero sporco.** Giro 5 di
    PBI-333, 02/09 00:32 → 00:46: il Builder fa 9 commit puliti, scrive due test rossi in
    `FoglioPage.test.tsx` e alle 00:46:20 risponde una riga sola —
    *«You've hit your session limit · resets 1:30am»*. Il runner non conosce quella frase:
    vede `M frontend/src/pages/FoglioPage.test.tsx`, rilancia con `-c` **due volte in
    quattro secondi** (stessa riga in risposta) e chiude `fermato` con la nota «il lavoro
    c'è ma non è committato». Vero alla lettera, falso nel senso: i tre giri d'igiene
    servivano a un Builder che si era dimenticato il `git add`, non a uno a cui è stata
    tolta la parola. Nessuna PR, perché la PR nasce solo a giro verde — e la nota manda a
    cercare un difetto nel codice che non c'è.

    Il log del runner, 14 righe, da solo non l'avrebbe mai detto: il transcript del Builder
    il runner non lo salva (`capture_output=True`), ma **Claude Code sì**, in
    `~/.claude/projects/-home-laisdev-ada-run/<sessione>.jsonl`. La prova stava lì, e
    l'appunto di sessione che diceva «il transcript non esiste da nessuna parte» è stato
    corretto il 02/09.

    La cura: riconoscere il limite nell'output del Builder e **fermarsi con la nota giusta**
    — `limite d'uso dell'account, reset alle 1:30` — senza consumare i giri d'igiene; o,
    meglio, **aspettare il reset** e riprendere con `-c`, visto che l'ora c'è scritta e il
    lavoro fatto sta nel worktree. Quale delle due è una decisione di costo (un runner che
    dorme un'ora tiene occupato il worktree), da prendere prima di scrivere il codice.
    ✅ Presa la prima, in due PBI: `PBI-367` chiude `senza esito` al primo lancio senza
    spendere i giri d'igiene, e `PBI-363` scrive nella nota il limite e l'ora del reset —
    o che l'ora non si legge — con `limite_d_uso()`. Si ferma, non dorme (decisione 1 di 363).

    **Causa:** `diagnosi-confusa`

28. **Il worktree usa e getta del gate si perde, e l'avviso che dovrebbe dirlo non parte.**
    Dopo il giro 6 di PBI-333 (02/09, 09:09 → 10:26) sono rimasti in `/tmp` tre alberi
    `ada-rosso-*` montati, uno per ogni giro del Builder — `09:24`, `09:34`, `09:42` — con
    dentro anche un `vitest-1.json` a metà. `git worktree list` li elencava tutti e tre.

    Il guasto non è che si perdano: è che si perdono **in silenzio**. `worktree_usa_e_getta`
    ha già il ramo che stampa `⚠️  worktree non smontato`, e nel log del giro quella riga
    **non c'è**. Quindi la strada che li ha lasciati lì non passa dal `finally` che li
    smonta, e chi legge il log non ha modo di saperlo.

    Il costo non è lo spazio. È che `PBI-105` dichiara fra i suoi criteri *«nessun worktree
    appeso, `/tmp` pulito»*, e quel criterio è stato spuntato leggendo l'esito di una corsa
    a mano invece che di un giro intero. Un albero appeso si contende poi il lock di
    `git worktree` col gate successivo, ed è il modo in cui due gate nello stesso repo si
    bloccano a vicenda.

    La cura ha due metà: chiudere la strada che salta lo smontaggio, e far sì che il giro
    **conti** gli alberi che ha montato e smontato, così che la differenza finisca nel
    rapporto invece che in `/tmp`.
    ✅ La seconda metà, con `PBI-363`: `USA_E_GETTA` conta montati e smontati, e
    `inventario()` fotografa rami, alberi e file all'inizio e alla fine del giro; ciò che
    resta in più va nel log e nella nota, e i residui dei giri prima si nominano all'avvio.
    La prima metà no: la strada che salta il `finally` non si è riprodotta, e un `finally`
    più grande a caso non è una cura (§Protocollo di rifinitura di 363).

    **Causa:** `residuo-di-un-giro`

*(Il numero 29 è già speso: `rami_locali` in `tools/asdlc_runner.py` lo usa per la ricaduta
del difetto 23 sul lancio di PBI-335, che qui sta scritta accanto alla sua spunta.)*

    **Causa:** `due-fonti`

30. **Il ramo si pubblica per il suo ref, e tutto il resto del giro guarda `HEAD`.**
    `pubblica()` fa `git push --force-with-lease -u origin <branch>`: manda il **ref**
    `refs/heads/<branch>`. Gate, gate del rosso, `conta_commit`, `diff --name-only` e il
    Critic leggono invece `origin/main..HEAD`. Finché i due coincidono la differenza non
    esiste — e il worktree del runner è staccato **per progetto** (`git switch --detach
    origin/main` nel pre-flight), quindi a separarli basta una mano di troppo.

    Misurato su **PBI-358, la notte del 21→22/09/2026**. Il pre-flight — tre righe non
    idempotenti, di cui la terza è quello `switch --detach` — è stato rieseguito **otto
    secondi dopo** il lancio, quando `crea_branch` aveva già fatto il suo `switch -c`: nel
    reflog il ramo nasce alle `23:20:14` e HEAD se ne stacca alle `23:20:21`. I 24 commit
    del giro sono nati su HEAD staccato, e il ref `pbi/pbi-358` è rimasto dov'era, su
    `origin/main`.

    Il rattoppo a mano l'ha peggiorato invece di chiuderlo: `git branch -f pbi/pbi-358
    bbec6a4` alle `23:46:04`, con uno sha letto quattro minuti prima — il commit `(RED)` del
    criterio 7, il cui GREEN era atterrato alle `23:46:01`. `apri_pr` ha pubblicato quel ref
    e aperto la PR #237 sopra.

    **Il guasto non è il distacco: è che il giro si è chiuso `fatto` senza accorgersene.**
    Rapporto `finito`, Critic **PASS**, `commit: 24`, nessun gate rosso — e su `origin`
    diciannove commit la cui punta è un `(RED)`, cioè CI rossa su una PR che il registro
    dichiara verde. I tre livelli di verifica vivono tutti dentro il worktree: nessuno
    guarda ciò che è stato pubblicato. È il difetto 18 preso dall'altro verso — là il push
    moriva e si vedeva, qui riesce e non si vede.

    Il costo, questa volta, è stato solo il tempo di capirlo: i commit erano tutti in
    `ada-run`, e `git push origin HEAD:refs/heads/pbi/pbi-358` è bastato. Ma il rapporto e
    `runs/tempi.csv` dicevano `fatto` su un lavoro che su `origin` non c'era, ed è quella la
    riga che si guarda per decidere se un branch si merga o si butta (difetto 10).

    La cura è una riga e mezza: pubblicare `HEAD:refs/heads/<branch>`, che è ciò che i gate
    hanno misurato, e in `apri_pr` fermarsi — `fermato`, non `fatto` — quando `rev-parse
    <branch>` non è `rev-parse HEAD`, nominando i due sha. Una PR aperta su commit che
    nessun gate ha visto è esattamente la promessa che la docstring di `apri_pr` dice di non
    voler più fare.

    **Causa:** `due-fonti`

31. **Il gate del rosso non vede il `git mv`, e conta un file traslocato come una nascita.**
    `file_del_commit` (`:1063`) chiede `git show --name-status` e il rename lo vede — la sua
    docstring lo dice. Lo perde il secondo `git show`, in `test_nuovi_del_commit` (`:1107`):
    `git show --format= --unified=0 <sha> -- <percorso>`. Con **un** pathspec git non applica
    il rename detection — per riconoscere una copia deve vedere tutti e due i lati — e il file
    risulta interamente aggiunto. `nomi_dei_test` legge allora una riga `+def test_…` per ogni
    test del file e nessuna `-`.

    Misurato su **PBI-360, il 22/09/2026**: il giro si è fermato dopo 4m39s e zero commit,
    perché spostare `test_asdlc_runner.py` in `tools/tests/` avrebbe fatto nascere **303**
    test in un colpo, tutti «nati verdi», tutti da passare per la quarta lettura di
    `ADR-0022`. Il Builder l'ha visto e ha chiesto invece di aggirarlo — la fermata è di
    quelle buone.

    **Il guasto non è il conteggio: è dove sta il rimedio.** `gate_del_rosso()` gira dentro il
    processo già caricato — nessun `execv`, nessun `reload`, e `--gate-rosso` (`:2731`) è solo
    un ingresso da riga di comando per le persone. Quindi un giro **non può ripararsi da sé**
    su questo difetto: qualunque correzione committi, continua a giudicarsi col codice che
    aveva in memoria all'avvio. È la stessa forma del difetto 9, e la seconda volta che si
    presenta.

    Il costo vero non è il giro perso, sono i falsi nati verdi: 303 test che passano per il
    mutante uno a uno, cioè un gate che gira per ore su una domanda che non ha senso porre —
    *«questo test, scritto sei mesi fa, morde una riga scritta oggi?»*.

    La cura è due comandi: `-M` esplicito, perché `diff.renames` è configurazione della
    macchina e il runner non può dipendere dal `.gitconfig` di chi lo lancia, ed entrambi i
    lati del rename nel pathspec. La semantica che ne esce è quella giusta: **un test
    traslocato non nasce**, e `ADR-0021` riguarda il nascere, non il cambiare cartella.
    Chiuso da `PBI-361`.
    Il meccanismo è lo stesso del difetto 61 (Francesco, 28/09/2026): `PBI-361` ha corretto le
    due letture del lato dei test, e la terza, sul lato della produzione, è rimasta com'era.
    La regola in un posto solo, per tutte le letture, è `PBI-387`.
    Il 03/10 la stessa domanda è tornata con un test spostato da un file a un altro, senza
    `git mv` (difetto 81). Per Python la radice la chiude `PBI-396`: la nascita si legge dalla
    collezione di pytest e non più dal diff (Francesco, 03/10/2026).
    Chiuso per Python da `PBI-396` (04/10/2026): un test nasce se il suo nome non è nella
    collezione del genitore né in quella della base, in qualunque file finisca. Per vitest
    la nascita resta letta dal diff, e va al repository `asdlc`.

    **Causa:** `codice-letto-come-testo`

32. **Lo `STOP:` del Builder si cerca come parola, e il prompt lo chiede come riga.**
    `esegui_pbi` (`:2293`) ferma il giro se `"STOP:" in out` — in un punto qualunque della
    risposta — e prende come domanda ciò che segue l'ultima occorrenza. Il prompt del
    Builder chiede invece di *terminare con la riga esatta* `STOP: <la domanda>`.

    Misurato su **PBI-363, il 23/09/2026** (`runs/20260923-103007.json`): il Builder aveva
    finito — 14 commit, sette coppie RED→GREEN, gli otto criteri coperti, 356 test verdi in
    `tools/tests` — e nel riepilogo ha citato la riga di fermata fra due backtick,
    descrivendo dove stava il controllo del limite d'uso. Il runner l'ha presa per una
    domanda: `fermato` in 9 minuti, gate e Critic mai partiti, nessuna PR, e come nota mezza
    frase — *«domanda dell'agente: `, prima dell'igiene e dei gate…»*.

    È il difetto 27 dall'altro lato: PBI-363 ha appena stabilito che la frase del limite
    conta solo se apre l'ultima riga, perché chi la cita ha ancora la parola, e lo stesso
    giro è stato fermato dal controllo di tre righe sopra, rimasto con la regola vecchia.
    La fermata finta costa più di un giro: somiglia a una fermata buona, e manda l'umano a
    leggere una domanda invece che a cercare un difetto.

    La cura: una fermata è una riga che **si apre** con `STOP:`, e un `FATTO:` sull'ultima
    riga vince su qualunque citazione sopra. Chiuso da `PBI-364`.

    **Causa:** `esito-da-testo-libero`

33. **La quarta lettura non vede la riga che decide, e vede la docstring.** Il gate di
    `ADR-0022` fa i mutanti delle righe del ramo con due operatori, la cancellazione e gli
    scambi, e su una funzione piccola scritta bene tutti e due mancano il bersaglio:

    - **la prosa di una docstring è una riga cancellabile.** È indentata, ha lettere, non
      è un commento e non apre un blocco: `si_puo_cancellare()` la accetta, il file
      compila, e il mutante non cambia niente. Ogni guardia gli sopravvive, e conta come
      «mutante provato»;
    - **la riga che decide può essere intoccabile.** Se è l'unica istruzione del suo
      blocco, cancellarla rompe la sintassi e il mutante si scarta (`compila()`); se non ha
      operatori da scambiare — `startswith`, `removeprefix`, `reversed` — non ne nasce
      nessuno. Il codice su cui la guardia monta è invisibile al gate;
    - **il guasto di esistenza passa ancora, dentro un corpo.** La cancellazione di
      un'assegnazione che una riga dopo usa fa sollevare `NameError` dentro il test, e
      pytest lo scrive `FAILED` come un'asserzione mancata: `falliti_per_asserzione()` lo
      conta come morso. `ADR-0022` ha escluso il guasto di esistenza a livello di modulo;
      nei corpi c'è ancora, e fa passare una guardia che non guarda niente. **Ha morso
      sulla #254** (secondo giro di PBI-364, `runs/20260923-222007.json`): le due guardie
      dichiarate sono passate nominando lo stesso mutante, la cancellazione di
      `righe = uscita.strip().splitlines()` (`tools/asdlc_runner.py:2206`), cioè un
      `NameError`. Erano guardie buone — provate a mano, ognuna fallisce per asserzione sul
      suo guasto di comportamento — ma il gate le ha fatte passare per la ragione sbagliata;
    - **un test parametrico si legge per funzione, non per caso.** `RE_PARAMETRO` toglie
      l'id: un caso rosso e due già verdi fanno un test rosso, e il gate non può dire quale
      caso ha portato il rosso. La verifica per caso resta a chi scrive il PBI.

    Misurato sul **primo giro di PBI-364, il 23/09/2026** (`runs/20260923-153009.json`):
    `b523fae` ed `e861db4`, due guardie nate verdi su `fermata_del_builder()`, fermate con
    «8 mutanti provati, nessuno lo fa fallire». Gli otto erano le sei righe di prosa della
    docstring, `riga = riga.strip()` (innocua sugli input dei test) e `return None`
    (restituisce `None` lo stesso). La riga che decide,
    `return riga.removeprefix("STOP:").strip()`, è l'unica istruzione del suo `if`: nessun
    mutante l'ha toccata. Il giro si è fermato per un difetto del PBI — i due criteri
    descrivevano un comportamento che `main` aveva già (`PBI-364` §un giro è già stato
    fatto) — ma una quarta lettura che vedesse quella riga avrebbe detto di più di «non
    morde».

    **I punti 2 e 3 sono in coda con `PBI-365`** (23/09/2026, Francesco), prima di PBI-363:
    un mutante è ucciso solo se il test fallisce per asserzione, la riga che decide si muta
    con `pass`, e il rapporto dice per ogni guardia mutante e tipo di fallimento. I punti 1
    (docstring) e 4 (parametri) restano aperti e non accodati. **Il punto 1 va a `PBI-378`**
    (Francesco, 26/09): la docstring si riconosce dall'AST, non dalla riga.
    Punto 1 chiuso da `PBI-378`: `righe_delle_docstring()` riconosce dall'AST il primo
    enunciato stringa di modulo, classe e funzione, e `mutanti_del_sorgente()` non genera
    mutanti su quelle righe, in nessun perimetro. Il punto 4 resta aperto.

    **Causa:** `codice-letto-come-testo`

34. **Una risposta senza marcatore valido passa ai gate in silenzio.** Dopo `PBI-364` una
    fermata è una riga che si apre con `STOP:` dopo lo `strip()`. Tutto il resto non ferma:
    una risposta che non termina né con `FATTO:` né con una riga di fermata, e le varianti
    che un modello scrive davvero — `**STOP:**`, `- STOP:`, `> STOP:` — vanno ai gate come
    un lavoro finito. È la decisione 4 di `PBI-364`, voluta: un Builder che dimentica la riga
    finale non ha chiesto niente. Ma una domanda vera scritta in grassetto si perde senza
    che nessuno lo veda.

    ❓ **Da decidere** (Francesco, 23/09/2026): se una risposta senza marcatore valido —
    o con un marcatore deformato — diventa un'**anomalia visibile** nel rapporto e nella
    coda, senza fermare il giro (`ADR-0008`). E intanto, prima di decidere, se il runner
    **scrive nel log** i marcatori accettati solo grazie allo `strip()`: è la misura che
    dice quanto spesso il caso capita. Non accodato.

    **Nella stessa voce, la domanda vuota.** Dopo `PBI-364` una riga di solo `STOP:` è una
    fermata con la domanda vuota, e la nota esce `domanda dell'agente: ` e basta. Fermarsi è
    giusto — la riga c'è — ma la nota deve **dire che la domanda è vuota** e rimandare
    all'uscita grezza del Builder, invece di lasciare una persona davanti a due punti.

    **Causa:** `esito-da-testo-libero`

35. **Lo `STOP:` del Critic si riconosce ancora con la regola vecchia.** `PBI-364` ha dato al
    Builder `fermata_del_builder()`; `revisione_critica()` (`:1930`, `:1938`) cerca ancora
    `"STOP:" in out` e prende ciò che segue **l'ultima occorrenza**. Oggi non morde, perché
    la stringa si cerca solo dopo un `VERDETTO: SOSPESO` (`PBI-364`, fuori scope), ma è la
    forma del difetto 32: due controlli sullo stesso protocollo scritti con due regole. La
    voce: **una funzione sola del protocollo** — la riga di fermata, la domanda su una riga,
    la domanda vuota del difetto 34 — usata dal Builder e dal Critic.

    **E una guardia da aggiungere, nello stesso lavoro:** nessun test passa una risposta con
    `FATTO:` finale **seguito da righe vuote**. Oggi quel caso lo regge solo lo `strip()`
    dell'intera uscita alla riga 2206 (`righe = uscita.strip().splitlines()`): senza, l'ultima
    riga è vuota, il `FATTO:` non si vede, e una riga di fermata citata sopra ferma il giro.
    ⚠️ Col gate di `PBI-365` quella guardia **non può mordere** così com'è il codice: la
    cancellazione della riga dà `NameError`, che non conterà più, e lo `strip()` dentro
    sé. Non accodato.

    **I difetti 34 e 35 sono in coda con `PBI-367`** (24/09/2026, Francesco), e non con una
    regola in più: l'esito del Builder e del Critic passa per una chiamata a strumento, e la
    riga non esiste più (`ADR-0027`). La domanda ❓ del 34 si chiude con lo stato
    `senza esito`, che è l'anomalia visibile. La guardia sul `FATTO:` seguito da righe vuote
    cade insieme al parser. **Chiusi da `PBI-367`** il 24/09: `fermata_del_builder()` e
    `VERDETTI` non ci sono più, e `esito_dichiarato()` legge per tutti e due i ruoli il file
    che il server dell'esito ha scritto.

    **Causa:** `esito-da-testo-libero`

36. **Un `NON PRONTO` che cita il `PASS` viene letto come `PASS`.** `revisione_critica()`
    cerca i tre verdetti come sottostringhe in tutto il testo, nell'ordine PASS → NON PRONTO →
    SOSPESO, e prende il primo che trova. Un rapporto che dice «non posso dare VERDETTO: PASS
    perché…» e chiude con `VERDETTO: NON PRONTO` è un **pass**, e il runner apre la PR su un
    lavoro respinto. **Verificato su `main` (`918f071`) il 24/09/2026**, eseguendo
    `revisione_critica()` con `esegui` sostituito. Non ha ancora morso: è latente, e peggiore
    del 32, perché fallisce verso il via libera invece che verso la fermata.

    Nella transizione morde più facilmente: i diff di `PBI-366` e `PBI-367` sono pieni di
    `VERDETTO:` e il Critic che li giudica li cita. Una decisione in tutti e due i PBI dice al
    Critic di non scrivere mai `VERDETTO` con due punti e un valore fuori dalla riga del
    verdetto, e **fino al merge di 367 i rapporti del Critic li legge Francesco** prima di ogni
    merge. Chiuso da `PBI-367`.

    **Causa:** `esito-da-testo-libero`

37. **Un'eccezione dentro il giro salta `chiudi()` e butta l'uscita.** Il timeout di una
    chiamata a un agente (due ore) o di un gate (un'ora) solleva `TimeoutExpired`, che
    `esegui()` non intercetta. La raccoglie la rete di `main()` (difetto 17), che scrive
    `rosso`, ma `chiudi()` non gira: il ramo non si pubblica, i commit non si contano,
    l'uscita parziale si perde, e il tick rilancia lo stesso PBI. Allo scadere restano vivi il
    server MCP e i test lanciati dal Builder, perché si uccide solo il figlio diretto.
    **Verificato su `main` (`e37caf7`) il 24/09/2026 eseguendolo**, non ancora successo in un
    giro vero. In coda con `PBI-369`, subito dopo `PBI-367` (Francesco, 24/09).

    **Causa:** `chiusura-saltata`

38. **I test del runner scrivono i loro prompt nella cartella vera.** Le venti classi di
    `tools/tests/` che fanno girare `esegui_pbi` o `revisione_critica` scrivono i
    `*_prompt.txt` in `runs/` del checkout, perché `LOG_DIR` è la cartella vera. Il Builder fa
    girare la suite a ogni giro: in `ada-run/runs/` ci sono 11.537 file di prompt per 119
    chiamate vere, e 320 nel checkout principale, dove il runner non gira. Un giro della
    suite ne scrive 124. **Misurato il 24/09/2026**, mentre si ricavava la durata delle
    chiamate per i tetti di `PBI-369`. Nessuno se n'era accorto, perché `runs/*_prompt.txt` è
    ignorato da git. In coda con `PBI-370`, dopo `PBI-369` (Francesco, 24/09).

    **Causa:** `test-senza-isolamento`

39. **Una riga che non è JSON fa cadere il server dell'esito.** `tools/asdlc_esito.py`
    passa ogni riga di stdin a `json.loads` senza intercettare l'errore: il processo muore
    con un traceback invece di rispondere con l'errore JSON-RPC `-32700`. Dalla nota del
    Critic sulla #263 (PASS di PBI-366, 24/09/2026). Non ha morso: la CLI manda JSON valido.
    Dopo `PBI-367` il runner lo leggerebbe come `senza esito`, cioè come un fallimento
    rumoroso e non come un esito falso. In coda con `PBI-372`, il PBI di approccio della causa.
    ✅ Fatto il 25/09 da `PBI-372`: la riga riceve `-32700` con `id` nullo e il server legge
    la dopo; sotto tutto il ciclo c'è una rete che risponde `-32603` a ciò che nessuno ha
    previsto, con il traceback su stderr.

    **Causa:** `ingresso-non-validato`

40. **Un `arguments` che non è un oggetto fa cadere il server dell'esito.** Una lista o una
    stringa al posto dell'oggetto fa sollevare `AttributeError` in `chiama()`, dopo che la
    chiamata è già finita nel log. Stessa fonte, stesso esito del 39. In coda con `PBI-372`.
    ✅ Fatto il 25/09 da `PBI-372`: la chiamata si rifiuta con `isError` e resta nel log; dei
    `params` o un messaggio che non sono un oggetto ricevono `-32600`.

    **Causa:** `ingresso-non-validato`

41. **Un campo che non è testo viene rifiutato come «vuoto».** Se `riepilogo` o `domanda`
    arriva come numero, il server lo rifiuta dicendo che il campo è vuoto. Rifiutarlo è
    giusto, ma il messaggio è falso: il modello che lo legge cerca il problema nel posto
    sbagliato.
    Stessa fonte. **Si corregge alla prima occasione in cui un PBI tocca
    `tools/asdlc_esito.py`** (Francesco, 24/09): il messaggio deve dire che il campo non è
    testo. È la decisione 4 di `PBI-372`.
    ✅ Fatto il 25/09 da `PBI-372`: «Il campo «riepilogo» non è testo: è un numero»;
    «è vuoto» resta per la stringa vuota, di soli spazi o assente.

    **Causa:** `ingresso-non-validato`

42. **Un `ASDLC_ESITO` mancante fa cadere il server con un traceback.** `os.environ[...]`
    solleva `KeyError`, mentre per un ruolo sbagliato il server si ferma in modo pulito, con
    un messaggio su stderr e un'uscita diversa da zero. Stessa fonte. `PBI-367` lo copre dal
    lato del runner: la config con un percorso mancante non si genera (decisione 4). Resta
    la forma della fermata, che non è quella degli altri errori di configurazione. In
    coda con `PBI-372`.
    ✅ Fatto il 25/09 da `PBI-372`: mancante o vuota, ferma il server all'avvio con un
    messaggio su stderr che la nomina e l'uscita `2`, come un ruolo sbagliato.

    **Causa:** `ingresso-non-validato`

43. **I criteri del PBI restano non spuntati a giro finito.** Su `PBI-366` (#263) e su
    `PBI-367` (#266) il file del PBI è arrivato in `main` con tutta la *Verifica* a `[ ]`,
    mentre i difetti di `PBI-102` si spuntavano. Il Builder ha rispettato lo Scope, e il file
    del PBI non c'era: `PBI-102` sì. Lo ha notato il Critic tutte e due le volte, come nota
    per chi mergia e non come rilievo. **Alla seconda occorrenza**, dalla nota del Critic
    sulla #266 (25/09/2026). Il template in `backlog/README.md` diceva le sezioni, ma non che
    lo Scope contiene sempre il file del PBI: la regola «si spunta a giro finito» viveva
    nell'abitudine. Corretto il template, e i PBI in coda che non lo avevano. Resta aperta,
    e può aspettare, la spunta fatta dal runner invece che dal Builder.

    **Causa:** `regola-non-scritta`

44. **I flussi e il log delle chiamate di un'invocazione non sono ignorati da git.** Da
    `PBI-367` ogni invocazione scrive in `runs/` anche `<esito>.stdout`, `<esito>.stderr` e
    `<esito>.chiamate.jsonl`. `.gitignore` prende `runs/*.json`, cioè il file d'esito e la
    config, ma non questi tre. Il log delle chiamate nasce mentre il Builder lavora, e il
    controllo dell'albero dopo il Builder lo avrebbe visto sporco: giri d'igiene, e alla
    fine `fermato` o i file committati nel ramo. **Verificato il 25/09/2026 con
    `git check-ignore`** su `main` (`d031444`), prima di riaccendere il tick: non è ancora
    successo in un giro vero, perché nessun giro è ancora partito col codice di 367. È la
    stessa forma del difetto 22, per il log del giro. Chiuso lo stesso giorno in
    `.gitignore`, senza PBI: sono tre righe e il primo giro di `PBI-370` ne ha bisogno.

    **Causa:** `scrittura-non-ignorata`

45. **La fixture dei test sposta i percorsi sotto la `runs/` di sempre, non sotto la
    `LOG_DIR` del momento.** `tools/tests/conftest.py` (`PBI-370`) confronta ogni percorso
    del runner con la `runs/` catturata all'inizio. Un test che applica un `asdlc.toml` con
    un'altra cartella del registro, per esempio `registro="giri"`, e poi fa girare
    `esegui_pbi`, scriverebbe in `REPO/giri/`. Quella cartella non è ignorata: sporca
    l'albero, e il tick si ferma al pre-flight. Oggi nessun test lo fa:
    `test_i_prestiti_e_il_registro_seguono_il_toml` usa `registro="giri"` ma non scrive.
    Dalla nota 1 del Critic sulla #270 (PASS di `PBI-370`, 25/09/2026). È il caso che la
    decisione 1 di 370 voleva coprire («la ventunesima classe di domani») e che copre solo
    in parte.

    **Causa:** `test-senza-isolamento`

46. **I file dei prompt nascono eseguibili.** Da `PBI-370` `file_dell_invocazione()` crea il
    prompt con `os.open(…, O_EXCL)` senza il terzo argomento. Vale quindi il default di
    `os.open`, `0o777` meno l'umask: con umask `022` il prompt è `0755`. Prima
    `write_text` lo creava `0644`. Non cambia il funzionamento. Dalla nota 2 del Critic
    sulla #270. Si chiude con un `0o644`, alla prima occasione in cui un PBI tocca
    `file_dell_invocazione()`.

    **Causa:** `default-implicito`

47. **Il tick decide `occupato` dai processi, e un processo qualsiasi lo ferma.**
    `runner_vivo()` in `tools/asdlc_coda.py` conta come runner vivo ogni processo con la
    cartella corrente nel worktree e `asdlc_runner` nella riga di comando, anche col
    lucchetto libero. Il 25/09 alle 11:00 un Monitor di Claude che seguiva il giro di
    `PBI-370` rispondeva a tutte e due le condizioni, e il tick ha scritto `occupato` con
    l'albero libero: un giro saltato. **Verificato su `main` (`e0297ca`) il 25/09/2026,
    eseguito.** È la terza occorrenza della causa (le altre due in `backlog/README.md`), e la
    prima scritta come difetto. In coda con `PBI-373`, il PBI di approccio (Francesco, 25/09).
    Chiuso da `PBI-373`: `giro_in_corso()` guarda solo il `flock` del lucchetto, e
    `runner_vivo()` non c'è più.

    **Causa:** `processo-per-euristica`

48. **Una chiusura che fallisce una volta cancella lo stato vero del giro.** Da `PBI-369` il
    giro sta in un `try`, e se `chiudi()` alza dentro il `try` l'`except` la riprova come
    `chiudi("rosso")`. Con un guasto transitorio la seconda riesce: un giro `sospeso`, o
    `fermato`, o `fatto`, finisce `rosso` con la nota «eccezione nel giro». Dalla prima nota
    del Critic sulla #272 (PASS di `PBI-369`, 25/09/2026). **Verificato su `main`
    (`be8320b`) il 25/09/2026, eseguito**, con un push che fallisce una volta su un giro
    `sospeso`. In coda con `PBI-375`, il PBI di approccio.
    Chiuso da `PBI-375`: la chiusura sta fuori dal `try` del giro e gira una volta. Una
    chiusura che fallisce alza `ChiusuraFallita` con il motivo che stava chiudendo, e sale
    alla rete di `main()` senza riprovare come `rosso`.

    **Causa:** `diagnosi-confusa`

49. **I rapporti del Critic di `PBI-371` non sarebbero ignorati da git.** La decisione 3 di 371
    li scrive in `runs/<run>-<PBI>-critic-<n>.md`, e `.gitignore` elencava le estensioni una
    per una, senza `.md`. Al primo `NON PRONTO` il file avrebbe sporcato l'albero dopo il
    Builder: giri d'igiene e poi `fermato`, o il rapporto committato nel ramo. **Trovato dal
    Builder di 371 prima di scrivere una riga**, il 25/09/2026 alle 13:01, con una chiamata a
    `fermati` che ha fatto la prova nel worktree (`runs/20260925-130007.json`). È la terza
    occorrenza della causa, dopo il 22 e il 44: si chiude rovesciando la regola in
    `.gitignore` (`runs/*` tranne `tempi.csv`), che è l'approccio e non un'altra riga
    (Francesco, 25/09).

    **Causa:** `scrittura-non-ignorata`

50. **Un'eccezione dopo `chiudi()` sostituisce l'esito già chiuso.** Dopo la chiusura
    `esegui_pbi()` fa ancora l'Acceptance Gate: `apri_pr()`, e dentro di lei il push, `gh pr
    create` e i commenti del Critic. Un'eccezione lì arriva alla rete di `main()`, che crea un
    `Esito` rosso nuovo: si perdono stato, commit, PR, puntatori ai rapporti e invocazioni.
    `PBI-371` ha coperto `TimeoutExpired` e `OSError` dei commenti, ma il meccanismo resta per
    ogni altra eccezione. `PBI-369` non lo copre, perché il suo `try` finisce con la chiusura.
    Da una nota del Critic sulla #279, rilevata da Francesco. **Verificato su `main`
    (`53da25c`) il 25/09/2026, eseguito.** In coda con `PBI-377`, dopo `PBI-375`.
    Chiuso da `PBI-377`: dopo `chiudi()` l'Acceptance Gate sta in un `try`, e un'eccezione
    si aggiunge in fondo alla nota dell'esito già chiuso («dopo la chiusura: `<tipo>:
    <messaggio>`»), con il traceback in `runs/*_traceback.log`; lo stato non cambia.
    `apri_pr()` scrive l'URL nell'esito prima dei commenti del Critic, così una PR già
    aperta resta nominata. La rete di `main()` resta per ciò che alza prima di un esito.

    **Causa:** `chiusura-saltata`

51. **`LIMITE_COMMENTO_GITHUB` è il limite documentato, senza margine.** `PBI-371` spezza i
    rapporti del Critic in commenti da 65.536 caratteri, contati come code point di Python.
    Se GitHub li contasse in byte o in unità UTF-16, un commento al limite verrebbe rifiutato.
    Dalla nota del Critic sulla #279. **Si porta a 60.000 alla prima occasione in cui un PBI
    tocca `parti_del_commento()`**, non ora (Francesco, 25/09).

    **Causa:** `soglia-non-misurata`

52. **Un `ls-remote` appeso in `crea_branch()` ferma il giro prima che esista.** `rami_su_origin()`
    chiede a `origin` i rami del PBI con `git ls-remote --heads`, e un timeout lì sale fuori dal
    `try` di `PBI-369`. `esegui_pbi()` alza prima di avere un esito, la rete di `main()` scrive
    un `rosso` «eccezione nel runner» senza ramo e senza giro, e senza ramo su `origin` il tick
    rilancia lo stesso PBI al passaggio dopo. Trovato dal Builder del primo giro di `PBI-363`
    (25/09, 17:03): il suo test faceva scadere ogni `ls-remote`, e quello di `crea_branch()` era
    fuori scope. **Verificato su `main` (`739fc08`) il 25/09/2026, eseguito.** Assegnato a
    `PBI-374`, che tocca già `crea_branch()` (Francesco, 25/09).
    Chiuso da `PBI-374`: un `ls-remote` che scade o fallisce in `crea_branch()` alza
    `OriginMuto`, e il giro chiude `fermato` passando da `chiudi()`, senza ramo e con la
    nota «origin non ha risposto».

    **Causa:** `chiusura-saltata`

53. **Una guardia su righe che il branch non cambia non può mordere, e i PBI che tolgono
    codice ne hanno bisogno.** Il gate di `ADR-0022` muta solo le righe **nuove o toccate**
    del ramo: `righe_cambiate()` legge gli hunk `@@ +c,d @@` del diff, e un hunk di sole
    cancellazioni (`d = 0`) non porta nessuna riga. Una guardia presidia per definizione un
    comportamento che c'è già, e quasi sempre vive su righe che il branch non tocca. Se il
    branch **toglie** codice attorno a quel comportamento, i soli mutanti sono le righe di
    prosa aggiunte (difetto 33, punto 1) e la guardia nasce verde e non morde, per
    costruzione: nessuna riscrittura del test la salva. Il gate dice «non morde» e il
    difetto è nel perimetro, non nel test.

    **Misurato sul primo giro di `PBI-373`, il 26/09/2026** (`runs/20260926-001008.json`):
    il branch cancella `runner_vivo()` e la riga `return runner_vivo(worktree)` in fondo a
    `giro_in_corso()`, e aggiunge solo docstring. Le tre guardie del criterio 2 (`5bebf3b`:
    lucchetto tenuto da fuori dall'albero, lucchetto che non si apre, lucchetto presente e
    libero) presidiano il ramo del `flock` di `giro_in_corso()`, che il branch non cambia.
    Nove mutanti provati, nessuno le fa fallire, e il giro si è fermato. Il PBI chiedeva
    guardie «verdi su `main`» su righe fuori dal diff, cioè una cosa che il gate non può
    accettare.

    **Assegnato a `PBI-378`** (Francesco, 26/09): il perimetro dei mutanti diventano le
    **funzioni** toccate dal diff, non le righe, e il commit della guardia può nominare la
    funzione da mutare quando il comportamento vive altrove. `PBI-373` è stato corretto:
    niente guardie, la rete del lucchetto è il test che c'è già su `main`. I due casi
    scoperti del lucchetto sono `PBI-379`, il collaudo della funzione nominata su un giro
    vero.
    Chiuso da `PBI-378`: il perimetro dei mutanti è la funzione più interna che contiene una
    riga cambiata o la posizione di un hunk di sole cancellazioni (`cancellazioni()`,
    `righe_del_perimetro()`), e il commit di una guardia può aggiungere una funzione che il
    branch non tocca con `Guardia-su: <percorso>::<nome>`. Il rapporto dice, per ogni
    guardia, le funzioni mutate e se sono entrate dal diff o per nome. Il collaudo su un giro
    vero resta a `PBI-379`.

    **Causa:** `codice-letto-come-testo`

54. **La nota di `head-non-su-origin` racconta due uscite.** `apri_pr()` mette la sua diagnosi
    **davanti** alla nota che `chiudi()` ha già scritto per il motivo `fatto`, invece di
    prenderne il posto: «`head-non-su-origin: PR non aperta … · fatto: giro chiuso`». Stato e
    motivo sono giusti, ma chi legge la nota vede due vie d'uscita, e il test parametrico di
    `PBI-375` guarda solo l'inizio (`startswith`). Dalla seconda nota del Critic sulla #289
    (PASS di `PBI-375`, 27/09/2026). **Verificato su `main` (`feffb8ec`) il 27/09/2026,
    eseguito**, con la via d'uscita `_head_non_su_origin` dei test di 375. In coda con
    `PBI-380`.
    Chiuso da `PBI-380`: `apri_pr()` toglie dalla testa della nota «`<motivo>: <testo>`» del
    motivo che l'esito aveva e ci mette la diagnosi di `head-non-su-origin`; l'avviso della
    base e ciò che il giro aveva dichiarato restano, una volta. Un test parametrico sulle
    uscite di 375 vuole che nessuna nota porti la diagnosi di un altro motivo.

    **Causa:** `diagnosi-confusa`

55. **La rete di `main()` butta il motivo di una chiusura fallita.** `PBI-375` fa salire
    `ChiusuraFallita` con il motivo che stava chiudendo (`exc.motivo`), ma la rete costruisce
    `Esito(pbi, "rosso", nota=…)` senza `motivo`: in `runs/<run>.json` il difetto 48 finisce
    `rosso` con il motivo vuoto, e il motivo vero sta solo nel testo della nota. La guardia di
    375 chiedeva la rete «come oggi», e il Builder l'ha rispettata. Dalla terza nota del
    Critic sulla #289. **Verificato su `main` (`feffb8ec`) il 27/09/2026, eseguito**: un giro
    con la domanda del Builder e `chiudi_la_fase()` che alza chiude `rosso`, `motivo` `''`,
    nota «chiusura del giro fallita (domanda-del-builder)». In coda con `PBI-380`.
    Chiuso da `PBI-380`: la rete copia `exc.motivo` nel campo `motivo` dell'`Esito` quando
    l'eccezione è una `ChiusuraFallita`; per ogni altra resta vuoto, e stato e nota non
    cambiano.

    **Causa:** `diagnosi-confusa`

56. **`--chiedi-impl` conta i commit del ramo su `BASE`, non sulla base del giro.**
    `test_nuovi_da_aprire()` fa `git rev-list --count {BASE}..HEAD`, e il Builder lo lancia
    dentro il giro: è l'ultima lettura del giro che nomina il ref e non lo sha di `PBI-374`.
    Oggi non sbaglia, perché un `origin/main` che avanza con commit estranei al ramo non
    cambia il conteggio. Ma è la seconda fonte che 374 voleva togliere. Dalla terza nota del
    Critic sulla #287 (PASS di `PBI-374`, 27/09/2026). **Letto su `main` (`feffb8ec`), non
    eseguito**: non c'è un caso che oggi dia un numero diverso. In coda con `PBI-380`.
    Chiuso da `PBI-380`: `esegui_pbi()` passa lo sha di `base_del_giro()` ad
    `apri_la_fase()`, che lo scrive in `asdlc-base` accanto al file della fase (e
    `chiudi_la_fase()` lo toglie); `test_nuovi_da_aprire()` conta da lì, e fuori da un giro
    ripiega su `BASE`. Il caso che dà un numero diverso c'è, con git vero: un `origin/main`
    che riceve il ramo stesso con un merge veloce.

    **Causa:** `due-fonti`

57. **Un timeout della pubblicazione dopo `chiudi()` diventa `fatto`.** `git()` passa per
    `esegui()`, che cattura solo `FileNotFoundError`: un `push` o un `ls-remote` che scade alza
    `subprocess.TimeoutExpired`. `pubblica()` e la verifica della testa in `apri_pr()`
    intercettano solo `RuntimeError`. Il `try` del giro 1 di `PBI-377` metteva l'eccezione in
    fondo alla nota, e un giro che prima chiudeva `rosso` chiudeva `fatto` con il ramo su
    `origin` in uno stato che nessuno conosceva. Dalla domanda del Critic sul giro 1 di
    `PBI-377` (27/09/2026). **Letto sul ramo `pbi/pbi-377`, non eseguito.** Risposta di
    Francesco: strada (c), il timeout va allo stato di pubblicazione che esiste già. In coda con
    `PBI-377`, con lo Scope allargato.
    Chiuso da `PBI-377`: `pubblica()` intercetta `TimeoutExpired` con `RuntimeError` e torna
    `False`, e nella nota aggiunge «push in timeout, stato di origin da verificare» accanto a
    `NON_PUBBLICATO` — vale per `apri_pr()` e per il giro fermato che `chiudi()` pubblica, dove
    il timeout non diventa più `ChiusuraFallita`. La verifica della testa in `apri_pr()`
    intercetta `(RuntimeError, TimeoutExpired)` come `base_del_giro()`, e un `ls-remote`
    scaduto chiude `head-non-su-origin` con la testa «non verificabile». Il `gh pr create` che
    scade resta a `PBI-381` (difetto 58).

    **Causa:** `diagnosi-confusa`

58. **Un `gh pr create` che scade può lasciare una PR senza URL nel registro.** È il terzo caso
    della stessa domanda del Critic. La PR può essere nata su GitHub mentre il client moriva, e
    l'esito non la nomina. Il tick vede il ramo su `origin` e scrive `attende … tocca a un
    umano`, ma non dice che una PR forse c'è già. Letto, non eseguito. Va in `PBI-381`
    (Francesco, 27/09/2026).
    Chiuso da `PBI-381`: `apri_pr()` chiede `gh pr list --head <ramo> --state open --json url`
    prima di creare, e non crea se trova una PR o se `gh` non risponde; dopo un create scaduto
    o senza URL rifà la ricerca una volta, e se non trova niente la nota dice «PR forse aperta,
    da verificare». La riga `attende` del tick nomina le PR aperte sul ramo, oppure dice
    «nessuna PR sul ramo: crearla o rilanciare» o «GitHub non ha risposto: PR da verificare».

    **Causa:** `traccia-persa`

59. **Il Builder ha messo una regressione in una docstring invece di fermarsi.** Nel giro 1 di
    `PBI-377` il Builder ha visto il caso del difetto 57 e l'ha scritto nella docstring di
    `apri_pr()`: «lascerebbe lo stato `fatto` a un giro la cui testa su origin nessuno ha
    verificato». Poi ha chiamato `fatto`. Il protocollo di rifinitura del PBI diceva di
    fermarsi, e il prompt del Builder non diceva che una regressione trovata in `IMPL` è una
    fermata. A fermare il giro è stato il Critic. Corretto nel prompt del Builder il 27/09/2026
    (Francesco), con il suo test.

    **Causa:** `regola-non-scritta`

60. **I test di `tools/` in un worktree nuovo danno 19 rossi falsi senza il venv sul `PATH`.**
    I test del gate del rosso e dei mutanti lanciano `pytest` in un albero temporaneo, e lo
    cercano sul `PATH`. Un worktree nuovo non ha `backend/.venv`, e con
    `backend/.venv/bin/python -m pytest` lanciato a mano il sottoprocesso non trova `pytest`:
    uscita 127, «comando non eseguibile: pytest». I test falliscono uno per uno, 19 su 562, con
    un `GuastoDelGate` ciascuno, e niente all'avvio dice che manca l'ambiente. Su `main`, nel
    checkout principale, passano tutti. Visto scrivendo la #291 (27/09/2026), **eseguito**.
    È la **terza occorrenza** della causa, dopo i difetti 15 e 21: la causa ha il suo
    approccio nella tabella di `backlog/README.md` (Francesco, 27/09).
    Va a `PBI-384`, i comandi e l'ambiente dichiarato.
    Chiuso da `PBI-384` (30/09/2026): `tools/tests/conftest.py` cerca `git` e `pytest` in
    `pytest_sessionstart`, nel venv di `[ambiente].venv` e poi sul `PATH`, e senza ferma la
    sessione con `pytest.exit` e una riga «ambiente mancante» per ognuno, prima della
    raccolta. Il runner e il tick verificano all'avvio gli `[ambiente].eseguibili` e i
    `[ambiente].minimi` di `asdlc.toml`, con tutte le mancanze e dove le hanno cercate.

    **Causa:** `ambiente-non-dichiarato`

61. **Il perimetro del gate del rosso legge un file spostato come un file nuovo.**
    `hunk_di_produzione()` elenca i file con `git diff --name-only base...sha` e poi chiede il
    diff di ciascuno nominando **solo il percorso nuovo**. Con un solo lato git non applica il
    rename detection, e il file risulta aggiunto per intero: `@@ -0,0 +1,N @@`. Da lì
    `righe_cambiate()` mette nel perimetro ogni funzione del modulo spostato. Il lato dei test
    lo sa già: `lati_del_diff()` chiede il diff sui due lati, con `-M` scritto nel comando,
    perché lo stesso buco era già costato un giro sulle nascite. La produzione è rimasta
    indietro. Visto scrivendo i PBI di impacchettamento (28/09/2026), **eseguito** su un
    repository usa-e-getta: un `git mv` con una riga d'import cambiata dà `@@ -0,0 +1,121 @@`
    sul solo lato nuovo, e `@@ -1 +1 @@` con i due lati e `-M`. Senza correzione, lo
    spostamento in `tools/asdlc/` di `PBI-383` metterebbe nel perimetro ogni funzione del
    runner e del tick. Va a `PBI-387`, in coda prima di 383.
    Chiuso da `PBI-387` (29/09/2026): il diff di un file lo chiede solo `diff_del_file()`,
    con `-M` scritto e i due lati di un rename. La usano `hunk_di_produzione()` e le due
    letture dei test; `guardia_del_commit()` e `file_toccati()` elencano i due lati con
    `--name-status -M`. Con lui è chiuso nel meccanismo anche il difetto 31.

    **Causa:** `default-implicito`

62. **`asdlc.toml` porta un percorso che vale su un PC solo.** `[worktree].percorso =
    "~/ada-run"`, da `PBI-358` (21/09/2026). Il file è versionato, e dice che «ogni percorso è
    relativo alla radice del repository», ma questo è della home di chi l'ha scritto. Un altro
    PC, o un altro utente, avrebbe il worktree del tick altrove, e il tick lo cercherebbe dove
    non c'è. Il commento di testa rimanda i percorsi di macchina ad `asdlc.local.toml`. Il
    worktree del giro, però, non ne ha uno, perché è gitignored, e il percorso è finito nel file
    versionato. La seconda occorrenza stava per entrare con `PBI-384` nella bozza del 28/09,
    `[ambiente].pacchetto = "~/ada_controller/.venv-asdlc"`, per la stessa ragione. Letta da
    Francesco il 28/09/2026: *«il modello dei progetti nuovi non deve contenere niente che
    funzioni su un solo PC»*. Va a `PBI-384`: i due percorsi diventano relativi alla radice
    comune del repository (`git rev-parse --git-common-dir`), e un percorso assoluto o con `~`
    in `asdlc.toml` è un errore di configurazione.
    Chiuso da `PBI-384` (30/09/2026): `carica()` risolve `[worktree].percorso` e
    `[ambiente].pacchetto` dalla cartella madre di `--git-common-dir`, e ferma un valore
    assoluto o con `~` in `asdlc.toml` nominando chiave e valore; in `asdlc.local.toml` lo
    stesso percorso vale. `asdlc.toml` dice `percorso = "../ada-run"` e
    `pacchetto = ".venv-asdlc"`.

    **Causa:** `percorso-di-macchina`

63. **Un file che entra in produzione con un rename non porta righe nel perimetro.** Da
    `PBI-387` il perimetro legge un rename sui due lati, e un rename al 100% non porta hunk
    (decisione 3 di 387). Vale anche quando il lato vecchio **non** è produzione:
    `git mv nota.txt backend/app/x.py`, oppure un test spostato sotto `app/`, fa entrare
    codice di produzione senza una riga aggiunta, e quindi senza un RED che l'abbia chiesto.
    Il gate dei mutanti non lo sfrutta: un perimetro vuoto lo rende più severo, non più
    permissivo. Però il codice arriva in produzione senza essere passato dal rosso. È il caso
    speculare di quello che `lati_del_diff()` ferma sul lato dei test. Dalla nota 2 del Critic
    sulla #305 (29/09/2026), **letto, non eseguito**. Correzione nella funzione di 387
    (Francesco, 29/09): un rename che attraversa il confine fra non produzione e produzione
    conta come tutte righe aggiunte. Va a `PBI-389`.
    Chiuso da `PBI-389` (01/10/2026): `diff_del_file()` chiede il diff di un rename con il
    lato vecchio fuori dalla produzione e il nuovo dentro col solo percorso nuovo, e il file
    entra nel perimetro per intero, anche con `diff.renames = false`. Con `lati` esplicito,
    il lato dei test, la regola non si applica.

    **Causa:** `modifica-senza-righe`, prima occorrenza (Francesco, 29/09).

64. **L'elenco dei file del giro legge ancora `git diff --name-only`.** A giro chiuso,
    `esegui_pbi()` stampa i file toccati con `git diff --name-only base...HEAD`, e di un
    rename dà solo il percorso nuovo. È l'elenco dello Scope di `ADR-0015` che finisce nel log
    e che chi mergia legge, e il test che lo fissa è `test_un_giro_intero_non_nomina_mai_origin_main`
    di `test_asdlc_runner.py`. `PBI-387` ha chiuso i quattro posti che aveva elencato, e questo
    era il quinto: il suo criterio sull'AST cerca `git diff` e `git show` con pathspec, e un
    `--name-only` senza pathspec gli passa sotto. Dalla nota 3 del Critic sulla #305
    (29/09/2026), **letto, non eseguito**. È il meccanismo del 61 (Francesco, 29/09):
    l'elenco dello Scope passa dalla funzione unica di 387, e il criterio sull'AST copre anche
    `git diff --name-only` senza pathspec. Va a `PBI-389`.
    Chiuso da `PBI-389` (01/10/2026): l'elenco a giro chiuso è `sorted(file_toccati(base))`,
    con i due lati di un rename, e il criterio sull'AST vieta `--name-only` in ogni
    `git("diff", …)` del runner.

    **Causa:** `default-implicito`

65. **Il gate del rosso non riconosce un test pytest che ha uno spazio nell'id.** Legge
    pytest dallo schermo: l'esito per test da `RE_ESITO_PYTEST`
    (`^(\S+::\S+) (PASSED|…)`) e il tipo del fallimento da `RE_RIEPILOGO_PYTEST`
    (`^FAILED (\S+::\S+) - `). Un test parametrico con uno spazio nell'id (`@parametrize` su
    stringhe, senza `ids=`) non combacia con nessuna delle due. Succedono due cose:
    - **l'identità del test**: `esiti_di_pytest()` non trova la sua riga, e al test si dà
      l'esito dei totali di tutto il comando (`leggi_esito()`). È il difetto che `PBI-376` ha
      tolto a vitest: un test nato verde, nello stesso comando con un test rosso, si legge
      rosso;
    - **i mutanti**: `falliti_per_asserzione()` non vede nessun fallimento, e ogni mutante
      risulta sopravvissuto. Il test sembra non mordere anche quando morde.

    Visto nel giro 1 di `PBI-388` (29/09/2026, `rosso-mai-visto` su `878f1be`), ed
    **eseguito**. `test_guardia_un_hook_altrui_non_si_riscrive` ha gli id
    `[#!/bin/sh\n# il formattatore di qualcun altro…]`. Cancellando `:3904`, o togliendo il
    `not` a `:3919`, fallisce in tutti e due i casi. Sull'uscita vera, però, la regex trova
    zero falliti. Il gate della suite non è toccato: `gira_gate()` decide dal codice d'uscita
    di pytest, quindi un test rosso con uno spazio nell'id ferma comunque la suite.
    È la **terza occorrenza** della causa, dopo i difetti 12 e 25. La causa si corregge ora
    (Francesco, 29/09): va a `PBI-390`, pytest letto dal JUnit sia per l'identità dei test sia
    per il tipo del fallimento. In coda davanti a 388.

    **Causa:** `strumento-letto-come-testo`

66. **Il Critic non trova il server dell'esito, perché il Builder l'ha spostato.** Il runner
    che giudica il giro è quello caricato all'avvio. La config MCP che genera per ogni
    sessione, invece, lancia il server dall'albero vivo, cioè
    `<worktree>/tools/asdlc_esito.py`. `PBI-383` sposta proprio quel file con `git mv` in
    `tools/asdlc/esito.py`. Il server del Builder era partito prima dello spostamento, quello
    del Critic dopo, a file già sparito: il server non si connette, il Critic non chiama né
    `fatto` né `fermati`, e il giro chiude `senza esito` (`critic-senza-esito`). Il rapporto
    del Critic dava **PASS**, ma soltanto nel testo, e il testo non decide (`ADR-0027`).
    Rilanciare non serve: il giro 2 rifarebbe lo spostamento e si fermerebbe nello stesso
    punto. Visto nel giro 1 di `PBI-383` (30/09/2026, `runs/20260930-010008`), ed
    **eseguito**: le due config MCP del giro nominano lo stesso percorso, e a fine giro il
    file non c'è. La PR #310 è stata aperta a mano, con il rapporto come commento.
    Il runner caricato all'avvio e il server lanciato dall'albero vivo sono due fonti, e il
    Builder le fa divergere (Francesco, 30/09). Vale anche per gli hook, che lanciano
    `runner.py` dall'albero vivo. Va a `PBI-384`: la config MCP e gli hook lanciano i comandi
    del venv installato, e non più i file dell'albero su cui il Builder lavora.

    **Causa:** `due-fonti`

67. **Un `pyproject.toml` sotto la cartella di lancio cambia gli id del JUnit.** Il gate del
    rosso lancia pytest da `dove_gira()`: `backend/` per il backend, la radice per `tools/`.
    `caso_junit()` ricava il caso dal node id relativo a quella cartella, e presuppone che
    pytest usi come rootdir proprio quella. È vero solo finché nessun file di
    configurazione sta fra la cartella di lancio e i test. Da pytest 8.1 un
    `pyproject.toml` vale come file di configurazione anche senza
    `[tool.pytest.ini_options]`, e decide il rootdir. `PBI-384` aggiunge
    `tools/pyproject.toml`, e `python3 -m pytest tools/tests/…` lanciato dalla radice
    prende `rootdir: tools`. Il `classname` del JUnit diventa `tests.test_x` invece di
    `tools.tests.test_x`, nessun caso combacia con la chiave, e ogni RED dopo il commit che
    aggiunge il file si legge «rosso non isolabile». Ha fermato il giro 1 di `PBI-384`
    (30/09/2026, `runs/20260930-105009`, `domanda-del-builder`) sul RED del criterio 3.
    **Eseguito** su pytest 9.1.1 con `comandi_dei_test()` di `main`: con
    `tools/pyproject.toml`, o con `tools/pytest.ini`, il caso è `tests.test_x`; con
    `--rootdir=.` torna `tools.tests.test_x`. Era la nota 2 del Critic sulla #308
    (`PBI-390`, 29/09), rimasta nel rapporto. Da qui la regola sulle note del Critic in
    `backlog/README.md`. Correzione (Francesco, 30/09): `comandi_dei_test()` lancia pytest con
    `--rootdir` uguale alla cartella di lancio. Il rootdir non si lascia al default che
    pytest ricava dai file che trova. Va a `PBI-391`, in coda davanti a 384.

    **Causa:** `default-implicito`

68. **Un rapporto JUnit che manca si legge «nessun test», se nessuno chiama dopo
    `leggi_esito()`.** `esiti_di_pytest()` intercetta il `GuastoDelGate` di
    `radice_del_junit()` e torna `{}`, cioè lo stesso valore di un rapporto letto senza casi
    per quelle chiavi. Il guasto lo alza poi `leggi_esito()`, che `esiti_del_comando()` chiama
    subito dopo. Oggi quindi è corretto, e la docstring lo dice. Però regge sull'ordine delle
    due chiamate, e nessun test lo fissa. Una chiamata a `esiti_di_pytest()` da sola
    leggerebbe un rapporto mancante come «nessun test». `esiti_di_vitest()` ha la stessa
    forma: torna `{}` e lascia il guasto a `esito_dei_file_di_vitest()`. Era la nota 1 del
    Critic sulla #308 (`PBI-390`, 29/09/2026), registrata all'indietro con la regola del
    30/09 (`backlog/README.md`, §I difetti e le loro cause). **Letto, non eseguito.** Si
    chiude alla prima occasione in cui un PBI tocca `esiti_di_pytest()`: il guasto passa, e
    chi vuole il vuoto lo chiede.

    **Causa:** `diagnosi-confusa`

69. **Il tick spento commentando la riga del crontab lancia lo stesso, finché cron non
    ricarica.** Per spegnere il tick si commenta la sua riga con `crontab -`, e `crontab -l`
    la mostra subito commentata. Ma cron lancia dalla tabella che ha caricato, e la rilegge
    solo quando la ricarica: nel journal è la riga `RELOAD (crontabs/laisdev)`. Fra la modifica
    e il `RELOAD` il tick lancia con la riga vecchia. Il 30/09/2026 la riga è stata commentata
    alle 17:51 per chiudere il giro 1 di `PBI-384` (journal: `REPLACE`, nessun `RELOAD`).
    Alle 18:00 cron ha lanciato il tick, che ha trovato libero il nome del ramo, appena
    cancellato su `origin`, e una coda ancora senza `PBI-391`. Ha lanciato 384 su `fe2a0eeb`
    (`runs/20260930-180016`). Il Builder si è fermato in 40 secondi, senza commit, perché la
    base non conteneva la correzione. È rimasto `pbi/pbi-384-giro2` vuoto, su `origin` e in
    locale, e avrebbe tenuto la coda in `attende`. Il `RELOAD` è arrivato alle 18:05:01, dopo
    la modifica successiva. **Eseguito**: journal e `coda.log` del 30/09. Il crontab nel file e
    la tabella caricata da cron sono due fonti (Francesco, 30/09). Va a `PBI-385`: il tick esce
    subito se esiste un file di pausa, `~/asdlc-tick.pausa`. Spegnere è crearlo, riaccendere è
    toglierlo, e `asdlc-chiudi-giro` usa il file, non il crontab. Fino ad allora, chi spegne a
    mano aspetta il `RELOAD` nel journal prima di cancellare un ramo.
    Chiuso da `PBI-385` (30/09/2026): `smista()` di `tools/asdlc/coda.py` legge
    `~/asdlc-tick.pausa` prima di `decidi()` e di nuovo subito prima di `lancia()`; con il file
    esce con 0 e scrive in `coda.log` `in pausa: <riga>`, e un file che non si legge è pausa lo
    stesso. `asdlc-chiudi-giro` crea il file prima del tag e lo toglie dopo il `ff-only`, anche
    se un passo fallisce; la riga del crontab non la legge né la scrive nessun passo.

    **Causa:** `due-fonti`

70. **Il tick non ha un lucchetto suo, e fra la seconda lettura della pausa e il runner
    niente lo esclude.** Il tick legge `~/asdlc-tick.pausa` due volte, prima di `decidi()` e
    subito prima di `lancia()` (`PBI-385`). Dopo la seconda lettura fa il pre-flight
    (`git fetch` fino a 300 s, `git switch --detach`) e avvia il runner, e fino al `flock`
    del runner non tiene nessun lucchetto. `asdlc-chiudi-giro` in quel momento guarda il
    lucchetto del runner, lo trova libero, crea la pausa e fa i sei passi, mentre il tick
    finisce il lancio. Il PBI che si sta chiudendo non può partire, perché per quello il tick
    aveva deciso `attende`. Può partire solo un PBI che in coda viene prima e non ha un ramo,
    cioè lo stesso che il tick lancerebbe appena tolta la pausa. Il danno è basso, ma la pausa
    non esclude quello che promette (decisione 5 di `PBI-385`). L'ha visto il Builder di
    `PBI-385` nel giro 1 (30/09/2026, `runs/20260930-211009`, `domanda-del-builder`), che si è
    fermato come chiedeva il protocollo di rifinitura. **Letto, non eseguito**: `coda.py` non
    prende nessun `flock` suo, e `giro_in_corso()` guarda solo quello del runner. Terza
    occorrenza di `concorrenza-non-esclusa`, dopo il 9 e il 19 (Francesco, 30/09). `PBI-385`
    dichiara la finestra come residuo (la sua decisione 8), e la cura va a `PBI-392`: il tick
    prende un lucchetto suo e lo tiene fino al distacco del runner, e `asdlc-chiudi-giro`
    prende lo stesso lucchetto per tutti i sei passi.
    Chiuso da `PBI-392` (01/10/2026): `lucchetto_del_tick()` prende senza aspettare un
    `flock` su `runs/.tick.lock` del checkout. Il tick lo prende prima della prima lettura
    della pausa e lo tiene fino alla fine di `smista()`, distacco del runner compreso, e chi
    lo trova tenuto scrive `occupato:` ed esce con 0; `asdlc-chiudi-giro` lo prende prima di
    ogni rifiuto e di ogni `git` e lo tiene per tutti i sei passi, e trovato tenuto rifiuta.
    Il runner staccato non lo eredita.

    **Causa:** `concorrenza-non-esclusa`

71. **Il runner confronta `sys.executable` così com'è con `PACCHETTO` risolto.**
    `mancanze_dell_ambiente()` di `tools/asdlc/runner.py:799` chiede
    `Path(sys.executable).is_relative_to(PACCHETTO)`. `sys.executable` non si risolve apposta,
    perché nel venv è un collegamento all'interprete di sistema. `PACCHETTO` invece passa da
    `.resolve()` in `config.risolvi()`. Se il percorso del checkout principale attraversa un
    collegamento simbolico, per esempio una home che è un link, i due percorsi divergono e il
    runner installato si dichiara «fuori dal venv». Su questo PC non succede. Era la nota 1
    del Critic sulla #316 (`PBI-384`, 30/09/2026), registrata con la regola del 30/09. **Letto,
    non eseguito.** La cura è confrontare con lo stesso trattamento tutti e due i lati: la
    cartella del venv di `sys.executable` (`Path(sys.executable).parent.parent`) risolta,
    contro `PACCHETTO` risolto. Si chiude alla prima occasione in cui un PBI tocca
    `mancanze_dell_ambiente()`.

    **Causa:** `due-fonti`

72. **Il test di `pip install ./tools` va in rete.**
    `tools/tests/test_asdlc_pacchetto.py` installa una copia di `tools/` in un venv pulito con
    il build isolato di pip, che scarica `setuptools>=61` da PyPI. In CI e su questo PC va
    bene, ma su una macchina senza rete il test fallisce, e il motivo non ha niente a che fare
    con il pacchetto. Era la nota 2 del Critic sulla #316 (`PBI-384`, 30/09/2026). **Letto,
    non eseguito.** Si chiude alla prima occasione in cui un PBI tocca quel test: o il build
    senza isolamento dal `setuptools` che c'è già, o uno skip dichiarato senza rete, da
    decidere lì.

    **Causa:** `test-senza-isolamento`

73. **Il tick non verifica il venv dei gate, e un venv che manca si legge «runner non
    partito».** `coda.mancanze_dell_ambiente()` controlla il runner installato, gli
    eseguibili e le versioni minime, ma non che `[ambiente].venv` esista. Il runner invece lo
    controlla. Se il venv dei gate manca, il tick lancia, il runner rifiuta con «ambiente
    mancante» e il tick scrive in `coda.log` che il runner non è partito. Non si perde niente,
    perché la ragione vera è nell'uscita del runner, ma la riga del log non dice «ambiente
    mancante». Due situazioni diverse finiscono nella stessa riga. Era la nota 3 del Critic
    sulla #316 (`PBI-384`, 30/09/2026). **Letto, non eseguito.** Si chiude alla prima occasione
    in cui un PBI tocca `coda.mancanze_dell_ambiente()`.

    **Causa:** `diagnosi-confusa`

74. **ADR-0022 non diceva quando si giudica il morso, e il gate lo guarda solo al commit
    della guardia.** `esamina_il_commit()` rigira la guardia nata verde nell'albero del suo
    commit, con i mutanti delle funzioni toccate fino a lì. Una guardia scritta **prima** di un
    cambiamento, per proteggerlo, lì può non avere niente da mordere. Il golden della decisione
    2 di `PBI-386` (`63c9e3e9`) fissa i cinque prompt quando sono ancora costanti di modulo:
    l'unico codice che li tocca è `configura()`, e i suoi mutanti danno solo `AttributeError`.
    26 mutanti provati, nessun morso, e il giro 1 si è fermato su una guardia che il PBI
    prescriveva (01/10/2026, `runs/20261001-004014.json`, `domanda-del-builder`). Il Builder si
    è fermato prima che il gate lo facesse. **Eseguito** il 01/10 col gate di `main`: alla punta
    del ramo (`00462357`) lo stesso golden morde, sulla cancellazione di
    `tools/asdlc/config.py:194`. La regola non era sbagliata, era incompleta: `ADR-0022` diceva
    **se** una guardia passa e non **dove** si guarda. Terza occorrenza di
    `regola-non-scritta`, dopo il 43 e il 59, e la colonna del PBI di approccio è vuota. Qui la
    cura è la revisione del 01/10 di `ADR-0022` (Francesco): il morso si giudica al commit che
    introduce la guardia oppure, se lì non morde, alla punta del ramo, e il gate ferma solo se
    non morde neanche lì. La implementa `PBI-393`. La decisione 2 di `PBI-386` resta com'è.
    Chiuso da `PBI-393` (01/10/2026): la guardia che non morde al suo commit si riprova
    nell'albero della punta del ramo, col perimetro di `base...punta` e le funzioni del suo
    `Guardia-su:`; il morso di lì passa con `"dove": "punta"`. **Eseguito** con
    `--gate-rosso` sui due tag: `63c9e3e9` passa alla punta `0046235`, `45a5f9de` resta ferma
    (`ADR-0022`, revisione del 01/10).

    **Causa:** `regola-non-scritta`

75. **Il tick decide da `origin/main` e lancia il runner installato dal suo checkout, e i
    due non si allineano da soli.** `decidi()` guarda le PR mergiate su `origin`;
    `~/asdlc-tick.sh` reinstalla `.venv-asdlc` dall'albero `tools/` di `HEAD` del checkout
    principale, che avanza solo col `ff-only` a mano dopo il merge. La #322 (`PBI-393`) è
    entrata alle 08:16 del 01/10, e il `ff-only` non c'è stato: il checkout era ancora a
    `907c5f9d`, il venv a `tools` `305e92d5` invece di `1796eecf`. Il tick delle 08:20 ha
    visto 393 in `main` e ha lanciato il giro 2 di `PBI-386` col runner di prima di 393. Il
    cherry-pick dal tag è andato (20 commit, testa `8041ba6a`), e il gate si è fermato in sei
    minuti con `rosso-mai-visto` sullo stesso golden del giro 1, `f6f9c4c`, giudicato solo
    al commit: proprio quello che 393 correggeva (`runs/20261001-082010.json`). Il giro non
    dice niente di 393, che non ha girato. **Eseguito**: `.venv-asdlc/.installato-da` e
    `git rev-parse HEAD` del checkout alle 22:30, e il rapporto del giro senza la lettura
    «alla punta». Il `ff-only` a mano è saltato due volte su due merge (Francesco, 01/10):
    un passo che il processo chiede a una persona a ogni merge, e che niente controlla. La
    cura va a `PBI-392`, come secondo criterio: il tick, prima di decidere, allinea il
    checkout a `origin/main` con `ff-only` e reinstalla se la firma cambia; se il `ff-only`
    non si può fare, lo scrive e non lancia (Francesco, 01/10). Il giro 2 è chiuso nel tag
    `giro-fermato/pbi-386-giro2-20261001`, per la provenienza; il giro 3 riprende dal tag del
    giro 1, come dice la sezione di ripresa di `PBI-386`.
    Chiuso da `PBI-392` (01/10/2026): fuori dalla pausa e prima di `decidi()`, `allinea()` fa
    `git fetch` e `git merge --ff-only origin/main` nel checkout, e se il checkout non è su
    `main` o `git` rifiuta scrive `non allineato:` e non decide. Poi `reinstalla()` confronta
    `git rev-parse HEAD:tools` con `<pacchetto>/.installato-da` e, col lucchetto del runner
    libero, reinstalla con `pip install ./tools`, scrive la firma solo se `pip` riesce, ed
    esce senza decidere; decide il tick dopo, col pacchetto nuovo.

    **Causa:** `due-fonti`

76. **`identita_del_runner()` legge `direct_url.json` senza controllarne la forma.** La
    funzione arriva con `PBI-386` (#324): legge la versione del pacchetto installato e lo sha
    da `vcs_info.commit_id` di `direct_url.json`, con `json.loads(...)` e `.get()` a catena
    (`tools/asdlc/runner.py:489` sul ramo `pbi/pbi-386`). Un file presente ma malformato
    alza `JSONDecodeError`, e un JSON valido che non è un oggetto (o un `vcs_info` che non lo
    è) alza `AttributeError`: in tutti e due i casi si ferma la scrittura del rapporto del
    giro. Regge su un presupposto che nessun test fissa, cioè che il file lo scriva solo
    `pip`, e sempre bene. Era la nota 2 del Critic sulla #324 (01/10/2026), registrata con la
    regola del 30/09. **Letto, non eseguito.** La cura è la stessa di un'installazione senza
    il file: un `direct_url.json` che non si legge dà `"sha": null`, e il giro va avanti.
    Si chiude alla prima occasione in cui un PBI tocca `identita_del_runner()`.

    **Causa:** `ingresso-non-validato`

77. **Il test dell'elenco dei file del giro cerca i percorsi in tutto lo stdout.**
    `TestLElencoDeiFileDelGiroNominaIDueLati` (`tools/tests/test_asdlc_runner.py:6217`,
    `PBI-389`) lancia `esegui_pbi()` e asserisce `"…" in uscita` sull'intero `capsys`, non
    sulla riga dell'elenco. Regge finché nessun'altra stampa del giro nomina quei percorsi:
    oggi nessuna lo fa e il rosso si è visto, ma il giorno in cui un'altra riga li stampasse
    il test non distinguerebbe più un elenco giusto da uno sbagliato. Era la nota 2 del
    Critic sulla #327 (`PBI-389`, 01/10/2026), registrata con la regola del 30/09. **Letto,
    non eseguito.** Cura, alla prima occasione in cui un PBI tocca quel test o l'elenco: il
    test asserisce sul valore restituito dalla funzione dell'elenco, `file_toccati()`, non
    sullo stdout (Francesco, 01/10).

    **Causa:** `strumento-letto-come-testo`

78. **Il `--dry-run` del tick non dice che il `fetch` è fallito.** `indietro()` di
    `tools/asdlc/coda.py` (`PBI-392`, decisione 12) lancia `git fetch` e ne scarta il codice
    d'uscita, poi conta i commit di `origin/main` che `HEAD` non ha. Se il `fetch` fallisce,
    il conto si fa su un `origin/main` vecchio, e la riga `dry-run:` dice «allineato» o
    «indietro di N» come se fosse fresco. Un `origin` raggiunto e uno non raggiunto finiscono
    nella stessa riga. Era la nota 1 del Critic sulla #329 (`PBI-392`, 01/10/2026), registrata
    con la regola del 30/09. **Letto, non eseguito.** Si chiude alla prima occasione in cui un
    PBI tocca `indietro()`: un `fetch` che fallisce si scrive nella riga, con la sua uscita.

    **Causa:** `diagnosi-confusa`

79. **`firme()` prende per albero quello che `git rev-parse` stampa, anche quando fallisce.**
    `firme()` di `tools/asdlc/coda.py` (`PBI-392`) scarta il codice d'uscita di
    `git rev-parse HEAD:tools` e usa l'uscita come albero. Su un checkout senza `tools/`, o
    con `git` che fallisce, al posto dello sha c'è il testo dell'errore: il tick lo trova
    diverso dalla firma, reinstalla una volta e lo scrive in `.installato-da` come firma. Regge
    sul presupposto che il checkout abbia sempre `tools/`, e nessun test lo fissa. Era la nota
    2 del Critic sulla #329 (01/10/2026). **Letto, non eseguito.** È la forma del 12: l'uscita
    di un programma presa come dato senza guardare l'esito. Si chiude alla prima occasione in
    cui un PBI tocca `firme()`: un `rev-parse` che non esce con 0 non è una firma, e il tick
    lo scrive e non reinstalla.
    ✅ Chiuso da `PBI-395` (06/10/2026): `firme()` alza `Guasto` se `git rev-parse` esce
    diverso da 0, e `reinstalla()` scrive `reinstallazione fallita: la cartella <cartella> non
    c'è a HEAD — <uscita di git>` senza chiamare `pip` né toccare la firma.

    **Causa:** `strumento-letto-come-testo`

80. **La decisione 8 di `PBI-392` dice «o il file manca», e nessun caso della Verifica lo
    esercita.** Il tick reinstalla se la firma in `.installato-da` è diversa dall'albero di
    `tools/` **o se il file manca**. Il codice tratta bene il secondo caso (`None` è diverso da
    ogni albero), ma nessun test lo prova: un cambiamento che lo rompesse passerebbe tutti i
    gate. Era la nota 3 del Critic sulla #329 (01/10/2026). **Letto, non eseguito.** Si chiude
    alla prima occasione in cui un PBI tocca `reinstalla()` o `firme()`, con un test per il
    file che manca. Prima occorrenza della causa nuova `decisione-senza-verifica` (Francesco,
    01/10).

    **Causa:** `decisione-senza-verifica`

81. **Un test spostato da un file a un altro si legge come nato.** `test_nuovi_del_commit()`
    decide la nascita dal diff letto come testo: ogni riga `+def test_…` è una nascita, a meno
    che lo stesso nome non sia in una riga `-` **dello stesso file**. `PBI-387` ha chiuso il
    `git mv`, perché lì il diff vede i due lati. Un test che lascia `tools/tests/x.py` ed entra
    in `backend/tests/y.py` nuovo invece nasce, e il gate chiede un rosso a un test che esiste
    dalla base.

    Misurato sul **giro 1 di `PBI-394`, il 03/10/2026** (`runs/20261003-184009.json` in
    `ada-run`): il commit `6406151` sposta `test_le_dipendenze_di_test_sono_dichiarate` in
    `backend/tests/test_dipendenze_dei_gate.py`, come chiede la decisione 5 di 394. Il gate
    l'ha letto come nato verde, senza mutanti da provare né al commit né alla punta, e ha
    fermato il giro con `rosso-mai-visto` dopo 27 minuti, con il lavoro fatto: 10 commit e i
    sei criteri spuntati. Il Builder l'aveva previsto nel riepilogo e non l'ha aggirato.

    È la stessa domanda del difetto 31, a cui `PBI-361` e `PBI-387` hanno risposto un caso
    alla volta. La cura (Francesco, 03/10): la nascita si decide con `pytest --collect-only`
    sulla base e sul ramo, e un test nasce se il suo nome non è nella collezione della base.
    Solo la metà Python: vitest resta al repository `asdlc`. Va a `PBI-396`, in coda davanti
    al giro 2 di 394. Quinta occorrenza della causa, con il 26, il 31, il 33 e il 53.
    Chiuso da `PBI-396` (04/10/2026): `nascite_python()` decide la nascita dalla collezione
    del commit, del genitore e della base, letta dal JSON del plugin `asdlc_collezione`, e il
    lucchetto usa la stessa regola. Misurato sul caso vero: con `6406151` rifatto dentro la
    classe, `--gate-rosso` sui dieci commit del giro 1 di 394 non ferma niente e scrive
    `spostati: 1`.

    **Causa:** `codice-letto-come-testo`

82. **La sonda dei test del runner usa l'interprete di chi la lancia.** La sonda della forma
    del repository `asdlc` (`tools/tests/test_asdlc_fuori_da_backend.py`, `PBI-394`) lancia
    `pytest -q tools/tests` con `sys.executable` (commit `77770a90` sul ramo del giro 1). In aDa è il python di `backend/.venv`, con
    tutte le dipendenze del backend. Il criterio di 394 dice «col solo `pytest` installato», ma
    la sonda non costruisce un venv col solo pytest: un import di un pacchetto del backend in
    `tools/tests` passerebbe nella sonda e fallirebbe nel repository `asdlc`. Era la nota 3
    del Builder nel riepilogo del giro 1 di 394 (03/10/2026). **Letto, non eseguito.** Non si
    corregge ora (Francesco, 03/10).

    **Causa:** `ambiente-non-dichiarato`

83. **I test del tick prendono il lucchetto dentro il progetto di prova versionato.** Col
    giro 1 di `PBI-394` (commit `d06d0b3b`, nel tag `giro-fermato/pbi-394-giro1-20261003`)
    `tools/tests/test_asdlc_coda.py` configura il tick con `coda.REPO =
    tools/tests/dati/progetto/`. I test che prendono `runs/.tick.lock` lo creano lì, in una
    cartella del repository, e `runs/` è ignorata dal `.gitignore` del progetto di prova solo
    per questo. Prima il file finiva nella `runs/` di aDa, già ignorata, e nessuno lo vedeva.
    Il giro 1 l'ha lasciato (`file tools` da 5 a 6 nell'inventario,
    `runs/20261003-184009.json` in `ada-run`), e l'avviso «il giro lascia» tornerà a ogni giro
    che fa girare `tools/tests`. Un test che scrive nel progetto di prova lo cambia anche per
    i test dopo. **Letto, non eseguito.** Non si corregge ora. La cura (Francesco, 03/10): i
    test del tick lavorano su una copia del progetto di prova in `tmp_path`. Arriva in `main`
    col giro 2 di 394.

    **La conseguenza del 05/10/2026.** La cura non è arrivata con i giri di 394: il giro 3
    (23:12 del 04/10) e il giro 4 (15:13 del 05/10) hanno lasciato di nuovo
    `tools/tests/dati/progetto/runs/.tick.lock`. Sul ramo di 394 il file è ignorato dal
    `.gitignore` del progetto di prova, ma in `main` quel `.gitignore` non c'è ancora:
    tornato su `main`, l'albero del runner aveva un file non tracciato, e i tick delle 14:50 e
    delle 15:00 si sono fermati con `albero-sporco-all-ingresso` (`runs/20261005-145014.json`
    e `runs/20261005-150014.json` in `ada-run`). Tolto a mano alle 15:06, il giro 4 è
    partito al tick delle 15:10, e alle 15:49 il file del giro 4 è stato tolto allo stesso
    modo. **Il merge di `PBI-394` chiude il sintomo**, perché porta in `main` il `.gitignore`
    che lo ignora; **la causa resta all'approccio** di `test-senza-isolamento` nel repository
    `asdlc` (Francesco, 05/10).

    **Causa:** `test-senza-isolamento`

84. **Il plugin della collezione importa l'`asdlc` installato invece di quello dell'albero
    esaminato.** Al giro 1 di `PBI-396` (tag `giro-fermato/pbi-396-giro1-20261003`) il plugin
    sta in `asdlc.collezione`, e il runner lo rende importabile mettendo nel `PYTHONPATH` di
    pytest un collegamento al pacchetto `asdlc` installato. Quando la collezione gira su un
    albero che ha un suo `asdlc`, come `tools/tests` di aDa, i test raccolti importano il
    pacchetto installato e non quello dell'albero: la collezione legge un albero e importa da
    un altro. Il Builder l'ha scritto fra le note del giro (03/10/2026); se un file non si
    raccoglie per questo, i suoi nomi vengono dall'AST e l'errore non si vede. **Letto, non
    eseguito.** La cura (Francesco, 03/10): il plugin vive in un modulo che non sta sotto il
    nome `asdlc`, ed è un criterio di `PBI-396` prima del suo giro 2.
    Chiuso da `PBI-396` (04/10/2026): il plugin è il modulo `tools/asdlc_collezione.py`,
    installato con `py-modules`, e sul `PYTHONPATH` di pytest c'è il solo link al modulo. Un
    test raccolto che importa `asdlc` vede quello dell'albero.

    **Causa:** `due-fonti`

85. **Un Builder che chiude il turno con un comando in background ancora in corso esce senza
    esito.** Al giro 2 di `PBI-396` (tag `giro-fermato/pbi-396-giro2-20261004`, `441cc1c4`,
    base `19bb6263`) il Builder ha ripreso i 23 commit del giro 1, ha spuntato i criteri e
    alle 01:06:05 ha lanciato `asdlc-runner --gate-rosso 19bb6263..HEAD` con
    `run_in_background`. Il suo ultimo messaggio dice che aspetta quel gate prima di chiamare
    `fatto`, ma il turno è finito lì: codice d'uscita 0, nessuna chiamata, giro chiuso alle
    01:06 con `builder-senza-esito` e 30 commit (`ada-run/runs/20261004-005008.json`). Il
    gate del runner e il Critic non sono girati. Nessun documento che il Builder legge dice
    che un turno chiuso non torna, né che il gate del rosso lo lancia il runner dopo `fatto`.
    **Letto, non eseguito.** La cura (Francesco, 04/10) è un PBI del repository `asdlc`: la
    guardia di fase rifiuta `Bash` con `run_in_background`, e la regola entra nel prompt del
    Builder. Per il giro 3 di 396 la regola sta nella sua sezione di ripresa.

    **Causa:** `regola-non-scritta`

86. **La riga `spostati: N` non arriva nel rapporto del giro.** Con `PBI-396` (#340) il
    gate del rosso conta i commit che spostano test Python di file, ma la conta la stampa
    solo `--gate-rosso` lanciato a mano (`stampa_il_gate_del_rosso()`). Dentro il giro
    `gate_del_rosso()` si chiama senza `spostati` (`runner.py:3876` sul ramo), e né lo
    schermo né il rapporto JSON dicono che la regola ha agito: al giro 2 di `PBI-394` chi
    legge il rapporto non vedrà `spostati: 1` su `6406151`. Nota del Critic sulla #340, nelle
    revisioni 0 e 1 (04/10/2026). **Letto, non eseguito.** Non blocca il merge della #340. Si
    chiude alla prima occasione in cui un PBI tocca `gate_del_rosso()` o il rapporto del giro
    (Francesco, 04/10): il giro passa `spostati`, e la conta va sullo schermo e nel rapporto
    accanto a `test_che_mordono`.

    **Causa:** `traccia-persa`

87. **Un `conftest.py` del ramo che non si raccoglie fa rinascere i test della sua
    cartella.** Con `PBI-396` (#340) un `conftest.py` che pytest non importa toglie dalla
    collezione l'intera cartella, ma il plugin `asdlc_collezione` mette fra i non raccolti
    solo il conftest. I file di test accanto non entrano né nella collezione né nella rete
    dell'AST, i loro nomi spariscono a quel commit, e al commit dopo i test nati nel ramo
    prima di lì «rinascono», perché il genitore non li ha. Nota del Critic sulla #340, nelle
    revisioni 0 e 1 (04/10/2026). **Letto, non eseguito.** Non blocca il merge della #340. Si
    chiude alla prima occasione in cui un PBI tocca il plugin o `nascite_python()`
    (Francesco, 04/10): un conftest non raccolto porta nella rete dell'AST tutti i file di
    test della sua cartella e delle sottocartelle.

    **Causa:** `caso-scoperto` (nuova, Francesco 04/10)

88. **L'avviso di `apri_la_fase()` perde il traceback.** Dal rimedio della revisione 0 di
    `PBI-396` (`4ed4856d`, #340), `apri_la_fase()` cattura qualunque `Exception` della
    collezione della base e stampa `⚠️ collezione della base non scritta:` con i primi 300
    caratteri del messaggio. È largo di proposito, perché un'eccezione lì lascerebbe la fase
    aperta, ma un errore di programmazione nella collezione diventa una riga a schermo senza
    tipo né traceback, e si rivede solo quando il giro ricalcola la collezione. Nota del
    Critic sulla #340, revisione 1 (04/10/2026). **Letto, non eseguito.** Non blocca il merge
    della #340. Si chiude alla prima occasione in cui un PBI tocca `apri_la_fase()`
    (Francesco, 04/10): l'avviso resta un avviso, e il traceback intero va nel log del giro.

    **Causa:** `traccia-persa`

89. **`--chiedi-impl` apre IMPL senza guardare se lo Scope ha file di produzione.** Al giro 2
    di `PBI-394` (tag `giro-fermato/pbi-394-giro2-20261004`, `51266455`, base `38a0bcea`) il
    Builder ha ripreso il RED `382a10ac` e ha chiamato `--chiedi-impl`, che ha visto il rosso
    e ha portato la fase in IMPL. Il commit dopo, `5ea9dcaf`, aggiunge
    `tools/tests/dati/estrazione.txt`, che per `e_file_di_test()` è un test: in IMPL la
    guardia lo blocca sia in `Edit` sia nel pre-commit. 394 tocca solo test e `backlog/`,
    quindi in IMPL non c'era niente da committare, e dalla fase si esce solo con un commit. Il
    giro si è fermato alle 22:32 con `domanda-del-builder`, dopo un commit; il Builder ha
    rifiutato di committare la sola spunta per uscirne. Era la sua nota per questo PBI
    (04/10/2026). **Letto, non eseguito.** La cura (Francesco, 04/10) è un PBI piccolo del
    repository `asdlc`: `--chiedi-impl` rifiuta, col motivo, quando lo Scope del PBI non ha
    file di produzione; e una IMPL aperta si può annullare finché dopo non c'è stato nessun
    commit. Per il giro 3 di 394 la regola sta nella sua sezione di ripresa.

    **Causa:** `ingresso-non-validato`

90. **`dove_gira()` ha scritte a mano le cartelle `backend/` e `frontend/`.** In
    `tools/asdlc/runner.py` la cartella da cui si rilancia un test isolato si ricava dal
    prefisso del percorso, con `("backend", "frontend")` nel codice, invece che dalle `cwd`
    dei gate di `GATE`. La docstring dice «sono le stesse di `GATE`», ma il codice non le
    legge: in un progetto con un layout diverso il test si rilancia dalla radice. Nel
    repository `asdlc` è un punto del pacchetto che conosce com'è fatto aDa. Nota del Builder
    al giro 3 di `PBI-394` (tag `giro-fermato/pbi-394-giro3-20261004`, 04/10/2026), dove ha
    escluso per questo lo spostamento dei 72 alberi di `repo_di_prova` sotto `tools/tests/`.
    **Letto, non eseguito.** La cura (Francesco, 04/10): `dove_gira()` legge le cartelle da
    `GATE`. Non alla prima occasione: è **fra i primi PBI del repository `asdlc`, prima di
    `v0.2.0`**, perché la Fase 6 lo incontra per forza. Nello stesso PBI va il punto di D3
    (`SCAFFOLDING.md`), i test che trovano il repository con `Path(__file__).parents[2]`:
    è la stessa classe, il layout di un progetto scritto nel codice.

    **Causa:** `default-implicito`

91. **La collezione di un commit si tiene in cache sotto il nome del riferimento, non
    sotto lo sha.** `collezione_al_commit(sha)` (`tools/asdlc/runner.py`, da `PBI-396`) usa
    l'argomento così com'è come chiave: il file `<run>_collezioni/<sha>.json` e la `memoria`.
    `test_nuovi_da_aprire()` la chiama con `"HEAD"`, attraverso
    `test_nuovi_del_commit("HEAD", …)`. Il primo `--chiedi-impl` del giro scrive `HEAD.json`.
    Il secondo, su un RED nuovo e rosso, rilegge quel file, che è la collezione di un `HEAD`
    di prima: la collezione al commit coincide col genitore, e la risposta è «nessun test
    nuovo». Da lì ogni RED del giro ha lo stesso esito. La docstring dice «un commit non
    cambia», ed è vero per uno sha, non per un nome che si muove. Lo stesso guasto del
    difetto 30: un nome che si muove usato al posto dello sha.

    Misurato al giro 1 di `PBI-395` (05/10/2026, tag `giro-fermato/pbi-395-giro1-20261005`,
    `00e0679d`, rapporto `runs/20261005-164011.json` in `ada-run`): primo `--chiedi-impl` su
    `45bfe8a7`, secondo sul RED `00e0679d`, che `pytest` dà rosso, rifiutato. Il Builder si è
    fermato con `fermati` e ha nominato la riga. `PBI-394` non l'ha visto perché non ha mai
    chiamato `--chiedi-impl`; ogni PBI con più di un criterio lo incontra al secondo.

    La cura (Francesco, 05/10): **`PBI-397`, davanti a 395. Le chiavi di cache sono sha
    risolti con `git rev-parse`, mai riferimenti**, e la regola vale per ogni cache del
    runner. Un criterio solo, perché il giro di 397 gira col runner difettoso, e il secondo
    `--chiedi-impl` lo fermerebbe.
    Chiuso da `PBI-397` (06/10/2026): la prima riga di `collezione_al_commit()` risolve
    l'argomento con `git rev-parse --verify <riferimento>^{commit}`, e lo sha risolto è la
    chiave del file, della `memoria` e il commit dell'albero usa-e-getta. Un riferimento che
    non si risolve alza. La regola è nella docstring, accanto alla cache.

    **Causa:** `due-fonti`

92. **Il pre-commit che `apri_la_fase()` installa nel repo di prova chiama il runner vero
    della macchina.** `RepoDiProva.commit()` (`tools/tests/test_asdlc_runner.py`) committa
    con `git commit` e passa dagli hook del repo di prova. Un test che chiama
    `runner.apri_la_fase()` ci installa `GUARDIA_DEL_COMMIT`, che lancia
    `<PACCHETTO>/bin/asdlc-runner --guardia-commit`. Dove `.venv-asdlc` non c'è, come in CI,
    l'hook stampa l'avviso ed esce con 0. Su questa macchina c'è, e il runner esce con 1
    («nessun `asdlc.toml` da `/tmp/.../repo` in su»): il commit che il test fa dopo
    `apri_la_fase()` muore con `CalledProcessError`. Lo stesso test dà un esito in CI e un
    altro sulla macchina del runner.

    Misurato al giro 2 di `PBI-397` (05/10/2026, tag `giro-fermato/pbi-397-giro2-20261005`,
    `6b7f3707`, base `0ce722bd`, rapporto `runs/20261005-174016.json` in `ada-run`). Il caso
    `[file]` del test RED falliva sul `git commit` del repo di prova e non su
    `assert dopo != prima`, già al commit RED: il rosso osservato da `--chiedi-impl` era il
    rosso di un errore. Dopo il GREEN `[memoria]` passa e `[file]` fallisce ancora per lo
    stesso motivo. Il Builder ha rifatto il caso in uno script a parte, con la guardia a
    runner vuoto, e il GREEN regge; si è fermato con la domanda. Gli altri test che
    chiamano `apri_la_fase()` non committano dopo, e non lo incontrano.

    La cura (Francesco, 05/10): **i commit di preparazione dei test saltano gli hook**.
    `RepoDiProva.commit()` committa con `--no-verify`, nel RED del giro 3 di `PBI-397`. Un
    test che vuole l'hook lo installa apposta, con un runner finto. È la quinta occorrenza
    della causa, e la regola entra nell'approccio del repository `asdlc`
    (`backlog/README.md`).

    **Causa:** `test-senza-isolamento`

93. **Una guardia che dice «questo si carica» morde solo con un'eccezione, e l'eccezione non
    conta.** `ADR-0022` conta come morso un `AssertionError` o il `Failed` di
    `pytest.fail`/`pytest.raises`. Un'altra eccezione del codice mutato è un guasto di
    esistenza, e il gate passa al mutante dopo. È la regola giusta per un `NameError`, ma
    non per una guardia il cui comportamento è *non alzare*: lì il mutante che la morde
    alza proprio l'eccezione di dominio che il test esiste per escludere, e il gate lo
    scarta.

    Misurato al giro 2 di `PBI-395` (06/10/2026, tag `giro-fermato/pbi-395-giro2-20261006`,
    `24a84c78`, base `359f2428`, rapporto `runs/20261006-114013.json` in `ada-run`).
    `d08fa5a7`, `test_guardia_le_due_forme_di_installa_si_caricano`, carica le due forme
    ammesse di `[ambiente].installa` con un `assert` sul valore letto. Fra i mutanti, 18
    lo fanno fallire con `asdlc.config.ErroreDiConfigurazione` (e qualche `NameError` e
    `TypeError`), e nessuno per asserzione: «nato verde e non morde», `rosso-mai-visto`.
    Verificato a mano lo stesso giorno: con la chiamata dentro `try`/`except
    ErroreDiConfigurazione` e un `pytest.fail` nel ramo d'eccezione, il mutante che
    rifiuta ogni URL (`if True:` al posto di `if not RE_PIN_URL.fullmatch(installa):`) la
    fa fallire con `Failed`, che il gate conta.

    La cura in aDa: **una guardia che afferma che qualcosa non alza lo scrive con
    `pytest.fail`** nel ramo d'eccezione, e così il morso si misura senza toccare `ADR-0022`.
    Si applica nella ripresa del giro 3 di `PBI-395`. Se contare l'eccezione di dominio
    come morso sia una revisione di `ADR-0022` lo decide Francesco; la cura in aDa non la
    presuppone.

    **Causa:** `regola-non-scritta`

94. **Il perimetro dei mutanti è solo Python, e una guardia su uno script shell non può
    mordere.** `linguaggio_del_file()` sceglie i file da mutare dal linguaggio del test, e
    `Guardia-su:` legge solo sorgenti `.py`. Un test pytest che presidia il comportamento
    di `.claude/hooks/fase-tdd.sh`, se nasce verde, non ha nessun mutante che lo possa far
    fallire: il gate prova le funzioni Python toccate dal ramo e lo ferma, qualunque cosa
    il test guardi. È la terza causa della nota del 23/09 di `ADR-0022`, «il gate», senza
    rimedio dal test.

    Misurato allo stesso giro 2 di `PBI-395`. `39cce442`,
    `test_guardia_fase_tdd_con_installato_e_albero_lancia_l_installato`, è il criterio
    «installato **e** albero» della *Verifica*, scritto dopo il GREEN `699c4578` che lo
    rendeva già vero: 123 mutanti provati, tutti in `coda.py`, `config.py` e `runner.py`,
    nessuno su `fase-tdd.sh`. Verificato a mano lo stesso giorno: col `fase-tdd.sh` della
    base, il test **fallisce**. Il rosso c'era, ma solo prima del GREEN, e lì il commit non
    c'era. Fallisce però con `FileNotFoundError` su `installato.read_text()`, non con un
    `AssertionError`.

    La cura in aDa: **un criterio il cui comportamento vive in un file che il gate non muta
    nasce nel RED**, insieme agli altri test dello stesso GREEN, e mai come guardia dopo.
    Si applica nella ripresa del giro 3 di `PBI-395`. Se il perimetro debba allargarsi agli
    script shell, che vuol dire mutarli e rilanciare un test Python, è una scelta per il
    repository `asdlc` e la decide Francesco.

    **Causa:** `regola-non-scritta`

95. **La pausa del tick è una per utente, e ferma tutti i progetti della macchina.**
    `file_di_pausa()` (`coda.py`) è `Path.home() / "asdlc-tick.pausa"`: nessuna chiave di
    `asdlc.toml` la nomina, e ogni progetto che installa il pacchetto legge lo stesso file.
    Finché il runner viveva in aDa c'era un progetto solo, e la differenza non si vedeva.

    Misurato il 07/10 al passo 2.7 della Fase 5: con la pausa messa per aDa dal passo 1,
    `.venv-asdlc/bin/asdlc-coda --dry-run` lanciato da `/home/laisdev/ada_asdlc` risponde
    `in pausa:`, e il controllo del 2.7 («in coda non c'è niente») si è potuto fare solo con
    una `HOME` temporanea. Dal passo 4.2 i due cron girano sulla stessa macchina: mettere in
    pausa aDa per chiudere un giro fermato spegne anche `asdlc`, e viceversa, senza che il
    `coda.log` dell'altro dica di chi era la pausa.

    La cura da decidere: il file di pausa per progetto (nella radice comune, o una chiave di
    `[ambiente]`), con un file per la macchina intera solo se serve davvero. Fino ad allora
    la regola 1 del runbook della Fase 5 (pausa dal passo 1 al 4) vale per tutti e due.

    **Causa:** `ambiente-non-dichiarato`

96. **Il messaggio della guardia di fase nomina un comando che non c'è più.** In
    `TEST_ONLY`, la guardia che blocca una scrittura di produzione dice al Builder di
    lanciare `tools/asdlc/runner.py --chiedi-impl` (`runner.py`, righe 1358 e 1364), il
    sorgente come stava in aDa prima del `PBI-384`. Il comando vero è
    `<pacchetto>/bin/asdlc-runner --chiedi-impl`, ed è `comando_del_pacchetto()` a
    costruirlo per l'hook e per la config della sessione: il testo del messaggio è una
    seconda copia dello stesso comando, scritta a mano, ed è rimasta indietro.

    Misurato il 07/10 al passo 3.4 della Fase 5, in aDa col runner `0.1.0` installato: una
    `Write` su `backend/app/status.py` in un worktree con la fase `TEST_ONLY` esce con 2,
    come deve, e lo stderr dice «poi `tools/asdlc/runner.py --chiedi-impl`». In aDa
    `tools/asdlc/` non esiste più. Un Builder che segue il messaggio alla lettera lancia un
    file che non c'è; il prompt del Builder ha il comando giusto, e oggi è lui a salvarlo.

    La cura: il messaggio prende il comando da `comando_del_pacchetto("asdlc-runner")`, e un
    test controlla che la stringa della guardia nomini quello e non un percorso.

    **Causa:** `due-fonti`

97. **Il Builder non può scrivere sotto `.claude/`, nemmeno dentro un'altra cartella.**
    Claude Code tratta ogni percorso con un segmento `.claude/` come file sensibile, e per
    scriverci chiede un permesso. In un giro nessuno è davanti alla sessione per darlo, e
    nessuna voce di `asdlc.toml` né la guardia che il runner passa con `--settings` lo
    concede. Il comportamento dipende da una regola della sessione che nessun file del
    progetto dichiara.

    Misurato l'08/10 al giro 1 di `PBI-501` (tag `giro-fermato/pbi-501-giro1-20261008`,
    `7a47fda`, rapporto `runs/20261008-230505.json` in `ada_asdlc-run`). `--chiedi-impl` ha
    visto il rosso e ha aperto IMPL. Poi `mkdir -p template/.claude/hooks` e
    `Write template/.claude/settings.json` sono stati negati: «…which is a sensitive file»,
    «…you haven't granted it yet». Il Builder si è fermato senza aggirarlo da shell. La
    risposta per quel PBI (Francesco, 08/10): il criterio esce, e la copia la fa una persona.

    La cura da decidere: il runner concede alla sessione del Builder la scrittura sotto i
    percorsi `.claude/` che lo Scope nomina, con `--settings` o con le regole dei permessi,
    e un test lo prova su un PBI di prova. Diventa attiva al tag dopo quello che la porta
    (`ADR-0026`).

    **Causa:** `ambiente-non-dichiarato`

98. **Il test della coda vuota del template passa perché gli esempi sono fra backtick.**
    `test_la_coda_del_template_e_vuota_e_ne_porta_la_grammatica`
    (`tools/tests/test_asdlc_template.py`) passa a `leggi_voci()` tutto `template/backlog/CODA.md`
    e chiede `voci == []`. Ma la prosa sopra `## La coda` ha gli esempi della grammatica:
    `- PBI-12` e `- ‖`. Il test è verde solo perché quegli esempi stanno fra backtick, e
    `RE_PBI` e `RE_BARRIERA` vogliono il trattino a inizio riga. Se un esempio perdesse i
    backtick il test diventerebbe rosso, eppure la coda sarebbe ancora vuota. In breve,
    il test non guarda dove sta la voce. Chiede «nessuna riga del file è una voce», non
    «la sezione `## La coda` è vuota», e il verde dipende dalla forma della prosa.

    Nota del Critic sulla #12 (`PBI-502`, rapporto `runs/20261009-000505-PBI-502-critic-0.md`
    in `ada_asdlc-run`, 09/10/2026), registrata al merge con la regola di
    `backlog/README.md`, §I difetti e le loro cause. Registrata come difetto da Francesco
    (09/10): un test che passa per il motivo sbagliato. La cura possibile è leggere le voci
    dalla sola sezione `## La coda`, perché è lì che il tick le cerca. Ancora da decidere.

    **Causa:** `test-per-il-motivo-sbagliato` (nuova, Francesco 09/10)

## ⛔ `ada-notte.sh` deve sparire (Francesco, 26/08/2026)

> *«Non voglio più vedere ada-notte.sh: eliminato, e usiamo solo asdlc_runner.»*

Quello script vive **fuori dal repository** — `/home/laisdev/ada-notte.sh`, 3.255 byte, non
tracciato — e fa quattro cose che il runner non fa:

| | oggi | difetto |
|---|---|---|
| venv sul `PATH` dei sottoprocessi | `export PATH="$WT/backend/.venv/bin:$PATH"` | 11 |
| registro fuori dall'albero di lavoro | `REG=~/ada-tempi-notte.csv` | 12 |
| archivio dei rapporti del Critic | `ARCHIVIO=~/ada-rapporti` | 12 |
| **staccarsi dalla sessione** | `setsid nohup … < /dev/null &` | **15** |

Finché esistono, il runner ha due modi di comportarsi a seconda di chi lo chiama, e quello
giusto è documentato in uno script che nessuno vede. Il 26/08 ho scritto `export PATH=…` a
mano **quattro volte in un pomeriggio**: è la definizione di una riga che appartiene al
codice.

✅ **Le quattro righe sono assorbite, e lo script è uscito di scena il 29/08/2026.** Le
prime due e la quarta stanno nel runner (`venv_sul_path()`, `ADR-0020`, `stacca()`); la
terza non serve più, perché i `runs/*.json` sono diventati la sorgente di `--registra` e
portarli via vorrebbe dire perdere le righe. Il file è **rinominato** in
`/home/laisdev/ada-notte.sh.bk`, non cancellato: il `rm` si fa dopo la prima corsa che
prova sul campo che l'assorbimento tiene.

⚠️ **L'ordine non è negoziabile: prima il runner assorbe, poi lo script si cancella.**
Toglierlo adesso lascerebbe i lanci senza la scorciatoia *e* senza il rimedio. La
cancellazione è l'ultimo gesto di questo PBI, non il primo — e la fa una persona, perché il
file sta fuori dal repository e nessun merge può toccarlo.

**Il numero resta lo strumento sbagliato, e va detto nel codice.** Il criterio giusto non è
*quante volte* ma *smetti quando un giro non produce più niente di sostanziale* — e il
Critic già distingue da sé le due cose: al quinto giro ha scritto *«Non è una violazione,
ma va detto»*. Quel segnale oggi il runner non lo legge. Se il formato di uscita del Critic
venisse esteso con una riga di conteggio (`BLOCCANTI: n`), la convergenza diventerebbe
misurabile e il tetto tornerebbe a essere solo un backstop.

**Scope**
- `tools/asdlc_runner.py` — la costante, lo stato nuovo, la colonna `stato` del CSV, lo
  stato `sospeso` per i rilievi che aspettano una persona, e il ritorno su `origin/main`
  prima di creare il branch.
- `tools/asdlc_runner.py`, ancora — il `push` fuori da `apri_pr`, e il commit di
  `runs/tempi.csv` a fine invocazione.
- `tools/asdlc_runner.py`, ancora — `MAX_IGIENE`, `PROMPT_IGIENE`, e il tetto dei gate che
  torna a valere per revisione invece che per PBI.
- `tools/asdlc_runner.py`, ancora — il PBI letto da `origin/main` invece che dall'albero
  estratto (difetto 7), e il `fermato` che **pusha il branch** prima di uscire, col nome
  disambiguato al rilancio (difetto 8).
- ~~`tools/asdlc_runner.py`, ancora — il lucchetto sul worktree e il censimento degli agenti
  che ci lavorano (difetto 9).~~ **Fuori dallo scope perché già fatto**, il 25/08.
- `tools/asdlc_runner.py`, ancora — il conteggio dei commit prima di ogni uscita (difetto 10),
  `esegui()` che cattura `FileNotFoundError` (difetto 11), l'URL della PR estratto per forma e
  `runs/tempi.csv` committato a fine invocazione (difetto 12).
- `tools/asdlc_runner.py`, ancora — la sorte del gate e2e da un worktree: stack del branch
  ricostruito a ogni giro, oppure `--e2e` tolto e l'e2e lasciato alla CI (difetto 13), e la
  coda dell'output di ogni gate rosso nel log e nel rapporto JSON (difetto 14).
- `tools/asdlc_runner.py`, ancora — il venv sul `PATH` (difetto 11), il registro e i rapporti
  fuori dall'albero (difetto 12) e il distacco dalla sessione con `--in-primo-piano` per
  disattivarlo (difetto 15): le quattro cose che oggi fa `ada-notte.sh`, così che quello
  script possa essere cancellato.
- `tools/asdlc_runner.py`, ancora — il nome del branch disambiguato quando `origin` ce l'ha
  già (difetto 16), l'eccezione di un PBI che chiude **quel** PBI invece di uccidere la
  sequenza, e il rapporto JSON con la riga del registro scritti a ogni PBI concluso
  (difetto 17).
- `tools/asdlc_runner.py`, ancora — chi pubblica il branch e quando: il push sta in
  `apri_pr` e non nel giro del Builder, e il push del proprio branch è
  `--force-with-lease` (difetto 18).
- `tools/asdlc_runner.py`, ancora — il rapporto del giro aperto **all'inizio** con lo stato
  `in-corso` e chiuso alla fine, così che un giro ucciso a metà resti scritto (difetto 20).
- `tools/asdlc_runner.py` · `backend/requirements-dev.txt` — le dipendenze di test
  dichiarate, e il controllo che i comandi dei gate esistano prima del primo PBI
  (difetto 21).
- `backlog/AUTOMAZIONE.md` — il giro che fa il runner, se il diagramma cambia.
- Nessun PBI, nessuna spec, nessun ADR: qui si tocca lo strumento.

## Dipendenze
- Bloccato da: nessuno.
- **`runs/tempi.csv` va versionato prima o insieme**: è il registro su cui questa misura si
  legge, e oggi è ancora non tracciato nonostante `.gitignore` dica il contrario.

## Contesto
- `tools/asdlc_runner.py` — `MAX_REVISIONI`, `Esito.stato`, `COLONNE_CSV`.
- `backlog/AUTOMAZIONE.md` — *«l'autonomia non è una proprietà dello strumento: è una
  proprietà del gate»*.
- I sei rapporti del Critic su PBI-201, se qualcuno vuole rifare il conto della tabella
  qui sopra.

## Verifica
- [x] Un PBI presente su `origin/main` ma non nell'albero estratto del worktree **si
      esegue**, invece di chiudere «saltato (PBI inesistente)» (difetto 7).
      ✅ Fatto il 29/08: `trova_pbi()` chiede il nome del file a `origin/main` — lo stesso
      da cui `crea_branch` ramifica un attimo dopo — e senza rete si ripiega sull'albero
      estratto **dichiarandolo**. Era il difetto che stava per costare il giro delle
      analitiche: quei PBI nascono su `main` dopo l'ultimo `switch` del worktree.
- [x] Un PBI che chiude `fermato` ha il suo branch **su `origin`** prima che il processo
      esca, e il rilancio dello stesso PBI non muore su «esiste già un ramo» (difetto 8).
      ✅ Fatto il 29/08: `chiudi()` pubblica su ogni stato che interrompe, e `nome_libero()`
      prende il primo nome che `origin` non ha.
- [x] Un giro che si chiude `fermato` scrive nel registro **quanti commit ha prodotto**
      davvero (difetto 10). ✅ Fatto il 29/08: il conteggio entra in `chiudi()`, che è
      l'unica strada da cui si esce, e `conta_commit()` non alza — un conteggio mancato
      non cancella quello di prima.
- [x] Un gate il cui comando non esiste chiude `rosso` con la diagnosi giusta e **lascia la
      sua riga** nel registro, invece di far morire il processo (difetto 11).
      ✅ Fatto il 29/08: `esegui()` cattura `FileNotFoundError` e torna `127` con la nota,
      e `venv_sul_path()` toglie di mezzo la causa più frequente. ⚠️ *«la sua riga in
      `runs/tempi.csv`»* adesso vuol dire **nel rapporto del giro**: il CSV non lo scrive
      più il branch (`ADR-0020`), e da lì la riga entra con `--registra`.
- [x] L'URL della PR si riconosce per forma, e un warning di `gh` non finisce nella colonna
      `pr` (difetto 12). ✅ Fatto il 29/08: un regex su `https://…/pull/N`, e se non c'è la
      colonna resta **vuota** — una colonna che mente costa più di una che tace.
      ⚠️ **La seconda metà del difetto 12 è stata rovesciata**: *«`runs/tempi.csv`
      committato a fine invocazione»* era la causa travestita da cura — più commit sullo
      stesso file condiviso, più conflitti. `ADR-0020` decide il contrario: il CSV **esce
      dai branch**.
- [x] Il gate e2e o prova **il codice del branch**, o non è un gate del runner: `--e2e` non
      può restare un flag che produce un rosso parlando di un altro checkout (difetto 13).
      ✅ Deciso il 29/08 fra le due strade che il PBI dava, e la strada è la seconda: l'e2e
      **esce da `GATE`** e resta alla CI sulla PR, che lo stack lo costruisce dal branch
      (`ADR-0009`). `--e2e` resta come flag e **ferma il lancio** spiegando dove girano
      davvero: toglierlo darebbe un «unrecognized arguments» a chi se lo ricorda.
- [x] Il runner si stacca dalla sessione da solo: chiudere il terminale che l'ha lanciato
      **non** interrompe il giro, e `--in-primo-piano` serve a chiedere il contrario
      (difetto 15). ✅ Fatto il 28/08: `stacca()` forka prima del lucchetto, il figlio prende
      `setsid()` e scrive in `runs/<run>.log`, accanto al rapporto JSON dello stesso giro.
- [x] **`/home/laisdev/ada-notte.sh` non si lancia più**, e lanciare il runner a mano non
      richiede di ricordarsi niente: né il `PATH`, né `setsid`, né dove finisce il registro.
      È il criterio che chiude il PBI, e si spunta **per ultimo**.
      ✅ Fatto il 29/08/2026 da Francesco. ⚠️ **Rinominato, non cancellato**: il file è oggi
      `/home/laisdev/ada-notte.sh.bk`. La lettera del criterio diceva *«è cancellato»* e la
      differenza si dichiara invece di tacerla — un `.bk` non è un `rm`. Basta però a
      chiudere il criterio, perché ciò che il criterio protegge è che **non esistano due
      modi di lanciare il runner**: fuori dal nome che le dita conoscono, quello script non
      è più una strada, è una copia da leggere. Il `rm` vero resta un gesto di Francesco,
      dopo la prima corsa che conferma sul campo le quattro assorbizioni.
      ⚙️ *La metà del runner è fatta il 29/08*: `setsid` (difetto 15), il `PATH` con
      `venv_sul_path()`, e il registro che il giro dichiara a schermo (`ADR-0020`).
      L'archiviazione dei `runs/*.json` fuori dal repository — l'ultimo mestiere dello
      script — non va più fatta: quei rapporti sono la **sorgente** di `--registra`, e
      portarli via vorrebbe dire perdere le righe.
- [x] Un PBI il cui branch esiste già su `origin` con un'altra storia **apre lo stesso la
      sua PR**, su un nome disambiguato: un giro riuscito non resta senza remoto per colpa
      di un giro fallito prima (difetto 16). ✅ Fatto il 29/08: `rami_su_origin()` +
      `nome_libero()`, `pbi/pbi-322` → `-giro2` → `-giro3`.
- [x] Un'eccezione su un PBI chiude **quel** PBI, e se proseguire lo decide la regola che
      esiste già (`STATI_CHE_INTERROMPONO`): il traceback non è più un modo in cui una
      sequenza finisce (difetto 16). ✅ Fatto il 29/08: l'eccezione diventa un `Esito`
      rosso con la sua diagnosi nella nota, e il traceback resta nel log.
- [x] Il rapporto JSON di un PBI c'è **appena quel PBI è finito**. Uccidere il processo a
      metà sequenza non cancella i rilievi del Critic dei PBI già chiusi (difetto 17).
      ✅ Fatto il 29/08: `scrivi_rapporto()` è l'unico scrittore e gira dopo ogni PBI.
      ⚠️ La riga *«in `runs/tempi.csv`»* non c'è più per scelta: il registro esce dai
      branch (`ADR-0020`), e il rapporto è il posto da cui `--registra` la prende.
- [x] Il branch di un PBI arriva su `origin` **una volta sola, a PBI finito**: nessuna PR
      esiste mentre il Critic sta ancora chiedendo giri, e un branch riscritto fra un giro e
      l'altro si pubblica lo stesso invece di far morire il processo (difetto 18).
      ✅ Fatto il 29/08: `pubblica()` con `--force-with-lease` che non alza mai, chiamata
      solo da `apri_pr` sulla strada buona, e il divieto scritto nel prompt del Builder —
      che era chi pushava dentro il giro. ⚠️ **La metà del Builder non è verificabile da un
      test**: il divieto è una frase in un prompt, e la prova che funziona è la prossima run
      che non apre una PR prima del Critic.
- [x] Due run che finiscono a cavallo di un merge **non si contendono l'ultima riga** di
      `runs/tempi.csv`: il registro non è più un file che ogni branch appende in coda
      (difetto 19, deciso insieme al 12). ✅ `ADR-0020`, deciso da Francesco il 29/08:
      il giro lascia il rapporto, `--registra` piega i rapporti nel CSV **su `main`, dopo
      il merge**, con chiave `(run, pbi)` e in ordine di `iniziato`.
- [x] Di un gate rosso resta **la ragione** e non solo il verdetto: la coda del suo output
      sta nel log e nel rapporto JSON, leggibile senza avere il Builder sotto mano
      (difetto 14). ✅ Fatto il 29/08: `gate_rossi` tiene `{gate, coda}` e la coda si
      stampa, cioè finisce in `runs/<run>.log`.
- [x] Un giro **ucciso a metà** lascia comunque la sua traccia: `runs/<run>.json` esiste
      dall'inizio con lo stato `in-corso` e senza `finito` (difetto 20). Il CSV condiviso non
      si tocca all'apertura, per non peggiorare il difetto 19. ✅ Fatto il 29/08 con
      `apri_rapporto()` / `chiudi_rapporto()`. ⚠️ **Il test non simula la morte del
      processo**: verifica che il rapporto esista *prima* del primo PBI, che è la condizione
      da cui la traccia discende. Uccidere un processo dentro pytest costa più di quanto
      dimostri.
- [x] Le dipendenze di test sono **dichiarate** in un file, e un albero nuovo si allestisce
      leggendolo invece che sapendolo (difetto 21). ✅ `backend/requirements-dev.txt`.
- [x] Il runner **verifica che i comandi dei suoi gate esistano** prima del primo PBI,
      accanto al lucchetto e al censimento degli agenti, e li nomina tutti in un colpo solo:
      un `pytest` che manca si dice in tre secondi, non dopo mezz'ora di Builder
      (difetto 21). ✅ `gate_mancanti()`, sui soli gate accesi e non su un `--dry-run`.
- [x] Due runner nello stesso worktree non partono insieme, e un agente che ci sta già
      lavorando ferma il lancio **prima** del primo PBI (difetto 9). ✅ Fatto il 25/08, a
      mano e fuori dal runner: lo strumento che deve smettere di sovrascriversi non si
      ripara con un giro di se stesso sullo stesso albero. Lo scostamento è questo, e resta
      scritto qui invece di sparire — stessa forma della riga sulle revisioni, più sotto.
- [x] Un PBI che esaurisce le revisioni chiude `non convergente`, non `respinto`, e la nota
      rimanda al rapporto JSON. **Fatto a mano la notte del 20→21/08**, fuori dal runner e
      prima della run notturna: con `MAX_REVISIONI = 2` quella run avrebbe misurato una
      soglia che stavamo già sostituendo. Lo scostamento è questo — un PBI eseguito a mano
      invece che dal runner — e resta scritto qui invece di sparire.
- [x] `runs/tempi.csv` distingue i due stati, e `--riepilogo` non li somma insieme. La
      colonna **esiti** dice cosa ha comprato quel tempo (`fatto·1  non convergente·1`), e
      una riga di totale li conta tutti. Il registro entra nel repository con le tre
      esecuzioni della run notturna già dentro: senza quelle, `--riepilogo` misurava un
      file che non esisteva.
- [x] Il commento accanto a `MAX_REVISIONI` spiega che è un backstop e non un criterio, e
      cita la misura di PBI-201. Era già così dal giro precedente.
- [x] Un `--riepilogo` su un CSV che contiene entrambi gli stati resta leggibile: la
      colonna nuova è l'ultima e a larghezza libera, quindi le cinque che c'erano non si
      spostano.
- [x] Un rilievo del Critic che chiede una decisione umana chiude il PBI **sospeso** al
      primo giro, non `non convergente` all'ultimo: il costo di quella diagnosi si misura in
      giri risparmiati, e su PBI-203 sarebbero stati quattro. Il Critic ha un terzo verdetto
      (`VERDETTO: SOSPESO` + `STOP:`), e un sospeso **senza** domanda è un guasto e non un
      giudizio — sospendere senza dire cosa si aspetta lascia una persona davanti a un muro.
      `sospeso` resta distinto da `fermato` perché il rimedio è diverso: il primo si chiude
      rispondendo, il secondo riscrivendo il PBI che era ambiguo.
- [x] Il runner crea il branch **da `origin/main`**, non da dove si trova, e lo verifica:
      due PBI nella stessa invocazione producono due branch fratelli, non impilati.
      Quando questo è vero, il ciclo esterno di `ada-notte.sh` può restare per igiene ma
      non è più un rimedio. `crea_branch` fa `fetch` → `switch main` → `merge --ff-only
      origin/main` → `switch -c`, e il `--ff-only` è la parte che protegge: se `main` ha
      commit che origin non ha, fallisce rumorosamente invece di costruire il PBI su una
      base che nessun altro vede.
- [x] Un PBI che chiude `non convergente`, `sospeso` o `fermato` ha il suo branch **su
      `origin`**, e il registro lo dice: la colonna `pr` resta vuota — la PR è dell'umano —
      ma il branch esiste in un posto che non è il worktree. Si misura riportando PBI-207:
      con il runner di oggi il branch era locale, con quello nuovo dev'essere su origin
      prima ancora che qualcuno legga il rapporto. ✅ Fatto il 29/08 dentro `chiudi()`, per
      tutti gli stati di `STATI_CHE_INTERROMPONO` — `rosso` compreso, che ha commit come
      gli altri. La misura su PBI-207 resta da fare alla prossima run.
- [x] Un giro speso a chiedere un commit non consuma un tentativo di gate, e un albero che
      resta sporco chiude `fermato` dicendo *questo* invece di «gate rossi» — che su
      PBI-208 era falso, perché i gate non erano mai partiti. Quattro test in
      `backend/tests/test_asdlc_runner.py`, più un quinto che difende il contorno scoperto
      scrivendoli: il tetto dei gate vale **per revisione**, e `e.tentativi` — che non si
      azzera mai perché è la fatica che finisce nel registro — non può essere il criterio
      d'uscita. Farlo diventare tale avrebbe lasciato la terza revisione senza un giro:
      lo stesso `rosso` senza gate, spostato di un livello.
- [x] ~~`runs/tempi.csv` è committato a fine invocazione~~, e una `git status --porcelain`
      nel worktree torna pulita anche su `runs/`. Il controllo d'igiene ha smesso di
      escludere `runs/`: quell'eccezione esisteva perché il file restava sporco, e se non
      resta sporco non serve più — finché serve, è il sintomo che questo punto non è
      chiuso. ✅ Fatto il 29/08, **dall'altro capo**: non committando il registro più
      spesso, ma togliendolo dal branch (`ADR-0020`). Il chiodo invece della toppa — la
      prima metà della riga è barrata perché è la strada che l'ADR ha scartato.
      ⚠️ **La seconda metà era falsa quando è stata spuntata**, e l'ha detto il primo
      lancio vero: `git status --porcelain` **non** tornava pulita su `runs/`, perché
      `stacca()` ci scrive il log del giro e `.gitignore` non lo copriva. Difetto 22.
- [x] **Il runner non si ferma su ciò che ha scritto lui.** Un giro parte su un worktree
      pulito e resta partito: il log che `stacca()` crea in `runs/<run>.log` non conta come
      albero sporco, perché è ignorato accanto al rapporto JSON di cui è il gemello
      effimero (difetto 22). ✅ Fatto il 29/08: una riga di `.gitignore`, trovata da un giro
      di sei secondi dopo otto ore di test verdi.

- [x] **Un nome di branch occupato in locale è occupato anche per il runner.** Con un
      `pbi/pbi-XXX` che esiste in locale e **non** su `origin` — la combinazione che lascia
      un PBI scritto su un branch e mergiato — `esegui_pbi` non muore su
      *«esiste già un ramo»*: prende il nome libero successivo. Difetto 23, misurato su
      PBI-103 il 30/08.
      ✅ Fatto il 03/09: `rami_locali()` chiede gli stessi nomi a `git branch --list`, e
      `nome_libero()` riceve l'unione dei due insiemi. I rami sono del repository e non
      del worktree, quindi li vede anche un giro che gira in un albero staccato.
      ⚠️ **Scritto il 30/08 e ricaduto il 02/09**, perché scriverlo non lo chiude: il
      lancio di PBI-335 (`20260902-220921`) è morto in **zero secondi** sul residuo del
      28/08, il commit che aveva scritto il documento del PBI, mergiato e cancellato su
      `origin` ma rimasto in `ada-run`. Fra la misura e il rimedio ci sono stati quattro
      giorni e un giro perso: è il costo di una riga non spuntata, e vale la pena averlo
      scritto qui accanto alla spunta.

- [ ] **Un Builder a cui è stata tolta la parola non è un Builder che ha dimenticato il
      `git add`.** Se l'output del Builder porta il limite d'uso dell'account (*«You've hit
      your session limit»*), il giro non consuma i giri d'igiene né i tentativi di gate:
      chiude `fermato` con una nota che nomina il limite e l'ora del reset, oppure aspetta
      il reset e riprende con `-c`. Difetto 27, misurato su PBI-333 il 02/09.
      Dal 24/09 le due metà si dividono: il limite non consuma igiene né tentativi perché è
      un `senza esito` (`PBI-367`), e l'ora del reset nella nota la legge `PBI-363`.

- [x] **Un mutante è ucciso solo da un'asserzione, e la riga che decide si muta.** Una
      guardia che muore di un'eccezione del codice mutato non è uccisa; la riga unica del suo
      blocco ha un mutante `pass`; il rapporto dice per ogni guardia mutante e tipo di
      fallimento. Difetto 33, punti 2 e 3, misurato sulla #254. Chiuso da `PBI-365`.
      ✅ Fatto il 24/09 da `PBI-365`: il gate rigira i test con `pytest -vv -rf` e
      `falliti_per_asserzione()` tiene solo i `FAILED` di tipo `AssertionError` o `Failed`;
      `sorgente_del_mutante()` scrive `pass` dove la riga cancellata non compila; ogni morso
      porta `tipo` e `prove`, e vitest dice che il tipo non è misurato.

- [x] **Nessun esito si ricava dal testo del modello.** Il Builder e il Critic dichiarano
      l'esito con una chiamata a strumento, e una risposta senza chiamata è `senza esito`, che
      ferma la coda. Difetti 34, 35 e 36. In coda con `PBI-366` e `PBI-367` (`ADR-0027`).
      ✅ Fatto il 24/09 da `PBI-367`: ogni invocazione ha la sua config MCP e il suo file
      d'esito in `runs/`, `esito_dichiarato()` è l'unica lettura, un agente senza chiamata
      valida chiude `senza esito` — senza igiene né gate, con stdout, stderr e codice d'uscita
      nel rapporto — e la coda si ferma pubblicando il ramo anche vuoto.
      ✅ **Collaudato su un giro vero il 25/09**, il primo col codice di 367: `PBI-370`,
      `runs/20260925-103016.json`, PR #270. Il Builder e il Critic hanno fatto una chiamata
      ciascuno, `fatto` e `fatto` con `verdetto: pass`, registrate nel loro
      `.chiamate.jsonl`. Il rapporto porta l'esito dei due file d'esito:
      `rapporto_critic` coincide con il `riepilogo` del file del Critic. Lo stdout dei due
      agenti non contiene né il riepilogo né un marcatore (`VERDETTO`, `FATTO:`), quindi non
      c'era un testo da cui leggere l'esito. Config generata, allowlist
      `mcp__asdlc__fatto mcp__asdlc__fermati` e albero pulito dopo il Builder, grazie al
      difetto 44 chiuso la mattina stessa. **Il collaudo del protocollo a strumenti è
      chiuso.**

- [x] **Un giro che si interrompe per un'eccezione passa dalla chiusura.** Ramo pubblicato,
      commit contati, eccezione nella nota; il timeout di un agente chiude `senza esito` con
      i flussi parziali, e allo scadere non restano processi del gruppo. Difetto 37. In coda
      con `PBI-369`.
      ✅ Fatto il 25/09 da `PBI-369`: il corpo di `esegui_pbi` sta in un `try`, e
      un'eccezione chiude `rosso` passando da `chiudi()`, con tipo e messaggio nella nota e
      il traceback in `runs/*_traceback.log`; una chiusura che fallisce sale a `main()`
      come «chiusura del giro fallita». Le chiamate agli agenti scrivono i flussi su file
      mentre girano, partono in una sessione loro e hanno un tetto per ruolo
      (`[soglie].minuti_builder = 90`, `minuti_critic = 25`): scaduto, si uccide il gruppo
      (`SIGTERM`, poi `SIGKILL`) e il giro chiude `senza esito`. Ogni chiamata lascia ruolo,
      durata e codice d'uscita in `runs/<run>.json`.

- [x] **I test del runner non scrivono nella cartella vera.** Un giro di `tools/tests`
      lascia `runs/` com'era. Difetto 38. In coda con `PBI-370`.
      ✅ Fatto il 25/09 da `PBI-370`: una fixture `autouse` in `tools/tests/conftest.py`
      sposta in una cartella temporanea ogni percorso del runner sotto `LOG_DIR`, anche dopo
      un `configura()` chiamato dal test, e `file_dell_invocazione()` prenota il nome del
      prompt con `O_EXCL`, così due invocazioni nello stesso istante non si sovrascrivono.

- [ ] **Nessun albero usa e getta sopravvive al giro che lo ha montato**, e se uno
      sopravvive il rapporto lo dice: il conteggio di quelli montati e di quelli smontati
      sta nel `runs/<run>.json`, non nella memoria di chi guarda `/tmp`. Difetto 28,
      misurato dopo il giro 6 di PBI-333 il 02/09.

- [x] **Su `origin` finisce ciò che i gate hanno misurato.** Il push del giro parte da
      `HEAD` e non dal ref del ramo, e un giro in cui i due divergono **non apre la PR**: si
      chiude `fermato` nominando i due sha. Si misura riproducendo PBI-358 — worktree
      staccato, ref del ramo indietro di un commit: con il runner di oggi la PR nasce lo
      stesso e la CI è rossa, con quello nuovo il giro si ferma e lo dice. Difetto 30,
      misurato il 21→22/09. ✅ Fatto il 22/09 da `PBI-362`: `pubblica()` manda
      `HEAD:refs/heads/<ramo>` quando il ref è indietro e poi lo riallinea con `branch -f`,
      e `apri_pr()` confronta `ls-remote` con `rev-parse HEAD` prima di `gh pr create`.

- [x] **Un test che trasloca non nasce.** Un commit di solo `git mv` di un file di test
      produce zero test nuovi, un rename con modifiche produce i soli test che le righe
      aggiunte introducono, e il conteggio non cambia con `diff.renames = false` nella
      configurazione. Vale anche per l'albero di lavoro, cioè per il lucchetto *ex ante*.
      Difetto 31, misurato su PBI-360 il 22/09 — e il giro non può chiuderlo da sé, perché il
      gate che sbaglia è quello che lo sta giudicando.

- [x] **Un modulo che trasloca non entra nel perimetro.** Un `git mv` senza cambi di un file
      di produzione non mette nel perimetro nessuna sua funzione, una riga cambiata mette
      quella funzione sola, e il rename si legge anche con `diff.renames = false`. Nel runner
      nessun `git diff` o `git show` con pathspec passa fuori da `diff_del_file()`. Difetto
      61, eseguito il 28/09. ✅ Fatto il 29/09 da `PBI-387`.

- [x] **Un rename si legge sui due lati anche ai confini.** Un file che entra in produzione
      da fuori (`git mv nota.txt backend/app/x.py`) mette nel perimetro tutte le sue righe;
      l'elenco dei file del giro nomina i due lati di un rename; nel runner nessun
      `git diff --name-only` resta fuori dalla funzione unica. Difetti 63 e 64, dalle note
      del Critic sulla #305 il 29/09. In coda con `PBI-389`.
      ✅ Fatto il 01/10 da `PBI-389`.

- [x] **Pytest si legge dal suo rapporto, non dallo schermo.** Un test con uno spazio nell'id
      ha il suo esito e non quello dei totali; un mutante che lo fa fallire per asserzione è
      ucciso; nel runner non resta una regex sull'uscita di pytest che decida un esito o un
      tipo. Difetto 65, eseguito sul giro 1 di `PBI-388` il 29/09. In coda con `PBI-390`,
      davanti a 388.
      ✅ Fatto il 29/09 da `PBI-390`: il gate rigira pytest con `--junitxml` in
      `pytest-<n>.xml`, tolto prima di ogni misura; `caso_junit()` lega il node id al caso,
      e esito, errore di raccolta e tipo del fallimento vengono dal rapporto. Un rapporto
      che manca è `GuastoDelGate`, fuori dal ramo del timeout. `RE_ESITO_PYTEST` e
      `RE_RIEPILOGO_PYTEST` non ci sono più.

- [ ] **Il server dell'esito non viene dall'albero che il Builder cambia.** Un giro che sposta
      o modifica `tools/asdlc/esito.py` chiude con l'esito chiamato dal Critic, perché la
      config MCP lancia il comando del venv installato e non il file dell'albero. Difetto
      66, eseguito sul giro 1 di `PBI-383` il 30/09. In coda con `PBI-384`.

- [x] **Una fermata del Builder è la riga che la apre.** Una risposta che cita `STOP:` a
      metà riga e chiude con `FATTO:` va ai gate e non chiude `fermato`; una che termina con
      la riga di fermata si ferma, e la nota porta la domanda intera. Si misura con la
      frase vera del giro di PBI-363 del 23/09. Difetto 32. ✅ Fatto il 23/09 da `PBI-364`:
      `fermata_del_builder()` guarda le righe dopo lo `strip()`, la domanda è il resto della
      riga di fermata, fra più righe vale l'ultima, e un `FATTO:` sull'ultima riga vince.
      Superato il 24/09 da `PBI-367`: la riga di fermata non esiste più, e l'esito è la
      chiamata a `fermati` o a `fatto` (`ADR-0027`).

- [ ] **Una guardia si giudica sulla funzione che presidia, non sulle righe del diff.** Su
      un branch che toglie codice da una funzione, una guardia sul resto di quella funzione
      morde; il commit di una guardia può nominare una funzione fuori dal diff, e il gate la
      muta; la prosa di una docstring non genera mutanti. Difetti 53 e 33 (punto 1),
      misurati sul primo giro di `PBI-373` il 26/09 e sul primo di `PBI-364` il 23/09. In
      coda con `PBI-378`.

- [x] **Il rootdir di pytest è la cartella da cui il gate lo lancia.** Con un
      `pyproject.toml` fra la cartella di lancio e i test, il caso JUnit di ogni chiave è
      quello che `caso_junit()` ricava, come senza. Difetto 67, eseguito sul giro 1 di
      `PBI-384` il 30/09. In coda con `PBI-391`, davanti a 384.
      ✅ Fatto il 30/09 da `PBI-391`: `comandi_dei_test()` lancia pytest con
      `--rootdir=<cartella>`, la stessa da cui lo lancia, e `esiti_del_comando()` e
      `morde()` rigirano quell'argv. Un pytest vero con `tools/pyproject.toml` o
      `tools/pytest.ini` scrive `tools.tests.test_x`.

- [ ] **Il tick in pausa non lancia.** Con `~/asdlc-tick.pausa` presente il tick esce senza
      lanciare, e `asdlc-chiudi-giro` spegne e riaccende creando e togliendo il file, senza
      toccare il crontab. Difetto 69, eseguito il 30/09 sul lancio di 384 delle 18:00. In coda
      con `PBI-385`.

## Protocollo di rifinitura
La riga `BLOCCANTI: n` nel formato del Critic è **suggerita, non decisa**: se scrivendo il
codice si vede che il conteggio è fragile — un Critic che sbaglia a contare è peggio di uno
che non conta — si implementa solo il tetto e lo stato nuovo, e la convergenza automatica
diventa un PBI suo.

## Quello che resta, e non è questo PBI
La riga `BLOCCANTI: n` del protocollo di rifinitura **non è stata implementata**, come quel
protocollo permetteva. Il tetto e i due stati bastano a togliere i giri buttati; far contare
al Critic i propri rilievi bloccanti è un'altra cosa — un Critic che sbaglia a contare è
peggio di uno che non conta — e diventa un PBI suo il giorno in cui serve.
