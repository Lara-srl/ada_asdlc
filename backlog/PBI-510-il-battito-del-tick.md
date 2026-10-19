# PBI-510: il battito del tick e il recupero dei tick persi

## Direttiva

Quinto PBI di `ADR-0030`, decisione 5. Il tick è un cron su un PC: se il PC si spegne o si
sospende, la coda si ferma in silenzio. Due cose, entrambe di codice:

- **Il battito:** a ogni passaggio il tick scrive un file con l'ora; se il file è più vecchio
  di 30 minuti, parte un avviso (`ADR-0008`: avviso, non blocco).
- **Il recupero:** un timer di systemd (utente) che rilancia il tick quando il PC riparte, per
  non aspettare il passaggio successivo del cron.

Il limite resta dichiarato nella spec: il PC spento ferma la coda.

**Scope**

- `tools/asdlc/coda.py` — la scrittura del battito a ogni passaggio e il controllo di età.
- `tools/asdlc/config.py` — la chiave `[tick].soglia_battito_minuti` (default 30).
- `tools/asdlc/ricetta/` o `README.md` — l'unità e il timer di systemd, come esempio; il
  crontab non si tocca da codice.
- `tools/tests/test_asdlc_battito.py` — nuovo: i test dei criteri.
- `README.md`, `backlog/AUTOMAZIONE.md` — la sezione.
- `backlog/PBI-510-il-battito-del-tick.md` — questo file, per la spunta.

**Fuori scope**

- Spostare il tick su un server sempre acceso (alternativa da rivalutare se i progetti
  crescono).
- Mandare l'avviso fuori dal log (mail, notifica): il canale lo sceglie Francesco in un PBI
  suo; qui l'avviso è nel log e a schermo.

## ✅ Deciso (Francesco, 16/10)

1. **La soglia è 30 minuti.**
2. **Il battito è un file per progetto,** `~/asdlc-tick.battito` accanto a
   `~/asdlc-tick.pausa`, con l'ora in ISO su una riga. Un file che manca è «mai partito»,
   non una violazione.
3. **Un tick in pausa batte lo stesso:** la pausa è un gesto, non un guasto.
4. **Il controllo lo fa il tick stesso** al passaggio successivo, ricordando il battito
   precedente: se il distacco supera la soglia, scrive l'avviso nel log prima di fare altro.
5. **Il timer è una ricetta,** non codice installato: l'unità vive nella documentazione e
   Francesco la installa, come il crontab.
6. **Lo scope dei commit è `coda` e `kb`.**

## Dipendenze

- Bloccato da: nessuno. Indipendente dagli altri quattro.

## Contesto

- `specs/solver-e-rilascio/spec.md`, «Il tick è sempre attivo».
- `tools/asdlc/coda.py`, `file_di_pausa()`, `pausa()`, `fermo_in_pausa()`.

## Verifica

Su `main` il battito non esiste: ogni criterio è un **rosso atteso**. L'ora è un parametro dei
test, mai l'orologio vero.

- [ ] **Il tick scrive il battito a ogni passaggio,** anche quando non lancia niente.
- [ ] **Il tick in pausa batte lo stesso.**
- [ ] **Un distacco oltre la soglia scrive l'avviso,** nel log e a schermo; sotto la soglia
      no. Tre casi, con 29, 30 e 31 minuti: a 30 esatti non avvisa, perché «oltre» non è «alla»
      (il caso al confine distingue `>` da `>=`, giro 2).
- [ ] **Un battito che manca non è un avviso.** Il primo passaggio assoluto scrive il file e
      tace.
- [ ] **La soglia si legge da `[tick]`.** Con 10 minuti nel file di configurazione, 11 minuti
      di distacco avvisano.
- [ ] **L'avviso non ferma il tick.** Dopo l'avviso, il passaggio prosegue come prima
      (`ADR-0008`).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde.

## Il giro 2, e cosa si riprende

Il giro 1 (19/10, run `20261019-121507`) ha scritto tutti i criteri e si è fermato a
`rosso-mai-visto` su due test: `fbdf83a` («il tick in pausa batte lo stesso») e `766ad34` («un
distacco di 29 minuti non avvisa»). Nascono verdi per la ragione di `PBI-509`: il codice che li
soddisfa c'era già (`batti(a.repo)` stava prima della pausa, e `minuti > soglia` non avvisa a 29)
e un test scritto dopo il codice non può essere rosso (`ADR-0021`: il ciclo mancato è ex ante e
nessuna fix lo annulla). Per `766ad34` c'è di più: il mutante `minuti >= soglia` sopravvive,
cioè il test non prova nemmeno il confine. `4e4766c` (l'avviso non ferma il tick) mordeva e
non è stato contestato.

**Si riprende il tag `ripresa/pbi-510-giro2`** (350867d), non un `giro-fermato/…`: è la storia del
giro 1 **senza `fbdf83a` e `766ad34`** (e senza altro), più un commit `350867d` che toglie a mano
due cose da `coda.py`: `batti(a.repo)` passa da prima della pausa a dopo `fermo_in_pausa`, e
`if minuti > soglia:` diventa `if minuti >= soglia - 1:`. Gate verde sul tag (1032 test). Ramo da
quel tag, niente cherry-pick e niente rebase: la storia è già pulita. Il file di questo PBI si
prende da `main` (`git checkout origin/main -- backlog/PBI-510-il-battito-del-tick.md`), un
commit. Se `git` vede un conflitto su quel file vale la versione di `main`.

**Da fare, in quest'ordine:**

1. **Il tick in pausa batte lo stesso, RED.** Il test di `fbdf83a`, riscritto uguale nella
   sostanza (un file di pausa, ora data, un passaggio: il file del battito ha l'ora e `in
   pausa:` è nel log una volta). Contro il tag fallisce: il battito non si scrive. Un commit
   `test(coda): …(RED)` da solo.
2. **GREEN.** `batti(a.repo)` torna prima della pausa, e il test passa. Un commit
   `feat(coda): …` con il solo codice che lo fa passare.
3. **Il distacco sotto e al confine, RED.** Un solo test con tre casi: 29 minuti non avvisa, 30
   non avvisa (non «oltre» la soglia), 31 avvisa. Contro il tag fallisce (la soglia è un minuto
   sotto): quello è il rosso. Un commit `test(coda): …(RED)` da solo.
4. **GREEN.** `minuti >= soglia - 1` torna `minuti > soglia`. Un commit `feat(coda): …`.
5. Spunte del PBI e, dove nominano il comportamento, README e `AUTOMAZIONE.md` nello stesso
   commit del codice che lo cambia.

**Non si fa:** non si rimettono `fbdf83a` e `766ad34`, non si tocca `350867d` (i due GREEN lo
annullano con commit nuovi, non lo riscrivono), non si riscrive la storia del tag, e non si
cambia la soglia di 30 minuti né il formato del file del battito.
