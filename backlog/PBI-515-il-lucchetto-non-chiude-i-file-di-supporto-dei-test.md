# PBI-515: il lucchetto non chiude i file di supporto dei test

**Stato:** pronto da accodare (hotfix di `v0.3.0`/`v0.4.0`; domanda chiusa da Francesco il 19/10)

## Direttiva

Il difetto 6 di `ada_planning` (`backlog/DIFETTI.md`, causa `runner-lucchetto-troppo-largo`),
PBI-005, giri 20261019-144204 e 20261019-170204, e il difetto 101 di `PBI-102`. Il lucchetto
di fase tratta come **produzione** ciò che non lo è, e ferma il Builder prima del primo RED:

- `genera_gpkg_prova.sh` sotto `app/src/test/resources/`: lo script che rigenera le fixture di
  un test. Il Builder lo scrive, il lucchetto lo chiude, e finisce in `IMPL` senza RED.
- Gli scheletri vuoti di `tools/migrazione/` e `db/V9__ricalcola_tutti.sql`, che il PBI
  ammetteva prima del primo RED (giro da 67 s).

Scheletri e fixture si sono committati a mano (PR #45, #47).

**Il PBI tocca l'hook e il `pre-commit`** (`stampa_la_guardia_di_fase()`, `guardia_del_commit()`).
Il giro ci sopravvive perché tutti e due lanciano il runner installato (`PBI-384`), non la copia
di lavoro: le modifiche del Builder non cambiano il lucchetto che lo sorveglia durante il giro
(difetto 66 di `PBI-102`).

**La causa nel codice** (`tools/asdlc/runner.py`): `e_file_di_produzione()` è «non è un test e
ha un'estensione di `ESTENSIONI_CODICE`», e `ESTENSIONI_CODICE` contiene `.sh` e `.sql`.
`e_file_di_test()` riconosce sotto `src/test/` **solo i `.java`**, per una scelta dichiarata di
`PBI-505` (non regressione: un `src/test/setup.ts` resta com'era). Quindi `src/test/resources/genera.sh`
è produzione.

**Scope**

- `tools/asdlc/runner.py` — `e_file_di_produzione()` e la sua parte che guarda `src/test/`;
  `guardia_di_fase()`, `stampa_la_guardia_di_fase()` e `guardia_del_commit()` per lo scheletro
  vuoto (decisioni 5-8).
- `tools/tests/test_asdlc_junit.py` (o un file nuovo accanto) — i test dei criteri. In
  `test_asdlc_junit.py` il test `TestUnFileInSrcTestEUnTestJunit::test_un_file_non_java_in_src_test_resta_produzione`
  contraddice la decisione 1: **si riscrive nel commit RED del criterio 1**, e il messaggio lo
  dichiara. Resta `not e_file_di_test(p)`; `e_file_di_produzione(p)` diventa falso. In `IMPL`
  i test sono in sola lettura, e senza questa riscrittura il GREEN non si chiude.
- `README.md`, `backlog/AUTOMAZIONE.md` solo se descrivono la regola, nello stesso commit.
- `backlog/PBI-515-…md` — questo file, per la spunta.

**Fuori scope**

- Il difetto 89 di `PBI-102` (`--chiedi-impl` e lo Scope senza produzione): è vicino, ma è un
  altro punto del codice.
- Gli scheletri con del codice dentro: restano produzione e restano chiusi in `TEST_ONLY`.
- Un `src/test/` che non è Maven.
- **Uno scheletro committato insieme al RED.** Lo scheletro si committa da solo, prima del RED:
  il gate del rosso e `--chiedi-impl` continuano a trattare come misto un commit con test e
  scheletro (`gate_del_rosso`, `MISTO`), e in `ada_planning` si ripresenterebbe il difetto 5.

## ✅ Deciso, per non fermare il giro

1. **Sotto `src/test/` nessun file è produzione**, qualunque estensione: la sequenza di
   cartelle di `PBI-505` (decisione 1) vale per tutti i file, non solo per i `.java`.
2. **Non diventano test.** `e_file_di_test()` e la nascita dei test non cambiano: un
   `genera.sh` non è un test, è un file di supporto, e il lucchetto lo lascia scrivere in
   `TEST_ONLY` come scrive i test.
3. **`src/main/…/test/Foo.java` resta produzione** (regola di `PBI-505`).
4. **Uno scheletro vuoto si può creare in `TEST_ONLY`** (Francesco, 19/10, scelta B). È un
   file di produzione il cui contenuto è **solo righe bianche e commenti**: nessun
   comportamento è anticipato, e il rosso resta quello del test. Il PBI-005 di `ada_planning`
   ne è il caso (`tools/migrazione/*.sh`, `db/V9__ricalcola_tutti.sql`).
5. **«Commento» dipende dall'estensione:** `#` per `.sh` e `.py` (la riga `#!` di un `.sh`
   conta), `--` per `.sql`, `//` e i blocchi `/* … */` per `.java`, `.js`, `.jsx`, `.ts`, `.tsx`,
   `.mjs`, `.cjs`. ~~Un'estensione che non è in questo elenco non ha commenti: ammette solo il
   file vuoto o di righe bianche.~~ **Tolta (lettura del 20/10):** l'elenco coincide con
   `ESTENSIONI_CODICE`, quindi un'estensione fuori elenco non è mai produzione e la frase non
   ha un caso. Un commento con il segno sbagliato (un `#` in un `.sql`) non è un commento.
6. **Il confine è il `pre-commit`**, che legge il contenuto **in stage** (`git show :percorso`):
   `Edit`, `Write`, un heredoc e `touch` finiscono tutti lì. L'hook `PreToolUse` lascia passare
   un `Write` il cui `content` è uno scheletro e continua a bloccare ogni `Edit` su un file di
   produzione, perché non vede il file intero. Un guasto nel leggere il contenuto non blocca
   (`ADR-0008`), e il `pre-commit` decide.
7. **Quando il file ha già del codice, vale il codice:** uno scheletro che riceve una riga di
   codice in stage torna produzione, e il commit è bloccato come oggi.
8. **Lo scope dei commit è `runner`.**

## Dipendenze

- Bloccato da: nessuno. Il tag e il pin sono gesti umani, dopo.

## Contesto

- `ada_planning`, `backlog/DIFETTI.md`, difetto 6; `backlog/PBI-102-…`, difetto 101.
- `PBI-505`, decisione 1 (la sequenza `src/test/`).
- `tools/asdlc/runner.py`: `ESTENSIONI_CODICE`, `e_file_di_test()`, `e_file_di_produzione()`.

## Verifica

Su `main` `src/test/resources/genera.sh` è produzione, e i criteri 1, 4, 6, 8 e 9 sono un
**rosso atteso**. Ciò che è già vero su `main` (un `.sh` fuori da `src/test/`, `src/main/…/test/`,
«non è un test», «un file con del codice resta chiuso») sta come caso nel test parametrico di
un criterio rosso: come test a sé nascerebbe verde (`rosso-mai-visto`).

- [x] **Un `.sh` sotto `src/test/` non è produzione, e non è un test.** Per
      `app/src/test/resources/genera.sh` e per un `.sql` sotto `src/test/`:
      `not e_file_di_produzione(p) and not e_file_di_test(p)`. Casi dello stesso test
      parametrico: `tools/migrazione/riconcilia.sh`, `db/V9__x.sql` e
      `app/src/main/java/it/x/test/Foo.java` restano produzione (pytest, parametrizzato).
- ~~**Un `.sh` fuori da `src/test/` resta produzione.**~~ **Diventato un caso del criterio 1**
      (lettura del 20/10): è vero su `main`.
- ~~**`src/main/…/test/Foo.java` resta produzione.**~~ **Diventato un caso del criterio 1**
      (lettura del 20/10): è vero su `main`.
- [x] **In `TEST_ONLY` la scrittura di quel `.sh` passa dalla guardia.** La guardia di fase
      con fase `TEST_ONLY` non blocca `app/src/test/resources/genera.sh` e blocca
      `tools/migrazione/riconcilia.sh` (pytest).
- ~~**Quel file non è un test.**~~ **Fuso nel criterio 1** (lettura del 20/10): è vero su `main`,
      e `e_file_di_test()` non cambia (decisione 2), quindi nessun mutante lo farebbe fallire.

- [x] **Uno scheletro vuoto passa dal `pre-commit` in `TEST_ONLY`.** Con in stage `tools/migrazione/
      riconcilia.sh` fatto di una riga `#!/bin/sh` e commenti, e `db/V9__x.sql` vuoto o di
      soli commenti `--`, `guardia_del_commit()` torna 0. Casi dello stesso test parametrico:
      lo stesso `riconcilia.sh` con una riga di codice in stage fa tornare 1 e nomina il file, e
      così un `.sql` con uno `SELECT 1;` (pytest, repository temporaneo; i commit di preparazione
      con `--no-verify`).
- ~~**Un file con del codice resta chiuso.**~~ **Diventato un caso del criterio 6** (lettura del
      20/10): è vero su `main`.
- [x] **L'hook lascia passare un `Write` di scheletro e blocca un `Edit`.** Con la fase
      `TEST_ONLY`, `stampa_la_guardia_di_fase()` esce 0 per un `Write` con `content` fatto di
      commenti, ed esce 2 per un `Write` con codice e per ogni `Edit` su un file di produzione
      (pytest, stdin finto).
- [x] **Il commento dipende dall'estensione.** Un `.py` fatto di `# x` passa, un `.sql` fatto di
      `# x` resta chiuso: per SQL `#` non è un commento (pytest). ~~Un `.rb` con `# x` no~~: `.rb`
      non è in `ESTENSIONI_CODICE`, non è mai produzione e il caso passava sempre.

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde; un `src/test/setup.ts` o
`helpers.py` si comporta come prima rispetto alle nascite.

## La lettura avversariale del 20/10

Un lettore in sola lettura ha provato il PBI su un clone di `main` (`2bad8ad`). Rilievi recepiti:
- `test_un_file_non_java_in_src_test_resta_produzione` contraddice la decisione 1: si riscrive
  nel RED del criterio 1 (Scope);
- i criteri 2, 3, 5 e 7 erano veri su `main`: sono diventati casi dei parametrici 1 e 6, e i
  criteri rossi sono cinque;
- il caso `.rb` del criterio 9 non era verificabile, e la frase sulle estensioni fuori elenco
  della decisione 5 non aveva un caso;
- lo scheletro si committa da solo, prima del RED (Fuori scope);
- la Direttiva dichiara che il PBI tocca l'hook e il `pre-commit`.

Verificato senza rilievi: il Builder scrive solo `.py` e `.md`; le fixture `.sh` e `.sql` sotto
`tools/tests/dati` sono test e si scrivono nel RED; 514 e 515 toccano funzioni diverse.
