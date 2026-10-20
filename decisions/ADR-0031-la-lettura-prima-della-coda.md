# ADR-0031: un PBI si legge prima del lancio, e il rosso si prova sulla base

**Stato:** **Proposta** · **Data:** 2026-10-20 · **Ratifica:** Francesco, con il merge
(`ADR-0012`, `ADR-0029`). Non cambia la costituzione: nessuna riga di `AGENTS.md` si
aggiunge o si abroga. Restringe due frasi di altri ADR, che restano scritte e barrate col
rimando: la nota del 23/09 di `ADR-0022` («oggi quel controllo lo fa chi scrive il PBI») e la
decisione 4 di `ADR-0030` («niente quarto agente»).

## Contesto

L'obiettivo di Francesco (20/10) è che **il runner non si fermi per motivi meccanici**: si
ferma solo per una domanda vera.

Il 20/10 cinque PBI (514, 515, 517, 518, 519) sono passati per una lettura avversariale prima
della coda (#68). Il lettore era un agente in sola lettura, con le prove fatte in un clone di
`main`. Ha portato 33 rilievi, 13 dei quali avrebbero fermato il giro. Dopo le correzioni,
tutti e cinque hanno chiuso `fatto` al primo giro, senza fermi.

Prima di quella lettura i fermi si distribuivano così (`runs/tempi.csv` di `asdlc` e di
`ada_planning`, circa 50 esiti non `fatto`):

| Classe | Fermi | Trovabile prima del lancio? |
|---|---|---|
| Criterio già vero su `main` (`rosso-mai-visto`, «non riesco a produrre un rosso») | 11 | sì, girando il test sulla base |
| Decisione non scritta nel PBI, domanda aperta accodata, fatto citato falso | 10 | sì, leggendo il PBI contro il codice |
| Ambiente o strumenti mancanti, GREEN non scrivibile nella fase | 4 | sì |
| Limite del runner (JUnit, scheletri, file dei test, `--fork-session`, limite d'uso, albero sporco) | ~19 | no: erano difetti del runner, curati fino alla `v0.5.0` |
| Emersi solo durante il giro (giudizio vero, errore dell'agente) | ~13 | in parte |

La regola che avrebbe evitato gli 11 fermi della prima riga esiste già. `backlog/README.md`
chiede di verificare sulla base, caso per caso, ogni criterio che dichiara un rosso, e la
nota del 23/09 di `ADR-0022` lo conferma. Il controllo però **lo fa chi scrive il PBI** e
nessun codice lo verifica: il runner passa la `Verifica` come testo a Builder e Critic, e
nessuna funzione la legge. Il tick ha un solo controllo sul PBI, l'avviso `❓` di
`avviso_domande()`, che per scelta lancia lo stesso.

## Decisione

1. **Ogni PBI passa una pre-verifica prima del giro.** Due livelli:
   - **controlli deterministici**, senza modello (`PBI-520`). La **forma** del PBI (c'è la
     `Verifica` con almeno un criterio, c'è lo **Scope** e nomina il file del PBI) dà
     rilievi. I **percorsi** dello Scope che non esistono sulla base, le **dipendenze** non
     ancora spuntate e uno Scope fatto **solo di test** danno avvisi, che vanno al Lettore.
     Restano avvisi perché, provati sui PBI 500–519 di `main` il 20/10, danno falsi rilievi
     su 7 PBI su 20: nomi abbreviati (`PBI-514-…md`), file che nascono a runtime
     (`runs/.tick.lock`), percorsi dei progetti e non di questo repository (`src/test/`),
     dipendenze con un criterio uscito dal PBI (`PBI-500`). Le regole di forma, invece, non ne
     danno nessuno. Un fermo falso è anche lui un fermo meccanico;
   - **un Lettore** (`PBI-521`), un agente in sola lettura sul repository che risponde a sette
     domande fisse:
     - **R** — può nascere rosso su `main`?
     - **F** — il GREEN è scrivibile nella fase?
     - **T** — un test esistente contraddice una decisione?
     - **A** — qualcosa sporca l'albero o scrive fuori?
     - **E** — un RED che non termina, flag doppi, nomi in conflitto?
     - **D** — una decisione è lasciata al Builder, o manca una dipendenza?
     - **N** — i nomi e i fatti citati sono veri nel codice?
2. **Il rosso sulla base lo decide il codice, non il modello.** Il Lettore scrive le sonde: i
   test RED dei criteri, in un albero usa e getta su `main`. Il runner le gira con gli stessi
   strumenti di `--chiedi-impl`. Una sonda verde su `main` è un rilievo R. Il Lettore propone
   la prova, ma il verdetto viene dall'esecuzione.
3. **Gli esiti passano per chiamate a strumento** (`ADR-0027`): `rilievo`, `sonda`, `letto`.
   Un Lettore che non chiama `letto` chiude la pre-verifica `senza esito`, e il giro non parte;
   ma non è un PBI da correggere (un tetto, il limite d'uso): ha un'uscita sua,
   `lettore-senza-esito`, che il tick riprende dopo il reset come `PBI-519` (`PBI-522`).
4. **La pre-verifica gira in due punti.**
   - **A mano, prima di accodare:** `asdlc-runner PBI-XXX --preverifica`.
   - **Nel giro, prima del ramo:** in `esegui_pbi()`, dopo il controllo dell'albero pulito
     (`PBI-522`).

   Con almeno un rilievo il giro chiude `fermato` con motivo `preverifica`, **prima di creare
   il ramo**: niente commit, niente PR, niente Solver. Il tick legge l'ultimo rapporto e non
   rilancia quel PBI finché il suo file non cambia. È il percorso di `riprendi_dopo`
   (`PBI-519`), letto dagli stessi rapporti.
5. **Non è un hard-block (`ADR-0008`).** È un fermo con una domanda, come `fermati`. È l'unico
   fermo che l'obiettivo ammette, e arriva prima di aver speso il giro. Ha un precedente nel
   tick: `mancanze_dell_ambiente()` ferma il lancio quando manca ciò che i gate chiedono. La
   pre-verifica non tocca l'albero del progetto, non blocca gli altri progetti e non cambia
   la coda. Chi corregge il PBI fa ripartire il giro solo con quella correzione.
6. **Il Lettore non corregge il PBI.** Scrive i rilievi nel rapporto. Le correzioni le scrive
   una persona, come nella #68: il PBI resta di chi lo firma. Lo **Scrittore**, il ruolo che
   scrive i PBI, si aggiunge dopo, quando i giri veri mostrano che il Lettore trova i fermi.
7. **Una pre-verifica per versione del PBI.** Il rapporto porta lo sha del blob del file del
   PBI (`git hash-object`). Un PBI già letto `pronto` e non cambiato non si rilegge, così la
   lettura si paga una volta per versione.

**Le quattro domande** (`decisions/README.md`):

1. **Cosa si controlla:** il file del PBI alla versione che il giro lancerà, contro `main`.
   Il controllo guarda la forma e lo Scope (in codice), le sette domande (il Lettore) e il
   rosso dei criteri (le sonde, eseguite dal runner).
2. **Quando:** prima del ramo, dentro `esegui_pbi()`, dopo il controllo dell'albero pulito.
   Gira su un albero usa e getta alla base del giro. A mano gira con `--preverifica`.
3. **Cosa conta come prova:** un rapporto con `letto` chiamato e nessun `rilievo`, e con
   ogni sonda rossa sulla base, come la conta `--chiedi-impl`. Il rapporto porta lo sha del blob del PBI.
   Una sonda verde, un rilievo, o la mancanza di `letto` sono prove contrarie.
4. **Cosa succede se manca:** con un rilievo il giro chiude `fermato`, motivo `preverifica`,
   coi rilievi nella nota; non nasce nessun ramo e il Solver non parte. Il tick scrive
   `attende: preverifica PBI-N — <n> rilievi` e rilancia solo quando cambia lo sha del file
   del PBI su `main`: lo legge Francesco, o chi corregge il PBI. Senza `letto` il giro chiude
   `senza esito`, motivo `lettore-senza-esito`, e il tick lo riprende come un limite d'uso.

## Le due frasi ristrette

- `ADR-0022`, nota del 23/09: ~~«Oggi quel controllo lo fa chi scrive il PBI, prima di
  accodarlo»~~. Lo fa la pre-verifica (`ADR-0031`, decisione 2). Chi scrive il PBI continua a
  farlo, ma non è più l'unico. *Si rivede se* la sonda non trova i criteri già veri che una
  persona trova.
- `ADR-0030`, decisione 4: ~~«Niente quarto agente»~~ come regola generale. La decisione 4
  resta per ciò che diceva: la conformità del Solver la controlla il codice. Il Lettore è un
  quarto agente, ma con lo stesso confine: il giudizio (le sette domande) è del modello, la
  prova (la sonda) è del codice. *Si rivede se* il Lettore porta rilievi burocratici, cioè
  fermi su PBI che il giro avrebbe chiuso: è la lezione di MOLT Sinai che `ADR-0030` cita.

## Conseguenze

- **Positive:** il controllo sulla base smette di dipendere dalla memoria di chi scrive. Un
  fermo meccanico si scopre in minuti, prima del ramo, invece che a giro speso. I rilievi
  restano scritti nel rapporto e si misurano.
- **Negative:** ogni versione nuova di un PBI costa una lettura. Il Lettore può sbagliare in
  due modi: un falso rilievo ferma un PBI buono (lo si vede nel rapporto e si toglie
  correggendo la regola), e un rilievo mancato lascia il fermo al giro, cioè com'è oggi.
- **Neutre:** il Builder, il Critic, il Solver, il gate del rosso e il lucchetto di fase non
  cambiano. La regola di `backlog/README.md` resta com'è.

## Alternative considerate

- **Solo regole più rigide nel TEMPLATE.** La regola c'è già e non è bastata: in un mese ha
  mancato 11 criteri. Una checklist in più nel TEMPLATE si aggiunge (`PBI-520`), ma da sola
  non cambia chi controlla.
- **Solo il comando a mano.** Dipende dal ricordarsene, che è il difetto di oggi. Scartata
  come unico punto; resta come primo.
- **Uno Scrittore subito.** Scrivere PBI migliori senza un controllo che li misuri sposta il
  problema: lo Scrittore avrebbe bisogno del Lettore come gate. Viene dopo.
- **Il Lettore che corregge il PBI da sé.** Cambierebbe un documento firmato da Francesco
  senza la sua firma (`ADR-0012`). Scartata.
