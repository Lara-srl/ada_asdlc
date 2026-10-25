# PBI-525: il Critic non blocca su un rimedio che il Builder non può eseguire

**Stato:** bozza, con le domande aperte (❓) qui sotto: non si accoda finché Francesco non le chiude.

## Direttiva

Osservato su `ada_nlt`, `PBI-5`, giro `20261025-085406` (asdlc `v0.7.0`, sha `eabbf15`): il giro
chiude `non convergente / revisioni-esaurite` dopo 5 passaggi del Critic, e il tick tiene la coda in
`attende` (`ramo su origin, nessuna PR`) da oltre 10 ore, scrivendo la stessa riga ogni 10 minuti.
Il codice in HEAD era giusto: dei 5 rilievi del Critic, 3 passaggi su 5 sono **meccanici**, non di merito.

1. **Il Critic ordina un rimedio che il Builder non può eseguire.** `tools/asdlc/prompt/critic.md:38`
   chiede di chiudere l'igiene dei commit «con un rebase»; il prompt del Builder vuole un commit per
   rimedio e non riscrive la storia di un ramo pubblicato (`ADR-0022`). Revisioni 0 e 1 del giro:
   rilievi di sola storia (`f6773bf` GREEN con suite rossa; deroga allo Scope dichiarata un commit
   dopo, `ADR-0015`) il cui «Rimedio» è un rebase, e la stessa chiusa di `critic-1` dice «i due
   rilievi si chiudono con un rebase, senza cambiare HEAD». Il Builder si è fermato con una `domanda`
   (un commit nuovo non rende verde un commit vecchio); il Solver ha risposto «strada (b), niente
   rebase, si dichiara nelle note per chi mergia, **non sono rilievi bloccanti** (`ADR-0008`)». Ma il
   verdetto del Critic era già `non pronto` e ha consumato due revisioni su quattro.
2. **Il Critic riporta un'istanza per passaggio, non la classe.** `critic-3`: un preventivo senza numero
   d'offerta fa `POST /preventivi` → 500. `critic-4`: una durata ≤ 0 fa `PUT …/comparazione` → 500.
   Stessa classe («un dato utente non valido torna 4xx», `Deciso 3` del PBI); il Builder chiude il
   caso nominato e il Critic scopre il prossimo al giro dopo, a tetto raggiunto.
3. **Il fermo è muto.** Un giro `non convergente` non avvisa nessuno: la coda attende per ore.
   Obiettivo di `PBI-519` (20/10): zero fermi meccanici, e se si ferma, si ferma con una domanda vera
   e lo si viene a sapere.

**Scope**
- `tools/asdlc/prompt/critic.md` — l'igiene dei commit su un ramo già pubblicato: il Critic la scrive
  tra le note per chi mergia e non la usa come motivo di `non pronto`; il rimedio non è un rebase.
  Per un rilievo di correttezza, il Critic esamina l'intera classe e riporta tutti i casi che trova.
- `tools/asdlc/runner.py` — il verdetto: un rilievo di sola storia non basta per `non pronto`.
- `tools/asdlc/coda.py` — l'avviso quando la coda resta in `attende` per un `non convergente`.
- `tools/tests/` — i test dei criteri.
- `backlog/PBI-525-…md` — questo file, per la spunta.
- **Fuori scope:** il tetto `[soglie].revisioni` (alzarlo nasconde il difetto).

## ❓ Domande aperte

1. Un rilievo di storia è sempre non bloccante, o solo dopo la prima pubblicazione del ramo
   (prima si può ancora riscrivere)? Il codice oggi non distingue.
2. L'avviso del fermo: file nella home, `PushNotification`, o una riga di `gh`? Scelta tua.

## Verifica
- [ ] **Un giro il cui solo rilievo è di storia chiude `pronto`**, con la nota nel rapporto. Rosso su
      `main`: oggi il Critic emette `non pronto`.
- [ ] **Il prompt del Critic non nomina più il rebase** come rimedio di un ramo pubblicato.
- [ ] **Un tick che trova un `non convergente` lo segnala con l'avviso scelto**, una volta e non a ogni
      passaggio.

**Non regressione:**
- Un rilievo di correttezza o di test-first resta `non pronto`.
- La suite dei test resta verde.
