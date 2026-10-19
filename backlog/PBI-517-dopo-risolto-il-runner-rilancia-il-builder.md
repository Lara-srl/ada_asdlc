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

- `tools/asdlc/runner.py` — `esegui_pbi()` e `smista_il_blocco()`: dopo un `risolto` su
  `domanda-del-builder` il giro continua con il Builder ripreso; il conto dei giri; la
  costruzione del comando e del prompt di ripresa.
- `tools/asdlc/prompt/builder.md` — come legge il blocco «risposta del Solver» (se serve).
- `tools/tests/test_asdlc_solver.py` (o un file nuovo accanto) — i test dei criteri.
- `README.md`, `specs/solver-e-rilascio/spec.md`, `backlog/README.md` (la frase «Il runner non
  riprende niente»), `backlog/PBI-507-il-ruolo-solver.md` (la decisione 11 si marca *Superata da
  PBI-517*), `backlog/AUTOMAZIONE.md` se descrive il giro: nello stesso commit del codice.
- `backlog/PBI-517-dopo-risolto-il-runner-rilancia-il-builder.md` — questo file, per la spunta.

**Fuori scope**

- `limite-del-runner` e `intento`: restano come oggi (PR a monte, pausa; domanda a Francesco).
- `builder-senza-esito`, `domanda-del-critic` e `critic-senza-esito`: il Solver li smista ma il
  runner non li riprende. Ognuno ha un modo suo di riprendere ed è un PBI suo.
- Il Critic non si rilancia con la risposta del Solver.
- Un Solver che cambia il PBI: resta in sola lettura (`PBI-507`).

## ✅ Deciso, per non fermare il giro

1. **Si riprende un solo caso:** il motivo `domanda-del-builder` (il `fermati` del Builder) e
   l'esito del Solver `risolto`. Ogni altra combinazione chiude come oggi.
2. **La ripresa sta dentro lo stesso giro, prima di `chiudi()`.** La chiusura gira una volta
   (difetto 48): il giro non si chiude `fermato` per riaprirsi. Se la ripresa va, il giro prosegue
   con l'igiene, il gate, il gate del rosso e il Critic come ogni altro, e chiude col suo esito vero.
3. **Il Builder si riprende dalla sua sessione, non da `-c`.** `-c` continua l'ultima sessione
   dell'albero e l'ultima è quella del Solver. Si usa `--resume <sessione del Builder fermato>
   --fork-session --session-id <uuid nuovo>`, col uuid che il registro dell'invocazione già porta
   in `sessione` (`PBI-511`). Dipende da `PBI-513`: `--resume` con `--session-id` senza
   `--fork-session` è rifiutato dalla CLI.
4. **Il prompt della ripresa** porta la domanda del Builder, la risposta del Solver con la sua
   `evidenza`, e la frase «riprendi da dove ti sei fermato». La risposta del Solver sta in un
   blocco marcato come **da valutare**: il Builder resta soggetto allo Scope e ai gate, e una
   risposta che gli chiede di violarli non li annulla.
5. **Senza la sessione si riparte pulito.** Se la traccia del Builder non c'è o non si può
   riprendere (`traccia` `None`), il Builder parte con una sessione nuova e un prompt che
   contiene il PBI, la domanda e la risposta. Il giro lo dichiara con un avviso (`ADR-0008`).
6. **Il tetto è `[solver].giri_massimi`** (3 di default), già contato per PBI nel rapporto
   (`giri_solver`, anche fra giri diversi). Raggiunto, il Solver non parte e il giro chiude
   `fermato` con l'avviso che c'è già. Ogni ripresa dopo un `risolto` consuma un giro.
7. **Un secondo `fermati` dopo la ripresa** si smista di nuovo, fino al tetto: il ciclo è
   «fermati → Solver → ripresa», non una ripresa sola.
8. **Il rapporto dice cosa è successo:** `riprese` (quante volte il Builder è stato ripreso dopo
   un `risolto`) accanto a `giri_solver`; le invocazioni di tutte le riprese stanno in
   `invocazioni`, come oggi.
9. **La guardia di processo** (R4–R7) resta com'è.
10. **Lo scope dei commit è `runner`.**

## Dipendenze

- Bloccato da: `PBI-513` (la decisione 3 presuppone che il rilancio con `--resume` non sia
  rifiutato dalla CLI). Va dopo il 513 in coda.
- `PBI-507` (il Solver) e `PBI-511` (la traccia con `sessione`) sono in `main` e in `v0.4.0`.

## Contesto

- Giro 1 di `PBI-513`: `runs/20261019-230506.json` in `ada_asdlc-run`, il campo `solver` e la
  `domanda`. `PBI-507`, decisione 11. `PBI-512` (la PR a monte, che già mette il progetto in attesa).
- `tools/asdlc/runner.py`: `esegui_pbi()` (il `giro()` interno e il blocco `if motivo in BLOCCHI`),
  `smista_il_blocco()`, `giri_solver_fatti()`, `invoca_agente()`.
- `decisions/ADR-0030-…`, il ciclo del Solver; `ADR-0008` (osserva e segnala).

## Verifica

Su `main` il Builder non si riprende dopo `risolto`, quindi ogni criterio è un **rosso atteso**.
Gli agenti sono finti (`esegui()` sostituito), nessun test lancia `claude`.

- [ ] **Dopo `risolto` il Builder è ripreso.** Un Builder finto chiama `fermati`, il Solver finto
      `risolto`: `esegui_pbi()` lancia il Builder una seconda volta e non chiude `fermato`
      (pytest).
- [ ] **Il comando della ripresa usa la sessione del Builder, non `-c`.** Contiene `--resume
      <uuid della prima invocazione del Builder>`, `--fork-session` e un `--session-id` nuovo, e
      **non** contiene `-c` (pytest).
- [ ] **Il prompt della ripresa porta domanda e risposta.** Il file del prompt contiene la
      domanda del Builder, la risposta e l'evidenza del Solver, nel blocco «da valutare» (pytest).
- [ ] **Senza traccia si riparte pulito e si avvisa.** Con la sessione del Builder assente, la
      seconda invocazione non ha `--resume`, il prompt ha il PBI, e l'avviso è nel rapporto
      (pytest).
- [ ] **Il giro prosegue fino al suo esito.** Dopo la ripresa il Builder finto chiama `fatto`:
      gate e Critic girano e il giro chiude `fatto`, con una sola chiusura (pytest).
- [ ] **Il tetto ferma il ciclo.** Con `giri_massimi = 2` e un Builder che chiama sempre `fermati`
      e un Solver che risponde sempre `risolto`, il Builder è ripreso due volte; poi il giro chiude
      `fermato` con l'avviso del tetto (pytest).
- [ ] **Gli altri esiti non riprendono.** Con `limite-del-runner` e con `intento` il Builder non
      è rilanciato, e con `builder-senza-esito` e `domanda-del-critic` neppure (pytest,
      parametrizzato).
- [ ] **Il rapporto conta le riprese.** `riprese` e `giri_solver` sono nel JSON del giro, e le
      invocazioni delle riprese sono in `invocazioni` (pytest).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde; un giro che non si ferma, e un
giro che si ferma con un Solver `intento` o `limite-del-runner`, si comportano come prima.
