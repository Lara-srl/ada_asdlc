# PBI-526: il gate del rosso non vede un test che presidia comportamento SQL

**Stato:** D1 e D2 chiuse da Francesco il 25/10 (*Deciso* qui sotto); **non letto** e **non in coda**.
Si accoda dopo `PBI-524` e `PBI-525`, che toccano `builder.md` e il gate del rosso.

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
- `tools/asdlc/prompt/builder.md` e `tools/asdlc/prompt/rimedio.md` — il paragrafo «Una guardia nasce
  verde, e passa solo se morde» (decisione 4). `tools/asdlc/prompt/critic.md` — la riga della
  decisione 5.
- `decisions/ADR-0022-il-verde-che-morde-passa.md` — la revisione del 25/10, già scritta in
  questa PR: il giro non la tocca.
- `tools/tests/test_asdlc_runner.py` — i test dei criteri.
- `tools/tests/dati/prompt/builder.txt`, `critic.txt`, `rimedio.txt` — i golden, nello stesso commit del
  testo.
- `README.md` — solo se il testo nuovo rende imprecisa la frase sul gate del rosso.
- `backlog/PBI-526-il-gate-del-rosso-non-vede-i-test-di-comportamento-sql.md` — questo file, per la spunta.
- **Fuori scope:** i mutanti SQL (strada C, un altro PBI dopo aver misurato il costo di un database usa e
  getta nel gate); l'esempio di Postgres, che sta in `ada_unical/asdlc-aggiunte/builder.md`; la forma dei
  mutanti per Python e TypeScript; `e_scheletro_vuoto()` e il `pre-commit`
  (`PBI-524`); il Critic (`PBI-525`).

## ✅ Deciso

Francesco, 25/10: **D1 = A con la riga di B; D2 = la regola nel prompt del Builder, l'esempio in
`ada_unical`.** Le domande, con le tre strade, restano nella storia di questo file (`8e472eb`).

1. **La riga è `Verde-per-costruzione: <motivo>`**, nel corpo del commit del test, come `Guardia-su:`:
   `RE_VERDE_PER_COSTRUZIONE = r"^Verde-per-costruzione:\s*(\S.*?)\s*$"`, multilinea. Il motivo è
   testo libero e non vuoto; il gate non lo giudica, lo riporta.
2. **Vale solo con un `.sql` nel ramo.** Se un test nato verde non morde, né al suo commit né alla
   punta, e il suo commit porta la riga, il gate guarda i file che il ramo cambia da `base` alla
   punta (al commit, se la punta manca). Con almeno un file `.sql` fra quelli il test **non** va fra
   i mancati: va in `verdi_dichiarati` con `commit`, `titolo`, `test`, `motivo` e `sql` (i file `.sql`),
   e il giro prosegue. Senza un `.sql` resta fra i mancati come oggi, e la sua lettura aggiunge
   «la riga Verde-per-costruzione vale solo se il ramo tocca un file .sql». Senza la riga, niente
   cambia. È la strada A di `ADR-0008` con la firma di B: si segnala, e chi l'ha scritto lo dice.
3. **Il rapporto e il Critic li vedono.** `Esito` ha `test_verdi_dichiarati`, scritto nel rapporto del
   giro e stampato come i morsi. `gate_per_il_critic()` li elenca sotto un titolo che contiene
   «non verificati: il gate non ha mutanti per l'SQL», ognuno col commit, il test e il motivo.
4. **Il prompt del Builder (e del rimedio)**, nel paragrafo della guardia, dice in quest'ordine: un test
   che nascerebbe verde per costruzione si scrive prima in una forma che possa nascere rossa; se non
   c'è, e il comportamento vive in un file `.sql` che il ramo tocca, il commit porta la riga
   `Verde-per-costruzione: <motivo>`; fuori dall'SQL la riga non serve e il giro si ferma come oggi.
5. **Il Critic legge ogni verde dichiarato** e si chiede se il test fallirebbe togliendo il `GRANT` o il
   `REVOKE` che il motivo nomina. Un test vero comunque è un rilievo di qualità dei test (`critic.md`,
   punto 5), non una nota.
6. **Scope dei commit:** `runner` per `runner.py`, `prompt` per i tre prompt e i golden.

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
- **T** — il golden del prompt contraddice una decisione? (anche `rimedio.txt` e `critic.txt`)
- **N** — i nomi e i fatti citati sono veri nel codice? (le righe di `linguaggio_del_file()`, il testo esatto
  del motivo `rosso-mai-visto`, quale perimetro il gate usa per i test che non uccidono mutanti)

## Verifica

Tutto pytest, sui repository temporanei dei test del gate del rosso (PBI-378, `Guardia-su:`). Su `main`
la riga non si legge: il test nato verde va sempre fra i mancati, e i criteri nascono rossi per
asserzione o per `TypeError` dentro il test.

- [ ] **Un verde dichiarato con un `.sql` nel ramo passa e si scrive.** Un ramo che aggiunge un `GRANT` in
      `db/schema.sql` e un test che nasce verde, senza mutanti che lo uccidano, il cui commit porta la riga
      con un motivo: `esamina_il_commit()` non lo mette fra i mancati, e la voce in `verdi_dichiarati`
      porta quel motivo e `db/schema.sql` in `sql`.
- [ ] **Senza un `.sql` nel ramo la riga non basta, e la lettura lo dice.** Lo stesso test con la riga
      in un ramo che tocca solo `.py`: resta fra i mancati, e la sua lettura contiene «Verde-per-costruzione»
      e «.sql».
- [ ] **Il Critic vede i verdi dichiarati.** `gate_per_il_critic()` con un verde dichiarato contiene
      «non verificati», il commit e il motivo; senza, non contiene «non verificati». `Esito` ha il campo
      `test_verdi_dichiarati`, e il rapporto del giro lo scrive.
- [ ] **I prompt dicono la regola.** `builder.md` e `rimedio.md` contengono `Verde-per-costruzione: <motivo>`
      e «possa nascere rossa»; `critic.md` contiene «Verde-per-costruzione». Oggi nessuno dei tre la
      contiene.

**Non regressione:**
- `python3 -m pytest -q tools/tests` resta verde.
- I test esistenti del gate del rosso restano verdi senza modifiche: è la **guardia** che un nato verde
  senza la riga, con o senza `.sql`, ferma il giro come oggi.
