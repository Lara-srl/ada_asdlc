# PBI-534: `asdlc-stato`, lo stato dei PBI a comando

**Stato:** proposto il 28/10 da Francesco («un comando per vedere lo stato, così non cerco parole nei
log ogni volta»); accodato il 28/10 dopo la barriera `v1.0.0`. Letto il 30/10 col Lettore (in fondo,
*Protocollo*): un fermo e sei rilievi minori recepiti.

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
   macchina, come la pausa): `checkout = ["/percorso/del/checkout", …]`. **Il nome di un progetto è il
   nome della cartella del checkout** (`Path(percorso).name`), lo stesso che usa `PBI-533` (decisione
   7) e che `PBI-536` riceve nei comandi: un nome solo, nessuna tabella da tenere allineata. Oggi
   quell'elenco esiste solo nel `crontab`. `asdlc-stato` senza argomenti li mostra tutti, nell'ordine
   del file; con un nome mostra quello; `--repo <percorso>` ne mostra uno senza passare dal file. Il
   file che manca o non si legge è un messaggio su stderr e l'uscita **2**; un nome che non c'è, lo
   stesso.
2. **Sola lettura.** Non prende il lucchetto del tick, non fa `fetch` che cambi un ramo locale, non
   scrive il log né il registro. Uno stato che chiede il lucchetto si fermerebbe quando serve di più.
   La prova istantanea del lucchetto del runner dentro `decidi()` (`giro_in_corso()`) è ammessa, come
   nel `--dry-run`. `coda` ha le costanti di un progetto solo: per ogni progetto si chiama
   `coda.configura()` con l'`asdlc.toml` di quel checkout, prima di `decidi()` e di `firme()`.
3. **Una riga per progetto**, in testo: `<nome> · <decisione> · <PBI o barriera> · <ultimo esito> ·
   PR <url, `?` se `gh` non risponde, o -> · pin <tag> installato <tag>`. L'ultimo esito è `stato` e
   `motivo` del rapporto (`ultimo_esito()`), o `-`. Con `--json` un oggetto per progetto con le stesse
   chiavi (`progetto`, `decisione`, `voce`, `esito`, `pr`, `pausa`, `allineato`, `installato`, `pin`).
4. **Un progetto che non si legge non ferma gli altri** (`ADR-0008`): una riga «<nome> · non
   raggiungibile — <motivo>» e si va avanti. Il codice d'uscita è 0.
5. **Il nome della decisione è quello di `racconta()`**, non un'altra formula: niente da tenere
   allineato.
6. **La decisione è quella che il tick prenderebbe adesso, nell'ordine del tick.** Se c'è la pausa
   (`pausa()`), la decisione è `in pausa: <riga>`; se il checkout non è sul ramo di `BASE` (`git branch
   --show-current`, in sola lettura: niente `allinea()`, che fa `fetch` e `merge`), è `non allineato: il
   checkout … è su «…», non su …`, la stessa frase del tick, e `allineato` è falso; altrimenti
   `racconta(decidi(...))`. Così il caso della *Direttiva* si vede.
7. **Il pin e l'installato sono tag.** Con un `installa` URL il pin è il `vX.Y.Z` dopo l'ultima `@`
   (la forma di `RE_PIN_URL`, `config.py`), e l'installato lo stesso dalla firma scritta, o `-` se non
   c'è. Con un `installa` cartella si stampa la cartella per tutti e due. Un `Guasto` di `firme()` non
   rende il progetto «non raggiungibile»: va nella colonna, `pin ? (<motivo>)`.

## Dipendenze

- Bloccato da: nessuno. `PBI-535` aggiunge la pausa per progetto a questo comando; `PBI-536` lo usa.
- Blocca: `PBI-536`.

## Contesto

- `tools/asdlc/coda.py`: `configura()`, `decidi()`, `racconta()`, `ultimo_esito()`, `pausa()`,
  `firme()`, `pr_sul_ramo()`, `allinea()` (la frase del non allineato).
- `tools/tests/dati/progetto/asdlc.toml` ha `installa = "./tools"`: i test dei criteri 1, 2 e 5
  scrivono un `asdlc.toml` con un `installa` URL.
- `backlog/PBI-533-le-notifiche-del-tick-su-slack.md` (stessa regola per i segreti e i file di
  macchina), `backlog/PBI-510-il-battito-del-tick.md`.

## Verifica

- [ ] **Il comando mostra lo stato di un progetto con la decisione del tick.** Repository temporaneo
      con una coda, un `origin` locale col ramo del PBI e un `gh` finto senza PR;
      `python -m asdlc.stato --repo <tmp>` esce 0 e stampa una riga che contiene il nome (la cartella),
      la voce e la stessa decisione che `racconta(decidi(...))` dà sullo stesso repo. Con la coda
      ferma su una barriera la riga porta `barriera: <testo>`: è lo stesso `racconta()`, e sta in
      questo criterio. Rosso su `main`: il modulo non c'è, il comando esce con un codice diverso da 0.
- [ ] **`--json` dà gli oggetti con le chiavi fisse.** Stesso repo: l'uscita è JSON valido e ha le
      chiavi della decisione 3; `pin` e `installato` possono essere `null` finché non c'è il criterio
      5. Rosso su `main`.
- [ ] **Senza argomenti mostra tutti i progetti del file.** `HOME` spostato in `tmp_path` con due
      progetti in `progetti.toml`: due righe, nell'ordine del file. Rosso su `main`.
- [ ] **Un progetto illeggibile non ferma gli altri.** Un percorso che non esiste e uno valido: la
      riga «non raggiungibile» e la riga dell'altro, uscita 0. Rosso su `main`.
- [ ] **Mostra la differenza fra pin e versione installata.** `installa` URL `…@v1.1.0`, firma
      scritta `…@v1.0.0`: la riga porta `pin v1.1.0 installato v1.0.0`. Rosso dopo i criteri 1-4:
      nessuno di loro chiede i tag.
- [ ] **La pausa e il checkout fuori dal ramo di `BASE` si vedono, come li vede il tick.** Con
      `HOME` in `tmp_path` e `~/asdlc-tick.pausa` scritto, la decisione è `in pausa: <riga>`. Senza
      pausa e col repository temporaneo su un ramo `docs/x`, la riga dice `non allineato` col nome del
      ramo, `--json` ha `allineato` falso, e il checkout resta su `docs/x`. Un caso per riga. Rosso
      dopo i criteri 1-5: la decisione è quella di `decidi()`.

**Non regressione:**
- Dopo `asdlc-stato` `git status --porcelain` e il registro del progetto sono identici a prima.
  È una **guardia**: su `main` il comando non c'è. `Guardia-su: tools/asdlc/stato.py::main`.
- `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura

Si può scegliere senza chiedere: i nomi delle funzioni, il separatore e l'ordine delle colonne
purché portino quanto la decisione 3 elenca, il formato dell'ora. Si chiama `fermati`: se `decidi()`
non si può chiamare senza scrivere nel log o prendere il lucchetto **del tick**; se serve una
dipendenza esterna.

**Lettura del 30/10** (Lettore separato, sola lettura, su `main` `13d6641`): un fermo — la forma del
pin e dell'installato, e un `Guasto` di `firme()` (decisione 7) — e sei rilievi minori: il criterio 5
coperto in parte dall'1 e dal 2 (la barriera nel criterio 1, i tag nel 5); il `non allineato` della
*Direttiva* che `decidi()` non vede (decisione 6, criterio 6); la PR come URL; il nome del progetto,
il file assente e il campo dell'esito (decisioni 1 e 3); il lucchetto del tick e `configura()` per
progetto (decisione 2); il ramo che viene dall'`origin` e non da `gh` (criterio 1).
