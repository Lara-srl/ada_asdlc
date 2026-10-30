# PBI-535: la pausa per progetto

**Stato:** proposto il 28/10 da una sessione con Francesco; accodato il 28/10 dopo `PBI-533`.
Letto il 30/10 col Lettore (in fondo, *Protocollo*): un fermo e quattro rilievi minori recepiti.

## Direttiva

Oggi la pausa del tick è un solo file, `~/asdlc-tick.pausa` (`file_di_pausa()`, `coda.py`), e vale per
**tutti** i progetti della macchina. Va bene per un tag da rilasciare e per i pin; non va bene per
fermare un solo repo dal telefono (`PBI-536`) mentre gli altri lavorano.

Il tick guarda anche un file di pausa **del progetto**, nella cartella del registro: se c'è, quel
progetto non lancia e lo scrive, gli altri non sono toccati. Due flag di `asdlc-coda` lo creano e lo
tolgono (`--pausa MOTIVO`, `--togli-pausa`), così chi lo fa (una persona o `asdlc-slack`) non scrive il file a mano.

**Scope**

- `tools/asdlc/coda.py` — `pausa_del_progetto(repo)`, nuova; `fermo_in_pausa(repo)` guarda anche
  quella; `--pausa MOTIVO` e `--togli-pausa`. `pausa()` **non cambia** (decisione 5).
- `tools/asdlc/stato.py` — la pausa del progetto compare nella riga (`PBI-534`).
- `README.md` — i due flag e la differenza fra pausa globale e di progetto.
- `tools/tests/test_asdlc_coda_pausa.py` — nuovo: i test dei criteri.
- `backlog/PBI-535-la-pausa-per-progetto.md` — questo file, per la spunta.
- **Fuori scope:** la pausa globale (`~/asdlc-tick.pausa`) non cambia, né chi la legge, la scrive o la
  toglie: `pausa()` (letta da `fermo_in_pausa()` e da `chiudi_giro.py`), chi la scrive
  (`chiudi_giro.py`, `metti_in_attesa_del_pbi_a_monte()` in `runner.py`), chi la toglie (`pin()` in
  `coda.py` al pin `MERGED`, `chiudi_giro.py`). `chiudi_giro.py` non cambia. Togliere la pausa a un
  `MERGED` verificato resta un gesto umano.

## ✅ Deciso

1. **Il file è `repo / CFG.registro.cartella / "pausa"`**, calcolato dal `repo` e **non** dal `LOG`
   (i test spostano `coda.LOG` fuori dal repository, `conftest.py`), una riga: data, ora e motivo, come
   la pausa globale. Un file che c'è ma non si legge è pausa lo stesso, come per `pausa()`.
2. **Le due pause si sommano:** il tick è fermo se c'è una delle due. La riga del log comincia sempre
   con `in pausa:`, così l'evento `pausa` di `PBI-533` la riconosce: `in pausa: <riga globale>` per la
   globale, `in pausa: (progetto) <riga del progetto>` per quella del progetto. Con tutte e due si
   scrive **una** riga, la globale.
3. **`--pausa MOTIVO` e `--togli-pausa` non fanno altro:** non lanciano, non decidono; `--togli-pausa`
   senza file esce 0. Prendono il lucchetto del tick, come `asdlc-chiudi-giro`: se è tenuto escono **2**
   con «il lucchetto … è tenuto: un tick è in corso in questo checkout: riprova fra un minuto.» e non
   toccano il file. Il nome non è `--riprendi`, che in `asdlc-runner` vuol dire «riprendi il giro dopo
   il limite d'uso».
4. **`--togli-pausa` non tocca la pausa globale.**
5. **`pausa()` resta solo globale e senza argomenti:** la chiama `asdlc-chiudi-giro` per sapere se la
   pausa globale c'era già, e quel senso non cambia. La pausa del progetto è `pausa_del_progetto(repo)`,
   con la stessa forma (riga o `None`).

## Dipendenze

- Bloccato da: `PBI-534` (la riga di stato). Blocca: `PBI-536`.

## Contesto

- `tools/asdlc/coda.py`: `file_di_pausa()`, `pausa()`, `fermo_in_pausa()`, `lucchetto_del_tick()`.
- `tools/asdlc/chiudi_giro.py` (mette e toglie la pausa globale, chiama `coda.pausa()`; non cambia).
- `tools/tests/conftest.py` — sposta `coda.LOG` in una cartella temporanea comune.

## Verifica

- [ ] **Con la pausa del progetto il tick non lancia e lo dice.** Repository temporaneo con una voce
      da lanciare e il file `<registro>/pausa`: nessun lancio, una riga `in pausa: (progetto) …` in
      `coda.LOG` (quello spostato dal `conftest`). Rosso su `main`: lancia.
- [ ] **`--pausa` e `--togli-pausa` creano e tolgono il file, e rispettano il lucchetto.**
      `asdlc-coda --repo <tmp> --pausa "prova"` esce 0 e il file c'è col motivo; `--togli-pausa` lo
      toglie; un secondo `--togli-pausa` esce 0; col lucchetto del tick tenuto `--pausa` esce 2 e il
      file non c'è. Rosso su `main`: il flag è rifiutato.
- [ ] **La pausa di un progetto non ferma un altro.** È una **guardia**: due repository, la pausa
      solo nel primo, il tick del secondo lancia. `Guardia-su: tools/asdlc/coda.py::fermo_in_pausa`.
- [ ] **La pausa globale vale ancora, e `--togli-pausa` non la toglie.** Guardia, stesso ancoraggio.
- [ ] **`asdlc-stato` mostra la pausa del progetto.** Rosso su `main`.

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura

Si può scegliere senza chiedere: i nomi delle funzioni private. Si chiama `fermati`:
se `PBI-534` non è in `main`; se un test esistente verifica che il tick ignori un file in `registro`.

**Lettura del 30/10** (Lettore separato, sola lettura, su `main` `13d6641`): un fermo — `pausa()` senza
argomenti chiamata da `chiudi_giro.py`, che lo Scope avrebbe fatto cambiare (decisione 5) — e quattro
rilievi minori: il file calcolato dal `repo` e non dal `LOG` spostato dei test (decisione 1, criterio
1); il «Fuori scope» con i punti veri che leggono, scrivono e tolgono la pausa globale; la riga che
comincia con `in pausa:` per l'evento di `PBI-533` (decisione 2); il lucchetto tenuto, le due pause
insieme e il nome `--togli-pausa` al posto di `--riprendi` (decisioni 2 e 3).
