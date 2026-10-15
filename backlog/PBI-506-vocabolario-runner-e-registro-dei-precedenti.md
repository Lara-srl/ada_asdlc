# PBI-506: il vocabolario delle cause `runner-*` e il registro dei precedenti

## Direttiva

Primo dei cinque PBI di `ADR-0030` (`specs/solver-e-rilascio/spec.md`). Il Solver ha bisogno
di due elenchi che oggi non esistono in forma leggibile da un agente: **le cause `runner-*`**
(R3: una causa fuori elenco non apre mai un PBI a monte) e **il registro dei precedenti**
(R12: le decisioni di Francesco che fanno precedente, lette prima di chiedere).

Il PBI è solo documentazione, più i test che ne fissano la forma. Non tocca il runner.

**Scope**

- `backlog/README.md` — la tabella delle cause: una sezione «Le cause `runner-*`» con la
  regola (uno slug che comincia per `runner-` è una causa del runner e di nessun altro;
  l'elenco è chiuso e si allarga con un ADR), e le righe. Si parte da `runner-non-legge-junit`
  (`PBI-505`, difetto 3 di `ada_planning`).
- `backlog/PRECEDENTI.md` — nuovo: il registro, solo in aggiunta, con l'intestazione e il
  formato della riga.
- `tools/tests/test_asdlc_precedenti.py` — nuovo: i test dei criteri.
- `backlog/PBI-506-vocabolario-runner-e-registro-dei-precedenti.md` — questo file, per la spunta.

**Fuori scope**

- Il Solver che legge i due file (`PBI-507`).
- Il codice che aggiunge righe al registro: le scrive Francesco, o il Solver in una PR.

## ✅ Deciso (Francesco, 16/10, `ADR-0030`)

1. **L'elenco `runner-*` sta in `backlog/README.md` di `asdlc`.** I progetti lo citano con un
   URL pinnato al tag e tengono solo le proprie cause.
2. **Il registro sta in `backlog/PRECEDENTI.md`**, append-only: una riga non si cancella né si
   riscrive; una decisione superata si barra e si cita la nuova (come le regole abrogate,
   `ADR-0011`).
3. **Formato della riga del registro:** `- AAAA-MM-GG · <causa o ruolo> · <sentenza in una
   frase> · <riferimento: PR, ADR o PBI>`. Una riga per decisione.
4. **Il primo contenuto del registro** sono le decisioni di Francesco già prese che il Solver
   userebbe: il 16/10 le cinque di `ADR-0030` (non come precedenti di merito, ma come
   esempio del formato), e il 15/10 «un limite del runner si corregge con un PBI in `asdlc`,
   non a mano» (`PBI-505`).
5. **Lo scope dei commit è `kb`** per i file di documentazione e `runner` per il test.

## Dipendenze

- Bloccato da: nessuno.
- Sblocca: `PBI-507` (il Solver legge i due file), `PBI-509` (usa il vocabolario per
  `rilascia:`).

## Contesto

- `specs/solver-e-rilascio/spec.md`, R3 e R12.
- `backlog/README.md`, «I difetti e le loro cause»: il vocabolario di ogni progetto è chiuso.

## Verifica

Su `main` i due elenchi non esistono: ogni criterio è un **rosso atteso**.

- [ ] **La tabella `runner-*` esiste e porta almeno `runner-non-legge-junit`.** Il test legge
      `backlog/README.md`, trova la sezione e verifica che ogni riga abbia uno slug che
      comincia per `runner-` e che `runner-non-legge-junit` ci sia.
- [ ] **Nessuno slug della tabella `runner-*` è uguale a una causa di progetto.** Il test
      confronta con gli slug della tabella generale: nessun doppione.
- [ ] **Il registro esiste e ogni riga ha il formato.** Il test legge `backlog/PRECEDENTI.md`
      e verifica che ogni riga che comincia per `- ` abbia data ISO, tre separatori `·` e un
      riferimento non vuoto.
- [ ] **Il registro è solo in aggiunta.** Il test confronta le righe con la versione su
      `origin/main`: nessuna riga non barrata è sparita (repository temporaneo, due commit).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde.
