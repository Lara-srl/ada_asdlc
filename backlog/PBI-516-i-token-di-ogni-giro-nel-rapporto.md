# PBI-516: i token di ogni giro nel rapporto

**Stato:** da accodare (dopo `PBI-513`, di cui legge il fork della sessione)

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
- `README.md` e `specs/` — dove descrivono il rapporto JSON, nello stesso commit.
- `backlog/PBI-516-i-token-di-ogni-giro-nel-rapporto.md` — questo file, per la spunta.

**Fuori scope**

- **Il costo in euro o dollari.** I prezzi cambiano per modello e per data: il rapporto porta
  i token e il modello, e chi vuole il prezzo lo calcola fuori.
- **`runs/tempi.csv`:** ha colonne fisse e un lettore (`PBI-368`); aggiungere colonne è un altro PBI.
- **Un tetto di spesa** che fermi il giro: sarebbe un hard-block (`ADR-0008`). Qui si misura.
- **Il confronto fra modelli:** serve prima qualche giro misurato.

## ✅ Deciso, per non fermare il giro

1. **Il dato si legge dalla traccia copiata**, mai dallo stdout del modello (`ADR-0027`).
   Una traccia che non c'è o non si legge lascia `token` a `None` con la nota che c'è già
   (`traccia_nota`): il giro non si ferma (`ADR-0008`).
2. **Un messaggio si conta una volta**, per `message.id` (l'ultima riga con quell'id vince, perché
   la stessa risposta può comparire più volte). Se un messaggio non ha id, vale il numero di riga.
3. **Un messaggio si conta una volta per giro**, non per invocazione. Il rilancio del Builder
   con `-c --fork-session` (`PBI-513`) scrive una sessione che **contiene la cronologia di quella
   di prima**: senza questa regola il giro conterebbe due volte i messaggi già spesi.
4. **La forma:** per invocazione `token = {"input", "output", "cache_creazione",
   "cache_lettura"}` e `modello`; per il giro, la somma per ruolo e il totale. I messaggi di
   modelli diversi non si sommano fra loro: il totale è per `(ruolo, modello)`.
5. **Lo scope dei commit è `runner`.**

## Dipendenze

- Bloccato da: `PBI-513` (la regola 3 presuppone il fork; senza il 513 il rilancio non parte).
- `PBI-511` è in `main` e in `v0.4.0`.

## Contesto

- `tools/asdlc/runner.py`: `copia_la_traccia()`, `blocchi_della_traccia()`,
  `contenuto_della_traccia()`; `PBI-511`, decisioni 1 e 2.
- La guida IBM «Architecting secure enterprise AI agents with MCP» (ott 2025), pag. 9 e 12:
  conto dei token e dei costi per task, e confronto *champion–challenger* come base per
  promuovere un cambio. Qui è solo la parte del conto.

## Verifica

Su `main` il rapporto non porta `token`, quindi ogni criterio è un **rosso atteso**.

- [ ] **Una traccia si somma.** Con una traccia di esempio di tre messaggi dell'assistente,
      la funzione restituisce la somma dei quattro contatori e il modello (pytest).
- [ ] **Un messaggio ripetuto conta una volta.** Due righe con lo stesso `message.id` danno
      l'uso dell'ultima, non la somma (pytest).
- [ ] **La cronologia del fork non si conta due volte.** Due tracce dello stesso giro, la
      seconda con i messaggi della prima più due nuovi: il totale del giro conta ogni id una
      volta (pytest).
- [ ] **Il registro porta `token` e `modello`.** Con `esegui()` finto che scrive la traccia,
      `invoca_agente()` mette `token` e `modello` nel registro dell'invocazione (pytest).
- [ ] **Il rapporto del giro porta la somma per ruolo.** Il JSON finale ha `token` per
      `(ruolo, modello)` e il totale (pytest, giro con Builder, Critic e Solver finti).
- [ ] **Una traccia assente o illeggibile non ferma il giro.** `token` è `None`, la nota dice
      perché, e il giro chiude com'era (pytest, due casi).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde; i campi esistenti del
rapporto non cambiano nome né posizione.
