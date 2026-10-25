# ADR-0033: il merge di un giro è del tick, alle condizioni che il codice verifica

**Stato:** **Proposta** · **Data:** 2026-10-25 · **Ratifica:** Francesco, con il merge
(`ADR-0012`, `ADR-0029`). Non cambia la costituzione: `AGENTS.md` non nomina chi mergia.
**Restringe** la frase di `ADR-0030`, decisione 3, «I merge restano sempre di Francesco», che
resta scritta e barrata col rimando: restano di Francesco i merge che questo ADR gli lascia, gli
altri sono del tick. `ADR-0012` non cambia: la ratifica di un ADR è un merge di una persona, e il
tick non mergia mai un file di `decisions/` o `AGENTS.md`.

## Contesto

Con tre progetti sul runner (19–25/10, `v0.7.0`) Francesco è stato nel giro in quattro punti:
scrive i PBI, risponde ai fermi, mergia, riprende i giri fermati. Tag e pin li fa già il tick
(`ADR-0030`). Delle 14 PBI arrivate in `main`, 10 hanno chiuso `fatto` al primo giro con Critic
`pass` e CI verde: in quei dieci merge non c'era una decisione da prendere, solo un clic da dare,
e il clic arrivava quando Francesco guardava, non quando il giro finiva. La coda si fermava lì.

La richiesta del 25/10 è togliersi di mezzo. Un agente che mergia (un «Merger») è stato
considerato e rimandato: il merge dei casi semplici non chiede giudizio, chiede verifiche, e le
verifiche le fa meglio il codice. Ciò che chiede giudizio resta a una persona, e questo ADR dice
esattamente cosa.

## Decisione

1. **Il tick mergia la PR di un giro quando tutte le condizioni sono vere**, e le verifica in
   codice, senza modello:
   - la PR l'ha aperta il runner: ramo `pbi/pbi-XXX…`, e il PBI è in `CODA.md`;
   - l'ultimo rapporto del giro di quel PBI chiude `fatto`, con il Critic che ha girato
     (`critic_saltato` falso) e nessun esito `intento`;
   - la CI sulla testa della PR è verde, e la PR è mergeabile;
   - il file del PBI alla testa della PR ha ogni criterio spuntato, e **nessun** criterio `(a vista)`
     (`ADR-0032`);
   - ogni file della PR sta nello Scope del PBI (i percorsi di `percorsi_dello_scope()`, prefisso
     per le cartelle) o è il file del PBI: una deroga allo Scope (`ADR-0015`) è un file fuori, e
     va a una persona;
   - nessun file della PR è `AGENTS.md`, `CLAUDE.md`, `asdlc.toml`, sotto `decisions/`, o sotto
     `template/AGENTS.md` e `template/decisions/`.
2. **Il merge è un merge commit**, come oggi a mano: i micro-commit restano, e il gate del rosso
   e `ADR-0022` leggono quella storia. Niente squash.
3. **Il tick dice cosa ha fatto.** Un commento sulla PR con l'elenco delle condizioni verificate,
   e una riga nel log del tick. Una PR che non passa resta aperta e il log dice quale condizione
   manca: è un `attende`, non un fermo.
4. **Restano di Francesco:** le PR con un criterio `(a vista)`; le PR che toccano la costituzione
   o `asdlc.toml`; le PR con una deroga allo Scope; le PR che non ha aperto il runner (accoda,
   riprese, documenti); ogni esito `intento`. Sono i casi in cui il merge è una decisione.

**Le quattro domande** (`decisions/README.md`):

1. **Cosa si controlla:** la PR aperta (ramo, file, stato della CI, mergeabilità), il file del
   PBI alla sua testa, l'ultimo rapporto del giro in `runs/`.
2. **Quando:** a ogni passaggio del tick, prima del rilascio e del pin, così il tag segue il
   merge nello stesso passaggio o in quello dopo.
3. **Cosa conta come prova:** `gh pr merge --merge` chiamato con uscita 0, la riga
   `merge: PBI-N #M` nel log, il commento sulla PR. Ogni condizione è un'asserzione su un campo di
   `gh pr view --json` o su un file.
4. **Cosa succede se manca:** nessuna azione, la PR resta aperta, il log scrive
   `merge: #M attende una persona — <condizione>` a ogni passaggio (`ADR-0008`: si segnala).

## Conseguenze

- Il giro normale chiude senza una persona: PBI in coda, giro, PR, merge, tag, pin. Francesco
  legge le PR dopo, non prima, e il revert resta a un comando.
- Il merge diventa anche il momento in cui la catena si conferma da sola: Builder, Critic e tick
  sono tre esecutori senza un occhio umano. La misura: un campione settimanale di PR mergiate dal
  tick lette da Francesco, e il conto delle PR che il tick ha lasciato a una persona, per cause.
- Il bump di `tools/pyproject.toml` oggi è una PR a mano prima del tag: con il merge automatico è
  l'ultimo gesto umano del rilascio, e va tolto con un PBI suo.
- `PBI-528` viene prima: un rilascio che parte dalla PR sbagliata, col merge automatico, taggherebbe
  ancora più spesso a vuoto.

## Alternative considerate

- **Un agente Merger.** Legge la PR, la traccia della sessione e il rapporto, e dichiara
  `mergia` o `rimanda` con uno strumento. Rimandato: per i casi semplici non aggiunge niente alle
  verifiche in codice, e per i casi difficili sposta su un modello ciò che il proprietario ha
  detto di voler decidere. Si riconsidera con i numeri del primo mese.
- **Merge su CI verde e basta.** Troppo poco: la CI non sa dello Scope, dei criteri spuntati, del
  Critic saltato. Dieci PR su quattordici passerebbero, e le quattro sbagliate pure.
- **Squash al merge.** Perde la storia che il gate del rosso e `ADR-0022` leggono, e i punti di
  ripristino dei micro-commit. `AGENTS.md` lo ammette «se serve»: qui non serve.
- **Il tick che chiude anche gli ultimi gesti del rilascio (il bump, il pin senza `attende:`).**
  Giusto, ma è un altro PBI: qui si decide chi mergia.
