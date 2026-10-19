# PBI-513: il rilancio del Builder forka la sessione

**Stato:** da accodare (hotfix di `v0.4.0`, da tagliare `v0.4.1`)

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

Su `main` il rilancio non porta `--fork-session`, quindi ogni criterio è un **rosso atteso**.

- [ ] **Il rilancio del Builder porta `-c`, `--fork-session` e `--session-id`.** Con `esegui()`
      finto, al secondo lancio dello stesso giro il comando contiene `-c`, `--fork-session` e
      `--session-id <uuid>` (pytest).
- [ ] **La prima invocazione non porta `--fork-session` né `-c`.** Primo lancio del giro: il
      comando ha `--session-id` e nessuno dei due (pytest).
- [ ] **Il registro del rilancio porta il uuid del fork.** `sessione` nel registro del secondo
      lancio è l'uuid nuovo e differisce da quello del primo; la traccia si copia da quel uuid
      (pytest, `esegui()` finto che scrive il file della sessione).
- [ ] **Guardia: `--session-id` con `-c` o `--resume` senza `--fork-session` non esce mai.** Su
      ogni comando costruito da `invoca_agente` per Builder e Critic, in primo lancio e in
      rilancio (pytest, parametrizzato).

**Non regressione:**

- `python3 -m pytest -q tools/tests` resta verde; nessun test esistente cambia asserzione.
- La traccia del primo lancio di ogni giro si copia come prima.
