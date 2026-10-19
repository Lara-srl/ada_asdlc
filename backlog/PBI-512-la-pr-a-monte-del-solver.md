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

- [x] **`segnala_limite_runner` apre il ramo sul fork e la PR, mai su `main`.** Il test verifica
      il ramo, la base della PR e che la PR porti il PBI col numero successivo e la riga di
      `backlog/CODA.md` (R5).
- [x] **Senza `[rilascio].clone` la PR non si apre** e lo strumento rende un errore al Solver.
- [x] **Una causa con PBI già a monte non ne apre un altro.** Cita il PBI o la PR esistente (R6).
- [x] **Dopo la PR il progetto è in attesa:** il PBI fermo ha la riga `attende:` e la pausa
      esiste; con una causa già a monte vale lo stesso.
- [x] **Nessun `gh pr merge` nel pacchetto** (il test AST di `PBI-509` resta verde).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde; senza Solver nulla cambia.

## Il giro 2, e cosa si riprende

Il giro 1 (19/10, run `20261019-095506`) ha fatto i primi tre passi con le loro coppie
RED→GREEN: `[rilascio].clone` (`e24c13e`, `ca8063a`), il campo `pbi` e l'errore senza clone in
`segnala_limite_runner` (`f56a996`, `d1ef6c4`), e `apri_pr_a_monte` con `ASDLC_CLONE` dal runner
(`5e8d045`, `21c8f8e`). Poi ha chiamato `fermati` su una domanda vera, non su un difetto del
codice: il test `test_il_limite_apre_un_ramo_sul_fork_e_una_pr_verso_main_col_pbi_successivo`
(`tools/tests/test_asdlc_pr_a_monte.py`) asserisce `mondo.rami(mondo.fork) == ["main",
"pbi/pbi-513"]`, ma `MondoAMonte` crea il fork come repository nudo vuoto e non vi spinge mai
`main`: l'elenco reale è `["pbi/pbi-513"]`. In IMPL il Builder non poteva correggere un test.

**Decisione di Francesco (19/10): la fixture si corregge, l'asserzione resta.** Un fork vero ha
`main`: la fixture ci spinge `main`, e il test continua a chiedere `["main", "pbi/pbi-513"]`.
Non si abbassa l'asserzione a `["pbi/pbi-513"]`.

**Si riprende il tag `giro-fermato/pbi-512-giro1-20261019`** (21c8f8e): ramo da quel tag, niente
cherry-pick e niente rebase. Il file di questo PBI si prende da `main` (`git checkout
origin/main -- backlog/PBI-512-la-pr-a-monte-del-solver.md`), un commit; se `git` vede un
conflitto su quel file vale la versione di `main`.

**Da fare, in quest'ordine:**

1. **La fixture, un commit di soli test.** In `MondoAMonte.__init__` si spinge `main` sul fork
   (dopo `git remote add fork`, prima che il test lo usi), e basta: nessun'altra riga del test
   cambia. Il commit è `test(runner): il fork della fixture ha main come un fork vero`, da solo,
   prima di ogni altro. Non è un nuovo ciclo: il rosso del test lo ha già osservato il gate nel
   giro 1 (`5e8d045`), e questo commit lo riporta alla sua intenzione. Il test deve passare
   contro `21c8f8e` senza toccare produzione. Se il gate del rosso lo ferma comunque, `fermati`
   con la riga della guardia, non una riscrittura della storia.
2. **R6, la causa già a monte.** Un test e poi il codice: con un PBI già a monte per la stessa
   causa, `segnala_limite_runner` non apre un ramo né una PR, e cita il PBI o la PR esistente.
3. **`attende:` e la pausa.** Dopo la PR il PBI fermo ha la riga `attende:` e la pausa esiste;
   con una causa già a monte vale lo stesso. La chiamata passa da `smista_il_blocco`.
4. **`prompt/solver.md`, README, `AUTOMAZIONE.md` e la spec** nello stesso commit del codice che
   ne cambia il comportamento, e le spunte del PBI man mano.

**Non si fa:** non si rifanno i tre passi del giro 1, non si tocca la storia del tag e non si
abbassa l'asserzione del test. Il criterio «nessun `gh pr merge`» si chiude con il test di
`PBI-509` che usa un finto `gh` (`tools/tests/test_asdlc_rilascio.py`), non con un test dell'AST:
quello è stato tolto dal giro 5 di `PBI-509`.
