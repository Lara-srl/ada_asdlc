# PBI-535: la pausa per progetto

**Stato:** proposto il 28/10 da una sessione con Francesco; accodato il 28/10 dopo `PBI-533`.
Letto il 30/10 col Lettore (in fondo, *Protocollo*): un fermo e quattro rilievi minori recepiti.
Preverifica del tick del 31/10: un rilievo (la pausa del progetto non andava su Slack), deciso da
Francesco il 31/10 — la pausa del progetto va su Slack (decisione 6, criterio 6).
Giro 1 del 31/10 fermato `rosso-mai-visto` su un test in più; **fatto** con la ripresa (*Il giro 2*, in fondo).

## Direttiva

Oggi la pausa del tick è un solo file, `~/asdlc-tick.pausa` (`file_di_pausa()`, `coda.py`), e vale per
**tutti** i progetti della macchina. Va bene per un tag da rilasciare e per i pin; non va bene per
fermare un solo repo dal telefono (`PBI-536`) mentre gli altri lavorano.

Il tick guarda anche un file di pausa **del progetto**, nella cartella del registro: se c'è, quel
progetto non lancia e lo scrive, gli altri non sono toccati. Due flag di `asdlc-coda` lo creano e lo
tolgono (`--pausa MOTIVO`, `--togli-pausa`), così chi lo fa (una persona o `asdlc-slack`) non scrive il file a mano.

**Scope**

- `tools/asdlc/coda.py` — `pausa_del_progetto(repo)`, nuova; `fermo_in_pausa(repo)` guarda anche
  quella; `notifica_la_pausa(repo)` manda anche quella su Slack (decisione 6); `--pausa MOTIVO` e
  `--togli-pausa`. `pausa()` **non cambia** (decisione 5).
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
   con `in pausa:` ~~, così l'evento `pausa` di `PBI-533` la riconosce~~ (*abrogato il 31/10 dalla
   preverifica del tick: nessun codice legge il log per riconoscere la pausa, l'evento lo manda
   `notifica_la_pausa()` leggendo il file — decisione 6; si rivede se una notifica passa mai dal log*):
   `in pausa: <riga globale>` per la globale, `in pausa: (progetto) <riga del progetto>` per quella
   del progetto. Con tutte e due si scrive **una** riga, la globale.
3. **`--pausa MOTIVO` e `--togli-pausa` non fanno altro:** non lanciano, non decidono; `--togli-pausa`
   senza file esce 0. Prendono il lucchetto del tick, come `asdlc-chiudi-giro`: se è tenuto escono **2**
   con «il lucchetto … è tenuto: un tick è in corso in questo checkout: riprova fra un minuto.» e non
   toccano il file. Il nome non è `--riprendi`, che in `asdlc-runner` vuol dire «riprendi il giro dopo
   il limite d'uso».
4. **`--togli-pausa` non tocca la pausa globale.**
5. **`pausa()` resta solo globale e senza argomenti:** la chiama `asdlc-chiudi-giro` per sapere se la
   pausa globale c'era già, e quel senso non cambia. La pausa del progetto è `pausa_del_progetto(repo)`,
   con la stessa forma (riga o `None`).
6. **La pausa del progetto va su Slack** (Francesco, 31/10): `notifica_la_pausa(repo)` manda l'evento
   `pausa` di `PBI-533` anche quando c'è solo la pausa del progetto, col motivo `(progetto) <riga del
   progetto>` — lo stesso testo della riga del log dopo `in pausa: `. Con tutte e due manda **una**
   notifica, la globale, come la riga del log. `asdlc_notifiche.pausa()`, la memoria delle notifiche e
   i due punti in cui `passaggio()` la chiama non cambiano; un `--dry-run` resta muto.
7. **Il motivo può mancare** (Francesco, 31/10, sulla domanda del giro 1): `--pausa ""` o un motivo di
   soli spazi è accettato e il file è solo `data ora`. Si segnala, non si blocca (`ADR-0008`).

## Dipendenze

- Bloccato da: `PBI-534` (la riga di stato). Blocca: `PBI-536`.

## Contesto

- `tools/asdlc/coda.py`: `file_di_pausa()`, `pausa()`, `fermo_in_pausa()`, `lucchetto_del_tick()`.
- `tools/asdlc/chiudi_giro.py` (mette e toglie la pausa globale, chiama `coda.pausa()`; non cambia).
- `tools/tests/conftest.py` — sposta `coda.LOG` in una cartella temporanea comune.

## Verifica

- [x] **Con la pausa del progetto il tick non lancia e lo dice.** Repository temporaneo con una voce
      da lanciare e il file `<registro>/pausa`: nessun lancio, una riga `in pausa: (progetto) …` in
      `coda.LOG` (quello spostato dal `conftest`). Rosso su `main`: lancia.
- [x] **`--pausa` e `--togli-pausa` creano e tolgono il file, e rispettano il lucchetto.**
      `asdlc-coda --repo <tmp> --pausa "prova"` esce 0 e il file c'è col motivo; `--togli-pausa` lo
      toglie; un secondo `--togli-pausa` esce 0; col lucchetto del tick tenuto `--pausa` esce 2 e il
      file non c'è. Rosso su `main`: il flag è rifiutato.
- [x] **La pausa di un progetto non ferma un altro.** È una **guardia**: due repository, la pausa
      solo nel primo, il tick del secondo lancia. `Guardia-su: tools/asdlc/coda.py::fermo_in_pausa`.
- [x] **La pausa globale vale ancora, e `--togli-pausa` non la toglie.** Guardia, stesso ancoraggio.
- [x] **`asdlc-stato` mostra la pausa del progetto.** Rosso su `main`.
- [x] **La pausa del progetto va su Slack.** Notifiche accese con un webhook finto (come in
      `tools/tests/test_asdlc_notifiche.py`), solo il file `<registro>/pausa` con «prova»: un tick
      fa **una** `POST` il cui testo contiene `in pausa — (progetto) ` e `prova`; con anche la pausa globale la `POST`
      è una e porta la riga globale. Il test sta in `tools/tests/test_asdlc_coda_pausa.py`. Rosso su
      `main`: nessuna `POST`.

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

**Domanda del giro 1, chiusa** dalla decisione 7 (Francesco, 31/10: accettato). Il testo di allora
(dalla revisione del Critic del 31/10, per chi mergia; `PBI-536` la eredita):
`--pausa ""`, o un motivo di soli spazi, va **rifiutato** o accettato? Oggi è accettato e il file
è solo `data ora`, senza motivo; la decisione 1 dice «data, ora e motivo» e non dice se il motivo
può mancare. Non si è scelto in silenzio: il comportamento resta quello di oggi.

## Il giro 2, e cosa si riprende

Il giro 1 (31/10, run `20261031-215511`, 21:55-22:15, runner `v1.0.0`) ha fatto i **sei criteri**, RED e
GREEN per criterio, e li ha spuntati. Il Critic (revisione 0) ha dato «non pronto» con due rilievi: codice
senza il suo RED (il file di pausa del progetto illeggibile; il gruppo mutuamente esclusivo di `--pausa` e
`--togli-pausa`) e il motivo con gli a capo che spezzava la riga (decisione 1). Il Builder ha chiuso il
secondo col suo RED (`15e6255` → `09c7aa7`) e il primo con due test nati verdi: `55be3d9` (il file
illeggibile) morde, `0d1233a` (i due flag insieme) no — nessun mutante del perimetro lo fa fallire per
asserzione — e il gate del rosso ha fermato il giro `rosso-mai-visto`. Il tag è
`giro-fermato/pbi-535-giro1-20261031` (`5ffc7aa`).

**Perché `0d1233a` non è riportato.** Un test nato verde non si toglie con un revert (il gate del rosso
guarda ogni commit del ramo); il gruppo esclusivo che guardava è già in `34137ae`. Come per il 530 si
riporta tutto **tranne** quel commit.

**Riportati in questa PR** (`cherry-pick -x` dal tag, quindici commit, da `f11e5a3` a `5ffc7aa`, senza
`0d1233a`; in `15e6255` il conflitto si è risolto togliendo solo il test di `0d1233a`). Verificato il 31/10
sul ramo: `python3 -m pytest -q tools/tests` dà `1345 passed`, `git status --porcelain` è vuoto e
`asdlc-runner --gate-rosso HEAD` dice «nessun test è nato verde». La punta differisce dal tag solo per quel
test.

**PBI-535 è fatto** con il merge di questa PR: non c'è un giro 2 da lanciare.

**Residui, per chi mergia:**
- I due flag insieme (`argparse` esce 2) non hanno un test; si riprende se un giro tocca il gruppo
  esclusivo di `smista()`. Nemmeno `--togli-pausa` col lucchetto tenuto è provato: il criterio 2 non lo
  chiede, e il ramo di codice è lo stesso di `--pausa`.
- Le correzioni della revisione 1 (`55be3d9`, `15e6255`, `09c7aa7`) non le ha rilette il Critic, perché il
  giro si è fermato prima. Le hanno verificate il gate e il gate del rosso.
- Note del Critic sulla storia: il README dei due flag entra in `e845228` (il commit di Slack) e non nei
  GREEN di `98a01fa`/`34137ae`. Lo squash, se serve, si fa al merge.
