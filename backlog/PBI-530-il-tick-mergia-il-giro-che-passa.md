# PBI-530: il tick mergia il giro che passa
rilascia: major

**Stato:** proposto il 25/10 con `ADR-0033`; **non letto**, **non in coda**. Entra dopo `PBI-528`.
Dichiara `rilascia: major` (decisione 5): il tag è la `v1.0.0`, e il merge di questa PR dice che
Francesco vuole che lo sia.

## Direttiva

Il merge delle PR dei giri passa al tick, alle condizioni di `ADR-0033`: verificabili in codice,
una riga nel log e un commento sulla PR, niente modello. Restano a una persona i casi che l'ADR
elenca. Il tick non ha mai mergiato niente: oggi legge `MERGED` per spegnere la voce, rilasciare e
pinnare, e lì non cambia nulla.

**Scope**

- `tools/asdlc/coda.py` — `passo_del_merge(repo)`, chiamato nel tick **prima** di
  `passo_di_rilascio()`: la lettura delle PR aperte (`gh pr list --state open --json
  number,title,headRefName,files,statusCheckRollup,mergeable`), le sei condizioni, `gh pr merge
  --merge`, `gh pr comment`, le righe del log. `RE_RILASCIA` e `prossimo_tag()` accettano `major`.
- `tools/asdlc/runner.py` — niente, se `percorsi_dello_scope()` e `criteri_del_pbi()` bastano da
  `coda.py` (che già importa `asdlc_runner`).
- `backlog/CODA.md` (testa) e `README.md` — il merge del tick, nello stesso commit del codice.
- `template/backlog/CODA.md` — la stessa frase.
- `tools/tests/test_asdlc_coda.py` — i test dei criteri, col `gh` finto dei test del pin.
- `backlog/PBI-530-il-tick-mergia-il-giro-che-passa.md` — questo file, per la spunta.
- **Fuori scope:** il bump di `pyproject.toml`; il pin senza `attende:`; l'agente Merger; una issue
  per le PR che attendono una persona (è il canale di `PBI-525` e si può aggiungere dopo).

Il PBI tocca `coda.py`, che il tick lancia: il tick gira **installato** (`ADR-0026`) e vede il passo
nuovo solo al tag successivo.

## ✅ Deciso

1. **Le condizioni sono quelle di `ADR-0033`, decisione 1**, nell'ordine scritto lì; la prima che
   manca dà il motivo nel log, e le altre non si guardano.
2. **Il file del PBI alla testa della PR** si legge con `git show origin/<ramo>:<percorso>` dopo
   il `fetch` che il tick già fa. Il rapporto del giro è l'ultimo in `runs/` per quel PBI, come lo
   trova `chiudi_giro.ultimo_rapporto()`.
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
- Bloccato da: `PBI-528` (il rilascio dalla PR giusta), `PBI-527` (la marca `(a vista)` nel codice:
  senza, la condizione si legge lo stesso con la stessa regex, ma la regola deve esistere prima).
- Blocca: nessuno.

## Contesto
- `decisions/ADR-0033-il-merge-di-un-giro-e-del-tick.md` — le condizioni e le quattro domande.
- `tools/asdlc/coda.py`: il tick, `passo_di_rilascio()`, `passo_del_pin()`, `pbi_nominato()`,
  `RE_RAMO_PR`, `tocca_codice()`, `LIMITE_FILE`, `ci_verde()`, `RE_RILASCIA`, `prossimo_tag()`.
- `tools/asdlc/runner.py`: `percorsi_dello_scope()`, `criteri_del_pbi()`, `RE_CRITERIO`; il
  rapporto del giro (`apri_rapporto()`, `Esito.critic_saltato`).
- `tools/asdlc/chiudi_giro.py`: `ultimo_rapporto()`.
- `tools/tests/test_asdlc_coda.py`: i test del rilascio e del pin col `gh` finto.

## Verifica
- [ ] **Una PR che passa tutte le condizioni si mergia, e il tick lo dice.** Repository di prova con
      `PBI-7` in coda, un rapporto `fatto` con Critic girato, il file del PBI tutto `[x]`, `gh` finto
      che rende una PR su `pbi/pbi-7` con CI `SUCCESS`, `MERGEABLE` e `files` dentro lo Scope:
      `passo_del_merge()` chiama `gh pr merge 1 --merge`, poi `gh pr comment`, e rende
      `merge: PBI-7 #1`. Rosso su `main`: `passo_del_merge` non esiste.
- [ ] **Ogni condizione che manca lascia la PR a una persona, col motivo.** Parametrico, un id per
      caso, sullo stesso scenario con una sola cosa cambiata: ramo non `pbi/`; rapporto con
      `critic_saltato`; esito `intento`; CI `FAILURE`; `CONFLICTING`; un criterio `[ ]`; un criterio
      marcato a vista e spuntato; un file fuori Scope; un file in `decisions/`; `files` assente. In ogni
      caso nessun `gh pr merge`, e la riga `merge: #1 attende una persona — …` nomina la condizione.
- [ ] **`rilascia: major` dà la `v1.0.0`.** `prossimo_tag(["v0.9.2"], "major") == "v1.0.0"` e
      `rilascia_del_pbi("…\nrilascia: major\n…") == "major"`. Rosso su `main`: `RE_RILASCIA`
      accetta solo `patch|minor`.
- [ ] **Il merge viene prima del rilascio nello stesso passaggio.** Col `gh` finto che rende la PR
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
