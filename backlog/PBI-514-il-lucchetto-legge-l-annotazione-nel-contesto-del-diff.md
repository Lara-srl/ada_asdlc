# PBI-514: il lucchetto di fase legge l'annotazione JUnit nel contesto del diff

**Stato:** da accodare (hotfix di `v0.3.0`/`v0.4.0`; ha una domanda aperta)

## Direttiva

Il difetto 5 di `ada_planning` (`backlog/DIFETTI.md`, causa `runner-non-legge-junit`, terza
occorrenza dopo il 3 e il 4), giri 20261019-095205 e 20261019-110204 di PBI-015, e il difetto
100 di `PBI-102`. `PBI-505` ha insegnato JUnit al lucchetto, ma il Builder di PBI-015 ha
committato un RED con quattro asserzioni rosse e `asdlc-runner --chiedi-impl` ha risposto «Non
c'è nessun test nuovo nell'albero»: il giro è rimasto in `TEST_ONLY` e l'hook ha bloccato
`db/V8__d1_solo_guasto.sql`. PBI-015 si è finito a mano (PR #41).

**La causa, riprodotta il 19/10** con il codice di `v0.4.0` sul commit `d11525c` di
`ada_planning`: `test_nuovi_del_commit("d11525c")` restituisce `[]`, e
`nomi_dei_test_junit(diff, "TriggerGuastiIT")` sul diff di quel commit restituisce
`([], set())`. Il commit cambia il **nome** di un test parametrico e le sue asserzioni:

```
     @ParameterizedTest
     @ValueSource(strings = {"SCALATO", "SOSPESO_MISTO", "PREVENTIVO"})
-    void unSitoConSoliGuastiNonPianificabiliESospeso(String stato) {
+    void unSitoConSoliStatiSospesiNonEGuastoMaESospeso(String stato) {
```

Le righe `@ParameterizedTest` e `@ValueSource(…)` sono **di contesto** (prefisso spazio), non
`+` né `-`: cambia solo la riga del metodo. `nomi_dei_test_junit()` arma l'attesa del metodo
solo sulle righe `+`/`-`, quindi non vede mai l'annotazione e il metodo nuovo non è un test.
Il secondo commit (`1a7f3f6`) dà lo stesso `[]`; la sua causa non è stata ricostruita.

**Scope**

- `tools/asdlc/runner.py` — `nomi_dei_test_junit()`: l'annotazione di una riga di contesto
  vale per il metodo che la segue, che sia aggiunto o tolto.
- `tools/tests/test_asdlc_junit.py` e `tools/tests/dati/` — i test dei criteri e il diff vero
  di `d11525c` come fixture.
- `README.md` e `specs/` solo se descrivono la regola, nello stesso commit.
- `backlog/PBI-514-…md` — questo file, per la spunta.

**Fuori scope**

- Il gate del rosso e i mutanti per Java (`PBI-505`, fuori scope).
- Il PBI-006 di `ada_planning` e il suo pin.
- `@Nested`, `@TestFactory` e `@TestTemplate`.

## ✅ Deciso, per non fermare il giro

1. **Un metodo che segue un'annotazione di test in una riga di contesto è letto come test**
   quando la sua riga è `+` (aggiunto) o `-` (tolto). Se invece nessuna riga del metodo
   cambia, il metodo non entra nel diff e non conta.
2. **Un nome tolto e riaggiunto resta un trasloco** (`PBI-505`, decisione 3): la regola
   cambia solo il modo di riconoscere il metodo, non la sottrazione.
3. **Il diff vero è la fixture**, non uno scritto a mano (protocollo di rifinitura di
   `PBI-505`).
4. **Lo scope dei commit è `runner`.**

## ❓ Domanda aperta, per Francesco (non accodare prima di averla chiusa)

Un RED che **riscrive un test esistente senza cambiarne il nome** (cambio di decisione del
PBI: stesso metodo, asserzione opposta) non ha nessun nome nuovo. Oggi il lucchetto lo
rifiuta come «nessun test nuovo». Due scelte:

- **A.** Resta così: il Builder deve far nascere un test con un nome nuovo, e il PBI lo scrive.
  Regola semplice, coerente con «un nome nuovo è un test che nasce» (`ADR-0021`).
- **B.** Il lucchetto riconosce anche il test **modificato** (il corpo cambia nel diff) e ne
  osserva il rosso. Copre il caso reale di PBI-015 (D1 ribalta una decisione), ma allarga la
  regola: un test ritoccato per sbaglio aprirebbe `IMPL`.

Questo PBI implementa **solo** il punto 1 della *Deciso*, che vale con A e con B. Se scegli B
è un PBI a parte.

## Dipendenze

- Bloccato da: nessuno. Il tag e il pin sono gesti umani, dopo.

## Contesto

- `ada_planning`, `backlog/DIFETTI.md`, difetti 3, 4, 5; `backlog/PBI-102-…`, difetto 100.
- `PBI-505` (decisioni 3, 6 e il protocollo di rifinitura); `decisions/ADR-0021-…`.
- `tools/asdlc/runner.py`: `nomi_dei_test_junit()`, `test_nuovi_del_commit()`,
  `test_nuovi_da_aprire()`, `chiedi_impl()`.

## Verifica

Su `main` il metodo con l'annotazione nel contesto non si vede, quindi ogni criterio è un
**rosso atteso**.

- [ ] **Un metodo rinominato sotto un'annotazione di contesto nasce.** Col diff vero di
      `d11525c` come fixture, `nomi_dei_test_junit(diff, "TriggerGuastiIT")` restituisce
      aggiunti `["TriggerGuastiIT#unSitoConSoliStatiSospesiNonEGuastoMaESospeso", …]` e tolti
      `{"TriggerGuastiIT#unSitoConSoliGuastiNonPianificabiliESospeso", …}` (pytest).
- [ ] **`test_nuovi_del_commit` vede quel commit.** In un repository temporaneo con il file
      prima e dopo, restituisce i test nuovi invece di `[]` (pytest).
- [ ] **Annotazione sul `+`, annotazione sul contesto e annotazione su più righe danno lo
      stesso nome.** Tre forme dello stesso metodo (`@Test`; `@ParameterizedTest` con
      `@ValueSource` in contesto; annotazione e metodo sulla stessa riga) (pytest, parametrizzato).
- [ ] **Un metodo non toccato non nasce.** Un'annotazione in contesto seguita da un metodo
      che non compare nel diff non dà nessun nome (pytest).
- [ ] **`--chiedi-impl` apre `IMPL` su quel RED.** Con il rapporto finto rosso, `chiedi_impl()`
      torna 0 e scrive `IMPL` (pytest).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde e i test di `PBI-505`
non cambiano asserzione.
