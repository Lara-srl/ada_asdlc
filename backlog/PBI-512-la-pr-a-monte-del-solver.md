# PBI-512: la PR a monte del Solver (R5 e R6)

## Direttiva

Seguito di `PBI-509`, da cui esce (Francesco, 16/10: il 509 si chiude con il rilascio, il pin e
la pausa). Quando il Solver segnala un limite del runner, il sistema apre davvero il PBI a
monte: un ramo su un fork di `asdlc` e una PR da lì, mai una scrittura su `main` (R5), e mai
due PBI per la stessa causa (R6).

Le decisioni di Francesco (16/10), che qui valgono:

1. **Il testo del PBI a monte lo scrive il Solver.** `segnala_limite_runner` prende un campo
   `pbi` con il testo completo (titolo, Direttiva con Scope, Verifica); il codice non genera
   testo con un modello e lo salva così com'è in un file.
2. **Il numero è il successivo libero** in `backlog/` del clone di `asdlc`, calcolato dal
   codice (`PBI-512` è l'ultimo oggi, il prossimo sarebbe il 513): numero incrementale e basta.
3. **Il clone di `asdlc`** è una chiave nuova, `[rilascio].clone`, il percorso di una copia di
   `asdlc` sul disco (qui `/home/laisdev/ada_asdlc`). Il codice non la deduce da altro. Senza
   chiave la PR non si apre e il Solver riceve l'errore.
4. **Dopo la PR il progetto si mette in attesa:** il codice scrive nel PBI fermo la riga
   `attende: Lara-srl/ada_asdlc#PBI-NNN` (formato di `PBI-509`) e crea la pausa
   `~/asdlc-tick.pausa`. A tornare in marcia ci pensa il pin di `PBI-509`.

**Scope**

- `tools/asdlc/esito.py` — il campo `pbi` di `segnala_limite_runner` e la chiamata che apre il
  ramo e la PR.
- `tools/asdlc/runner.py` — la lettura del clone, il numero successivo, il controllo dei
  duplicati e la riga `attende:` con la pausa.
- `tools/asdlc/config.py` — la chiave `[rilascio].clone`.
- `tools/asdlc/prompt/solver.md` — il campo `pbi` nelle istruzioni del Solver.
- `tools/tests/test_asdlc_pr_a_monte.py` — nuovo: i test dei criteri.
- `README.md`, `backlog/AUTOMAZIONE.md`, `specs/solver-e-rilascio/spec.md` — la sezione, nello
  stesso commit del codice.
- `backlog/PBI-512-la-pr-a-monte-del-solver.md` — questo file, per la spunta.

**Fuori scope**

- Il merge: mai automatico (R10-R11). Un `gh pr merge` nel codice è una violazione.
- Il rilascio e il pin (`PBI-509`) e il battito (`PBI-510`).

## Dipendenze

- Bloccato da: `PBI-509` (la riga `attende:` e il pin, che la usano), `PBI-507`, `PBI-508`.

## Contesto

- `specs/solver-e-rilascio/spec.md`, R5 e R6.
- La domanda del Builder al giro 2 di `PBI-509` (`runs/tempi.csv`, 16/10) e le risposte sopra.

## Verifica

`gh` e `git` sono sostituiti da finti; nessun test usa la rete.

- [ ] **`segnala_limite_runner` apre il ramo sul fork e la PR, mai su `main`.** Il test verifica
      il ramo, la base della PR e che la PR porti il PBI col numero successivo e la riga di
      `backlog/CODA.md` (R5).
- [ ] **Senza `[rilascio].clone` la PR non si apre** e lo strumento rende un errore al Solver.
- [ ] **Una causa con PBI già a monte non ne apre un altro.** Cita il PBI o la PR esistente (R6).
- [ ] **Dopo la PR il progetto è in attesa:** il PBI fermo ha la riga `attende:` e la pausa
      esiste; con una causa già a monte vale lo stesso.
- [ ] **Nessun `gh pr merge` nel pacchetto** (il test AST di `PBI-509` resta verde).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde; senza Solver nulla cambia.
