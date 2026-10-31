# PBI-533: le notifiche del tick su Slack, con un webhook

**Stato:** proposto il 26/10 su richiesta di Francesco («un canale Slack per le notifiche, così se il
runner si ferma lo so, tramite webhook»); accodato il 28/10 dopo la barriera `v1.0.0`; letto il 30/10 col Lettore (in fondo, *Protocollo*): tre
fermi e sette rilievi minori recepiti. Le due domande hanno una **proposta** (*Deciso*, punti 3 e 4) che
il merge della PR che accoda ratifica.

## Direttiva

Oggi un fermo si scopre guardando: `runs/coda.log` di un progetto, una PR, un `attende` che si ripete.
Il 26/10 il tick di `ada_asdlc` ha scritto 84 volte lo stesso `non lanciato` in 14 ore, e nessuno lo ha
saputo. Il 25/10 `PBI-524` ha aspettato otto ore dopo il reset del limite d'uso. Il tick gira in sei
progetti sulla stessa macchina (`ada_controller`, `ada_asdlc`, `ada_planning`, `ada_dispense`,
`ada_nlt`, `ada_unical_exec`), ognuno col suo log.

`PBI-510` aveva lasciato il canale a Francesco («mandare l'avviso fuori dal log: il canale lo sceglie
Francesco in un PBI»). `PBI-525` (decisione 6) apre una issue su GitHub per un `non convergente`: è il
registro, non una notifica, e copre un solo caso. Francesco sceglie **Slack, con un Incoming Webhook**.

Il tick manda un messaggio su Slack quando la sua decisione **cambia** verso uno stato che chiede una
persona, o che una persona vuole sapere. Un messaggio per cambio, non uno ogni dieci minuti.

**Scope**

- `tools/asdlc/notifiche.py` — nuovo: la classificazione della decisione in evento, la memoria
  dell'ultimo evento mandato, l'invio con `urllib.request` della libreria standard (il pacchetto non ha
  dipendenze, `tools/pyproject.toml`, e non ne prende).
- `tools/asdlc/coda.py` — in `passaggio()` e in `fermo_in_pausa()`, ogni punto che oggi scrive nel log
  una riga della tabella della decisione 3 chiama anche le notifiche (decisione 10); `Barriera` prende
  un campo che dice se nasce da un guasto (decisione 3).
- `tools/asdlc/config.py` — la sezione `[notifiche]` (decisione 4).
- `asdlc.toml` e `template/asdlc.toml` — la sezione `[notifiche]`, spenta nel template e accesa qui.
- `tools/tests/` — i test lavorano su un repository temporaneo in `tmp_path`, mai sul progetto di prova
  in `tools/tests/dati/`, così `notifiche.json` non sporca l'albero.
- `README.md` — come si crea il webhook e dove si mette, nello stesso commit del codice.
- `tools/tests/` — i test dei criteri, con un server HTTP finto su `127.0.0.1` e nessuna rete.
- `backlog/PBI-533-le-notifiche-del-tick-su-slack.md` — questo file, per la spunta.
- **Fuori scope:** il tick che non gira affatto (un cron spento, la macchina spenta): nessun tick,
  nessun messaggio, ed è il battito di `PBI-510`; i messaggi del runner dentro il giro; la issue di
  `PBI-525`, che resta com'è; i pulsanti o le risposte da Slack.

**Aggiunta del 28/10.** Gli ultimi tre eventi della tabella (`non-allineato`, `reinstallazione`, `pausa`)
sono i fermi silenziosi visti quel giorno: due checkout fermi per ore su un ramo, e una barriera ferma
per venti. Valgono la regola «un messaggio per cambio» come gli altri, e il criterio «ogni evento ha il
suo messaggio» li copre nello stesso test parametrico.

## Domande, chiuse dal *Deciso*

**1 — Quali eventi?** (a) solo i fermi; (b) i fermi e le PR pronte da mergiare; (c) anche il
rilascio, la barriera e la coda finita.

**2 — Dove sta l'URL del webhook?** È un segreto: chi lo ha scrive nel canale. (a) una variabile
d'ambiente nel `crontab`; (b) un file fuori dai repository, letto da tutti i progetti; (c)
`asdlc.local.toml`, che non è versionato ma oggi accetta solo alcune sezioni.

## ✅ Deciso

1. **Il messaggio nasce dalla decisione del tick, non dal testo.** Il tick ha già una decisione con un
   tipo (`Attende`, `Barriera`, `Finita`, `AttendeLaPreverifica`, …) e già legge l'ultimo esito del
   PBI (`ultimo_esito()`, `PBI-519`). L'evento si ricava da questi, in codice: niente si ricava dal
   testo di un modello (`ADR-0027`).
2. **Un messaggio per cambio.** Il tick tiene l'ultimo evento mandato in `<registro>/notifiche.json`
   del checkout (la cartella è ignorata). Un evento uguale al precedente, stesso tipo, stesso PBI e
   stesso motivo, non si rimanda. Un `lancia` o un `occupato` azzera la memoria, così il fermo dopo si
   notifica anche se ha lo stesso motivo del precedente. **Fa eccezione il conto dei `non lanciato`**,
   che sta a parte nello stesso file: un `lancia` seguito nello stesso tick da `non lanciato` non lo
   azzera, perché è proprio quella la coppia che si ripete. «Lo stesso» `non lanciato` vuol dire **lo
   stesso PBI** (il testo del `Guasto` porta l'uscita di un comando e cambia da un tick all'altro).
   Il conto dei `guasto` si tiene allo stesso modo, per stesso tipo di sorgente.
3. **Proposta per la domanda 1: (c), con l'elenco in configurazione.** Gli eventi, la loro sorgente
   nel codice e il loro testo:

   | Evento | Quando | Messaggio |
   |---|---|---|
   | `fermo` | `Attende` con `pr == ()` (nessuna PR), o `AttendeLaPreverifica` | «⛔ <progetto>: PBI-N fermo — <motivo>», con la domanda del rapporto se c'è |
   | `non-lanciato` | la riga `non lanciato: …` di `passaggio()` (un `Guasto` di `lancia()`, pre-flight compreso) per lo stesso PBI due tick di fila | «⛔ <progetto>: PBI-N non parte — <motivo>» |
   | `pronto` | la riga `merge: #N attende una persona — <manca>` di `passo_del_merge()` | «✅ <progetto>: PR #N da mergiare a mano — <manca>» |
   | `rilascio` | il tick taglia un tag | «🏷️ <progetto>: <tag> da PBI-N» |
   | `barriera` | `Barriera` scritta in `CODA.md` | «⏸️ <progetto>: barriera — <testo>» |
   | `finita` | `Finita` | «🏁 <progetto>: coda finita» |
   | `guasto` | una `Barriera` nata in `decidi()` da un `Guasto` o da una coda che non si legge (il campo nuovo di `Barriera`, non il testo), o `Attende` con `pr is None` (`gh` muto), tre tick di fila | «⚠️ <progetto>: il tick non riesce — <riga>» |
   | `non-allineato` | il tick scrive `non allineato: …` (il checkout non è su `main`) | «⚠️ <progetto>: checkout non allineato — <ragione>» |
   | `reinstallazione` | il tick scrive `reinstallazione fallita: …` | «⚠️ <progetto>: reinstallazione fallita — <riga>» |
   | `pausa` | `fermo_in_pausa()` scrive `in pausa: …` (globale; di progetto con `PBI-535`, la cui riga comincia allo stesso modo) | «⏸️ <progetto>: in pausa — <motivo>» |

   `Attende` con la PR (`pr` non vuoto) non è un evento: dalla `v1.0.0` il tick mergia da solo, e una PR
   aperta che passa le condizioni aspetta solo la CI. Quella che aspetta una persona la dice la riga del
   merge, ed è l'evento `pronto`. `[notifiche].eventi` sceglie quali mandare; il default è tutti.
4. **Proposta per la domanda 2: (b).** L'URL sta in un file fuori dai repository,
   `~/.config/asdlc/slack-webhook` (calcolato quando serve da `Path.home()`, come `file_di_pausa()`),
   una riga sola, permessi `600`. Lo leggono tutti i progetti della macchina: un webhook, un canale, e
   il nome del progetto in ogni messaggio. **Il percorso non sta in `asdlc.toml`**, che non porta
   percorsi di macchina (l'intestazione del file lo dice: un `~` lì è un errore). Scartati: (a) il `crontab` va riscritto per ogni progetto
   e il segreto sta in un file che si copia nei backup (`crontab-backup-…`); (c) chiede di allargare le
   sezioni che il file locale può sovrascrivere, e va ripetuto in ogni progetto.
5. **L'URL non esce mai dal processo.** Né nel log, né nei rapporti, né nei messaggi d'errore, né nei
   test: un errore dice l'esito («HTTP 404», «scaduto dopo 10 s», «file del webhook assente»), mai
   l'indirizzo.
6. **Una notifica che fallisce non ferma niente** (`ADR-0008`). Timeout di 10 secondi, una costante
   del modulo che i test abbassano, nessun
   tentativo ripetuto nello stesso tick, una riga «notifica non inviata: <esito>» in `coda.log`, e il
   tick prosegue. La memoria dell'ultimo evento si aggiorna solo se l'invio è riuscito: il tick dopo
   ci riprova.
7. **Il messaggio è testo semplice**, nel campo `text` del JSON che il webhook accetta. Il nome del
   progetto è la cartella del checkout (`ada_nlt`, `ada_asdlc`, …).
8. **Configurazione:**

   ```toml
   [notifiche]
   # Le notifiche del tick su Slack (PBI-533). Il webhook è un segreto e non sta qui.
   attive = true
   eventi = ["fermo", "non-lanciato", "pronto", "rilascio", "barriera", "finita", "guasto",
              "non-allineato", "reinstallazione", "pausa"]
   ```

   Senza la sezione, o con `attive = false`, il tick non manda niente e non lo dice. Con `attive = true`
   e il file assente, lo dice una volta per evento nel log.
9. **Lo scope dei commit è `coda`**, `config` per `asdlc.toml` e il README, `template` per `template/`.
10. **L'aggancio è in `passaggio()`, sito per sito.** Non c'è un punto unico dove passano la decisione e
    le righe del rilascio: `passaggio()` esce prima di `decidi()` per la pausa, il non allineato e la
    reinstallazione, e scrive le righe del merge e del rilascio prima della decisione. Ogni sito che oggi
    chiama `scrivi_nel_log()` per una riga della tabella chiama anche una funzione di `notifiche.py` con
    l'evento già classificato; la classificazione dei tipi di `Decisione` sta in `notifiche.py`.

**Gesti umani, fuori dal giro:** Francesco crea l'app Slack con l'Incoming Webhook sul canale scelto e
scrive l'URL nel file della decisione 4. Il messaggio arriva nei progetti dopo il tag e il pin, come
ogni cambio del tick (`ADR-0026`).

## Dipendenze

- Bloccato da: nessuno. Se `PBI-532` è già in `main`, l'evento `non-lanciato` legge il motivo che quel
  PBI mette nel `Guasto`; se non c'è, usa la riga di oggi.
- Blocca: nessuno.

## Contesto

- `tools/asdlc/coda.py`: `decidi` (le decisioni del tick), `racconta()`, `scrivi_nel_log()`,
  `ultimo_esito()`, `passo_di_rilascio()`, `lancia()`, `pr_sul_ramo()`.
- `tools/asdlc/config.py`: le sezioni e `asdlc.local.toml`.
- `backlog/PBI-510-il-battito-del-tick.md`, `backlog/PBI-525-…md` (decisione 6),
  `backlog/PBI-532-…md` (decisione 6).
- Il formato del webhook: una `POST` con `Content-Type: application/json` e `{"text": "…"}`; Slack
  risponde `200` con `ok`.

## Verifica

- [x] **Un fermo manda un messaggio, uno solo.** Server HTTP finto su `127.0.0.1`, `HOME` in `tmp_path`
      col file del webhook che porta il suo indirizzo, un `origin` locale col ramo del PBI, `gh` finto
      senza PR e un rapporto `fermato`: il
      primo tick fa una `POST` con `text` che contiene il progetto, il PBI e il motivo; il secondo tick,
      con la stessa situazione, non ne fa. Rosso su `main`: nessuna `POST`.
- [x] **Ogni evento ha il suo messaggio.** Parametrico, un id per evento della decisione 3 **tranne
      `fermo`**, che è il criterio 1: la sorgente della tabella dà il testo atteso; per `non-lanciato`
      due tick di fila con `lancia` e `non lanciato` dello stesso PBI, e la `POST` solo al secondo; per
      `guasto` tre tick, e la `POST` solo al terzo; un evento fuori da `eventi` non manda niente. Rosso
      dopo il criterio 1: nessun altro evento manda.
- [x] **Dopo un `lancia` lo stesso fermo si notifica di nuovo.** Fermo, lancia, stesso fermo: due
      `POST`. Rosso su `main`.
- [x] **Una notifica che fallisce non ferma il tick e non svela l'URL.** Il server finto risponde 500,
      o non risponde entro il timeout: il tick scrive la sua decisione come sempre, una riga «notifica
      non inviata» in `coda.log`, e né il log né l'uscita contengono l'indirizzo del server. Il tick
      dopo ci riprova. Rosso su `main`.
- [x] **Senza `[notifiche]` non cambia niente.** Un `asdlc.toml` senza la sezione: nessuna `POST` e
      nessuna riga in più nel log. È una **guardia**: su `main` è già così.
      `Guardia-su: tools/asdlc/coda.py::main`.

**Non regressione:** i test del tick restano verdi senza rete; `python3 -m pytest -q tools/tests` resta
verde.

## Protocollo di rifinitura

Si può scegliere senza chiedere: i nomi delle funzioni, la forma di `notifiche.json`, gli emoji e le
parole dei messaggi purché portino progetto, PBI e motivo. Si chiama `fermati`: se serve una dipendenza
esterna.

**Lettura del 30/10** (Lettore separato, sola lettura, su `main` `13d6641`): tre fermi — il
`non-lanciato` che non scattava mai, perché il `lancia` dello stesso tick azzerava la memoria (decisione
2); la sorgente di `guasto`, che oggi è una `Barriera` o un `Attende` senza distinzione (decisione 3); la
condizione di `fermati` vera sulla base, nessun punto unico (decisione 10) — e sette rilievi minori: il
percorso del webhook fuori da `asdlc.toml` (decisione 4); la pausa di progetto con la riga di `PBI-535`;
`pronto` dalla riga del merge, perché dalla `v1.0.0` mergia il tick; il timeout come costante; i test su
un repository temporaneo; `fermo` tolto dal criterio 2; la sezione delle domande senza l'emoji della domanda, che faceva
scattare l'avviso a ogni lancio; il ramo dall'`origin` e non da `gh`.
