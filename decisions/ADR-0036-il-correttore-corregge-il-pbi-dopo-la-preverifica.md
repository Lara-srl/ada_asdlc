# ADR-0036: dopo una preverifica con rilievi un Correttore corregge il PBI, e il merge resta di una persona

**Stato:** **Proposta** · **Data:** 2026-11-06 · **Ratifica:** Francesco, con il merge
(`ADR-0012`, `ADR-0029`). Non cambia la costituzione: `AGENTS.md` non dice chi corregge un PBI.
**Restringe** la decisione 6 di `ADR-0031`, «Le correzioni le scrive una persona», che resta
scritta e barrata col rimando (sotto, *La frase ristretta*). Il Lettore continua a non correggere.

## Contesto

Da `PBI-522` (`v1.0.0`) un PBI con un rilievo della preverifica si ferma prima del ramo, e il tick
scrive `attende: preverifica PBI-N — K rilievi, correggi il PBI` ogni dieci minuti, finché una
persona non corregge il file e la correzione arriva su `main`. In `ada_dispense` è successo con
`PBI-011` (30/10), `PBI-037` (3/11), `PBI-043` (4/11, due volte) e `PBI-015` (6/11). Ogni volta il
Lettore aveva già scritto la correzione nel rilievo («il PBI dovrebbe dire che…, per esempio…»).
Il lavoro della persona era stato copiare quella strada nel PBI, aprire la PR e mergiarla. La coda
è rimasta ferma ore, dall'ora del rilievo all'ora in cui Francesco guardava.

Il 06/11 Francesco ha chiesto che le proposte della preverifica si applichino da sole e che a lui
resti il merge: «le proposte della revisione [vengano] approvate e il builder rilanciato e a me il
merge».

`ADR-0031` aveva scartato «il Lettore che corregge il PBI da sé», perché cambierebbe un documento
firmato da Francesco senza la sua firma. Questo ADR tiene quella ragione: la correzione è una PR, e
la firma è il merge.

## Decisione

1. **Il Correttore è un agente nuovo, separato dal Lettore.** Chi trova il difetto non è chi lo
   corregge: il Lettore resta in sola lettura (`ADR-0031`, decisione 6, prima frase), e il
   Correttore legge i suoi rilievi e il codice alla base.
2. **Il Correttore scrive solo il file del PBI.** Lo controlla il codice sul diff, non il prompt.
   Un diff che tocca altro non diventa una PR.
3. **La correzione è una PR che il tick non mergia mai.** Il ramo non è `pbi/pbi-…`, e la prima
   condizione di `ADR-0033` la esclude già. Questo ADR la nomina tra le PR che restano di Francesco
   (`ADR-0033`, decisione 4: «le PR che non ha aperto il runner»). Al merge il tick rilancia il PBI
   come oggi: il file è cambiato su `main`, e la preverifica riparte col Lettore.
4. **Un rilievo che chiede una decisione del proprietario non si corregge.** Sono una scelta tra
   strade che il rilievo lascia aperta, un limite o una regola del progetto (il CHIEDI di
   `AGENTS.md` del progetto), un ADR. Il Correttore chiama `chiede` con la domanda, e il tick la
   notifica come fermo.
5. **Gli esiti passano per chiamate a strumento** (`ADR-0027`): `corretto` o `chiede`. Senza
   chiamata la correzione è `senza esito`, e non nasce nessuna PR.
6. **È spento se il progetto non lo accende**, con `[preverifica].correzione = true`, come
   `[preverifica].attiva`.

**Le quattro domande** (`decisions/README.md`):

1. **Cosa si controlla:** il diff della correzione (un solo file, quello del PBI) e la
   preverifica di forma (`PBI-520`) sul file corretto.
2. **Quando:** al tick che trova un `AttendeLaPreverifica` senza una correzione per quella
   versione del PBI.
3. **Cosa conta come prova:** la PR aperta, col corpo che dice per ogni rilievo come è stato
   corretto, e `corretto` chiamato. Oppure `chiede` chiamato, con la domanda nella notifica.
4. **Cosa succede se manca:** nessuna PR. Il tick torna alla riga di oggi, `correggi il PBI`,
   col motivo (`ADR-0008`: si segnala, non si blocca).

## La frase ristretta

- `ADR-0031`, decisione 6: ~~«Le correzioni le scrive una persona, come nella #68»~~. Le scrive il
  Correttore, in una PR che mergia una persona (questo ADR); la persona resta chi firma. *Si rivede
  se* le PR del Correttore vengono chiuse senza merge o riscritte a mano più spesso di una su tre:
  vorrebbe dire che copiare la strada del rilievo non basta.

## Conseguenze

- **Positive:** il tempo tra il rilievo e la correzione passa da ore a minuti. A Francesco resta
  una PR da leggere, col confronto rilievo per rilievo, invece di un PBI da riscrivere.
- **Negative:** un agente in più e una chiamata in più per ogni preverifica rossa. Un Correttore
  che copia una strada sbagliata del Lettore la porta nella PR. La difesa è la lettura al merge, e
  dopo il merge la preverifica col Lettore rifatta sulla versione nuova.
- **Neutre:** il Lettore, il Builder, il Critic, il Solver e le condizioni del merge di `ADR-0033`
  non cambiano.

## Alternative considerate

- **Il Lettore corregge da sé.** Già scartata in `ADR-0031`: chi trova il difetto confermerebbe
  la propria lettura. Resta scartata.
- **Il tick mergia la correzione se la preverifica di forma è verde.** Toglierebbe Francesco dal
  giro anche dove il Lettore ha scelto una strada al posto suo. Francesco il 06/11 ha chiesto di
  restare sul merge. Scartata.
- **Lo Scrittore** (`ADR-0031`, decisione 6, ultima frase): un ruolo che scrive i PBI da zero. È
  più largo di ciò che serve oggi. Il Correttore ne è il pezzo più piccolo, e lo Scrittore resta
  dopo.
