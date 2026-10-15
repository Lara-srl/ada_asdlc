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
      no. Due casi, con 29 e 31 minuti.
- [ ] **Un battito che manca non è un avviso.** Il primo passaggio assoluto scrive il file e
      tace.
- [ ] **La soglia si legge da `[tick]`.** Con 10 minuti nel file di configurazione, 11 minuti
      di distacco avvisano.
- [ ] **L'avviso non ferma il tick.** Dopo l'avviso, il passaggio prosegue come prima
      (`ADR-0008`).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde.
