# PBI-524: lo scheletro che il prompt chiede è quello che il lucchetto accetta

**Stato:** da rileggere prima di accodare (la lettura avversariale non c'è ancora). La decisione 1
è confermata: Francesco, 24/10/2026, «allinea il prompt e non allargare il lucchetto».

## Direttiva

Un fermo meccanico, un giro perso di `ada_nlt` (`PBI-3`, giro 2, 23/10/2026, 2 min 26 s,
nessun commit). Il Builder ha chiamato `fermati` dicendo di non poter aprire il giro: **il prompt gli
chiede una cosa che il lucchetto di fase rifiuta**.

- `tools/asdlc/prompt/builder.md` (righe 34-44): «Un modulo nuovo nasce vuoto, in un commit suo
  […] Fai prima lo **scheletro** che compila e non fa niente — il componente che rende un
  contenitore vuoto, la funzione che torna `None` — committalo».
- `e_scheletro_vuoto()` (`PBI-515`, decisione 4): in `TEST_ONLY` passa solo un file di **righe
  bianche e commenti**. Una classe con metodi che tornano `None` è codice, e il `pre-commit` la
  rifiuta con «`nlt/archivio.py` è codice di produzione e il giro è in TEST_ONLY».

Il Builder ha fatto come il prompt dice: `nlt/archivio.py` con `Archivio` e `LavorazioneNonTrovata` a
metodi vuoti, più `Lavorazione` in `nlt/schema.py`. Rifiutato, ha annullato tutto (giusto: non ha
aggirato il gate) e ha chiesto come aprire il giro, a (sbloccare lo scheletro), b (crearlo prima) o c
(partire da un test che importa un modulo inesistente). Il giro è chiuso `senza esito`, il ramo è
rimasto su `origin` senza PR, e la coda è ferma da più di un giorno perché il tick aspetta una persona
(`attende: PBI-3 ha un ramo su origin e non è in main`).

**Il difetto ha due metà, e tutte e due sono del runner:**

1. **Il prompt promette uno scheletro che il lucchetto non accetta.** Basta la forma: «a metodi
   vuoti» non è «righe bianche e commenti».
2. **Per `.py` lo scheletro con firme non serve.** Un file di soli commenti si importa, e il test
   che scrive `archivio.Archivio` (non `from archivio import Archivio`, la regola già nel prompt)
   fallisce con `AttributeError` dentro il test: è un rosso vero. Lo scheletro vuoto serve solo a
   far **raccogliere** il file. Per un simbolo nuovo in un file che esiste già (`Lavorazione` in
   `nlt/schema.py`) non serve niente, e non si può comunque: aggiungere una riga a un file con
   del codice lo rende «codice in stage» (`PBI-515`, decisione 7).

Ne segue che oggi il Builder non ha modo di sapere, né dal prompt né dal messaggio del rifiuto, che
cosa il lucchetto lascia passare. Il messaggio di `guardia_di_fase()` parla di «scrivi il test, poi
`--chiedi-impl`» e non dice che esiste lo scheletro vuoto.

**Scope**

- `tools/asdlc/prompt/builder.md` — il paragrafo «Un modulo nuovo nasce vuoto»: lo scheletro è un
  file di soli commenti (con un esempio per `.py`), per un simbolo nuovo in un file che esiste non si
  scrive niente, e il rosso è l'`AttributeError` del test.
- `tools/asdlc/runner.py` — il messaggio di `chiedi_impl()` quando non trova test nuovi (decisione
  6), e il messaggio di `guardia_di_fase()` per un file di produzione in
  `TEST_ONLY`: dice che uno scheletro è fatto solo di righe bianche e commenti, e che per un file
  esistente non c'è scheletro.
- `tools/tests/dati/prompt/builder.txt` — il golden del prompt, aggiornato nello stesso commit del
  testo (`tools/tests/test_asdlc_prompt.py`).
- `tools/tests/test_asdlc_prompt.py` (o un file nuovo accanto) e `tools/tests/test_asdlc_runner.py` —
  i test dei criteri.
- `README.md` — la frase sullo scheletro vuoto (`In TEST_ONLY il pre-commit lascia passare…`) solo
  se il testo nuovo la rende imprecisa, nello stesso commit.
- `backlog/PBI-524-lo-scheletro-del-prompt-e-quello-del-lucchetto.md` — questo file, per la spunta.
- **Fuori scope:** `e_scheletro_vuoto()` e il `pre-commit` (la regola di `PBI-515` non cambia: vedi
  la decisione 1); la ripresa dopo il limite d'uso (`PBI-519`); `--chiedi-impl` e gli errori di
  import (`PBI-521`).

**Il PBI tocca il prompt e il messaggio della guardia, non il lucchetto.** Il prompt lo legge il
Builder all'inizio del giro e il messaggio lo stampa il runner installato (`PBI-384`): un giro in
corso non cambia sotto i piedi.

## ✅ Deciso, per non fermare il giro

1. **A: si allinea il prompt al lucchetto; il lucchetto non si tocca** (Francesco, 24/10). `PBI-515` ha scelto lo
   scheletro vuoto (Francesco, 19/10, scelta B) perché uno scheletro con firme **anticipa il
   comportamento**: se fa già ciò che il test chiede, il test nasce verde e la fase non si apre, ed
   è l'avvertimento che lo stesso prompt dà due righe dopo. Alternativa scartata, **B: accettare
   anche le firme** (`class X: pass`, `def f(): return None`). Allargherebbe il `pre-commit` a un
   riconoscitore di sintassi per linguaggio (oggi basta il segno del commento), reintrodurrebbe la
   questione di dove finisce «solo una firma», e ribalterebbe una decisione di Francesco. Se la
   vuole, è un altro PBI con un ADR che abroga la decisione 4 di `PBI-515`.
2. **Lo scheletro vuoto vale solo per un file nuovo.** Per un file che esiste non c'è scheletro:
   il test accede al simbolo che manca e fallisce con `AttributeError`, `NameError` o
   `ImportError` del nome, e il gate legge l'esito test per test.
3. **L'esempio nel prompt è verificato dal codice.** Il blocco di esempio di `builder.md` passa da
   `e_scheletro_vuoto()` in un test: il prompt e il lucchetto non possono più divergere in
   silenzio. È il motivo per cui il difetto è stato possibile (due testi scritti a mano in giorni
   diversi, nessun test che li metta insieme).
4. **Il messaggio del rifiuto dice cosa passa.** Il Builder del giro 2 ha ricevuto una frase che
   non nominava lo scheletro e ha chiesto a un umano. Il messaggio nomina la regola (righe bianche
   e commenti) e la strada (il test accede all'attributo che manca).
5. **Lo scope dei commit è `runner`.**
6. **Il rifiuto di `--chiedi-impl` spiega cosa conta come test nuovo, e in che ordine si chiede**
   (aggiunta del 24/10, giri 3 e 4 di `PBI-3` di `ada_nlt`). Oggi dice «Non c'è nessun test nuovo
   nell'albero». Il Builder del giro 3 aveva committato un RED che estendeva soltanto un
   `parametrize` esistente: per il runner un test che c'era non nasce, e non aveva modo di saperlo.
   Il messaggio nomina i due fatti: **il test nuovo è una funzione nuova** (nuovi casi di un
   `parametrize` esistente non contano) e **il RED si committa da solo prima di `--chiedi-impl`**,
   che legge l'ultimo commit se l'albero non ha test non committati. `builder.md` lo dice già
   (riga 55); qui si dice anche dove il Builder lo incontra. Alternativa scartata: far nascere i
   casi nuovi di un `parametrize` come test nuovi. Cambierebbe la regola della nascita (`PBI-396`)
   per tutti i linguaggi, ed è un altro PBI.

## Dipendenze

- Bloccato da: nessuno. `PBI-519` è vicino ma indipendente (il limite d'uso, non il lucchetto).
- Blocca: la ripresa di `PBI-3` di `ada_nlt` non lo aspetta: riprende dal tag di un giro che ha già
  lo scheletro vuoto, e l'ordine del RED lo dice nel PBI stesso. Lo incontrerà il prossimo modulo
  nuovo di un PBI di `ada_nlt` (`PBI-4`: `nlt/offerta.py`).

## Contesto

- `ada_nlt`: `runs/20261023-180406.json` e `runs/20261023-180411-253702_builder_esito.json` (la
  domanda del Builder), tag `giro-fermato/pbi-3-giro2-20261023`.
- `ada_nlt`: tag `giro-fermato/pbi-3-giro3-20261024` (il RED di soli casi di `parametrize`) e
  `giro-fermato/pbi-3-giro4-20261024` (il RED chiesto dopo `--chiedi-impl`, rifiutato in `IMPL`).
- `tools/asdlc/runner.py`: `test_nuovi_da_aprire()` (l'ultimo commit se l'albero è pulito) e
  `chiedi_impl()`.
- `PBI-515`, decisioni 4 e 7 (lo scheletro vuoto; il file con del codice resta chiuso).
- `ADR-0021` (il rosso si chiede prima; lo scheletro vuoto per i moduli nuovi, riga 78) e
  `ADR-0024` (anti-pattern nel prompt del Builder).
- `tools/asdlc/runner.py`: `e_scheletro_vuoto()`, `guardia_di_fase()`.

**Prima di accodare, rileggi:**
- **R** — ogni criterio può nascere rosso su `main`?
- **T** — il golden del prompt contraddice una decisione? (si aggiorna nel commit del testo)
- **N** — i nomi e i fatti citati sono veri nel codice? (le righe 34-44 di `builder.md`, il testo
  esatto del rifiuto)

## Verifica

Su `main` i criteri 1, 2 e 3 sono un **rosso atteso**.

- [ ] **L'esempio di scheletro del prompt è uno scheletro vuoto per il lucchetto.** Il test estrae
      da `builder.md` il blocco di esempio dello scheletro e verifica
      `e_scheletro_vuoto("nlt/esempio.py", blocco)`. Sul prompt di `main` il blocco non c'è (il
      prompt descrive uno scheletro con una funzione che torna `None`): rosso. Un caso dello stesso
      test: il prompt non contiene più «la funzione che torna `None`» (pytest, parametrizzato).
- [ ] **Il rifiuto dice cosa passa.** Con fase `TEST_ONLY`, `guardia_di_fase()` su un `.py` di
      produzione con del codice torna un messaggio che contiene «commenti» e «AttributeError» (o
      la formula equivalente scelta nel RED, dichiarata nel messaggio del commit); su un
      `.py` fatto di commenti torna `None` (pytest).
- [ ] **Il rifiuto di `--chiedi-impl` dice cosa conta come test nuovo.** Con la fase `TEST_ONLY` e
      nessun test nuovo, l'uscita di `chiedi_impl()` contiene «funzione» e «parametrize» (o la formula
      equivalente scelta nel RED, dichiarata nel messaggio del commit) e il suo codice resta 1
      (pytest, repository temporaneo). Su `main` il messaggio non li nomina: rosso.
- [ ] **Il golden segue il testo.** `test_asdlc_prompt.py` resta verde col golden aggiornato nello
      stesso commit del testo del prompt.

**Non regressione:**
- `e_scheletro_vuoto()` e il `pre-commit` si comportano come prima: i test di `PBI-515`
  (`test_asdlc_supporto_dei_test.py`) restano verdi senza modifiche.
- `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura

Se il testo del rifiuto o dell'esempio ha più di una formulazione lecita, si sceglie la più corta e
si dichiara nel messaggio del commit RED. Se durante il giro emerge che il Builder ha bisogno di
**firme** per far raccogliere un test (un linguaggio diverso da Python in cui un file vuoto non
basta), non si allarga il lucchetto: si chiama `fermati` con la domanda, perché è la decisione 1.
