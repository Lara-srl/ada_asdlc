# PBI-502: il metodo in `template/` — costituzione, regole delle cartelle, ADR, coda

## Direttiva

Terzo dei quattro PBI di `template/` (D5 di `SCAFFOLDING.md` di aDa). Entra in `template/`
**il metodo**: ciò che un progetto nuovo deve sapere per lavorare col runner, senza niente
del dominio di chi l'ha scritto.

- `template/AGENTS.md` — la parte `## Metodo` **identica** a quella di `AGENTS.md` di qui, e
  una parte `## Dominio` scritta a istruzioni: cosa ci va, non cosa c'è.
- `template/CLAUDE.md` — un link simbolico ad `AGENTS.md`, come qui.
- `template/backlog/README.md`, `template/decisions/README.md`, `template/specs/README.md` —
  le regole di ogni cartella, ciascuna col rimando al suo `TEMPLATE.md` (`PBI-500`).
- `template/decisions/ADR-*.md` — i dodici ADR di metodo, **copiati senza rinumerare** e
  identici a quelli di `decisions/`.
- `template/backlog/CODA.md` — la grammatica della coda, con la coda vuota.
- `template/backlog/AUTOMAZIONE.md` — la parte di metodo di `backlog/AUTOMAZIONE.md`, con la
  riga di cron documentata.

**Scope**
- I file qui sopra — nuovi.
- `tools/tests/test_asdlc_template.py` — i test dei criteri.
- `backlog/PBI-502-il-metodo-in-template.md` — questo file, per la spunta.
- **Fuori scope:** `AGENTS.md`, `backlog/` e `decisions/` di questo repository, che non
  cambiano; le revisioni degli ADR elencate in `backlog/RILETTURA-ADR-DI-METODO.md`, che sono
  lavoro loro e si copiano dopo, quando ci sono; `ZERO.md` (`PBI-503`).

**`template/AGENTS.md` non è la costituzione di questo repository**: è un file da copiare.
La regola di `ADR-0012` vale per `AGENTS.md` della radice, che questo PBI non tocca.

**Nessun file di produzione.** Il giro resta in `TEST_ONLY` dall'inizio alla fine e non
chiama mai `--chiedi-impl` (difetto 89 di `PBI-102`). Durante il giro il runner non lancia
nessun file dello Scope.

## ✅ Deciso, per non fermare il giro

1. **Ogni test asserisce prima che il suo file ci sia**, così su `main` il rosso è un
   fallimento per asserzione e non un errore. Nessuna asserzione nelle fixture.
2. **La parte `## Metodo` si confronta come testo**: dalla riga `## Metodo` esclusa alla riga
   `## Dominio` esclusa, in `AGENTS.md` e in `template/AGENTS.md`, uguali carattere per
   carattere. È la regola di `ADR-0028` di aDa («`## Metodo` vale identica in ogni progetto»)
   fatta controllare dal codice: quando il metodo cambia qui, il test obbliga a cambiarlo
   anche nel template, nella stessa PR.
3. **`## Dominio` del template ha quattro sottosezioni a istruzioni**: `### Toolchain`,
   `### Confini di giudizio`, `### Sorgenti`, `### Scope dei commit`. Sotto ognuna una o due
   righe dicono cosa ci si scrive, fra parentesi quadre come nei modelli di `PBI-500`.
4. **I dodici ADR di metodo** sono `0008 0009 0011 0012 0015 0017 0020 0021 0022 0024 0026
   0027`: l'elenco di `SCAFFOLDING.md` §5b di aDa. Si copiano così come sono, byte per byte.
   L'elenco vive nel test come costante, perché è una decisione e non si ricava dai file:
   `ADR-0028` di questo repository, per esempio, è di dominio e non si copia.
5. **`ADR-0017` cita `../backlog/PBI-102-…`**, che nel template non c'è. Il link resta rotto
   nella copia, perché la copia è identica; `template/decisions/README.md` lo dice in una riga
   («`PBI-102` è il registro dei difetti del runner, nel repository del pacchetto»). La
   guardia dei nomi e dei percorsi di `PBI-500` lascia già fuori questi file.
6. **`template/decisions/README.md`** ha la tabella dei dodici con un link per riga, la regola
   delle quattro domande e il numero del prossimo ADR del progetto nuovo: **0028**. Le frasi
   che sono storia di questo repository («copiati al commit di estrazione», il difetto 74
   raccontato) non entrano: entra la regola.
7. **Il vocabolario delle cause è lo stesso slug per slug**, e la colonna dei PBI di approccio
   del template è vuota: i PBI di approccio sono del progetto che li apre.
8. **`template/backlog/AUTOMAZIONE.md` porta la parte di metodo** di `backlog/AUTOMAZIONE.md`:
   il giro del runner, i gate, il rosso e il morso, il runner installato, la riga di cron,
   spegnere il tick e chiudere un giro fermato, la regola che regge tutto. Le tre sezioni
   🟢 🟡 🔴 restano come intestazioni con una riga che dice cosa ci va, senza i PBI di qui.
   Non entrano `~/asdlc-tick.sh`, i PBI e i difetti citati per numero, né «In aDa resta
   `true`»: la guardia di `PBI-500` li ferma.
9. **La riga di cron del template** è
   `*/10 * * * * cd <checkout> && <checkout>/<pacchetto>/bin/asdlc-coda >> runs/cron.log 2>&1`
   con `<pacchetto>` sostituito dal valore di `[ambiente].pacchetto` di `template/asdlc.toml`
   (`PBI-501`) e `<checkout>` lasciato così: è il segnaposto che chi installa sostituisce. È
   la sola riga del file che comincia con `*/10 `.
10. **Lo scope dei commit è `template`** (`ADR-0028`).

## Dipendenze
- Bloccato da: `PBI-501` (il criterio della riga di cron legge `template/asdlc.toml`), e
  quindi da `PBI-500`.

## Contesto
- `AGENTS.md` — la parte `## Metodo`, e la parte `## Dominio` per vedere cosa ci si scrive.
- `backlog/README.md` — le regole dei PBI e §I difetti e le loro cause, con la tabella del
  vocabolario.
- `backlog/CODA.md` — la grammatica (`- PBI-…`, `- ‖ …`, la prosa che il tick non guarda).
- `tools/asdlc/coda.py` — `leggi_voci()`, che il test usa sulla coda del template.
- `backlog/AUTOMAZIONE.md` — le sezioni da cui si prende la parte di metodo.
- `decisions/README.md` — le regole degli ADR e le quattro domande.
- `backlog/RILETTURA-ADR-DI-METODO.md` — perché gli ADR si copiano come sono, e le loro
  revisioni vengono dopo.

## Verifica
- [x] **La costituzione del template ha il metodo di qui e un dominio da scrivere.** La parte
      `## Metodo` di `template/AGENTS.md` è uguale a quella di `AGENTS.md`; la parte
      `## Dominio` ha le quattro sottosezioni della decisione 3, nell'ordine;
      `template/CLAUDE.md` è un link simbolico che punta ad `AGENTS.md`.
- [ ] **Ogni cartella del metodo spiega le sue regole e rimanda al suo modello.**
      `template/backlog/README.md`, `template/decisions/README.md` e
      `template/specs/README.md` esistono, e ognuno contiene un link `](TEMPLATE.md)` che porta
      a un file che c'è. Un criterio solo con tre esempi: un test parametrico, un id per
      cartella.
- [ ] **Gli ADR di metodo sono nel template, identici e numerati come qui.** Per ognuno dei
      dodici numeri della decisione 4, `template/decisions/` ha un file con lo stesso nome di
      quello di `decisions/` e lo stesso contenuto; `template/decisions/README.md` ha un link
      a ognuno, e dice che il prossimo ADR è lo `0028`.
- [ ] **Il vocabolario delle cause del template è quello di qui.** Gli slug della tabella di
      §I difetti e le loro cause in `template/backlog/README.md` sono gli stessi, nello stesso
      ordine, di quelli in `backlog/README.md`; e la colonna dei PBI di approccio è vuota in
      ogni riga.
- [ ] **La coda del template è vuota e ne porta la grammatica.** `coda.leggi_voci()` sul testo
      di `template/backlog/CODA.md` torna una lista vuota; il file ha la sezione `## La coda`,
      e nella prosa sopra nomina le due forme di riga, `- PBI-` e `- ‖`.
- [ ] **La riga di cron del template lancia il tick del pacchetto del template.** In
      `template/backlog/AUTOMAZIONE.md` c'è una riga sola che comincia con `*/10 `, ed è quella
      della decisione 9 col `pacchetto` di `template/asdlc.toml`.

**Non regressione:**
- La guardia di `PBI-500` resta verde con i file nuovi (gli ADR copiati ne sono fuori per
  nome).
- I test di `PBI-500` e `PBI-501` restano verdi senza cambiare.
- `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura
Una regola di metodo vive in un posto solo qui, e il template ne è una copia tenuta uguale
da un test. Se una regola cambia qui, la PR che la cambia cambia anche la copia, e lo dice.
