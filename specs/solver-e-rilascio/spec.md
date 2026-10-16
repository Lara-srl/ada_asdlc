# Spec: il Solver e il rilascio a catena

Lo **stato** voluto del sistema (come funziona). Le decisioni e le alternative stanno in
`decisions/ADR-0030-il-solver-smista-i-blocchi-e-il-rilascio-corre-da-solo.md`; ciò che
cambia, PBI per PBI, sta in `backlog/`.

> **Stato di costruzione: niente di questo esiste ancora nel runner.** La spec descrive il
> comportamento a cui i PBI devono arrivare. Oggi la catena è manuale (v. l'ADR, Contesto).

## Il ciclo

```
giro fermato / domanda bloccante del Critic
        │
        ▼
     Solver ──risolto──────────► il Builder riprende con la risposta
        │
        ├─limite-del-runner────► PR in asdlc (PBI + riga di coda) ──► merge di Francesco
        │                                                                   │
        │                           tick di asdlc: main allineato, --registra, tag
        │                                                                   │
        │                           tick del progetto: PR del nuovo pin ──► merge di Francesco
        │                                                                   │
        │                                                  pausa tolta, il PBI fermo riparte
        └─intento──────────────► avviso a Francesco; il giro resta fermo
```

## Regole

Ogni regola risponde alle quattro domande: **cosa si controlla · quando · cosa conta come
prova · cosa succede se manca**. Se manca, si segnala e il flusso va avanti (`ADR-0008`),
salvo dove è scritto che il giro chiude `senza esito`.

### R1 — Il Solver esce con una chiamata a strumento

- **Cosa:** l'esito del Solver (`risolto`, `limite-del-runner`, `intento`).
- **Quando:** alla fine di ogni chiamata del Solver.
- **Prova:** una chiamata a uno dei tre strumenti nel rapporto del giro; la prima è definitiva.
- **Se manca:** il giro chiude `senza esito`, con l'uscita grezza allegata. Mai ripiego sul
  testo (`ADR-0027`).

### R2 — `risolto` porta la fonte

- **Cosa:** la risposta a una domanda fattuale o tecnica.
- **Quando:** alla chiamata di `risolvi`.
- **Prova:** il campo `evidenza` nomina un file (codice, spec o ADR) che esiste nell'albero.
- **Se manca:** lo strumento rifiuta la chiamata; il Solver vede l'errore e risponde di nuovo.

### R3 — `limite-del-runner` vale solo per una causa `runner-*`, con riproduzione

- **Cosa:** la causa, il comando, l'output e il commit che mostrano il comportamento sbagliato.
- **Quando:** alla chiamata di `segnala_limite_runner`.
- **Prova:** `causa` è nell'elenco chiuso delle `runner-*` del progetto; `comando` e `output`
  non sono vuoti; `commit` esiste nell'albero; la riproduzione è un caso minimo che il PBI
  porterà come test rosso nel repository `asdlc`.
- **Se manca:** lo strumento rifiuta la chiamata. Una causa fuori elenco non apre mai un PBI
  a monte.

### R4 — La configurazione del progetto si esclude prima

- **Cosa:** che il blocco non venga da una chiave sbagliata del progetto (per esempio
  `[gate_del_rosso]` o `[ambiente].eseguibili`).
- **Quando:** prima di `segnala_limite_runner`; l'ordine è `risolto`, poi `limite-del-runner`.
- **Prova:** il rapporto del Solver riporta la lettura di `asdlc.toml` del progetto.
- **Se manca:** il Critic lo segnala nella rilettura.

### R5 — A monte si scrive solo con una PR

- **Cosa:** dove atterrano il PBI e la riga di `backlog/CODA.md`.
- **Quando:** all'apertura del PBI a monte.
- **Prova:** un ramo su un fork di `asdlc` e una PR da lì verso `asdlc`; nessuna scrittura su `main`, su
  `AGENTS.md` o sui file di `decisions/` esistenti.
- **Se manca:** la guardia di processo (v. sotto) lo segnala. Il merge di Francesco resta il
  cancello della coda.

### R6 — Un solo PBI a monte per causa

- **Cosa:** i duplicati.
- **Quando:** prima di aprire la PR.
- **Prova:** nessun PBI in `backlog/` né PR aperta in `asdlc` con la stessa `causa`.
- **Se manca:** si cita il PBI o la PR esistente e il progetto si mette in attesa di quello.

### R7 — Il PBI a monte cambia solo il runner

- **Cosa:** la parte a valle (per esempio la sezione `[junit]` di `asdlc.toml` del progetto)
  resta fuori dallo scope del PBI a monte e diventa un PBI del progetto, con `attende:`.
- **Quando:** alla scrittura del PBI.
- **Prova:** lo Scope del PBI a monte non elenca file del progetto; la sezione *Dipendenze*
  del PBI a valle nomina il tag atteso. Il `PBI-505` è la forma di riferimento.
- **Se manca:** il Critic lo segnala come scope largo (`ADR-0015`).

### R8 — Il tag solo per i PBI che lo dichiarano

- **Cosa:** il rilascio dopo il merge a monte.
- **Quando:** a ogni tick di `asdlc`, per ogni PR di PBI `MERGED`.
- **Prova:** il PBI ha `rilascia: patch` o `rilascia: minor`; la CI su `main` è verde; il tag
  non esiste già.
- **Se manca:** nessun tag; un PBI senza `rilascia:` non produce rilascio, ed è il caso dei
  PBI di documentazione.

### R9 — Il giro del tag lavora in un worktree usa-e-getta

- **Cosa:** `--registra` e il tag.
- **Quando:** al rilascio.
- **Prova:** i comandi girano in un worktree separato dal checkout del tick; il checkout
  del tick resta pulito.
- **Se manca:** il tick si ferma con un avviso (un albero sporco ferma già il tick).

### R10 — Il progetto vede il tag e propone il pin

- **Cosa:** i PBI fermi con `attende: <repo>#<PBI>`.
- **Quando:** a ogni tick del progetto.
- **Prova:** la PR a monte è `MERGED` (verificato con `gh pr view`, mai sulla parola) e
  il tag che la contiene esiste.
- **Se manca:** il progetto resta in attesa. Quando c'è, apre una PR che cambia solo la riga
  `[ambiente].installa` di `asdlc.toml`; la parte specifica del progetto è del PBI a valle.

### R11 — La pausa si toglie solo a pin mergiato

- **Cosa:** la ripartenza del PBI fermo.
- **Quando:** a ogni tick del progetto, dopo R10.
- **Prova:** la PR del pin è `MERGED`, verificata con `gh pr view`.
- **Se manca:** la pausa resta.

### R12 — Il ciclo ha un tetto, e Francesco è l'ultimo

- **Cosa:** i giri Solver↔Builder per lo stesso blocco (massimo 3), e gli esiti `intento`.
- **Quando:** a ogni giro del Solver.
- **Prova:** un contatore nel rapporto del giro; l'esito `intento`.
- **Se manca / si supera:** il giro si ferma con un avviso a Francesco (`ADR-0008`). Una
  decisione che fa precedente si scrive nel registro dei precedenti (`backlog/PRECEDENTI.md`), che il Solver legge
  prima di chiedere.

### R13 — La guardia di processo è codice

- **Cosa:** che R1-R12 siano state rispettate.
- **Quando:** alla chiusura del giro e a ogni tick.
- **Prova:** letta da campi del rapporto, da git e da `gh`; mai da un modello.
- **Se manca:** si segnala nel rapporto e nell'avviso; il flusso non si blocca. Il giudizio
  sulla diagnosi del Solver non è nella guardia: lo dà il Critic.
- **Dove sta:** `guardia_del_solver()` scrive in `Esito.guardia` la sezione
  `## Guardia di processo`, una riga per regola (`ok`, `violata`, `non eseguita`). Un giro
  senza Solver non ha la sezione. R4 è `non eseguita (PBI-511)` finché non c'è la traccia
  delle letture; R5-R7 leggono la PR a monte (git e `gh`) e sono `non eseguita` senza PR o
  se `gh` o git non rispondono. Ogni riga `violata` o `non eseguita` è anche un avviso
  nella nota del giro. Il Critic rilegge l'output del Solver e non rifà questi
  controlli.

## Il tick è sempre attivo

- **Meccanismo:** un cron per progetto, come oggi (`asdlc-coda`), più un timer che recupera i
  tick persi quando il PC riparte.
- **Battito:** a ogni giro il tick scrive un file con l'ora; se il file è più vecchio di una
  soglia (30 minuti), l'avviso parte.
- **Limite dichiarato:** se il PC è spento o in sospensione, la coda si ferma e riprende da
  sola alla ripartenza. Un server sempre acceso è un'alternativa da rivalutare se i progetti
  crescono.

## Decisioni di Francesco (16/10/2026)

Le cinque domande aperte dell'ADR sono chiuse così.

1. **Tetto dei giri:** 3 giri Solver↔Builder per lo stesso blocco (R12). Al quarto, o a ogni
   esito `intento`, il giro si ferma con un avviso.
2. **Soglia del battito:** 30 minuti senza che il tick scriva il file.
3. **Registro dei precedenti:** `backlog/PRECEDENTI.md`, append-only, una riga per decisione
   (data, causa, sentenza). Il Solver lo legge prima di chiedere.
4. **Permesso:** il Solver spinge su un fork di `asdlc` e apre la PR dal fork, con la
   credenziale `gh` del proprietario. Nessun permesso di scrittura su `asdlc` (R5). Il merge
   resta di Francesco.
5. **Cause `runner-*`:** l'elenco unico vive in `backlog/README.md` di `asdlc`, che possiede
   il runner. I progetti lo citano (URL pinnato al tag) e tengono solo le proprie cause. Si
   allarga con un ADR (`ADR-0030` §2).
