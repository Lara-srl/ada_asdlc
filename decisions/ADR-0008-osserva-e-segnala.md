# ADR-0008: aDa osserva e segnala, non blocca

**Stato:** Accettata · **Data:** 2026-07-30

## Contesto

Un software gestionale che impone la sequenza «giusta» viene aggirato: si scrive un valore
falso pur di passare, oppure si torna alla carta. Qui l'utente è la titolare, e i suoi
operai lavorano con le mani sporche su un PC condiviso: ogni ostacolo si paga in adozione.

## Decisione

Nessun hard-block nel flusso operativo. Le violazioni si esprimono come **avvisi
strutturati** nella risposta (`avvisi`), e l'operazione va comunque a buon fine.
Una mossa di stato fuori sequenza passa e torna marcata `forzata`.

## Conseguenze

**Positive**
- Il dato entra sempre: un modulo che pretende una data fa scrivere una data falsa, e una
  data falsa ha l'aria di essere vera.
- Gli avvisi diventano un segnale misurabile (quante `forzata`, quanti ricambi senza costo).

**Negative**
- I dati incompleti esistono e vanno gestiti a valle: il margine di una pratica con ricambi
  senza costo si **dichiara incompleto** invece di essere sbagliato in silenzio.
- Serve disciplina per non farne un alibi: «non blocca» non vuol dire «facile da sbagliare»
  (vedi ADR-0004).

## Alternative considerate

**Campi obbligatori e transizioni rigide.** Danno dati puliti in teoria; in pratica danno
dati inventati, perché l'utente ha comunque un lavoro da consegnare.

## Confine

L'eccezione sono le regole che proteggono l'**integrità**, non il processo: cancellare un
utente con una storia risponde 409 **con la via d'uscita** (disattivalo). Non è un blocco di
flusso: è un'operazione che distruggerebbe dati altrui.
