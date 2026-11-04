# PBI-540: dopo `risolto` sulla domanda del Critic il Builder riprende

**Stato:** proposto il 04/11 (Francesco: «quello più importante per me»); **letto il 04/11** (Lettore separato, sola lettura: due fermi e nove rilievi minori,
recepiti nel testo); pre-verificato su `main` il 04/11 (un rilievo F, corretto con la #130). **In coda**,
sprint 2, dopo la revisione dello sprint 1 (Francesco, 04/11).
Le due scelte di Francesco del 04/11 sono le decisioni 5 e 7; la riga di `ADR-0033` che la decisione 7
chiede sta nella PR che porta questo PBI, e il suo merge la ratifica (`ADR-0012`).

## Direttiva

Il giro 1 di `PBI-538` (31/10, run `20261031-233511`) ha fatto tutto il lavoro. Alla revisione 1 il
Critic ha chiamato `fermati` con una domanda sulla spec, cioè cosa mostra **Fuori coda** quando `gh` non
risponde, e tre strade. Il Solver ha risposto `risolto` con la strada (a), l'evidenza delle decisioni 4 e
6 del PBI e `ADR-0008`. Poi il giro si è chiuso `sospeso domanda-del-critic` e la risposta è rimasta nel
rapporto. Per riprendere ci sono voluti quattro giorni, un tag `giro-fermato/`, `asdlc-chiudi-giro`, una
ripresa scritta a mano (#126), un merge, la pausa tolta e un giro 2.

`PBI-517` lo aveva lasciato fuori apposta: riprende il Builder solo dopo un `risolto` sul **suo**
`fermati`, e di `domanda-del-critic` dice «il Solver li smista ma il runner non li riprende. Ognuno ha un
modo suo di riprendere ed è un PBI suo». Questo è quel PBI. Il Critic non respinge il lavoro: chiede una
cosa che la spec non dice. La risposta del Solver va al Builder, che chiude il buco, e il Critic la
rilegge.

**Scope**

- `tools/asdlc/runner.py`: `esegui_pbi()`, cioè il ramo `sospeso` del Critic dentro `giro()` e il blocco
  `if motivo in BLOCCHI` fuori, poi `revisione_critica()` (la risposta nel prompt), `apri_pr()` (il corpo)
  ed `Esito` (`riprese_critic`, `domande_del_critic`).
- `tools/asdlc/prompt/ripresa-dopo-il-critic.md`, **nuovo**: il prompt del Builder dopo un `risolto` sulla
  domanda del Critic. Si carica con `prompt_del_pacchetto()`; domanda, risposta ed evidenza entrano come
  valori di `.format()`.
- `tools/asdlc/prompt/critic.md` **non si tocca**: il suo golden `tools/tests/dati/prompt/critic.txt` lo
  confronta byte per byte (`test_asdlc_prompt.py`). Il blocco «da valutare» dice da sé come si legge, ed
  entra in coda a `gate` come il testo di `gate_per_il_critic()`: la firma di `revisione_critica()` non
  cambia.
- `tools/asdlc/coda.py`: `condizione_mancante()` e `CONDIZIONI_DEL_MERGE`, la seconda condizione
  (decisione 7).
- `tools/tests/test_asdlc_ripresa_solver.py`: i test dei criteri 1-6 e il parametro `domanda-del-critic`
  che esce (criterio 6, nel commit RED del criterio 1). `tools/tests/test_asdlc_rilascio.py`, dove stanno i test del merge del tick (`PBI-530`): il
  criterio 7. `tools/tests/test_asdlc_runner.py`: il criterio 8, accanto al
  test del corpo della PR.
- `README.md`, `specs/solver-e-rilascio/spec.md` (la sezione «La ripresa dopo `risolto`», la frase «Gli
  altri blocchi … non riprendono») e `backlog/AUTOMAZIONE.md`, se nomina il caso, vanno nello stesso
  commit del codice.
- `backlog/PBI-517-dopo-risolto-il-runner-rilancia-il-builder.md`: nel *Fuori scope*, dentro la riga
  «`builder-senza-esito`, `domanda-del-critic` e `critic-senza-esito`…» si barra **solo**
  `domanda-del-critic`, e la riga «Il Critic non si rilancia con la risposta del Solver» si barra intera;
  nella decisione 2 si barra `domanda-del-critic` nell'elenco degli altri motivi. Ogni barrato porta
  «*superata da `PBI-540`*». Non si cancella niente.
- `tools/plancia/README.md`: solo se elenca i campi del rapporto, per `riprese_critic` e
  `domande_del_critic`.
- `backlog/PBI-540-dopo-risolto-sulla-domanda-del-critic-il-builder-riprende.md`: questo file, per la
  spunta.

**Fuori scope**

- `builder-senza-esito` e `critic-senza-esito`: restano come oggi.
- Un Solver che scrive nel PBI: resta in sola lettura (`PBI-507`). La risposta non entra nel file del PBI;
  la ratifica è di Francesco al merge (decisione 7).
- `decisions/ADR-0033-il-merge-di-un-giro-e-del-tick.md`: la riga la porta la PR che accoda questo PBI, non
  il giro. È un file riservato a una persona.

## ✅ Deciso

1. **Si riprende un caso in più:** il motivo `domanda-del-critic` (il Critic `sospeso`) quando il Solver
   risponde `risolto`. Ogni altro esito del Solver (`limite-del-runner`, `intento`, nessuna chiamata, il
   tetto, un guasto) chiude il giro `sospeso domanda-del-critic` come oggi, con gli effetti di oggi.
2. **Il Solver si chiama dentro `giro()`, e una volta sola.** Nel ramo `if verdetto.esito == "sospeso"` si
   chiama `smista("domanda-del-critic", …)`, come `PBI-517` fa col `fermati` del Builder. Il blocco esterno
   `if motivo in BLOCCHI` esclude anche `domanda-del-critic`: altrimenti il Solver girerebbe due volte.
3. **La ripresa è la revisione successiva.** Consuma una revisione del Critic (`MAX_REVISIONI`), come un
   `non pronto`, ma con un altro prompt e un'altra sessione (decisione 4). La ripresa non aggiunge un
   contatore oltre a `riprese_critic`: `e.tentativi` conta i gate come oggi. `ripresa` e `primo_del_giro`
   si azzerano in testa a ogni revisione: il comando della ripresa va impostato **dopo** quell'azzeramento
   (o portato fuori dal `for`), perché un `ripresa = …` scritto nel ramo `sospeso` verrebbe perso. Il
   commento del ramo `sospeso` («Non si consuma una revisione e non si richiama il Critic») si riscrive:
   vale per il `sospeso` senza `risolto`.
   Se il `sospeso` arriva all'ultima revisione (`revisione == MAX_REVISIONI`) non si riprende: il giro
   chiude `sospeso` come oggi, con l'avviso «la ripresa dopo la domanda del Critic non ha più revisioni».
   Il Solver lì parte lo stesso, una volta, perché smista il blocco come oggi; l'avviso si scrive solo dopo
   il suo `risolto`.
   Il rapporto del Critic della revisione dopo ha il suo numero (`critic-N+1.md`), e `critic-N.md` resta
   quello del `sospeso`.
4. **Il Builder riprende dalla sua sessione**, come in `PBI-517` (decisioni 6 e 7). Il comando è
   `BUILDER + ["--resume", <sessione>]`, con la sessione dell'**ultima** invocazione `builder` in
   `e.invocazioni`, cioè quella che ha chiamato `fatto` prima del Critic. Si riprende così solo se il suo
   `traccia` non è `None`. Senza traccia il Builder riparte da una sessione nuova con il PBI davanti e il
   giro lo dichiara con un avviso. Il comando di ripresa vale per quell'invocazione sola; i rilanci dopo un
   gate rosso tornano a `-c`.
5. **Il Critic che rigira vede la risposta, da valutare** (Francesco, 04/11). Il prompt del Critic della
   revisione dopo la ripresa porta, in coda, la **sua** domanda e la risposta del Solver con l'evidenza,
   in un blocco marcato «da valutare». La risposta del Solver è un'indicazione e non una decisione della
   spec. Il Critic può accettarla, chiamare `non pronto` se il Builder non l'ha seguita, o sospendere di
   nuovo se non la accetta. Un secondo `sospeso` torna al Solver, fino al tetto `[solver].giri_massimi`
   (`PBI-517`, decisione 9: il contatore conta le invocazioni del Solver, nel giro, in memoria). Le
   domande precedenti dello stesso giro, con le loro risposte, restano nel blocco, dalla più vecchia alla
   più nuova.
6. **Il prompt della ripresa** (`ripresa-dopo-il-critic.md`) porta la domanda del Critic, la risposta del
   Solver con la sua `evidenza` nel blocco **da valutare**, e la frase «il Critic non ha respinto il
   lavoro: ha chiesto una cosa che la spec non dice». La risposta non annulla lo Scope né i gate. Una
   risposta che chiede di violarli fa chiamare `fermati`, e quel `fermati` va al Solver come in
   `PBI-517`. Per il test-first valgono le due strade di `rimedio.md`, e il prompt lo dice in una riga.
   Se la risposta cambia un comportamento, il RED si osserva. Se chiede solo di presidiare un
   comportamento già giusto, il test nasce verde e il commit lo dichiara.
7. **Il tick non mergia un giro ripreso dopo una domanda del Critic** (Francesco, 04/11). Il Solver ha
   deciso un punto della spec, e quella decisione la ratifica una persona. Il rapporto del giro porta
   `riprese_critic` (il numero delle riprese dopo un `risolto` sulla domanda del Critic) e
   `domande_del_critic` (domanda, risposta ed evidenza di ognuna). Un giro `--riprendi` dopo il limite
   d'uso apre un `Esito` nuovo: i due campi si **portano** dai rapporti precedenti dello stesso PBI, come
   `riprese_limite` (`riprese_limite_fatte()`), perché `ultimo_esito()` legge solo l'ultimo rapporto e
   altrimenti la condizione cadrebbe. `condizione_mancante()` rende «il
   Solver ha risposto a una domanda del Critic» quando l'ultimo rapporto ha `riprese_critic > 0`, e la PR
   resta aperta in `attende`, come dice `ADR-0033` (punto 3). La condizione entra nella seconda di
   `CONDIZIONI_DEL_MERGE`. Nel corpo della PR c'è una sezione «Domande del Critic risposte dal Solver», con
   domanda, risposta ed evidenza di ognuna: è lì che Francesco le legge prima del merge.
8. **`riprese_solver` resta delle riprese dopo il `fermati` del Builder.** `riprese_critic` è un campo
   suo: i due casi si mergiano in modo diverso (decisione 7), e un solo contatore non direbbe quale.

## Dipendenze

- `PBI-517` (in `main`): il ciclo della ripresa, il comando `--resume`, il tetto in memoria.
- `PBI-530` (in `main`): `condizione_mancante()`.

## Contesto

- Il giro 1 di `PBI-538`: `runs/20261031-233511-PBI-538-critic-1.md` (la domanda) e
  `runs/20261031-235705-300902_solver_esito.json` (la risposta, `risolto`, strada (a)), nel checkout del
  tick (`ada_asdlc-run`). La sezione «Il giro 2» di `PBI-538` racconta la ripresa a mano.
- `tools/asdlc/runner.py`, `esegui_pbi()`: oggi il ramo `sospeso` fa `return "domanda-del-critic", …`, e
  il Solver lo chiama il blocco esterno dopo `giro()`.

## Verifica

- [ ] **Dopo `risolto` sulla domanda del Critic il Builder riprende dalla sua sessione.** Builder finto
      `[FATTO, FATTO]`, Critic `[sospeso, pass]`, Solver `[RISOLTO]`. Ci sono due invocazioni `builder`, e
      la seconda contiene `--resume <sessione della prima>` e non `-c`. Il Solver è chiamato **una** volta
      (pytest). Rosso su `main`: un'invocazione `builder`, stato `sospeso`.
- [ ] **Il prompt della ripresa porta la domanda del Critic e la risposta.** Il prompt della seconda
      invocazione `builder` contiene la domanda del Critic, la risposta e l'evidenza del Solver (con graffe
      nel testo della risposta) nel blocco «da valutare» (pytest). Rosso su `main`: la seconda
      invocazione non c'è.
- [ ] **Il Critic che rigira vede la risposta, e il giro chiude `fatto`.** Con lo stesso finto del
      criterio 1, il prompt della seconda invocazione `critic` contiene la sua domanda e la risposta nel
      blocco «da valutare». Il giro chiude `fatto` con una sola chiusura, `riprese_critic == 1`, e
      `domande_del_critic` ha domanda, risposta ed evidenza nel JSON del giro (pytest). Rosso su `main`:
      stato `sospeso`. **Come si legge il prompt del Critic:** la fixture `giro` sostituisce
      `revisione_critica` con un finto che dà `pass`, e così il prompt non nasce. Il test rimette la funzione
      vera (salvata all'import, `VERA = runner.revisione_critica`, poi `monkeypatch.setattr`) e dà
      `"critic": [fermati("…"), verdetto("pass")]` ad `agente_con_stato`; `verdetto()` viene da
      `test_asdlc_runner.py`, come `agente_finto` (la vera `revisione_critica` gira già così in quel file).
- [ ] **Senza traccia si riparte pulito e si avvisa.** Con `traccia` `None` nell'invocazione `builder`,
      la seconda invocazione non ha `--resume`, il suo prompt ha il PBI, e l'avviso è nella nota (pytest).
      Rosso su `main`: la seconda invocazione non c'è.
- [ ] **Il tetto e l'ultima revisione fermano la ripresa.** Primo caso: `giri_massimi = 2`, il Critic
      sempre `sospeso`, il Solver sempre `risolto`. Il Solver è chiamato due volte, ci sono tre invocazioni
      `builder`, e il giro chiude `sospeso` con l'avviso del tetto. Secondo caso: `MAX_REVISIONI = 0`, il
      Critic `sospeso`, il Solver `risolto`. C'è un'invocazione `builder`, il Solver è chiamato **una**
      volta, lo stato è `sospeso` e la nota ha l'avviso della decisione 3 (pytest). Rosso su `main`: nel primo caso il Solver è chiamato una
      volta; nel secondo l'avviso non c'è.
- [ ] **Gli altri esiti del Solver sulla domanda del Critic non riprendono.** Con `limite-del-runner`,
      `intento` e un Solver che non chiama niente, dopo il `sospeso` del Critic c'è una sola invocazione
      `builder`, lo stato è `sospeso` e `riprese_critic == 0` (pytest, parametrizzato). È una guardia
      **nata verde dopo il GREEN del criterio 3**, quando `riprese_critic` esiste (su `main` il campo non
      c'è, e il test sarebbe rosso per `AttributeError`, non per il comportamento): si committa da sola,
      dopo quel GREEN, senza `--chiedi-impl`, con `Guardia-su: tools/asdlc/runner.py::esegui_pbi`, e deve
      mordere. Per `limite-del-runner` vale il
      finto di `metti_in_attesa_del_pbi_a_monte` e `HOME` in `tmp_path`, come nel test di `PBI-517`.
      **Test che cambia:** in `test_gli_altri_esiti_e_gli_altri_blocchi_non_riprendono_il_builder`
      (`tools/tests/test_asdlc_ripresa_solver.py`) il parametro `id="domanda-del-critic"` (Critic
      `sospeso` e Solver `RISOLTO`) **esce**. Questo PBI rovescia proprio quel comportamento, e il suo caso
      è il criterio 1: esce **nel commit RED del criterio 1**, accanto al test nuovo. Non nel GREEN: in
      `IMPL` la guardia di fase e il `pre-commit` rifiutano ogni file di test cambiato (`PBI-525`), e in
      `TEST_ONLY` togliere un parametro non cambia il permesso di `--chiedi-impl`, che gira i test nuovi
      (rilievo F della preverifica del 04/11).
      Gli altri tre parametri restano com'erano.
- [ ] **Il tick non mergia un giro ripreso dopo la domanda del Critic.** Una PR che passa ogni altra
      condizione e un ultimo rapporto `fatto` con `riprese_critic: 1`: `condizione_mancante()` rende «il
      Solver ha risposto a una domanda del Critic» (pytest: un parametro nuovo `riprese-critic` in
      `SCENARI_CHE_ATTENDONO` di `test_asdlc_rilascio.py`, `({"esito": {"riprese_critic": 1}}, "Solver")`).
      Rosso su `main`: la PR si mergia. Il rapporto senza il campo è già il caso di
      `test_una_pr_che_passa_tutte_le_condizioni_si_mergia_e_il_tick_lo_dice`, che resta verde; un test
      a parte per `riprese_critic: 0` nascerebbe verde e non si scrive.
- [ ] **La PR porta le domande del Critic e le risposte.** `apri_pr()` con un `Esito` che ha
      `riprese_critic == 1` e una voce in `domande_del_critic`: il corpo passato a `gh pr create` ha la
      sezione «Domande del Critic risposte dal Solver», con domanda, risposta ed evidenza; nella **stessa**
      funzione di test, un `Esito` senza riprese dà un corpo che non contiene la sezione (pytest). Rosso
      su `main`: la sezione non c'è.

**Non regressione:**
- Un giro senza `sospeso` del Critic, e la ripresa dopo il `fermati` del Builder (`PBI-517`), si comportano
  come oggi: i test di `test_asdlc_ripresa_solver.py` (tranne il parametro che esce), di
  `test_asdlc_solver.py` e di `TestOgniUscitaHaIlSuoMotivo` restano verdi. Il caso `domanda-del-critic`
  della tabella `USCITE` ha il Solver muto, e resta `sospeso`.
- `TestIlSospesoChiudeAlPrimoGiro::test_non_consuma_le_revisioni` (`test_asdlc_runner.py`) resta com'è e
  verde: il Solver è muto (`agente_finto({"builder": FATTO})`), non c'è `risolto` e quindi non c'è ripresa,
  e `esito.revisioni == 0` e un Critic solo restano veri. La decisione 3 vale solo dopo un `risolto`. Così
  gli altri test con un Critic sospeso e il Solver muto (`test_asdlc_runner.py`, `test_asdlc_traccia.py`).
- `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura

Si può scegliere senza chiedere: i nomi delle funzioni private; come `giro()` porta la ripresa alla
revisione dopo (una variabile accanto a `ripresa`, o un'altra forma); il testo esatto degli avvisi, purché
contenga le parole che i criteri cercano. Si chiama `fermati`: se un test esistente oltre al parametro del
criterio 6 fissa che dopo un `sospeso` del Critic **con un Solver che risponde `risolto`** il Builder non
riparte, o conta le sue revisioni; se per passare la risposta al Critic servisse cambiare la firma di
`revisione_critica()` o toccare `critic.md`.
