# PBI-543: la riga di stato dice la barriera una volta, e la panoramica segnala i fatti che non tornano

**Stato:** proposto il 06/11 (Francesco, alla revisione dello sprint 1). Contiene i tre difetti visti in
`asdlc-panoramica` sui cinque progetti. **Non letto**, **non in coda**: lo sprint 3, insieme a
`PBI-541` e al Correttore, si accoda dopo la revisione dello sprint 2 (`ADR-0034`).

## Direttiva

La revisione dello sprint 1 (06/11) ha lanciato `asdlc-panoramica` sui cinque progetti, e sono venute
fuori tre righe sbagliate.

1. **La barriera due volte.** In `ada_asdlc` e `ada_nlt` la riga di stato è
   `ada_asdlc · barriera: revisione dello sprint 1 … · revisione dello sprint 1 … · - · PR - · …`.
   `stato.riga()` mette in fila la decisione (`barriera: <testo>`) e la voce, e per una barriera
   `voce_di()` restituisce lo stesso `<testo>`. Su una barriera lunga la riga raddoppia. Il difetto
   è di `asdlc-stato` (`PBI-534`), e la panoramica lo eredita dalla sua prima riga.
2. **PBI-526 tra i fatti, con criteri 0/4.** La #97 ha `PBI-526:` nel titolo e tocca `decisions/`:
   per `coda.pbi_mergiati()` è una PR che fa il PBI. È il limite che `CODA.md` dichiara («una PR che
   nomina un PBI nel titolo e scrive un ADR lo spegne lo stesso»). La panoramica lo mostra come
   fatto, senza nessun segno.
3. **PBI-530 fuori coda, con criteri 4/4.** La #113 ha toccato `tools/asdlc/coda.py`, ma il suo titolo
   è `PBI-530, ripresa del giro 2 …` (virgola, non due punti) e il ramo è `backlog/pbi-530-giro2`, non
   `pbi/`. `pbi_nominato()` non ci trova niente, e il PBI non risulta fatto.

Il 2 e il 3 nascono in `pbi_mergiati()`, cioè dove il tick decide cosa è in `main`. Francesco ha
scelto (06/11) di **non toccare il tick**: è la panoramica a segnalare quando la PR e i criteri non
dicono la stessa cosa (`ADR-0008`, osserva e segnala).

**Scope**

- `tools/asdlc/stato.py`: `riga()`. Per una barriera, al posto della voce va `‖`. Il JSON
  (`--json`, la chiave `voce`) non cambia.
- `tools/asdlc/panoramica.py`: `riga_del_pbi()` e `sezioni()`, l'avviso sulle righe di **Fatti** e di
  **Fuori coda**.
- `README.md`: una riga sull'avviso, accanto ad `asdlc-panoramica`, nello stesso commit del codice.
- `tools/tests/test_asdlc_stato.py`, `tools/tests/test_asdlc_panoramica.py`: i test dei criteri.
- `backlog/PBI-543-la-panoramica-segnala-cio-che-non-torna.md`: questo file, per la spunta.
- **Fuori scope:** `tools/asdlc/coda.py`. `pbi_mergiati()`, `pbi_nominato()` e `RE_TITOLO_PR` non
  cambiano, e il tick decide come prima. Fuori anche la riga vuota tra la tabella degli sprint e
  `## In corso` (in GFM il titolo chiude la tabella e si legge bene), e le sezioni **In corso** e
  **In coda**, dove i criteri non spuntati sono la norma.

## ✅ Deciso

1. **La voce di una barriera, nella riga, è `‖`.** È il segno con cui `CODA.md` scrive una barriera.
   Il testo resta una volta sola, nella decisione. Il JSON resta com'è, perché chi lo legge vuole il
   testo della voce.
2. **Sui fatti, l'avviso è `⚠ criteri non spuntati`.** Si mette quando il PBI ha almeno un criterio
   e non sono tutti spuntati. Un PBI senza criteri (`0/0`) non ha avviso: non c'è niente da
   confrontare.
3. **Sui fuori coda, l'avviso è `⚠ criteri spuntati, nessuna PR lo fa`.** Si mette quando il PBI
   ha almeno un criterio e sono tutti spuntati.
4. **L'avviso sta prima del `❓`.** La domanda resta l'ultima cosa della riga, come vuole la decisione 5
   di `PBI-538`.
5. **Il PBI resta nella sezione in cui lo mette il tick.** L'avviso dice che qualcosa non torna, ma
   non sposta il PBI. Le sezioni restano la vista del tick, con un dato in più.

## Dipendenze

- Bloccato da: nessuno.
- Blocca: niente.

## Contesto

- `tools/asdlc/stato.py`: `riga()`, `voce_di()`.
- `tools/asdlc/panoramica.py`: `riga_del_pbi()`, `criteri_di()`, `sezioni()`.
- `tools/asdlc/coda.py`: `pbi_mergiati()`, `pbi_nominato()`, `tocca_codice()`. Si leggono e non si
  cambiano.
- `PBI-534` (asdlc-stato), `PBI-538` (asdlc-panoramica), decisioni 3 e 5.
- La #97 (`PBI-526: D1 e D2 chiuse…`, ramo `backlog/pbi-526-decisioni`) e la #113 (`PBI-530, ripresa
  del giro 2…`, ramo `backlog/pbi-530-giro2`).

## Verifica

- [ ] **Con la coda ferma su una barriera, il testo compare una volta.** Su un progetto con
      `- ‖ il merge della v1.0.0` in testa alla coda, la riga di `asdlc-stato` contiene
      `barriera: il merge della v1.0.0 · ‖ ·` e `il merge della v1.0.0` compare una volta sola.
      Con `--json`, `voce` è ancora `il merge della v1.0.0`. Rosso su `main`: oggi il testo compare
      due volte.
- [ ] **Un fatto coi criteri non spuntati ha l'avviso.** Con un `gh` finto che dà una PR mergiata che
      nomina `PBI-1` e tocca `tools/`, e `PBI-1` con un criterio su due spuntato, la riga di `PBI-1`
      in `## Fatti` finisce con `criteri 1/2 · ⚠ criteri non spuntati`. Rosso su `main`.
- [ ] **Un fuori coda coi criteri tutti spuntati ha l'avviso.** Con `PBI-2` fuori da `CODA.md`, nessuna
      PR che lo nomina e due criteri su due spuntati, la riga di `PBI-2` in `## Fuori coda` finisce
      con `criteri 2/2 · ⚠ criteri spuntati, nessuna PR lo fa`. Rosso su `main`.
- [ ] **Niente avviso dove PR e criteri dicono la stessa cosa** (guardia: nasce verde). Un fatto con
      `2/2`, un fatto con `0/0` e un fuori coda con `0/3` non hanno `⚠`. Su un fatto con `1/2` e una
      sezione di domande, la riga finisce con `⚠ criteri non spuntati · ❓`.

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde, compresi i test di `PBI-534` sulla
riga e di `PBI-538` sulle quattro sezioni.

## Protocollo di rifinitura

Si può scegliere senza chiedere: il nome della funzione che decide l'avviso, e se `riga_del_pbi()`
riceve la sezione o l'avviso già fatto.
Si chiama `fermati`: se il RED del primo criterio mostra che la riga di `asdlc-stato` ripete il testo
anche dove la coda non è ferma su una barriera. In quel caso la causa non è `voce_di()`, e il rapporto
deve dire qual è.
