# PBI-514: il lucchetto di fase legge l'annotazione JUnit nel contesto del diff

**Stato:** pronto da accodare (hotfix di `v0.3.0`/`v0.4.0`; domanda chiusa da Francesco il 19/10)

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
Il secondo commit (`1a7f3f6`) dà lo stesso `[]` e ha la stessa causa: le annotazioni dei suoi
metodi sono di contesto (lettura avversariale del 20/10, due nascite col prototipo della cura).

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
   `PBI-505`). Si prende così: `git -C ../ada_planning show --format= d11525c >
   tools/tests/dati/junit/d11525c.diff`. **La fixture e i file prima/dopo del criterio 2 si
   salvano come `.diff`/`.txt`, o come stringhe nel test, mai come `.java`**: un `.java` sotto
   `tools/tests/` è un test per `e_file_di_test()` e JUnit per `linguaggio_del_test()`, e qui
   `asdlc.toml` non ha `[junit]`, quindi sarebbe un test orfano (`runner.py`, ~2197): `--chiedi-impl`
   lo rifiuta e il gate del rosso ferma il giro.
4. **Un test riscritto con lo stesso nome non è una nascita** (Francesco, 19/10, scelta A).
   Il lucchetto non guarda il corpo dei test: per aprire `IMPL` il Builder fa nascere un test
   con un nome nuovo (`ADR-0021`), e il PBI che ribalta una decisione lo scrive nella *Verifica*.
   Un test modificato con lo stesso nome resta «nessun test nuovo», com'è oggi.
5. **Lo scope dei commit è `runner`.**
6. **I criteri 1, 2, 3 e 5 hanno un solo RED e un solo GREEN** (Francesco, 20/10). Li fa
   passare la stessa modifica minima a `nomi_dei_test_junit()`: con una coppia per criterio,
   dopo il primo GREEN i test degli altri nascerebbero verdi e il gate del rosso fermerebbe il
   giro (`rosso-mai-visto`). Quindi un commit `test(runner): … (RED)` con i test dei quattro
   criteri, `--chiedi-impl`, poi un commit `fix(runner): …`. **È una deroga al micro-commit
   per criterio** (`ADR-0015`): si dichiara nel messaggio del commit RED, con cosa (quattro
   criteri in una coppia), perché (una modifica sola li rende verdi tutti) e cosa non cambia
   (ogni criterio ha il suo test, e ognuno è rosso nel commit RED).

## Dipendenze

- Bloccato da: nessuno. Il tag e il pin sono gesti umani, dopo.

## Contesto

- `ada_planning`, `backlog/DIFETTI.md`, difetti 3, 4, 5; `backlog/PBI-102-…`, difetto 100.
- `PBI-505` (decisioni 3, 6 e il protocollo di rifinitura); `decisions/ADR-0021-…`.
- `tools/asdlc/runner.py`: `nomi_dei_test_junit()`, `test_nuovi_del_commit()`,
  `test_nuovi_da_aprire()`, `chiedi_impl()`.

## Verifica

Su `main` il metodo con l'annotazione nel contesto non si vede, quindi i criteri 1, 2, 3 e 5
sono un **rosso atteso**, in un commit RED solo (decisione 6). Il caso «metodo non toccato» è
vero anche su `main` e sta nel test parametrico del criterio 3.

- [ ] **Un metodo rinominato sotto un'annotazione di contesto nasce.** Col diff vero di
      `d11525c` come fixture, `nomi_dei_test_junit(diff, "TriggerGuastiIT")` restituisce
      aggiunti, in quest'ordine, `TriggerGuastiIT#unSitoConSoliStatiSospesiNonEGuastoMaESospeso`,
      `TriggerGuastiIT#unSitoApertoChePerdeIlSuoUnicoGuastoDiventaSospesoEChiudeLEpisodio`,
      `TriggerGuastiIT#unSitoSospesoCuiSiAggiungeUnGuastoDiventaApertoConUnEpisodio`, e tolti
      `TriggerGuastiIT#unSitoConSoliGuastiNonPianificabiliESospeso`,
      `TriggerGuastiIT#unSitoApertoChePerdeIlSuoUnicoGuastoPianificabileDiventaSospeso`,
      `TriggerGuastiIT#unSitoSospesoCuiSiAggiungeUnGuastoPianificabileDiventaApertoNellStessoEpisodio`
      (pytest).
- [ ] **`test_nuovi_del_commit` vede quel commit.** In un repository temporaneo con il file
      prima e dopo, restituisce i test nuovi invece di `[]` (pytest).
- [ ] **Annotazione sul `+`, annotazione sul contesto e annotazione sulla stessa riga del
      metodo danno lo stesso nome; un metodo non toccato non nasce.** Tre forme dello stesso
      metodo (`@Test`; `@ParameterizedTest` con `@ValueSource` in contesto; annotazione e metodo
      sulla stessa riga), più il caso id `non-toccato`: un'annotazione in contesto seguita da un
      metodo che non compare nel diff, atteso `([], set())` (pytest, parametrizzato).
- ~~**Un metodo non toccato non nasce.**~~ **Diventato il caso `non-toccato` del criterio 3**
      (lettura del 20/10): su `main` `nomi_dei_test_junit` restituisce già `([], set())`, quindi
      come test a sé nascerebbe verde e senza mutante da uccidere.
- [ ] **`--chiedi-impl` apre `IMPL` su quel RED.** Con il rapporto finto rosso, `chiedi_impl()`
      torna 0 e scrive `IMPL` (pytest).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde e i test di `PBI-505`
non cambiano asserzione.

## La lettura avversariale del 20/10

Un lettore in sola lettura ha provato il PBI su un clone di `main` (`2bad8ad`). Rilievi recepiti:
- la fixture `.java` sarebbe stata un test JUnit orfano (decisione 3);
- il criterio 4 era vero su `main`, ed è diventato un caso del 3;
- i criteri 1, 2, 3 e 5 hanno un RED e un GREEN solo (decisione 6, Francesco);
- i nomi dei metodi del criterio 1 sono scritti per intero, verificati sul diff di `d11525c`;
- il titolo del criterio 3 diceva «su più righe» per il caso «sulla stessa riga»;
- `1a7f3f6` ha la stessa causa.

Verificato senza rilievi: il lucchetto installato non ostacola il giro (qui i test sono Python),
i 26 test di `test_asdlc_junit.py` passano col prototipo della cura, l'albero resta pulito.
