# PBI-500: i quattro modelli dei documenti in `template/`

## Direttiva

Primo dei quattro PBI di `template/` (D5 di `SCAFFOLDING.md` di aDa; passo 4.2 del suo
`RUNBOOK-FASE-5.md`). Nasce la cartella `template/`, quella che un progetto nuovo copia alla
nascita, con dentro **i quattro modelli** da cui si scrivono i documenti del metodo:

- `template/backlog/TEMPLATE.md` — il modello dei PBI;
- `template/decisions/TEMPLATE.md` — il modello degli ADR;
- `template/specs/TEMPLATE.md` — il modello delle spec;
- `template/.github/PULL_REQUEST_TEMPLATE.md` — il modello del corpo di una PR.

Oggi nessuno dei quattro esiste in questo repository: il modello dei PBI è descritto a parole
in `backlog/README.md`, quello degli ADR in `decisions/README.md`, quello della PR vive dentro
`apri_pr()` di `tools/asdlc/runner.py`, e quello delle spec stava solo in aDa.

**Scope**
- `template/backlog/TEMPLATE.md`, `template/decisions/TEMPLATE.md`,
  `template/specs/TEMPLATE.md`, `template/.github/PULL_REQUEST_TEMPLATE.md` — nuovi.
- `tools/tests/test_asdlc_template.py` — nuovo: i test dei criteri e la guardia.
- `backlog/PBI-500-i-quattro-modelli-di-template.md` — questo file, per la spunta.
- `tools/tests/test_asdlc_fuori_da_backend.py` — **la sonda si ritira** (giro 1, qui sotto):
  esce `test_i_test_di_tools_tests_non_aprono_connessioni_a_un_database` con ciò che serve
  solo a lei.
- **Fuori scope:** `apri_pr()` che legge il modello della PR invece del suo testo cablato
  (è comportamento del runner: un PBI suo, dopo); i `README.md` delle cartelle, `AGENTS.md`
  e il resto del metodo (`PBI-502`); la configurazione d'esempio (`PBI-501`); `ZERO.md`
  (`PBI-503`); i `backlog/`, `decisions/` e `specs/` di questo repository, che non cambiano.

**Nessun file di produzione.** Per la guardia di fase un `.md` non è codice
(`ESTENSIONI_CODICE` in `runner.py`), quindi si scrive anche in `TEST_ONLY`. **Il giro resta
in `TEST_ONLY` dall'inizio alla fine e non chiama mai `--chiedi-impl`**: una IMPL aperta su
un PBI senza produzione non si richiude (difetto 89 di `PBI-102`, giro 2 di `PBI-394` in aDa).
Durante il giro il runner non lancia nessun file dello Scope.

## ✅ Deciso, per non fermare il giro

1. **Un test per modello, e ogni test fallisce per asserzione su `main`.** Il test controlla
   prima che il file ci sia (`assert percorso.is_file()`), poi ne legge le intestazioni: su
   `main` `template/` non esiste, e il rosso è l'asserzione, non un `FileNotFoundError`.
2. **I test leggono `template/` del repository che li ospita**: portano il marcatore
   `progetto_ospite` (`tools/tests/conftest.py`), e trovano la cartella con
   `asdlc_config.radice()` dalla cartella del test, come
   `test_guardia_l_asdlc_toml_del_progetto_ospite_regge` in `test_asdlc_config.py`.
3. **Le intestazioni si confrontano come lista ordinata**, estratte con una regex su `^#+ `:
   l'ordine delle sezioni fa parte del modello. Il testo sotto le intestazioni è libero, e i
   test non lo guardano, salvo dove un criterio lo dice.
4. **La guardia** (sotto *Verifica*, non regressione) **nasce nel commit RED del criterio 1**,
   insieme al suo test, e diventa verde col suo GREEN. Su `main` è rossa perché asserisce che
   `template/` contiene almeno un file: una guardia che passa su una cartella vuota non
   guarda niente.
5. **Il modello degli ADR fissa una sola forma della firma**: `**Ratificata da** … **il** …`,
   con i due puntini di sospensione al posto del nome e della data. `RILETTURA-ADR-DI-METODO.md`
   ne ha contate tre forme negli ADR di metodo; il modello sceglie quella di
   `SCAFFOLDING.md` §Fase 4 di aDa, e gli ADR che ci sono non si toccano.
6. **Il modello dei PBI porta la sezione della ripresa**, `## Il giro N, e cosa si riprende`,
   fra le decisioni e le dipendenze, con dentro la regola di `backlog/README.md`: nomina il
   tag `giro-fermato/…` e gli sha da riprendere in ordine. È il posto deciso da Francesco il
   01/10/2026 (`PBI-391` e `PBI-385` di aDa hanno quella forma).
7. **Lo scope dei commit è `template`** (`ADR-0028`): `test(template): …` per il RED,
   `docs(template): …` per il GREEN.

## Il giro 1, e cosa si riprende (08/10/2026)

Il giro 1 è partito alle 22:05 col runner `0.1.0` installato e si è fermato alle 22:11 con
`domanda-del-builder`, dopo 8 commit: i quattro criteri, una coppia RED→GREEN per ognuno, con
la *Verifica* spuntata. Il lavoro è giusto. **La non regressione no**: `tools/tests` dava 855
passati e 1 fallito, `test_asdlc_fuori_da_backend.py::test_i_test_di_tools_tests_non_aprono_connessioni_a_un_database`.
Quel test, la **sonda**, rigira `tools/tests` in una copia ridotta del repository, costruita
da `estrazione.txt` più `DELL_OSPITE` e `DEL_PROGETTO_DI_PROVA`. Nella copia `template/` non
c'è, e i test nuovi cadono su `assert percorso.is_file()`. La domanda del Builder era giusta,
e lui non ha scelto da solo. Il PBI non aveva visto la sonda.

**Decisioni (Francesco, 08/10/2026):**

1. **La sonda si ritira.** Era il collaudo del trasloco fatto prima del trasloco (`PBI-394`,
   passi 0.2 e 2.5 del runbook della Fase 5 di aDa, tutti e due chiusi dal 07/10). A trasloco
   fatto non prova più niente. Contava le connessioni SQLite perché in aDa il `conftest.py`
   di `backend/` ne apriva una per test, e qui in `tools/` niente apre SQLite o SQLAlchemy.
   Ogni test che legge un file del repository la farebbe cadere di nuovo: 501 col pin, 502 con
   `AGENTS.md`, `backlog/README.md` e `decisions/`. Non c'è una ragione scritta per tenerla
   come guardia («i test del runner non dipendono da file fuori da `estrazione.txt`»), e
   quindi non la si trasforma in una.
2. **Cosa esce** da `tools/tests/test_asdlc_fuori_da_backend.py`: il test della sonda, la
   costante `SONDA`, `DELL_OSPITE`, `DEL_PROGETTO_DI_PROVA`, `forma_del_repository_asdlc()`, il
   commento che li introduce, gli import che restano senza uso, e il punto «Nessuna
   connessione a un database» della docstring del modulo. **Cosa resta**:
   `test_l_estrazione_porta_il_pacchetto_e_i_nomi_di_prima_e_lascia_aggiorna_kb`,
   `test_gira_gate_esegue_la_suite_asdlc_del_progetto_di_prova` e ciò che usano.
3. **Il ritiro è il primo commit del giro**, prima dei commit ripresi: `test(template):
   ritira la sonda della forma del repository asdlc`. Nel corpo dichiara la deroga allo Scope
   (`ADR-0015`): cosa esce, perché (decisione 1), e che nessun altro test cambia. Tocca solo un
   file di test, quindi si fa in `TEST_ONLY`.
4. **Poi si riprendono gli 8 commit del tag `giro-fermato/pbi-500-giro1-20261008`**, in
   quest'ordine, con `git cherry-pick`: `8f098df`, `66f3411`, `c8105b2`, `e55199f`,
   `a2bc0af`, `6687f20`, `32b8059`, `95e8f5c`. Si riprendono tutti, e niente si lascia.
5. **Il giro resta in `TEST_ONLY` e non chiama `--chiedi-impl`**, come dice la *Direttiva*.
   `python3 -m pytest -q tools/tests` si gira prima di dichiarare `fatto`.

## Dipendenze
- Bloccato da: nessuno. È il primo PBI del repository dopo la `v0.1.0`.
- `PBI-501`, `PBI-502` e `PBI-503` scrivono in `template/` e aggiungono test allo stesso
  file: vengono dopo, uno per volta.

## Contesto
- `backlog/README.md` — il formato dei PBI: le sezioni, lo Scope che nomina il PBI stesso, la
  ripresa che nomina tag e sha, il criterio come comportamento, la non regressione.
  `backlog/PBI-102-soglia-di-revisione-del-runner.md` e `backlog/PBI-368-il-tick-conta-le-cause.md`
  sono due PBI veri da guardare per la forma.
- `decisions/README.md` — le sezioni di un ADR e le quattro domande, che il modello porta come
  elenco numerato vuoto dentro `## Decisione`. `decisions/ADR-0027-…` e
  `decisions/ADR-0028-…` per l'intestazione.
- `tools/asdlc/runner.py`, `apri_pr()` — il corpo che il runner scrive oggi: è da lì che
  vengono le tre domande dell'accettazione umana.
- Il modello delle spec di aDa (`specs/TEMPLATE.md`, allo sha `ee97b3f8`), da generalizzare: è
  riportato qui sotto, in *Allegato*. Si tolgono la riga `Fase: [1|2|3|4|5]` (le fasi sono
  di aDa: resta `Stato`) e la frase su `e2e/tests/` ed `e2e/contract.ts`, che diventa «gli
  scenari di un livello hanno un test di quel livello».

## Verifica
- [x] **Il modello dei PBI ha le sezioni del formato, nell'ordine.** Il titolo è
      `# PBI-XXX: …`; poi `## Direttiva`, `## ✅ Deciso`, `## Il giro N, e cosa si riprende`,
      `## Dipendenze`, `## Contesto`, `## Verifica`, `## Protocollo di rifinitura`. Sotto
      `## Direttiva` c'è una riga `**Scope**` il cui elenco nomina `backlog/PBI-XXX-…` (il
      PBI stesso); sotto `## Verifica` c'è almeno una riga `- [ ]` e una riga che comincia con
      `**Non regressione:**`.
- [x] **Il modello degli ADR porta la firma presente e vuota, e le quattro domande.** Il
      titolo è `# ADR-NNNN: …`; la riga d'intestazione contiene `**Ratificata da** … **il** …`
      esattamente così; le sezioni sono `## Contesto`, `## Decisione`, `## Conseguenze`,
      `## Alternative considerate`, nell'ordine; dentro `## Decisione` c'è un elenco
      numerato di quattro voci che cominciano con **cosa si controlla**, **quando**, **cosa
      conta come prova**, **cosa succede se manca**.
- [x] **Il modello delle spec ha le sezioni di quello di aDa, senza aDa.** Il titolo è
      `# Feature: …`; le sezioni sono `## Blueprint` (`### Contesto`, `### Architettura`,
      `### Vincoli`) e `## Contratto` (`### Definition of Done`, `### Guardie di regressione`,
      `### Scenari`, `### Domande aperte`), nell'ordine. Il testo non contiene `Fase:` né
      `e2e/contract.ts`.
- [ ] **Il modello della PR chiede le tre cose dell'accettazione umana.** Contiene una riga
      `PBI:` e tre righe `- [ ]`: i criteri della *Verifica* del PBI spuntati, il diff fuori
      dallo Scope dichiarato nel commit che lo introduce (`ADR-0015`), la spec aggiornata nello
      stesso commit del comportamento che cambia. Il test cerca le tre parole chiave
      `Verifica`, `Scope`, `spec` in tre righe `- [ ]` distinte.

**Non regressione:**
- **La guardia di `template/`**: nessun file sotto `template/` contiene un percorso di
  macchina (`/home/`, `/Users/`, `~/`: difetto 62 di `PBI-102`) né un nome del dominio di
  aDa (`aDa`, `Barbara`, `Oltre3D`, `Carrozzeria`); e `template/` ha almeno un file. Vale anche
  per i PBI dopo questo, che la ereditano. **Ne restano fuori i file `template/decisions/ADR-*.md`**,
  per nome: sono le copie identiche degli ADR di metodo (`PBI-502`), e dieci su dodici
  nominano aDa, perché è lì che la regola è nata.
- `python3 -m pytest -q tools/tests` resta verde: nessun test che c'è cambia, **tranne la
  sonda, che si ritira** (decisione 1 del giro 1).

## Protocollo di rifinitura
Un modello è vivo: se una sezione resta vuota tre volte di fila nei documenti veri, si toglie
(la regola di `specs/README.md` di aDa). La lista delle sezioni vive nel test e nel modello:
cambiano nello stesso commit.

## Allegato: `specs/TEMPLATE.md` di aDa (sha `ee97b3f8`)

````markdown
# Feature: [Nome del dominio]

> Fase: [1|2|3|4|5] · Stato: [bozza | attiva | in evoluzione]
> PBI aperti: [PBI-XXX, …] · ADR collegati: [ADR-XXXX, …]

## Blueprint

### Contesto
Uno o due paragrafi: perché esiste questo dominio, quale gesto reale sostituisce, cosa
succede se non c'è. Niente product brief.

### Architettura
- **API:** `VERBO /rotta` — cosa fa, cosa accetta, cosa torna. Percorsi veri, non descrizioni.
- **Modello:** entità e colonne che contano, con il file in cui vivono.
- **Dipende da:** [altre spec, servizi, tool] · **Ne dipendono:** [chi consuma questo]

### Vincoli
Regole enunciate **al positivo**, come fatti sul sistema: «i tool di scrittura passano dal
service», non «non scrivere in tabella». Dove un vincolo esiste per un fallimento già visto,
il fallimento si codifica in uno scenario del Contratto, non in un avvertimento.

## Contratto

### Definition of Done
- [ ] Criterio osservabile e verificabile da solo.

### Guardie di regressione
- Invarianti che restano veri **dopo** questo PBI e dopo i prossimi.

### Scenari

```gherkin
Scenario: [Nome descrittivo]
  Dato [stato di partenza]
  Quando [l'azione]
  Allora [esito osservabile]
```

Marca ogni scenario con il livello che lo verifica: `[unit]` `[api]` `[e2e]`.
Gli scenari `[e2e]` hanno un test corrispondente in `e2e/tests/` e usano i testid
dichiarati in `e2e/contract.ts`.

### Domande aperte
| # | domanda | chi risponde | blocca? |
|---|---|---|---|
````
