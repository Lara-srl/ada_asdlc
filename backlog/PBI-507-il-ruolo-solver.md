# PBI-507: il ruolo Solver, i suoi tre strumenti e il tetto dei giri

## Direttiva

Secondo PBI di `ADR-0030`. Il Solver è il terzo ruolo, accanto a Builder e Critic: riceve un
giro fermato (`fermati` del Builder, `senza esito`, o una domanda bloccante del Critic) e lo
smista con uno di **tre strumenti** — `risolvi`, `segnala_limite_runner`, `chiedi_a_francesco`
— che il server dell'esito valida (`ADR-0027`). Il PBI scrive anche il prompt del ruolo, il
tetto di 3 giri (R12) e la regola che esclude prima la configurazione del progetto (R4).

Il Solver **non apre ancora la PR a monte**: `segnala_limite_runner` valida e registra la
chiamata nel rapporto. Aprire la PR è il lavoro di `PBI-509` (il ramo e il fork) insieme al
rilascio; qui basta che l'esito esista e sia valido.

**Scope**

- `tools/asdlc/esito.py` — il ruolo `solver` in `strumenti()` e in `chiama()`; la validazione
  di R2 (`evidenza` nomina un file che esiste nell'albero) e R3 (`causa` nell'elenco
  `runner-*`, `comando`/`output` non vuoti, `commit` esistente).
- `tools/asdlc/prompt/solver.md` — nuovo: il prompt del ruolo. L'ordine degli esiti è
  `risolto` prima (R4); legge `asdlc.toml` del progetto e `backlog/PRECEDENTI.md`.
- `tools/asdlc/runner.py` — l'invocazione del Solver dopo un giro fermato, il contatore dei
  giri nel rapporto (R12) e l'avviso al quarto giro o a `intento`.
- `tools/asdlc/config.py` — le chiavi `[solver].giri_massimi` (default 3), `[solver].cause`
  (la lista `runner-*`) e `[solver].modello` (default `"opus"`).
- `tools/tests/test_asdlc_solver.py` — nuovo: i test dei criteri.
- `README.md` e `backlog/AUTOMAZIONE.md` — il terzo ruolo, in una sezione.
- `backlog/PBI-507-il-ruolo-solver.md` — questo file, per la spunta.

**Fuori scope**

- La PR a monte, il fork, il rilascio (`PBI-509`), la guardia di processo (`PBI-508`).
- Il modello usato per il Solver oltre a una chiave di configurazione; la scelta del modello
  si misura sui primi casi (`soglia-non-misurata`).

## ✅ Deciso

1. **Tre strumenti, nomi in italiano**, uno per esito: `risolto`, `limite-del-runner`, `intento` (`ADR-0030` §1). `risolvi(risposta, evidenza)`,
   `segnala_limite_runner(causa, comando, output, commit)`, `chiedi_a_francesco(domanda)` (l'esito `intento`).
   La prima chiamata è definitiva; un Solver senza chiamate chiude `senza esito` con l'uscita
   grezza (R1).
2. **La validazione sta nello strumento**, non nel prompt: un rifiuto torna al Solver come
   errore dello strumento e può riprovare, nel tetto dei giri.
3. **`evidenza` è un percorso** relativo alla radice del progetto, con un eventuale `:riga`.
   Il file deve esistere nell'albero del giro (R2).
4. ~~**L'elenco `runner-*` si legge da `backlog/README.md` di `asdlc`**, tramite l'URL
   pinnato al tag che il progetto dichiara; senza, la causa è rifiutata.~~ Superata il 16/10
   dalla decisione 8 (giro 1): il server non ha rete e i test non devono averla.
5. **Il tetto è 3 giri Solver↔Builder per lo stesso blocco.** Il contatore sta nel rapporto
   del giro. Al quarto giro o a `chiedi_a_francesco` il giro si ferma con un avviso
   (`ADR-0008`: avviso, non blocco).
6. **Prima di `chiedi_a_francesco` il Solver legge `backlog/PRECEDENTI.md`**; se la domanda ha
   già una riga, risponde con quella (`risolvi`, evidenza `backlog/PRECEDENTI.md`).
7. **Lo scope dei commit è `runner` e `prompt`.**
8. **L'elenco `runner-*` è una lista nel TOML**, `[solver].cause = ["runner-non-legge-junit", …]`
   (Francesco, 16/10, risposta al punto 1 del giro 1). Il runner la legge da `asdlc.toml` e
   la passa al server dell'esito nella variabile `ASDLC_CAUSE` (slug separati da virgola) in
   `config_del_server`. Nessuna lettura di rete. Il progetto tiene la lista allineata a
   `backlog/README.md` di `asdlc` (`PBI-506`); una causa fuori lista è rifiutata.
9. **Gli alberi:** «commit esistente» (R3) si verifica con `git cat-file -e <commit>^{commit}`
   e `evidenza` (R2) con un file dell'albero, entrambi nella `os.getcwd()` del server, che è
   la radice del giro (`claude -p` parte da lì). Nessuna variabile `ASDLC_RADICE`.
10. **Il contatore:** un intero `giri_solver` per blocco nel rapporto `runs/<run>.json`,
    riletto dal giro successivo dello stesso PBI. «Lo stesso blocco» è il **PBI**. Al quarto
    giro (con `giri_massimi = 3`) o a `chiedi_a_francesco` il runner scrive l'avviso con
    `dichiara(...)` e non lancia il Solver.
11. **Il Solver è invocato e registrato, non ancora seguito.** Dopo un giro fermato il runner
    lancia il Solver e salva l'esito nel rapporto; con `risolto` **non rilancia il Builder**
    (la ripresa non ha un meccanismo, `backlog/README.md`: «Il runner non riprende niente»).
    Riprendere dopo `risolto` è di un PBI successivo.
12. **Il modello e gli strumenti:** la chiave è `[solver].modello`, default `"opus"` come il
    Builder (la misura sui primi casi resta `soglia-non-misurata`). Gli strumenti consentiti
    sono di sola lettura: `Read`, `Grep`, `Glob` e i tre `mcp__asdlc__*`. `RUOLI`,
    `config_del_server` e `invoca_agente` ammettono il ruolo `solver` e un comando `SOLVER`.

## Dipendenze

- Bloccato da: `PBI-506` (i due file che il Solver legge).
- Sblocca: `PBI-508`, `PBI-509`.

## Contesto

- `specs/solver-e-rilascio/spec.md`, R1-R4 e R12.
- `tools/asdlc/esito.py`, `strumenti()`, `chiama()`; `tools/asdlc/prompt/`.
- `decisions/ADR-0027-gli-esiti-passano-per-chiamate-a-strumento.md`.

## Verifica

Su `main` il ruolo non esiste: ogni criterio è un **rosso atteso**.

- [x] **Il server dell'esito espone i tre strumenti al Solver e a nessun altro ruolo.**
      `strumenti("solver")` elenca `risolvi`, `segnala_limite_runner`, `chiedi_a_francesco`;
      `strumenti("builder")` non li elenca.
- [x] **Un Solver senza chiamate chiude `senza esito`.** Con un finto `claude` che esce senza
      chiamare niente, il giro chiude `senza esito` con l'uscita grezza (R1).
- [x] **`risolvi` rifiuta un'evidenza che non esiste.** Percorso inesistente → errore dello
      strumento; percorso esistente → esito `risolto` (R2, due casi).
- [x] **`segnala_limite_runner` rifiuta una causa fuori elenco, un comando o un output vuoti,
      un commit sconosciuto.** Quattro rifiuti e un caso valido (R3).
- [x] **La prima chiamata è definitiva.** Una seconda chiamata dopo un esito valido non cambia
      l'esito (`ADR-0027`).
- [x] **Il quarto giro Solver↔Builder si ferma con un avviso.** Con `giri_massimi = 3` e tre
      giri già nel rapporto, il quarto non parte e l'avviso è scritto; `chiedi_a_francesco`
      ferma il giro con lo stesso avviso (R12).
- [x] **Il prompt dice di leggere `asdlc.toml` e il registro prima di segnalare.** Il test
      verifica le due righe nel prompt e l'ordine degli esiti (R4, R12; come
      `test_asdlc_prompt.py`).

**Non regressione:** i ruoli Builder e Critic vedono gli stessi strumenti di prima;
`python3 -m pytest -q tools/tests` resta verde.

## Il giro 1, e cosa si riprende (16/10/2026)

Il giro 1 (`20261016-104507`) si è fermato con `domanda-del-builder` dopo 3m30 e due criteri:
`strumenti("solver")` e `risolvi` con evidenza = file dell'albero (RED→GREEN ciascuno, fino a
`fe6ac33`, nel tag `giro-fermato/pbi-507-giro1-20261016`). Chiedeva cinque punti: le risposte
di Francesco sono le decisioni 8–12 qui sopra, tutte come proposte dal Builder.

- Il ramo `pbi/pbi-507` è tolto da origin; il giro 2 riparte da `main`.
- I due criteri fatti valgono e si possono riprendere dal tag. Restano: `segnala_limite_runner`
  (4 rifiuti e il caso valido), la prima chiamata definitiva, il contatore a 3, `solver.md` e
  le sezioni di `README.md` e `backlog/AUTOMAZIONE.md`.
