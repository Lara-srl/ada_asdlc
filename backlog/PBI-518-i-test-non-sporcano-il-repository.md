# PBI-518: i test non sporcano il repository

**Stato:** in coda (Francesco, 19/10: subito dopo il 513, in forma ridotta)

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
criterio è un **rosso atteso**.

- [ ] **Il test del tetto scaduto non lascia nessun file in `tools/tests/dati/`.** Si lancia
      `TestIlTimeoutDiUnAgenteChiudeSenzaEsito` in un sottoprocesso e si confronta l'elenco di
      `tools/tests/dati/` prima e dopo: è uguale (pytest, sottoprocesso).
- [ ] **Il finto trova la config MCP per nome.** Il finto scrive il suo esito accanto al percorso
      che segue `--mcp-config`, anche se prima di quell'argomento ce ne sono di più o di meno
      (pytest, due posizioni diverse).
- [ ] **La guardia segnala un file nato in `tools/tests/dati/`.** Con una funzione che confronta
      due elenchi, un file nuovo (anche ignorato da git) è nominato nell'errore; elenchi uguali
      non danno errore (pytest).
- [ ] **La suite esce rossa se un test sporca.** In un sottoprocesso con un test che scrive un
      file in `tools/tests/dati/`, `pytest` esce con un codice diverso da 0 e il file è nominato
      (pytest, sottoprocesso).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde su un albero pulito e ne esce
pulito (`git status --porcelain` vuoto, anche per i file ignorati in `tools/tests/dati/`); il tempo
della suite non raddoppia.
