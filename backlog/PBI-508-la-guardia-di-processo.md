# PBI-508: la guardia di processo del Solver

## Direttiva

Terzo PBI di `ADR-0030`, decisione 4: niente quarto agente. Che il Solver abbia rispettato le
regole R1-R12 lo dice **il codice**, leggendo il rapporto del giro, git e `gh`; mai un modello
(R13, `ADR-0027`). Il giudizio sulla diagnosi resta al Critic, che rilegge anche l'output del
Solver.

La guardia **segnala e non blocca** (`ADR-0008`): ogni controllo fallito è una riga nel
rapporto e nell'avviso, e il flusso va avanti. Fanno eccezione le chiusure `senza esito` che
R1 già prevede.

**Scope**

- `tools/asdlc/runner.py` — una funzione `guardia_del_solver()` che, a chiusura del giro,
  applica i controlli sotto e scrive le violazioni nel rapporto.
- `tools/asdlc/prompt/critic.md` — la riga che dice al Critic di rileggere l'output del
  Solver, e di non rifare i controlli che la guardia ha già fatto.
- `tools/tests/test_asdlc_guardia_solver.py` — nuovo: i test dei criteri.
- `backlog/PBI-508-la-guardia-di-processo.md` — questo file, per la spunta.

**Fuori scope**

- La PR a monte e il rilascio (`PBI-509`): qui si controlla la PR se c'è, non la si apre.
- Qualunque giudizio sulla qualità della diagnosi.
- Il controllo R4, cioè la traccia delle letture del Solver: è di `PBI-511`.

## ✅ Deciso

1. **I controlli sono quelli di R4-R7, fatti sui fatti:**
   - ~~R4: il rapporto del Solver riporta la lettura di `asdlc.toml` del progetto prima di
     `segnala_limite_runner` (il campo c'è e viene prima, in ordine di chiamata).~~ Spostata il
     16/10 in `PBI-511`: il campo non esiste e il runner non registra le letture (giro 1).
     Qui la riga R4 della sezione è sempre `non eseguita`, con il rinvio a `PBI-511`.
   - R5: la PR a monte parte da un ramo di un fork, non da `main`, e non tocca `AGENTS.md` né
     file esistenti di `decisions/` (`git diff --name-only` della PR contro la sua base).
   - R6: nessun altro PBI in `backlog/` né PR aperta in `asdlc` (`gh pr list`) con la stessa
     `causa`.
   - R7: lo Scope del PBI a monte non elenca file del progetto.
2. **Un controllo che non può girare** (per esempio `gh` non risponde) è un avviso «controllo
   non eseguito», non un successo né un blocco.
3. **L'esito della guardia sta nel rapporto**, in una sezione `## Guardia di processo`, una
   riga per regola, con `ok`, `violata` o `non eseguita`.
4. **Lo scope dei commit è `runner` e `prompt`.**

## Dipendenze

- Bloccato da: `PBI-507` (il rapporto del Solver e i suoi campi).
- Sblocca: `PBI-511` (porta la traccia e accende la riga R4).
- Usa i fatti di `PBI-509` quando la PR a monte esiste; senza, i controlli R5-R7 sono
  `non eseguita`.

## Contesto

- `specs/solver-e-rilascio/spec.md`, R4-R7 e R13.
- `decisions/ADR-0008-osserva-e-segnala.md`, `ADR-0015` (lo scope largo lo segnala il Critic).

## Verifica

Su `main` la guardia non esiste: ogni criterio è un **rosso atteso**.

- ~~**R4 violata se `asdlc.toml` non è stato letto prima.**~~ Spostato in `PBI-511` (16/10).
- [ ] **R4 è `non eseguita` finché `PBI-511` non porta la traccia.** La sezione `## Guardia di
      processo` ha la riga R4 con `non eseguita` e il rinvio a `PBI-511`, sempre, e il giro non
      si ferma.
- [ ] **R5 violata se la PR parte da `main` o tocca `AGENTS.md`.** Due violazioni e un caso
      valido (repository temporaneo con base e ramo).
- [ ] **R6 violata se esiste un PBI con la stessa causa.** Un file in `backlog/` con
      `**Causa:** runner-x` e una seconda segnalazione di `runner-x` → `violata`, con il
      riferimento al PBI esistente.
- [ ] **R7 violata se lo Scope elenca un file del progetto.** Un PBI il cui Scope nomina
      `asdlc.toml` del progetto → `violata`.
- [ ] **Un controllo che non può girare è `non eseguita` e il giro non si ferma.** Con `gh`
      finto che esce 1, la riga è `non eseguita` e il giro chiude come prima.
- [ ] **Nessun controllo legge testo libero di un modello.** Il test sostituisce l'uscita
      grezza del Solver con rumore e verifica che la sezione non cambi.

**Non regressione:** un giro senza Solver non ha la sezione; `python3 -m pytest -q tools/tests`
resta verde.

## Il giro 1, e cosa si riprende (16/10/2026)

Il giro 1 (`20261016-154506`) si è fermato dopo 41 secondi con `domanda-del-builder`, senza
commit: il criterio R4 chiedeva un campo che non c'è (`segnala_limite_runner` ha solo `causa`,
`comando`, `output`, `commit`), e il log delle chiamate non registra `Read`, `Grep`, `Glob`.
Francesco ha scelto (16/10) di far registrare le letture dal runner, **in un PBI a parte**:
`PBI-511`. Il tag è `giro-fermato/pbi-508-giro1-20261016` (`f4f2b6f`, nessun commit del PBI).

- Il ramo `pbi/pbi-508` è tolto da origin; il giro 2 riparte da `main`.
- Gli altri criteri (R5, R6, R7, `non eseguita`, nessun testo libero) non cambiano.
