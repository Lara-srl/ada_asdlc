# PBI-504: il layout del progetto dai gate, non dal codice

## Direttiva

Il difetto 90 di `PBI-102`, con la causa `default-implicito`. `dove_gira()` in
`tools/asdlc/runner.py` decide da quale cartella si rilancia un test isolato. Per farlo
guarda il prefisso del percorso, e ha scritte a mano le cartelle di aDa: `("backend",
"frontend")`. La docstring dice «sono le stesse di `GATE`», ma il codice non le legge. In un
progetto con un altro layout il test si rilancia dalla radice. Al contrario, in un progetto
che ha una cartella `backend/` senza un gate lì, il test si rilancia da `backend/` anche se
nessun gate gira da lì. La cura l'ha decisa Francesco il 04/10: `dove_gira()` legge le
cartelle dai `cwd` di `GATE`. È fra i primi PBI di questo repository e viene prima di
`v0.2.0`, perché la Fase 6 lo incontra per forza: il progetto giocattolo non ha il layout di
aDa.

Nello stesso PBI va il punto di D3 di `SCAFFOLDING.md` di aDa, perché è la stessa classe di
difetto. Otto file di test trovano la radice del repository con
`Path(__file__).resolve().parents[2]`, cioè contando le cartelle da `tools/tests/`. La
radice si trova invece con `radice()` di `asdlc.config`, che risale fino ad `asdlc.toml`.

**Scope**
- `tools/asdlc/runner.py` — `dove_gira()` e la sua docstring.
- `tools/tests/test_asdlc_layout.py` — nuovo: i test dei quattro criteri.
- `tools/tests/test_asdlc_runner.py` — i cinque test della decisione 3, e la riga di `REPO`.
- `tools/tests/test_asdlc_ambiente_dei_test.py`, `test_asdlc_cartella_di_lavoro.py`,
  `test_asdlc_coda.py`, `test_asdlc_config.py`, `test_asdlc_esito.py`,
  `test_asdlc_fuori_da_backend.py`, `test_asdlc_pacchetto.py` — la sola riga di `REPO`.
- `backlog/PBI-504-il-layout-dai-gate.md` — questo file, per la spunta.
- **Fuori scope:** `REPO / "tools" / "asdlc"` e gli altri percorsi del pacchetto composti
  con `"tools"`, che vanno al PBI del trasloco a `src/` (decisione 6); `conftest.py`, che
  mette `tools/` sul `sys.path` e resta com'è; la riga «Chiuso da» del difetto 90 in
  `PBI-102`, che si scrive al merge.

## ✅ Deciso, per non fermare il giro

1. **Le cartelle sono i `cwd` dei gate di `GATE`, tolto `.`.** Un percorso appartiene a una
   cartella se comincia con la cartella seguita da `/`. Se nessuna cartella lo prende, il
   test gira dalla radice, `.`, col percorso com'è. La firma di `dove_gira(percorso)` non
   cambia: legge `GATE` come lo leggono gli altri punti del runner.
2. **Fra due cartelle annidate vince la più lunga**: un test sotto `app/web/` gira da
   `app/web` anche se c'è un gate in `app`.
3. **I cinque test che oggi contano su `backend/` e `frontend/` scritti a mano si adattano
   per primi, in `TEST_ONLY`, con le asserzioni intatte.** Ognuno dichiara con
   `monkeypatch.setattr(runner, "GATE", […])` un gate col `cwd` che il suo percorso usa,
   `backend` o `frontend`, e non cambia nient'altro. Il commit lo dichiara come deroga
   (`ADR-0015`): cosa cambia, perché, e che nessuna asserzione cambia. Sono verdi su `main`
   prima e dopo, e restano verdi dopo la cura. I cinque sono:
   - `TestIlGateDelRossoCamminaICommit::test_sul_commit_misto_un_test_del_frontend_porta_il_filtro_di_vitest`
   - `TestIlGateDelRossoCamminaICommit::test_un_test_punto_spec_non_esce_dal_gate_per_il_suo_nome`
   - `TestLEsitoSiLeggePerTest::test_un_test_nato_verde_con_uno_spazio_nellid_resta_verde_accanto_a_un_rosso`
   - `TestLeLettureDiPytestCheNonCambiano::test_guardia_un_test_rosso_resta_rosso`
   - `TestLeLettureDiPytestCheNonCambiano::test_guardia_un_xfail_resta_saltato`
4. **L'ordine dei commit**: l'adattamento della decisione 3; poi il criterio 4, tutto in
   `TEST_ONLY`, perché il suo verde cambia solo file di test; poi i criteri 1, 2 e 3, in
   quest'ordine, ognuno col suo `--chiedi-impl`. Ogni test nasce rosso sul codice del commit
   prima. Il verde di ogni criterio è il minimo che lo fa passare: il criterio 1 aggiunge le
   cartelle dei gate e lascia `backend` e `frontend`, il criterio 2 le toglie, il criterio
   3 ordina per lunghezza.
5. **I test dei criteri 1, 2 e 3 dichiarano `GATE` con `monkeypatch`**, con gate costruiti
   da `Gate` di `asdlc.config`. Non leggono l'`asdlc.toml` del progetto di prova, che ha un
   solo gate in `.`.
6. **`REPO / "tools" / "asdlc"` resta** (Francesco, 09/10). Si sarebbe tolto solo se la
   cartella si potesse leggere da `[ambiente].installa`. Non si può: `installa` dice dove
   sta il pacchetto **al tag del pin**, e i test leggono la copia di lavoro. Durante un
   trasloco i due layout differiscono finché il pin non sale. La cartella della copia di
   lavoro si leggerebbe da `asdlc.__file__`, che è il trasloco a `src/`.
7. **Lo scope dei commit è `runner`**, anche per l'adattamento e per il criterio 4.

## Dipendenze
- Bloccato da: nessuno. `PBI-500`…`503` sono in `main`.
- Dopo questo: il tag `v0.2.0`, e i pin di qui e di aDa (passo 4.3 del runbook della Fase 5
  di aDa).

## Contesto
- `backlog/PBI-102-soglia-di-revisione-del-runner.md`, difetto 90 — il guasto e la cura.
- `backlog/README.md`, la riga `default-implicito` della tabella delle cause.
- `tools/asdlc/runner.py`, `dove_gira()` e i suoi due chiamanti: `etichette_al_commit()`
  per le etichette, `comandi_dei_test()` per la cartella del comando.
- `tools/asdlc/config.py`, `Gate` e `radice()`.

## Verifica
- [x] **Un test gira dalla cartella di un gate, e il comando isolato parte da lì.** Con un
      solo gate in `servizio`, `dove_gira("servizio/tests/test_a.py")` restituisce
      `("servizio", "tests/test_a.py")`. `comandi_dei_test()` su quel test, in un albero
      temporaneo che lo contiene, restituisce un comando con cartella `<albero>/servizio`,
      etichetta `tests/test_a.py::test_x` e nessun orfano. Su `main` dà la radice.
- [x] **`backend/` non è più speciale, e il confine è la cartella intera.** Con un solo gate
      in `.`, `dove_gira("backend/tests/test_a.py")` restituisce
      `(".", "backend/tests/test_a.py")`. Con un solo gate in `back`, lo stesso percorso dà
      lo stesso risultato: `back` non prende `backend/`. Su `main` danno `backend`.
- [x] **Fra due cartelle annidate vince la più lunga.** Con gate in `app` e in `app/web`,
      `dove_gira("app/web/src/x.test.ts")` restituisce `("app/web", "src/x.test.ts")`, in
      qualunque ordine stiano i due gate in `GATE`.
- [x] **Nessun test trova la radice contando le cartelle.** Nessun file `.py` di
      `tools/tests`, tranne `conftest.py`, ha `Path(__file__)` seguito da `.parents[`, con o
      senza `.resolve()`. Il test costruisce il modello in modo da non trovare sé stesso.
      Su `main` lo trova in otto file.

**Non regressione:**
- I cinque test della decisione 3 restano verdi con le stesse asserzioni.
- Con i gate di aDa, `backend` e `frontend`, `dove_gira()` dà gli stessi risultati di prima.
- `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura
Un punto del pacchetto che conosce le cartelle di un progetto è un difetto con la causa
`default-implicito`. Le cartelle di un progetto si leggono da `asdlc.toml`.
