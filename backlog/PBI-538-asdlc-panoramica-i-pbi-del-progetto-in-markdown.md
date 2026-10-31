# PBI-538: `asdlc-panoramica`, i PBI del progetto in markdown

**Stato:** proposto il 31/10 da una sessione con Francesco («un comando per avere una panoramica del
progetto con tutti i PBI, in coda, da fare e fatti, in formato .md», prima della plancia). Sprint 1
della coda di questo repository (`ADR-0034`).

## Direttiva

`asdlc-stato` (`PBI-534`) dice in una riga cosa fa il tick adesso. Non dice cosa c'è dietro: quali PBI
sono fatti, quali aspettano in coda, quali sono scritti e fuori coda. Il 31/10, per rispondere a «quanti
PBI ci sono in coda», si è dovuto leggere `CODA.md` e i file di `backlog/` di cinque repository con
uno script a mano, e il conto dei criteri non spuntati sbagliava i PBI fatti con una verifica a vista.

`asdlc-panoramica` stampa in markdown, per ogni progetto, i PBI divisi in **in corso**, **in coda**,
**fatti** e **fuori coda**, con il titolo e i criteri spuntati. È di **sola lettura** come
`asdlc-stato`, e prende i suoi dati dalle stesse funzioni del tick: non è una seconda verità.

**Scope**

- `tools/asdlc/panoramica.py` — nuovo: il markdown di un progetto e di tutti.
- `tools/pyproject.toml` — `asdlc-panoramica = "asdlc.panoramica:main"` in `[project.scripts]`.
- `README.md` — come si usa, accanto ad `asdlc-stato`, nello stesso commit del codice.
- `tools/tests/test_asdlc_panoramica.py` — nuovo: i test dei criteri, con `gh` finto e nessuna rete.
- `backlog/PBI-538-asdlc-panoramica-i-pbi-del-progetto-in-markdown.md` — questo file, per la spunta.
- **Fuori scope:** `tools/asdlc/stato.py` e `tools/asdlc/coda.py` non cambiano (si importano); gli
  sprint (`PBI-539`, che li aggiunge a questo comando); scrivere un file (la panoramica va su stdout:
  chi la vuole in un file la redirige); una plancia o un'API.

## ✅ Deciso

1. **Gli stessi argomenti di `asdlc-stato`:** senza argomenti tutti i progetti di
   `~/.config/asdlc/progetti.toml`, nell'ordine del file; con un nome quello; `--repo <percorso>` uno
   senza l'elenco. Un elenco che manca o non si legge, o un nome che non c'è, è un messaggio su stderr e
   l'uscita **2**, come lì: si riusano `stato.progetti()` e `stato.nome_di()`.
2. **Sola lettura**, come la decisione 2 di `PBI-534`: niente lucchetto del tick, niente `fetch` che
   cambi un ramo, niente log né registro. Per ogni progetto `coda.configura()` col suo `asdlc.toml`.
3. **La forma, per un progetto:**

   ```markdown
   # <nome>

   <la riga di `asdlc-stato` di quel progetto, `stato.riga(stato.stato_o_guasto(checkout))`>

   ## In corso
   - **PBI-XXX** — <titolo> · criteri <x>/<y> · PR <url o ->
   ## In coda
   1. **PBI-XXX** — <titolo> · criteri <x>/<y>
   - ‖ <testo della barriera>
   ## Fatti
   - **PBI-XXX** — <titolo> · criteri <x>/<y>
   ## Fuori coda
   - **PBI-XXX** — <titolo> · criteri <x>/<y> · ❓
   ```

   Una sezione vuota ha la riga `- nessuno`. Con più progetti le sezioni `# <nome>` si susseguono
   separate da una riga vuota.
4. **Da dove viene ogni sezione:**
   - **Fatti:** i PBI di `coda.pbi_mergiati()` che hanno un file in `backlog/`, in ordine di numero;
   - **In corso:** le voci di `CODA.md` non fatte che hanno un ramo su `origin`
     (`coda.pbi_con_ramo()`), con le PR aperte di `coda.pr_sul_ramo()`, `-` se non ce ne sono;
   - **In coda:** le altre voci di `CODA.md` non fatte, nell'ordine del file (`coda.leggi_voci()`),
     numerate, con le barriere al loro posto come righe `- ‖`;
   - **Fuori coda:** i file `backlog/PBI-*.md` il cui PBI non è in `CODA.md` e non è fatto, in ordine
     di numero.
5. **Il titolo e i criteri vengono dal file del PBI** (`CFG.backlog`, la stessa ricerca di
   `coda.avviso_domande()`): il titolo è la prima riga `# PBI-XXX: <titolo>` senza il prefisso; i
   criteri sono le righe `- [x]` e `- [ ]` **della sola sezione `## Verifica`**, fino alla `##`
   seguente. `❓` compare se `coda.RE_DOMANDE` trova una sezione `❓` nel file. Una voce di coda senza
   file ha il titolo `(file mancante)`.
6. **Un progetto che non si legge non ferma gli altri** (`ADR-0008`): la sua sezione è `# <nome>` e la
   riga `non raggiungibile — <motivo>`, e si va avanti. **`gh` che non risponde** non rende il progetto
   non raggiungibile: con un `Guasto` di `pbi_mergiati()` la sezione **Fatti** è la riga
   `- ? gh non risponde — <motivo>` e le voci di `CODA.md` si trattano come non fatte; con `None` da
   `pr_sul_ramo()` la PR è `?`. Con un `Guasto` di `pbi_con_ramo()` (`origin` che non risponde) la
   sezione **In corso** è la riga `- ? origin non risponde — <motivo>` e le voci vanno in **In coda**.
   L'uscita è 0.

## Dipendenze

- Bloccato da: nessuno (`PBI-534` e `PBI-535` sono in `main`). Blocca: `PBI-539`.

## Contesto

- `tools/asdlc/stato.py`: `progetti()`, `nome_di()`, `stato_o_guasto()`, `riga()`, `main()` (il
  modello degli argomenti e delle uscite).
- `tools/asdlc/coda.py`: `configura()`, `leggi_voci()`, `pbi_mergiati()`, `pbi_con_ramo()`,
  `pr_sul_ramo()`, `RE_DOMANDE`, `avviso_domande()` (la ricerca del file del PBI).
- `tools/tests/test_asdlc_stato.py` — come si costruiscono il repository temporaneo, l'`origin`
  locale e il `gh` finto.

## Verifica

- [ ] **Le quattro sezioni coi PBI giusti.** Repository temporaneo con `CODA.md` = `PBI-1`, `PBI-2`,
      `‖ prova`, `PBI-3`, i file di `PBI-1`…`PBI-4`, nessun ramo su `origin`, e un `gh` finto con una PR
      mergiata che nomina `PBI-1` e tocca `tools/`: `python -m asdlc.panoramica --repo <tmp>` esce 0;
      `## Fatti` ha `PBI-1` col suo titolo, `## In coda` ha `1. **PBI-2**`, `- ‖ prova`, `2. **PBI-3**`
      in quest'ordine, `## Fuori coda` ha `PBI-4`, `## In corso` ha `- nessuno`. Rosso su `main`: il
      modulo non c'è.
- [ ] **Un PBI col ramo è in corso, con la PR.** Stesso repository con un ramo `pbi/pbi-2` su `origin`
      e il `gh` finto che dà una PR aperta su quel ramo: `PBI-2` è in `## In corso` con l'URL, e non è
      in `## In coda`. Rosso dopo il criterio 1: nessun ramo lo chiede.
- [ ] **I criteri si contano nella sola Verifica, e la `❓` si vede.** Un PBI con tre righe di criterio
      in `## Verifica`, due spuntate, e una riga `- [ ]` in un'altra sezione: `criteri 2/3`. Un PBI con
      un'intestazione `## ❓ Domande`: la sua riga finisce con `· ❓`. Rosso dopo i criteri 1-2.
- [ ] **Tutti i progetti, e uno illeggibile non ferma gli altri.** `HOME` in `tmp_path` con
      `progetti.toml` di due progetti validi e un percorso che non esiste, in mezzo: tre sezioni `# `
      nell'ordine del file, quella di mezzo con `non raggiungibile`, uscita 0. Rosso dopo i criteri 1-3.
- [ ] **`gh` che non risponde non ferma la panoramica.** Il `gh` finto esce 1: `## Fatti` ha
      `- ? gh non risponde`, `PBI-1`, `PBI-2` e `PBI-3` sono in `## In coda`, uscita 0. Rosso dopo i
      criteri 1-4.

**Non regressione:**
- Dopo `asdlc-panoramica` `git status --porcelain`, `runs/coda.log` e il registro del progetto sono
  identici a prima. È una **guardia**: su `main` il comando non c'è.
  `Guardia-su: tools/asdlc/panoramica.py::main`.
- `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura

Si può scegliere senza chiedere: i nomi delle funzioni private, l'ordine delle funzioni nel modulo.
Si chiama `fermati`: se una funzione di `coda.py` o `stato.py` nominata qui non c'è o ha un'altra firma;
se servisse cambiare `coda.py` o `stato.py`.
