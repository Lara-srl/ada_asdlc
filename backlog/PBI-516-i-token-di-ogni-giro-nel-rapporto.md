# PBI-516: i token di ogni giro nel rapporto

**Stato:** in coda dopo `PBI-523`; riletto il 21/10 su `main` `681c5d0` (la `v0.6.0`, che contiene
513, 517, 519 e 521): vedi in fondo.

## Direttiva

Oggi il rapporto di un giro (`runs/<run>.json`) dice **quanto** è durato ogni ruolo
(`durata_s`) ma non **quanto ha speso**. Con il Solver su `fable` (`PBI-512` e la PR #55) e il
Builder che rilancia dopo un gate rosso, il costo di un giro è la domanda che non si può più
rimandare, e la risposta non c'è: nessun file lo dice. Senza il conto non si può confrontare
un modello con un altro (`opus` e `fable` come Solver) su un lavoro uguale.

Il dato c'è già. `PBI-511` copia accanto ai file del giro la traccia della sessione
(`<esito>.sessione.jsonl`), e ogni messaggio dell'assistente porta `message.usage`
(`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`) e
`message.model`. Verificato il 19/10 su una sessione di prova. Manca la somma.

**Scope**

- `tools/asdlc/runner.py` — una funzione nuova accanto a `copia_la_traccia()` che somma l'uso
  dei messaggi di una traccia, e il campo `token` nel registro di ogni invocazione e nel
  totale del giro.
- `tools/tests/test_asdlc_traccia.py` — i test dei criteri, con una traccia di esempio in
  `tools/tests/dati/`.
- `specs/solver-e-rilascio/spec.md`, §«La traccia delle sessioni (`PBI-511`)», e `README.md` se
  descrive il rapporto JSON — nello stesso commit del codice.
- `backlog/PBI-516-i-token-di-ogni-giro-nel-rapporto.md` — questo file, per la spunta.

**Fuori scope**

- **Il costo in euro o dollari.** I prezzi cambiano per modello e per data: il rapporto porta
  i token e il modello, e chi vuole il prezzo lo calcola fuori.
- **`runs/tempi.csv`:** ha colonne fisse e un lettore (`PBI-368`); aggiungere colonne è un altro PBI.
- **Un tetto di spesa** che fermi il giro: sarebbe un hard-block (`ADR-0008`). Qui si misura.
- **Il confronto fra modelli:** serve prima qualche giro misurato.
- **I token del Lettore** (`PBI-521`). La sua invocazione entra in `e.invocazioni` solo quando
  chiude `senza esito` (`esegui_pbi()`, l'uscita `lettore-senza-esito`); con `letto`, o con dei
  rilievi, la voce non arriva al rapporto del giro. Portarla sempre è un altro PBI.
- **Il conteggio di `contenuto_della_traccia()`**, che conta anche le righe `api-request-blob` e
  dà più risposte e chiamate di quelle vere (21/10: 16 risposte contro 10 sulla traccia del Critic
  `20261021-092929`). È un difetto a parte; questo PBI non lo tocca.

## ✅ Deciso, per non fermare il giro

1. **Il dato si legge dalla traccia copiata**, mai dallo stdout del modello (`ADR-0027`).
   Una traccia che non c'è o non si legge lascia `token` a `None` con la nota che c'è già
   (`traccia_nota`): il giro non si ferma (`ADR-0008`).
2. **Un messaggio si conta una volta**, per `message.id`. Si contano solo le righe con `type ==
   "assistant"` e `message.usage`: le righe `api-request-blob`, copie del messaggio senza id né
   uso, si saltano. Lo stesso id su più righe porta lo stesso `usage` (misurato il 21/10 su 167
   casi in 8 tracce vere): conta l'ultima. Con questa regola la somma combacia esatta con la riga
   `cost-state.modelUsage` di Claude Code, su 6 tracce confrontate.
3. **Un messaggio si conta una volta per esito**, non per invocazione. Il rilancio del Builder
   con `-c` o `--resume` e `--fork-session` (`PBI-513`, `PBI-517`) scrive una sessione che
   **contiene la cronologia di quella di prima**: senza questa regola l'esito conterebbe due
   volte i messaggi già spesi. La forma della traccia di un fork **non è stata osservata** (21/10:
   in oltre 100 sessioni nessun `message.id` è condiviso fra due tracce): la regola conta per id, e
   se il fork riscrivesse gli id il doppio conto si vedrebbe confrontando con `cost-state`.
4. **La forma.**
   - Per invocazione, nel registro: `token = {"input", "output", "cache_creazione",
     "cache_lettura"}` e `modello`, dalla sua traccia; `None` tutti e due senza traccia leggibile.
   - Per esito, un campo nuovo `token` **in fondo** a `Esito`: una lista di `{"ruolo", "modello",
     "input", "output", "cache_creazione", "cache_lettura"}`, una voce per coppia `(ruolo,
     modello)`, con i duplicati per `message.id` tolti su tutte le invocazioni dell'esito
     (decisione 3). Non c'è un totale fra modelli diversi, perché non si sommano.
   - Al livello del rapporto (`run`, `stato`, `esiti`) non si aggiunge niente.
5. **Lo scope dei commit è `runner`.**

## Dipendenze

- `PBI-513` (il fork della sessione, regola 3): soddisfatta, è in `main` dalla `v0.5.0`.
- Dopo `PBI-523` in coda: tutti e due toccano `tools/asdlc/runner.py` e il 516 parte dalla base
  che contiene il 523.
- `PBI-511` è in `main` e in `v0.4.0`.

## Contesto

- `tools/asdlc/runner.py`: `copia_la_traccia()`, `blocchi_della_traccia()`,
  `contenuto_della_traccia()`, `traccia_nota`, `invoca_agente()` (dove si costruisce il registro),
  `Esito`, `scrivi_rapporto()`; `PBI-511`, decisioni 1 e 2.
- `tools/tests/test_asdlc_traccia.py`: il finto sostituisce `cartella_delle_sessioni` con una
  `lambda` senza argomenti; il GREEN non deve chiamarla con `cwd` (lo fa solo il Lettore).
- Una traccia vera ha anche righe `api-request-blob` con `message.role == "assistant"`: la
  traccia di esempio in `tools/tests/dati/` ne porta una, perché la decisione 2 si veda.
- La guida IBM «Architecting secure enterprise AI agents with MCP» (ott 2025), pag. 9 e 12:
  conto dei token e dei costi per task, e confronto *champion–challenger* come base per
  promuovere un cambio. Qui è solo la parte del conto.

## Verifica

Su `main` il rapporto non porta `token`, quindi ogni criterio è un **rosso atteso**.

- [x] **Una traccia si somma.** Con una traccia di esempio di tre messaggi dell'assistente e
      una riga `api-request-blob`, la funzione restituisce la somma dei quattro contatori dei tre
      messaggi e il modello (pytest).
- [x] **Un messaggio ripetuto conta una volta.** Due righe con lo stesso `message.id` danno
      l'uso dell'ultima, non la somma (pytest).
- [x] **La cronologia del fork non si conta due volte.** Due tracce dello stesso esito, la
      seconda con i messaggi della prima più due nuovi: il `token` dell'esito conta ogni id una
      volta (pytest).
- [x] **Una traccia assente o illeggibile non ferma il giro.** Test parametrico con id `assente`
      e `illeggibile`: `registro.get("token", "manca") is None` e il giro chiude com'era. Su `main`
      la chiave `token` non c'è, quindi il test cade per asserzione. La nota non si asserisce:
      `traccia_nota` c'è già (pytest).
- [x] **Il registro porta `token` e `modello`.** Con `esegui()` finto che scrive la traccia,
      `invoca_agente()` mette `token` e `modello` nel registro dell'invocazione (pytest).
- [x] **Il rapporto del giro porta la somma per ruolo.** Nel JSON finale l'esito ha `token`, una
      voce per `(ruolo, modello)` con i quattro contatori (pytest, giro con Builder, Critic e
      Solver finti).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde; i campi esistenti del
rapporto non cambiano nome né posizione.

## La lettura avversariale del 21/10

Un lettore in sola lettura ha provato il PBI sul codice di `main` (`681c5d0`, `v0.6.0`) e su 8 tracce
vere di `ada_asdlc-run/runs/`. Il PBI era del 19/10, scritto prima della `v0.5.0`.

**Avrebbe fermato il giro:**

- il criterio «traccia assente o illeggibile» era l'ultimo, ma la decisione 1 chiede già `token =
  None`: il GREEN del criterio del registro l'avrebbe implementato insieme, e il criterio sarebbe
  nato verde (`rosso-mai-visto`). La parte «la nota dice perché» era già vera su `main`. Ora viene
  prima del registro, e asserisce solo la chiave.

**Erano da correggere:**

- la decisione 4 chiedeva «la somma per ruolo e il totale» e insieme «il totale è per `(ruolo,
  modello)`», con una tupla che non può essere una chiave JSON: ora la forma è scritta per intero;
- il Lettore non era nominato: va nel Fuori scope, perché la sua voce arriva al rapporto solo con
  `senza esito`;
- le tracce vere hanno righe `api-request-blob` senza id né uso, che con «senza id vale il numero di
  riga» sarebbero diventate messaggi in più (decisione 2, criterio 1);
- la regola del fork si appoggiava a una forma mai osservata, e citava solo `-c` (decisione 3);
- lo Stato e le Dipendenze dicevano il 513 ancora da fare.

**Verificato senza rilievi:**

- su `main` niente somma i token: i criteri nascono rossi, e il criterio 2 non nasce verde dopo un
  GREEN minimo del criterio 1;
- `message.usage`, `message.id` e `message.model` stanno dove il PBI dice;
- nessun test esistente confronta il registro o l'esito per intero: aggiungere chiavi e un campo in
  fondo a `Esito` non ne rompe nessuno;
- la guardia di fase lascia scrivere la traccia di esempio sotto `tools/tests/`, e la guardia del
  518 non la vede;
- il criterio 5 è fattibile: Builder, Critic `sospeso` e Solver passano da `smista`.
