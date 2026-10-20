# PBI-521: il Lettore, e la sonda del rosso sulla base

**Stato:** proposto, letto il 20/10 (vedi in fondo). Secondo di tre: 520, 521, 522 (`ADR-0031`).

## Direttiva

Il fermo più frequente nei giri misurati è il criterio che **nasce verde**: 11 fermi su circa 50
(`rosso-mai-visto`, «non riesco a produrre un rosso»). Il comportamento c'era già su `main`, e nessun
ordine di commit poteva mostrarne il rosso. La regola che lo evita esiste (`backlog/README.md`:
verificare sulla base caso per caso, prima di accodare), ma la applica solo chi scrive il PBI.

Questo PBI aggiunge due cose:

- **un quarto ruolo, il Lettore** (`ADR-0031`, decisioni 1-3). Legge il PBI contro il codice di `main`
  e risponde alle sette domande.
- **la sonda del rosso.** Il Lettore scrive i test RED dei criteri in un albero usa e getta alla base.
  Il **runner** li esegue con gli strumenti di `--chiedi-impl`, e una sonda verde diventa un rilievo R
  deciso dal codice.

Si lancia a mano con `asdlc-runner PBI-N --preverifica --lettore`: il controllo di `PBI-520` più il
Lettore, nello stesso rapporto.

**Scope**

- `tools/asdlc/esito.py`:
  - il ruolo `lettore` in `RUOLI`, `STRUMENTI_DEL_LETTORE` e `strumenti("lettore")`;
  - in `chiama()`, il ramo che accumula `rilievo` e `sonda` e chiude con `letto` (decisione 2).

  Solo libreria standard: lo vuole `test_il_server_esiste_e_usa_solo_la_libreria_standard`.
- `tools/asdlc/runner.py`:
  - il ruolo in `RUOLI` e `comando_del_lettore()`;
  - in `invoca_agente()`: un argomento `cwd` (default `REPO`), e il tetto `[lettore].minuti` per il
    ruolo `lettore`, oggi preso da `MINUTI_CRITIC` (~1235);
  - `cartella_delle_sessioni()` che prende la cartella da `cwd`: oggi la prende da `REPO` (~1142),
    e con `cwd` in `/tmp` la traccia non si troverebbe;
  - `lettura_del_lettore()` con la sonda;
  - il flag `--lettore`.
- `tools/asdlc/config.py` e `asdlc.toml` — la sezione `[lettore]` con `modello` (default `opus`, come
  `[solver]`) e `minuti` (default 30).
- `tools/asdlc/prompt/lettore.md` — **nuovo**: il prompt del ruolo, con le sette domande. Passa per
  `.format()`, quindi le graffe degli esempi vanno doppie.
- `tools/tests/test_asdlc_lettore.py` — **nuovo**: i test dei criteri, con un Lettore finto.
- `README.md` — il ruolo e il flag, nello stesso commit del codice.
- `backlog/PBI-521-il-lettore-e-la-sonda-del-rosso.md` — questo file, per la spunta.

Il PBI tocca `esito.py`, il server dell'esito che il runner lancia durante il giro. Il giro ci
sopravvive perché il pacchetto che gira è quello **installato** (`ADR-0026`): il server nuovo entra
solo al tag successivo.

**Fuori scope**

- Il Lettore dentro il giro e nel tick (`PBI-522`).
- Il Lettore che corregge il PBI (`ADR-0031`, decisione 6), e lo Scrittore.
- Un'esecuzione vera di `claude` nei test.
- La misura sui PBI veri: è un gesto da fare dopo il merge, ed è scritta in fondo.

## ✅ Deciso

1. **Gli strumenti del Lettore sono tre.** Il server li valida (`ADR-0027`):
   - `rilievo(domanda, criterio, testo, evidenza)`: `domanda` è una fra `R F T A E D N`;
     `criterio` è un intero ≥ 0 (0 vuol dire il PBI intero); `evidenza` è un `percorso` o un
     `percorso:riga` che esiste nell'albero, con la regola di `_risolvi()`. **Si può chiamare più
     volte.**
   - `sonda(criterio, file, nome)`: `criterio` ≥ 1, e `file` esiste nell'albero (regola di
     `_risolvi()`). **Il server non decide se il file è un test**, perché non può importare
     `linguaggio_del_test()`: lo decide il runner, e un file che non è un test dà
     `ESITI_MANCATI["nessuno"]`. **Si può chiamare più volte.**
   - `letto(riepilogo)`: chiude la lettura. **È definitiva**, e dopo `letto` gli altri due strumenti
     rifiutano.
2. **Il formato dell'esito.** `rilievo` e `sonda` validi si aggiungono, una riga JSON per chiamata
   (`{"strumento", ...argomenti}`), a `<esito>.lettura.jsonl`. `letto` scrive `<esito>` con
   `_scrivi()`, come gli altri esiti definitivi:
   `{"esito": "letto", "riepilogo", "rilievi": [...], "sonde": [...]}`. Le due liste sono lette dal
   `.jsonl` al momento di `letto`. Senza `letto` la lettura è `senza esito`: i rilievi del `.jsonl`
   entrano lo stesso nel rapporto, marcati `"lettore": "senza esito"`, ma le sonde non si eseguono.
   La chiave `esiti` non si usa. Il Lettore finto dei test scrive questi stessi file.
3. **Il Lettore lavora in un albero usa e getta alla base** (`worktree_usa_e_getta(base)`).
   L'albero è il `cwd` della sua invocazione, e il server dell'esito lo eredita (`config_del_server`
   non fissa un `cwd`). `--allowedTools` vale `Read,Grep,Glob,Write,Edit` più i tre `mcp__asdlc__*`.
   **Niente `Bash`**: le sonde le esegue il runner. L'albero si smonta comunque vada.
4. **La sonda la giudica il runner.** Dopo `letto` il runner, per ogni `sonda`:
   - se `linguaggio_del_test(file)` è `None`, scrive un rilievo `R` con `ESITI_MANCATI["nessuno"]`;
   - altrimenti costruisce `TestNuovo(file, nome, linguaggio)` e lo passa a
     `comandi_dei_test(albero, nuovi)` e `esiti_del_comando()`.

   Poi, sempre per ogni sonda:
   - una sonda con esito diverso da `rosso` dà un rilievo `R` col testo `ESITI_MANCATI[esito]`;
   - un orfano (le etichette che `comandi_dei_test` rende al secondo posto) torna al criterio
     confrontando l'etichetta col `file` di ogni sonda, e dà `ESITI_MANCATI["nessuno"]`;
   - un `GuastoDelGate` di `esiti_del_comando()` diventa un **avviso** (`sonda del criterio N: gate
     guasto`), non un'eccezione.

   Il rosso conta come in `--chiedi-impl`: un errore d'import è rosso.
5. **Un criterio dichiarato guardia non ha sonda.** Per gli altri criteri (quelli di `PBI-520`, coi
   loro testi), un criterio senza sonda dà un **avviso** `criterio N senza sonda`, non un rilievo.
   È guardia un criterio il cui testo intero, righe rientrate comprese, contiene «guardia» o «nato
   verde», senza distinguere maiuscole e minuscole.
6. **Il prompt** (`lettore.md`) dà al Lettore:
   - il percorso del PBI e gli avvisi di `PBI-520`;
   - le sette domande di `ADR-0031`, ognuna con l'esempio del 20/10 da cui è nata;
   - la regola: un rilievo è **solo ciò che fermerebbe il giro**, con la prova. Il gusto non è un
     rilievo (la lezione MOLT Sinai di `ADR-0030`).
7. **Il rapporto** è quello di `PBI-520`, con in più:
   - `lettore`: `letto`, `senza esito`, oppure `null` senza `--lettore`;
   - `sonde`: oggetti `{criterio, file, nome, esito}`.

   I rilievi del Lettore e del runner vanno nella stessa lista `rilievi`. Il comando esce 1 se c'è
   almeno un rilievo, oppure con `senza esito`.
8. **Lo scope dei commit è `runner`**, `prompt` per `lettore.md` e `config` per la sezione.

## Dipendenze

- Bloccato da: `PBI-520`, per il comando, il rapporto e i testi dei criteri.
- Blocca: `PBI-522`.

## Contesto

- `decisions/ADR-0031-la-lettura-prima-della-coda.md` — le decisioni 1-3 e 6.
- `tools/asdlc/esito.py`: `STRUMENTI_DEL_SOLVER`, `strumenti()`, `chiama()`, `_scrivi()` (~181) e
  `_risolvi()` (la regola dell'evidenza).
- `tools/asdlc/runner.py`:
  - per l'agente: `comando_del_solver()`, `invoca_agente()`, `cartella_delle_sessioni()`;
  - per l'albero e i test nuovi: `worktree_usa_e_getta()`, `TestNuovo`, `linguaggio_del_test()`;
  - per eseguire le sonde: `comandi_dei_test()`, `esiti_del_comando()`, `ESITI_MANCATI`,
    `chiedi_impl()`.
- `tools/tests/test_asdlc_esito.py` — come si prova il server, e il vincolo della libreria standard.
- Le sezioni «La lettura avversariale del 20/10» di `PBI-514`, `PBI-515`, `PBI-517`, `PBI-518` e
  `PBI-519`: gli esempi delle sette domande.

## Verifica

Il Lettore è finto: uno script che scrive un test nel suo `cwd` e i file della decisione 2. Nessun
test lancia `claude`. Su `main` il ruolo, gli strumenti e il flag non esistono, quindi i criteri
nascono rossi per asserzione (`getattr` più `assert` dove serve).

- [x] **Il server accetta e accumula gli strumenti del Lettore.** Sul server, come i test di `risolvi`:
      - `strumenti("lettore")` dà `rilievo`, `sonda` e `letto`;
      - due `rilievo` validi finiscono tutti e due in `letto`;
      - un `rilievo` con `domanda` fuori da `R F T A E D N`, o con un'evidenza che non è un file
        dell'albero, è rifiutato;
      - dopo `letto` un altro `rilievo` è rifiutato.

      (pytest)
- [x] **Una sonda verde sulla base è un rilievo R, e il Lettore lavora fuori dal checkout.** Un
      repository temporaneo con una funzione che esiste già. Il Lettore finto scrive due sonde: una
      passa sulla base, l'altra chiama una funzione che non c'è. Nel rapporto la prima dà un rilievo
      `R` col testo «nato verde», la seconda ha `esito == "rosso"` e nessun rilievo. **Nello stesso
      test:**
      - il checkout ha lo stesso `git status --porcelain` e gli stessi rami di prima;
      - il file della sonda nel checkout non c'è;
      - `USA_E_GETTA["montati"] == USA_E_GETTA["smontati"]`.

      (pytest)
- [x] **Senza `letto` la lettura è `senza esito`.** Un Lettore finto che scrive solo un `rilievo`
      dà `lettore == "senza esito"`, quel rilievo nel rapporto e nessuna sonda eseguita. Il comando
      esce 1 (pytest).
- [x] **Un criterio senza sonda è un avviso.** Un PBI con tre criteri, uno con la parola «Guardia»
      su una riga rientrata, e una sola sonda per il primo. Il risultato è l'avviso
      `criterio 3 senza sonda`, nessun avviso per il criterio 2 e nessun rilievo (pytest).
- [x] **Il Lettore ha il suo tetto e la sua traccia.** `invoca_agente("lettore", …, cwd=albero)`
      usa `[lettore].minuti`, e cerca la traccia nella cartella delle sessioni di `albero`, non di
      `REPO` (pytest, `esegui` finto come nei test del tetto del 369 e della traccia del 511).
- [x] **`invoca_agente()` senza `cwd` lancia da `REPO`.** È una **guardia**: i test esistenti degli
      agenti restano verdi. Non c'è un test nuovo.

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde. Builder, Critic e Solver lanciano
come prima.

## Dopo il merge (non è un criterio)

La **misura retroattiva**, con un modello vero. Si lancia
`asdlc-runner PBI-N --preverifica --lettore` sulle versioni dei PBI **prima** della #68
(`git show 2bad8ad:backlog/PBI-51x-…`, in un ramo di prova). Deve trovare almeno:

- `R` sul criterio 8 di `PBI-519` e sul criterio 8 di `PBI-517`;
- `R` sul criterio 2 di `PBI-518` e sul criterio 4 di `PBI-514`;
- `R` sui criteri 2, 3, 5 e 7 di `PBI-515`;
- `F` su `PBI-518`.

Sulle versioni di `main` non deve trovare niente. Il risultato va in una nota di `ADR-0031`.

## Protocollo di rifinitura

Si può scegliere senza chiedere:

- il testo del prompt, purché porti le sette domande e la regola della decisione 6;
- i nomi interni delle funzioni.

Si scrive come domanda (e si chiama `fermati`):

- se `comandi_dei_test()` non sa eseguire una sonda nell'albero usa e getta per una ragione diversa
  da quelle di `ESITI_MANCATI`;
- se la CLI rifiuta `Write` nel `cwd` del Lettore;
- se rifiuta il prompt `@<LOG_DIR>/…`, che sta fuori dal `cwd`.

## La lettura avversariale del 20/10

Un lettore in sola lettura ha provato il PBI sul codice di `main` (`be41405`). I rilievi recepiti:

**Avrebbero fermato il giro:**

- il server non può importare `linguaggio_del_test()`, perché è solo libreria standard: il controllo
  del linguaggio passa al runner (decisione 1);
- il vecchio criterio 3, l'albero fuori dal checkout, sarebbe nato verde dopo il GREEN del 2: ora sta
  nel test del criterio 2.

**Erano da correggere:**

- il formato dell'esito accumulato non era scritto (decisione 2);
- mancavano dallo Scope il tetto e la traccia del ruolo, ora nello Scope e nel criterio 5;
- non era detto come un orfano torna al suo criterio, e un gate guasto alzava un'eccezione
  (decisione 4);
- «guardia» su quali righe (decisione 5);
- le graffe del prompt, e `@prompt` fuori dal `cwd` (Protocollo).

**Verificato senza rilievi:**

- il server parte dal `cwd` dell'invocazione;
- l'hook di fase tace nell'albero usa e getta;
- `lettore.md` è coperto da `package-data`;
- nessun test enumera `runner.RUOLI` o i flag.
