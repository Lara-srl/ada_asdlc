# PBI-541: la sonda JUnit col solo nome del metodo prende la classe dal file

**Stato:** proposto il 06/11 (Francesco); **non letto**, **non in coda**. Nasce dal difetto 9 di
`ada_planning` (`backlog/DIFETTI.md`), mai aperto a monte fino a oggi.

## Direttiva

La preverifica col Lettore ferma i PBI Java con «rosso non isolabile» su sonde che esistono e
girano. Tre volte in `ada_planning`:

- `PBI-017`: giri `20261026-234204` e `20261028-141001`, tre sonde `nessuno` su tre;
- `PBI-023`: giro `20261106-182206`, due sonde `nessuno` su due. La coda è ferma da allora.

Il Lettore chiama `sonda` col solo nome del metodo, per esempio
`{"file": "app/src/test/java/…/CaricamentoIT.java", "nome": "sonda_…"}`. `esegui_le_sonde()` ne fa un
`TestNuovo` con quel nome. `comandi_dei_test()` lo mette in `per_junit` così com'è, e
`sintassi_del_test()` lo spezza su `#`: la classe diventa il nome del metodo, il metodo è vuoto, e il
selettore è `-Dtest=sonda_…#`. Maven, con `-Dsurefire.failIfNoSpecifiedTests=false`, non trova
niente ed esce 0 senza rapporti. L'esito è `nessuno`, e il rilievo `R` ferma il giro.

Con `Classe#metodo` la stessa sonda esce `rosso`: provato a mano il 28/10 su un albero di prova, e
visto nelle preverifiche di `PBI-017` (`20261028-150824`) e `PBI-018` (`20261028-163010`,
`…-165205`), dopo che i PBI avevano scritto nel testo «le sonde si nominano `Classe#metodo`». È un
aggiramento che va ripetuto in ogni PBI Java, e quando manca la coda si ferma.

Il runner sa già da che classe viene un test JUnit: `test_nuovi_dellalbero()` ricava `Classe#metodo` da
`Path(percorso).stem` (`nomi_dei_test_junit(diff, classe)`). La sonda deve avere lo stesso nome.

**Scope**

- `tools/asdlc/runner.py`: `esegui_le_sonde()`, o `comandi_dei_test()` (vedi il Protocollo). Una sonda
  JUnit il cui nome non ha `#` diventa `<stem del file>#<nome>`. Un nome che ha già `#` non cambia.
  Il nome nel rapporto (`sonde[].nome`) resta quello che ha dato il Lettore.
- `tools/asdlc/esito.py`: la `description` del campo `nome` dello strumento `sonda` dice la forma
  attesa per JUnit, `Classe#metodo`, e che il solo metodo si completa dal file.
- `tools/asdlc/prompt/lettore.md`, sezione «Le sonde»: una riga per JUnit, `Classe#metodo`.
- `tools/tests/test_asdlc_lettore.py`: i test dei criteri.
- `backlog/PBI-541-la-sonda-junit-col-solo-metodo-prende-la-classe-dal-file.md`: questo file, per la
  spunta.
- **Fuori scope:** il nome dei test JUnit nel lucchetto di fase e nel gate del rosso, che già passa
  da `nomi_dei_test_junit()`; le classi annidate (`@Nested`), che oggi non si isolano neanche dal
  diff; le sonde pytest e vitest; `PBI-529` (il messaggio del gate guasto), che resta a sé.

## ✅ Deciso

1. **Si completa, non si rifiuta.** Il Lettore che dà il solo metodo non ha sbagliato: ha dato il nome
   che il file contiene. Rifiutare la chiamata (`-32602`) sposterebbe il difetto nel prompt, e a ogni
   modello nuovo tornerebbe. Il runner ha il file e ne ricava la classe come fa per il diff.
2. **Il rapporto resta fedele al Lettore.** `sonde[].nome` è quello chiamato; il selettore costruito
   compare dove già compaiono i comandi dei gate (la coda del rapporto), non in un campo nuovo.
3. **La classe è lo stem del file**, la stessa regola di `nomi_dei_test_junit()`. Un file con più
   classi di primo livello non è il caso di Java né di questo PBI.

## Dipendenze

- Bloccato da: nessuno.
- Blocca: niente in `ada_asdlc`. In `ada_planning` toglie l'aggiramento dei PBI Java (`PBI-017`,
  `PBI-018`, `PBI-023`); il pin che lo porta è una PR di `ada_planning`.

## Contesto

- `tools/asdlc/runner.py`: `esegui_le_sonde()`, `comandi_dei_test()`, `sintassi_del_test()`,
  `nomi_dei_test_junit()`, `JUNIT_COMANDO`, `ESITI_MANCATI`.
- `PBI-505` (il lucchetto di fase legge JUnit): la sintassi `Classe#m1+m2` e `[junit].comando`.
- `PBI-521` (il Lettore e la sonda del rosso), decisione 4: cosa vuol dire `nessuno`.
- In `ada_planning`: `backlog/DIFETTI.md`, 9; `runs/20261106-182206-PBI-023-preverifica.json` nel
  worktree del runner (`../ada_planning-run`).

## Verifica

- [ ] **Una sonda JUnit col solo nome del metodo si esegue come `Classe#metodo`.** Con `[junit]`
      configurato e `esiti_del_comando` finto che registra il comando, una sonda su
      `app/src/test/java/x/CaricamentoIT.java` col nome `sonda_uno` produce un comando con
      `CaricamentoIT#sonda_uno` nel selettore di `-Dtest=`. Rosso su `main`: oggi il selettore è
      `sonda_uno#`.
- [ ] **La sonda completata ha l'esito del suo test, non `nessuno`.** Lo stesso caso, con
      `esiti_del_comando` finto che risponde `rosso` per `CaricamentoIT#sonda_uno`: la sonda nel
      rapporto ha `esito == "rosso"`, `nome == "sonda_uno"`, e nessun rilievo `R`. Rosso su `main`:
      oggi l'esito è `nessuno` e c'è il rilievo «rosso non isolabile».
- [ ] **Un nome che ha già la classe non cambia** (guardia: nasce verde). Una sonda col nome
      `CaricamentoIT#sonda_uno` produce lo stesso selettore del primo criterio, senza la classe
      ripetuta.

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde, compresi i test di
`PBI-521` sulle sonde pytest e quello del nome che nel file non c'è.

## Protocollo di rifinitura

Si può scegliere senza chiedere: se il nome si completa in `esegui_le_sonde()`, prima di costruire
il `TestNuovo`, o in `comandi_dei_test()`, dove `per_junit` riceve il nome. La seconda strada vale
anche per chi chiama `comandi_dei_test()` da altrove: se il Builder la sceglie, verifica che il
lucchetto di fase non riceva mai un nome senza `#` e lo scrive nel commit.
Si chiama `fermati`: se il RED del primo criterio mostra che il selettore è già giusto su `main`. In
quel caso la causa del difetto 9 è un'altra, e il rapporto deve dire quale.
