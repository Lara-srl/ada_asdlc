# La rilettura dei dodici ADR di metodo con le quattro domande

> Passo 0.6 di [`RUNBOOK-FASE-5.md`](https://github.com/Lara-srl/ada_controller/blob/683e2dd79d4a53fd39904b8e3e4bba66b5e47236/backlog/RUNBOOK-FASE-5.md), 03/10/2026. Le quattro domande sono
> quelle di `decisions/README.md`: **cosa** si controlla, **quando**, cosa conta come
> **prova**, cosa succede **se manca**. Valgono per una regola di gate o di giro.
>
> **I buchi si registrano, non si correggono ora** (Francesco, 03/10). Ognuno diventa una
> revisione dell'ADR nel repository `asdlc`, dove gli ADR traslocano, con un PBI o un ADR suo.
> Gli ADR si copiano al passo 2.3 così come sono: questo file va con loro, e la revisione
> nasce di là.

## In sintesi

| ADR | Regola di gate o di giro | Buchi | Il più serio |
|---|---|---|---|
| 0008 osserva e segnala | no: è di prodotto, il runner la cita come principio (`ADR-0015` §7) | — | — |
| 0009 e2e nel gate | sì | prova, se manca (in parte) | non dice cosa fa passare il job (retry? test instabili?), né che il merge si ferma |
| 0011 dati reali | in parte: lo skip di un test senza `data/` | quando, prova, se manca | «si preferiscono i valori nel test» è una preferenza, non un controllo |
| 0012 ratifica | sì | quando (in parte), prova, se manca | il formato della firma non è fissato (0011, 0015, 0017 ne usano tre), e la riga la scrive l'agente prima del merge |
| 0015 deroga allo Scope | sì | prova (in parte), se manca (Critic) | non dice con quale esito il Critic tratta una deroga assente |
| 0017 il runner è un prodotto | no: strutturale | — | due link rotti (sotto) |
| 0020 il registro esce dai branch | in parte | prova, se manca | niente dice come si accorge, e cosa fa, un branch che scrive `runs/tempi.csv` |
| 0021 il rosso si chiede prima | sì | cosa (in parte), prova, se manca (pre-commit) | non dice che fallimento conta per `--chiedi-impl` (raccolta o asserzione), né come si classifica un file di produzione |
| 0022 il verde che morde | sì | prova (vitest) | per vitest non dice cosa conta come uccisione; il **quando** lo chiude la revisione del 01/10 (difetto 74) |
| 0024 anti-pattern nel Builder | in parte: un divieto nel prompt, senza controllo | quando, prova, se manca | nessun controllo sul diff decide la violazione |
| 0026 pacchetto da tag | in parte: decisioni 3 e 4 | quando, prova, se manca | niente dice come il codice accerta che runner e server vengono dal pacchetto installato, e cosa fa se no |
| 0027 esiti da strumento | sì | quando (implicito), prova (in parte), chi legge | i valori ammessi per ruolo non stanno nella Decisione |

## Le anomalie, oltre ai buchi

- **`ADR-0024` si intitola «ADR-0022»** nella prima riga, ed è ancora **«Proposto»**, senza
  ratifica, mentre la decisione è applicata dal commit `10f3400`. Va sistemato prima di
  copiarlo, o si copia un ADR che si cita col numero sbagliato. Lo si registra qui e non si
  corregge (`ADR-0012`: lo stato lo cambia la ratifica).
- **Le risposte stanno fuori dalla sezione Decisione** in `ADR-0009` (Alternative) e
  `ADR-0012` (Conseguenze), mentre il README le chiede nella Decisione.
- **La firma della ratifica ha tre forme**: «Ratificata da Francesco il …» (0011, 0012),
  «Ratifica di Francesco: Francesco, …» (0015), «Accettata: … con PBI-360» (0017). Il buco di
  `ADR-0012` si vede qui.

## I link che si rompono nella copia

- **`ADR-0017`**: `../backlog/PBI-358-…` e `../backlog/PBI-360-…` (due volte). `PBI-102`
  trasloca (D7) e regge. Al passo 2.3 si convertono da link a citazione in prosa
  (`SCAFFOLDING.md` §5b, il grep dei link).
- Gli altri undici non hanno link relativi fuori dal gruppo. Hanno riferimenti in backtick a
  file di aDa (`ci.yml`, `e2e/contract.ts`, `backend/tests/conftest.py`, `FoglioPage.tsx`,
  `/home/laisdev/ada-run/…`), che non si rompono ma fuori da aDa perdono senso. Restano: sono
  la storia di dove la regola è nata.

## Il dettaglio, ADR per ADR

Per ognuno la risposta trovata nel testo, o il buco in una riga: cosa sceglierebbe in
silenzio chi implementa.

**ADR-0009.** Cosa: Playwright headless contro lo stack Docker con seed (Decisione). Quando:
ogni PR, ogni push in `main`, e un tag non lo scavalca (Decisione). *Prova:* buco — codice
d'uscita del job, retry, instabili. *Se manca:* buco in parte — che si fermi lo dice solo
un'alternativa scartata; non dice se il job è richiesto per il merge (oggi non lo è come
nome: la regola di `main` chiede `backend`, `e2e`, `frontend`, ed `e2e` c'è).

**ADR-0011** (la sola parte di regola). *Quando:* buco — né il momento né chi guarda. *Prova:*
buco — manca un criterio decidibile (nessuno `skipif` su `data/`, per esempio). *Se manca:*
buco — rilievo, blocco o niente.

**ADR-0012.** Cosa: modifica ad `AGENTS.md` o ADR che abroga un'istruzione del proprietario;
«abroga» resta un giudizio. *Quando:* buco in parte — la ratifica è il merge, ma non quando il
Critic controlla la firma. *Prova:* buco — formato non fissato; chi scrive la riga. *Se
manca:* buco — l'esito del «no» del Critic sta in Conseguenze e non è detto.

**ADR-0015.** Cosa: `git diff --name-only` contro il perimetro letto al dispatch (§5, §2).
Quando: al dispatch, a ogni giro, nel commit del primo file fuori (§4, §6, §1). *Prova:* buco
in parte — il formato del perimetro e della deroga è rinviato a un PBI; nessuno verifica che la
deroga stia nello stesso commit. Se manca: il runner lo scrive nella PR e non blocca (§6);
*buco* per il Critic, che non ha un esito scritto.

**ADR-0020.** Cosa: un giro lascia solo `runs/<run>.json`. Quando: dopo il merge, con
`--registra`. *Prova:* buco — come si accorge il codice di un branch che tocca il CSV (la
registrazione invece ha la chiave `(run, pbi)`). *Se manca:* buco per la violazione; per il
`--registra` dimenticato c'è «il CSV è indietro» (Conseguenze).

**ADR-0021.** Cosa: `Edit`/`Write` fuori fase, il pre-commit sullo stage; *buco in parte* su
come si classifica un file di produzione. Quando: il giro nasce in `TEST_ONLY`, il commit lo
riporta lì. *Prova:* buco — che fallimento conta, e quali sono «i test nati nell'albero». Se
manca: l'hook esce 2 e spiega; *buco* per l'esito del pre-commit e per chi legge la perdita
dichiarata di un pre-commit altrui.

**ADR-0022.** Cosa: il test nato verde contro i mutanti delle funzioni toccate, più
`Guardia-su:` (Rev. 26/09). Quando: al commit, o alla punta del ramo se lì non morde (Rev.
01/10). Prova: un mutante lo fa fallire per asserzione; *buco* per vitest. Se manca: ferma,
«nato verde e non morde», col perimetro nel rapporto. Il controllo sulla base lo fa chi
scrive il PBI, ed è dichiarato (nota del 23/09).

**ADR-0024.** Cosa: i file da non toccare e i comandi vietati, nel prompt. *Quando, prova, se
manca:* buchi — la verifica è umana («dopo 3-5 PBI»), e la sola conseguenza è il passaggio a
Opus, deciso a mano.

**ADR-0026** (decisioni 3 e 4). Cosa: la versione nel rapporto. *Quando:* buco — all'avvio o
per PBI. *Prova:* buco — come si accerta che il runner non è la copia di lavoro, e cosa si
scrive senza tag. *Se manca:* buco — la condizione di revisione è governo umano, non un esito.

**ADR-0027.** Cosa: ogni esito di un modello passa per uno strumento (Decisione 1). Quando:
implicito, a ogni risposta. Prova: lo strumento valida (campo vuoto, fuori elenco, la prima
chiamata è definitiva); *buco in parte* — i valori per ruolo non stanno nella Decisione. Se
manca: `senza esito` con l'uscita grezza, e non si prosegue; *buco minore* su chi lo legge e
sui tentativi dopo un rifiuto dello strumento.
