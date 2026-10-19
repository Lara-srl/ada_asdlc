# PBI-519: il limite d'uso non ferma la coda

**Stato:** in coda, dopo `PBI-518` e prima di `PBI-517` (Francesco, 20/10: gli obiettivi sono zero fermi meccanici)

## Direttiva

Francesco ha fissato un obiettivo (20/10): **il runner non si ferma per motivi meccanici**; si ferma
solo per una domanda vera. Dei 23 fermi misurati il 19/10 circa dieci sono meccanici, e due non hanno
niente da decidere: `PBI-509`, il Builder (16/10, 17:45) e il Critic (18/10, 22:00), `senza esito` con
codice d'uscita 1 e lo stderr «You've hit your session limit · resets 7:50pm» (e «…2:10am»). È il
limite d'uso dell'account, il difetto 27 di `PBI-102`, di cui oggi è chiusa solo la metà: il giro non
consuma igiene né tentativi (`PBI-367`) e la nota nomina l'ora del reset (`PBI-363`). **L'altra
metà, aspettare il reset e riprendere, non c'è mai stata** (la riga di `PBI-102` dice «oppure aspetta
il reset e riprende con `-c`», e resta non spuntata).

Il giro chiude `senza esito`, pubblica il ramo senza PR, e il tick dice `attende: PBI-N ha un ramo su
origin e non è in main — nessuna PR sul ramo`. La coda resta ferma finché una persona non chiude il
giro, scrive una ripresa e fa un merge: per un guasto che dopo qualche ora passa da solo. Il limite si
ripresenterà, e di più con i giri lunghi e con modelli più costosi.

Questo PBI chiude l'altra metà: dopo un `senza esito` dovuto al limite d'uso, **il tick aspetta il
reset e riprende il PBI da dove era**, senza una persona.

**Scope**

- `tools/asdlc/runner.py` — `limite_d_uso()` e la nota del `senza esito` (l'ora del reset diventa un
  valore), il campo `riprendi_dopo` nel rapporto, e `--riprendi` (la partenza dalla punta del ramo).
- `tools/asdlc/coda.py` — `decidi()`: la decisione nuova per un PBI che aspetta il reset, e il
  lancio con `--riprendi`; la riga del log.
- `tools/asdlc/prompt/riprendi.md` — **nuovo**: il testo di ripresa per il Builder (uno per ruolo
  come gli altri file di `tools/asdlc/prompt/`; se `pyproject.toml` elenca i prompt, si aggiunge lì).
- `tools/tests/` — i test dei criteri, in un file nuovo accanto a quelli del tick e del limite d'uso.
- `README.md`, `backlog/AUTOMAZIONE.md`, `specs/` — dove descrivono il tick e il `senza esito`, nello
  stesso commit del codice.
- `backlog/PBI-519-il-limite-d-uso-non-ferma-la-coda.md` — questo file, per la spunta.

**Fuori scope**

- **Un'eccezione per i file sporchi all'ingresso.** Il controllo dell'albero pulito guarda tutto, senza
  eccezioni (`ADR-0020`, e il commento in `esegui_pbi()`): una lista di percorsi tollerati è la toppa che
  `ADR-0020` ha già tolto. Il fermo all'ingresso per file lasciati dai test si cura alla causa,
  `PBI-518`.
- **Riprendere dopo un `fermati` o altri fermi meccanici** (la ripresa dal tag senza una persona): è
  un PBI suo, dopo `PBI-517`.
- **Il Critic rilanciato da solo.** Dopo la ripresa il giro rifà il suo percorso intero (Builder, gate,
  Critic); un Builder che trova il lavoro già fatto chiama `fatto`.
- **Un'ora del reset inventata:** se l'ora non è leggibile non si riprende (decisione 2).
- **Un limite d'uso del Solver o del tick.**

## ✅ Deciso, per non fermare il giro

1. **Quando.** Il giro chiude `senza esito` per `builder-senza-esito` o `critic-senza-esito` e l'uscita
   dell'agente porta la frase del limite (`FRASE_DEL_LIMITE`) **con l'ora del reset leggibile**
   (`ORA_DEL_RESET`). Ogni altro `senza esito` resta com'è. La lettura dell'ora è un testo letto da
   uno strumento, l'eccezione già dichiarata da `PBI-363`: se la CLI esporrà l'ora in un campo si
   leggerà da lì.
2. **L'ora non leggibile non si inventa.** Con la frase ma senza ora (`PBI-363`, decisione 4) non c'è
   `riprendi_dopo` e il giro resta com'è oggi: una persona lo chiude.
3. **Il rapporto porta `riprendi_dopo`:** data e ora locali, ISO, la **prima occorrenza di quell'ora
   successiva all'istante in cui l'uscita è stata scritta**, più cinque minuti di margine. «Resets
   7:50pm» letto alle 17:45 è oggi alle 19:55, letto alle 21:00 è domani alle 19:55. Il fuso è quello del
   runner; il messaggio dice «Europe/Rome» e la macchina è la stessa.
4. **Il giro si chiude come oggi:** `senza esito`, una sola chiusura, il ramo pubblicato (difetto 48).
   Nessun Solver (non è un blocco da smistare) e nessuna pausa.
5. **Il tick decide, e sa solo questo:** un PBI con un ramo su origin non in `main`, senza PR, il cui
   **ultimo** rapporto porta `riprendi_dopo`. Prima di quell'ora la riga del log dice `attende il reset
   del limite d'uso: PBI-N riprende dopo HH:MM`, e non lancia: non è un blocco e non ferma la coda
   (`ADR-0008`). Dopo quell'ora lancia `asdlc-runner PBI-N --riprendi`. Con un rapporto senza
   `riprendi_dopo` il comportamento è quello di oggi (`attende: …`).
6. **`--riprendi` parte dalla punta del ramo pubblicato, non da `origin/main`.** Il worktree del giro
   si porta alla punta di `origin/<ramo del PBI>` e il giro continua **su quello stesso ramo** (i commit
   nuovi avanzano di `fast-forward`; niente `-giro2`). I controlli dell'ingresso non cambiano: l'albero
   deve essere pulito.
7. **Il Builder riparte con una sessione nuova**, non con `--resume`: la sua sessione può essere
   incompleta, e così il PBI non dipende da `PBI-513` né da `PBI-517`. Il prompt (`riprendi.md`) dice
   che il giro precedente si è interrotto per il limite d'uso dell'account, che il lavoro fatto è nel
   ramo (`git log`, le spunte del PBI), e di continuare dal primo criterio non spuntato **senza rifare**
   ciò che è già committato.
8. **Un tetto di tre riprese per PBI** per limite d'uso (`riprese_limite` nel rapporto, contato come
   `giri_solver_fatti()`, sui rapporti del PBI). Oltre, il giro chiude come oggi e una persona
   interviene.
9. **Se la ripresa si ferma per altro**, vale quel motivo e il suo percorso (Solver, domanda, gate):
   la ripresa è un giro come gli altri.
10. **Lo scope dei commit è `runner` (e `coda` per il tick).**

## Dipendenze

- Bloccato da: `PBI-518`, perché la suite di questo PBI gira un agente finto e rischia gli stessi
  fermi. Va dopo il 513 in coda (tocca `runner.py` e `coda.py`).
- Non dipende da `PBI-517`.

## Contesto

- `PBI-102`, difetto 27, e la riga non spuntata «Un Builder a cui è stata tolta la parola…»;
  `PBI-363` (la frase e l'ora, decisioni 3-5) e `PBI-367` (il limite d'uso è un `senza esito`).
- Gli stderr dei due fermi: `runs/20261016-174510-871136_builder_esito.json.stderr` e
  `runs/20261018-220019-113148_critic_esito.json.stderr`, in `ada_asdlc-run`.
- `tools/asdlc/runner.py`: `FRASE_DEL_LIMITE`, `ORA_DEL_RESET`, `limite_d_uso()`, `nota_senza_esito()`,
  `esegui_pbi()`, `giri_solver_fatti()`; `tools/asdlc/coda.py`: `decidi()`, `Attende`, `attese()`.
- `decisions/ADR-0008` (osserva e segnala), `ADR-0020` (il controllo senza eccezioni).

## Verifica

Su `main` il rapporto non porta `riprendi_dopo` e il tick non sa riprendere, quindi i criteri sono un
**rosso atteso**, salvo il 3 (vedi). Gli agenti e l'orologio sono finti: nessun test lancia `claude` né
aspetta davvero.

- [ ] **Un `senza esito` per il limite con l'ora leggibile porta `riprendi_dopo`.** Un Builder finto
      che esce 1 con «You've hit your session limit · resets 7:50pm»: il rapporto ha `riprendi_dopo`
      (pytest).
- [ ] **L'ora è la prima occorrenza successiva, con il margine.** «resets 7:50pm» con l'orologio alle
      17:45 dà oggi 19:55; alle 21:00 dà domani 19:55 (pytest, orologio finto, due casi).
- [ ] **Senza ora leggibile non c'è `riprendi_dopo`.** Nato verde su `main`, per costruzione: è una
      guardia, si committa da sola con `Guardia-su: tools/asdlc/runner.py::limite_d_uso` e deve mordere
      (pytest).
- [ ] **Il tick aspetta prima dell'ora.** Con un PBI il cui ultimo rapporto ha `riprendi_dopo` nel
      futuro, `decidi()` non lancia e la riga del log dice `attende il reset del limite d'uso` con l'ora
      (pytest, tick finto).
- [ ] **Il tick riprende dopo l'ora.** Con `riprendi_dopo` nel passato, `decidi()` lancia il PBI con
      `--riprendi` (pytest).
- [ ] **`--riprendi` parte dalla punta del ramo.** In un repository temporaneo con `origin/main` e un
      ramo `pbi/pbi-N` con due commit, il giro di ripresa non crea `-giro2`, parte dai due commit e i
      nuovi avanzano di `fast-forward` (pytest).
- [ ] **Il prompt di ripresa dice di non rifare il lavoro.** Il prompt del Builder in ripresa contiene
      il rimando a `git log` e alle spunte, e «senza rifare» ciò che è committato (pytest).
- [ ] **Il tetto di tre riprese.** Con un rapporto che porta `riprese_limite = 3`, `decidi()` non
      riprende e la riga dice `attende: …` come oggi (pytest).

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde; un `senza esito` che non è il
limite d'uso, e un giro che non incontra il limite, si comportano come prima.
