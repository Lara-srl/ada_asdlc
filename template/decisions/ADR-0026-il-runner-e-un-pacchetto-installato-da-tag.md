# ADR-0026: il runner ASDLC è un pacchetto installato da un tag git, non una fotocopia

**Stato:** **Accettata** · **Data:** 2026-09-25 · **Ratifica:** Francesco, con il merge
(`ADR-0012`). La decisione è sua: la **B**, del 24/09. L'ADR lo scrive un agente che ne
beneficia, perché smette di tenere due copie allineate a mano, e per questo la ratifica è
il merge. Cambia la **scelta 1** del 12/09 in `backlog/SCAFFOLDING.md` («template repo, non
pacchetto pip») ed emenda la seconda alternativa scartata di `ADR-0017`. Non tocca
`AGENTS.md`.

## Contesto

`ADR-0017` ha deciso che il runner si estrae e non si riscrive, e le sue tre precondizioni
sono vere dal 22/09. Restava da decidere la **forma** dell'estrazione. `SCAFFOLDING.md` la
fissava il 12/09: un template repo su GitHub, da cui ogni progetto nasce con una fotocopia di
`tools/asdlc_*.py`, e un `PROVENIENZA.md` che misura la divergenza col comando
`git diff --no-index`.

Da allora sono successe tre cose che quella scelta non aveva visto:

- **Il ritmo delle correzioni.** Fra il 22/09 e il 24/09 sono stati scritti quattordici PBI
  del runner (359-372), e il registro dei difetti di `PBI-102` è passato da 28 a 42 (44 al
  25/09). Con la
  fotocopia, ogni correzione andrebbe portata a mano in ogni copia. `ADR-0017` scarta
  proprio questo, per nome: «due copie che divergono, e le correzioni fatte di là che non
  tornano mai di qua». Il template non lo evita, lo rimanda al giorno del fork.
- **Il runner non è più un file solo.** Ci sono `asdlc_runner.py`, `asdlc_coda.py`,
  `asdlc_config.py`, il server dell'esito `asdlc_esito.py` (`ADR-0027`), i cinque prompt e i
  test. Il server lo lancia la CLI di Claude come processo a parte, da un percorso che il
  runner scrive nella config: deve essere lo stesso codice del runner che lo chiama, alla
  stessa versione.
- **Il repository `asdlc`.** Il runner si svilupperà in un repository suo, e quel
  repository è il suo secondo consumatore. `ADR-0017` rimandava il pacchetto «finché esiste
  un solo consumatore»: da quel momento i consumatori sono due.

## Decisione

1. **Il runner e il server dell'esito sono un pacchetto Python**, sviluppato nel repository
   `asdlc`. I progetti lo installano **da un tag git** (`pip install
   git+…/asdlc@vX.Y.Z`), pinnato a un tag e mai a un ramo. **Niente PyPI**: il pacchetto ha
   un produttore e pochi consumatori, e tutti possono leggere il repository. Il tag è la
   release.
   **Come si installa** (Francesco, 25/09, dopo il merge): in un **ambiente virtuale per
   progetto**, con la versione fissata dal tag. Il crontab del tick e l'hook di fase chiamano
   i comandi di quell'ambiente. Il repository `asdlc` è **privato**, e l'installazione passa
   per `git+ssh` con la chiave che la macchina già usa.
2. **I prompt sono dati del pacchetto, e un progetto li estende, non li sostituisce mai.**
   Ogni ruolo ha un file di aggiunte nel progetto, che il runner accoda al prompt del
   pacchetto. Il percorso lo dichiara `asdlc.toml`. Se un progetto potesse sostituire un
   prompt, le istruzioni che portano i difetti imparati (`ADR-0024`, i casi di `PBI-102`)
   sparirebbero senza che nessuno lo decida. Con l'aggiunta, un aggiornamento del pacchetto
   arriva a tutti, e ciò che è del progetto resta suo.
3. **Il runner che lavora è sempre quello installato, mai la copia di lavoro.** Vale anche
   nel repository `asdlc`: lì il sorgente si sviluppa con la **versione rilasciata**. Un giro
   che corregge il runner non lo esegue mentre lo cambia: il `PBI-358` ha mostrato che un
   runner che riscrive se stesso può togliersi `git commit` a metà giro. La correzione
   diventa attiva al tag successivo.
   **Oggi non è così, e si vede.** Nel primo giro con le chiamate a strumento (`PBI-370`,
   25/09) la config generata lancia `/home/laisdev/ada-run/tools/asdlc_esito.py`: il server
   che sta nell'albero su cui il Builder lavora. Per `PBI-372`, che modifica proprio quel
   file, ogni invocazione dopo il primo commit partirebbe col server a metà della modifica:
   il Critic, una riprova, un giro d'igiene. Il pacchetto installato toglie il caso alla
   radice.
4. **Ogni giro registra in `runs/<run>.json` la versione del pacchetto che lo ha prodotto**
   (tag e sha). Prende il posto di `PROVENIENZA.md`: con una sola sorgente la divergenza non
   c'è più, e resta da sapere quale versione ha prodotto un giro.
5. **I documenti di metodo si copiano, il codice si installa.** Lo scheletro di `AGENTS.md`,
   i `TEMPLATE.md`, la grammatica di `CODA.md`, gli ADR di metodo e la knowledge base stanno
   nel repository `asdlc` e si copiano **una volta**, alla nascita di un progetto. Da lì in
   poi sono del progetto e devono divergere: un `AGENTS.md` identico a quello del template
   non descrive nessun progetto.

**L'ordine** (Francesco, 24/09): prima si svuota la coda del runner in aDa fino a `PBI-372`.
Poi vengono i PBI di impacchettamento, scritti ed eseguiti **qui**: `pyproject.toml`, prompt
come dati, file di aggiunte, versione nel rapporto. Solo dopo nasce il repository `asdlc`,
e aDa diventa il primo progetto che lo installa. Così il pacchetto nasce dal runner che ha
fatto i giri veri, come vuole `ADR-0017`, e il suo primo consumatore è il progetto che quei
giri li ha pagati.

## Alternative scartate

**La fotocopia: un template repo e un `PROVENIENZA.md`** (`SCAFFOLDING.md`, scelta 1 del
12/09). È l'alternativa che `ADR-0017` scarta, con una misura accanto: la divergenza si
vedrebbe, ma non si eviterebbe. Con quattordici PBI del runner in tre giorni, «si misura»
vuol dire rincorrerla. Ogni progetto diventerebbe un fork del runner, e il difetto 44
corretto qui resterebbe aperto in tutti gli altri.

**PyPI.** Aggiunge un account, un processo di pubblicazione e un registro pubblico per un
pacchetto che ha un solo produttore. Il tag git dà le stesse garanzie di versione, e la
sorgente resta quella che si legge.

**Un submodule git.** Il codice arriverebbe in una cartella del progetto, e sarebbe
modificabile lì: è la copia di lavoro che la decisione 3 esclude. E il server dell'esito
avrebbe un percorso che cambia da progetto a progetto.

**Prompt sostituibili per intero.** Un progetto potrebbe adattarli meglio al suo dominio, ma
perderebbe in silenzio ogni correzione futura ai prompt del pacchetto. Le aggiunte bastano per
il dominio, e la parte comune resta comune.

## Conseguenze

**Positive**
- Una correzione del runner arriva a ogni progetto con un tag, e ogni progetto sa da quale
  tag viene ogni suo giro.
- Il server dell'esito e il runner hanno sempre la stessa versione, perché sono lo stesso
  pacchetto installato.
- Il rischio del runner che riscrive se stesso sparisce: il codice che gira non è mai quello
  sotto modifica.

**Negative**
- **Una correzione urgente costa un tag.** Il runner in lavorazione non si usa finché non è
  rilasciato. Si accetta: è il prezzo della decisione 3, e rilasciare un tag costa un minuto.
- **La compatibilità all'indietro diventa un tema.** `asdlc.toml`, il contratto di
  `runs/<run>.json` e i file di aggiunte sono un'interfaccia. Un cambio incompatibile si
  dichiara nel tag, e il progetto sceglie quando salire.
- **I PBI del runner non vivono più in aDa.** I difetti che aDa trova si scrivono nel
  repository `asdlc`, e aDa li riceve con un aggiornamento del tag.
- **Il lavoro della Fase 5 cambia.** Non si copiano più i file: si scrive il pacchetto.
  `SCAFFOLDING.md` §Fase 5 e §Fase 6 lo dicono nello stesso commit.

## Condizione di revisione

- **Un progetto deve modificare il codice del pacchetto per funzionare**, e non gli bastano
  `asdlc.toml` e le aggiunte ai prompt. Se capita, l'interfaccia è troppo stretta: prima di
  aprirla si rivede questo ADR, perché la risposta facile, la copia locale, è la fotocopia che
  qui si scarta.
- **Una correzione gira in un progetto dalla copia di lavoro**, perché il tag costava troppo.
  Una volta è un incidente. Alla seconda la decisione 3 non regge, e va rivista con una misura
  di quanto costa davvero un rilascio.
- **Il terzo progetto.** Lì si rivede se il repository `asdlc` resta privato (Francesco,
  25/09).
- **Un consumatore fuori da Lara srl.** Lì PyPI, o un indice privato, torna una domanda
  vera.
