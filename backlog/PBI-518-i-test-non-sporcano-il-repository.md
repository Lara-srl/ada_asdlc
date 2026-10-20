# PBI-518: i test non sporcano il repository

**Stato:** in coda (Francesco, 19/10: subito dopo il 513, in forma ridotta); corretto dopo la lettura
avversariale del 20/10

## Direttiva

La causa `test-senza-isolamento` (`backlog/README.md`: «un test scrive o legge fuori dalla sua
cartella temporanea, nello stato vero del repository») ha già quattro occorrenze nel registro dei
difetti (38, 45, 72, 83) e il 03/10 Francesco ha deciso un PBI per toglierla. Il PBI non c'è stato,
e la stessa causa ha fermato tre giri il 19/10: due volte `PBI-511` (un JSON con nome uuid) e il giro 1
di `PBI-513` (`--session-id.json`).

Il meccanismo è sempre lo stesso. Un test del runner gira un agente finto con la cartella di lavoro
nel progetto di prova `tools/tests/dati/progetto/`, dentro il repository; il finto scrive lì un file
d'esito che nessuno cancella. Il gate (`pytest -q tools/tests`) lascia l'albero sporco, e il controllo
dell'albero pulito all'ingresso o a fine giro ferma il giro. Finora si è curato il sintomo con una
riga in `tools/tests/dati/progetto/.gitignore` per ogni forma nuova del nome (uuid, poi `--*.json`):
una toppa che si ripresenta alla forma successiva.

Questo PBI è la **forma ridotta** del PBI del 03/10: toglie la causa dei fermi visti, e mette una
guardia che mostra il prossimo test che sporca prima che fermi un giro. Non rifà la suite.

**Scope**

- `tools/tests/test_asdlc_runner.py` — `AGENTE_CHE_DORME` e i test che lo usano
  (`TestIlTimeoutDiUnAgenteChiudeSenzaEsito`, righe ~8453-8560): l'esito si scrive dove la
  config MCP dell'invocazione dice, non in `$2`, e in una cartella temporanea.
- `tools/tests/conftest.py` (o un modulo accanto) — la guardia di fine suite.
- `tools/tests/` — un test della guardia.
- `tools/tests/test_asdlc_coda.py` —
  `test_guardia_il_dry_run_lanciato_dal_checkout_decide_come_col_repo_esplicito` (~1296): il
  lucchetto del tick (`runs/.tick.lock`) va in una cartella temporanea e non in
  `tools/tests/dati/progetto/runs/`. In un clone fresco la suite lo crea lì (`coda.main` con
  `--repo PROGETTO`), e la guardia lo vedrebbe: la CI, che parte da un checkout pulito, uscirebbe
  rossa, mentre nell'albero del giro, dove `runs/` c'è già, la guardia tace. Deroga allo Scope
  dichiarata (`ADR-0015`). Se la guardia nomina un altro test che prende il lucchetto in
  `PROGETTO`, si fa lo stesso.
- `backlog/README.md` — la riga della causa `test-senza-isolamento`, con il PBI che la copre.
- `backlog/PBI-518-i-test-non-sporcano-il-repository.md` — questo file, per la spunta.

**Fuori scope**

- **Una copia del progetto di prova per ogni test** e **la rete spenta per default**, le altre due
  regole del 03/10: toccherebbero centinaia di test. Un PBI a parte, se la guardia ne mostra ancora.
- **Togliere le righe di `.gitignore`** di `tools/tests/dati/progetto/`: restano finché la guardia
  non ha girato qualche giro senza segnalare niente.
- Altri agenti finti che scrivono fuori dalla cartella temporanea e che nessun giro ha ancora
  segnalato: la guardia li troverà.

## ✅ Deciso, per non fermare il giro

1. **Il finto agente scrive il suo esito accanto alla config MCP che riceve**, cercando l'argomento
   `--mcp-config` fra i suoi, e mai per posizione (`$2`, `$1`): la posizione cambia quando il runner
   aggiunge un flag (è successo con `--session-id` e `--fork-session`). Quel percorso sta in una
   cartella temporanea del test.
2. **Una guardia di fine suite:** a suite finita, in `tools/tests/dati/` non c'è nessun file o
   cartella che prima non c'era, ignorato o no. Se c'è, la suite esce rossa nominando i file. Vale
   per l'intera suite, quindi anche per il gate e per la CI.
3. **La guardia confronta un elenco prima e dopo**, e non `git status`: deve vedere anche i file
   ignorati, che sono proprio quelli che le toppe di `.gitignore` nascondevano.
4. **La guardia non cancella niente.** Se trova un file lo nomina e basta: il file lo cancella o lo
   ignora chi corregge il test (`ADR-0008`: si segnala, non si ripara in silenzio).
5. **Lo scope dei commit è `runner`.**
6. **Tutto lo Scope è sotto `tools/tests/`, cioè test per `e_file_di_test`.** Non c'è produzione da
   aprire: niente `--chiedi-impl`. Ogni GREEN si scrive in `TEST_ONLY`, in un commit suo
   (`test(runner): …`) dopo il commit `test(runner): … (RED)`. In `IMPL` quei file sarebbero
   bloccati (`guardia_di_fase`, `tools/asdlc/runner.py`): chiamare `--chiedi-impl` qui ferma il giro.
7. **La funzione della guardia nasce scheletro** (torna `[]`) in un commit suo, prima del RED del
   criterio 3, e il test la chiama come attributo del modulo: un modulo che non c'è dà un errore di
   import, che non è un rosso.

## Dipendenze

- Bloccato da: `PBI-513` (il finto agente cambia le sue posizioni con i flag del 513). Va dopo il 513.
- Va prima di `PBI-517`, che gira la suite e rischia gli stessi fermi.

## Contesto

- Giri del 19/10 fermati dalla causa: `PBI-511` (giri 1 e 3), `PBI-513` (giro 1). Il registro:
  `backlog/PBI-102-…`, difetti 38, 45, 72, 83; `backlog/README.md`, causa `test-senza-isolamento`.
- Le decisioni del 19/10 su `PBI-511` (giro 3) e `PBI-513` (giro 2): il file si ignora e la cura vera
  è un PBI a parte. Questo è quel PBI.
- `tools/tests/dati/progetto/.gitignore`: le due toppe.

## Verifica

Su `main` il finto scrive in `tools/tests/dati/progetto/` e nessuna guardia lo dice, quindi ogni
criterio è un **rosso atteso**. I criteri 1 e 2 di prima li rendeva verdi la stessa modifica (cercare
`--mcp-config` per nome): il secondo sarebbe nato verde e il gate del rosso avrebbe fermato il giro.
Ora sono un criterio solo.

- [x] **Il finto trova la config MCP per nome, e il test del tetto non lascia file in
      `tools/tests/dati/`.** Un test parametrico con id espliciti: `critic` (`--session-id U
      --mcp-config P`), `builder` (`--settings S --session-id U --mcp-config P`) e `rilancio` (`-c
      --fork-session --session-id U --mcp-config P`). Ogni caso è rosso su `main` per asserzione: il
      file nasce accanto a `U` o a `S`, non a `P`. Il finto si lancia senza `sleep` (pytest).
- ~~**Il finto trova la config MCP per nome.**~~ **Fuso nel criterio 1 (20/10, lettura
      avversariale).** Diventava verde con la stessa modifica del criterio 1, e un caso
      (`--mcp-config P` in testa, dove `$2` è già `P`) era verde anche su `main`.
- [x] **La guardia segnala un file nato in `tools/tests/dati/`.** Con una funzione che confronta
      due elenchi, un file nuovo (anche ignorato da git) è nominato nell'errore; elenchi uguali
      non danno errore (pytest).
- [x] **La suite esce rossa se un test sporca.** In un sottoprocesso con un test che scrive un
      file in `tools/tests/dati/`, `pytest` esce con un codice diverso da 0 e il file è nominato
      (pytest, sottoprocesso). Il test sporco sta in `tmp_path` e il sottoprocesso carica la guardia
      con `-p`; il file che scrive in `tools/tests/dati/` il test esterno lo cancella in `finally`,
      perché la guardia non cancella niente (decisione 4) e il file resterebbe nell'albero vero.

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde su un albero pulito e ne esce
pulito: `git status --porcelain --ignored tools/tests/dati/` è uguale prima e dopo (`git status
--porcelain` da solo non mostra i file ignorati, e nell'albero del giro ce ne sono già). Il tempo
della suite non raddoppia.

## La lettura avversariale del 20/10

Un lettore in sola lettura ha cercato i fermi meccanici prima del giro; ogni rilievo è verificato nel
codice o in un clone fresco. Cambiati: la decisione 6 (niente `--chiedi-impl`, perché in `IMPL` i test
sono chiusi e il GREEN qui è tutto sotto `tools/tests/`); la 7 (lo scheletro); i criteri 1 e 2 fusi,
perché il secondo sarebbe nato verde; il criterio 4 col test sporco in `tmp_path`; la non regressione
con `--ignored`; lo Scope col lucchetto del tick, che in un clone fresco nasce in
`tools/tests/dati/progetto/runs/` (verificato il 20/10). Non cambiata la dipendenza dal 513: il 518
resta dopo.
