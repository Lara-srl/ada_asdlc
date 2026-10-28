# PBI-535: la pausa per progetto

**Stato:** proposto il 28/10 da una sessione con Francesco; accodato il 28/10 dopo `PBI-533`.
**Da leggere con la lettura avversariale prima di togliere la barriera `v1.0.0`.**

## Direttiva

Oggi la pausa del tick è un solo file, `~/asdlc-tick.pausa` (`file_di_pausa()`, `coda.py`), e vale per
**tutti** i progetti della macchina. Va bene per un tag da rilasciare e per i pin; non va bene per
fermare un solo repo dal telefono (`PBI-536`) mentre gli altri lavorano.

Il tick guarda anche un file di pausa **del progetto**, nella cartella del registro: se c'è, quel
progetto non lancia e lo scrive, gli altri non sono toccati. Due flag di `asdlc-coda` lo creano e lo
tolgono, così chi lo fa (una persona o `asdlc-slack`) non scrive il file a mano.

**Scope**

- `tools/asdlc/coda.py` — `pausa()` e `fermo_in_pausa()` guardano anche il file del progetto;
  `--pausa MOTIVO` e `--riprendi`.
- `tools/asdlc/stato.py` — la pausa del progetto compare nella riga (`PBI-534`).
- `README.md` — i due flag e la differenza fra pausa globale e di progetto.
- `tools/tests/test_asdlc_coda_pausa.py` — nuovo: i test dei criteri.
- `backlog/PBI-535-la-pausa-per-progetto.md` — questo file, per la spunta.
- **Fuori scope:** la pausa globale (`~/asdlc-tick.pausa`) non cambia, né chi la mette (`pin()`,
  `asdlc-chiudi-giro`); togliere la pausa a un `MERGED` verificato resta un gesto umano.

## ✅ Deciso

1. **Il file è `<registro>/pausa`**, una riga: data, ora e motivo, come la pausa globale.
2. **Le due pause si sommano:** il tick è fermo se c'è una delle due, e la riga del log dice quale
   (`in pausa (progetto): …` / `in pausa: …`).
3. **`--pausa MOTIVO` e `--riprendi` non fanno altro:** non lanciano, non decidono; `--riprendi` senza
   file non è un errore. Prendono il lucchetto del tick, come `asdlc-chiudi-giro`, per non incrociarsi
   con un tick che lancia.
4. **`--riprendi` non tocca la pausa globale.**

## Dipendenze

- Bloccato da: `PBI-534` (la riga di stato). Blocca: `PBI-536`.

## Contesto

- `tools/asdlc/coda.py`: `file_di_pausa()`, `pausa()`, `fermo_in_pausa()`, `lucchetto_del_tick()`.
- `tools/asdlc/chiudi_giro.py` (mette e toglie la pausa globale).

## Verifica

- [ ] **Con la pausa del progetto il tick non lancia e lo dice.** Repository temporaneo con una voce
      da lanciare e il file `<registro>/pausa`: nessun lancio, una riga «in pausa (progetto)» nel
      log. Rosso su `main`: lancia.
- [ ] **`--pausa` e `--riprendi` creano e tolgono il file.** `asdlc-coda --repo <tmp> --pausa "prova"`
      esce 0 e il file c'è col motivo; `--riprendi` lo toglie; un secondo `--riprendi` esce 0.
      Rosso su `main`: il flag è rifiutato.
- [ ] **La pausa di un progetto non ferma un altro.** È una **guardia**: due repository, la pausa
      solo nel primo, il tick del secondo lancia. `Guardia-su: tools/asdlc/coda.py::fermo_in_pausa`.
- [ ] **La pausa globale vale ancora, e `--riprendi` non la toglie.** Guardia, stesso ancoraggio.
- [ ] **`asdlc-stato` mostra la pausa del progetto.** Rosso su `main`.

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura

Si può scegliere senza chiedere: il formato della riga, i nomi delle funzioni. Si chiama `fermati`:
se `PBI-534` non è in `main`; se un test esistente verifica che il tick ignori un file in `registro`.
