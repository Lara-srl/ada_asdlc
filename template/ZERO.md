# Il livello zero — il metodo senza il runner

Un progetto può adottare ASDLC **senza il pacchetto** `asdlc`: la struttura e il metodo, e
niente runner. È il **livello zero**, il gradino prima di `mvp` nella scala
zero → `mvp` → `staged` → `prod`: si sale soltanto, e il passaggio da zero a `mvp`, cioè
l'installazione del pacchetto, si fa con un ADR.

Questo file dice **cosa si copia** da `template/`, **cosa non si copia**, e **cosa si aggiunge
per salire a `mvp`**. Ogni file di `template/` è in una delle due liste, e in una sola: una
voce è un percorso relativo a `template/`, e un percorso che finisce con `/` vale per tutta
la cartella. A zero i PBI li esegue una persona con una sessione dell'agente, i gate li gira
la CI, e il merge resta un gesto umano: il metodo è lo stesso, cambia chi lancia il giro.

## Si copia

- `AGENTS.md` — la costituzione: il metodo, identico, e il dominio da scrivere. Due regole
  del metodo esistono solo per il runner, e a zero si tolgono a mano, così come sono citate
  qui sotto: la riga `MAI` sugli esiti dal testo libero (`ADR-0027`), e la frase di `SEMPRE`
  sul rosso chiesto prima (`ADR-0021`). Il resto della voce resta.

> - Un esito ricavato dal testo libero di un modello. Ciò che il codice decide da un agente
>   passa per una chiamata a strumento o per un output strutturato validato, senza ripiegare
>   sul testo (`decisions/ADR-0027-gli-esiti-passano-per-chiamate-a-strumento.md`).

> Nel giro del runner il permesso di scrivere produzione lo dà il rosso osservato, non la
>   parola di chi lo scrive (`decisions/ADR-0021-il-rosso-si-chiede-prima.md`).

- `CLAUDE.md` — il symlink ad `AGENTS.md`, per chi legge quel nome.
- `backlog/README.md` — le regole dei PBI, e il vocabolario dei difetti e delle cause.
- `backlog/TEMPLATE.md` — il modello di un PBI.
- `backlog/CODA.md` — la coda dei PBI: a zero la scrive e la lancia una persona, a mano,
  un PBI alla volta e nell'ordine scritto.
- `decisions/README.md` — le regole degli ADR e la tabella di quelli di metodo. La tabella
  nomina anche i sette ADR del runner, che a zero non ci sono: le righe restano, dicono
  cosa arriva con `mvp`.
- `decisions/TEMPLATE.md` — il modello di un ADR.
- `specs/README.md` — le regole delle spec.
- `specs/TEMPLATE.md` — il modello di una spec.
- `.github/PULL_REQUEST_TEMPLATE.md` — le tre cose che guarda chi mergia.
- `.github/workflows/ci.yml` — il gate CI è la verità anche a zero: una PR entra solo col
  job verde.
- `decisions/ADR-0008-osserva-e-segnala.md` — si segnala, non si blocca.
- `decisions/ADR-0009-e2e-playwright-nel-gate.md` — gli E2E stanno nel gate CI.
- `decisions/ADR-0011-dati-reali-nel-repository.md` — una regola abrogata resta scritta.
- `decisions/ADR-0012-ratifica-dei-cambi-di-costituzione.md` — chi beneficia di una
  decisione non la firma: la ratifica è il merge.
- `decisions/ADR-0015-la-deroga-allo-scope-si-dichiara.md` — la deroga allo Scope si
  dichiara nel commit.

## Non si copia

- `asdlc.toml` — la configurazione del runner: senza il pacchetto non la legge nessuno.
- `asdlc-aggiunte/` — le aggiunte del progetto ai prompt dei ruoli del runner.
- `.claude/` — l'hook di fase, che lancia il runner installato.
- `runs/` — il registro dei tempi lo scrive il runner.
- `.gitignore` — le sue regole sono tutte del runner: gli effimeri di `runs/`, il venv del
  pacchetto, `asdlc.local.toml`.
- `backlog/AUTOMAZIONE.md` — il tick e la riga di cron: l'autonomia che a zero non c'è.
- `decisions/ADR-0017-il-runner-e-un-prodotto-a-se.md` — il runner è un prodotto a sé.
- `decisions/ADR-0020-il-registro-dei-tempi-esce-dai-branch.md` — il registro dei tempi
  del runner.
- `decisions/ADR-0021-il-rosso-si-chiede-prima.md` — il gate del rosso del runner.
- `decisions/ADR-0022-il-verde-che-morde-passa.md` — i mutanti del gate del rosso.
- `decisions/ADR-0024-anti-pattern-nel-prompt-del-builder.md` — il prompt del Builder.
- `decisions/ADR-0026-il-runner-e-un-pacchetto-installato-da-tag.md` — il pacchetto
  installato da un tag.
- `decisions/ADR-0027-gli-esiti-passano-per-chiamate-a-strumento.md` — gli esiti del
  runner.
