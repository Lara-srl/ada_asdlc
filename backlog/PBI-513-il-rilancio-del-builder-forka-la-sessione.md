# PBI-513: il rilancio del Builder forka la sessione

**Stato:** in coda; giri 1 e 2 fermati il 19/10, giro 3 il 20/10 (hotfix di `v0.4.0`, da tagliare `v0.4.1`)

## Direttiva

Il difetto 7 di `ada_planning` (`backlog/DIFETTI.md`, giro 20261019-215204 di PBI-006), e il
difetto 99 di `PBI-102`. Con il pin `v0.4.0` il rilancio del Builder dopo un gate rosso non
parte: il giro chiude `senza esito`, codice d'uscita 1, e lo stderr dice «`--session-id` can
only be used with `--continue` or `--resume` if `--fork-session` is also specified».

La causa sta in due righe di `tools/asdlc/runner.py` che non sapevano l'una dell'altra:

- il rilancio costruisce il comando come `BUILDER + ["-c"]` (`primo_del_giro` falso);
- `PBI-511` (decisione 1) ha fatto aggiungere `--session-id <uuid nuovo>` a **ogni**
  invocazione, per legare il registro alla traccia della sessione.

La CLI rifiuta le due cose insieme. `test_asdlc_traccia.py` prova solo la prima invocazione,
quindi nessun test copriva il rilancio. Ogni progetto a `v0.4.0` si ferma al primo gate rosso.

La cura è quella che la CLI chiede, verificata a mano il 19/10 con la CLI installata: `-c
--fork-session --session-id <uuid>` **mantiene il contesto** della sessione continuata (il
modello ricorda la risposta di prima) e **scrive una sessione nuova** col uuid dato. Il
registro e `copia_la_traccia` continuano a vedere un uuid per invocazione, come voleva `PBI-511`.

**Scope**

- `tools/asdlc/runner.py` — il comando del rilancio (`BUILDER + ["-c"]`) e la costruzione
  dell'invocazione che aggiunge `--session-id`.
- `tools/tests/test_asdlc_traccia.py` — i test dei criteri.
- `specs/` e `README.md` solo se descrivono il rilancio con `-c` da solo, nello stesso commit.
- `backlog/PBI-513-il-rilancio-del-builder-forka-la-sessione.md` — questo file, per la spunta.

**Fuori scope**

- Il tag `v0.4.1`, la versione del pacchetto e i pin dei progetti: gesti umani, in PR a parte.
- Il Critic: non si rilancia con `-c`.
- Altre ragioni per cui il rilancio può fallire.

## ✅ Deciso, per non fermare il giro

1. **Il rilancio con `-c` porta anche `--fork-session`.** La prima invocazione del giro non lo
   porta: `--fork-session` senza `-c` non serve a niente e non deve comparire.
2. **Un uuid nuovo per ogni invocazione resta la regola di `PBI-511`.** Il rilancio forka da
   dove si trovava il Builder e scrive la sua traccia sotto il uuid del fork.
3. **Una guardia generale:** nessun comando che il runner lancia con `--session-id` contiene
   `-c` o `--resume` senza `--fork-session`. Si prova sui comandi costruiti, con `esegui()`
   sostituito da un finto. Nessun test lancia la CLI vera.
4. **Lo scope dei commit è `runner`.**

## Dipendenze

- Bloccato da: nessuno. `PBI-511` è in `main` e in `v0.4.0`.
- Dopo questo, a mano: il tag `v0.4.1` e i pin dei progetti (`ada_planning`, `ada_asdlc`, aDa
  quando la #361 sarà mergiata, il template). Finché il tag non c'è, la #361 di aDa non va
  mergiata.

## Contesto

- `ada_planning`, `backlog/DIFETTI.md`, difetto 7; `backlog/PBI-102-…`, difetto 99.
- `PBI-511` (la traccia delle sessioni), decisioni 1 e 2.
- `tools/asdlc/runner.py`: l'invocazione dell'agente (`--session-id`) e il rilancio del Builder
  (`cmd = BUILDER + ([] if primo_del_giro else ["-c"])`).

## Verifica

Su `main` il rilancio non porta `--fork-session`, quindi ognuno dei criteri qui sotto è un **rosso
atteso**.

- [ ] **Il rilancio del Builder porta `-c`, `--fork-session` e `--session-id`.** Con `esegui()`
      finto, al secondo lancio dello stesso giro il comando contiene `-c`, `--fork-session` e
      `--session-id <uuid>` (pytest).
- [ ] **La prima invocazione non porta `--fork-session` né `-c`.** Primo lancio del giro: il
      comando ha `--session-id` e nessuno dei due (pytest).
- ~~**Il registro del rilancio porta il uuid del fork.**~~ **Uscito dal PBI (19/10, giro 2).** Il
      criterio è vero anche su `main`: `PBI-511` (decisione 1) scrive già un uuid nuovo per ogni
      invocazione, quindi non può nascere rosso, e il test del giro 1 (`763b668`) è nato verde e
      non morde (22 mutanti non lo fanno fallire per asserzione). Il gate del rosso ha fermato il
      giro 2 per quel commit. La proprietà resta garantita da `PBI-511`.
- [ ] **Guardia: `--session-id` con `-c` o `--resume` senza `--fork-session` non esce mai.** Su
      ogni comando costruito da `invoca_agente` per Builder e Critic, in primo lancio e in
      rilancio (pytest, parametrizzato).

**Non regressione:**

- `python3 -m pytest -q tools/tests` resta verde; nessun test esistente cambia asserzione.
- La traccia del primo lancio di ogni giro si copia come prima.

## Il giro 2, e cosa si riprende

Il giro 1 (19/10, run `20261019-230506`, 15 minuti) ha fatto **tutto il lavoro** del PBI: i
quattro criteri con le loro coppie RED→GREEN, la guardia anche per `--resume`, le spunte. La suite
dava `1058 passed`. Si è fermato solo alla fine, con una domanda del Builder: la cura fa sì che
`invoca_agente` aggiunga `--fork-session` ai comandi con `-c` o `--resume`, e il test
`TestIlTimeoutDiUnAgenteChiudeSenzaEsito` (`tools/tests/test_asdlc_runner.py`, riga ~8478) usa un
agente finto `sh -c` che scrive il suo esito in `"${2%.mcp.json}.json"`. Con `--fork-session`
`$2` diventa `--session-id`, e ogni `pytest` lascia `tools/tests/dati/progetto/--session-id.json`
non tracciato: l'albero resta sporco. Su `main` non succede. Il Critic non è girato.

**Risposta (il Solver, `fable`, 19/10, confermata da Francesco con lo stesso precedente di
`PBI-511`): strada B.** Il file si ignora, non si committa e non si cancella a mano. La cura vera
(il finto che scrive su `tmp_path` e non legge `$2`) è un PBI a parte, non questo. La strada C
(restringere la condizione ai soli comandi `claude`) **no**: la decisione 3 vuole la guardia su
ogni comando con `-c` o `--resume`, e non si piega su un finto dei test.

**Si riprende il tag `giro-fermato/pbi-513-giro1-20261019`** (`fc8a898`): ramo da quel tag, niente
cherry-pick e niente rebase. Il file di questo PBI si prende da `main` (`git checkout
origin/main -- backlog/PBI-513-il-rilancio-del-builder-forka-la-sessione.md`), un commit; sul tag
ha le spunte e su `main` questa sezione. **Dopo averlo preso, i quattro criteri vanno
rispuntati**: sono già fatti, i commit lo provano.

**Da fare, in quest'ordine:**

1. **Una riga in `tools/tests/dati/progetto/.gitignore`**, accanto a quella dei JSON con nome
   uuid: `--*.json`, con il commento sul perché (l'esito che il finto scrive quando `$2` è un
   flag). Un commit `chore(runner): …`, il primo del giro. La deroga allo Scope (`ADR-0015`) si
   dichiara nel suo messaggio: cosa (la riga), perché (il gate sporca l'albero con l'esito di un
   test finto), cosa non cambia (nessun file tracciato della cartella, `runs/` e gli uuid restano
   ignorati). Non è codice di produzione e non ha un rosso da osservare.
2. **Il gate** sul ramo: verde, e `git status --porcelain` vuoto dopo averlo girato.
3. **`fatto`**, perché il Critic legga il lavoro del giro 1 e questo commit. Se il gate è rosso o
   `git status` mostra altro, è un fatto nuovo: `fermati` con la domanda.
4. **Nella risposta `fatto` una riga che nomina il PBI da aprire:** il finto `AGENTE_CHE_DORME`
   legge `$2` invece di `--mcp-config` o `ASDLC_ESITO` e scrive in `tools/tests/dati/progetto/`:
   deve scrivere su `tmp_path`.

**Non si fa:** non si rifanno i passi del giro 1, non si riscrive la storia del tag, non si
tocca `tools/tests/test_asdlc_runner.py` (la cura del finto è di un PBI suo) e non si committa
nessun JSON.

## Il giro 3, e cosa si riprende

Il giro 2 (19/10, run `20261019-233508`, 4 minuti e 45) ha applicato la strada B del giro 1 (la riga
`--*.json` in `.gitignore`, `cd247e4`) e ha portato il gate `asdlc` a verde. Si è fermato
`rosso-mai-visto`: il gate del rosso ha trovato il test del **criterio 3**, commit `763b668`,
nato verde e senza morso. Il difetto era del PBI, che chiamava «rosso atteso» un criterio vero
anche su `main`, e del Builder del giro 1, che lo ha committato dichiarando nel messaggio «nasce
verde» invece di fermarsi. Il Critic non è girato.

**Decisione di Francesco (19/10): il criterio 3 esce dal PBI** e il suo test esce dal ramo. Il
test non può nascere rosso e `PBI-511` garantisce già la proprietà.

**Si riprende il tag `giro-fermato/pbi-513-giro2-20261019`** (`63bdd08`): ramo da quel tag, niente
cherry-pick e niente rebase. Il file di questo PBI si prende da `main` (`git checkout
origin/main -- backlog/PBI-513-il-rilancio-del-builder-forka-la-sessione.md`), un commit; i criteri
1, 2 e 4 **vanno rispuntati** (sono già fatti, i commit lo provano) e il 3 resta barrato, non spuntato.

**Da fare, in quest'ordine:**

1. **Togliere il test del criterio 3.** Un commit `revert(runner): …` (o `test(runner): …`) che
   toglie da `tools/tests/test_asdlc_traccia.py` **solo** la funzione
   `test_il_registro_del_rilancio_porta_il_uuid_del_fork_e_ne_copia_la_traccia` (commit `763b668`).
   `git revert 763b668` è la strada; se dà un conflitto perché dopo di lui lo stesso file è cambiato
   (`677dfc9`), si risolve tenendo tutto il resto e togliendo quella funzione. **Verifica:**
   `grep -c test_il_registro_del_rilancio_porta_il_uuid tools/tests/test_asdlc_traccia.py` dà 0, e
   `grep -c "def test_" tools/tests/test_asdlc_traccia.py` è il numero di prima meno uno. Nessun
   altro test cambia. Non è codice di produzione e non ha un rosso da osservare: toglie un
   test che non può nascere rosso.
2. **Il gate** sul ramo: verde, e `git status --porcelain` vuoto dopo averlo girato.
3. **`fatto`**, perché il gate del rosso giri sui commit rimasti e poi il Critic legga il lavoro dei
   giri 1 e 2. Se il gate del rosso segnala un altro commit nato verde, è un fatto nuovo:
   `fermati` con la domanda, senza tentare di farlo mordere a forza.

**Non si fa:** non si riscrive la storia dei tag, non si rifanno i passi dei giri 1 e 2, non si
riscrive il criterio 3 in un'altra forma, non si committa nessun JSON e non si tocca
`tools/tests/test_asdlc_runner.py`.

## Il giro 4, e cosa si riprende

Il giro 3 (20/10, 00:05-00:09) ha fatto il `git revert` di `763b668` come chiedeva la sezione qui
sopra, e si è fermato `rosso-mai-visto` **sullo stesso commit**: il gate del rosso guarda ogni
commit del ramo fuori da `origin/main` (`gate_del_rosso`, `tools/asdlc/runner.py`), e un revert
toglie il test dall'albero ma non il commit dalla storia. Il difetto era della ripresa, non del
Builder: chiedeva di riprendere un tag che conteneva il commit da togliere. Il giro 3 è chiuso col
tag `giro-fermato/pbi-513-giro3-20261020` (`a20d1bb`).

**Si riprende il tag `ripresa/pbi-513-giro4`** (`a2f96a7`). Non è un giro: sono i sei commit di
codice del giro 1, **senza `763b668`**, rimessi con `git cherry-pick -x` sopra `origin/main`
(`2bad8ad`), in quest'ordine: `d22bdc1`, `c255807`, `ab087e8`, `dbdd1f0`, `677dfc9`, `6dc7eb6`.
L'unico conflitto, in `677dfc9`, è risolto togliendo la funzione del criterio 3 e tenendo il
test parametrizzato. Il commit `cd247e4` (la riga `--*.json`) non c'è perché è già in `main`
(#65). Sul tag, verificato il 20/10: `python3 -m pytest -q tools/tests` dà `1057 passed`,
`git status --porcelain` è vuoto dopo il gate, e `asdlc-runner --gate-rosso origin/main..HEAD`
dice «nessun test è nato verde».

**Da fare, in quest'ordine:**

1. **I sei commit sul ramo del giro:** `git cherry-pick 2bad8ad..ripresa/pbi-513-giro4`. I commit
   non toccano `backlog/`, quindi passano anche se `main` si è mosso dopo `2bad8ad`. **Verifica:**
   `git log --oneline origin/main..HEAD` mostra sei commit, e `git grep -c
   test_il_registro_del_rilancio_porta_il_uuid tools/tests/` non trova niente. Se il cherry-pick
   dà un conflitto è un fatto nuovo: `fermati` con la domanda, senza risolverlo a mano.
2. **Le spunte:** in questo file i criteri 1, 2 e 4 si spuntano (sono fatti, i commit lo provano),
   il 3 resta barrato. Un commit `docs(runner): …`.
3. **Il gate** sul ramo: verde, e `git status --porcelain` vuoto dopo averlo girato.
4. **`fatto`**, perché il gate del rosso giri sui sei commit e il Critic legga il lavoro. Se il
   gate del rosso segnala un commit nato verde, è un fatto nuovo: `fermati` con la domanda.

**Non si fa:** non si riprende nessuno dei tag `giro-fermato/pbi-513-*`, non si fa `git revert`,
non si riscrive la storia di `ripresa/pbi-513-giro4`, non si rifanno i test o le cure, non si
tocca `tools/tests/test_asdlc_runner.py` (è di `PBI-518`) e non si committa nessun JSON.
