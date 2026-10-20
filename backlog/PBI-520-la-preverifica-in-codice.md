# PBI-520: la pre-verifica in codice, e il comando che la lancia

**Stato:** proposto, letto il 20/10 (vedi in fondo). È il primo di tre: 520, 521, 522 (`ADR-0031`).

## Direttiva

Francesco ha fissato un obiettivo (20/10): **il runner non si ferma per motivi meccanici**. Il 20/10
cinque PBI sono passati da una lettura avversariale (#68), e dopo quella lettura tutti e cinque hanno
chiuso al primo giro. Prima di quella lettura, circa metà dei fermi si poteva trovare prima del
lancio (`ADR-0031`, Contesto). Quel controllo però lo fa solo chi scrive il PBI, e nessun codice legge
la `Verifica` di un PBI.

Questo PBI dà al runner la parte del controllo che non ha bisogno di un modello, e un comando che la
lancia: `asdlc-runner PBI-N --preverifica`. Il comando legge il file del PBI così com'è alla base e
scrive un rapporto con:

- i **rilievi di forma**: manca la `Verifica`, non ci sono criteri, manca lo **Scope**, lo Scope non
  nomina il file del PBI;
- gli **avvisi**: un percorso dello Scope che non esiste sulla base, una dipendenza non spuntata, uno
  Scope fatto solo di test.

Il comando esce 1 se c'è almeno un rilievo, altrimenti 0. Gli avvisi non cambiano il codice d'uscita:
li legge il Lettore (`PBI-521`).

**Scope**

- `tools/asdlc/runner.py`:
  - il dataclass `Rilievo`;
  - la funzione pura `forma_del_pbi(testo, pbi)`;
  - `avvisi_della_base(testo, pbi, base)`;
  - il parser dello Scope e quello dei criteri;
  - il flag `--preverifica`, smistato in `smista()`;
  - il rapporto.
- `tools/tests/test_asdlc_preverifica.py` — **nuovo**: i test dei criteri.
- `README.md` — il flag nuovo, dove il README elenca gli altri, nello stesso commit del codice.
- `backlog/README.md` (la sezione sul formato, ~31) e `template/backlog/TEMPLATE.md` (dentro
  `## Contesto`) — le sette domande, secondo la decisione 6.
- `backlog/PBI-520-la-preverifica-in-codice.md` — questo file, per la spunta.

**Fuori scope**

- Il Lettore e le sonde del rosso (`PBI-521`).
- La pre-verifica dentro il giro e nel tick (`PBI-522`): qui il giro non cambia.
- Gli avvisi trasformati in rilievi. La ragione è la misura in `ADR-0031`, decisione 1.
- `avviso_domande()` del tick e la sezione `❓`.

## ✅ Deciso

1. **Il testo del PBI si legge alla base.** Si usa `git show <base>:<percorso>`, dove il percorso è
   quello che `trova_pbi(pbi, base)` rende, relativo a `REPO`. Non si legge il file dell'albero:
   `trova_pbi` rende `REPO/<nome>` (~3984), cioè l'albero di lavoro. La base è quella di
   `base_del_giro()`, che **fa** `git fetch` (~3954) e tollera un fetch fallito con un avviso.
2. **I rilievi di forma sono una funzione pura del testo**, `forma_del_pbi(testo, pbi)`, senza git.
   Sono quattro, ognuno con `domanda = "forma"` e `criterio = None`:
   - non c'è nessuna riga `## Verifica`, ancorata a inizio riga;
   - la sezione `## Verifica` c'è ma non contiene righe `^\s*- \[[ x]\]`. Questo rilievo non si
     controlla se manca la sezione;
   - non c'è nessun blocco `**Scope**`;
   - il blocco **Scope** c'è ma non contiene `backlog/PBI-<n>` seguito da un carattere che non è una
     cifra. La regola accetta il nome abbreviato `PBI-514-…md` e non scambia `PBI-52` per `PBI-520`.
     Questo rilievo non si controlla se manca il blocco.

   Un PBI senza `## Verifica` dà quindi **un** rilievo, e uno senza Scope ne dà **uno**.
3. **I criteri** sono le righe `^\s*- \[[ x]\]` **dentro** la sezione `## Verifica`, cioè fino alla
   `## ` successiva ancorata. Ogni criterio comprende anche le sue righe rientrate. La funzione che li
   legge rende **i testi**, non solo il conto: `PBI-521` ne ha bisogno.
4. **Il blocco dello Scope** si legge con la regex di `controllo_r7()` (~4719), estratta in una
   funzione che `controllo_r7()` usa. **L'estrazione sta nel commit GREEN del primo criterio**, in
   `IMPL`. Non va in un commit `refactor` a parte, perché dopo ogni commit l'hook `post-commit`
   rimette il giro in `TEST_ONLY` (`RITORNO_IN_TEST_ONLY`, ~5152), e `runner.py` si richiude.
5. **Gli avvisi**, in `avvisi_della_base(testo, pbi, base)`, sono tre:
   - **un percorso tra backtick dello Scope** che contiene `/`, non contiene spazio, `*`, `<`, `>`,
     `{`, `}` né `…`, e non esiste alla base (`git cat-file -e <base>:<percorso senza la / finale>`),
     purché la sua riga non contenga «nuov»;
   - **una dipendenza**: un `PBI-NNN` della riga `Bloccato da:` il cui file alla base non c'è, oppure
     ha un `- [ ]` **dentro la sua `## Verifica`**;
   - **uno Scope solo di test**: tolti il file del PBI e le cartelle (i percorsi che finiscono con
     `/`), resta almeno un percorso e sono tutti test per `e_file_di_test()`.
6. **Le sette domande nel formato.** In `template/backlog/TEMPLATE.md` vanno **dentro `## Contesto`**,
   come un paragrafo in grassetto, `**Prima di accodare, rileggi:**`, seguito da sette voci `- ` (non
   `- [ ]`). Non si aggiunge nessuna `##`, perché `test_il_modello_dei_pbi_ha_le_sezioni_del_formato_nell_ordine`
   (`test_asdlc_template.py`, ~182) vuole l'elenco esatto delle sezioni. Le voci non hanno la casella:
   ogni PBI futuro le copierebbe, e il conto dei criteri si sporcherebbe. Le stesse sette righe vanno
   in `backlog/README.md`, sotto il formato. È documentazione, e nessun test la legge.
7. **Il comando.** `--preverifica` si smista in `smista()` **prima** di `mancanze_dell_ambiente()`,
   `stacca()` e `lucchetto()` (~5413-5440), come `--gate-rosso`. Gira in primo piano e il codice
   d'uscita resta al chiamante. Non crea rami né commit, non cambia la fase, e non scrive file fuori
   da `LOG_DIR`.
8. **Il rapporto** è `LOG_DIR/<run>-<PBI>-preverifica.json` e contiene:
   - `pbi`, `base`;
   - `sha_pbi`, cioè `git rev-parse <base>:<percorso>`;
   - `criteri`, il loro numero;
   - `rilievi`, una lista di `{domanda, criterio, testo, evidenza}`;
   - `avvisi`, una lista di stringhe.

   **Non ha la chiave `esiti`**: `ultimo_esito()` del tick, `esiti_dei_rapporti()`, `registra()` e
   `chiudi_giro` lo ignorano.
9. **Lo scope dei commit è `runner`**, e `template` per il TEMPLATE (`ADR-0028`).

## Dipendenze

- Bloccato da: nessuno. `PBI-519` è in `main` (`v0.5.0`).
- Blocca: `PBI-521`, `PBI-522`.

## Contesto

- `decisions/ADR-0031-la-lettura-prima-della-coda.md` — la decisione e la misura degli avvisi.
- `decisions/ADR-0022-il-verde-che-morde-passa.md`, nota del 23/09 — il controllo sulla base.
- `tools/asdlc/runner.py`:
  - `trova_pbi()`, `base_del_giro()`, `controllo_r7()`, `e_file_di_test()`;
  - `smista()` e il ramo di `--gate-rosso`;
  - `RITORNO_IN_TEST_ONLY`.
- Come i test lanciano un flag: `monkeypatch.setattr(sys, "argv", [...])` e `runner.smista()`
  (`test_asdlc_runner.py`, ~5366). La fixture `log_dir_temporanea` (`conftest.py`, ~96) sposta
  `LOG_DIR`.
- Il repository con un remoto vero (bare più clone): `test_asdlc_limite_d_uso.py`, ~233.

## Verifica

Su `main` le funzioni e il flag non esistono. I test le prendono con
`getattr(runner, "…", None)` e un `assert`, così il rosso è **per asserzione**
(`backlog/README.md`). Ogni criterio nasce rosso, tranne le guardie, che sono dichiarate.

- [ ] **I quattro rilievi di forma.** È un test parametrico su `forma_del_pbi(testo, pbi)`, con un
      id per caso. Ogni caso dà **un solo** rilievo, con `domanda == "forma"`:
      - un PBI senza `## Verifica`;
      - un PBI con la `Verifica` senza criteri;
      - un PBI senza **Scope**;
      - un PBI con lo Scope che non nomina `backlog/PBI-<n>`.

      Nello **stesso test**, il caso con `backlog/PBI-<n>-…md` abbreviato non dà rilievi, e
      `backlog/PBI-52` non vale per `PBI-520` (pytest).
- [ ] **Gli avvisi non sono rilievi.** Un repository con remoto bare e un clone, con i commit fatti
      `--no-verify`. `avvisi_della_base()` dà un avviso per ognuno di questi tre casi:
      - un percorso dello Scope che non c'è e non è detto nuovo;
      - un `Bloccato da: PBI-<m>` con un `- [ ]` nella `Verifica` di `<m>`;
      - uno Scope di soli `tools/tests/…`.

      Nello **stesso test**: la stessa riga di percorso con «— **nuovo**» non dà avvisi, e un
      `- [ ]` di `<m>` fuori dalla sua `Verifica` non conta (pytest).
- [ ] **`--preverifica` scrive il rapporto e non tocca l'albero.** Lo stesso repository, con
      `runner.REPO` puntato al clone. `sys.argv` e `runner.smista()` lanciano
      `PBI-<n> --preverifica`. Il codice d'uscita è 1 con un rilievo e 0 senza. Il rapporto in
      `LOG_DIR` ha le chiavi della decisione 8, con `sha_pbi == git rev-parse <base>:<file>` e senza
      `esiti`. `git branch` e `git status --porcelain` del clone sono uguali a prima (pytest).
- [ ] **`controllo_r7()` non cambia.** È una **guardia**: i suoi test esistenti restano verdi. Non
      c'è un test né un commit nuovi, perché l'estrazione sta nel GREEN del primo criterio.
- [ ] **I PBI di `main` non danno rilievi di forma.** È una **guardia**, e nasce verde dopo il GREEN
      del primo criterio. Legge dal disco ogni `backlog/PBI-5*.md` del repository e si aspetta zero
      rilievi da `forma_del_pbi()`, senza git e senza rete. Porta
      `@pytest.mark.progetto_ospite`. Si committa da sola con
      `Guardia-su: tools/asdlc/runner.py::forma_del_pbi` e deve mordere (pytest). È la misura di
      `ADR-0031`: se fallisce, una regola di forma è diventata un fermo falso.

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde. Il giro, il tick e
`controllo_r7()` si comportano come prima.

## Protocollo di rifinitura

Si possono scegliere senza chiedere:

- i nomi interni dei parser;
- il testo degli avvisi;
- l'ordine delle chiavi nel rapporto.

Si scrive come domanda, e si chiama `fermati`:

- una regola di forma che, scritta come sopra, dà un rilievo su un PBI di `main`;
- un percorso per cui la decisione 5 non basta a dire se è un avviso.

## La lettura avversariale del 20/10

Un lettore in sola lettura ha provato il PBI contro il codice di `main` (`be41405`). Questi rilievi
sono stati verificati nel codice e recepiti.

**Avrebbero fermato il giro:**

- il commit `refactor` dopo il GREEN non si poteva fare, perché l'hook `post-commit` rimette il giro
  in `TEST_ONLY`. L'estrazione ora sta nel GREEN (decisione 4);
- un nuovo `## Prima di accodare` rompeva il test delle sezioni del TEMPLATE, e le caselle `- [ ]`
  avrebbero sporcato i criteri (decisione 6);
- le regole di forma davano due rilievi dove il criterio ne voleva uno (decisione 2).

**Erano da correggere:**

- `base_del_giro()` fa `fetch`, e `trova_pbi` legge l'albero di lavoro (decisione 1);
- la guardia sui PBI di `main` non deve usare git né rete (decisione 2 e criterio 5);
- `main()` non prende `argv`, e il flag va smistato prima di `stacca()` (decisione 7);
- il caso negativo stava in un test a sé, e sarebbe nato verde (criteri 1 e 2);
- la regola `PBI-52` contro `PBI-520` (decisione 2);
- il rosso deve essere per asserzione, quindi `getattr` e `assert`.

Verificato senza rilievi: un rapporto senza `esiti` è ignorato da tutti i lettori dei rapporti, e il
prototipo delle regole di forma dà zero rilievi sui PBI da 500 a 519.
