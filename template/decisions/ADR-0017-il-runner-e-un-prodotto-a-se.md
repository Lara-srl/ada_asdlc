# ADR-0017: il runner ASDLC è un prodotto a sé, e va estratto — non riscritto

**Stato:** **Accettata** · **Data:** 2026-08-25 · **Accettata:** 2026-09-22, con
[PBI-360](https://github.com/Lara-srl/ada_controller/blob/683e2dd79d4a53fd39904b8e3e4bba66b5e47236/backlog/PBI-360-i-test-asdlc-escono-da-backend-tests.md) — le tre precondizioni
sono vere (§Decisione), l'estrazione è autorizzata anche se non fatta

## Contesto

`tools/asdlc_runner.py` è nato come utensile interno di aDa Controller. Dopo dieci giorni di
uso reale — quattro PBI eseguiti solo il 25/08 — non lo è più: è l'**implementazione del
metodo ASDLC**, e di aDa gli resta addosso pochissimo.

Il conto, misurato il 25/08:

```
834 righe totali                    +  730 righe di test
133  vuote
110  commenti
226  stringhe multilinea (5 prompt + docstring)
─────
365  righe di codice
```

Non è uno script da mille righe: è uno script da **365 righe** con addosso 336 righe di prosa
— che qui non è decorazione, è il *perché* di ogni soglia e di ogni diagnosi.

**Cosa è specifico di aDa:** la lista dei `Gate` (pytest · tsc · eslint · vitest · e2e, con le
loro `cwd`) e i percorsi (`backlog/PBI-*.md`, `specs/`, `AGENTS.md`). **Una ventina di righe di
configurazione**, non di logica.

**Cosa è del metodo, e vale altrove:**

- i **tre gate** e il principio che li tiene insieme — *«un agente che si autodichiara verde è
  un agente che ha imparato a dire verde»*; il Critic in **sessione separata**, modello
  diverso, senza permessi di scrittura, perché chi rilegge il proprio lavoro nella stessa
  sessione conferma le proprie premesse; e lo script che **non mergia mai**;
- il **vocabolario degli stati**, che è la cosa che ha retto meglio alla prova:
  `fermato` (il Builder chiede) ≠ `sospeso` (il Critic chiede) ≠ `non convergente` (le
  revisioni sono finite, e **non** vuol dire che il PBI fosse scritto male);
- il **protocollo di fermata** — scrivi la domanda nel PBI e fermati, invece di scegliere in
  silenzio. Il 25/08 ha fermato tre giri, e in tutti e tre il PBI aveva davvero un buco. Dal
  24/09 la fermata è una chiamata allo strumento `fermati` e non più la riga `STOP:`, e un
  agente che non chiama niente chiude `senza esito` (`ADR-0027`, `PBI-367`);
- la **rotazione delle sessioni**: una nuova per revisione, i ritentativi dentro la revisione
  la continuano;
- il **registro con i tre tempi separati** (builder · gate · critic), che è l'unica ragione
  per cui si è potuto dire *«il Critic è il 39% del giro»* invece di stimarlo;
- i **226 righe di prompt**: TDD, micro-commit, messaggi di commit leggibili senza il diff.
  È il pezzo più difficile da riscrivere bene.

**E il valore vero non è il codice: sono i dodici difetti.** In dieci giorni quello script ha
imparato dodici cose che nessuno avrebbe previsto scrivendolo — ramificare da `origin/main`
invece che da dove ci si trova, escludere il registro dal controllo d'igiene, distinguere un
giro speso a committare da un gate rosso, il lucchetto sul worktree, il PID della shell che
somiglia al PID del runner. Tre di quelli, il 25/08, sono costati ore. **Una riscrittura da
zero li riscopre tutti, uno alla volta, allo stesso prezzo** — ed è la ragione per cui questo
ADR esiste.

## Decisione

**Il runner si estrae come progetto suo, e non si riscrive.** Quando servirà un secondo
progetto in ASDLC, si parte da questo file e dai suoi test, non da una pagina bianca.

Prima dell'estrazione, tre cose vanno fatte **qui**, perché sono difetti anche per aDa:

1. **Le costanti diventano configurazione** — i gate, i percorsi e i comandi in un file
   (`asdlc.toml` o simile). Oggi si duplicherebbe il sorgente e si editerebbero venti righe:
   funziona, e diverge al primo aggiornamento.
2. **Il runner basta a se stesso.** Oggi `PATH` del venv e destinazione del registro vivono
   **fuori dal repository**, in `/home/laisdev/ada-notte.sh`. Conseguenza misurata il 25/08:
   **lo stesso runner si comporta in due modi a seconda di come lo si chiama** — le run
   notturne non hanno mai visto il crash su `pytest` né il registro non committato, i lanci
   diretti sì. Uno strumento riusabile non può avere due comportamenti.
3. **I test viaggiano con lui.** Le 730 righe di `test_asdlc_runner.py` sono metà dell'asset:
   sono i dodici difetti trasformati in regressioni. Senza, il progetto successivo li rifà.

Le prime due sono già nello scope di [PBI-102](../backlog/PBI-102-soglia-di-revisione-del-runner.md)
(difetti 11 e 12). La terza è già vera e va solo mantenuta tale.

Al 22/09/2026 sono tutte e tre vere, ognuna con la sua prova:

- [x] **① Le costanti diventano configurazione** —
  [PBI-358](https://github.com/Lara-srl/ada_controller/blob/683e2dd79d4a53fd39904b8e3e4bba66b5e47236/backlog/PBI-358-il-runner-legge-i-suoi-gate-da-asdlc-toml.md), in `main` dal
  22/09: `asdlc.toml` + `tools/asdlc_config.py`. Lo presidia `tools/tests/test_asdlc_config.py`.
- [x] **② Il runner basta a se stesso** — `ada-notte.sh` è sparito con la PR #141: `PATH` del
  venv e registro stanno in `asdlc.toml` (`[ambiente]`, `[registro]`). Il job CI `asdlc`
  (`pip install pytest` e nient'altro, niente `backend/requirements.txt`) lo ridimostra a
  ogni PR; lo aggiunge Francesco a `ci.yml`, perché il token del runner non scrive in
  `.github/workflows/`.
- [x] **③ I test viaggiano con lui** —
  [PBI-360](https://github.com/Lara-srl/ada_controller/blob/683e2dd79d4a53fd39904b8e3e4bba66b5e47236/backlog/PBI-360-i-test-asdlc-escono-da-backend-tests.md): i tre file
  `test_asdlc_*.py` stanno in `tools/tests/`, spostati con `git mv`, e li gira il gate `asdlc`
  di `asdlc.toml`. Fuori da `backend/tests/` non pagano più le fixture `autouse` di quel
  `conftest.py`: `tools/tests/test_asdlc_fuori_da_backend.py` conta zero connessioni SQLite
  in tutta la cartella.

Le 730 righe di test del 25/08, al 22/09, sono diventate 330 test sui tre file.

## Alternative scartate

**Riscriverlo da zero per il prossimo progetto, «adesso che sappiamo come si fa».** È la
strada che sembra più pulita e costa di più: le dodici lezioni non stanno nel disegno, stanno
nei casi limite — e i casi limite si riscoprono solo pagandoli. La versione nuova sarebbe più
elegante e meno esperta.

**Estrarlo subito in un pacchetto separato.** Prematuro: finché esiste **un solo** consumatore,
la configurazione la si progetterebbe su un caso solo — che è il modo di ottenere una
configurazione che va bene per uno. Si estrae quando il secondo progetto esiste e dice cosa
gli serve davvero.
> **Emendata il 25/09/2026 da `ADR-0026`.** Il «subito» resta scartato: il pacchetto nasce
> dopo le tre precondizioni e dopo la coda del runner fino a `PBI-372`. Ma la forma
> dell'estrazione è il pacchetto, installato da un tag git, e non la fotocopia. Il secondo
> consumatore è il repository `asdlc`, che sviluppa il runner con la versione rilasciata.

**Lasciarlo com'è e copiarlo all'occorrenza.** È ciò che succede se questo ADR non esiste: due
copie che divergono, e le correzioni fatte di là che non tornano mai di qua.

## Conseguenze

**Positive**
- Il prossimo progetto ASDLC parte con dieci giorni di lezioni già pagate.
- Le tre condizioni sono **difetti anche per aDa**: farle non è lavoro speso per il futuro, è
  lavoro che serve adesso — ed è il motivo per cui questa decisione non costa nulla in più.
- `tools/asdlc_runner.py` smette di essere un utensile e diventa una cosa che si **mantiene**:
  i difetti si scrivono in PBI-102 invece di essere aggiustati al volo.

**Negative**
- **La configurazione è lavoro vero**, e oggi non serve a nessuno: aDa ha un solo insieme di
  gate. Si accetta di farla adesso soltanto perché rende esplicito ciò che è specifico — che è
  metà dell'estrazione.
- **Un ADR su uno strumento interno**, non sul dominio. È fuori dal solito: gli altri sedici
  parlano di marginalità, stati e documenti. Sta qui perché *vincola il lavoro futuro e aveva
  alternative ragionevoli*, che è il criterio scritto in `decisions/README.md` — e perché
  senza, fra sei mesi, la scelta ovvia sarà riscriverlo.

## Cosa lo farebbe rivedere

Un secondo progetto ASDLC con gate **radicalmente diversi** — non un altro stack, ma un altro
modo di verificare (niente CI, niente PR, niente git). Lì la configurazione non basterebbe, e
la parte comune sarebbe solo il vocabolario degli stati e i prompt. In quel caso l'estrazione
diventa una **libreria di concetti**, non uno script parametrico.
