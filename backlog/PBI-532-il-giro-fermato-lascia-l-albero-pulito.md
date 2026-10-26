# PBI-532: il giro fermato archivia il lavoro non committato e lascia l'albero pulito

**Stato:** proposto il 26/10 in una sessione con Francesco, che ha scelto la strada (*Deciso*,
punto 1); **non letto**, **non in coda**. Entra dopo `PBI-525`, di cui usa l'avviso (decisione 6) e di
cui sostituisce il criterio 3.

## Direttiva

Quando un giro si ferma a metà, ciò che il Builder non ha committato resta nell'albero del runner, e
il giro dopo non parte. Tre casi in una settimana, sempre la stessa forma:

- `ada_nlt` `PBI-5`, 25/10: il test del giro 2 in stage nel worktree; il pre-flight del tick si ferma
  su `git switch --detach` e una persona fa `git stash` (`PBI-525`, punto 4).
- `ada_asdlc` `PBI-524`, 25-26/10: il giro 1 chiude `senza esito` per il limite d'uso con il RED del
  criterio 2 scritto e non committato (+25 righe in `tools/tests/test_asdlc_runner.py`). Dal 26/10
  08:25 alle 22:35 il tick ha scritto **84** volte `non lanciato: … in ada_asdlc-run non c'è nessun giro
  vivo. Il perché è nell'ultimo runs/*.log`, e il log diceva `albero-sporco-all-ingresso`. Nessuno lo
  ha saputo per 14 ore; l'albero l'ha pulito una persona.
- `ada_asdlc` `PBI-511`, 19/10: un JSON scritto dai test, non committato, chiede al Builder di
  scegliere fra il PBI e il controllo dell'albero pulito.

**Il difetto ha tre metà, e sono tutte del runner:**

1. **Nessuno mette al sicuro il lavoro non committato e nessuno lo toglie.** `chiudi()` in
   `esegui_pbi()` lo vede (`lasciato()`, «il giro lascia: file tools +1») e lo scrive nella nota, poi
   esce. `asdlc-chiudi-giro` tagga e cancella il ramo e non guarda l'albero. La ripresa dopo il limite
   d'uso (`PBI-519`) riparte dalla punta pubblicata del ramo, e trova lo stesso albero sporco.
2. **Il tick riprova in silenzio.** `lancia()` in `coda.py` alza un `Guasto` con un testo generico
   («una gara sul lucchetto, un file sporco, un PBI senza file in backlog/») invece del motivo che il
   runner ha scritto nel rapporto, e lo ripete ogni dieci minuti senza limite.
3. **La nota storpia il nome della cartella.** `file_dell_inventario()` legge `git status --ignored
   --porcelain` attraverso `git()`, che fa `strip()` dell'uscita: la prima riga ` M tools/…` perde lo
   spazio iniziale e `riga[3:]` le toglie la `t`. Nel rapporto di `PBI-524` giro 1: «file ools +1».

**Scope**

- `tools/asdlc/runner.py` — `chiudi()` dentro `esegui_pbi()`: l'archivio e la pulizia (decisioni 2-4);
  il campo nuovo dell'esito e del rapporto; `file_dell_inventario()` (decisione 6).
- `tools/asdlc/coda.py` — `lancia()`: il motivo dall'ultimo rapporto nel `Guasto` (decisione 5); la
  ripetizione dello stesso «non lanciato» passa per l'avviso di `PBI-525` (decisione 6 di quel PBI).
- `README.md` — la frase sull'albero pulito all'ingresso e sul giro fermato, nello stesso commit del
  comportamento.
- `tools/tests/` — i test dei criteri, col finto agente di `PBI-518` su `tmp_path`.
- `backlog/PBI-532-il-giro-fermato-lascia-l-albero-pulito.md` — questo file, per la spunta.
- **Fuori scope:** il controllo dell'albero pulito all'ingresso, che resta com'è (si ferma e non pulisce:
  decisione 7); `asdlc-chiudi-giro` (decisione 8); il giro `fatto`, che non passa da qui.

## ✅ Deciso, per non fermare il giro

1. **Lo stato di un giro sono i suoi commit** (Francesco, 26/10: «la cosa che comporta meno effetti
   collaterali e più in stile deterministico devops»). Una ripresa parte sempre dalla punta pubblicata
   del ramo o dal tag del giro fermato: lo stesso punto di partenza dà lo stesso giro. Il lavoro non
   committato **non entra mai** in una ripresa; si archivia per chi lo vuole leggere. È già il contratto
   di `PBI-519` (decisione 6) e di `prompt/riprendi.md` («il lavoro fatto fin lì è nel ramo, già
   committato»): questo PBI lo rende vero anche per l'albero. Il costo massimo è rifare un
   micro-commit, che è il motivo per cui i commit sono micro. Alternative scartate: **(a)** il runner
   riapplica il lavoro nella ripresa: un file scritto a metà, forse codice di produzione in una fase che
   il lucchetto non accetterebbe, forse in conflitto con un `main` mosso; il risultato dipende da dove
   il giro si è interrotto. **(b)** il prompt dice al Builder che il lavoro c'è e lui decide: la ripresa
   dipende dal giudizio di un modello, e due riprese uguali vanno in due modi.
2. **Si archivia e si pulisce in `chiudi()`, per ogni stato di `STATI_CHE_INTERROMPONO`.** Dopo
   l'inventario di fine (che resta la fotografia di ciò che il giro ha lasciato) e prima di `pubblica`:
   se `git status --porcelain` non è vuoto, `git add -A`, poi `git diff --cached --binary HEAD` in
   `<registro>/<run>-<PBI>-non-committato.patch`, poi `git reset --hard HEAD`. Il file `.patch` sta
   nella cartella del registro, che è ignorata (`runs/*`, anche in `template/.gitignore`): scriverlo
   non sporca l'albero. I file **ignorati** non si toccano: niente `git clean -x`, il venv, `node_modules`
   e il registro restano. Lo stato della fase sta nel git dir del worktree (`ADR-0021`, emendamento del
   02/09) e `chiudi_la_fase()` lo toglie già prima.
3. **È sicuro perché l'ingresso esige l'albero pulito.** Il giro parte solo con `git status
   --porcelain` vuoto (`albero-sporco-all-ingresso`), e il lucchetto tiene fuori ogni altro runner: ciò
   che è sporco a fine giro l'ha scritto il giro. Non c'è lavoro di qualcun altro da proteggere.
4. **Se l'archivio fallisce, non si pulisce.** Una scrittura del `.patch` che non riesce, o un `git
   diff` che esce male, lascia l'albero com'è e lo dichiara nella nota; il giro dopo si fermerà
   all'ingresso, come oggi, e l'avviso lo dirà. Non si perde mai lavoro per pulire. L'esito porta il
   percorso del `.patch` in un campo `non_committato` (stringa vuota se non c'era niente), e la nota lo
   nomina: «il lavoro non committato è in …, l'albero è tornato all'ultimo commit».
5. **Il tick dice il motivo.** Quando `lancia()` non trova un giro vivo dopo il distacco, legge
   l'ultimo esito del PBI con `ultimo_esito()` (`PBI-519`) e mette nel `Guasto` il suo motivo e la sua
   nota, al posto dell'elenco di cause possibili. Se l'esito non c'è (il runner è uscito prima di
   scrivere il rapporto), resta il testo di oggi.
6. **Lo stesso «non lanciato» due volte apre l'avviso di `PBI-525`.** Il canale è quello della
   decisione 6 di `PBI-525` (una issue nel repository del progetto, una sola per fermo), col titolo
   «fermo: PBI-N — non lanciato: <motivo>». Il tick continua a provare (`ADR-0008`): l'avviso non è un
   blocco, è il modo in cui una persona lo viene a sapere.
7. **L'ingresso resta com'è.** Il controllo dell'albero pulito all'ingresso non pulisce: lì non si sa
   di chi è il lavoro, e il commento in `esegui_pbi()` («non si parte sopra al lavoro di qualcun altro»)
   vale ancora. **Limite dichiarato:** un runner ucciso con `SIGKILL`, o una macchina spenta a metà
   giro, non arriva a `chiudi()` e lascia l'albero sporco; lo copre l'avviso della decisione 6, e lo
   pulisce una persona.
8. **`asdlc-chiudi-giro` non cambia.** Il criterio 3 di `PBI-525` (il settimo passo con `git stash`) è
   sostituito da questo PBI e barrato là: con l'albero già pulito da `chiudi()`, uno stash in
   `chiudi-giro` non troverebbe niente, e se trovasse qualcosa (il caso della decisione 7) uno stash
   in una lista nascosta e condivisa fra i worktree è più difficile da leggere di un `.patch` nominato
   nel rapporto.
9. **La cartella in `file_dell_inventario()` si legge dall'uscita grezza** di `git status`, senza lo
   `strip()` di `git()`: il formato porcelain ha due caratteri di stato e uno spazio prima del percorso.
10. **Lo scope dei commit è `runner`**, e `coda` per i criteri del tick.
11. **Vale anche per `albero-sporco-dopo-igiene`.** Un Builder che chiama `fatto` con l'albero sporco
    riceve ancora i suoi `MAX_IGIENE` giri per committare (`PBI-363`); se l'albero resta sporco il giro
    chiude `fermato`, ed è uno stato di `STATI_CHE_INTERROMPONO`: l'archivio vale anche lì.
12. **I test che confrontano la nota intera di un giro fermato con l'albero sporco cambiano nel
    commit RED**, per attendere la frase dell'archivio in coda alla nota: per esempio
    `TestLAlberoSporcoVeroNonDiventaUnLimite` (`tools/tests/test_asdlc_runner.py`, `assert esito.nota
    == …`). I test col `git` finto rispondono anche ai tre comandi nuovi (`add -A`, `diff --cached`,
    `reset --hard`) senza cambiare ciò che verificano.

## Dipendenze

- Bloccato da: `PBI-525` (l'avviso, decisione 6 di quel PBI; il criterio 3 di là è barrato).
- Blocca: niente per forza, ma ogni giro che si ferma con lavoro non committato ferma la coda finché
  una persona non pulisce l'albero.

## Contesto

- `tools/asdlc/runner.py`: `esegui_pbi()` (il controllo all'ingresso e `chiudi()`), `inventario()`,
  `file_dell_inventario()`, `lasciato()`, `pubblica()`, `STATI_CHE_INTERROMPONO`, `chiudi_la_fase()`,
  `riprendi_il_ramo()`.
- `tools/asdlc/coda.py`: `lancia()`, `preflight()`, `ultimo_esito()`.
- `tools/asdlc/prompt/riprendi.md`.
- `runs/coda.log` dal 26/10 08:25 al 22:35; `../ada_asdlc-run/runs/20261025-232512.json`.
- `backlog/PBI-519-il-limite-d-uso-non-ferma-la-coda.md` (decisione 6),
  `backlog/PBI-525-i-fermi-meccanici-del-pbi-5-di-ada-nlt.md` (punto 4, decisione 6).

## Verifica

- [ ] **Un giro fermato con lavoro non committato lascia l'albero pulito e il lavoro in un `.patch`.**
      Repository temporaneo, finto agente che committa un file e ne lascia un secondo modificato e un
      terzo nuovo non tracciato, poi chiama `fermati`: dopo il giro `git status --porcelain` è vuoto,
      `HEAD` è l'ultimo commit dell'agente, l'esito ha `non_committato` col percorso del `.patch` sotto
      la cartella del registro, e `git apply` di quel file su `HEAD` riproduce i due file. Rosso su
      `main`: oggi i due file restano nell'albero.
- [ ] **I file ignorati restano.** Nello stesso giro, un file in una cartella ignorata (il venv
      finto, un file del registro) c'è ancora dopo la pulizia. È una **guardia**: su `main` non si tocca
      niente. `Guardia-su: tools/asdlc/runner.py::esegui_pbi`.
- [ ] **Se l'archivio non si scrive, l'albero non si pulisce.** Con la cartella del registro non
      scrivibile, il file modificato è ancora nell'albero dopo il giro e la nota lo dichiara. È una
      **guardia**. `Guardia-su: tools/asdlc/runner.py::esegui_pbi`.
- [ ] **La nota dice la cartella giusta.** `file_dell_inventario()` con un solo file tracciato
      modificato in `tools/` rende `{"tools": 1}`. Rosso su `main`: rende `{"ools": 1}`.
- [ ] **Il «non lanciato» del tick dice il motivo del rapporto.** Con un finto runner che si stacca
      ed esce lasciando un rapporto con `albero-sporco-all-ingresso`, il `Guasto` di `lancia()` contiene
      `albero-sporco-all-ingresso`. Rosso su `main`: contiene l'elenco «una gara sul lucchetto, un file
      sporco, …».
- [ ] **Lo stesso «non lanciato» al secondo tick apre l'avviso, una volta sola.** Con il `gh` finto
      dei test di `PBI-525`: due tick con lo stesso motivo chiamano `gh issue create` una volta, col
      titolo «fermo: PBI-N — non lanciato: …»; il terzo, con la issue aperta, no. Rosso su `main` (e su
      `PBI-525`): l'avviso c'è solo per `non convergente`.

**Non regressione:**
- Un giro `fatto` non passa dall'archivio: i test della strada buona restano verdi senza modifiche.
- L'ingresso con l'albero sporco chiude `albero-sporco-all-ingresso` come oggi, senza pulire.
- `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura

Si può scegliere senza chiedere: il nome esatto del `.patch` (purché porti run e PBI e stia nella
cartella del registro), la formula della nota, dove sta la lettura dell'ultimo esito in `lancia()`.
Si chiama `fermati`: se un test esistente verifica che dopo un giro fermato i file non committati sono
**ancora nell'albero** (un confronto della nota non conta: è la decisione 12);
se `pubblica()` ha bisogno dell'albero sporco per qualcosa; se l'avviso di `PBI-525` non c'è in `main`
quando il giro parte.
