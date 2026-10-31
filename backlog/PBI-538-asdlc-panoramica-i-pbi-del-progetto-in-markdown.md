# PBI-538: `asdlc-panoramica`, i PBI del progetto in markdown

**Stato:** proposto il 31/10 da una sessione con Francesco («un comando per avere una panoramica del
progetto con tutti i PBI, in coda, da fare e fatti, in formato .md», prima della plancia). Sprint 1
della coda di questo repository (`ADR-0034`). Letto il 31/10 (in fondo, *Protocollo*): un fermo e
quattro rilievi minori recepiti.

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
   l'uscita **2**, come lì: si riusano `stato.progetti()` e `stato.nome_di()`. `main(argv)` prende la
   lista degli argomenti come `stato.main()`.
2. **Sola lettura**, come la decisione 2 di `PBI-534`: niente lucchetto del tick, niente `fetch` che
   cambi un ramo, niente log né registro. Per ogni progetto `coda.configura()` col suo `asdlc.toml`.
3. **La forma, per un progetto:**

   ```markdown
   # <nome>

   <stato.riga(stato.stato_o_guasto(checkout))>

   ## In corso
   - **PBI-XXX** — <titolo> · criteri <x>/<y> · PR <url>, <url> (o -)
   ## In coda
   1. **PBI-XXX** — <titolo> · criteri <x>/<y>
   - ‖ <testo della barriera>
   ## Fatti
   - **PBI-XXX** — <titolo> · criteri <x>/<y>
   ## Fuori coda
   - **PBI-XXX** — <titolo> · criteri <x>/<y>
   ```

   In **ogni** sezione la riga di un PBI che ha una sezione `❓` (`coda.RE_DOMANDE`) finisce con `· ❓`.
   Più PR si separano con `, `. Una sezione vuota ha la riga `- nessuno`. Con più progetti le sezioni
   `# <nome>` si susseguono separate da una riga vuota.
4. **Da dove viene ogni sezione:**
   - **Fatti:** i PBI di `coda.pbi_mergiati()` che hanno un file in `backlog/`, in ordine di numero (un
     PBI fatto senza file non compare);
   - **In corso:** le voci di `CODA.md` non fatte che hanno un ramo su `origin`
     (`coda.pbi_con_ramo()`), con le PR aperte di `coda.pr_sul_ramo()`, `-` se non ce ne sono;
   - **In coda:** le altre voci di `CODA.md` non fatte, nell'ordine del file (`coda.leggi_voci()`),
     numerate, con le barriere al loro posto come righe `- ‖`;
   - **Fuori coda:** i file di `backlog/` col nome del modello `[backlog].file` (`CFG.backlog`, come per
     `avviso_domande()`) il cui PBI non è in `CODA.md` e non è fatto, in ordine di numero.
5. **Il titolo e i criteri vengono dal file del PBI**: il titolo è la prima riga `# PBI-XXX: <titolo>`
   senza il prefisso; i criteri sono le righe `- [x]` e `- [ ]` **della sola sezione `## Verifica`**,
   fino alla `##` seguente. Una voce di coda senza file ha il titolo `(file mancante)` e `criteri 0/0`.
6. **Un progetto che non si legge non ferma gli altri** (`ADR-0008`): la sua sezione è `# <nome>` e,
   sotto, la riga di `stato.riga()` (`<nome> · non raggiungibile — <motivo>`), senza le quattro sezioni;
   si va avanti. **`gh` o `origin` che non rispondono** non rendono il progetto non raggiungibile:
   - un `Guasto` di `pbi_mergiati()`: **Fatti** è la riga `- ? <messaggio del Guasto>` (comincia già con
     `gh non risponde`), e le voci di `CODA.md` si trattano come non fatte;
   - un `Guasto` di `pbi_con_ramo()`: **In corso** è la riga `- ? <messaggio del Guasto>`, e le voci
     vanno in **In coda**;
   - `None` da `pr_sul_ramo()`: la PR è `?`.
   L'uscita è 0.

## Dipendenze

- Bloccato da: nessuno (`PBI-534` e `PBI-535` sono in `main`). Blocca: `PBI-539`.

## Contesto

- `tools/asdlc/stato.py`: `progetti()`, `nome_di()`, `stato_o_guasto()`, `riga()`, `main()` (il
  modello degli argomenti e delle uscite).
- `tools/asdlc/coda.py`: `configura()`, `leggi_voci()`, `pbi_mergiati()`, `pbi_con_ramo()`,
  `pr_sul_ramo()`, `RE_DOMANDE`, `avviso_domande()` (la ricerca del file del PBI).
- `tools/tests/test_asdlc_stato.py` — come si costruiscono il repository temporaneo e l'`origin`
  locale, e il `gh` finto: un monkeypatch di `coda.esegui`, quindi i test chiamano `panoramica.main()`
  **nello stesso processo**, non `python -m` in un sottoprocesso (andrebbe al `gh` vero).

## Verifica

- [ ] **Un progetto, con le quattro sezioni, i criteri e la `❓`.** Repository temporaneo con `CODA.md` =
      `PBI-1`, `PBI-2`, `‖ prova`, `PBI-3`, `PBI-5`; i file di `PBI-1`…`PBI-5`; un ramo `pbi/pbi-5` su
      `origin`; un `gh` finto con una PR mergiata che nomina `PBI-1` e tocca `tools/`, e una PR aperta sul
      ramo di `PBI-5`. `PBI-2` ha tre righe di criterio in `## Verifica`, due spuntate, e una `- [ ]` in
      un'altra sezione; `PBI-4` ha un'intestazione `## ❓ Domande`. `panoramica.main(["--repo", <tmp>])`
      esce 0; `## Fatti` ha `PBI-1` col suo titolo; `## In corso` ha `PBI-5` con l'URL della PR;
      `## In coda` ha `1. **PBI-2**` con `criteri 2/3`, `- ‖ prova`, `2. **PBI-3**` in quest'ordine;
      `## Fuori coda` ha `PBI-4` con la riga che finisce in `· ❓`. Rosso su `main`: il modulo non c'è.
- [ ] **Tutti i progetti, e uno illeggibile non ferma gli altri.** È una **guardia** (la decisione 1 si
      può scrivere già nel GREEN del criterio 1): `HOME` in `tmp_path` con `progetti.toml` di due progetti
      validi e un percorso che non esiste, in mezzo; `panoramica.main([])` dà tre sezioni `# `
      nell'ordine del file, quella di mezzo con `non raggiungibile`, uscita 0.
      `Guardia-su: tools/asdlc/panoramica.py::main`.
- [ ] **`gh` e `origin` che non rispondono non fermano la panoramica.** È una **guardia** (decisione 6):
      con il `gh` finto che esce 1 su `pr list --state merged`, `## Fatti` ha `- ? gh non risponde` e
      `PBI-1` è in `## In coda`; con `git ls-remote` che esce 1, `## In corso` ha `- ? git non parla con`;
      uscita 0 in tutti e due. `Guardia-su: tools/asdlc/panoramica.py::main`.

**Non regressione:**
- Dopo `asdlc-panoramica` `git status --porcelain`, `runs/coda.log` e il registro del progetto sono
  identici a prima. È una **guardia**: su `main` il comando non c'è.
  `Guardia-su: tools/asdlc/panoramica.py::main`.
- `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura

Si può scegliere senza chiedere: i nomi delle funzioni private, l'ordine delle funzioni nel modulo.
Si chiama `fermati`: se una funzione di `coda.py` o `stato.py` nominata qui non c'è o ha un'altra firma;
se servisse cambiare `coda.py` o `stato.py`.

**Lettura del 31/10** (Lettore separato, sola lettura, sul ramo `c95c1ea`): un fermo — i criteri 2, 3 e 4
della prima stesura potevano nascere verdi dopo un GREEN del criterio 1 che seguisse le decisioni; ora il
criterio 1 li comprende e i due casi di guasto sono guardie — e quattro minori: la riga del progetto non
raggiungibile (decisioni 3 e 6), il `gh non risponde` ripetuto (decisione 6), il `gh` finto che non arriva
a un sottoprocesso (*Contesto*), il separatore delle PR, la `❓` in ogni sezione e il modello del nome
del file (decisioni 3 e 4).
