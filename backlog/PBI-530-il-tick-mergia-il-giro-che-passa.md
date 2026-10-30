# PBI-530: il tick mergia il giro che passa
rilascia: major

**Stato:** letto il 26/10 col Lettore (in fondo), **in coda** dopo `PBI-528` (Francesco, 26/10: «quello
che mi interessa di più è il merge in automatico»).
Dichiara `rilascia: major` (decisione 5): il tag è la `v1.0.0`, e il merge di questa PR dice che
Francesco vuole che lo sia.

## Direttiva

Il merge delle PR dei giri passa al tick, alle condizioni di `ADR-0033`: verificabili in codice,
una riga nel log e un commento sulla PR, niente modello. Restano a una persona i casi che l'ADR
elenca. Il tick non ha mai mergiato niente: oggi legge `MERGED` per spegnere la voce, rilasciare e
pinnare, e lì non cambia nulla.

**Scope**

- `tools/asdlc/coda.py` — `passo_del_merge(repo, worktree)`, chiamato da `passaggio()` con `a.worktree`
  e nel tick **prima** di `passo_di_rilascio()`: la lettura delle PR aperte (`gh pr list --state open --json
  number,title,headRefName,files,statusCheckRollup,mergeable`), le sei condizioni, `gh pr merge
  --merge`, `gh pr comment`, le righe del log. `RE_RILASCIA` e `prossimo_tag()` accettano `major`.
- `tools/asdlc/runner.py` — niente, se `percorsi_dello_scope()` e `criteri_del_pbi()` bastano da
  `coda.py` (che già importa `asdlc_runner`).
- `backlog/CODA.md` (testa) e `README.md` — il merge del tick, nello stesso commit del codice.
- `template/backlog/CODA.md` — la stessa frase.
- `specs/solver-e-rilascio/spec.md` — nello stesso commit del codice (`AGENTS.md`, SEMPRE): in R8
  «`rilascia: patch` o `rilascia: minor`» diventa «`patch`, `minor` o `major`» e «`major` alza X e azzera
  Y e Z»; in R11 «Il merge non è del tick» diventa «Il merge delle PR dei giri è del tick alle condizioni
  di `ADR-0033`; `rilascia()` e `pin()` non emettono mai `gh pr merge`», così il test
  `test_nessun_gh_pr_merge_esce_da_rilascia_ne_da_pin` resta valido; in R8 «Dove sta», l'ordine dei passi
  del tick con `passo_del_merge` davanti al rilascio.
- `tools/tests/test_asdlc_rilascio.py` — i test dei criteri, con la classe `Mondo` e le fixture `mondo` e
  `progetto` (origin bare, checkout, `gh` finto) che stanno lì; il criterio 4 fa girare davvero
  `passo_di_rilascio()` dopo il merge e ha bisogno di quel mondo.
- `backlog/PBI-530-il-tick-mergia-il-giro-che-passa.md` — questo file, per la spunta.
- **Fuori scope:** il bump di `pyproject.toml`; il pin senza `attende:`; l'agente Merger; una issue
  per le PR che attendono una persona (è il canale di `PBI-525` e si può aggiungere dopo).

Il PBI tocca `coda.py`, che il tick lancia: il tick gira **installato** (`ADR-0026`) e vede il passo
nuovo solo al tag successivo.

## ✅ Deciso

1. **Le condizioni sono quelle di `ADR-0033`, decisione 1**, nell'ordine scritto lì; la prima che
   manca dà il motivo nel log, e le altre non si guardano.
2. **Il file del PBI alla testa della PR** si legge con `git show origin/<ramo>:<percorso>` dopo
   il `fetch` che il tick già fa. **Il rapporto del giro sta nel worktree del runner**, non nel checkout
   del tick (`PBI-519`, decisione 5): lo legge `coda.ultimo_esito(worktree, pbi)`, che esiste già, ed è
   per questo che `passo_del_merge` riceve `worktree`. ~~come lo trova `chiudi_giro.ultimo_rapporto()`~~:
   corretto il 26/10, `chiudi_giro.py` importa `coda` e l'import sarebbe circolare. L'esito `intento` non
   è lo `stato` del giro: è `esito == "intento"` in una delle voci di `Esito.solver` del rapporto.
3. **I file della PR** sono `files` di `gh pr list`, con il fail-closed di `tocca_codice()`: un elenco
   assente o lungo `LIMITE_FILE` **non** si mergia (qui il segno è l'opposto della coda: nel dubbio
   non si agisce).
4. **Lo Scope si legge con `percorsi_dello_scope()`**: un file della PR passa se è uguale a un
   percorso dello Scope o sta sotto un percorso dello Scope che finisce con `/`. I file che `PBI-520`
   segnala come avvisi (nomi abbreviati) non si interpretano: se un file non passa, va a una persona.
5. **`rilascia: major`** alza X e azzera Y e Z. Serve per la `v1.0.0` di questo PBI e per le volte
   in cui un rilascio cambia il contratto dei progetti (il formato di `asdlc.toml`, i nomi degli
   strumenti). Non è un terzo modo di dire `minor`: si usa quando chi pinna deve rileggere.
6. **Il commento sulla PR** elenca le sei condizioni con «ok» e lo sha mergiato; è l'unico testo
   che il tick scrive su GitHub oltre alla PR del pin. **Scope dei commit:** `coda` per `coda.py`,
   `config` per le frasi di `CODA.md` e `README.md`, `template` per `template/`.

## Dipendenze
- Bloccato da: `PBI-528` (il rilascio dalla PR giusta). ~~`PBI-527` (la marca `(a vista)` nel codice:
  senza, la condizione si legge lo stesso con la stessa regex, ma la regola deve esistere prima)~~:
  Francesco, 26/10: `PBI-527` esce dal cammino critico. La regola esiste (`ADR-0032` è in `main`), la
  condizione si legge con la stessa regex, e il 527 va dopo il 530.
- Blocca: nessuno.

## Contesto
- `decisions/ADR-0033-il-merge-di-un-giro-e-del-tick.md` — le condizioni e le quattro domande.
- `tools/asdlc/coda.py`: il tick, `passo_di_rilascio()`, `passo_del_pin()`, `pbi_nominato()`,
  `RE_RAMO_PR`, `tocca_codice()`, `LIMITE_FILE`, `ci_verde()`, `RE_RILASCIA`, `prossimo_tag()`.
- `tools/asdlc/runner.py`: `percorsi_dello_scope()`, `criteri_del_pbi()`, `RE_CRITERIO`; il
  rapporto del giro (`apri_rapporto()`, `Esito.critic_saltato`).
- `tools/tests/test_asdlc_rilascio.py`: i test del rilascio e del pin col `gh` finto (`class Mondo`,
  fixture `mondo` e `progetto`).
- `tools/asdlc/coda.py`: `ultimo_esito()`, `passaggio()`; `specs/solver-e-rilascio/spec.md`: R8, R11.

## Verifica
- [x] **Una PR che passa tutte le condizioni si mergia, e il tick lo dice.** Repository di prova con
      `PBI-7` in coda, un rapporto `fatto` con Critic girato, il file del PBI tutto `[x]`, `gh` finto
      che rende una PR su `pbi/pbi-7` con CI `SUCCESS`, `MERGEABLE` e `files` dentro lo Scope:
      `passo_del_merge()` chiama `gh pr merge 1 --merge`, poi `gh pr comment`, e rende
      `merge: PBI-7 #1`. Rosso su `main`: `passo_del_merge` non esiste.
- [x] **Ogni condizione che manca lascia la PR a una persona, col motivo.** Parametrico, un id per
      caso, sullo stesso scenario con una sola cosa cambiata: ramo non `pbi/`; rapporto con
      `critic_saltato`; esito `intento`; CI `FAILURE`; `CONFLICTING`; un criterio `[ ]`; un criterio
      marcato a vista e spuntato; un file fuori Scope; un file in `decisions/`; `files` assente. In ogni
      caso nessun `gh pr merge`, e la riga `merge: #1 attende una persona — …` nomina la condizione.
- [x] **`rilascia: major` dà la `v1.0.0`.** `prossimo_tag(["v0.9.2"], "major") == "v1.0.0"` e
      `rilascia_del_pbi("…\nrilascia: major\n…") == "major"`. Rosso su `main`: `RE_RILASCIA`
      accetta solo `patch|minor`.
- [x] **Il merge viene prima del rilascio nello stesso passaggio.** Col `gh` finto che rende la PR
      aperta e poi, dopo il `merge`, la stessa PR `MERGED`: un passaggio del tick scrive
      `merge: PBI-7 #1` e poi `rilascio: PBI-7 → …`, in quest'ordine. Rosso su `main`: nessuna riga
      `merge:`.

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde; i test del rilascio e del pin
non cambiano; senza PR aperte il tick scrive le stesse righe di oggi (guardia).

## Protocollo di rifinitura
Si può scegliere senza chiedere: il testo esatto del commento e delle righe del log, purché portino
«merge:», il numero della PR e la condizione; se `statusCheckRollup` si legge da `pr list` o da
`pr view`.
Si chiama `fermati`: se `gh pr merge` chiede un'interazione che un cron non può dare; se il
rapporto del giro non basta a dire che il Critic ha girato.

## La lettura del 26/10

`asdlc-runner PBI-530 --preverifica --lettore` (runner `v0.7.0`), su `main` `3acb74d`, in un albero usa e
getta: tre rilievi, tutti verificati nel codice e recepiti. **D** sulla firma: `passo_del_merge(repo)`
avrebbe letto `runs/` del checkout del tick, che è vuota, perché i rapporti stanno nel worktree del runner
(`coda.ultimo_esito()`), e in produzione nessuna PR avrebbe passato la condizione del rapporto:
decisione 2 e Scope. **D** sulla spec: `specs/solver-e-rilascio/spec.md` R8 e R11 dicono l'opposto dei
criteri 1 e 3 e non erano nello Scope: Scope. **N** sui test: `Mondo` e le fixture stanno in
`test_asdlc_rilascio.py`, non in `test_asdlc_coda.py`: Scope e Contesto. Le quattro sonde sono uscite
`guasto` (il gate nell'albero usa e getta, `PBI-529`): il rosso resta dichiarato, non provato.

## Il giro 2, e cosa si riprende

Il giro 1 (28/10, run `20261028-212514`, 21:25-21:44, runner `v0.9.0`) ha fatto i **quattro criteri**
con quindici commit, RED e GREEN per criterio, e li ha spuntati. Il Critic (revisione 0) ha dato
«non pronto» con quattro rilievi: il tick scriveva «mergiato» anche se il merge non era avvenuto (1), il
commento sulla PR non elencava le sei condizioni né lo sha (2), comportamenti nati senza RED nel GREEN del
criterio 4 (3), il PBI nominato nel log poteva non essere quello verificato (4). I rilievi 1, 2 e 4 il
Builder li ha corretti **con i loro RED** (`7d5a6cf`…`64a03c4`). Il 3 lo ha chiuso con `5ec7fa2`, un test
nato verde che non morde (122 mutanti provati nelle funzioni toccate, nessun fallimento per asserzione):
il gate del rosso ha fermato il giro `rosso-mai-visto`. Il tag è `giro-fermato/pbi-530-giro1-20261028`
(`5ec7fa2`).

**Perché `5ec7fa2` non è riportato.** Un test nato verde non si toglie con un revert (il gate del rosso
guarda ogni commit del ramo, lezione del 19/10); e il codice che doveva guardare è già in `6ca9a7e`.
Come per il 525 si riporta tutto **tranne** quel commit e il RED dei tre comportamenti si rifà vero.

Sul ramo di ripresa, verificato il 28/10: `python3 -m pytest -q tools/tests` dà `1257 passed`,
`git status --porcelain` è vuoto e `asdlc-runner --gate-rosso HEAD` dice «nessun test è nato verde».

**Da fare, in quest'ordine:**

1. **I quindici commit sono già in `main`** (li porta la PR di ripresa, `cherry-pick -x` dal tag, senza
   `5ec7fa2`), dal RED `64d024a` al GREEN `64a03c4`. **Verifica:** `git log --oneline` su `main` li
   mostra; non si riportano di nuovo.
2. **Due comportamenti del rilievo 3, ciascuno col suo RED**, in un commit `test` solo dopo averne
   tolto il codice in un `refactor`, come per la guardia del dry-run del 525: (a) `mergia()` rende
   `merge: avviso, …` quando `passo_del_merge()` solleva e il tick prosegue e rilascia (il `refactor` toglie
   il `try/except` di `mergia()`); (b) `gh pr list` che esce diverso da 0 non scrive nessuna riga `merge:`
   (il `refactor` toglie `if codice != 0: return []` in `passo_del_merge()`, e `json.loads` legge l'uscita
   d'errore). Per ognuno: `refactor` (si toglie il codice, nessun test cambia), `test` (rosso), `fix` (si
   rimette il codice). **Verifica:** `asdlc-runner --gate-rosso HEAD` passa e i due test falliscono ognuno
   sul proprio RED.
   **Il terzo comportamento, (c), esce dal punto 2** (deciso il 30/10/2026, rilievo R della preverifica
   `20261029-000511`): «con zero PR aperte nessuna riga `merge:`, né `gh pr merge` né commento» non ha codice
   da togliere in un `refactor`, perché con `[]` `passo_del_merge()` non entra nel ciclo per costruzione; un
   suo test nascerebbe verde e il gate del rosso fermerebbe il giro come ha fermato il giro 1 con `5ec7fa2`.
   Resta quello che già era: la **non regressione** «senza PR aperte il tick scrive le stesse righe di oggi»,
   coperta dai test del tick che esistono. **Nessun test nuovo per (c)**, e il Critic accetta (a) e (b) come
   chiusura del rilievo 3. Scartata l'alternativa di dichiarare (c) guardia: dovrebbe mordere un mutante, e
   nelle funzioni toccate nessuno la fa fallire (122 mutanti provati sul giro 1).
3. **Il Critic** deve poter dire `pronto`: il rilievo 3 era l'ultimo aperto.
