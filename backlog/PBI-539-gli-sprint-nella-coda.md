# PBI-539: gli sprint nella coda

**Stato:** proposto il 31/10 da una sessione con Francesco («organizzare sempre i PBI in sprint […] e non
sviluppare mai per troppo senza far vedere artefatti al cliente»), con `ADR-0034`. Sprint 1 della coda di
questo repository.

## Direttiva

`ADR-0034` fa lavorare ogni progetto a sprint: da 1 a 5 PBI sotto un'intestazione `### Sprint N —
<risultato da mostrare>` di `CODA.md`, chiusi da una barriera `‖ revisione dello sprint N …`. Il tick di
oggi la barriera la sa già rispettare, ma l'intestazione per lui è prosa: non sa dire che uno sprint è
troppo lungo, che non dice cosa mostrare o che non finisce con la sua revisione, e quando arriva alla
revisione su Slack manda la stessa riga di una barriera qualunque.

Questo PBI insegna al runner a leggere gli sprint, **senza bloccare niente** (`ADR-0008`): avvisa al lancio
del primo PBI di uno sprint, manda la revisione su Slack col risultato e i PBI fatti, e mette gli sprint
nella panoramica di `PBI-538`. Porta anche `ADR-0034` nel `template/`, perché valga dai progetti futuri.

**Scope**

- `tools/asdlc/coda.py` — `Sprint` e `leggi_sprint(testo)`, nuovi; gli avvisi dello sprint accanto a quello
  delle domande, al lancio; la notifica della revisione quando la barriera è quella di uno sprint.
  `leggi_voci()` e `prossimo()` **non cambiano**: l'ordine e le fermate della coda restano quelli di oggi.
- `tools/asdlc/notifiche.py` — `revisione(progetto, sprint, fatti)`, nuova: un `Evento` di tipo
  `barriera` col testo della revisione.
- `tools/asdlc/panoramica.py` — la sezione `## Sprint` (decisione 5).
- `README.md`, `specs/solver-e-rilascio/spec.md` — gli sprint nella coda, nello stesso commit del codice.
- `template/decisions/ADR-0034-si-lavora-a-sprint.md` (copia identica), `template/decisions/README.md` (la
  riga nell'elenco degli ADR di metodo), `template/backlog/CODA.md` (l'esempio di uno sprint).
- `tools/tests/test_asdlc_sprint.py` (nuovo), `tools/tests/test_asdlc_panoramica.py`,
  `tools/tests/test_asdlc_template.py` (`ADR_DI_METODO` con `"0034"`, nel RED del criterio 5).
- `backlog/PBI-539-gli-sprint-nella-coda.md` — questo file, per la spunta.
- **Fuori scope:** cambiare l'ordine o le fermate della coda; scrivere `CODA.md` (il tick non la scrive
  mai, `PBI-350`); un nome di evento nuovo in `[notifiche].eventi` (la revisione è un evento `barriera`);
  `asdlc-stato`; convertire a sprint le code dei progetti (la scrive Francesco).

## ✅ Deciso

1. **La forma è quella di `ADR-0034`, decisione 3.** `RE_SPRINT = ^###\s+Sprint\s+(\d+)\s*—\s*(.*?)\s*$`:
   il numero e il risultato (vuoto se dopo `—` non c'è niente). Uno sprint contiene le voci `- PBI` e
   `- ‖` che seguono la sua intestazione, fino alla prossima intestazione `### Sprint` o `## `. Le voci
   prima del primo sprint, o dopo un `## ` che chiude l'ultimo, non sono di nessuno sprint.
2. **`leggi_sprint(testo) -> list[Sprint]`**, `Sprint(numero: int, risultato: str, pbi: tuple[str, ...],
   revisione: str | None)`: `pbi` in ordine di file; `revisione` è il testo della barriera dello sprint che
   comincia con `revisione dello sprint <numero>`, o `None`. Una coda senza intestazioni dà `[]`.
3. **Gli avvisi, al lancio del primo PBI di uno sprint** (il primo di `Sprint.pbi`), in coda alla riga del
   log come quello delle domande e senza trattenere il lancio:
   - `avviso, lo sprint N ha K PBI (al più 5)` se `K > 5` (la costante `PBI_PER_SPRINT = 5`);
   - `avviso, lo sprint N non dice il risultato da mostrare` se il risultato è vuoto;
   - `avviso, lo sprint N non finisce con la sua revisione` se `revisione` è `None`.
   Il lancio degli altri PBI dello sprint non ripete gli avvisi.
4. **La revisione su Slack.** Quando la decisione è una `Barriera` il cui testo è la `revisione` di uno
   sprint, l'evento è `asdlc_notifiche.revisione(...)` al posto di quello della barriera, con tipo
   `barriera` (stessa memoria, stesso filtro di `[notifiche].eventi`) e il testo
   `🎯 <progetto>: sprint N pronto per la revisione — <risultato> · fatti: PBI-a, PBI-b`, dove i fatti sono
   i PBI dello sprint in `pbi_mergiati()`. Una barriera che non è una revisione manda il messaggio di
   sempre. Con `gh` che non risponde i fatti sono `?`.
5. **Nella panoramica** (`PBI-538`), dopo la riga di `asdlc-stato`, una sezione `## Sprint` con una tabella
   `| Sprint | Risultato | Fatti | Stato |`, una riga per sprint: `Fatti` è `<fatti>/<totale>`; `Stato` è
   **chiuso** se tutti i PBI sono fatti e la barriera di revisione non c'è più, **in revisione** se sono
   tutti fatti e la barriera c'è, **in corso** se almeno uno è fatto o ha un ramo, **da fare** altrimenti.
   Senza sprint la sezione non c'è. Le sezioni di oggi non cambiano.
6. **`ADR-0034` è un ADR di metodo:** la sua copia in `template/decisions/` è identica byte per byte, come
   le altre (`test_gli_adr_di_metodo_sono_nel_template_identici_e_numerati_come_qui`), e il template mostra
   uno sprint d'esempio in `CODA.md`.

## Dipendenze

- Bloccato da: `PBI-538` (la panoramica), `ADR-0034` (in `main` con la PR che accoda questo PBI).
- Blocca: nessuno.

## Contesto

- `decisions/ADR-0034-si-lavora-a-sprint.md`; `backlog/PIANO-SPECIFICHE.md` §8 di `ada_dispense`, dove la
  regola è nata.
- `tools/asdlc/coda.py`: `leggi_voci()`, `RE_BARRIERA`, `avviso_domande()` e il punto in cui la riga del
  lancio lo aggiunge (`passaggio()`), `pbi_mergiati()`, `pbi_con_ramo()`, `notifica()`.
- `tools/asdlc/notifiche.py`: l'`Evento` della `Barriera` (righe ~110-116).
- `tools/tests/test_asdlc_template.py`: `ADR_DI_METODO`.

## Verifica

- [ ] **`leggi_sprint` legge gli sprint.** Un testo con `PBI-0` prima di ogni sprint, `### Sprint 1 — il
      PDF` con `PBI-1`, `PBI-2` e `‖ revisione dello sprint 1 con Jona: il PDF`, poi `### Sprint 2 —` (senza
      risultato) con `PBI-3`: due `Sprint` con numeri, risultati (`"il PDF"`, `""`), PBI e revisione
      (`None` per il 2); `PBI-0` non è in nessuno; `leggi_voci()` dà sullo stesso testo le voci di prima.
      Rosso su `main`: `leggi_sprint` non c'è.
- [ ] **Gli avvisi al lancio del primo PBI dello sprint.** Un tick con `decidi` che dà `Lancia(PBI-1)` e una
      coda con lo sprint 1 di sei PBI, senza risultato e senza barriera: la riga del log ha i tre avvisi
      della decisione 3 e il lancio avviene; con `Lancia(PBI-2)` nessun avviso. Rosso dopo il criterio 1:
      il tick non legge gli sprint.
- [ ] **La revisione va su Slack col risultato e i fatti.** Notifiche accese con un webhook finto, `decidi`
      che dà `Barriera("revisione dello sprint 1 con Jona: il PDF")`, la coda del criterio 1 e `PBI-1`
      mergiato: una `POST` il cui testo contiene `sprint 1 pronto per la revisione`, `il PDF` e `PBI-1`, e
      non `PBI-2`. Con `Barriera("pin")` il testo è quello di sempre (`barriera — pin`). Rosso dopo i
      criteri 1-2.
- [ ] **La panoramica ha la tabella degli sprint.** La coda del criterio 1 con `PBI-1` e `PBI-2` mergiati e
      la barriera ancora lì: la riga dello sprint 1 è `| 1 | il PDF | 2/2 | in revisione |`, quella del 2 è
      `| 2 |  | 0/1 | da fare |`; una coda senza sprint non ha `## Sprint`. Rosso dopo i criteri 1-3.
- [ ] **`ADR-0034` è nel template.** `ADR_DI_METODO` ha `"0034"`; la copia in `template/decisions/` è
      identica, linkata nel suo `README.md`; `template/backlog/CODA.md` ha un'intestazione `### Sprint 1 — `.
      Rosso su `main`: la copia non c'è (il test aggiornato nel RED fallisce).

**Non regressione:**
- Una coda senza sprint decide, avvisa e notifica come oggi: i test di `test_asdlc_coda.py` e di
  `test_asdlc_notifiche.py` restano verdi.
- `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura

Si può scegliere senza chiedere: i nomi delle funzioni private, dove sta `PBI_PER_SPRINT` in `coda.py`.
Si chiama `fermati`: se `PBI-538` non è in `main`; se servisse cambiare `leggi_voci()` o `prossimo()`; se
un test esistente fissa il testo della riga del lancio in modo che gli avvisi lo rompano.
