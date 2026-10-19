# PBI-511: la traccia completa delle sessioni degli agenti, e il controllo R4

## Direttiva

Nato dal giro 1 di `PBI-508` (16/10): R4 chiede che il Solver abbia **letto `asdlc.toml` prima
di `segnala_limite_runner`**, e oggi nessun dato lo dice. Il runner lancia i tre agenti come
`claude -p` in modalità testo e salva solo il messaggio finale e le chiamate ai propri
strumenti (`<esito>.chiamate.jsonl`); le letture (`Read`, `Grep`, `Glob`) e il ragionamento no.
Claude Code scrive la sessione per conto suo, in
`~/.claude/projects/<cartella-del-giro>/<id-sessione>.jsonl`, con ogni `tool_use` e i
risultati; ma il rapporto del giro non dice quale sessione sia, e il file sta fuori dal
repository.

Francesco ha deciso (16/10) che **la traccia dev'essere completa e puntuale, per ogni
agente**: il prompt ricevuto, ogni chiamata a strumento con argomenti e risultato, ogni
risposta e i ragionamenti (blocchi `thinking`), nell'ordine in cui sono avvenuti, legata al
giro. Il PBI lega la sessione al giro, la conserva intera e usa quel fatto per R4: un fatto
letto dal registro delle chiamate, non dal testo di un modello (R13, `ADR-0027`).

Da verificare nel primo criterio: quanto del ragionamento Claude Code scrive davvero nella
sessione (i blocchi `thinking` possono essere assenti o riassunti). Il PBI conserva ciò che
c'è e il rapporto dice cosa manca; non promette ciò che la sessione non contiene.

**Scope**

- `tools/asdlc/runner.py` — l'identificativo della sessione di ogni invocazione di agente,
  scritto nel rapporto del giro; la lettura della traccia; la riga R4 della guardia.
- `tools/tests/test_asdlc_traccia.py` — nuovo: i test dei criteri.
- `backlog/PBI-511-la-traccia-delle-sessioni.md` — questo file, per la spunta.
- `specs/solver-e-rilascio/spec.md` — **allargamento del 19/10** (giro 2): R4, R13 e la
  traccia delle sessioni, nello stesso commit del codice che li cambia (`AGENTS.md`, SEMPRE).
- `tools/tests/test_asdlc_guardia_solver.py` — **allargamento del 19/10**: il test di `PBI-508`
  che nomina il rinvio «(PBI-511)» cambia con il testo di R4.

**Fuori scope**

- Il giudizio sul ragionamento: la traccia dice *cosa* l'agente ha fatto e pensato, non se
  ha ragionato bene. Resta del Critic.
- Cambiare il modo in cui il runner legge l'esito degli agenti (`ADR-0027`).

## ✅ Deciso (Francesco, 16/10)

1. **La sessione si lega al giro con `--session-id`.** Il runner genera un uuid per ogni
   invocazione, lo passa a `claude -p --session-id <uuid>` e lo salva nel rapporto del giro.
   Vale per Builder, Critic e Solver. Niente `--output-format stream-json`: i log del giro
   esistono già, e il legame con la sessione di Claude Code basta ad avere tutto il resto.
2. **La traccia sta in `runs/`.** A fine invocazione il runner **copia** il `.jsonl` della
   sessione in `runs/`, accanto agli altri file del giro (`runs/*` è ignorato da git), perché
   la cartella di Claude Code è fuori dal repository e può essere ripulita.
3. **Per chi: tutti e tre i ruoli, traccia completa.** Identificativo e copia valgono per
   Builder, Critic e Solver; il controllo R4 usa la traccia del Solver.

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
- [ ] **La traccia della sessione si copia intera in `runs/`.** Con un finto file di sessione
      sotto una cartella di prova, a fine invocazione la copia è identica, con prompt,
      chiamate, risultati, risposte e blocchi `thinking`; se il file manca, il rapporto lo dice
      e il giro non si ferma (`ADR-0008`).
- [ ] **Il rapporto dice cosa contiene la traccia.** Per ogni invocazione: numero di chiamate
      a strumento, di risposte e di blocchi `thinking`, così che una traccia senza ragionamenti
      si veda subito.
- [ ] **R4 è `ok` se `asdlc.toml` è letto prima di `segnala_limite_runner`.** Una traccia con
      `Read` su `asdlc.toml` e poi la chiamata → `ok`.
- [ ] **R4 è `violata` se la lettura manca o viene dopo.** Due tracce, due `violata`.
- [ ] **R4 è `non eseguita` se la traccia non c'è o non si legge.** Il giro chiude come prima.
- [ ] **Nessun controllo legge testo libero di un modello.** Si sostituisce il testo delle
      risposte nella traccia con rumore, lasciando le chiamate a strumento: la riga R4 non
      cambia.

**Non regressione:** i ruoli ricevono gli stessi strumenti di prima;
`python3 -m pytest -q tools/tests` resta verde.

## Il giro 2, e cosa si riprende

Il giro 1 (19/10, run `20261019-155507`) ha fatto i criteri 1-5 e 7 e si è fermato a
`rosso-mai-visto` su `df769b7` («R4 è non eseguita se la traccia manca, è illeggibile o non
segnala alcun limite»). Nasce verde per la ragione di `PBI-509` e `PBI-510`: il codice c'era già
(`controlla_r4` aveva la sua rete e `controllo_r4` finiva con «non eseguita»), e un test scritto
dopo il codice non può essere rosso (`ADR-0021`). Dei tre casi del test uno non potrà mai
essere rosso: **«la traccia non c'è»** è già presidiato dal test di `PBI-508`
(`test_la_riga_r4_e_non_eseguita_con_il_rinvio_a_pbi_511`) e non si riscrive.

**Si riprende il tag `ripresa/pbi-511-giro2`** (fe51914), non un `giro-fermato/…`: è la storia del
giro 1 fino a `f559361` (i criteri 1-5, 4 coppie RED→GREEN più la base delle tracce di R4),
**senza `df769b7` e senza i quattro commit dopo**, più un commit `fe51914` che toglie a mano due
cose da `runner.py`: `controlla_r4` non intercetta più l'eccezione (una traccia illeggibile
arriva alla guardia) e `controllo_r4` senza `segnala_limite_runner` nella traccia rende `violata`
invece di `non eseguita`. Resta il caso senza traccia (`if not voci`). Gate verde sul tag (1044
test). Ramo da quel tag, niente cherry-pick e niente rebase. Il file di questo PBI si prende da
`main` (`git checkout origin/main -- backlog/PBI-511-la-traccia-delle-sessioni.md`), un commit;
se `git` vede un conflitto su quel file vale la versione di `main`, poi si spunta ciò che il
giro ha fatto.

**Da fare, in quest'ordine:**

1. **Traccia illeggibile, RED.** Un test: una traccia che non è JSON → la riga è «R4: non
   eseguita» e le righe R5-R7 ci sono lo stesso (il corpo del secondo test di `df769b7`). Contro
   il tag fallisce: l'eccezione esce dalla guardia. Un commit `test(runner): …(RED)` da solo.
2. **GREEN.** Si rimette la rete in `controlla_r4`. Un commit `feat(runner): …`.
3. **Nessuna segnalazione, RED.** Un test: una traccia con la lettura di `asdlc.toml` ma senza
   `segnala_limite_runner` → «R4: non eseguita». Contro il tag è `violata`. Un commit
   `test(runner): …(RED)` da solo.
4. **GREEN.** `controllo_r4` torna a rendere «non eseguita» in fondo. Un commit `feat(runner): …`.
5. **Il criterio 7 (il testo libero non conta),** che il giro 1 aveva coperto in `a91120a`, e il
   **testo del caso senza traccia**, «nessuna traccia utile del Solver» al posto del rinvio
   provvisorio «(PBI-511)» (`c1d76ed`, `e88e1ac`, `1e32bf8` del giro 1): si rifanno come
   coppie RED→GREEN, ciascuna col suo commit. Il test di `PBI-508` che nomina il rinvio cambia nel
   commit del testo nuovo.
6. **La spec** (R4, R13, la traccia delle sessioni) e le spunte dei sette criteri, nello stesso
   commit del codice che ne cambia il comportamento.

**Un file che non è del giro.** I test del gate lasciano nell'albero un
`tools/tests/dati/progetto/<uuid>.json` non tracciato (il giro 1 lo ha segnalato come «il giro
lascia: file tools +1»; un altro l'ha committato per errore, tolto in `1e32bf8`). **Non si
committa** e non si tocca la cartella: se un test in questo giro lo scrive, il test si sposta su
`tmp_path`. Fuori da questo, un test che scrive in `tools/tests/dati/` è un difetto a parte.

**Non si fa:** non si riscrive `df769b7`, non si rifà il caso «la traccia non c'è», non si tocca
`fe51914` (i GREEN lo annullano con commit nuovi) e non si riscrive la storia del tag.
