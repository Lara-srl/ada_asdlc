# PBI-541: dopo una preverifica con rilievi un Correttore corregge il PBI e apre la PR

**Stato:** proposto il 06/11 da Francesco («le proposte della revisione [vengano] approvate e il
builder rilanciato e a me il merge»); **non letto**, **non in coda**. La regola che cambia è in
`decisions/ADR-0036-il-correttore-corregge-il-pbi-dopo-la-preverifica.md`, nella stessa PR: il
merge la ratifica (`ADR-0012`). Va letto (Lettore separato) e pre-verificato prima di entrare nello
sprint 2, accanto a `PBI-540`.

## Direttiva

Con un rilievo la preverifica chiude il giro `fermato` col motivo `preverifica`, prima del ramo
(`PBI-522`). Il tick poi scrive `attende: preverifica PBI-N — K rilievi, correggi il PBI` ogni dieci
minuti, finché una persona non corregge il file su `main`. Nei cinque fermi di `ada_dispense` dal
30/10 al 06/11 (`PBI-011`, `PBI-037`, `PBI-043` due volte, `PBI-015`) il rilievo scriveva già la
correzione: «il PBI dovrebbe dire che…, per esempio…». La persona l'ha copiata nel PBI, ha aperto
una PR e l'ha mergiata, e la coda è rimasta ferma dall'ora del rilievo all'ora in cui Francesco
guardava. Il 06/11 alle 20:28 è successo con `PBI-015`, e il tick ha ripetuto la riga fino alla PR
#85 di `ada_dispense`, scritta a mano.

Questo PBI aggiunge il **Correttore** (`ADR-0036`). Al tick che trova il fermo, il Correttore legge
i rilievi e il codice alla base, corregge **solo** il file del PBI e apre la PR. Il merge resta di
Francesco. Al merge il tick rilancia il PBI come oggi, perché lo sha del file è cambiato, e la
preverifica col Lettore rilegge la versione nuova. Un rilievo che chiede una scelta del
proprietario non lo corregge: lo chiede.

**Scope**

- `tools/asdlc/config.py`: `Preverifica.correzione` (default `False`) e la sezione `[correttore]`
  (`modello`, `minuti`), come `[lettore]`.
- `tools/asdlc/runner.py`: `--correggi`, cioè `correggi(pbi) -> int`; la lettura del Correttore
  nel suo albero usa e getta alla base, come `lettura_del_lettore()`; il controllo del diff; la
  forma con `forma_del_pbi()` sul testo corretto; la PR; il rapporto
  `<run>-<PBI>-correzione.json`.
- `tools/asdlc/prompt/correttore.md`: **nuovo**, il prompt del Correttore.
- `tools/asdlc/coda.py`: `decidi()` (il ramo di `AttendeLaPreverifica`), le decisioni nuove
  `Corregge` e `AttendeLaCorrezione`, `racconta()`, `lancia_la_correzione()`.
- `tools/asdlc/notifiche.py`: `della_decisione()`, gli eventi di `AttendeLaCorrezione`.
- `tools/tests/test_asdlc_correzione.py`: **nuovo**, i test dei criteri.
- `tools/tests/dati/prompt/correttore.txt`: **nuovo**, il golden del prompt (criterio 8), come
  gli altri di `test_asdlc_prompt.py`.
- `README.md`: i ruoli e il ciclo, nello stesso commit del codice.
- `specs/solver-e-rilascio/spec.md`: la preverifica e il fermo, nello stesso commit del codice.
- `backlog/AUTOMAZIONE.md`: il fermo in preverifica, nello stesso commit del codice.
- `template/asdlc.toml`: `correzione = true` commentato sotto `[preverifica]`, con il rimando a
  `ADR-0036`.
- `backlog/PBI-541-dopo-la-preverifica-un-correttore-corregge-il-pbi.md`: questo file, per la
  spunta.

**Fuori scope**

- Il Lettore, le sette domande, le sonde: restano come sono. Il Correttore non rifà la lettura,
  e la rilettura la fa la preverifica del giro dopo il merge.
- Il merge della correzione: resta di una persona (`ADR-0036`, decisione 3). Le condizioni di
  `ADR-0033` non cambiano: la prima esclude già un ramo che non è `pbi/pbi-…`.
- Uno Scrittore che scrive i PBI da zero (`ADR-0031`, decisione 6, ultima frase).
- Accendere la correzione nei cinque progetti: una PR di configurazione ciascuno, dopo il pin.
- `decisions/ADR-0031-la-lettura-prima-della-coda.md` e `decisions/ADR-0033-…`: la barratura
  della decisione 6 di `ADR-0031` e la riga in `ADR-0033`, decisione 4, le porta la PR che
  accoda questo PBI. Un file di `decisions/` lo ratifica il merge di una persona, e non deve
  stare nel diff di un giro.

## ✅ Deciso

1. **Quando parte.** Con `[preverifica].attiva` e `[preverifica].correzione`, `decidi()` cambia
   il suo `AttendeLaPreverifica` in `Corregge(pbi)` se non c'è un rapporto di correzione per lo
   stesso `sha_pbi` dell'ultima preverifica. Il tick lancia allora `<pacchetto>/bin/asdlc-runner
   PBI-N --correggi` nel worktree del runner, come `lancia()`, col lucchetto del giro. Senza
   `correzione` il tick fa quello che fa oggi.
2. **Una correzione per versione del PBI**, come una preverifica per versione (`ADR-0031`,
   decisione 7). Il rapporto `<run>-<PBI>-correzione.json` porta `sha_pbi`, `esito` (`corretto`,
   `chiede`, `senza esito`, `fuori scope`, `forma rossa`), `pr`, `domanda` e i rilievi a cui
   risponde. Con un rapporto per lo stesso `sha_pbi` il tick non rilancia. Il tick dice
   `AttendeLaCorrezione(pbi, pr, domanda, esito)`.
3. **Il Correttore lavora come il Lettore:** un albero usa e getta alla base, che è il suo `cwd`
   e si smonta comunque vada. Ha `Read`, `Grep`, `Glob`, `Write` ed `Edit`, e non ha `Bash`. Gli
   strumenti dell'esito sono `corretto(sintesi, risposte)`, con una risposta per rilievo (il
   rilievo e come è stato corretto), e `chiede(domanda, rilievo)`. Modello e tetto vengono da
   `[correttore]`, con default `opus` e 30 minuti come `[lettore]`.
4. **Il diff lo controlla il codice.** Dopo `corretto`, `git status --porcelain` nell'albero ha
   una riga sola, quella del file del PBI. Se non è così l'esito è `fuori scope` e nessuna PR
   nasce: l'albero si smonta, e il rapporto elenca i file toccati.
5. **La forma prima della PR.** `forma_del_pbi(testo corretto, pbi)` deve dare zero rilievi.
   Altrimenti l'esito è `forma rossa` e nessuna PR nasce. Il Lettore non rigira qui: lo fa la
   preverifica del giro dopo il merge, sulla versione nuova.
6. **La PR.** Il ramo è `correzione/<id in minuscolo>-<run>`, dalla base, con un commit
   `docs(backlog): recepisci in PBI-N i K rilievi della preverifica del <data>`. Il titolo è
   «PBI-N: i rilievi della preverifica, corretti». Il corpo ha, per ogni rilievo, la domanda,
   il testo del rilievo e la risposta del Correttore, e in fondo la riga «La mergia una persona
   (`ADR-0036`): al merge il tick rilancia il PBI». La PR la apre `gh pr create`, come
   `apri_pr()`.
7. **`chiede` non apre una PR.** La domanda va nel rapporto e nella notifica `fermo`: «⛔
   <progetto>: PBI-N fermo — preverifica, il Correttore chiede: <domanda>». Il tick resta su
   `AttendeLaCorrezione` finché il file del PBI non cambia su `main`, come oggi.
8. **Il prompt dice tre cose, che vengono dai fermi veri.** (a) Si prende la strada che il
   rilievo propone quando ne propone una, e si chiede quando ne lascia aperte due o più. (b) Una
   correzione che fa cambiare un test esistente nomina il test nello Scope e nella Non
   regressione, e prima cerca **tutti** i test che leggono lo stesso file o lo stesso valore. In
   `PBI-015` il Lettore aveva visto `test_figure.py` e non `test_sorgente.py:32`, che legge lo
   stesso blocco. (c) Un limite, una regola o un CHIEDI dell'`AGENTS.md` del progetto si
   chiedono, non si correggono.
9. **Le notifiche.** `Corregge` non notifica: è un lavoro in corso, come `Lancia`.
   `AttendeLaCorrezione` con una PR è l'evento `pronto`, «🟢 <progetto>: PBI-N, correzione della
   preverifica pronta — #M». Con `chiede`, `senza esito`, `fuori scope` o `forma rossa` è l'evento
   `fermo`, col motivo. Un evento uguale non si ripete (`PBI-533`).

## Dipendenze

- Bloccato da: `PBI-522` (in `v1.0.0`).
- Blocca: niente. Con `PBI-540` divide `runner.py` e `coda.py` ma non le stesse funzioni.

## Contesto

- `decisions/ADR-0036-il-correttore-corregge-il-pbi-dopo-la-preverifica.md`, `ADR-0031`
  (decisioni 6 e 7), `ADR-0033` (decisioni 1 e 4), `ADR-0027`, `ADR-0008`.
- `tools/asdlc/runner.py`: `scrivi_la_preverifica()`, `lettura_del_lettore()`, `forma_del_pbi()`,
  `apri_pr()`.
- `tools/asdlc/coda.py`: `decidi()` (il blocco `isinstance(decisione, Lancia)`),
  `AttendeLaPreverifica`, `sha_del_pbi()`, `ultimo_esito()`, `lancia()`.
- `tools/asdlc/notifiche.py`: `della_decisione()` per `AttendeLaPreverifica`, `pronto()`.
- Il fermo vero: `ada_dispense`, `runs/20261106-202815-PBI-015-preverifica.json` nel worktree del
  runner, e la correzione a mano, PR #85.

## Verifica

- [ ] **Con `correzione` accesa il tick corregge.** Con `[preverifica] attiva = true, correzione =
      true`, un ultimo esito `fermato`/`preverifica` con `sha_pbi` uguale al file su `main` e
      nessun rapporto di correzione, `decidi()` dà `Corregge(pbi)`, e `racconta()` dà
      `corregge: PBI-N — K rilievi della preverifica` (pytest). Rosso su `main`:
      `AttendeLaPreverifica`.
- [ ] **Senza `correzione` resta com'è, ed è una guardia.** Lo stesso stato senza la chiave dà
      `AttendeLaPreverifica` e la riga di oggi (pytest, nato verde). `Guardia-su:
      tools/asdlc/coda.py::decidi`.
- [ ] **`--correggi` apre la PR con le risposte.** Con un Correttore finto che modifica il file
      del PBI e chiama `corretto` con una risposta per ognuno dei due rilievi del rapporto finto,
      e con `gh` finto: c'è un commit sul ramo `correzione/pbi-n-<run>` che tocca solo il file del
      PBI, `gh pr create` è chiamato con il corpo che contiene i due rilievi, le due risposte e la
      riga «La mergia una persona», e il rapporto ha `esito: corretto` e il `pr` (pytest). Rosso su
      `main`: `--correggi` è un argomento che argparse rifiuta.
- [ ] **Un diff fuori dal PBI non diventa una PR.** Lo stesso finto, che tocca anche
      `tools/asdlc/coda.py`: `gh pr create` non è chiamato, il rapporto ha `esito: fuori scope` e
      i due file toccati, e l'albero usa e getta non c'è più (pytest). Rosso su `main` come il
      criterio 3.
- [ ] **Una forma rossa non diventa una PR.** Il finto toglie la sezione `## Verifica` dal PBI e
      chiama `corretto`: il rapporto ha `esito: forma rossa` e il rilievo di `forma_del_pbi()`, e
      `gh pr create` non è chiamato (pytest). Rosso su `main` come il criterio 3.
- [ ] **`chiede` e il silenzio non aprono una PR.** Un finto che chiama `chiede("quale delle due
      strade?", 2)` dà `esito: chiede` con la domanda. Un finto che non chiama niente dà `esito:
      senza esito`. In tutti e due i casi `gh pr create` non è chiamato (pytest). Rosso su `main`
      come il criterio 3.
- [ ] **Una correzione per versione, e il tick lo dice.** Con un rapporto di correzione per lo
      stesso `sha_pbi`, `decidi()` dà `AttendeLaCorrezione` e non `Corregge`. `racconta()` dà
      `attende: correzione PBI-N — PR #M, la mergia una persona` con la PR, e `attende:
      correzione PBI-N — il Correttore chiede: <domanda>` con `chiede`. `notifiche.della_decisione()` dà
      `pronto` nel primo caso e `fermo` nel secondo. Con lo sha cambiato su `main`, `decidi()` dà
      `Lancia` (pytest). Rosso su `main`: la decisione non c'è.
- [ ] **Il prompt ha le tre regole e il golden.** `prompt_del_pacchetto("correttore")` reso coi
      valori di un PBI e di due rilievi è uguale byte per byte a
      `tools/tests/dati/prompt/correttore.txt`, che contiene le tre regole del Deciso 8 (pytest).
      Rosso su `main`: il prompt non c'è.

**Non regressione:**

- Il Lettore, il suo prompt e il suo golden non cambiano: `test_asdlc_lettore.py` e
  `test_asdlc_prompt.py` restano verdi senza essere toccati.
- `condizione_mancante()` non cambia, e una PR su `correzione/…` non si mergia: la prima
  condizione di `ADR-0033` già la esclude.
- Un progetto senza `[preverifica].correzione` ha lo stesso comportamento e lo stesso log di oggi.
- I test scrivono solo in `tmp_path`.

## ❓ Domande aperte

1. **Il modello del Correttore.** Il default proposto è `opus`, come il Lettore. Il Correttore
   però scrive meno di quanto legga, e `sonnet` potrebbe bastare. Lo decide Francesco alla
   lettura.
2. **Più di una correzione di fila.** Se dopo il merge la preverifica trova rilievi nuovi, la
   versione nuova ha uno sha nuovo e il Correttore riparte. Serve un tetto per PBI (per esempio
   `[soglie].correzioni = 2`, poi la riga di oggi)? Proposta: sì, in questo PBI, come criterio
   in più.
