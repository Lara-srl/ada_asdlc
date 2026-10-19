# PBI-515: il lucchetto non chiude i file di supporto dei test

**Stato:** da accodare (hotfix di `v0.3.0`/`v0.4.0`; ha una domanda aperta)

## Direttiva

Il difetto 6 di `ada_planning` (`backlog/DIFETTI.md`, causa `runner-lucchetto-troppo-largo`),
PBI-005, giri 20261019-144204 e 20261019-170204, e il difetto 101 di `PBI-102`. Il lucchetto
di fase tratta come **produzione** ciò che non lo è, e ferma il Builder prima del primo RED:

- `genera_gpkg_prova.sh` sotto `app/src/test/resources/`: lo script che rigenera le fixture di
  un test. Il Builder lo scrive, il lucchetto lo chiude, e finisce in `IMPL` senza RED.
- Gli scheletri vuoti di `tools/migrazione/` e `db/V9__ricalcola_tutti.sql`, che il PBI
  ammetteva prima del primo RED (giro da 67 s).

Scheletri e fixture si sono committati a mano (PR #45, #47).

**La causa nel codice** (`tools/asdlc/runner.py`): `e_file_di_produzione()` è «non è un test e
ha un'estensione di `ESTENSIONI_CODICE`», e `ESTENSIONI_CODICE` contiene `.sh` e `.sql`.
`e_file_di_test()` riconosce sotto `src/test/` **solo i `.java`**, per una scelta dichiarata di
`PBI-505` (non regressione: un `src/test/setup.ts` resta com'era). Quindi `src/test/resources/genera.sh`
è produzione.

**Scope**

- `tools/asdlc/runner.py` — `e_file_di_produzione()` e la sua parte che guarda `src/test/`.
- `tools/tests/test_asdlc_junit.py` (o un file nuovo accanto) — i test dei criteri.
- `README.md`, `backlog/AUTOMAZIONE.md` solo se descrivono la regola, nello stesso commit.
- `backlog/PBI-515-…md` — questo file, per la spunta.

**Fuori scope**

- Il difetto 89 di `PBI-102` (`--chiedi-impl` e lo Scope senza produzione): è vicino, ma è un
  altro punto del codice.
- Gli scheletri vuoti (vedi la domanda aperta).
- Un `src/test/` che non è Maven.

## ✅ Deciso, per non fermare il giro

1. **Sotto `src/test/` nessun file è produzione**, qualunque estensione: la sequenza di
   cartelle di `PBI-505` (decisione 1) vale per tutti i file, non solo per i `.java`.
2. **Non diventano test.** `e_file_di_test()` e la nascita dei test non cambiano: un
   `genera.sh` non è un test, è un file di supporto, e il lucchetto lo lascia scrivere in
   `TEST_ONLY` come scrive i test.
3. **`src/main/…/test/Foo.java` resta produzione** (regola di `PBI-505`).
4. **Lo scope dei commit è `runner`.**

## ❓ Domanda aperta, per Francesco (non accodare prima di averla chiusa)

Gli **scheletri vuoti** (file creati vuoti o con soli commenti, che il PBI ammette prima del
primo RED) non sono ancora un caso risolto. Un RED su un file che non esiste non è un'asserzione
che fallisce, quindi il giro non arriva a `IMPL`. Tre scelte:

- **A.** Il PBI dichiara gli scheletri in una sezione e il lucchetto li lascia creare in
  `TEST_ONLY`. Esplicito, ma serve un formato nuovo.
- **B.** In `TEST_ONLY` si può creare un file di produzione **vuoto** o con soli commenti e
  righe bianche. Nessun comportamento è anticipato; il rosso resta quello del test.
- **C.** Resta com'è: gli scheletri li committa una persona (come in PBI-005).

Raccomando **B**: è la regola più stretta che non anticipa niente, e non chiede formato.
Questo PBI implementa **solo** la *Deciso*; con B è un PBI a parte.

## Dipendenze

- Bloccato da: nessuno. Il tag e il pin sono gesti umani, dopo.

## Contesto

- `ada_planning`, `backlog/DIFETTI.md`, difetto 6; `backlog/PBI-102-…`, difetto 101.
- `PBI-505`, decisione 1 (la sequenza `src/test/`).
- `tools/asdlc/runner.py`: `ESTENSIONI_CODICE`, `e_file_di_test()`, `e_file_di_produzione()`.

## Verifica

Su `main` `src/test/resources/genera.sh` è produzione, quindi ogni criterio è un **rosso atteso**.

- [ ] **Un `.sh` sotto `src/test/` non è produzione.** `e_file_di_produzione(
      "app/src/test/resources/genera.sh")` è falso; lo stesso per un `.sql` sotto `src/test/`
      (pytest, parametrizzato).
- [ ] **Un `.sh` fuori da `src/test/` resta produzione.** `tools/migrazione/riconcilia.sh` e
      `db/V9__x.sql` sono produzione (pytest).
- [ ] **`src/main/…/test/Foo.java` resta produzione** (pytest).
- [ ] **In `TEST_ONLY` la scrittura di quel `.sh` passa dalla guardia.** La guardia di fase
      con fase `TEST_ONLY` non blocca `app/src/test/resources/genera.sh` e blocca
      `tools/migrazione/riconcilia.sh` (pytest).
- [ ] **Quel file non è un test.** `e_file_di_test("app/src/test/resources/genera.sh")` resta
      falso e non produce nascite (pytest).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde; un `src/test/setup.ts` o
`helpers.py` si comporta come prima rispetto alle nascite.
