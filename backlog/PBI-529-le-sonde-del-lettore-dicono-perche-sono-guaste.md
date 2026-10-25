# PBI-529: le sonde del Lettore girano come i gate, e un guasto dice perché

**Stato:** proposto il 25/10; **non letto**, **non in coda**. Entra dopo la barriera della `v0.8.0`,
con `PBI-528`.

## Direttiva

Il 25/10 `asdlc-runner PBI-524 --preverifica --lettore` e lo stesso su `PBI-525` (runner `v0.7.0`,
lanciati a mano da `/home/laisdev/ada_asdlc`) hanno avuto **tutte e sei le sonde `guasto`**:
`avviso: sonda del criterio N: gate guasto`, e nient'altro. Il Lettore ha scritto sei test, il runner
non li ha potuti eseguire, e il rapporto non dice perché. I criteri di 524 e 525 sono entrati in coda
con il rosso dichiarato e non provato, che è esattamente ciò che `ADR-0031` voleva evitare.

Due difetti:

1. **L'avviso tace la causa.** `esegui_le_sonde()` cattura `GuastoDelGate` e scrive `gate guasto`;
   il messaggio dell'eccezione, che ha il comando, la cartella e la coda dell'output, non va né
   nell'avviso né nel rapporto. Senza, un guasto delle sonde si indaga a mano o non si indaga.
2. **L'albero usa e getta non ha l'ambiente dei gate.** Causa probabile, da provare nel RED: l'albero
   del Lettore (`worktree_usa_e_getta(base)`, in `/tmp`) non ha `.venv`, e `[ambiente].prestiti` di
   questo repository è vuoto; `tools/tests/conftest.py` cerca `pytest` in `.venv/bin` dell'albero e sul
   `PATH` (`eseguibili_mancanti()`) e, se non lo trova, esce con «ambiente mancante: `pytest`». Lo stesso
   errore si riproduce in un worktree del repository senza `.venv`, e sparisce con `.venv/bin` sul
   `PATH`. Il gate del rosso non lo soffre perché gira dopo `venv_sul_path()`; la pre-verifica a mano
   e nel giro vanno verificate una per una.

**Scope**

- `tools/asdlc/runner.py` — `esegui_le_sonde()`: l'avviso porta il messaggio del guasto (una riga,
  troncata come le altre code); e il comando delle sonde gira con lo stesso `PATH` dei gate
  (`venv_sul_path()` o il suo equivalente per un albero che non è `REPO`), con i prestiti già previsti.
- `asdlc.toml` e `template/asdlc.toml` — se il RED dimostra che serve, `prestiti = [".venv"]` con il
  commento corretto (oggi dice che i test del runner non hanno file gitignored: `.venv` lo è).
- `tools/tests/test_asdlc_lettore.py` — i test dei criteri, col Lettore finto di `PBI-521`.
- `backlog/PBI-529-le-sonde-del-lettore-dicono-perche-sono-guaste.md` — questo file, per la spunta.
- **Fuori scope:** il Lettore in sé; `conftest.py`, che fa il suo mestiere.

## ✅ Deciso

1. **Il guasto si scrive, non si riassume.** `avvisi` porta `sonda del criterio N: gate guasto — <messaggio>`
   e il rapporto JSON ha, per ogni sonda `guasto`, il campo `guasto` col messaggio intero. Chi legge
   il rapporto deve poter capire senza rilanciare.
2. **Le sonde vedono ciò che vedono i gate.** Stesso `PATH`, stessi prestiti: il criterio è il
   comportamento, non il meccanismo, e il RED lo fissa su un repository di prova senza `.venv`
   nell'albero usa e getta e con `pytest` raggiungibile dal `PATH` del runner.

## Dipendenze
- Bloccato da: nessuno. Blocca: la misura retroattiva di `PBI-521` («Dopo il merge»), che senza sonde
  non si può fare.

## Contesto
- `tools/asdlc/runner.py`: `esegui_le_sonde()`, `worktree_usa_e_getta()` e `PRESTITI`,
  `venv_sul_path()`, `eseguibili_mancanti()`, `GuastoDelGate`.
- `runs/20261025-230609-PBI-524-preverifica.json` e `…-230822-PBI-525-preverifica.json`: sei sonde `guasto`.
- `tools/tests/test_asdlc_lettore.py`: il test del criterio 2 di `PBI-521` (la sonda che gira).

## Verifica
- [ ] **Un gate guasto durante le sonde lascia il suo messaggio.** Con `esiti_del_comando` finto che
      alza `GuastoDelGate("pytest non c'è")`, l'avviso della sonda contiene «pytest non c'è» e la voce
      della sonda nel rapporto ha `esito == "guasto"` e `guasto` col messaggio. Rosso su `main`: oggi
      l'avviso è `gate guasto` e basta.
- [ ] **Una sonda gira anche se l'albero usa e getta non ha `.venv`.** Repository di prova come nel
      criterio 2 di `PBI-521`, con un `conftest.py` che esce se non trova `pytest` in `.venv/bin`
      dell'albero o sul `PATH`, e nessun `.venv` dentro l'albero: la sonda esce `rosso`, non `guasto`.
      Rosso su `main`, se la causa è quella della Direttiva: se il RED invece passa, la causa è un'altra
      e il Builder chiama `fermati` col messaggio che il criterio 1 ormai mostra.

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde; il test del criterio 2 di `PBI-521`
non cambia.

## Protocollo di rifinitura
Si può scegliere senza chiedere: come si tronca il messaggio nell'avviso; se il `PATH` si compone in
`esegui_le_sonde()` o in `comandi_dei_test()`.
Si chiama `fermati`: se il RED del criterio 2 non riproduce il guasto (vedi il criterio).
