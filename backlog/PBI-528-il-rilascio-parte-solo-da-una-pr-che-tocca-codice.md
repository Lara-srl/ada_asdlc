# PBI-528: il rilascio parte solo da una PR che tocca codice
rilascia: patch

**Stato:** letto il 26/10 col Lettore (in fondo), **in coda** dopo la barriera della `v0.9.0` e prima di `PBI-530` (Francesco, 26/10). ~~Entra dopo la barriera della `v0.8.0`~~ (la `v0.8.0` è il tag fantasma di questo PBI; la barriera è la `v0.9.0`)
(che in realtà sarà `v0.9.0`: sotto), insieme a `PBI-529`.

## Direttiva

Il 25/10 alle 23:25 il tick di `ada_asdlc` ha scritto `rilascio: PBI-525 → v0.8.0` e ha messo il tag
su `297c1be`, il merge della PR #98. Quella PR **accoda** 524 e 525 e tocca solo `backlog/`; il codice
di `PBI-525` non esiste ancora, il giro di `PBI-524` è partito nello stesso tick. Il tag `v0.8.0` ha lo
stesso codice della `v0.7.0` e `tools/pyproject.toml` dice ancora `0.7.0`. Non si cancella: il tick lo
rifarebbe al passaggio dopo, perché la causa è nel passo. La release dei fix sarà il tag successivo,
`v0.9.0` per `prossimo_tag()`.

La causa: `passo_di_rilascio()` (`tools/asdlc/coda.py`) prende ogni PR mergiata che **nomina** un PBI
(`pbi_nominato()`: titolo `PBI-XXX:` o ramo `pbi/pbi-XXX`) e, se il file del PBI dichiara
`rilascia:`, tagga. La coda, per spegnere una voce, chiede anche che la PR abbia cambiato qualcosa
fuori da `backlog/` (`tocca_codice()`, difetto della #215 del 09/09). Il rilascio quella domanda non la
fa. Qui la PR #93, che ha scritto il file di 525 col titolo `PBI-525: …`, bastava.

Il sesto fermo meccanico della settimana; **finché non è in `main`**, una PR che accoda o scrive un PBI
non si intitola `PBI-XXX:` e non nasce da un ramo `pbi/` (regola scritta in `backlog/README.md` in
questo PBI).

**Scope**

- `tools/asdlc/coda.py` — `passo_di_rilascio()`: la PR deve passare `tocca_codice()`, e la chiamata a
  `gh pr list` chiede anche `files`, come fa la coda. Una PR che nomina il PBI e non tocca codice si
  salta in silenzio, non è un avviso.
- `backlog/README.md` — la regola sui titoli delle PR che accodano, con il caso del 25/10.
- `tools/tests/test_asdlc_rilascio.py` — i test dei criteri, accanto a quelli di R8 (`PBI-509`), con la classe
  `Mondo` e la fixture `mondo` (origin bare, checkout e `gh` finto) che stanno lì.
- `backlog/PBI-528-il-rilascio-parte-solo-da-una-pr-che-tocca-codice.md` — questo file, per la spunta.
- **Fuori scope:** il bump di `tools/pyproject.toml` al tag (oggi è una PR a mano, `build/versione-…`,
  come per `v0.6.0` e `v0.7.0`; farlo fare al tick senza scrivere su `main` è un altro PBI, e serve
  prima del merge automatico); cancellare o spostare `v0.8.0`; `pbi_nominato()` e la coda.

## ✅ Deciso

1. **La stessa regola della coda.** La PR che fa partire un rilascio è la PR che spegne la voce: nomina
   il PBI **e** tocca codice. Non si inventa un terzo criterio (criteri spuntati, ramo del runner): la
   coda non lo chiede, e due regole diverse per «la PR del PBI» sono il difetto di oggi.
2. **`v0.8.0` resta.** Un tag pubblicato non si riscrive; nessun progetto lo pinna, e il prossimo
   rilascio lo scavalca.

## Dipendenze
- Bloccato da: nessuno (ma dopo la barriera della `v0.9.0`, per non cambiare `coda.py` sotto il tick).
- Blocca: il merge automatico (`PBI-530`), che non può esistere con un rilascio che parte dalla PR sbagliata.

## Contesto
- `tools/asdlc/coda.py`: `passo_di_rilascio()`, `pbi_nominato()`, `tocca_codice()`, `LIMITE_FILE`, e il
  punto in cui la coda le usa insieme (riga ~352).
- `runs/cron.log` del 25/10, 23:25; il tag `v0.8.0` su `297c1be`.
- `tools/tests/test_asdlc_rilascio.py`: i test di R8 (`PBI-509`) col `gh` finto, `class Mondo` e la fixture `mondo`
  (righe 65-115).

## Verifica
- [ ] **Una PR mergiata che nomina il PBI e tocca solo `backlog/` non rilascia.** Col `gh` finto: una
      PR `PBI-7: …` con `files` tutti sotto `backlog/`, e il file di `PBI-7` con `rilascia: minor`:
      `passo_di_rilascio()` non chiama `git tag` e non rende nessuna riga. Rosso su `main`: oggi tagga.
- [ ] **La stessa PR con un file fuori da `backlog/` rilascia come prima.** È la **guardia** del
      comportamento di `PBI-509`: lo stesso scenario con `tools/asdlc/x.py` fra i `files` tagga e rende
      `rilascio: PBI-7 → …`. Un `gh` che non rende `files` conta come «tocca», come in `tocca_codice()`.

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde; i test di `PBI-509` e `PBI-512`
non cambiano.

## Protocollo di rifinitura
Si può scegliere senza chiedere: se `files` entra nella stessa chiamata a `gh pr list` o in una seconda.
Si chiama `fermati`: se `tocca_codice()` ha bisogno di un campo che `gh pr list --json` non dà per le
PR mergiate.

## La lettura del 26/10

`asdlc-runner PBI-528 --preverifica --lettore` (runner `v0.7.0`), su `main` `3acb74d`, in un albero usa e
getta. Un rilievo, verificato nel codice e recepito nello Scope e nel Contesto: i test di R8 e il `gh`
finto del rilascio (`class Mondo`, fixture `mondo`) stanno in `tools/tests/test_asdlc_rilascio.py`, non in
`test_asdlc_coda.py`, che del rilascio non ha niente. Il Lettore ha controllato e confermato il resto:
`PBI-7` corrisponde a `RE_TITOLO_PR`, il `gh` finto di oggi non rende `files` (la guardia del criterio 2
e i test di `PBI-509` restano verdi), `files` si chiede già per le PR mergiate in `coda.py`. La sonda del
criterio 1 è uscita `guasto` (il gate nell'albero usa e getta, `PBI-529`): il rosso resta dichiarato.
