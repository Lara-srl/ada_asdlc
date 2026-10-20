# ADR-0022: un test nato verde passa se morde

**Stato:** **Accettata**, **rivista il 2026-09-26** (la prima delle quattro scelte) e **il
2026-10-01** (quando si giudica il morso), tutte e due in fondo
· **Data:** 2026-09-01 · **Ratifica:** Francesco, con il merge (`ADR-0012`); la revisione
le revisioni le ha decise Francesco, il 26/09 e il 01/10, e le ratifica il merge della PR che
le scrive. Non abroga niente di `AGENTS.md`: il SEMPRE del test-first resta, e questo
ADR dice come il gate lo **misura** quando il rosso non c'è stato.

## Contesto

`PBI-103` ha dato al gate la domanda *«quei test sono mai stati rossi?»* e tre letture
per il no: `nato verde`, `rosso non osservabile`, `rosso non isolabile`. `ADR-0021` ha
messo la stessa regola prima della scrittura, col lucchetto delle fasi, e ha lasciato
scritto cosa restava scoperto: *«il test che non morde»*, con il mutation testing come
direzione naturale del passo dopo.

Il passo dopo è arrivato prima del previsto, e da un'altra parte: **la regola ha un falso
positivo sistematico**, e il lucchetto non lo cura perché il lucchetto governa la
produzione, non i test. Misurato il 01/09 in tre modi indipendenti:

1. **Il mutante che solo la guardia uccide.** Su `pbi/pbi-333-giro3`, la guardia nata
   verde in `AppLayout.test.tsx` — *su una pratica tiene accesa la sezione che la
   contiene* — è l'unica a uccidere il mutante «solo match esatto» su `navItemForPath`.
   Il rosso vero che la accompagna non lo vede. Quattro mutanti a mano: due li uccide il
   rosso vero, uno **solo la guardia**, uno sopravvive a tutt'e due.
2. **Il Critic ha ordinato quel test.** Giro `20260901-204028`, rilievo 2: *«è proprio il
   comportamento che nessun test presidia […] la suite resta verde. Rimedio: un secondo
   caso in `AppLayout.test.tsx`»*. Il Builder ha obbedito (`9f952c0`), e il gate ha chiuso
   il giro `fermato` per quel commit. I due agenti del runner si sono contraddetti, e la
   macchina ha dato ragione a quello che sbagliava.
3. **Due sessioni indipendenti hanno scritto la stessa guardia.** Non è un vezzo di un
   Builder: è la mossa giusta davanti a quel codice, e la fanno tutti. Due giri su quattro
   di PBI-333 sono morti lì, per circa 2h30 di macchina.

La causa è nella domanda. *«È mai stato rosso?»* è una prova di **processo**: dice che il
test è stato scritto prima del codice. Ma la ragione per cui il processo conta è un'altra —
un test che non è mai stato rosso potrebbe non guardare niente — e quella ragione **si
misura direttamente**: si guasta il codice che il test dovrebbe coprire e si guarda se se
ne accorge. Un test nato verde che uccide un mutante è un buon test, qualunque sia la
storia del suo commit.

## Decisione

**Un test nato verde passa il gate se morde.** Prima di fermare, il gate prende le righe
di produzione che il branch ha cambiato fino a quel commit (`base...sha`), ne fa dei
mutanti — la cancellazione della riga, e gli scambi `===`/`!==`, `&&`/`||`, `==`/`!=`,
`and`/`or`, `true`/`false`, `<`/`<=`, `>`/`>=` — e rigira **quel test** un mutante alla
volta. In Python la cancellazione che lascerebbe un file che non compila — la riga unica
del suo blocco — scrive `pass` al posto della riga (`PBI-365`): resta un mutante solo, e
se non compila neanche così dalla riga non ne nasce nessuno. Il test si rigira nel
worktree usa e getta in cui già lo aveva visto verde:

```
nato verde
   ├── almeno un mutante lo fa fallire per asserzione  → passa; il rapporto dice quale
   └── nessuno                                          → ferma: «nato verde e non morde»
```

Quattro scelte dentro la regola, ognuna col suo perché:

- **Le righe del branch, non il file.** Il codice che quel giro ha scritto è l'unico di
  cui i suoi test rispondono. Una guardia su codice che `main` aveva già ferma come
  prima: non appartiene a questo branch, e il gate non deve indovinare cosa la copra.
- **Il kill è un fallimento per asserzione.** Un mutante che rompe la compilazione fa
  fallire *tutto*, non il test: l'errore di raccolta di pytest e il file che vitest non
  carica non hanno una riga per test, e non contano. Contare quelli farebbe passare ogni
  guardia, perché cancellare una riga a caso rompe la sintassi una volta su tre.
  E l'asserzione è **misurata** (`PBI-365`): in pytest il tipo del fallimento si legge
  dal riepilogo di `-rf`, e conta solo un `AssertionError` o il `Failed` di
  `pytest.fail`/`pytest.raises`; un `NameError` o un'altra eccezione del codice mutato è
  un guasto di esistenza, e il gate passa al mutante dopo. Il rapporto dice, per ogni
  guardia, i mutanti provati fino al kill e com'è andato ciascuno — *sopravvissuto*,
  *fallito per eccezione* col tipo, *ucciso per asserzione* — e in vitest, dove il tipo
  non è misurato, lo scrive.
- **Un mutante ucciso basta.** Il gate chiede che il test *osservi* le righe nuove, non
  che le copra tutte: è un gate, non una misura di copertura. Il mutation score è
  un'altra cosa, e non è questa decisione.
- **Il linguaggio del test sceglie i file.** Un test Python non morde un `.ts`: mutare
  l'altra metà del monolite è tempo speso per non vedere niente.

Il tempo macchina non è un vincolo, ed è stato detto esplicitamente: O(mutanti × un test)
per ogni test nato verde, con l'uscita al primo kill. Sul caso vero sono minuti, e il
giro che salvano ne costava novanta.

## Conseguenze

**Il gate torna a dire il vero sulla guardia.** La stessa `9f952c0` che ha chiuso il
giro del 01/09 passa, col mutante nominato accanto al test. Il Critic può ordinare una
guardia, e il Builder può scriverla, senza che la macchina li contraddica.

**Il verde che non morde resta fermo, e adesso lo dice meglio.** `nato verde e non
morde: N mutanti provati sulle righe cambiate, nessuno lo fa fallire` è una lettura più
forte di prima: non «il codice c'era già», ma «il test non guarda il codice». È la prova
di PBI-103 senza il falso positivo.

**Un mutante ucciso non è una copertura.** Un test che rende la pagina e guarda una cosa
sola uccide la cancellazione di quella riga e passa. Il gate misura che il test guardi
*qualcosa* delle righe nuove; quanto, non lo misura. Il Protocollo di rifinitura di
PBI-105 raccoglie i casi in cui una persona giudica vuoto un test che ha morso.

**Un guasto di esistenza non è un guasto di comportamento.** La prima prova sul caso vero
ha lasciato passare `9f952c0` nominando come mutante ucciso la cancellazione di
`import { … } from '../lib/nav'` in `AppLayout.tsx`: vero, ma lo uccide *ogni* test che
rende il componente, compreso uno che non guarda niente. La cancellazione vale solo per le
righe **indentate** — quelle dentro un corpo, che decidono; una riga a livello di modulo
dichiara, e su di lei restano solo gli scambi. È la stessa famiglia del mutante che non
compila, vista da un'altra parte, e altri membri possono emergere: il Protocollo di
rifinitura di PBI-105 è il posto in cui scriverli.

**Il lucchetto non cambia.** Una guardia nasce e si committa in `TEST_ONLY`; `--chiedi-impl`
non serve, perché non c'è produzione da scrivere. Le tre letture di prima restano: un test
che si salta o non gira non si può neanche mutare.

## Alternative considerate

**Il tag `(GUARD)` che esenta il commit.** Scartato in `ADR-0021` e resta scartato per la
stessa ragione: sarebbe l'agente esaminato a decidere quali suoi commit vengono esaminati.
La quarta lettura dà lo stesso permesso senza chiedere la parola a nessuno.

**Il mutation testing su tutto il file, o su tutta la suite.** Più forte e più lento, e
soprattutto **cambia domanda**: dice quanto bene la suite copre il codice, che è una
misura di qualità del repository e non un verdetto su un commit. Il gate risponde su un
test e su un branch; il resto è un altro strumento.

**Lasciare che sia il Critic a giudicare la guardia.** Il Critic l'ha già giudicata — l'ha
ordinata — e il gate lo ha smentito. Un gate deterministico che contraddice il giudizio
probabilistico va corretto nel gate, non delegato al giudizio.

**Chiedere il rosso *anche* alla guardia**, cioè pretendere che il Builder rompa il codice
a mano per vederla fallire e poi lo ripari. Funziona, e produce esattamente un mutante
scelto dal Builder: è la stessa cosa che il gate fa da sé, con in più la parola del
Builder su quale riga rompere. Meglio che la scelga la macchina.

## Nota del 23/09/2026 — il controllo sulla base, e il nato verde che non morde

*Nota, non abrogazione: la regola non cambia. Registra un limite misurato sul primo giro di
`PBI-364` (`runs/20260923-153009.json`, difetto 33 di `PBI-102`).*

**Il gate misura il rosso sul commit prima, non sulla base.** «Nato verde» vuol dire verde
sul genitore del commit di test, cioè sul ramo com'era un passo prima. Ne escono due errori
opposti, visti tutti e due sullo stesso giro:

- un criterio che descrive un comportamento che `main` **ha già** nasce verde sul ramo e
  sulla base: nessun ordine dei commit ne mostra il rosso, e la guardia può mordere solo le
  righe che il ramo ha scritto, che quel comportamento non lo decidono. Erano i vecchi
  criteri 2 e 3 di `PBI-364`;
- un criterio che `main` soddisfa già può invece risultare **rosso sul ramo**, se un verde
  precedente l'ha ristretto: il gate lo registra come un ciclo RED→GREEN buono, e il ciclo
  dimostra solo di aver riparato ciò che il ramo stesso aveva rotto. Era il vecchio
  criterio 5 di `PBI-364`, *vale l'ultima*: `main` con `[-1]` prende già l'ultima occorrenza.

Il controllo che li distingue è uno solo, ed è **sulla base**: il test, caso per caso, gira
contro `main`. Rosso su `main` è un criterio; verde su `main` è una guardia, e si dichiara.
~~Oggi quel controllo lo fa chi scrive il PBI, prima di accodarlo (`backlog/README.md`, formato).~~
Ristretta da `ADR-0031` (20/10): il controllo lo fa anche la pre-verifica, con la sonda sulla
base. Chi scrive il PBI continua a farlo, ma non è più l'unico. *Si rivede se* la sonda non trova i criteri già veri che una persona trova.

**«Nato verde e non morde» è un esito inconclusivo.** Dice che nessun mutante provato ha
fatto fallire il test, e da solo non dice di chi è il difetto. Le cause possibili sono tre:

1. **il test**: un'asserzione vera comunque, un dato costruito perché il guasto non si veda —
   è il caso per cui questo ADR è scritto, e la cura è riscriverlo;
2. **il PBI**: il criterio chiede un rosso che non esiste, perché il comportamento c'è già
   sulla base — si riconosce dal controllo sulla base, e la cura è nel PBI;
3. **il gate**: i mutanti non hanno toccato la riga che decide — prosa di docstring
   cancellata, la riga che decide unica istruzione del suo blocco, nessun operatore da
   scambiare (difetto 33 di `PBI-102`) — e il conto dei mutanti provati non lo mostra.

Chi legge un «non morde» non deve rimandare il Builder a riscrivere il test prima di aver
escluso la seconda e la terza causa. Sul primo giro di `PBI-364` era la seconda, con la
terza sopra.

## Revisione del 26/09/2026 — le funzioni toccate, non le righe

*Revisione, non nota: cambia la prima delle quattro scelte («Le righe del branch, non il
file»). Decisa da Francesco il 26/09, dopo il primo giro di `PBI-373`
(`runs/20260926-001008.json`, difetto 53 di `PBI-102`). ✅ Implementata da `PBI-378`
(28/09/2026), vedi in fondo alla sezione.*

**Cosa è cambiato.** La scelta del 01/09 diceva che una guardia su codice che `main` aveva
già «non appartiene a questo branch, e il gate non deve indovinare cosa la copra». Il primo
giro di `PBI-373` ha mostrato il caso che quella scelta non vedeva: un branch che **toglie**
codice. `PBI-373` cancellava `runner_vivo()` e la riga che la chiamava in fondo a
`giro_in_corso()`. Il comportamento da presidiare, il ramo del `flock`, stava nella stessa
funzione, su righe che il branch non cambiava. Un hunk di sole cancellazioni non porta
righe, e le guardie sono nate verdi e non hanno morso per costruzione. La terza causa della
nota del 23/09, «il gate», senza un modo di rimediare dal test o dal PBI.

**La decisione.**

- **Il perimetro dei mutanti sono le funzioni toccate dal diff, non le righe.** Una funzione
  è toccata se contiene una riga nuova o la posizione di una cancellazione. Il gate non
  indovina: la funzione la dice il parser, non il testo del diff.
- **Se il comportamento vive altrove, il commit della guardia nomina la funzione da
  mutare** (`Guardia-su: <percorso>::<nome>`) e il gate la include. Chi scrive la guardia
  dichiara cosa presidia, e il gate lo verifica: la regola «passa se morde» resta intera.
- **La prosa di una docstring non è codice**, e non genera mutanti (difetto 33, punto 1).

**Alternativa scartata: restare alle righe e scrivere le guardie nei PBI che cambiano quelle
righe.** È ciò che la scelta del 01/09 implicava. Scartata perché lascia scoperti proprio i
PBI che tolgono codice: la rete va scritta **quando** si cancella quella di prima, non in un
PBI successivo che tocchi per caso le stesse righe. E costringe a forzare un test su righe
del diff per accontentare il gate, cioè a scrivere il test per il gate e non per il
comportamento.

**Condizione di revisione.** Se il perimetro per funzione porta il gate a tempi che fermano i
giri (una funzione lunga toccata in una riga porta tutti i suoi mutanti), si rivede con la
misura in mano, non con un tetto fissato prima (`PBI-378`, protocollo di rifinitura).

**Limite dichiarato.** Vale per Python, che ha `ast`. Il frontend TypeScript resta per riga
finché un parser non entra nel repository `asdlc` (`ADR-0026`).

**✅ Implementata da `PBI-378` (28/09/2026).** `righe_del_perimetro()` allarga a tutte le
righe della funzione più interna (`def` o `async def`, dall'AST del file a quel commit) che
contiene una riga cambiata o la posizione di un hunk di sole cancellazioni; le righe fuori da
ogni funzione restano per riga. La riga `Guardia-su: <percorso>::<nome>` nel corpo del commit
di una guardia (`funzione` o `Classe.metodo`) aggiunge quella funzione al perimetro dei test
di quel commit; un nome che non si trova si scrive nel rapporto («funzione nominata non
trovata») e la guardia si giudica sul resto (`ADR-0008`). Entra solo un file di produzione
dentro il worktree: un test che nomina sé stesso morirebbe del proprio `==`→`!=`, e un
percorso assoluto o con `..` farebbe scrivere i mutanti fuori; lì il rapporto scrive
«funzione nominata fuori dalla produzione», allo stesso modo. `righe_delle_docstring()` toglie le
docstring di modulo, classe e funzione da ogni perimetro. Un `.ts` e un `.py` che non si
analizza restano per riga, e il rapporto lo dice. Per ogni guardia il rapporto — il log del
giro e `--gate-rosso` — elenca il perimetro: le funzioni mutate, ciascuna «dal diff» o
«nominata». Misura sul branch stesso di `PBI-378` (tre guardie, 14 funzioni toccate in
`tools/asdlc_runner.py`): 144 mutanti provati in 45 secondi, nessun tetto necessario.

## Revisione del 01/10/2026 — quando si giudica il morso

*Revisione, non nota: la regola diceva **se** una guardia nata verde passa, e non diceva
**dove** si guarda. Decisa da Francesco il 01/10, dopo il giro 1 di `PBI-386`
(`runs/20261001-004014.json`, difetto 74 di `PBI-102`). La implementa `PBI-393`.*

**Cosa è successo.** La decisione 2 di `PBI-386` chiede un golden dei cinque prompt, scritto
**prima** di spostarli dal codice ai file del pacchetto: «È una guardia: nasce verde». Il
Builder l'ha scritto in `63c9e3e9`, con `Guardia-su: tools/asdlc/runner.py::configura`. A quel
commit i prompt sono costanti di modulo, cioè dati. L'unica funzione che li tocca è
`configura()`, che assegna i globali: un mutante che cancella un'assegnazione fa esplodere il
test con `AttributeError`, e un'eccezione non è un morso. 26 mutanti provati, nessuno lo fa
fallire per asserzione. Il gate ha fermato il giro su una guardia che il PBI prescriveva e che,
a quel commit, non poteva mordere per costruzione. È la terza causa della nota del 23/09, «il
gate», vista da un lato nuovo. Il test è giusto e il PBI anche: è sbagliato il momento in cui
lo si guarda.

**La decisione.** Il morso di una guardia nata verde si giudica **al commit che la
introduce** oppure, se lì non morde, **sullo stato finale del ramo**. Ferma solo se non morde
neanche lì.

```
nato verde
   ├── morde al suo commit                          → passa, come prima
   ├── non morde lì, e morde alla punta del ramo     → passa; il rapporto dice «alla punta»
   └── non morde né al suo commit né alla punta      → ferma: «nato verde e non morde»
```

Una guardia scritta prima di un cambiamento protegge il cambiamento, e il cambiamento sta
dopo di lei, non nel suo commit. Chiederle di mordere a quel commit vuol dire chiederle di
proteggere quello che c'era, cioè proprio quello che il ramo sta per togliere.

**Il caso vero, misurato il 01/10** col gate di `main` (`quarta_lettura()` sui due alberi):

| Guardia | Al suo commit | Alla punta del ramo |
|---|---|---|
| `63c9e3e9`, il golden di `PBI-386` | non morde: 26 mutanti, 1 per `AttributeError` | **morde**: la cancellazione di `tools/asdlc/config.py:194`, la sovrascrittura con `asdlc.local.toml`, `AssertionError` |
| `45a5f9de`, la guardia della vecchia decisione 3 di `PBI-391` | non morde: 22 mutanti | non morde: 22 mutanti. **Resta ferma** |

Il `pass` al posto della lettura da `importlib.resources` (`prompt_del_pacchetto()`) **non**
è un morso: fa cadere `configura()` con un `TypeError` su `None + str`, che è un guasto di
esistenza. Il golden morde alla punta perché il percorso del venv, scritto nel file locale,
arriva dentro il prompt del Builder. Il mutante che uccide lo trova il gate, e il rapporto lo
nomina: non si prescrive nella regola.

**Perimetro e nomi alla punta.** Alla punta il perimetro è quello della revisione del 26/09,
calcolato fra la base e la punta: le funzioni toccate dal ramo intero, più quelle che il
commit della guardia nomina con `Guardia-su:`, cercate nell'albero della punta. Una funzione
nominata che alla punta non c'è più si scrive nel rapporto come oggi, «funzione nominata non
trovata», e la guardia si giudica sul resto.

**Alternative scartate.**

- **Mutare i dati**, cioè un operatore che cambia il testo delle costanti di modulo nominate
  in `Guardia-su:`. Un golden sui dati prova sé stesso: il mutante cambia il dato e il golden,
  che è quel dato scritto due volte, se ne accorge sempre. Il morso sarebbe garantito e quindi
  non direbbe niente.
- **Esentare i golden dal gate**, o dichiararli fuori. È il tag `(GUARD)` sotto un altro nome:
  sarebbe l'agente esaminato a decidere quali suoi commit si esaminano.
- **Riscrivere la guardia** perché morda al suo commit, passando dalle funzioni che scrivono i
  prompt. Riscrive la storia di un ramo già pubblicato, e il Builder stesso non sapeva se
  sarebbe bastato: molte cancellazioni lì producono eccezioni, non asserzioni.

**Conseguenze.**

- La decisione 2 di `PBI-386` resta com'è. Il giro 2 riprende i 20 commit dal tag, e il golden
  passa alla punta.
- Il caso di `PBI-391` resta un fermato giusto: una guardia che non morde da nessuna parte non
  guarda niente, e la risposta resta toglierla.
- **Limite dichiarato.** Alla punta il gate misura che la guardia guardi *qualcosa* del ramo,
  non ciò che la sua `Guardia-su:` nomina. Il golden di `PBI-386` morde su `carica()`, non su
  `configura()`. È la stessa misura della scelta «un mutante ucciso basta», allargata
  all'albero finale: vale come prova di esistenza, non come copertura.
- Il costo: una guardia che non morde al suo commit si prova una seconda volta, con i mutanti
  del ramo intero. Si paga solo sulle guardie che oggi fermano il giro.

**✅ Implementata da `PBI-393` (01/10/2026).** `gate_del_rosso()` tiene la punta del ramo —
il suo `ref`, risolto al commit anche quando è un tag annotato — e ne estrae il worktree alla
prima guardia che non morde al suo commit; vale per tutte le guardie della stessa chiamata, e
se nessuna ne ha bisogno non si estrae. `morso_alla_punta()` cerca lì il test con lo stesso
file e lo stesso nome, lo gira da solo, e se è verde lo passa a `quarta_lettura()` col
perimetro di `base...punta` più le funzioni che il commit della guardia nomina con
`Guardia-su:`, cercate nell'albero della punta. Un morso di lì entra in `morsi` con
`"dove": "punta"` e lo sha corto della punta, e il rapporto scrive «nato verde, non morde al
suo commit, morde alla punta `<sha>`»; un morso al commit porta `"dove": "commit"` e non si
riprova. La guardia che non morde da nessuna parte ha una lettura sola, «nato verde e non
morde, né al suo commit né alla punta `<sha>`», con i mutanti provati e il perimetro di
ciascuno dei due alberi; quella che alla punta non si trova, o lì non è verde, resta ferma con
«alla punta il test non si trova» o «alla punta il test non è verde».

Misura sul caso vero, `asdlc-runner --gate-rosso` col codice del branch di `PBI-393`, base
`origin/main`:

| Ref | Guardia | Esito | Tempo |
|---|---|---|---|
| `giro-fermato/pbi-386-giro1-20261001` | `63c9e3e9` | **passa alla punta `0046235`**: `tools/asdlc/config.py:194` cancellata, `AssertionError`, dopo 10 sopravvissuti | 36 s |
| `giro-fermato/pbi-391-giro1-20260930` | `45a5f9de` | **resta ferma**: né al suo commit né alla punta `9fb4cfd`, 22 mutanti per albero (15 falliti per eccezione), perimetro `comandi_dei_test` | 13 s |

Torna con la tabella del 01/10: nessun tetto necessario.
