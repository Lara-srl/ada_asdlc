# PBI-537: lo Scope si legge per intero, i file in radice compresi, e senza il «Fuori scope»

**Stato:** proposto il 30/10 in una sessione con Francesco, che lo vuole **in testa** alla coda della
`v1.1.0`, prima di `PBI-534` (Francesco, 30/10: «procedi» sul piano). Letto il 30/10 (in fondo, *Protocollo*).

## Direttiva

Dalla `v1.0.0` il tick mergia da solo la PR di un giro, e una delle condizioni di `ADR-0033` è che
**ogni file della PR stia nello Scope del PBI**. I percorsi li dà `percorsi_dello_scope()` in
`runner.py`, la stessa funzione che dà alla pre-verifica gli avvisi dei percorsi che alla base non ci
sono (`PBI-520`, decisione 5). Il 30/10, sulla `#44` di `ada_dispense` (`PBI-009`), la funzione ha
mostrato due difetti:

1. **Un file in radice non conta.** Lo Scope di `PBI-009` dice ``- `requirements.txt` — `weasyprint`
   fissato…``; la funzione tiene solo i percorsi con una `/`, e il tick ha scritto `merge: #44 attende
   una persona — il file requirements.txt è fuori dallo Scope`. Un fermo meccanico: la PR era in regola,
   e una persona l'ha mergiata a mano. Lo stesso vale per `README.md`, `pyproject.toml`, `Makefile`.
2. **Il «Fuori scope» conta come Scope.** Lo stesso PBI scrive, sotto `- **Fuori scope:**`,
   ``- `assets/style.css`: non cambia``, e la funzione rende `assets/style.css` fra i percorsi dello
   Scope. Un giro che toccasse proprio il file che il PBI vieta passerebbe la condizione, e il tick lo
   mergerebbe da solo. È il difetto peggiore dei due, perché indebolisce la guardia del merge
   automatico invece di fermarla. Nella pre-verifica dà anche un avviso sbagliato: un file del «Fuori
   scope» che alla base non c'è è «nominato dallo Scope e non detto nuovo».

**Scope**

- `tools/asdlc/runner.py` — `percorsi_dello_scope()` (decisioni 1-3).
- `tools/tests/test_asdlc_preverifica.py` — i test di `percorsi_dello_scope()` e dell'avviso (criteri 1-2).
- `tools/tests/test_asdlc_rilascio.py` — gli scenari del merge (criteri 1-2).
- `README.md` — la frase sulle condizioni del merge (punto 5 del giro), nello stesso commit del
  comportamento.
- `backlog/PBI-537-lo-scope-si-legge-per-intero-e-senza-il-fuori-scope.md` — questo file, per la spunta.
- **Fuori scope:** `blocco_dello_scope()`, che resta com'è: la leggono anche `forma_del_pbi()` e
  `controllo_r7()`, che non cambiano; `ADR-0033`, che nomina la funzione e non la sua regola; le
  altre condizioni del merge.

## ✅ Deciso, per non fermare il giro

1. **Il «Fuori scope» chiude i percorsi.** Le righe dello Scope si leggono fino alla prima che
   contiene `Fuori scope` (senza distinguere maiuscole), **esclusa**; quella riga e tutte le seguenti
   del blocco non danno percorsi. È la forma di `template/backlog/TEMPLATE.md` (`- **Fuori scope:** …`,
   ultima voce dello Scope) e di tutti i PBI dei cinque progetti; il «Fuori scope» a metà Scope non c'è
   e non si prevede. La regola sta in `percorsi_dello_scope()`, non in `blocco_dello_scope()`: la forma
   (`forma_del_pbi()`) e `R7` leggono lo stesso blocco e non cambiano (*Fuori scope*).
2. **I percorsi in testa a una voce contano anche senza `/`.** In una riga che comincia con `- `
   **senza rientro** (`^- `), i testi fra apici inversi della **testa** della voce sono percorsi anche
   senza `/`, se non contengono spazi né `*<>{}…()[]`. La testa è il primo testo e quelli che lo seguono
   separati **solo** da `, `, ` e ` oppure ` o `: in ``- `a/b` e `README.md` — …`` e in
   ``- `docker-compose.yml`, `Dockerfile`, `.env.example` — …`` contano tutti (è la forma di
   `PBI-530`, riga 24, e della `PBI-001` di `ada_unical`). Gli altri testi della riga restano percorsi
   solo con una `/`, come oggi: `` `weasyprint` `` o `` `html(…)` `` dopo il trattino lungo non diventano
   file. Le voci annidate (con rientro) restano come oggi, solo con la `/`: le sotto-voci nominano
   funzioni e costanti (``  - `RE_A_VISTA` e …`` in `PBI-527`), che darebbero avvisi falsi.
   Alternativa scartata: ogni testo con un punto (`requirements.txt`) è un file. Prende anche `70.0`,
   `formule.rendi` e `asdlc.toml` citati a metà riga, e la pre-verifica darebbe avvisi falsi.
3. **Le cartelle restano prefissi** (`tools/tests/`), come oggi e come dice `ADR-0033`.
4. **Una PR che tocca un file del «Fuori scope» attende una persona** con il motivo che c'è già
   («il file … è fuori dallo Scope»): non serve un motivo nuovo, e il motivo è vero.

## Dipendenze

- Bloccato da: nessuno. Va dopo la barriera della `v1.0.0`, in testa alla coda della `v1.1.0`.
- Blocca: nessuno. Dopo il suo merge il pin negli altri quattro progetti porta la guardia anche lì.
- **La PR di questo PBI la mergia una persona:** il tick gira con la `v1.0.0`, che non vede
  `README.md` nello Scope, e scriverà «il file README.md è fuori dallo Scope». È il difetto che il PBI
  corregge, non un fermo nuovo.

## Contesto

- `tools/asdlc/runner.py` — `percorsi_dello_scope()`, `blocco_dello_scope()`, `avvisi_della_base()`.
- `tools/asdlc/coda.py` — `condizione_mancante()`, la condizione dello Scope.
- `decisions/ADR-0033-il-merge-di-un-giro-e-del-tick.md` — decisione 1, la condizione dello Scope.
- `ada_dispense`, `backlog/PBI-009-dal-sorgente-al-pdf.md` e la `#44`: il caso reale.

## Verifica

- [x] **Un file in radice nello Scope conta, e la PR che lo tocca si mergia.** **Una sola asserzione**
      sulla lista resa da `percorsi_dello_scope()` per uno Scope con le voci ``- `requirements.txt` —
      fissato.``, ``- `tools/a.py` e `README.md` — x.``, ``- `x.yml`, `Dockerfile` — y.``,
      ``- `tools/asdlc/runner.py` — usa `weasyprint` e `html(x)`.`` e ``  - `COSTANTE` e `tools/b.py` ``
      (annidata): la lista è esattamente `requirements.txt`, `tools/a.py`, `README.md`, `x.yml`,
      `Dockerfile`, `tools/asdlc/runner.py`, `tools/b.py`. Le esclusioni (`weasyprint`, `html(x)`,
      `COSTANTE`) sono già vere sulla base: stanno nella stessa asserzione come guardia, non in un test
      a sé, che nascerebbe verde.
      Nel mondo del merge di `test_asdlc_rilascio.py`, un PBI con `- \`requirements.txt\`` nello Scope e
      una PR che tocca `requirements.txt` e il file del PBI si mergia (`merge: PBI-7 #1`). Rosso sulla
      base: `requirements.txt` non c'è fra i percorsi, e la PR attende «fuori dallo Scope».
- [x] **Il «Fuori scope» non dà percorsi: la PR che lo tocca attende, e la pre-verifica non avvisa.**
      Con uno Scope che finisce con ``- **Fuori scope:** `tools/asdlc/coda.py` resta com'è;`` e una
      voce annidata ``  - `docs/vecchio.md`: non cambia.``, `percorsi_dello_scope()` non rende né
      `tools/asdlc/coda.py` né `docs/vecchio.md`. Una PR che tocca `tools/asdlc/coda.py` (nominato solo
      nel «Fuori scope») attende con «fuori dallo Scope»; `avvisi_della_base()` non avvisa per
      `docs/vecchio.md`, che alla base non c'è. Rosso sulla base: i due percorsi ci sono, la PR si
      mergia e l'avviso c'è.

**Non regressione:**
- I test di `test_asdlc_preverifica.py` e di `test_asdlc_rilascio.py` restano verdi: il percorso con una
  `/` a metà riga conta come oggi, la cartella è un prefisso, il testo con uno spazio o un `…` no.
- `forma_del_pbi()` e `controllo_r7()` danno gli stessi risultati: i loro test restano verdi.

## Protocollo di rifinitura

- Il README dice in una frase che lo Scope conta fino al «Fuori scope» e che i file in radice valgono;
  una frase, non una sezione.
- Lettura del 30/10 (Lettore separato, sola lettura): zero fermi, quattro rilievi minori recepiti — i
  file in radice dopo il primo (decisione 2, la testa della voce), le voci annidate (decisione 2, senza
  rientro), le esclusioni già vere come guardia nell'asserzione del criterio 1, la PR di questo PBI a
  una persona (*Dipendenze*).
- Ogni altra ambiguità si scrive qui e si chiama `fermati`.
