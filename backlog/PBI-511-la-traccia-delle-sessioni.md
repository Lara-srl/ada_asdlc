# PBI-511: la traccia delle sessioni degli agenti, e il controllo R4

## Direttiva

Nato dal giro 1 di `PBI-508` (16/10): R4 chiede che il Solver abbia **letto `asdlc.toml` prima
di `segnala_limite_runner`**, e oggi nessun dato lo dice. Il runner lancia i tre agenti come
`claude -p` in modalità testo e salva solo il messaggio finale e le chiamate ai propri
strumenti (`<esito>.chiamate.jsonl`); le letture (`Read`, `Grep`, `Glob`) e il ragionamento no.
Claude Code scrive la sessione per conto suo, in
`~/.claude/projects/<cartella-del-giro>/<id-sessione>.jsonl`, con ogni `tool_use` e i
risultati; ma il rapporto del giro non dice quale sessione sia, e il file sta fuori dal
repository.

Il PBI lega la sessione al giro e usa quel fatto per R4. Un fatto letto dal registro delle
chiamate, non dal testo di un modello (R13, `ADR-0027`).

**Scope**

- `tools/asdlc/runner.py` — l'identificativo della sessione di ogni invocazione di agente,
  scritto nel rapporto del giro; la lettura della traccia; la riga R4 della guardia.
- `tools/tests/test_asdlc_traccia.py` — nuovo: i test dei criteri.
- `backlog/PBI-511-la-traccia-delle-sessioni.md` — questo file, per la spunta.

**Fuori scope**

- Il giudizio sul ragionamento (i blocchi `thinking`): la traccia dice *cosa* l'agente ha
  fatto, non se ha ragionato bene. Resta del Critic.
- Cambiare il modo in cui il runner legge l'esito degli agenti (`ADR-0027`).

## ❓ Da decidere (Francesco) prima di accodarlo

Le proposte sono quelle che scriverei; non sono decise.

1. **Come si lega la sessione al giro.** Proposta: il runner passa a `claude -p`
   `--session-id <uuid>` generato da lui, e salva l'uuid nel rapporto. Alternativa:
   `--output-format stream-json`, che cambia ciò che il runner legge da `stdout` per tutti i
   ruoli, e quindi tocca di più.
2. **Dove sta la traccia.** Proposta: il runner **copia** il `.jsonl` della sessione in
   `runs/` a fine invocazione, accanto agli altri file del giro (`runs/*` è ignorato da git),
   perché la cartella di Claude Code è fuori dal repository e può essere ripulita.
3. **Per chi.** Proposta: l'identificativo e la copia valgono per tutti e tre i ruoli
   (Builder, Critic, Solver); il controllo R4 usa solo la traccia del Solver.

## Dipendenze

- Bloccato da: `PBI-507` (il Solver), `PBI-508` (la guardia, di cui accende la riga R4).
- Sblocca: nessuno.

## Contesto

- `specs/solver-e-rilascio/spec.md`, R4 e R13.
- `backlog/PBI-508-la-guardia-di-processo.md`, «Il giro 1, e cosa si riprende».
- `decisions/ADR-0027-gli-esiti-passano-per-chiamate-a-strumento.md`.

## Verifica

Su `main` la traccia non esiste: ogni criterio è un **rosso atteso**.

- [ ] **Il rapporto del giro riporta l'id di sessione di ogni invocazione.** Con un finto
      `claude` che registra gli argomenti, ogni invocazione riceve `--session-id` e lo stesso
      uuid sta nel rapporto, per Builder, Critic e Solver.
- [ ] **La traccia della sessione si copia in `runs/`.** Con un finto file di sessione sotto
      una cartella di prova, a fine invocazione la copia c'è; se manca, il rapporto lo dice
      e il giro non si ferma (`ADR-0008`).
- [ ] **R4 è `ok` se `asdlc.toml` è letto prima di `segnala_limite_runner`.** Una traccia con
      `Read` su `asdlc.toml` e poi la chiamata → `ok`.
- [ ] **R4 è `violata` se la lettura manca o viene dopo.** Due tracce, due `violata`.
- [ ] **R4 è `non eseguita` se la traccia non c'è o non si legge.** Il giro chiude come prima.
- [ ] **Nessun controllo legge testo libero di un modello.** Si sostituisce il testo delle
      risposte nella traccia con rumore, lasciando le chiamate a strumento: la riga R4 non
      cambia.

**Non regressione:** i ruoli ricevono gli stessi strumenti di prima;
`python3 -m pytest -q tools/tests` resta verde.
