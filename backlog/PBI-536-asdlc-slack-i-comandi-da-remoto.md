# PBI-536: `asdlc-slack`, i comandi del runner da Slack

**Stato:** proposto il 28/10 da Francesco («Slack per alcuni comandi base per gestire il runner da
remoto»); le scelte sono sue: ricezione per **polling del canale**, comandi **stato, pausa/riprendi,
rilancia**. Accodato dopo `PBI-535`. **Da leggere con la lettura avversariale prima di togliere la
barriera `v1.0.0`:** è il PBI che dà a una chat il potere di toccare il repository.

## Direttiva

`PBI-533` manda i messaggi del tick su Slack. Questo li risponde: un comando, lanciato dal `cron` ogni
minuto, legge i messaggi nuovi del canale, esegue un **vocabolario chiuso** e risponde nel thread.
Niente demone, nessuna porta aperta, nessuna dipendenza (`urllib.request`, come il 533).

**Scope**

- `tools/asdlc/slack.py` — nuovo: la lettura del canale, il vocabolario, la conferma, la risposta.
- `tools/pyproject.toml` — `asdlc-slack = "asdlc.slack:main"` in `[project.scripts]`.
- `README.md` — come si crea l'app, i permessi, il file di configurazione, la riga del `cron`.
- `tools/tests/test_asdlc_slack.py` — nuovo: i test dei criteri, con un server finto su `127.0.0.1`.
- `backlog/PBI-536-asdlc-slack-i-comandi-da-remoto.md` — questo file, per la spunta.
- **Fuori scope:** il merge, il rilascio e il pin (sono di Francesco, `ADR-0033`); qualunque comando
  che non sia nel vocabolario; la risposta alle domande dei PBI; il battito del tick.

## ✅ Deciso

1. **Una sola istanza per macchina**, non una per progetto: un'app, un canale. Il `cron` la lancia
   dal venv di un progetto (`ada_asdlc`); i progetti sono quelli di `~/.config/asdlc/progetti.toml`
   (`PBI-534`).
2. **Configurazione e segreti fuori dai repository**, in `~/.config/asdlc/slack.toml`: `canale`, `utenti`
   (gli **ID** Slack ammessi, non i nomi), `token` (il percorso di un file `600` col token bot,
   `chat:write` e `channels:history`), `conferma_minuti` (default 5), `api` (default
   `https://slack.com/api`, i test lo puntano al server finto). Il token non esce mai dal processo:
   né log, né risposte, né errori (`PBI-533`, decisione 5).
3. **Il vocabolario è chiuso e il testo non va mai a una shell né a un modello** (`ADR-0027`):
   - `stato [progetto]` — l'uscita di `asdlc-stato` (`PBI-534`);
   - `pausa <progetto> [motivo]` — `asdlc-coda --pausa` (`PBI-535`);
   - `riprendi <progetto>` — `asdlc-coda --togli-pausa`;
   - `rilancia <progetto> PBI-N` — `asdlc-chiudi-giro PBI-N` nel checkout del progetto.
   Ogni altra riga, o una riga che non comincia per una parola del vocabolario, riceve l'elenco dei
   comandi e non fa niente.
4. **Chi non è in `utenti` non riceve risposta e non ottiene effetti.** Il messaggio si ignora e si
   scrive una riga nel registro dei comandi.
5. **I comandi che scrivono (`pausa`, `riprendi`, `rilancia`) chiedono conferma nel thread:** il
   bot risponde «conferma?» e agisce solo se **lo stesso utente** scrive `conferma` entro
   `conferma_minuti`. `stato` risponde subito.
6. **`rilancia` rifiuta i fermi che chiedono una persona.** Se l'ultimo esito del PBI è
   `domanda-del-builder` o `domanda-del-critic` (`BLOCCHI`, `runner.py`) la risposta è il motivo e
   «risponde Francesco nel PBI»: rilanciare con lo stesso testo rifarebbe lo stesso giro. Per gli altri
   fermi (limite d'uso, albero sporco, `non lanciato`) si procede con `asdlc-chiudi-giro` dopo la
   conferma; se rifiuta (un giro in corso, il lucchetto) la sua riga d'errore va nella risposta.
7. **Un messaggio si elabora una volta.** L'ultimo `ts` visto sta in `~/.config/asdlc/slack-ts`, scritto
   solo dopo l'esecuzione; un'esecuzione interrotta riprova il messaggio, e i comandi che scrivono sono
   idempotenti (la pausa già messa, un ramo già chiuso).
8. **Un guasto non ferma niente** (`ADR-0008`): Slack che non risponde, un progetto illeggibile, un
   comando che fallisce → una riga nel registro dei comandi e, se si può, una risposta; uscita 0.
9. **Il registro dei comandi** è `~/.config/asdlc/slack-comandi.log`: ora, utente, comando, esito.

**Gesti umani, fuori dal giro:** Francesco crea l'app Slack (bot token con i due permessi) e il canale,
scrive `slack.toml` e il file del token, aggiunge al `crontab` la riga di `asdlc-slack` ogni minuto.

## Dipendenze

- Bloccato da: `PBI-534` (`stato`), `PBI-535` (`--pausa`/`--togli-pausa`), `PBI-533` (condivide il canale,
  la regola dei segreti e il modo di provare con un server finto).
- Blocca: nessuno.

## Contesto

- `tools/asdlc/chiudi_giro.py`, `tools/asdlc/coda.py` (`ultimo_esito()`, `lucchetto_del_tick()`),
  `tools/asdlc/runner.py` (`BLOCCHI`).
- `backlog/PBI-533-le-notifiche-del-tick-su-slack.md`, `decisions/ADR-0027-…`, `ADR-0008-…`, `ADR-0033-…`.
- Slack: `conversations.history` (messaggi dopo un `ts`), `chat.postMessage` con `thread_ts`.

## Verifica

- [ ] **`stato` da un utente ammesso risponde nel thread con una riga per progetto.** Server finto
      con un messaggio `stato` di un utente in `utenti`: una `chat.postMessage` col `thread_ts` del
      messaggio e il nome del progetto. Rosso su `main`: il comando non c'è.
- [ ] **Un utente fuori dalla lista non ottiene niente.** Messaggio `pausa ada_x` di un ID non
      ammesso: nessuna `chat.postMessage`, nessun file di pausa. Rosso su `main`.
- [ ] **Un comando che scrive agisce solo dopo la conferma dello stesso utente.** `pausa ada_x
      prova`: la risposta chiede conferma e il file non c'è; col `conferma` dello stesso utente il
      file `<registro>/pausa` c'è; il `conferma` di un altro utente, o oltre `conferma_minuti`, non
      lo crea. Parametrico, un id per caso. Rosso su `main`.
- [ ] **`rilancia` rifiuta una domanda e procede su un fermo meccanico.** Due progetti finti: uno con
      ultimo esito `domanda-del-builder` (rifiuto col motivo, `asdlc-chiudi-giro` finto non chiamato),
      uno con `albero-sporco-all-ingresso` (dopo la conferma `asdlc-chiudi-giro` è chiamato con il
      PBI). Rosso su `main`.
- [ ] **Una riga fuori dal vocabolario non esegue niente.** `rm -rf x`, `stato; ls`, una riga vuota:
      la risposta elenca i comandi e nessun processo parte. Parametrico. Rosso su `main`.
- [ ] **Un messaggio non si elabora due volte.** Due esecuzioni consecutive con lo stesso messaggio:
      una sola risposta. Rosso su `main`.
- [ ] **Il token non esce e un guasto non ferma.** Server finto che risponde 500: uscita 0, una riga
      nel registro dei comandi, e né l'uscita né i file scritti contengono il token. Rosso su `main`.

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde senza rete.

## Protocollo di rifinitura

Si può scegliere senza chiedere: la forma dei messaggi di risposta, i nomi delle funzioni, il
formato del registro. Si chiama `fermati`: se `asdlc-chiudi-giro` non si può chiamare per un
progetto diverso da quello della cartella di lavoro; se `PBI-534` o `PBI-535` non sono in `main`; se
serve una dipendenza esterna.
