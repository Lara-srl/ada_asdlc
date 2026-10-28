# PBI-534: `asdlc-stato`, lo stato dei PBI a comando

**Stato:** proposto il 28/10 da Francesco («un comando per vedere lo stato, così non cerco parole nei
log ogni volta»); accodato il 28/10 dopo la barriera `v1.0.0`. **Da leggere con la lettura
avversariale prima di togliere la barriera.**

## Direttiva

Per sapere a che punto sono i PBI oggi si legge `runs/coda.log` di ogni progetto, `runs/tempi.csv`,
`gh pr list`, e si lancia `asdlc-coda --dry-run` un repo alla volta. Il 28/10 una barriera ha scritto
la stessa riga per venti ore e due checkout sono rimasti `non allineato` senza che si vedesse.

`asdlc-stato` è un comando di **sola lettura** che mostra, per ogni progetto, ciò che il tick vede
adesso. Non decide niente di suo: usa `decidi()` e `ultimo_esito()` di `coda.py`, così dice
esattamente ciò che farebbe il tick e non è una seconda verità. È anche la base di `PBI-536`, che lo
chiama da Slack.

**Scope**

- `tools/asdlc/stato.py` — nuovo: legge l'elenco dei progetti e dà, per ognuno, un dato (decisione,
  voce corrente, ultimo esito, PR aperta, barriera, pausa, versione installata e versione del pin).
- `tools/pyproject.toml` — `asdlc-stato = "asdlc.stato:main"` in `[project.scripts]`.
- `README.md` — come si usa e dove sta l'elenco dei progetti, nello stesso commit del codice.
- `tools/tests/test_asdlc_stato.py` — nuovo: i test dei criteri, con `gh` finto e nessuna rete.
- `backlog/PBI-534-asdlc-stato-lo-stato-dei-pbi-a-comando.md` — questo file, per la spunta.
- **Fuori scope:** scrivere qualsiasi cosa nei progetti; la pausa per progetto (`PBI-535`, che la
  aggiunge a questo comando); un'API HTTP o una plancia (non servono: Slack e il terminale bastano).

## ✅ Deciso

1. **L'elenco dei progetti sta in `~/.config/asdlc/progetti.toml`**, fuori dai repository (è di
   macchina, come la pausa): una tabella `[progetti]` con `nome = "/percorso/del/checkout"`. Oggi
   quell'elenco esiste solo nel `crontab`. `asdlc-stato` senza argomenti li mostra tutti, con un nome
   mostra uno; `--repo <percorso>` ne mostra uno senza passare dal file.
2. **Sola lettura.** Non prende il lucchetto del tick, non fa `fetch` che cambi un ramo locale, non
   scrive il log né il registro. Uno stato che chiede il lucchetto si fermerebbe quando serve di più.
3. **Una riga per progetto**, in testo: `<nome> · <decisione> · <PBI o barriera> · <ultimo esito> ·
   PR <numero o -> · pin <tag> installato <tag>`. Con `--json` un oggetto per progetto con le stesse
   chiavi (`progetto`, `decisione`, `voce`, `esito`, `pr`, `pausa`, `installato`, `pin`).
4. **Un progetto che non si legge non ferma gli altri** (`ADR-0008`): una riga «<nome> · non
   raggiungibile — <motivo>» e si va avanti. Il codice d'uscita è 0.
5. **Il nome della decisione è quello di `racconta()`**, non un'altra formula: niente da tenere
   allineato.

## Dipendenze

- Bloccato da: nessuno. `PBI-535` aggiunge la pausa per progetto a questo comando; `PBI-536` lo usa.
- Blocca: `PBI-536`.

## Contesto

- `tools/asdlc/coda.py`: `decidi()`, `racconta()`, `ultimo_esito()`, `pausa()`, `firme()`.
- `backlog/PBI-533-le-notifiche-del-tick-su-slack.md` (stessa regola per i segreti e i file di
  macchina), `backlog/PBI-510-il-battito-del-tick.md`.

## Verifica

- [ ] **Il comando mostra lo stato di un progetto con la decisione del tick.** Repository temporaneo
      con una coda e un `gh` finto; `python -m asdlc.stato --repo <tmp>` esce 0 e stampa una riga
      che contiene il nome, la voce e la stessa decisione che `racconta(decidi(...))` dà sullo stesso
      repo. Rosso su `main`: il modulo non c'è, il comando esce con un codice diverso da 0.
- [ ] **`--json` dà gli oggetti con le chiavi fisse.** Stesso repo: l'uscita è JSON valido e ha le
      chiavi della decisione 3. Rosso su `main`.
- [ ] **Senza argomenti mostra tutti i progetti del file.** `HOME` spostato in `tmp_path` con due
      progetti in `progetti.toml`: due righe, nell'ordine del file. Rosso su `main`.
- [ ] **Un progetto illeggibile non ferma gli altri.** Un percorso che non esiste e uno valido: la
      riga «non raggiungibile» e la riga dell'altro, uscita 0. Rosso su `main`.
- [ ] **Mostra una barriera e la differenza fra pin e versione installata.** Coda ferma su una
      barriera, firma scritta diversa dal pin: la riga porta il testo della barriera e i due tag.
      Rosso su `main`.

**Non regressione:**
- Dopo `asdlc-stato` `git status --porcelain` e il registro del progetto sono identici a prima.
  È una **guardia**: su `main` il comando non c'è. `Guardia-su: tools/asdlc/stato.py::main`.
- `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura

Si può scegliere senza chiedere: i nomi delle funzioni, il separatore e l'ordine delle colonne
purché portino quanto la decisione 3 elenca, il formato dell'ora. Si chiama `fermati`: se `decidi()`
non si può chiamare senza scrivere nel log o prendere il lucchetto; se serve una dipendenza esterna.
