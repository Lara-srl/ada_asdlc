# PBI-526: il gate del rosso non vede un test che presidia comportamento SQL

**Stato:** bozza, con le domande aperte (❓) qui sotto: non si accoda finché Francesco non le chiude.

## Direttiva

Un fermo meccanico di `ada_unical` (`PBI-003`, giro 1, 25/10/2026, 5 min 45 s): il giro si è chiuso
`fermato`, motivo `rosso-mai-visto`, con 40 commit sul ramo, di cui uno solo segnalato dal gate.

Il commit incriminato è `7a6a15e`, `test_etl_non_legge_viste_e_funzioni`: verifica che il ruolo `etl`
non possa leggere le viste né chiamare le due funzioni (`SET ROLE etl`, poi `pytest.raises(InsufficientPrivilege)`).
Il criterio del PBI lo chiede («`etl` no»), il Builder l'ha scritto e l'ha dichiarato nel messaggio del
commit («Nato verde»). Il gate l'ha rifiutato:

> nato verde e non morde, né al suo commit né alla punta: 23 mutanti provati nelle funzioni che il
> branch ha toccato non lo fanno fallire

**Il difetto ha due metà.**

1. **Un test che nega un permesso nasce verde per costruzione.** Un ruolo senza `GRANT` non legge una
   vista nuova: non c'è un'implementazione da scrivere perché il test diventi verde, e quindi non c'è un
   rosso da vedere prima. Non è un errore del Builder.
2. **Il gate non ha mutanti per l'SQL.** `linguaggio_del_file()` conosce `python` e `vitest`; i mutanti
   (`mutanti_del_sorgente()`) sono righe cancellate e operatori scambiati in file `.py`/`.ts`. Un `GRANT`
   cancellato in `db/schema.sql` non è un mutante, e `Guardia-su: <percorso>::<funzione>` nomina
   funzioni di quei linguaggi. Per questo il gate non può mai concludere che una guardia su un
   comportamento che vive in `db/schema.sql` «morde»: il suo perimetro è fatto di funzioni Python
   che quella guardia non guarda.

Il giro si è fermato «ex ante e nessuna fix lo annulla» (`rosso-mai-visto`): il commit non si può
correggere dopo, perché il ciclo RED→GREEN non è mai stato visto in quel punto della storia. Il ramo
si è chiuso con `asdlc-chiudi-giro` (tag `giro-fermato/pbi-003-giro1-20261025`) e il PBI è ripartito da
zero, dopo che chi gestisce il progetto ha riscritto il criterio perché il rosso ci fosse.

**Il rimedio di progetto che ha funzionato.** Un test che interroga i cataloghi invece di eseguire
la lettura: `has_function_privilege('etl', 'fermi_da(int)', 'EXECUTE')` è `true` finché lo schema non
ha `REVOKE EXECUTE ON FUNCTION … FROM PUBLIC`, perché Postgres dà `EXECUTE` a `PUBLIC` alla creazione.
È un rosso vero, ma solo per le funzioni: `has_table_privilege` su una vista è `false` fin dalla nascita.
Il rimedio non vale in generale, perché non sempre c'è un default permissivo da revocare.

**Scope**

- `tools/asdlc/runner.py` — il punto in cui il gate decide `rosso-mai-visto` per un test che non è mai
  stato rosso e non ha ucciso nessun mutante: la decisione 1 dice che cosa succede quando il test
  presidia un file `.sql`.
- `tools/asdlc/prompt/builder.md` — il paragrafo «Una guardia nasce verde, e passa solo se morde»: dice
  cosa fare quando il comportamento presidiato vive in SQL.
- `tools/tests/test_asdlc_runner.py` — i test dei criteri.
- `tools/tests/dati/prompt/builder.txt` — il golden del prompt, nello stesso commit del testo.
- `README.md` — solo se il testo nuovo rende imprecisa la frase sul gate del rosso.
- `backlog/PBI-526-il-gate-del-rosso-non-vede-i-test-di-comportamento-sql.md` — questo file, per la spunta.
- **Fuori scope:** la forma dei mutanti per Python e TypeScript; `e_scheletro_vuoto()` e il `pre-commit`
  (`PBI-524`); il Critic (`PBI-525`).

## ❓ Domande aperte

**D1. Che cosa fa il gate con una guardia su un file `.sql`?** Tre strade, in ordine di costo:

- **A. Segnala e lascia passare.** Se il test nuovo nasce verde e il perimetro del branch contiene un
  `.sql` che il test nomina o legge (il file è nel diff), il gate non ferma il giro: scrive nel
  rapporto «non verificabile: nessun mutante per l'SQL» e passa la guardia al Critic. È la strada di
  `ADR-0008` (si segnala, non si blocca) e non richiede di eseguire SQL. Rischio: una guardia che non
  guarda niente passa senza che nessuno se ne accorga, se il Critic non la legge.
- **B. Una dichiarazione del Builder.** Una riga `Verde-per-costruzione: <motivo>` nel corpo del
  commit, come `Guardia-su:`, che il gate legge e riporta nel rapporto. Il Builder si assume la
  responsabilità per iscritto; senza la riga il giro si ferma come oggi. Rischio: diventa una
  formula che si scrive sempre.
- **C. Mutanti SQL.** Cancellare un `GRANT` o scambiare `GRANT`/`REVOKE` in `db/schema.sql` e rieseguire
  il test. È l'unica che dimostra che la guardia morde, ma il gate dovrebbe ricaricare lo schema in
  un database usa-e-getta a ogni mutante: oggi il worktree del gate non porta con sé un database, e la
  forma dello schema è del progetto, non del runner.

Raccomando **A**, con la riga di **B** come condizione per non fermarsi in silenzio. **C** è un altro PBI,
dopo che il costo di un database usa-e-getta nel gate è stato misurato. Non scelgo io: la decisione 1
di `PBI-524` («non allargare il lucchetto») e `ADR-0008` tirano in direzioni diverse su quanto il gate
debba fermare.

**D2. Il prompt dice di scrivere il test in modo che il rosso ci sia, quando si può?** Il rimedio di
progetto (cataloghi invece di esecuzione) è una buona pratica per i permessi di Postgres. Si scrive in
`builder.md` come esempio, oppure resta nelle aggiunte del progetto (`asdlc-aggiunte/`)?

## Contesto

- `ada_unical`: `runs/20261025-201606.json` (voce `commit_senza_rosso`, commit `7a6a15e`), tag
  `giro-fermato/pbi-003-giro1-20261025` (la testa `69ffeab`, con le 40 commit).
- `ada_unical`: `backlog/PBI-003-viste-e-libreria-di-calcolo.md`, il criterio sul ruolo `etl` dopo il
  commit `d8cbf15` (il rimedio con `has_function_privilege`).
- `tools/asdlc/runner.py`: `linguaggio_del_file()`, `mutanti_del_sorgente()`, `lettura_del_verde()`,
  il motivo `rosso-mai-visto`.
- `tools/asdlc/prompt/builder.md`: «Una guardia nasce verde, e passa solo se morde» e `Guardia-su:`.
- `ADR-0008` (osserva e segnala), `ADR-0021` (il rosso si chiede prima).

**Prima di accodare, rileggi:**
- **R** — ogni criterio può nascere rosso su `main`?
- **T** — il golden del prompt contraddice una decisione?
- **N** — i nomi e i fatti citati sono veri nel codice? (le righe di `linguaggio_del_file()`, il testo esatto
  del motivo `rosso-mai-visto`, quale perimetro il gate usa per i test che non uccidono mutanti)

## Verifica

I criteri si scrivono quando D1 è chiusa: dipendono dalla strada scelta.

- [ ] *(da scrivere dopo D1)* Un test nato verde il cui perimetro contiene solo `.sql` non ferma il giro
      con `rosso-mai-visto` e il rapporto dice perché non è verificabile.
- [ ] *(da scrivere dopo D1)* Un test nato verde con un `.py` nel perimetro e nessun mutante ucciso
      continua a fermare il giro.

**Non regressione:**
- `python3 -m pytest -q tools/tests` resta verde.
- I test esistenti del gate del rosso restano verdi senza modifiche.
