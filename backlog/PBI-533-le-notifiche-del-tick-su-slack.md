# PBI-533: le notifiche del tick su Slack, con un webhook

**Stato:** proposto il 26/10 su richiesta di Francesco («un canale Slack per le notifiche, così se il
runner si ferma lo so, tramite webhook»); **non letto**; accodato il 28/10 dopo la barriera `v1.0.0` (**da leggere con la lettura avversariale prima di toglierla**). Le due domande hanno una
**proposta** (*Deciso*, punti 3 e 6) che il merge della PR che accoda ratifica.

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
- `tools/asdlc/coda.py` — il punto in cui il tick scrive la sua riga nel log chiama le notifiche con la
  decisione, e con le righe del rilascio e dei guasti.
- `tools/asdlc/config.py` — la sezione `[notifiche]` (decisione 4).
- `asdlc.toml` e `template/asdlc.toml` — la sezione `[notifiche]`, spenta nel template e accesa qui.
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

## ❓ Domande aperte

**❓1 — Quali eventi?** (a) solo i fermi; (b) i fermi e le PR pronte da mergiare; (c) anche il
rilascio, la barriera e la coda finita.

**❓2 — Dove sta l'URL del webhook?** È un segreto: chi lo ha scrive nel canale. (a) una variabile
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
   notifica anche se ha lo stesso motivo del precedente.
3. **Proposta per ❓1: (c), con l'elenco in configurazione.** Gli eventi e il loro testo:

   | Evento | Quando | Messaggio |
   |---|---|---|
   | `fermo` | `Attende` senza PR, o `AttendeLaPreverifica` | «⛔ <progetto>: PBI-N fermo — <motivo>», con la domanda del rapporto se c'è |
   | `non-lanciato` | lo stesso `non lanciato` due tick di fila (come `PBI-532`, decisione 6) | «⛔ <progetto>: PBI-N non parte — <motivo>» |
   | `pronto` | `Attende` con la PR | «✅ <progetto>: PBI-N pronto, PR <url>» |
   | `rilascio` | il tick taglia un tag | «🏷️ <progetto>: <tag> da PBI-N» |
   | `barriera` | `Barriera` | «⏸️ <progetto>: barriera — <testo>» |
   | `finita` | `Finita` | «🏁 <progetto>: coda finita» |
   | `guasto` | lo stesso guasto del tick (`gh` che non risponde, un pre-flight) tre tick di fila | «⚠️ <progetto>: il tick non riesce — <riga>» |
   | `non-allineato` | il tick scrive `non allineato: …` (il checkout non è su `main`) | «⚠️ <progetto>: checkout non allineato — <ragione>» |
   | `reinstallazione` | il tick scrive `reinstallazione fallita: …` | «⚠️ <progetto>: reinstallazione fallita — <riga>» |
   | `pausa` | il tick scrive `in pausa: …` (globale o di progetto, `PBI-535`) | «⏸️ <progetto>: in pausa — <motivo>» |

   Le PR pronte servono perché i merge li fa Francesco: è lo stesso gesto che oggi si scopre guardando.
   `[notifiche].eventi` sceglie quali mandare; il default è tutti.
4. **Proposta per ❓2: (b).** L'URL sta in un file fuori dai repository, di default
   `~/.config/asdlc/slack-webhook`, una riga sola, permessi `600`. Lo leggono tutti i progetti della
   macchina: un webhook, un canale, e il nome del progetto in ogni messaggio. `[notifiche].webhook`
   in `asdlc.toml` può dare un altro percorso. Scartati: (a) il `crontab` va riscritto per ogni progetto
   e il segreto sta in un file che si copia nei backup (`crontab-backup-…`); (c) chiede di allargare le
   sezioni che il file locale può sovrascrivere, e va ripetuto in ogni progetto.
5. **L'URL non esce mai dal processo.** Né nel log, né nei rapporti, né nei messaggi d'errore, né nei
   test: un errore dice l'esito («HTTP 404», «scaduto dopo 10 s», «file del webhook assente»), mai
   l'indirizzo.
6. **Una notifica che fallisce non ferma niente** (`ADR-0008`). Timeout di 10 secondi, nessun
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
   webhook = "~/.config/asdlc/slack-webhook"
   eventi = ["fermo", "non-lanciato", "pronto", "rilascio", "barriera", "finita", "guasto",
              "non-allineato", "reinstallazione", "pausa"]
   ```

   Senza la sezione, o con `attive = false`, il tick non manda niente e non lo dice. Con `attive = true`
   e il file assente, lo dice una volta per evento nel log.
9. **Lo scope dei commit è `coda`**, `config` per `asdlc.toml` e il README, `template` per `template/`.

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

- [ ] **Un fermo manda un messaggio, uno solo.** Server HTTP finto su `127.0.0.1`, file del webhook in
      `tmp_path` col suo indirizzo, `gh` finto che dà un ramo senza PR e un rapporto `fermato`: il
      primo tick fa una `POST` con `text` che contiene il progetto, il PBI e il motivo; il secondo tick,
      con la stessa situazione, non ne fa. Rosso su `main`: nessuna `POST`.
- [ ] **Ogni evento ha il suo messaggio.** Parametrico, un id per evento della decisione 3: la
      decisione o la riga che lo produce danno il testo atteso; un evento fuori da `eventi` non manda
      niente. Rosso su `main`: il modulo non c'è.
- [ ] **Dopo un `lancia` lo stesso fermo si notifica di nuovo.** Fermo, lancia, stesso fermo: due
      `POST`. Rosso su `main`.
- [ ] **Una notifica che fallisce non ferma il tick e non svela l'URL.** Il server finto risponde 500,
      o non risponde entro il timeout: il tick scrive la sua decisione come sempre, una riga «notifica
      non inviata» in `coda.log`, e né il log né l'uscita contengono l'indirizzo del server. Il tick
      dopo ci riprova. Rosso su `main`.
- [ ] **Senza `[notifiche]` non cambia niente.** Un `asdlc.toml` senza la sezione: nessuna `POST` e
      nessuna riga in più nel log. È una **guardia**: su `main` è già così.
      `Guardia-su: tools/asdlc/coda.py::main`.

**Non regressione:** i test del tick restano verdi senza rete; `python3 -m pytest -q tools/tests` resta
verde.

## Protocollo di rifinitura

Si può scegliere senza chiedere: i nomi delle funzioni, la forma di `notifiche.json`, gli emoji e le
parole dei messaggi purché portino progetto, PBI e motivo. Si chiama `fermati`: se il tick non ha un
punto unico dove la decisione e le righe del rilascio passano insieme; se serve una dipendenza esterna.
