# PBI-505: il lucchetto di fase legge i test JUnit

## Direttiva

Il difetto 3 di `ada_planning` (`backlog/DIFETTI.md`, causa `runner-non-legge-junit`), visto
sul giro del PBI-002 il 15/10/2026. Il Builder scrive `SchemaIT.java`, lo vede rosso per
asserzione e lo committa. Poi chiede `asdlc-runner --chiedi-impl` e riceve «Non c'è nessun test
nuovo nell'albero»: il lucchetto di fase resta in `TEST_ONLY` e blocca la scrittura di
`db/V1__schema.sql`. Il gate del rosso, in quel progetto, è spento (`ADR-0005`); il lucchetto
non ha un interruttore e conosce solo pytest e vitest.

Il guasto ha tre punti, tutti in `tools/asdlc/runner.py`:

- `e_file_di_test()` non riconosce `src/test/java/…`, e `linguaggio_del_test()` non
  riconosce `.java`. Nessun file Java è un test.
- `ESTENSIONI_CODICE` non contiene `.java`. Un file Java non è produzione, quindi il commit
  «misto» (test + produzione) non si riconosce e la scrittura di `src/main/java/…` non è
  nemmeno vietata in `TEST_ONLY`.
- `comandi_dei_test()` e `esiti_del_comando()` sanno lanciare e leggere solo pytest e vitest.

Il PBI insegna il terzo linguaggio, `junit`, al **lucchetto**: nascita dei test, comando che li
isola, esito letto per test dai rapporti di Maven. Il comando che li lancia lo dichiara il
progetto in `asdlc.toml`, perché il runner non deve conoscere Maven (README, «Linguaggi e
stack»). Il gate del rosso e la quarta lettura (i mutanti) restano fuori: un progetto Java li
tiene spenti con `[gate_del_rosso].attivo = false`, e riaccenderli è un altro PBI.

**Scope**

- `tools/asdlc/runner.py` — `e_file_di_test()`, `linguaggio_del_test()`, `ESTENSIONI_CODICE`,
  la nascita dei test JUnit (nuova funzione accanto a `nomi_dei_test()`),
  `test_nuovi_dellalbero()`, `test_nuovi_del_commit()`, `comandi_dei_test()`,
  `esiti_del_comando()` e la lettura dei rapporti (nuova, accanto a `esiti_di_pytest()`).
- `tools/asdlc/config.py` — la sezione opzionale `[junit]`.
- `tools/tests/test_asdlc_junit.py` — nuovo: i test dei criteri.
- `tools/tests/dati/` — i rapporti di esempio (surefire/failsafe) che i test leggono.
- `README.md` — la tabella «Quello che il runner riconosce davvero» e il paragrafo che dice
  «da verificare sul primo PBI».
- `backlog/AUTOMAZIONE.md` — la sezione `[junit]` accanto a quella del gate del rosso.
- `backlog/PBI-505-il-lucchetto-di-fase-legge-junit.md` — questo file, per la spunta.

**Fuori scope**

- **Il gate del rosso e i mutanti per Java.** `test_nuovi_del_commit()` impara il linguaggio
  perché il lucchetto lo chiama sul commit RED già fatto (`test_nuovi_da_aprire()`), ma la
  quarta lettura non si tocca. Un progetto Java tiene il gate spento.
- **`ada_planning`.** Aggiungere `[junit]` al suo `asdlc.toml` e salire il pin sono PBI e PR
  di quel repository, dopo il tag (vedi *Dipendenze*).
- **Le classi annidate (`@Nested`)** e i test dichiarati senza annotazione (`@TestFactory`,
  `@TestTemplate`): si riconoscono solo `@Test`, `@ParameterizedTest` e `@RepeatedTest`.
- Il tag e il rilascio.

## ✅ Deciso, per non fermare il giro

1. **Il linguaggio si chiama `junit`.** `linguaggio_del_test()` lo restituisce per un
   percorso che finisce in `.java` ed è un file di test. Un file è di test per
   `e_file_di_test()` se nel percorso compare la sequenza di cartelle `src/test/`. La regola
   cerca la sequenza, non una cartella `test` qualunque: `app/src/main/java/.../test/Foo.java`
   è produzione.
2. **`.java` entra in `ESTENSIONI_CODICE`.** È la sola riga che rende Java «produzione» per
   il commit misto e per il lucchetto. Il cambio vale per ogni progetto con file `.java`, ed
   è voluto: prima un `.java` non era niente.
3. **La nascita si legge dal diff**, come per vitest. Un test è un metodo che segue
   un'annotazione `@Test`, `@ParameterizedTest` o `@RepeatedTest` (anche con argomenti, anche
   con altre annotazioni in mezzo). Il nome è `Classe#metodo`, con `Classe` il nome semplice
   del file. Un nome aggiunto e tolto nello stesso diff è un trasloco, non una nascita.
4. **Il comando lo dichiara il progetto.** `asdlc.toml` ha una sezione opzionale `[junit]` con
   una sola chiave, `comando`: una lista di argomenti che deve contenere l'elemento
   `{test}`, sostituito con `Classe#m1+m2,Altra#m3` (la sintassi di `-Dtest=` di Maven). Un
   progetto Maven con unit e integrazione scrive, per esempio:
   `["./mvnw", "-B", "verify", "-Dtest={test}", "-Dit.test={test}",
   "-Dsurefire.failIfNoSpecifiedTests=false", "-Dfailsafe.failIfNoSpecifiedTests=false"]`.
   La cartella di lancio la decide `dove_gira()` (PBI-504), cioè il `cwd` del gate che copre
   quel test. Un comando per cartella, come per pytest. Chiavi sconosciute nella sezione,
   o un `comando` senza `{test}`, sono un errore di configurazione.
5. **Senza `[junit]` un test JUnit non si isola.** Finisce negli *orfani* di
   `comandi_dei_test()` (esito «nessuno»), e `--chiedi-impl` non apre `IMPL`. Il runner non
   indovina un comando.
6. **L'esito si legge dai rapporti, non dallo schermo.** Prima di lanciare, il runner toglie
   i `TEST-*.xml` di `target/surefire-reports/` e `target/failsafe-reports/` sotto la
   cartella di lancio; dopo li legge tutti. Un caso appartiene a un test chiesto se il
   `classname` finisce con `.Classe` e il `name` è il metodo, oppure comincia con il metodo
   seguito da `(` o `[` (i parametrici di JUnit 5). Esito del test: `rosso` se un suo caso ha
   `<failure>` o `<error>`; `saltato` se `<skipped>`; `verde` altrimenti; `nessuno` se non ha
   casi. Il più forte vince (`ORDINE_ESITI`).
7. **Il rosso si riporta col suo tipo** (`ADR-0021`). Un `<failure>` il cui `type` è
   `org.opentest4j.AssertionFailedError` o `java.lang.AssertionError` è un'asserzione. Un
   `<error>` (eccezione qualunque, per esempio `NullPointerException`) conta `rosso` anche
   lui, come l'errore di raccolta di pytest: il rapporto non dice se l'eccezione è
   l'asserzione mancata o un guasto del test, e il runner non inventa una distinzione che
   non ha. Il tipo si riporta nel rapporto del giro, perché lo giudichi chi legge.
8. **Un errore di compilazione è `rosso`.** Il caso più comune del test-first in Java è il
   test che nomina una classe che non esiste ancora. Maven esce con errore senza scrivere
   rapporti: se l'uscita contiene `COMPILATION ERROR` il comando intero vale `rosso` per tutti
   i test chiesti, come l'errore di raccolta di pytest (`leggi_esito`). Un'uscita non zero
   senza rapporti e senza `COMPILATION ERROR` è `GuastoDelGate`, con la coda dell'uscita.
9. **L'ordine dei commit**: un criterio, una coppia RED → GREEN, nell'ordine della
   *Verifica*. Ogni test nasce rosso sul codice del commit prima. I test usano `esegui()`
   sostituito da un finto (`monkeypatch`) che scrive i rapporti di `tools/tests/dati/`: nessun
   test lancia Maven, e nessuno usa la rete.
10. **Lo scope dei commit è `runner`.**

## Dipendenze

- Bloccato da: nessuno. `PBI-504` è in `main` (`dove_gira()` legge i `cwd` dei gate).
- Dopo questo, a mano: il tag (`v0.3.0`), la PR in `ada_planning` che sale il pin e aggiunge
  `[junit]` al suo `asdlc.toml`, poi il rilancio del PBI-002. Il gate del rosso di
  `ada_planning` resta spento (`ADR-0005`).

## Contesto

- `ada_planning`, `backlog/DIFETTI.md`, difetto 3: il guasto, con il giro e il commit
  `aa6db16`. `backlog/README.md` di quel repository: la causa `runner-non-legge-junit`.
- `tools/asdlc/runner.py`: `test_nuovi_da_aprire()` (il ripiego su `HEAD` è il percorso che
  ha fallito), `chiedi_impl()`, `comandi_dei_test()`, `esiti_del_comando()`,
  `esiti_di_pytest()`, `caso_junit()`.
- `README.md`, «Linguaggi e stack»; `backlog/AUTOMAZIONE.md`, il gate del rosso.
- `decisions/ADR-0021-il-rosso-si-chiede-prima.md`.

## Verifica

Su `main` il lucchetto non conosce JUnit, quindi ogni criterio è un **rosso atteso**.

- [x] **Un file in `src/test/` è un test JUnit, uno in `src/main/` è produzione.**
      `linguaggio_del_test("app/src/test/java/it/x/SchemaIT.java")` è `junit` ed
      `e_file_di_test` lo accetta; `e_file_di_produzione("app/src/main/java/it/x/Foo.java")`
      è vero; `e_file_di_produzione("app/src/main/java/it/x/test/Foo.java")` è vero
      (pytest).
- [x] **La nascita dei test JUnit si legge dall'albero.** Un file non tracciato con due
      `@Test`, un `@ParameterizedTest` e un metodo senza annotazione dà tre `TestNuovo`
      `SchemaIT#a`, `SchemaIT#b`, `SchemaIT#c`, linguaggio `junit` (pytest, repository
      temporaneo).
- [x] **Il commit RED di soli test si vede dal ripiego su `HEAD`.** Dopo il commit del file
      del criterio precedente, `test_nuovi_da_aprire()` restituisce quei tre test; se lo
      stesso commit tocca anche `app/src/main/java/…/Foo.java` restituisce una lista vuota
      (pytest, repository temporaneo con base e ramo).
- [x] **Il comando isola i test e rispetta `[junit]`.** Con `[junit].comando` configurato,
      `comandi_dei_test()` restituisce un comando per cartella, con `{test}` sostituito da
      `SchemaIT#a+b` e l'etichetta `SchemaIT#a`; senza la sezione i test sono *orfani* e
      nessun comando parte. La sezione con una chiave sconosciuta, o senza `{test}`, è un
      errore di configurazione (pytest, tre casi).
- [x] **L'esito si legge per test dai rapporti.** Con un `TEST-…SchemaIT.xml` di esempio:
      un caso con `AssertionFailedError` è `rosso`, uno passato `verde`, uno `<skipped>`
      `saltato`, un test senza caso `nessuno`, un parametrico `c(String)[2]` conta per `c`;
      se due casi dello stesso test dicono cose diverse vince il più forte (pytest,
      parametrico: un caso per lettura).
- [x] **Un errore di compilazione vale `rosso`.** Con `esegui()` finto che torna codice 1 e
      un'uscita con `COMPILATION ERROR`, senza rapporti, `esiti_del_comando()` dà `rosso`
      per tutti i test chiesti; con codice 1 e nessun'altra spiegazione solleva
      `GuastoDelGate` (pytest).
- [x] **`--chiedi-impl` apre `IMPL` su un RED JUnit.** In fase `TEST_ONLY`, con il commit RED
      del criterio 3 e il rapporto finto rosso, `chiedi_impl()` torna 0 e scrive `IMPL`; con il
      rapporto verde torna 1 e la fase resta `TEST_ONLY` (pytest, due casi).

**Non regressione:**

- I test di pytest e vitest si leggono come prima: `python3 -m pytest -q tools/tests` resta
  verde, e nessun test esistente cambia asserzione.
- Un progetto senza `[junit]` e senza file `.java` non vede nessuna differenza.
- Il README non dice più che JUnit non è letto dal lucchetto; dice ancora che il gate del
  rosso legge solo pytest e vitest.

## Protocollo di rifinitura

Se il rapporto di surefire/failsafe di un progetto vero non combacia con la regola 6 — nomi
dei parametrici, classi annidate, `classname` diverso dal nome del file — non si allarga la
regola a occhio: ci si ferma, si allega il rapporto vero a `tools/tests/dati/` e si corregge
la regola 6 sul caso reale. Il primo rapporto vero è quello del PBI-002 di `ada_planning`.
