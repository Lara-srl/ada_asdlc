# PBI-517: dopo `risolto` il runner rilancia il Builder

**Stato:** in coda (Francesco, 19/10: «la questione fondamentale dell'automazione», subito dopo il 513)

## Direttiva

Il Solver risponde ma il runner non segue la risposta. `PBI-507` (decisione 11) lo ha lasciato
apposta: «Il Solver è invocato e registrato, non ancora seguito; con `risolto` **non rilancia il
Builder**… Riprendere dopo `risolto` è di un PBI successivo». Questo è quel PBI. La spec lo
disegna già (`specs/solver-e-rilascio/spec.md`, il ciclo: `risolto → il Builder riprende con la
risposta`) e il codice no.

Il caso che lo mostra è il giro 1 di `PBI-513` (19/10, run `20261019-230506`): il Builder ha fatto
tutto il lavoro e si è fermato con una domanda (`fermati`). Il Solver (`fable`) ha risposto
`risolto`, con la strada giusta e il precedente di `PBI-511`, in due minuti. Poi il giro si è
chiuso `fermato` e la risposta è rimasta nel rapporto: per riprendere c'è voluto un tag, una
ripresa scritta a mano nel PBI, una PR, un merge e un giro nuovo. Il Solver non serve a niente
finché la sua risposta non arriva al Builder.

**Scope**

- `tools/asdlc/runner.py` — `esegui_pbi()` (il `giro()` interno e il blocco `if motivo in BLOCCHI`),
  `smista_il_blocco()`, `invoca_agente()` solo se serve, il comando e il prompt della ripresa.
- `tools/asdlc/prompt/ripresa.md` — **nuovo**: il testo del prompt di ripresa, uno per ruolo come
  gli altri file di `tools/asdlc/prompt/`. Si carica con `prompt_del_pacchetto("ripresa")`; la risposta
  del Solver entra come **valore** di `.format()`, mai nel template (le graffe del testo non si
  interpretano). Se `pyproject.toml` elenca i prompt uno per uno, il file si aggiunge lì.
- `tools/asdlc/prompt/builder.md` — solo se serve dire come si legge il blocco «da valutare».
- `tools/tests/test_asdlc_solver.py` (o un file nuovo accanto) — i test dei criteri.
- `README.md`, `specs/solver-e-rilascio/spec.md`, `backlog/README.md`, `template/backlog/README.md` e
  `template/backlog/TEMPLATE.md` (la frase «Il runner non riprende niente» sta in tutti e tre),
  `backlog/PBI-507-il-ruolo-solver.md` (la decisione 11 si marca *Superata da PBI-517*) e
  `backlog/AUTOMAZIONE.md` (la riga «Il Solver non rilancia il Builder»): nello stesso commit del codice.
- `backlog/PBI-517-dopo-risolto-il-runner-rilancia-il-builder.md` — questo file, per la spunta.

**Fuori scope**

- `limite-del-runner` e `intento`: restano come oggi (PR a monte, pausa; domanda a Francesco).
- `builder-senza-esito`, `domanda-del-critic` e `critic-senza-esito`: il Solver li smista ma il
  runner non li riprende. Ognuno ha un modo suo di riprendere ed è un PBI suo.
- `rosso-mai-visto`: non è un blocco del Solver e non si riprende (il ciclo mancato è ex ante).
- Il Critic non si rilancia con la risposta del Solver.
- Un Solver che cambia il PBI: resta in sola lettura (`PBI-507`).
- Mostrare la risposta del Solver nella PR all'Acceptance Gate: è un PBI suo.

## ✅ Deciso, per non fermare il giro

1. **Si riprende un solo caso:** il motivo `domanda-del-builder` (il `fermati` del Builder) e
   l'esito del Solver `risolto`. Ogni altra combinazione chiude come oggi.
2. **La ripresa sta dentro lo stesso giro, prima di `chiudi()`, e `smista_il_blocco()` si chiama da
   un posto solo.** Oggi lo chiama il blocco `if motivo in BLOCCHI` fuori da `giro()`. Dopo questo PBI lo
   chiama **solo il ciclo dentro `giro()`**, quando il Builder fa `fermati`; quel blocco esterno non
   smista più (altrimenti l'ultimo blocco si smisterebbe due volte e il Solver girerebbe due volte).
   Per ogni altro motivo di `BLOCCHI` (`builder-senza-esito`, `domanda-del-critic`,
   `critic-senza-esito`) il Solver si chiama come oggi, una volta, fuori da `giro()`. La chiusura gira
   una volta (difetto 48).
3. **`guardia_del_solver()` gira ogni volta che il Solver ha scritto**, cioè se `e.solver` non è vuoto, e
   non solo quando il motivo finale è in `BLOCCHI`. Dopo una ripresa il motivo finale può essere
   `fatto`, `gate-rossi` o `revisioni-esaurite`, e R4–R7 valgono lo stesso. Le regole R4–R7 non cambiano.
4. **Un guasto del Solver resta un avviso.** Un'eccezione di `smista_il_blocco()` dentro il ciclo non
   diventa `eccezione-nel-giro`: si registra come oggi («il Solver è fallito», `ADR-0008`) e il giro
   chiude col motivo del blocco, `fermato`. Il test esistente
   `test_un_guasto_del_solver_non_salta_la_chiusura_del_giro` mantiene la sua asserzione.
5. **`intento` e `limite-del-runner` fermano il ciclo.** Gli effetti di
   `metti_in_attesa_del_pbi_a_monte()` (il commit sul ramo e la pausa) restano dove sono, dentro
   `smista_il_blocco()`, e il giro chiude `fermato` senza riprese.
6. **Il Builder si riprende dalla sua sessione, non da `-c`.** `-c` continua l'ultima sessione
   dell'albero e l'ultima è quella del Solver. Si usa `--resume <sessione> --fork-session
   --session-id <uuid nuovo>`, dove `<sessione>` è il `sessione` **dell'ultima invocazione `builder` in
   `e.invocazioni`** (quella che ha chiamato `fermati`): dopo un gate rosso, a una revisione successiva
   e al secondo `fermati` non è la prima. Il comando di ripresa **sostituisce** quello costruito da
   `primo_del_giro` per quell'unica invocazione e non incrementa `gate_falliti` né `e.tentativi`. Dopo
   la ripresa i rilanci per gate rosso o igiene tornano a `-c --fork-session` (`PBI-513`).
7. **Si riprende solo se la traccia c'è.** Il criterio è `registro["traccia"]` non `None`: `sessione`
   c'è sempre, anche se il file della sessione non si è copiato, e un `--resume` su una sessione
   assente fallirebbe. Senza traccia il Builder parte con una sessione nuova e un prompt che contiene
   il PBI, la domanda e la risposta. Il giro lo dichiara con un avviso (`ADR-0008`). Alla revisione ≥1 la
   ripartenza pulita non ha i rilievi del Critic: il prompt dice di rileggerli da `git log` e dal rapporto
   del Critic in `runs/`.
8. **Il prompt della ripresa** (`ripresa.md`) porta la domanda del Builder, la risposta del Solver con la
   sua `evidenza`, e la frase «riprendi da dove ti sei fermato, nella fase in cui sei» (la fase sta su
   disco e non cambia). La risposta sta in un blocco marcato come **da valutare**: il Builder resta
   soggetto allo Scope e ai gate, e una risposta che gli chiede di violarli non li annulla.
9. **Il tetto è `[solver].giri_massimi`, e il contatore cresce in memoria dentro il giro.**
   `giri_solver_fatti()` legge i rapporti su disco e **non vede il giro in corso** (il rapporto
   `in-corso` non ha `esiti`): `smista_il_blocco()` lo legge una volta, all'inizio del giro, e da lì
   `e.giri_solver` cresce a ogni invocazione del Solver, senza rileggere il disco. Il contatore conta le
   **invocazioni del Solver**, non le riprese: un Solver `senza esito` o `intento` consuma un giro senza
   riprendere. Raggiunto il tetto il Solver non parte e il giro chiude `fermato` con l'avviso che c'è
   già. Il contatore non si azzera fra giri: un PBI che ha già `giri_solver` ≥ tetto in un rapporto
   precedente non riprende più, ed è il comportamento di oggi.
10. **Un secondo `fermati` dopo la ripresa** si smista di nuovo, fino al tetto: il ciclo è
    «fermati → Solver → ripresa».
11. **Il rapporto dice cosa è successo:** `riprese` (quante volte il Builder è stato ripreso dopo un
    `risolto`), campo nuovo di `Esito`, accanto a `giri_solver`; le invocazioni di ogni ripresa stanno in
    `invocazioni`, come oggi.
12. **Lo scope dei commit è `runner`.**

## Dipendenze

- Bloccato da: `PBI-513` (la ripresa porta `--fork-session`, ma i rilanci per gate rosso dopo la ripresa
  usano `-c --fork-session`, e la guardia sui comandi con `--session-id` è del 513). Va dopo il 513 in coda.
- Va dopo `PBI-518`: la suite di questo PBI gira un agente finto e rischia gli stessi fermi.
- `PBI-507` (il Solver) e `PBI-511` (la traccia con `sessione`) sono in `main` e in `v0.4.0`.

## Contesto

- Giro 1 di `PBI-513`: `runs/20261019-230506.json` in `ada_asdlc-run`, il campo `solver` e la
  `domanda`. `PBI-507`, decisione 11. `PBI-512` (la PR a monte, che già mette il progetto in attesa).
- `tools/asdlc/runner.py`: `esegui_pbi()` (il `giro()` interno e il blocco `if motivo in BLOCCHI`),
  `smista_il_blocco()`, `giri_solver_fatti()`, `invoca_agente()`.
- `decisions/ADR-0030-…`, il ciclo del Solver; `ADR-0008` (osserva e segnala).

## Verifica

Su `main` il Builder non si riprende dopo `risolto`, quindi i criteri 1–6 e 8–9 sono un **rosso
atteso**. Il criterio 7 no (vedi sotto). Gli agenti sono finti (`esegui()` sostituito), nessun test
lancia `claude`. Per le riprese il test **crea il file della sessione** in `cartella_delle_sessioni()`
(con la cartella monkeypatchata) o sostituisce `copia_la_traccia`: senza, `traccia` è sempre `None` e
si passerebbe sempre dal percorso «riparti pulito». Serve un agente finto **con stato** (prima
`fermati`, poi `fatto`): `agente_finto` dà un esito fisso per ruolo.

- [ ] **Dopo `risolto` il Builder è ripreso.** Il Builder finto chiama `fermati`, il Solver finto
      `risolto`: `esegui_pbi()` lancia il Builder una seconda volta e non chiude `fermato` (pytest).
- [ ] **Il comando della ripresa usa la sessione dell'ultima invocazione del Builder, non `-c`.**
      Contiene `--resume <sessione dell'ultima invocazione builder>`, `--fork-session` e un
      `--session-id` nuovo, e **non** `-c`. Provato con un gate rosso prima del `fermati`, in modo che
      l'ultima invocazione non sia la prima (pytest).
- [ ] **Il prompt della ripresa porta domanda e risposta**, anche con graffe nel testo della risposta,
      nel blocco «da valutare» (pytest).
- [ ] **Senza traccia si riparte pulito e si avvisa.** Con `traccia` `None` la seconda invocazione non ha
      `--resume`, il prompt ha il PBI, e l'avviso è nel rapporto (pytest).
- [ ] **Il giro prosegue fino al suo esito e la guardia gira.** Dopo la ripresa il Builder finto
      chiama `fatto`: gate e Critic girano, il giro chiude `fatto` con una sola chiusura, e `e.guardia` è
      valorizzata (pytest).
- [ ] **Il tetto ferma il ciclo dentro lo stesso giro.** Con `giri_massimi = 2`, un Builder che chiama
      sempre `fermati` e un Solver che risponde sempre `risolto`, il Solver è chiamato due volte, il
      Builder due volte ripreso, poi il giro chiude `fermato` con l'avviso del tetto (pytest, e il
      test termina).
- [ ] **Gli altri esiti non riprendono.** Con `limite-del-runner`, `intento`, `builder-senza-esito` e
      `domanda-del-critic` il Builder non è rilanciato. **Nato verde su `main`, per costruzione**: la
      guardia si committa da sola, senza `--chiedi-impl`, con `Guardia-su: tools/asdlc/runner.py::esegui_pbi`
      (la regola di `tools/asdlc/prompt/builder.md`), e deve mordere (pytest, parametrizzato).
- [ ] **Un guasto del Solver resta un avviso.** Con `smista_il_blocco()` che alza, il giro chiude
      `fermato` con l'avviso «il Solver è fallito», non `rosso` né `eccezione-nel-giro` (pytest; è
      l'asserzione del test esistente, che resta).
- [ ] **Il rapporto conta le riprese.** `riprese` e `giri_solver` sono nel JSON del giro, e le
      invocazioni delle riprese sono in `invocazioni` (pytest).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde; un giro che non si ferma, e un
giro che si ferma con un Solver `intento` o `limite-del-runner`, si comportano come prima.
