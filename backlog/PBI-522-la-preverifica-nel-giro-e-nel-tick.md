# PBI-522: la pre-verifica nel giro, e il tick che non rilancia un PBI da correggere

**Stato:** giro 1 fermato su una domanda del Protocollo, risposta e ripresa nel giro 2 (vedi in fondo).
Letto il 20/10. Terzo di tre: 520, 521, 522 (`ADR-0031`).

## Direttiva

Con `PBI-520` e `PBI-521` la pre-verifica esiste, ma si lancia a mano. Senza un comando che la faccia
girare da sé si torna al punto di partenza: il controllo dipende da chi si ricorda di farlo.

Questo PBI mette la pre-verifica **dentro il giro, prima del ramo** (`ADR-0031`, decisione 4). Dopo il
controllo dell'albero pulito, `esegui_pbi()` lancia la pre-verifica sul PBI della base:

- **con almeno un rilievo** il giro chiude `fermato` col motivo `preverifica`. Non nascono ramo,
  commit né PR, e il Solver non parte;
- **senza rilievi** il giro va avanti come oggi.

Il tick legge l'ultimo rapporto e non rilancia il PBI finché il suo file non cambia su `main`. Quando
una persona lo corregge e la correzione arriva su `main`, il tick rilancia da solo.

**Scope**

- `tools/asdlc/runner.py`:
  - `esegui_pbi()`: la pre-verifica, fra il controllo dell'albero e `inventario()`;
  - due righe in `USCITE`;
  - i campi `sha_pbi` e `rilievi_preverifica` in `Esito`.
- `tools/asdlc/config.py`:
  - la sezione `[preverifica]` con `attiva` (default `false`) e `lettore` (default `true`);
  - un `default` per `_Sezione.booleano()`, che oggi non ce l'ha (~562).
- `asdlc.toml` e `template/asdlc.toml` — `[preverifica] attiva = true`. In questo repository conta
  solo dopo il tag: il tick gira col pacchetto installato (`ADR-0026`).
- `tools/asdlc/coda.py`:
  - `decidi()`, con la decisione nuova `AttendeLaPreverifica`;
  - la riga del log in `racconta()`.
- `tools/tests/test_asdlc_preverifica_nel_giro.py` — **nuovo**: i test dei criteri.
- `tools/tests/test_asdlc_runner.py` — **solo** i due casi nuovi di `USCITE_DEL_GIRO` (~9293), nel
  commit RED del primo criterio (decisione 5).
- `README.md`, `backlog/AUTOMAZIONE.md`, `specs/solver-e-rilascio/spec.md` — dove descrivono
  l'ingresso del giro e le decisioni del tick, nello stesso commit del codice.
- `backlog/PBI-522-la-preverifica-nel-giro-e-nel-tick.md` — questo file, per la spunta.

**Fuori scope**

- Le regole della pre-verifica: sono di `PBI-520` e `PBI-521`.
- Accendere `[preverifica]` in `ada_planning`, `ada_dispense` e aDa. È un gesto da fare dopo il tag,
  nel loro `asdlc.toml`, insieme al pin.
- La pre-verifica nel `--dry-run`.
- **La riga «non lanciato» del tick.** Una pre-verifica senza Lettore chiude prima dei 15 secondi di
  `ATTESA_DEL_DISTACCO` (`coda.py`, ~695), e `lancia()` scrive «il runner si è staccato e poi si è
  fermato». Il tick successivo legge il rapporto e decide giusto. È un limite dichiarato, non un fermo.

## ✅ Deciso

1. **Spenta di default nel pacchetto.** Se la sezione manca, `[preverifica].attiva` vale `false`.
   Circa 90 test chiamano `esegui_pbi()` con PBI finti di poche righe e `git` finto: con la
   pre-verifica accesa si fermerebbero tutti. La pre-verifica si accende nell'`asdlc.toml` di ogni
   progetto, come `[junit]` (`PBI-505`). `tools/tests/dati/progetto/asdlc.toml` non cambia.
2. **Dove e quando.** In `esegui_pbi()` subito dopo il controllo `albero-sporco-all-ingresso`, e prima
   di `inventario()` e di `crea_branch`. Lavora sul PBI alla base, con le funzioni di `PBI-520`. Se
   `[preverifica].lettore` è `true` aggiunge il Lettore di `PBI-521`. **Non gira con `--riprendi`.**
3. **Una lettura per versione.** La pre-verifica non rigira, e il giro prosegue, se fra i rapporti
   `LOG_DIR/*-<PBI>-preverifica.json` ce n'è uno con:
   - lo stesso `sha_pbi`;
   - nessun rilievo;
   - col Lettore acceso, `lettore == "letto"`.

   (`ADR-0031`, decisione 7)
4. **Le uscite sono due.**
   - `"preverifica": ("fermato", "pre-verifica: il PBI ha dei rilievi prima del ramo")`. Il dettaglio
     porta il numero dei rilievi e il percorso del rapporto. L'`Esito` porta `sha_pbi` e
     `rilievi_preverifica`.
   - `"lettore-senza-esito": ("senza esito", "il lettore non ha fatto nessuna chiamata valida")`.
     Vale per un Lettore senza `letto`, che sia per un tetto scaduto o per il limite d'uso. Con il
     limite d'uso e l'ora leggibile l'`Esito` porta `riprendi_dopo`, come il Builder (`PBI-519`).
     **Non** è un fermo da correggere nel PBI.

   Nessuno dei due motivi sta in `BLOCCHI`, quindi il Solver non parte.
5. **Il test della tabella.** `test_ogni_motivo_della_tabella_ha_il_suo_caso` (~9371) chiede
   `set(USCITE) == set(USCITE_DEL_GIRO)`. Il commit RED del primo criterio aggiunge i due casi in
   `USCITE_DEL_GIRO`, con un `percorri` che accende la sezione. In `IMPL` quel file è chiuso, quindi i
   casi non possono arrivare dopo. `Config` è `frozen` (`config.py`, ~39), quindi la sezione si accende
   con `monkeypatch.setattr(runner, "CFG", dataclasses.replace(runner.CFG, preverifica=…))`, non
   assegnando il campo.
6. **Il tick.** In `decidi()`, quando `prossimo()` dà `Lancia` senza `riprendi`, si legge
   `ultimo_esito(worktree, pbi)`:
   - con `motivo == "preverifica"` si calcola, **solo allora**, `git rev-parse HEAD:<percorso del
     PBI>` nel checkout del tick, che `allinea()` ha portato su `main`. Si usa `rev-parse` e non
     `hash-object` del file: una modifica non committata non deve far rilanciare. Se lo sha è uguale a
     `sha_pbi`, la decisione è `AttendeLaPreverifica(pbi, rilievi_preverifica)` e la riga dice
     `attende: preverifica PBI-N — <n> rilievi, correggi il PBI`. Se è diverso, la decisione resta
     `Lancia`;
   - con `motivo == "lettore-senza-esito"` e `riprendi_dopo` nel futuro, la decisione è
     `AttendeIlReset`, cioè `riprendi_dopo()` di `PBI-519`. Altrimenti resta `Lancia`.

   Non è un blocco: la coda resta su quel PBI come per `Attende`, e il tick successivo rilegge
   (`ADR-0008`).
7. **Lo scope dei commit:** `runner`, `coda` per il tick, `config` per la sezione.

## Dipendenze

- Bloccato da: `PBI-520`, `PBI-521`.
- Dopo questo, a mano:
  - il tag `v0.6.0`;
  - i pin nei quattro repository;
  - `[preverifica] attiva = true` nei loro `asdlc.toml`.

## Contesto

- `decisions/ADR-0031-la-lettura-prima-della-coda.md`: le decisioni 4, 5 e 7, e le quattro domande.
- `tools/asdlc/runner.py`: `esegui_pbi()`, `USCITE`, `BLOCCHI`, `Esito`, `limite_d_uso()`.
- `tools/asdlc/coda.py`: `decidi()`, `prossimo()`, `ultimo_esito()`, `riprendi_dopo()`, `racconta()`,
  `allinea()`.
- `tools/asdlc/config.py`: `[junit]` come modello di una sezione opzionale, e `_Sezione.booleano()`.
- **L'impianto dei test con `git` vero.** `giro_col_limite` (`test_asdlc_limite_d_uso.py`, ~84) usa un
  remoto bare e un clone, e sostituisce `smista_il_blocco` e `pubblica`. I test esistenti di
  `esegui_pbi()` hanno `git` finto, che risponde `""` a tutto, e non bastano per «`git branch`
  invariato». Per il tick: `mondo()` in `test_asdlc_coda.py` (~270) risponde a ogni `git`.

## Verifica

I test accendono `[preverifica]` solo per sé (decisione 5). Usano il Lettore finto di `PBI-521`,
oppure `lettore = false`. Su `main` la sezione e le uscite non esistono.

- [ ] **Con un rilievo il giro si ferma prima del ramo.** Con `attiva = true`, `lettore = false` e un
      PBI senza `## Verifica`, `esegui_pbi()` dà:
      - `motivo == "preverifica"` e `stato == "fermato"`;
      - `sha_pbi` valorizzato e `rilievi_preverifica == 1`.

      Inoltre il Builder finto non è stato invocato, `git branch` è uguale a prima ed `e.solver` è
      vuoto (pytest, `git` vero). **Il GREEN di questo criterio è solo la parte in codice:** il Lettore
      entra col criterio 2.
- [ ] **Col Lettore acceso, il Lettore gira prima del Builder.** Con `lettore = true`, un PBI in forma
      e il Lettore finto che chiama solo `letto`, il Lettore è invocato **una** volta e il Builder
      finto dopo di lui (pytest).
- [ ] **Un Lettore senza esito non è un PBI da correggere.** Il Lettore finto esce 1 con il limite
      d'uso nello stderr e non chiama `letto`. Il giro dà `motivo == "lettore-senza-esito"` con
      `riprendi_dopo`, e `decidi()` dà `AttendeIlReset`, non `AttendeLaPreverifica` (pytest).
- [ ] **La stessa versione non si rilegge.** Due giri di fila sullo stesso PBI pronto: il Lettore
      finto è invocato una volta. Dopo una modifica al file del PBI, committata e portata sulla base,
      è invocato di nuovo (pytest).
- [ ] **Il tick non rilancia un PBI da correggere.** Con un ultimo esito `preverifica` e lo stesso
      sha di `git rev-parse HEAD:<file>` nel checkout, `decidi()` dà `AttendeLaPreverifica`, e la riga
      di `racconta()` contiene `attende: preverifica`. Con lo sha cambiato dà `Lancia`. Una modifica
      non committata al file del PBI nel checkout non cambia la decisione (pytest).
- [ ] **`--riprendi` non lancia la pre-verifica.** È una **guardia**: su `main` è vera, perché la
      pre-verifica non c'è. Nasce verde dopo il GREEN del primo criterio. Si committa da sola con
      `Guardia-su: tools/asdlc/runner.py::esegui_pbi`, e deve mordere (pytest).

**Non regressione:**

- `python3 -m pytest -q tools/tests` resta verde.
- Con `[preverifica]` assente il giro è quello di oggi: i test esistenti di `esegui_pbi()` passano
  senza modifiche.
- L'unico test esistente che cambia è `USCITE_DEL_GIRO` (decisione 5).

## Protocollo di rifinitura

Si può scegliere senza chiedere:

- il testo delle righe del log, purché contenga `attende: preverifica` e il numero dei rilievi;
- il nome della decisione del tick.

Si scrive come domanda (e si chiama `fermati`):

- se l'ordine fra la pre-verifica e `inventario()` cambia ciò che il giro registra dei residui;
- se un caso fa divergere `sha_pbi` della base del giro dallo sha nel checkout del tick, per un PBI
  che non è cambiato.

## La lettura avversariale del 20/10

Un lettore in sola lettura ha provato il PBI sul codice di `main` (`be41405`). Ha portato rilievi di
tre tipi, tutti recepiti.

**Avrebbero fermato il giro:**

- il GREEN rompeva `test_ogni_motivo_della_tabella_ha_il_suo_caso`, e in `IMPL` quel file è chiuso.
  I casi ora entrano nel commit RED (decisione 5);
- un Lettore `senza esito`, per esempio per il limite d'uso, avrebbe fermato la coda finché qualcuno
  non riscriveva il PBI, cioè un fermo meccanico. Ora ha un'uscita sua, che si riprende dopo il reset
  (decisione 4, criterio 3).

**Erano da correggere:**

- `hash-object` dell'albero faceva rilanciare il PBI, e pagare il Lettore, a ogni tick, per una
  modifica non committata. Ora si usa `rev-parse HEAD:` (decisione 6);
- `Config` è `frozen`, e `booleano()` non ha un default (Scope, decisione 5);
- il campo `rilievi` si confondeva con la lista del rapporto: ora è `rilievi_preverifica`;
- l'impianto dei test serve con `git` vero (Contesto);
- il GREEN del criterio 1 non deve contenere il Lettore, o il criterio 2 nascerebbe verde;
- la riga «non lanciato» sotto i 15 secondi (Fuori scope).

**Verificato senza rilievi:**

- con `attiva` assente i test esistenti di `esegui_pbi()` restano intatti;
- le sezioni sconosciute non rompono la lettura dell'`asdlc.toml` ospite.

## Il giro 2, e cosa si riprende

Il giro 1 (20/10, run `20261020-230508`, 18 minuti) ha fatto **tutto il lavoro** del PBI: i sei
criteri con le loro coppie RED→GREEN (il 3 in due coppie, runner e coda), il 6 come guardia con
`Guardia-su: tools/asdlc/runner.py::esegui_pbi`. La suite dava `1187 passed` e l'albero era pulito.
Si è fermato alla fine, senza spuntare la Verifica, con la prima domanda del Protocollo di
rifinitura: l'ordine fra la pre-verifica e `inventario()` cambia ciò che il giro registra dei
residui, ma solo in due casi di guasto del Lettore:

- (a) un albero usa e getta del Lettore che `git worktree remove` non smonta entra
  nell'inventario d'inizio come «residuo dei giri prima», e non conta come «albero usa e getta
  montato e non smontato», perché `contati = Counter(USA_E_GETTA)` si fotografa dopo;
- (b) un file che il Lettore scrivesse nel worktree del giro, fuori dal suo albero, arriva dopo il
  controllo dell'albero pulito: il Builder partirebbe su un albero sporco.

Sulla seconda domanda (uno `sha_pbi` diverso fra la base del giro e il checkout del tick) il
Builder non ha trovato casi, e non serve risposta. Il giro è chiuso col tag
`giro-fermato/pbi-522-giro1-20261020` (`17d93b3`).

**Risposta di Francesco (21/10): la (0).** L'ordine della decisione 2 resta com'è, e i due casi
sono un **limite dichiarato** di questo PBI. Le due correzioni proposte dal Builder, il conteggio
`contati` prima della pre-verifica e un secondo `git status --porcelain` dopo, sono
`PBI-523`, non questo. In questo giro non si tocca `esegui_pbi()` e non si aggiunge nessun test.

**Si riprendono i dodici commit del tag**, rimessi sul ramo del giro con `git cherry-pick -x` in
ordine. Sono tutti sopra `9537640`, la base del giro 1, e nessuno tocca `backlog/`, quindi passano
anche se `main` si è mosso dopo (si è mosso solo per questo file).
Sul tag, verificato il 21/10 in un albero in `/tmp`: `python3 -m pytest -q tools/tests` dà
`1187 passed`, `git status --porcelain` è vuoto dopo il gate, e `asdlc-runner --gate-rosso HEAD`
dice «nessun test è nato verde». Il giro 1 non era arrivato ai gate: è la prima volta che girano
su questi commit.

**Da fare, in quest'ordine:**

1. **I dodici commit sul ramo del giro:** `git cherry-pick -x
   9537640..giro-fermato/pbi-522-giro1-20261020`. **Verifica:** `git log --oneline
   origin/main..HEAD` mostra dodici commit, dal `test(runner): con un rilievo della pre-verifica…`
   al `test(runner): con --riprendi il giro non lancia la pre-verifica`, e l'ultimo ha ancora il
   trailer `Guardia-su: tools/asdlc/runner.py::esegui_pbi`. Se il cherry-pick dà un conflitto è
   un fatto nuovo: `fermati` con la domanda, senza risolverlo a mano.
2. **Il limite dichiarato nel `README.md`.** Nella sezione `### La pre-verifica nel giro`, dopo
   il paragrafo e prima del blocco `toml`, un paragrafo con questo testo:

   > **Un limite dichiarato** (`PBI-522`, giro 2). La pre-verifica gira prima dell'inventario
   > d'inizio del giro e prima che il giro conti gli alberi usa e getta. Nel caso normale non
   > cambia niente: il Lettore lavora nel suo albero, che si smonta, e il rapporto sta in `runs/`.
   > Cambia in due casi di guasto del Lettore. Un suo albero che `git worktree remove` non smonta
   > finisce fra i «residui dei giri prima» e non nel conto degli alberi montati e non smontati;
   > un file che il Lettore scrivesse nel worktree del giro arriva dopo il controllo dell'albero
   > pulito, e il Builder parte su un albero sporco. La correzione è `PBI-523`.

   Un commit `docs(runner): …`. Non è codice di produzione e non ha un rosso da osservare; il
   `README.md` è nello Scope.
3. **Le spunte:** in questo file i sei criteri della Verifica si spuntano. Sono fatti, i commit
   lo provano. Un commit `docs(runner): …`.
4. **Il gate** sul ramo: `python3 -m pytest -q tools/tests` verde, e `git status --porcelain`
   vuoto dopo averlo girato.
5. **`fatto`**, perché il gate del rosso giri sui dodici commit e il Critic legga il lavoro. Se il
   gate del rosso segnala un commit nato verde, fuori dalla guardia del criterio 6, è un fatto
   nuovo: `fermati` con la domanda.

**Non si fa:** non si riprende il tag come ramo e non se ne riscrive la storia, non si fa `git
revert`, non si rifanno i test o il codice dei criteri, non si sposta né si aggiunge niente in
`esegui_pbi()` (è `PBI-523`), non si committa nessun JSON. La prima domanda del Protocollo ha la
sua risposta qui sopra e non si riapre.
