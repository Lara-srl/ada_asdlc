# ADR-0027: tra codice e modello, gli esiti passano per chiamate a strumento

**Stato:** **Accettata** · **Data:** 2026-09-24 · **Ratifica:** Francesco, con il merge
(`ADR-0012`). **Cambia la costituzione**: aggiunge una riga **MAI** ad `AGENTS.md`, nella
stessa PR.

## Contesto

Il runner ricava gli esiti degli agenti da marcatori di testo: `STOP:` e `FATTO:` per il
Builder, `VERDETTO:` per il Critic. Ogni forma nuova che un modello ha scritto ha richiesto una
regola in più e un test in più:

- la citazione dentro il riepilogo (difetto 32 di `PBI-102`, chiuso da `PBI-364`);
- il grassetto, gli elenchi e la domanda vuota (difetto 34);
- il secondo parser, quello del Critic, rimasto con la regola vecchia (difetto 35);
- il `PASS` citato dentro un `NON PRONTO` (difetto 36).

Il difetto 36 è **verificato su `main` il 24/09**: `revisione_critica()` cerca i verdetti come
sottostringhe in un ordine fisso, e un rapporto che dice «non posso dare VERDETTO: PASS» e
chiude con `VERDETTO: NON PRONTO` viene letto come **pass**. Il runner aprirebbe la PR su un
lavoro respinto. Non è ancora successo.

Le forme non finiscono, perché il testo libero non ha grammatica. La chat di aDa ha già preso
l'altra strada (`backend/app/services/llm.py`, `tool_calls`).

## Decisione

1. Un esito o una decisione che il codice ricava da un modello passa per una **chiamata a
   strumento** oppure per un **output strutturato validato**. Il testo libero del modello
   resta contenuto per le persone (un rapporto, una nota) e non decide mai un ramo del
   codice.
2. **Nessun ripiego sul testo.** Una risposta senza l'esito strutturato è un'anomalia
   visibile: lo stato è `senza esito`, con l'uscita grezza allegata, e non si prosegue.
3. **Le regole di validazione stanno nello strumento**: il campo vuoto, il valore fuori
   elenco, la prima chiamata che è definitiva. Il modello vede l'errore e può rispondere.
   Non ci si affida allo schema: nella prova del 24/09 la CLI ha lasciato arrivare al
   server una chiamata senza il campo `required` (`PBI-366` §Prova di fattibilità).
4. Si può ricavare un esito da testo libero **solo con un ADR** che spieghi perché lo
   strumento non è praticabile e che cosa succede alla forma che nessuno ha previsto.
5. **La regola vale anche per il software che la pipeline costruisce** nei progetti nuovi:
   entra nel template dello scaffolding insieme al runner, e in `AGENTS.md` come riga **MAI**.

**Fuori da questa decisione.** Il testo che producono strumenti deterministici (pytest, `gh`,
la CLI stessa) non è uscita di un modello. Dove esiste un formato strutturato lo si preferisce
(JUnit, `--json`), ma non serve un ADR per leggerne il testo. Per questo la frase del limite
d'uso della CLI (`PBI-363`) si può leggere. Deve però **fallire in modo sicuro**: una frase che
non si riconosce lascia lo stato `senza esito` e non lo trasforma in nient'altro.

## Conseguenze

**Positive**
- La famiglia dei difetti 32, 34, 35 e 36 si chiude per costruzione, senza aggiungere un'altra
  regola di parsing.
- Il limite d'uso (difetto 27) cade in `senza esito` al primo lancio, e non consuma più né i
  giri d'igiene né i tentativi.
- Il server è in sola stdlib e parla MCP, cioè lo standard fra harness diverse: si estrae per
  fotocopia insieme al runner (`ADR-0017`).

**Negative**
- Il protocollo dipende dal supporto MCP della CLI. Un cambio che lo rompe produce
  `senza esito` al primo giro: è rumoroso, ma ferma la coda.
- Con `--strict-mcp-config` il Builder vede solo il server del runner. Un progetto che vuole
  dargli un server MCP suo deve farlo entrare nella config generata (`SCAFFOLDING.md`).
- Nel passaggio, i giri di `PBI-366` e `PBI-367` li giudica ancora il Critic testuale, su un
  diff pieno di `VERDETTO:`. Lo coprono una decisione nei due PBI e la lettura a mano dei
  rapporti del Critic fino al merge di 367.

**Neutre**
- Il contratto «la domanda sta tutta su una riga» cade insieme al parser che lo imponeva.

## Alternative considerate

- **Regole di parsing più strette, o sentinelle rare.** Spostano il problema e non lo tolgono:
  ogni regola nuova è la prossima che un modello aggira citandola.
- **`--json-schema`.** Valida la forma, ma non sa esprimere «la prima chiamata è definitiva» e
  dà un errore di schema invece di un rifiuto che il modello legge e a cui risponde.
- **Il parsing di `stream-json`.** Lega il runner al formato degli eventi della CLI e serve
  comunque uno strumento da chiamare. Con il file d'esito decide il server, e il runner legge
  un dato solo, che ha nominato lui.

## Condizione di revisione

Se un'harness usata dal runner non offre né strumenti né output strutturato.
