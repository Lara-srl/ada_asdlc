# PBI-525: i fermi meccanici del PBI-5 di ada_nlt, cinque difetti in un solo caso

**Stato:** bozza, con le domande aperte (❓) qui sotto: non si accoda finché Francesco non le chiude.

## Direttiva

Osservato su `ada_nlt`, `PBI-5`, due giri (asdlc `v0.7.0`, sha `eabbf15`): giro 1
(`20261025-085406`) e giro 2 (`20261025-212406`). Il giro 1 chiude `non convergente / revisioni-esaurite` dopo 5 passaggi del Critic, e il tick tiene la coda in
`attende` (`ramo su origin, nessuna PR`) da oltre 10 ore, scrivendo la stessa riga ogni 10 minuti.
Il codice in HEAD era giusto. In più il giro 2, ripartito dopo due fermi di pre-verifica che erano
errori veri del PBI (non meccanici, già corretti), si è fermato su un quarto difetto, sotto. Dei 5 rilievi del Critic, 3 passaggi su 5 sono **meccanici**, non di merito.

1. **Il Critic ordina un rimedio che il Builder non può eseguire.** `tools/asdlc/prompt/critic.md:38`
   chiede di chiudere l'igiene dei commit «con un rebase»; il prompt del Builder vuole un commit per
   rimedio e non riscrive la storia di un ramo pubblicato (`ADR-0022`). Revisioni 0 e 1 del giro:
   rilievi di sola storia (`f6773bf` GREEN con suite rossa; deroga allo Scope dichiarata un commit
   dopo, `ADR-0015`) il cui «Rimedio» è un rebase, e la stessa chiusa di `critic-1` dice «i due
   rilievi si chiudono con un rebase, senza cambiare HEAD». Il Builder si è fermato con una `domanda`
   (un commit nuovo non rende verde un commit vecchio); il Solver ha risposto «strada (b), niente
   rebase, si dichiara nelle note per chi mergia, **non sono rilievi bloccanti** (`ADR-0008`)». Ma il
   verdetto del Critic era già `non pronto` e ha consumato due revisioni su quattro.
2. **Il Critic riporta un'istanza per passaggio, non la classe.** Anche nel giro 2: `critic-0` trova
   `economia` come padre e `Infinity` nella PUT, `critic-1` un importo finito ma enorme
   (`decimal.InvalidOperation`). Giro 1: `critic-3`: un preventivo senza numero
   d'offerta fa `POST /preventivi` → 500. `critic-4`: una durata ≤ 0 fa `PUT …/comparazione` → 500.
   Stessa classe («un dato utente non valido torna 4xx», `Deciso 3` del PBI); il Builder chiude il
   caso nominato e il Critic scopre il prossimo al giro dopo, a tetto raggiunto.
3. **`--chiedi-impl` apre `IMPL` anche con un test non committato, e da `IMPL` non si torna.**
   Giro 2, revisione 1 (`20261025-212406`, run chiuso `fermato / domanda-del-builder`): il Builder
   ha scritto i 5 test RED, li ha visti rossi, ha lanciato `--chiedi-impl` **prima** di committarli.
   Il comando ha letto i test dall'albero e ha aperto la fase `IMPL`; il `pre-commit` ha poi rifiutato
   il commit del test («è un test e il giro è in IMPL»). Il Builder non poteva né tornare a
   `TEST_ONLY` né aggirare il lucchetto, e ha chiamato `fermati`. Il prompt (`builder.md` righe
   16-24 e 73) dice l'ordine giusto: è uno scivolone del modello che il runner trasforma in un
   fermo. È la terza volta (`PBI-3` giri 3 e 4, `PBI-5` giro 2). `PBI-524` decisione 6 sistema solo
   il **messaggio** del rifiuto quando i test sono già committati; qui il comando **accetta** un
   albero sporco di test e apre la fase sbagliata, ed è un altro caso.
4. **Il worktree del runner resta sporco dopo un giro fermato, e il giro dopo non parte.**
   Giro 3 di `PBI-5` (25/10, 22:14): dopo `asdlc-chiudi-giro PBI-5` il worktree `../ada_nlt-run` aveva
   ancora il test non committato del giro 2 in stage (`M  tests/test_servizio.py`, 21 righe). Il
   tick ha provato il pre-flight e si è fermato su `git switch --detach origin/main` (uscita 1:
   «Le tue modifiche locali […] sarebbero sovrascritte»), scrivendo `non lanciato`. Il comando
   (`tools/asdlc/chiudi_giro.py`) fa i sei passi su `origin` e sul checkout del tick, ma non guarda il
   worktree del runner. Un'altra persona è dovuta intervenire a mano (`git stash`); il lancio è
   ripartito al tick dopo, ~10 minuti persi.
5. **Il fermo è muto.** Un giro `non convergente` non avvisa nessuno: la coda attende per ore.
   Obiettivo di `PBI-519` (20/10): zero fermi meccanici, e se si ferma, si ferma con una domanda vera
   e lo si viene a sapere.

**Scope**
- `tools/asdlc/prompt/critic.md` — l'igiene dei commit su un ramo già pubblicato: il Critic la scrive
  tra le note per chi mergia e non la usa come motivo di `non pronto`; il rimedio non è un rebase.
  Per un rilievo di correttezza, il Critic esamina l'intera classe e riporta tutti i casi che trova.
- `tools/asdlc/runner.py` — il verdetto: un rilievo di sola storia non basta per `non pronto`; e
  `--chiedi-impl`, che con test non committati nell'albero **non apre `IMPL`** e risponde «committa
  prima il RED, poi richiedi la fase» (la fase resta `TEST_ONLY`, il Builder può proseguire).
- `tools/asdlc/chiudi_giro.py` — un settimo passo: se il worktree del runner ha modifiche non
  committate, le mette in `git stash` con un messaggio che nomina il PBI e il giro (mai
  `reset --hard`: il lavoro si recupera), e lo dice nel resoconto.
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
- [ ] **`--chiedi-impl` con un test non committato non apre `IMPL`.** Fase `TEST_ONLY`, un file di
      test modificato e non committato: il comando esce con il messaggio «committa prima il RED» e la
      fase resta `TEST_ONLY`. Rosso su `main`: oggi apre `IMPL`.
- [ ] **Il Critic che trova un 500 su un dato utente elenca l'intera classe che ha verificato**
      (campi e rotte esaminati), non il solo caso: nel giro 2 ha trovato `economia` come padre e
      `Infinity` alla revisione 0, e un importo finito ma enorme alla revisione 1.
- [ ] **Il prompt del Critic non nomina più il rebase** come rimedio di un ramo pubblicato.
- [ ] **`asdlc-chiudi-giro` lascia il worktree del runner pulito.** Con un file in stage nel
      worktree, dopo il comando `git status --porcelain` è vuoto, `git stash list` nomina il PBI e
      il giro, e il pre-flight del tick successivo passa. Rosso su `main`: oggi il file resta.
- [ ] **Un tick che trova un `non convergente` lo segnala con l'avviso scelto**, una volta e non a ogni
      passaggio.

**Non regressione:**
- Un rilievo di correttezza o di test-first resta `non pronto`.
- La suite dei test resta verde.
