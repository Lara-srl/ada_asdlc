#!/usr/bin/env python3
"""Esegue i PBI uno per volta: Builder → gate deterministici → Critic → PR.

Il principio è quello di `.claude/skills/asdlc/practices/workflow-as-code.md`:
l'orchestrazione è deterministica (branch, gate, retry, stop), probabilistico è solo
ciò che richiede intelligenza — scrivere il codice, e giudicarlo.

Tre livelli di verifica, come in `.claude/skills/asdlc/patterns/context-gates.md`, e sono
tre cose diverse:

  1. Quality Gate  (deterministico) — pytest, tsc, eslint, vitest. Gli E2E no: li fa la CI.
     Li esegue QUESTO script e ne legge l'exit code: un agente che si autodichiara
     verde è un agente che ha imparato a dire "verde".
  2. Review Gate   (probabilistico) — il **Critic**, sessione separata, modello
     diverso, nessun permesso di scrittura. Non è pignoleria: un builder che rilegge
     il proprio lavoro nella stessa sessione conferma le proprie premesse.
  3. Acceptance Gate (umano) — la PR. Lo script la apre; **non la mergia mai**.
     Il merge è il confine dell'accountability, e non è delegabile.

Ogni esecuzione scrive i **tempi** in `runs/tempi.csv` (una riga per PBI, in append):
è la base per fatturare l'ingegnere-agente a ore. `--riepilogo` li rilegge e somma.

Un PBI = una sessione = un contesto pulito. È il motivo per cui il PBI è un puntatore
alla spec invece che una copia: tutto ciò che serve si rilegge dai file.

    python3 tools/asdlc_runner.py PBI-201
    python3 tools/asdlc_runner.py PBI-313 --senza-critic   # due gate su tre, e lo dichiara
    python3 tools/asdlc_runner.py PBI-201 PBI-203 --dry-run
    python3 tools/asdlc_runner.py --riepilogo --tariffa 90

⚠️ Da usare in un clone o in un worktree dedicato, mai sull'albero che stai guardando:
   l'agente gira in modalità non interattiva e scrive senza chiedere conferma.
   **Un albero, un agente.** Dal 25/08 il runner lo verifica invece di sperarlo: prende
   un lucchetto sul worktree e censisce chi altro ci sta lavorando (`lucchetto()`,
   `agenti_estranei()`). Serve un secondo giro in parallelo? Un altro worktree.
"""
from __future__ import annotations

import argparse
import ast
import csv
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parent.parent

# `tools/` non è un pacchetto e non deve diventarlo: il runner si lancia per
# percorso, e sotto i test si carica con `importlib` da `backend/tests/`. Il
# lettore della configurazione sta accanto a questo file, e si importa da lì.
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))
import asdlc_config  # noqa: E402

# Le costanti che seguono nascono da `asdlc.toml`, in `configura()`: i percorsi
# sono relativi a `REPO`, e la ragione di ogni valore sta accanto a dove si legge.
CFG: asdlc_config.Config
GATE_DEL_ROSSO_ATTIVO: bool  # `[gate_del_rosso].attivo` — la valvola del livello 4
BASE: str                # `[git].base` — `origin/main`: da cui si nasce e su cui si misura
REMOTO: str              # `origin`, da `BASE`
RAMO_PRINCIPALE: str     # `main`, da `BASE`: verso cui si apre la PR
LOG_DIR: Path            # `[registro].cartella` — `runs/`
CSV_TEMPI: Path          # `[registro].tempi` — `runs/tempi.csv`
BACKLOG: str             # `[backlog].cartella`
VENV: str                # `[ambiente].venv`
PRESTITI: tuple[str, ...]  # `[ambiente].prestiti`
# Il worktree è uno solo e non aveva un lucchetto: vedi `lucchetto()`. Qui c'è il
# **nome** del file e non il suo percorso: la cartella è `LOG_DIR`, e un percorso
# calcolato qui la congelerebbe all'import — chi sposta `LOG_DIR` (i test di
# `main()`, che girano su `tmp_path`) si ritroverebbe il lucchetto rimasto
# indietro nel `runs/` vero, cioè un test che misura se sul PC c'è un runner vivo.
NOME_LUCCHETTO = ".runner.lock"

# Chi, girando in questo albero, ci **scrive**. Un `tail -f` sul log o un `git log`
# aperto non sono un pericolo, e un controllo che grida sempre si impara a spegnere.
AGENTI = ("claude", "asdlc_runner")

# I flag di autonomia e di routing stanno qui, in un posto solo, così si vedono e si
# cambiano. ⚠️ Verifica i nomi con `claude --help`: cambiano fra versioni della CLI.
# ⚠️ **Non** `--dangerously-skip-permissions`, e nemmeno `--permission-mode auto`:
# in quelle due modalità l'hook di fase (`.claude/hooks/fase-tdd.sh`) non viene
# chiamato affatto — misurato il 01/09, e la documentazione dice il contrario. Il
# lucchetto sembrerebbe esserci e non ci sarebbe, che è il modo peggiore di non
# funzionare. `acceptEdits` accetta le modifiche senza chiedere ma le fa passare
# dall'hook; `Bash` va permesso per nome, o gira in una sandbox che non scrive
# fuori dalla working directory. `--allowedTools` è variadico e non deve restare
# in coda: il prompt si concatena subito dopo, e se lo mangia.
# I due strumenti del server dell'esito vanno permessi per nome, come `Bash`: senza,
# `-p` li nega (`permission_denials`) e il file d'esito non si scrive (PBI-367).
BUILDER = ["claude", "-p", "--allowedTools", "Bash", "mcp__asdlc__fatto", "mcp__asdlc__fermati",
           "--permission-mode", "acceptEdits"]
# Model routing (patterns/model-routing.md): il giudizio costa più della generazione,
# e il Critic non scrive niente — solo lettura e `git diff`, più i due strumenti
# con cui dichiara l'esito.
# ⚠️ `--allowedTools <tools...>` è **variadico**: se resta in coda si mangia il prompt,
# che viene concatenato subito dopo, e `-p` parte senza input. Il flag variadico non
# deve mai essere l'ultimo, e lo stesso vale per `--mcp-config` (`invoca_agente`).
CRITIC = ["claude", "-p", "--allowedTools",
          "Read,Grep,Glob,Bash(git diff:*),mcp__asdlc__fatto,mcp__asdlc__fermati",
          "--model", "opus"]

# Il server dell'esito (`PBI-366`, `ADR-0027`): sta accanto al runner, e si
# estrae con lui. I ruoli sono i suoi: un altro valore lo ferma all'avvio.
SERVER_DELL_ESITO = Path(__file__).resolve().parent / "asdlc_esito.py"
RUOLI = ("builder", "critic")

# Le tre soglie: sezione `[soglie]` di `asdlc.toml`, in `configura()`. Il TOML porta
# il numero; la ragione di ognuno sta lì accanto, dove chi lo cambia la legge.
MAX_TENTATIVI: int
MAX_IGIENE: int
MAX_REVISIONI: int
# E i tetti di una chiamata a un agente, in minuti: `[soglie].minuti_builder` e
# `[soglie].minuti_critic` (PBI-369).
MINUTI_BUILDER: float
MINUTI_CRITIC: float

# Gli stati dopo i quali non si prosegue. `sospeso` sta qui insieme a `fermato`
# per la stessa ragione — sono tutti e due «fermo su una domanda» — e la domanda
# aperta è precisamente ciò che non si supera andando avanti. `senza esito` ci sta
# per un'altra ragione: se l'ha causato il limite d'uso, colpirebbe anche il PBI
# dopo, e una catena di `senza esito` consumerebbe la coda senza fare niente
# (PBI-367, decisione 10). Come gli altri, pubblica il ramo anche vuoto: è il
# segno su `origin` che il tick legge per non rilanciare il PBI.
# ⚠️ `respinto` non è assegnato da nessuna parte: PBI-102 lo ha sostituito con
# `non convergente` sul caso «revisioni esaurite», e la diagnosi che gli resterebbe —
# *il PBI non era pronto a partire*, riconosciuta al primo giro invece che all'ultimo —
# è il segnale che quel PBI ha proposto e rinviato (`BLOCCANTI: n`). Sta qui e non si
# toglie perché è un'intenzione, non codice morto: cancellarlo perderebbe la distinzione
# che PBI-102 ha introdotto, e chi legge `runs/tempi.csv` deve sapere che quello stato
# esiste e che nessuna run lo porta ancora.
STATI_CHE_INTERROMPONO = ("rosso", "respinto", "non convergente", "fermato", "sospeso",
                          "senza esito")

COLONNE_CSV = [
    "run", "pbi", "stato", "iniziato", "finito", "durata_s", "durata_hms",
    "builder_s", "gate_s", "critic_s", "tentativi", "revisioni", "commit", "pr", "nota",
]


# Un gate è quello di `asdlc.toml`: nome, comando, `cwd` relativa a `REPO`, e
# `solo_se_tocca` — i percorsi che lo accendono (`acceso()`).
Gate = asdlc_config.Gate


# I gate li dichiara `asdlc.toml`, sezione `[[gate]]`: pytest da `backend`, poi
# tsc, eslint e vitest da `frontend`. Niente e2e: `npm run e2e` da un worktree
# punta a localhost:8081, che è lo stack del checkout principale — cioè `main`,
# non il branch che si sta costruendo. Lo stack andrebbe rialzato a ogni giro
# del Builder, e questo non lo fa. Gli E2E li fa la CI sulla PR, che lo stack lo
# costruisce dal branch (`ADR-0009`, difetto 13 di PBI-102).
GATE: list[Gate] = []


def configura(cfg: asdlc_config.Config) -> None:
    """Le costanti di modulo, dalla configurazione. Si chiama una volta,
    all'import, e i test la richiamano con un `asdlc.toml` di prova.

    Restano **nomi di modulo** e non attributi di un oggetto: 36 punti dei test
    fanno `monkeypatch.setattr(runner, …)` su queste costanti, e spostarle
    dentro un oggetto costruito in `main()` li romperebbe tutti (PBI-358,
    decisione 1). Il guadagno — un posto solo — è lo stesso.
    """
    global CFG, GATE, LOG_DIR, CSV_TEMPI, BACKLOG, VENV, PRESTITI
    global MAX_TENTATIVI, MAX_IGIENE, MAX_REVISIONI, MINUTI_BUILDER, MINUTI_CRITIC
    global BASE, REMOTO, RAMO_PRINCIPALE, PROMPT_CRITIC, PROMPT_RIMEDIO
    global GATE_DEL_ROSSO_ATTIVO
    CFG = cfg
    GATE = list(cfg.gate)
    # `false` spegne la seconda domanda del Quality Gate — e il giro lo scrive.
    GATE_DEL_ROSSO_ATTIVO = cfg.gate_del_rosso.attivo

    # Il ramo di base: da dove nasce ogni branch, e contro cui misurano il conteggio
    # dei commit, il gate del rosso e il diff che il Critic legge.
    BASE, REMOTO, RAMO_PRINCIPALE = cfg.git.base, cfg.git.remoto, cfg.git.ramo
    # I prompt che nominano il ramo lo prendono da qui, e non da una riga scritta a
    # mano: un prompt che dice all'agente un ramo diverso da quello su cui il gate
    # misura è una bugia che costa un giro. `{pbi_path}` e `{rapporto}` restano a
    # chi chiama, che li riempie a ogni giro.
    PROMPT_CRITIC = MODELLO_CRITIC.format(base=BASE, pbi_path="{pbi_path}")
    PROMPT_RIMEDIO = MODELLO_RIMEDIO.format(base=BASE, pbi_path="{pbi_path}",
                                            rapporto="{rapporto}")

    # Il registro dei giri: i rapporti, i log, i prompt, il lucchetto, e il CSV
    # dei tempi su cui si fattura. Relativo a `REPO`, come ogni percorso del TOML.
    LOG_DIR = REPO / cfg.registro.cartella
    CSV_TEMPI = LOG_DIR / cfg.registro.tempi
    # La cartella dei PBI, che `trova_pbi` chiede al ramo di base.
    BACKLOG = cfg.backlog.cartella
    # Il venv da mettere sul PATH prima dei gate (`venv_sul_path`), relativo a `REPO`.
    VENV = cfg.ambiente.venv
    # Ciò che il worktree usa e getta non ha perché è gitignored, e senza cui i test
    # non girano: si presta dall'albero del giro con un link. `data/` è il foglio
    # vero, che la CI non ha e questa macchina sì; `node_modules` è mezzo minuto di
    # `npm ci` per ogni commit da guardare. Sono le dipendenze di **oggi** e non
    # quelle di quel commit: se un test di allora chiedesse un pacchetto che oggi
    # non c'è più, il gate lo leggerebbe come rosso — che è il verso giusto in cui
    # sbagliare.
    PRESTITI = cfg.ambiente.prestiti

    # Gate rossi: oltre, il problema non è che l'agente non ci ha provato.
    MAX_TENTATIVI = cfg.soglie.tentativi
    # Giri spesi a **chiedere un commit**, contati a parte. Non sono la stessa cosa
    # di un gate rosso — quello è «hai sbagliato una riga», questo è «il lavoro c'è
    # ma non è durevole» — e sommarli è costato a PBI-208 tutti e tre i tentativi
    # senza che un gate girasse mai: `git commit -am` non prende i file non
    # tracciati, e la pagina che l'agente aveva scritto è rimasta fuori da ogni
    # commit. Un tetto ci vuole lo stesso: un Builder che non riesce a committare
    # non migliora girando, e senza numero girerebbe finché non finisce la notte.
    MAX_IGIENE = cfg.soglie.igiene
    # Backstop, non criterio. Il criterio giusto è «smetti quando un giro non
    # produce più niente di bloccante», e il Critic quel segnale lo emette già da
    # sé — distingue una violazione da un «non è una violazione, ma va detto». È il
    # runner a non leggerlo (PBI-102). Finché non lo legge, serve un numero, e
    # questo è tarato su una misura: PBI-201 ha richiesto sei revisioni, e i due
    # difetti peggiori — il criterio centrale che si skippava su ogni runner, una
    # decisione autocertificata da chi ne beneficiava — sono usciti al quarto e al
    # quinto giro. Con 2 il runner avrebbe chiuso prima di vederli, dichiarando
    # «il PBI non era pronto»: vero e fuorviante insieme.
    MAX_REVISIONI = cfg.soglie.revisioni
    # Il tetto di una chiamata, per ruolo: la ragione dei due valori sta nel TOML.
    MINUTI_BUILDER = cfg.soglie.minuti_builder
    MINUTI_CRITIC = cfg.soglie.minuti_critic


PROMPT_BUILDER = """Sei l'ingegnere di questo repository. Lavori in ASDLC: la spec è lo stato, il PBI è il delta.

Leggi, in quest'ordine:
1. AGENTS.md — confini di giudizio e toolchain
2. {pbi_path} — il PBI da eseguire: direttiva, scope, verifica, protocollo di rifinitura
3. le spec e gli ADR che il PBI cita — sono puntatori, non decorazione

Esegui il PBI con queste regole non negoziabili:

- **TDD, e il permesso di scrivere codice te lo dà il rosso.** Il giro nasce in fase
  `TEST_ONLY`: i file di produzione sono in **sola lettura**, e ogni tentativo di
  scriverli viene bloccato — da qualunque strumento, `Edit`, `Write` o una scrittura da
  shell. Il ciclo di ogni comportamento è questo, e non ha scorciatoie:
  1. scrivi il test del comportamento che ti serve, **solo quello**;
  2. **committalo**, da solo: `test(scope): … (RED)`. Un commit di soli test, senza una
     riga di produzione dentro — il rosso non può essere esistito in mezzo a un commit
     misto, e il gate lo ferma dal solo diff;
  3. `python3 tools/asdlc_runner.py --chiedi-impl` — rigira quei test e apre la fase
     `IMPL` **solo se li vede fallire**. Se passano, quel comportamento c'è già e non è
     questo il commit in cui nasce: non insistere, vai a vedere cosa lo copre;
  4. scrivi **solo il codice** che li fa passare. Non il resto del PBI, non il criterio
     successivo per quanto ti sia già chiaro: ciò che scrivi adesso senza un rosso
     davanti non potrai più dimostrarlo, e il criterio dopo ha diritto al suo ciclo;
  5. committa il `feat` o il `fix`, di sola produzione — il commit riporta il giro in
     `TEST_ONLY`, e si ricomincia dal punto 1 col criterio dopo. **I commenti che quel
     cambiamento rende falsi si correggono in questo stesso commit**: una frase che dice
     ancora dove stava una casella spostata non ha comportamento, nessun test la può
     nominare, e chiusa la produzione non c'è più un rosso che riapra quel file — il
     giro 4 di PBI-335 (03/09/2026) si è fermato lì. Prima di committare, cerca nei
     file dello Scope le righe che parlano di ciò che hai spostato o tolto.
  In fase `IMPL` sono i **test** a essere in sola lettura: il verde si ottiene scrivendo
  il codice, mai ammorbidendo l'asserzione. Se un test è davvero sbagliato, fermati e
  dillo con lo strumento `fermati`.
- **Un modulo nuovo nasce vuoto, in un commit suo.** Il primo test di un file che non
  esiste non fallisce: esplode in raccolta, e un errore di import non è un rosso — non
  dimostra che il test morde, e `--chiedi-impl` lo rifiuta dicendolo. Fai prima lo
  **scheletro** che compila e non fa niente — il componente che rende un contenitore
  vuoto, la funzione che torna `None` — committalo, e da lì ogni rosso è un'asserzione
  che fallisce. Uno scheletro generoso però si ritorce contro di te: se fa già quello
  che il test chiede, il test passa e la fase non si apre.
- **Micro-commit**: una coppia RED→GREEN **per criterio** della checklist del PBI. Un
  PBI da otto criteri fa sedici commit, ed è giusto così — i commit sono i punti di
  ripristino, e uno solo non ripristina niente. **Non fare squash**: al merge ci pensa
  la PR.
- **Il messaggio di commit si legge senza il diff sotto gli occhi.** Formato
  `tipo(scope): descrizione imperativa` in italiano, corpo con i dettagli. Il soggetto dice
  **cosa cambia**, con un verbo e un oggetto concreti; il corpo dice **perché**, e cosa
  succedeva prima. Chi legge `git log` fra sei mesi non ha il contesto che hai adesso.
  - sì:  `feat(officina): aggiungi la casella netto/lordo alla riga di ricambio`
  - no:  `test(officina): il «no» che il default ripropone è fissato, e la spec lo dice`
  Vietate le frasi allusive, le metafore, le personificazioni («la riga sa», «il default
  cede») e i messaggi che si capiscono solo avendo già letto il codice. Se il soggetto non
  regge la prova «un estraneo capisce cosa è cambiato?», riscrivilo.
- **Un commit RED lo dichiara**, e dice quale comportamento sta fissando:
  `test(marginalita): il ricambio lordo entra nel costo maggiorato dell'IVA (RED)`.
- **Una restrizione si guadagna in due coppie RED→GREEN, non in una.** Un test che
  asserisce un'**assenza** — `not.toContain(…)`, `assert x not in …`, il 403 che deve
  arrivare — è verde per costruzione finché ciò che nega non esiste ancora. Scritto nel RED
  della cosa che non c'è, non può fallire, quindi non dimostra niente e il gate del rosso
  ferma il giro. L'ordine in cui invece morde è uno solo:
  (1) fai esistere la cosa nel modo più semplice, **senza** la restrizione — il test della
  presenza passa; (2) **poi** scrivi il test dell'assenza, che ora è **rosso** perché la
  restrizione non c'è; (3) aggiungi la restrizione, che lo fa passare. Il commit intermedio
  in cui la cosa è visibile a chi non deve vederla vive dentro il branch e non si
  distribuisce: è il prezzo di una prova che vale.
- **Una guardia nasce verde, e passa solo se morde.** Il test che presidia un comportamento
  che c'è già — quello che il Critic ti chiede quando «nessun test lo presidia» — non può
  essere rosso, e va scritto lo stesso: si committa da solo, in `TEST_ONLY`, senza
  `--chiedi-impl`. Il gate lo rigira contro i **mutanti** delle righe che il branch ha
  cambiato — la riga cancellata, `===` che diventa `!==`, `&&` che diventa `||` — e lo
  lascia passare solo se almeno uno lo fa fallire. Una guardia che non guarda quelle
  righe — un'asserzione vera comunque, un dato costruito perché il guasto non si veda —
  ferma il giro come un nato verde qualsiasi.
- Resta dentro lo **scope** dichiarato dal PBI. Se ti serve toccare altro, fermati e dillo.
- Se il PBI cambia un contratto, aggiorna la spec NELLO STESSO commit del codice.
- Non lasciare modifiche non committate: ciò che non è committato non esiste.
- Non toccare .github/workflows/ (il push verrebbe rifiutato dal token).
- **Dipendenze mancanti: installa, non modificare l'ambiente.** Se vedi errori come
  "Failed to resolve import X", "ModuleNotFoundError", "Cannot find module":
  1. Verifica se X è in `package.json` o `requirements.txt`
  2. Se c'è ma manca in `node_modules`/`.venv`: esegui `npm install` o `pip install -r requirements.txt`
  3. Se non c'è E serve al PBI: aggiungilo al file delle dipendenze e installa
  **NON modificare MAI** per "far passare i test": `conftest.py`, `vite.config.ts`,
  `pytest.ini`, `tsconfig.json`, `eslint.config.js`. Il problema è l'ambiente (dipendenze
  non installate), non la configurazione. **NON cambiare il test environment**
  (es. jsdom→happy-dom) per errori di dipendenze.
- **Non bypassare i gate con trucchi.** Vietato:
  - `--no-verify` per saltare i pre-commit hook
  - Modificare `PATH` o altre variabili d'ambiente nei file di test
  - Aggiungere fixture che manipolano `os.environ` per "far funzionare" i test
  - Disattivare test, marcare `skip`, allargare tolleranze per far passare il gate
  - Modificare asserzioni per renderle meno stringenti
  Se un gate è rosso, la causa è nel **codice di dominio**, non nell'infrastruttura di
  test. L'unica eccezione: se il gate fallisce per un bug nel gate stesso, chiama
  `fermati` con la diagnosi.
- **Non pubblicare niente**: nessun `git push`, nessun `gh pr create`. Al branch e alla PR
  ci pensa il runner, quando il Critic ha finito. Un branch pushato a metà giro è una
  promessa fatta su lavoro che nessuno ha ancora accettato — su PBI-324 quella promessa è
  stata riscossa con un merge, e in `main` è entrato un terzo del lavoro con la sua
  checklist spuntata.

Se incontri un'ambiguità che il protocollo di rifinitura non copre, NON scegliere in
silenzio: chiama lo strumento `fermati` con la domanda, per intero.

Quando hai finito, chiama lo strumento `fatto` con il riepilogo del lavoro.

L'esito il runner lo legge **solo** da una di queste due chiamate, e la prima valida è
definitiva: il testo della tua risposta resta per le persone e non decide niente. Una
risposta che non chiama né `fatto` né `fermati` chiude il giro senza esito.
"""

PROMPT_IGIENE = """Ci sono modifiche non committate:

{sporco}

Committale con micro-commit coerenti. **`git add` esplicito**, o `git add -A`: i file nuovi
non sono tracciati, e `git commit -am` li lascia fuori senza dire niente — è così che una
pagina intera è rimasta a un `git add` dal non esistere. Finché l'albero è sporco il lavoro
non è giudicabile e i gate non partono. Poi chiama `fatto`, oppure `fermati` con la
domanda, come prima.
"""

PROMPT_RIPROVA = """I gate sono rossi. Output (troncato):

{esiti}

Correggi la causa, non il sintomo: se un test è sbagliato lo si corregge, se è giusto si
corregge il codice. Non disattivare test, non marcare skip, non allargare tolleranze.
Committa la correzione con un commit suo. Poi chiama `fatto`, oppure `fermati` con la
domanda, come prima.
"""

# I due prompt che nominano il ramo di base sono **modelli**: `PROMPT_CRITIC` e
# `PROMPT_RIMEDIO` nascono in `configura()`, col ramo di `asdlc.toml` al posto di
# `{base}` e `{pbi_path}` / `{rapporto}` lasciati a chi chiama.
MODELLO_CRITIC = """Sei un **Critic Agent** e fai una revisione avversariale secondo ASDLC.

Il tuo ruolo è scettico per costruzione: respingi il codice che viola la spec o i confini
di AGENTS.md **anche se funziona e anche se i test passano**. Preferisci un falso positivo
a un falso negativo. Non sei qui per essere utile: sei qui per trovare ciò che è sfuggito.

## Contratti da caricare
- `AGENTS.md` — i confini di giudizio (la costituzione di questo repository)
- `{pbi_path}` — direttiva, **scope**, criteri di verifica
- le spec e gli ADR che il PBI cita

## Artefatto da giudicare
Il diff del branch corrente: `git diff {base}...HEAD`
I commit: `git log --oneline {base}..HEAD`

## Cosa controllare, in quest'ordine
1. **Criteri di verifica del PBI**: uno per uno, spuntato o no.
2. **Scope**: file toccati fuori da quelli dichiarati?
3. **Contratti della spec**: gli scenari Gherkin sono coperti da test veri? Le guardie di
   regressione reggono ancora?
4. **Confini di AGENTS.md**: numeri calcolati dall'LLM, hard-block introdotti, dati reali
   entrati nel repository, transizioni senza timbro.
5. **Qualità dei test**: un test che passerebbe anche con il codice rotto è un test rosso
   travestito. Verifica che ci sia stato un RED prima del GREEN (guarda i commit).
6. **Igiene dei commit**: micro-commit veri o un unico commit finale? La spec è stata
   aggiornata nello stesso commit del codice che ne cambia il comportamento? E i
   **messaggi**: leggi `git log --oneline` come se il diff non ce l'avessi. Un soggetto
   che allude invece di dire cosa è cambiato è un rilievo da chiudere con un rebase dei
   messaggi, non una questione di gusto.

## Come si dichiara l'esito
Il runner legge l'esito **solo** dalla tua chiamata a uno dei due strumenti, e la prima
chiamata valida è definitiva: il testo della risposta non decide niente.

Chiama `fatto` con il verdetto e con il rapporto intero nel riepilogo: è l'unico testo
che arriva al Builder e a chi mergia.

- Se non ci sono violazioni, il verdetto è `pass`.
- Altrimenti elenca nel rapporto ogni violazione come

      **N. [categoria]: descrizione breve**
      - Violato: <clausola della spec o di AGENTS.md>
      - Impatto: <perché conta>
      - Rimedio: <come si chiude>

  e il verdetto è `non pronto`.

Se invece trovi un rilievo che **nessuna correzione può chiudere** — perché la risposta è
di una persona: una decisione di dominio, un `CHIEDI` di AGENTS.md saltato, una violazione
*ex ante* che chi l'ha commessa non può annullare — non mandare il Builder a girare a
vuoto: chiama `fermati` con la domanda per la persona, per intero. È la stessa diagnosi
che il Builder produce quando incontra un'ambiguità, raggiunta dall'altro lato.

**Un commento falso non fa `non pronto` da solo**, né in produzione né in un file di test.
Un commento non ha comportamento — nessun rosso lo produce, nessuna asserzione
cambia — e spendere un giro intero, Builder e gate e Critic, per una frase è un giro
buttato ovunque quella frase stia (PBI-335, giro 4, 03/09/2026; PBI-342, giro 5,
07/09/2026, chiuso `non convergente` proprio così, con quattro giri di rilievi di
comportamento alle spalle). In produzione c'è una ragione in più, non l'unica: il
Builder in `TEST_ONLY` quel file non può nemmeno aprirlo. Segnalalo lo stesso, con file
e riga, sotto il titolo

    ## Note per chi mergia

fuori dai rilievi numerati: se è l'unica cosa che resta, il verdetto è `pass` e la nota
va nel rapporto, dove chi mergia la legge.
"""

MODELLO_RIMEDIO = """Sei l'ingegnere di questo repository. Lavori in ASDLC: la spec è lo stato, il PBI è il delta.

Un giro precedente ha scritto del codice e il Critic lo ha respinto. **La sessione è
nuova: quello che sai è solo ciò che leggi qui sotto.** Rileggi, in quest'ordine:

1. AGENTS.md — confini di giudizio e toolchain
2. {pbi_path} — il PBI: direttiva, scope, verifica, protocollo di rifinitura
3. `git log --oneline {base}..HEAD` e `git diff {base}...HEAD` — il lavoro già
   fatto, che è tuo anche se non lo ricordi: non rifarlo e non disfarlo
4. le spec e gli ADR che il PBI e il rapporto citano

Rapporto del Critic:

{rapporto}

Chiudi ogni violazione, una alla volta, con **un commit per rimedio** e lo stesso formato
del resto del PBI (`tipo(scope): descrizione imperativa`, in italiano). Valgono tutte le
regole di prima: test-first, la spec nello stesso commit del codice che ne cambia il
comportamento, niente modifiche non committate.

**Qui «test-first» vuol dire dichiarare, non riordinare.** Il codice che il rilievo
riguarda è già committato: un test scritto adesso nasce verde, e non c'è gesto che possa
renderlo rosso davvero. Spostarlo indietro nella storia lascia un albero identico e un
rosso recitato, e **non vale come rosso osservato** (deciso il 02/09/2026, misurato in
`PBI-105`): non farlo. Le due strade sono queste, e la scelta la fa il rilievo.

**Se il rilievo è che un comportamento non ha un test che lo presidia** — il codice è
giusto, manca la guardia:

- il test resta **in coda**, dove lo stai scrivendo. Si committa da solo, in `TEST_ONLY`,
  senza `--chiedi-impl`: non c'è produzione da aprire, e i test nuovi passano già;
- il messaggio lo **dichiara nato verde**, con la stessa parola che userà il gate, e dice
  su quale comportamento monta la guardia. Non spacciarlo per un `(RED)`: il gate legge
  il diff, e un rosso dichiarato che non c'è stato costa il giro;
- a dire se quel test vale non sei tu, è il gate: lo rigira contro i **mutanti** delle
  righe che il branch ha cambiato — la riga cancellata, `===` che diventa `!==`, `&&` che
  diventa `||` — e lo lascia passare solo se almeno uno lo fa fallire (`ADR-0022`);
- se non morde, il difetto è **nel test**: un'asserzione vera comunque, un dato costruito
  perché il guasto non si veda. Riscrivilo perché guardi quelle righe.

**Se il rilievo è che il codice è sbagliato**, il rosso c'è davvero e si chiede come
sempre: il `test (RED)` committato da solo, `--chiedi-impl` che apre la fase perché lo
vede fallire, e poi il `fix`. Sono **due** commit, mai uno: il rosso non può essere
esistito in mezzo a un commit solo.

**Se il rilievo è un commento falso** — una frase che manda a un posto che non c'è più —
non c'è un rosso da osservare: un commento non ha comportamento. Non recitare un rosso e
non spegnere un hook per passarci. Se sta in un file di test, correggilo in questo giro e
scrivi nel commit perché il rosso non c'era. Se sta in produzione, in `TEST_ONLY` quel
file è chiuso: se nel giro apri `IMPL` per un rilievo vero sullo stesso file la correzione
viaggia dentro quel `fix`; altrimenti lascia il rilievo aperto e nomina file e riga nella
risposta, e lo corregge chi mergia (PBI-104, 03/09/2026).

Se il rosso non si ottiene in nessuno di questi modi, **non** riscrivere la storia per
nasconderlo: scrivi nel commit perché non era osservabile e lascialo vedere.

**Un rilievo non si chiude spegnendo ciò che lo ha trovato.** Cancellare un test, allargare
una tolleranza o aggiungere uno `skip` fa passare il gate e disfa la cosa che il gate
proteggeva: se una violazione si chiude solo così, non è una violazione da chiudere ed è il
caso qui sotto.

Se ritieni che una violazione sia infondata, NON ignorarla: spiega perché nella risposta e
lasciala aperta. Poi chiama `fatto` con il riepilogo, oppure `fermati` con la domanda:
l'esito il runner lo legge solo da quella chiamata, non dal testo della risposta.
"""

PROMPT_CRITIC: str   # `MODELLO_CRITIC` col ramo di base dentro, da `configura()`
PROMPT_RIMEDIO: str  # idem, da `MODELLO_RIMEDIO`

# `asdlc.toml` è obbligatorio, e un file che manca o non si legge ferma qui con
# un messaggio e non con un traceback: lo legge chi ha appena perso l'uso di
# `git commit`, perché il `pre-commit` esegue questo file a ogni commit. Sta
# dopo i modelli dei prompt perché li riempie.
try:
    configura(asdlc_config.carica(REPO))
except asdlc_config.ErroreDiConfigurazione as guasto:
    sys.exit(f"asdlc_runner: {guasto}")


@dataclass
class Verdetto:
    """Cosa ha detto il Critic. Tre esiti, non due — più `senza esito`, che è
    il Critic che non ha detto niente.

    ``non pronto`` e ``sospeso`` sembrano vicini e sono opposti: il primo dice
    «c'è del lavoro da fare», il secondo «il lavoro non può proseguire finché
    qualcuno non risponde». Confonderli manda il Builder a correggere ciò che
    nessuna correzione chiude — su PBI-203 sono stati quattro giri buttati.
    """

    esito: str  # pass | non pronto | sospeso | senza esito
    domanda: str  # valorizzata solo su `sospeso`
    rapporto: str
    registro: dict | None = None  # la voce dell'invocazione, come `Invocazione.registro`


@dataclass
class Esito:
    pbi: str
    # fatto | rosso | respinto | non convergente | fermato | sospeso | senza esito | saltato
    #
    # `fermato` e `sospeso` sono tutti e due «aspetta una persona», e restano
    # distinti perché il rimedio è diverso: `fermato` arriva dal Builder e si
    # chiude riscrivendo il PBI che era ambiguo; `sospeso` arriva dal Critic e si
    # chiude rispondendo alla domanda. `senza esito` è l'agente, dell'uno o
    # dell'altro ruolo, che non ha fatto nessuna chiamata valida: non aspetta una
    # risposta, è un'anomalia da guardare (`ADR-0027`).
    stato: str
    tentativi: int = 0
    revisioni: int = 0
    commit: int = 0
    nota: str = ""
    pr: str = ""
    # Un puntatore per revisione del Critic, in ordine: `{"revisione", "verdetto",
    # "percorso"}`. Il testo sta intero nel file (`scrivi_rapporto_critic`), e non
    # qui: nel JSON era tagliato a 6000 caratteri e riscritto a ogni revisione, e
    # dei `NON PRONTO` che portano al `PASS` non restava niente (PBI-371).
    rapporti_critic: list[dict] = field(default_factory=list)
    # La domanda di un `fermato` del Builder o di un `sospeso` del Critic, intera:
    # nella nota le sue righe si uniscono con « / », qui restano com'erano.
    domanda: str = ""
    # Una voce per invocazione di un agente, nell'ordine: `Invocazione.registro`.
    invocazioni: list[dict] = field(default_factory=list)
    # Il Review Gate è stato saltato (`--senza-critic`). Un booleano e non una
    # frase dentro `nota`: la nota la legge una persona, questo lo legge il corpo
    # della PR, che deve dire il vero senza doverla interpretare.
    critic_saltato: bool = False
    # Un dizionario per gate caduto — `{"gate": nome, "coda": ultimo output}` — e
    # non il solo nome: il verdetto senza la ragione obbliga a rifar girare la
    # suite per sapere quale test, o ad avere ancora il Builder sotto mano
    # (difetto 14). La coda ce l'abbiamo già: `gira_gate` la restituisce.
    gate_rossi: list[dict[str, str]] = field(default_factory=list)
    # I commit in cui un test è nato senza essere mai stato rosso: `{"commit",
    # "titolo", "test", "esito", "coda"}`. Un elenco e non un booleano — la lettura
    # la fa una persona, che deve poter andare a quel commit e guardarlo.
    commit_senza_rosso: list[dict[str, str]] = field(default_factory=list)
    # I test nati verdi che il gate ha lasciato passare perché mordono: `{"commit",
    # "titolo", "test", "mutante", "tipo", "prove"}`, dove le prove sono i mutanti
    # provati fino al kill, ognuno con esito e tipo (PBI-365). Stanno nel rapporto
    # per la stessa ragione dei commit senza rosso — chi legge deve poter andare a
    # quella riga — e in più perché un passaggio senza ragione scritta è una
    # parola, e la parola qui non vale (PBI-105).
    test_che_mordono: list[dict] = field(default_factory=list)
    # Tempi: il totale è il tempo di parete del PBI, il resto ne è la scomposizione.
    iniziato: str = ""
    finito: str = ""
    durata_s: float = 0.0
    tempi: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    # Il file col traceback di un'eccezione che ha interrotto il giro: la nota ne
    # porta tipo e messaggio, e il resto sta lì (PBI-369, decisione 2).
    file_traceback: str = ""


def apri_rapporto(run: str, pbi: list[str]) -> Path:
    """Scrive il rapporto del giro **prima** di cominciare, con stato `in-corso`.

    `scrivi_tempi` gira in fondo a `main()`: fino a lì, di un giro in corso non
    esiste niente da nessuna parte. Un giro che non arriva in fondo — il
    terminale chiuso, un `kill`, una macchina che si sospende — non lascia
    traccia, e chi guarda il registro il giorno dopo vede un buco fra due orari.
    È successo a PBI-329 il 28/08: diciassette commit, la Verifica spuntata
    cinque su cinque, e nessuna riga da nessuna parte (difetto 20).

    Va nel rapporto per-run e **non** nel CSV: `runs/*.json` è gitignored, quindi
    aprire una riga qui non moltiplica i conflitti del difetto 19, che nascono
    proprio dall'appendere in coda a un file condiviso.
    """
    rapporto = LOG_DIR / f"{run}.json"
    rapporto.parent.mkdir(exist_ok=True)
    rapporto.write_text(
        json.dumps({"run": run, "stato": "in-corso",
                    "iniziato": datetime.now().isoformat(timespec="seconds"),
                    "pbi": pbi}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return rapporto


def scrivi_rapporto(run: str, esiti: list[Esito], stato: str) -> Path:
    """Il rapporto del giro con gli esiti che ci sono **finora**.

    Si riscrive dopo ogni PBI e non solo in fondo a `main()`: un `kill` a metà
    della seconda ora cancellava la prima, e con lei i rilievi del Critic dei PBI
    già chiusi, che vivevano solo in memoria (difetto 17). Riscrivere tutto il
    file ogni volta costa niente — sono kilobyte — e non lascia mai un JSON
    troncato a metà, che è ciò che un append farebbe.
    """
    rapporto = LOG_DIR / f"{run}.json"
    rapporto.parent.mkdir(exist_ok=True)
    rapporto.write_text(
        json.dumps({
            "run": run, "stato": stato,
            ("finito" if stato == "finito" else "aggiornato"):
                datetime.now().isoformat(timespec="seconds"),
            "esiti": [{k: v for k, v in e.__dict__.items() if k != "tempi"}
                      | {"tempi": dict(e.tempi)} for e in esiti],
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return rapporto


def chiudi_rapporto(run: str, esiti: list[Esito]) -> Path:
    """Riscrive il rapporto a giro finito: gli esiti, e lo stato che non è più `in-corso`."""
    return scrivi_rapporto(run, esiti, "finito")


def venv_sul_path() -> str | None:
    """Mette il `bin` del venv — `[ambiente].venv`, `backend/.venv` — in testa al
    `PATH`, se c'è e non c'è già.

    `backend/requirements.txt` è il file del runtime: `pytest` non c'è, e i gate
    girano col venv del worktree. Finora quel `PATH` andava scritto a mano prima
    di ogni lancio — `PATH=$PWD/backend/.venv/bin:$PATH python3 …` — e
    dimenticarlo dava un `pytest: command not found` che sembrava un errore del
    codice. Il difetto 21 lo ha reso una diagnosi da tre secondi; questo lo
    toglie di mezzo del tutto, che è il criterio con cui PBI-102 si chiude:
    lanciare il runner non richiede di ricordarsi niente.

    Torna il percorso aggiunto, o `None` se non c'era niente da fare — così chi
    lancia lo legge a schermo invece di doverlo dedurre.
    """
    bin_venv = REPO / VENV / "bin"
    if not bin_venv.is_dir():
        return None
    if str(bin_venv) in os.environ.get("PATH", "").split(os.pathsep):
        return None
    os.environ["PATH"] = f"{bin_venv}{os.pathsep}{os.environ.get('PATH', '')}"
    return str(bin_venv)


def acceso(g: Gate, attivi: set[str], toccati: set[str]) -> bool:
    """Se il gate gira: sempre, senza `solo_se_tocca`; con, se è fra i nomi
    accesi a prescindere o se il diff del branch tocca uno dei suoi percorsi.

    Era `Gate.solo_se`, un flag che nessuno accendeva più (`--e2e` esce prima):
    `[[gate]].solo_se_tocca` gli dà la semantica che serve davvero — un gate che
    costa e che vale solo se il branch ha toccato ciò che guarda. Il primo
    consumatore è il gate `asdlc` della Fase 2 di `SCAFFOLDING.md`.
    """
    if not g.solo_se_tocca or g.nome in attivi:
        return True
    return any(t.startswith(p) for p in g.solo_se_tocca for t in toccati)


def file_toccati() -> set[str]:
    """I file che il branch ha cambiato rispetto al ramo di base, `BASE...HEAD`
    come per i mutanti: un `main` andato avanti nel frattempo non entra."""
    return {p for p in git("diff", "--name-only", f"{BASE}...HEAD").splitlines() if p}


def gate_mancanti(attivi: set[str]) -> list[str]:
    """I gate accesi il cui comando non esiste su questa macchina.

    `backend/requirements.txt` è il file del runtime e `pytest` non c'è: un
    worktree nuovo nasce senza il gate più importante, e senza questo controllo
    lo scopre dopo mezz'ora di Builder, su un gate rosso che sembra un errore del
    codice (difetto 21). Si guardano solo i gate accesi a prescindere dal diff:
    prima del primo PBI il diff non c'è ancora, e un gate condizionato non deve
    pretendere il suo strumento su un giro che forse non lo tocca.
    """
    return [g.nome for g in GATE
            if acceso(g, attivi, set()) and shutil.which(g.comando[0]) is None]


def log_del_giro(run: str) -> Path:
    """Il log di un giro porta il nome del suo rapporto JSON.

    `runs/<run>.log` accanto a `runs/<run>.json`: sono lo stesso giro visto da due
    parti, e chi ne ha uno deve poter aprire l'altro senza cercare.
    """
    return LOG_DIR / f"{run}.log"


def va_staccato(in_primo_piano: bool, pid: int, sid: int) -> bool:
    """Se il processo deve mettersi in una sessione sua prima di cominciare.

    Due sole eccezioni al distacco: chi lo chiede esplicitamente — il debug e la
    CI, che vogliono l'output sotto gli occhi e un exit code — e chi è **già**
    leader della propria sessione, perché è stato lanciato da `setsid` o è già
    passato di qui. Staccare due volte non fa danno, ma un fork in più a ogni
    rilancio è rumore in `ps` e una riga in meno che si capisce.
    """
    return not in_primo_piano and pid != sid


def stacca(run: str) -> Path:
    """Mette il runner in una sessione sua, e il suo output in un file.

    Un giro dura un'ora: legarlo al terminale che l'ha lanciato significa che
    chiudere quella finestra butta via il lavoro a metà. È successo il 26/08 su
    PBI-322 — difetto 15 di PBI-102 — e finché il distacco lo faceva chi lancia
    (`setsid nohup … < /dev/null &`) il runner si comportava in due modi a
    seconda di come lo si chiamava.

    Il padre esce **subito** e con `os._exit`: torna la shell a chi ha lanciato,
    senza far girare gli `atexit` di un processo che non ha fatto niente. Il
    figlio prende una sessione sua con `setsid()` — da lì non ha più un terminale
    di controllo, quindi nessun SIGHUP lo raggiunge — e si riapre i tre canali:
    stdin sul vuoto, stdout e stderr in append sul log del giro.
    """
    log = log_del_giro(run)
    log.parent.mkdir(exist_ok=True)
    print(f"Staccato dalla sessione: PID del figlio in `ps`, log in {log.name}.\n"
          f"  tail -f {log.relative_to(REPO) if log.is_relative_to(REPO) else log}")
    sys.stdout.flush()

    if os.fork() > 0:
        os._exit(0)

    os.setsid()
    vuoto = os.open(os.devnull, os.O_RDONLY)
    scritto = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(vuoto, 0)
    os.dup2(scritto, 1)
    os.dup2(scritto, 2)
    return log


class AlberoOccupato(RuntimeError):
    """Qualcun altro sta già lavorando in questo worktree."""


@contextmanager
def lucchetto():
    """Un runner per volta in questo albero.

    La notte del 24→25/08 il builder del runner e un agente avviato a mano un
    minuto prima sono finiti sullo stesso `ada-run` sullo stesso branch: il
    secondo ha committato due modifiche non committate del primo, e il runner si
    è fermato accorgendosene dai file. Se n'è accorto — non gliel'ha impedito
    niente. Difetto n°9 di PBI-102.

    `flock` e non un file con dentro il PID: il lucchetto è dell'**open file
    description**, quindi il kernel lo rilascia quando il processo muore, comunque
    muoia. Un PID scritto su disco dopo un `kill -9` resta lì a bloccare il lancio
    successivo, e il rimedio — cancellarlo a mano — è esattamente il gesto che
    finisce per diventare automatico e disinnescare il controllo.

    Il percorso si compone **adesso** e non all'import: il lucchetto è uno dei
    file che il runner scrive sotto `runs/`, e deve seguire `LOG_DIR` ovunque
    vada. Congelato all'import restava indietro nel `runs/` vero anche per chi
    aveva spostato la cartella, e i test di `main()` finivano per misurare se su
    quel PC ci fosse un runner vivo.
    """
    lucchetto_qui = LOG_DIR / NOME_LUCCHETTO
    lucchetto_qui.parent.mkdir(exist_ok=True)
    fd = lucchetto_qui.open("w")
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlberoOccupato(
                f"un altro runner sta già lavorando in {REPO} ({lucchetto_qui})"
            ) from exc
        yield
    finally:
        fd.close()


def agenti_estranei(radice: Path, proc: Path = Path("/proc")) -> list[tuple[int, str]]:
    """Gli agenti che stanno già lavorando in `radice`, oltre a noi.

    Il lucchetto tiene fuori un secondo runner; questo tiene fuori il caso che è
    successo davvero, che è l'altro — una sessione avviata a mano, che un
    lucchetto del runner non lo prende e nemmeno lo guarda. L'unico segnale
    comune ai due è **dove lavorano**: `/proc/<pid>/cwd`.

    È un controllo Linux e non si scusa di esserlo: il runner gira sul PC di
    sviluppo, non è codice che va in produzione. Dove `/proc` non c'è la
    cartella non si legge e la lista esce vuota — il lucchetto resta.
    """
    radice = radice.resolve()
    nostri = {os.getpid(), os.getppid()}
    trovati: list[tuple[int, str]] = []
    try:
        cartelle = list(proc.iterdir())
    except OSError:
        return trovati

    for d in cartelle:
        if not d.name.isdigit() or int(d.name) in nostri:
            continue
        try:
            cwd = (d / "cwd").resolve()
            riga = (d / "cmdline").read_bytes()
        except OSError:
            # Un processo che finisce mentre lo leggiamo, o di un altro utente.
            continue
        if cwd != radice and radice not in cwd.parents:
            continue
        cmd = " ".join(riga.decode(errors="replace").split("\x00")).strip()
        if not any(nome in cmd for nome in AGENTI):
            continue
        trovati.append((int(d.name), cmd))
    return sorted(trovati)


def hms(secondi: float) -> str:
    s = int(round(secondi))
    return f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


@contextmanager
def misura(e: Esito, voce: str):
    """Somma il tempo di parete della fase su cui è aperto."""
    t0 = time.monotonic()
    try:
        yield
    finally:
        e.tempi[voce] += time.monotonic() - t0


def esegui(cmd: list[str], cwd: Path, timeout: int = 7200,
           flussi: tuple[Path, Path] | None = None) -> tuple[int, str]:
    """Il varco verso il mondo. Un comando che non esiste torna `127`, non alza.

    `subprocess.run` alza `FileNotFoundError`, e l'eccezione saliva fino a
    `main()`: il processo moriva col traceback, senza riga nel registro e senza
    rapporto — un `pytest` non installato spegneva la sequenza invece di essere
    il gate rosso con la diagnosi più ovvia che ci sia (difetto 11). `127` è la
    convenzione della shell per «comando non trovato», e la nota dice quale.

    Con `flussi`, stdout e stderr vanno in due file separati **mentre il comando
    gira**: nel testo reso sono concatenati, e per un agente senza esito sono ciò
    che distingue un limite d'uso da un crash della CLI (PBI-367, decisione 11).
    Scaduto il tetto, il comando si uccide e si alza `TettoSuperato` con ciò che
    i file hanno raccolto fin lì (PBI-369, decisione 4): raccolti alla fine, come
    fa `subprocess.run`, dopo un timeout non ci sarebbe niente.
    """
    try:
        if flussi is not None:
            return esegui_su_file(cmd, cwd, timeout, flussi)
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        return 127, (f"comando non eseguibile: {cmd[0]} — {exc}\n"
                     f"le dipendenze dei gate stanno in backend/requirements-dev.txt")
    return p.returncode, (p.stdout + p.stderr)


class TettoSuperato(Exception):
    """Una chiamata scaduta: il codice d'uscita del processo ucciso, e l'uscita
    parziale che i file dei flussi hanno raccolto."""

    def __init__(self, codice: int, uscita: str):
        super().__init__(f"tetto superato (codice {codice})")
        self.codice, self.uscita = codice, uscita


# I secondi fra il `SIGTERM` al gruppo di una chiamata scaduta e il `SIGKILL`.
ATTESA_DOPO_SIGTERM = 5


def esegui_su_file(cmd: list[str], cwd: Path, timeout: float,
                   flussi: tuple[Path, Path]) -> tuple[int, str]:
    """`esegui` con stdout e stderr scritti nei due file mentre il comando gira.

    Il comando parte in una sessione sua, e allo scadere si uccide il **gruppo**:
    `SIGTERM`, qualche secondo, poi `SIGKILL`. Uccidere la sola CLI lasciava vivi
    il server MCP e i test lanciati dal Builder (PBI-369, decisione 5). Sfugge
    solo un processo che si stacca da sé in una sessione nuova.
    """
    scaduto = False
    with flussi[0].open("w", encoding="utf-8") as fuori, \
            flussi[1].open("w", encoding="utf-8") as dentro:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=fuori, stderr=dentro, text=True,
                             start_new_session=True)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            scaduto = True
            uccidi_il_gruppo(p)
    uscita = (flussi[0].read_text(encoding="utf-8", errors="replace")
              + flussi[1].read_text(encoding="utf-8", errors="replace"))
    if scaduto:
        raise TettoSuperato(p.returncode, uscita)
    return p.returncode, uscita


def uccidi_il_gruppo(p: subprocess.Popen) -> None:
    """`SIGTERM` al gruppo di `p`, `ATTESA_DOPO_SIGTERM` secondi perché il capo
    esca, poi `SIGKILL` a chi del gruppo è rimasto."""
    for segnale in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(p.pid, segnale)
        except ProcessLookupError:
            break  # il gruppo non c'è più
        try:
            p.wait(timeout=ATTESA_DOPO_SIGTERM)
        except subprocess.TimeoutExpired:
            pass
    p.wait()


def file_dell_invocazione(ruolo: str) -> tuple[Path, Path]:
    """Il prompt e il file d'esito di un'invocazione, in `LOG_DIR` e con lo
    stesso prefisso: sono la stessa invocazione vista da due parti.

    Il nome si **prenota** creando il prompt con `O_EXCL` (PBI-370): i
    microsecondi non bastano a distinguere due invocazioni a pochi microsecondi
    l'una dall'altra, e due con lo stesso nome si sovrascrivono prompt e config
    mentre la seconda legge l'esito della prima. Un nome preso ne fa provare un
    altro con un suffisso (`-1`, `-2`…) prima di `_<ruolo>_`, senza toccare il
    file che c'è: i pattern di `.gitignore` restano validi."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    tentativo = 0
    while True:
        prefisso = timestamp if tentativo == 0 else f"{timestamp}-{tentativo}"
        prompt = LOG_DIR / f"{prefisso}_{ruolo}_prompt.txt"
        try:
            os.close(os.open(prompt, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            tentativo += 1
            continue
        return prompt, LOG_DIR / f"{prefisso}_{ruolo}_esito.json"


def config_del_server(ruolo: str | None, esito: Path | None) -> Path:
    """Scrive la config MCP che fa partire il server dell'esito per questa
    invocazione, accanto al suo file d'esito, e ne torna il percorso.

    Un ruolo che non è `builder` o `critic`, o un file d'esito mancante,
    sollevano `ValueError` **prima** del lancio. Il server si fermerebbe da sé
    all'avvio, ma dentro un giro quella fermata arriverebbe come un agente
    senza esito, dopo i minuti del Builder (PBI-367, decisione 4).

    Il file d'esito non si crea qui: lo crea il server alla prima chiamata
    valida, con `O_EXCL`, e un file già presente la rifiuterebbe.
    """
    if ruolo not in RUOLI:
        raise ValueError(f"ruolo {ruolo!r}: il server dell'esito conosce solo {RUOLI}")
    if esito is None:
        raise ValueError(f"il {ruolo} non ha un file d'esito in cui il server possa scrivere")
    config = esito.with_suffix(".mcp.json")
    config.write_text(json.dumps({"mcpServers": {"asdlc": {
        "command": sys.executable,
        "args": [str(SERVER_DELL_ESITO)],
        "env": {"ASDLC_RUOLO": ruolo, "ASDLC_ESITO": str(esito)},
    }}}, indent=2, ensure_ascii=False), encoding="utf-8")
    return config


class Invocazione(NamedTuple):
    """Cosa resta di un'invocazione: il codice d'uscita di `claude -p`, il suo
    testo, l'esito che il server ha scritto — `None` se l'agente non ha fatto
    nessuna chiamata valida — e la voce per `runs/<run>.json`: ruolo, codice,
    durata in secondi e i percorsi di stdout, stderr e del log delle chiamate al
    server, dove si vedono anche quelle rifiutate (PBI-367, decisioni 7 e 11). La
    durata c'è per ogni chiamata, anche scaduta: il registro somma le chiamate di
    un giro, e i tetti si rileggono da qui (PBI-369, decisione 7)."""

    codice: int
    uscita: str
    dichiarato: dict | None
    registro: dict


def esito_dichiarato(percorso: Path) -> dict | None:
    """L'esito che il server ha scritto nel file di questa invocazione, o `None`.

    È l'unica lettura dell'esito, per il Builder e per il Critic, e non ha un
    ripiego sul testo: il testo libero del modello non decide niente
    (`ADR-0027`). Prima c'erano due parser di marcatori, e ogni forma nuova
    che un modello scriveva chiedeva una regola in più (difetti 32, 34, 35 e
    36 di `PBI-102`).
    """
    try:
        return json.loads(percorso.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def una_riga(testo: str) -> str:
    """Un testo su più righe nella nota, che è una colonna di `runs/tempi.csv`:
    le righe si uniscono con « / », e non se ne perde nessuna."""
    return " / ".join(r.strip() for r in testo.splitlines() if r.strip())


def invoca_agente(ruolo: str | None, comando: list[str], prompt: Path,
                  esito: Path | None) -> Invocazione:
    """Lancia un agente con il server dell'esito accanto, e legge l'esito.

    `--mcp-config` è variadico come `--allowedTools`: lo chiude
    `--strict-mcp-config`, un flag booleano, e il prompt viene dopo. Nella
    prima prova il prompt in coda a `--mcp-config` è stato preso per un'altra
    config, e `-p` è partito senza input.

    La chiamata ha un tetto per ruolo, `MINUTI_BUILDER` o `MINUTI_CRITIC`.
    Scaduto, l'esito è `None` anche se l'agente ne aveva dichiarato uno: non ha
    finito, e il giro chiude `senza esito` (PBI-369, decisione 3). Il registro
    porta allora `tetto_minuti`, che è ciò che la nota dice.
    """
    config = config_del_server(ruolo, esito)
    fuori, dentro = Path(f"{esito}.stdout"), Path(f"{esito}.stderr")
    minuti = MINUTI_BUILDER if ruolo == "builder" else MINUTI_CRITIC
    scaduto = False
    t0 = time.monotonic()
    try:
        codice, uscita = esegui(comando + ["--mcp-config", str(config), "--strict-mcp-config",
                                           f"@{prompt}"], REPO, timeout=minuti * 60,
                                flussi=(fuori, dentro))
    except TettoSuperato as tetto:
        codice, uscita, scaduto = tetto.codice, tetto.uscita, True
    registro = {"ruolo": ruolo, "codice": codice,
                "durata_s": round(time.monotonic() - t0, 1), "stdout": str(fuori),
                "stderr": str(dentro), "chiamate": f"{esito}.chiamate.jsonl"}
    if scaduto:
        registro["tetto_minuti"] = minuti
    dichiarato = None if scaduto else esito_dichiarato(esito)
    return Invocazione(codice, uscita, dichiarato, registro)


def nota_senza_esito(registro: dict) -> str:
    """La nota di un `senza esito`: chi non ha chiamato, o chi è scaduto, e dove
    guardare."""
    if "tetto_minuti" in registro:
        chi = f"tetto di {registro['tetto_minuti']:g} minuti superato ({registro['ruolo']})"
    else:
        chi = f"il {registro['ruolo']} non ha chiamato né fatto né fermati"
    return (f"{chi} · "
            f"codice d'uscita {registro['codice']} · stdout {registro['stdout']} · "
            f"stderr {registro['stderr']}")


def git(*args: str) -> str:
    code, out = esegui(["git", *args], REPO, timeout=120)
    if code != 0:
        raise RuntimeError(f"git {' '.join(args)} → {out}")
    return out.strip()


def gira_gate(attivi: set[str]) -> list[tuple[str, str]]:
    """Gate rossi con la coda del loro output. Lista vuota = tutto verde.

    `attivi` sono i nomi dei gate accesi a prescindere dal diff — oggi nessuno.
    Il diff si chiede a git solo se un gate ha `solo_se_tocca`: gli altri non
    ne hanno bisogno, e un `git diff` a vuoto è una chiamata in più da finta.
    """
    rossi: list[tuple[str, str]] = []
    toccati = file_toccati() if any(g.solo_se_tocca for g in GATE) else set()
    for g in GATE:
        if not acceso(g, attivi, toccati):
            continue
        print(f"    gate {g.nome} … ", end="", flush=True)
        t0 = time.monotonic()
        code, out = esegui(g.comando, REPO / g.cwd, timeout=3600)
        print(f"{'verde' if code == 0 else 'ROSSO'} ({hms(time.monotonic() - t0)})")
        if code != 0:
            rossi.append((g.nome, out[-3000:]))
    return rossi


# --- Il gate del rosso: quei test sono mai stati rossi? ----------------------
#
# La seconda domanda del Quality Gate (PBI-103). La prima — *i test passano?* — la
# risponde `gira_gate`; questa chiede se quei test hanno **mai** avuto un momento in
# cui erano rossi. Un test nato verde non prova niente: può essere verde perché il
# codice è giusto, o perché non guarda niente. Il RED del ciclo TDD è la prova
# gratuita che il test morde, ed è per questo che `AGENTS.md` lo mette fra i SEMPRE.
#
# Dichiararlo non basta: due volte su due in tre giorni — `aa40167` (PBI-328, pagina
# e test nello stesso commit) e `e6a394f` → `f35abd1` (PBI-330, il `feat` e i suoi
# test dopo) — il divieto scritto non ha fermato niente, perché una frase in un
# prompt è un consiglio che l'agente pesa insieme agli altri. I gate sono l'unica
# cosa che lega.

# I file che sono **codice**. Un `.md` non c'è dentro: la spec si aggiorna nello
# stesso commit del codice che ne cambia il comportamento (`AGENTS.md`, SEMPRE), e
# contarla come produzione fermerebbe ogni commit di soli test con la sua spec.
ESTENSIONI_CODICE = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sql", ".sh"}

RE_TEST_PY = re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)\s*\(")
# `it('…')`, `test("…")`, e le loro varianti `.each` / `.skip`: il nome è ciò che
# vitest filtra con `-t`. Un apice **scappato** non chiude la stringa —
# `(?:\\.|[^\\])+?` mangia il `\'` invece di fermarcisi — o di `it('l\'officina…')`
# si leggerebbe `l\`, che non è il titolo di nessun test.
RE_TEST_JS = re.compile(r"""^\s*(?:it|test)(?:\.\w+)?\s*\(\s*(['"`])((?:\\.|[^\\])+?)\1""")

# Gli escape che JavaScript valuta dentro una stringa: `\u2019` e `\u{1f600}`,
# `\xe8`, i sette con la lettera, e `\<qualsiasi altro>` che vale il carattere
# stesso — è la forma di `\'` e di `\\`.
RE_ESCAPE_JS = re.compile(
    r"\\(?:u\{([0-9a-fA-F]{1,6})\}|u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2})|(.))")
ESCAPE_CON_LETTERA = {"n": "\n", "t": "\t", "r": "\r",
                      "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


def decodifica_escape(titolo: str) -> str:
    """Il titolo com'è **a runtime**, dal titolo com'è scritto nel sorgente.

    Il gate legge i nomi dal testo del file, ma li usa in due posti dove il titolo è
    già valutato: il filtro `-t`, che vitest matcha sul titolo vero, e la chiave con
    cui si rilegge il json del rapporto. Senza questo passaggio ogni test il cui
    titolo contiene un apostrofo tipografico scritto `\u2019` — la forma che il
    linter del frontend impone — non matcha niente: zero test girati, `nessuno`, e
    il gate ferma un ciclo TDD fatto bene.

    Non si usa `unicode_escape`: decodifica in latin-1 e trasformerebbe in mojibake
    le lettere accentate che nel sorgente stanno già in chiaro, che qui sono la norma.
    """
    def uno(trovato: re.Match[str]) -> str:
        graffe, u, x, semplice = trovato.groups()
        punto = graffe or u or x
        if punto is not None:
            return chr(int(punto, 16))
        return ESCAPE_CON_LETTERA.get(semplice, semplice)

    return RE_ESCAPE_JS.sub(uno, titolo)


@dataclass(frozen=True)
class TestNuovo:
    """Un test che **nasce** in un commit: dove sta, come si chiama, chi lo esegue."""

    file: str       # dalla radice del repository
    nome: str       # la funzione (python) o il titolo (vitest)
    linguaggio: str  # python | vitest


# I nomi che vitest esegue per default (`**/*.{test,spec}.?(c|m)[jt]s?(x)`). Una
# lista sola, e non due: quando `e_file_di_test` conosceva anche i `.spec.*` e
# `linguaggio_del_test` no, un `Foo.spec.tsx` non era né produzione né portatore di
# test nuovi, e il commit che lo portava insieme alla pagina usciva dal gate in
# silenzio. Chi decide cosa è un test e chi lo sa eseguire devono leggere la stessa
# riga, o tornano a divergere.
SUFFISSI_VITEST = (".test.ts", ".test.tsx", ".test.js", ".test.jsx",
                   ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx")


def e_file_di_test(percorso: str) -> bool:
    parti = Path(percorso).parts
    nome = Path(percorso).name
    if "tests" in parti or "__tests__" in parti:
        return True
    if nome.endswith(SUFFISSI_VITEST):
        return True
    return (nome.startswith("test_") and nome.endswith(".py")) or nome.endswith("_test.py")


def e_file_di_produzione(percorso: str) -> bool:
    """Codice che non è un test. È la metà del criterio che ferma PBI-328."""
    return not e_file_di_test(percorso) and Path(percorso).suffix in ESTENSIONI_CODICE


# --- Il lucchetto ex ante: la fase dice cosa si può scrivere ----------------
#
# Il gate del rosso guarda **dopo**: a giro finito dice quali test sono nati
# verdi, quando l'ora è spesa e il ciclo mancato non si annulla. Su PBI-333 sono
# stati due giri e 49 minuti per due fermate, e in mezzo il Builder aveva scritto
# 494 righe di pagina con dentro un comportamento che nessun test gli aveva
# chiesto — il test nato verde era solo la ricevuta di quell'anticipo.
#
# La stessa regola messa **prima** della scrittura non accerta: impedisce. Le due
# fasi sono i due imbrogli simmetrici, e ognuna chiude il suo:
#
#   TEST_ONLY   la produzione è chiusa → non si implementa ciò che nessun rosso
#               ha chiesto, che è la causa a monte
#   IMPL        i test sono in sola lettura → il verde non si ottiene
#               ammorbidendo l'asserzione, che è la scorciatoia dell'altro verso
#
# Chi apre il passaggio non è l'agente: è `--chiedi-impl`, che gira i test nuovi
# e scrive `IMPL` solo se li vede fallire **per asserzione**. L'agente può
# chiedere il permesso, non prenderselo — per questo il file della fase è
# protetto in tutte e due le fasi.
#
# Fuori da un giro il file non c'è e la guardia tace: `.claude/settings.json` sta
# nel repository e l'hook vale per ogni sessione, comprese quelle di una persona.
#
# Il file sta nel **git dir del worktree** (`git rev-parse --git-path asdlc-fase`,
# cioè `.git/worktrees/<nome>/asdlc-fase`), non nella radice dell'albero. Quando
# stava lì, era protetto da `Edit` e `Write` ma non da un `rm` o da un `git clean
# -fdx` via Bash: nei due giri del 01/09 è sparito a metà, e da lì hook e
# `pre-commit` sono stati inerti in silenzio. Dove sta ora l'albero di lavoro non
# arriva, e ogni worktree ha il suo: la fase di `~/ada-run` non si accende
# nell'albero accanto.

FILE_DELLA_FASE = "asdlc-fase"
FASE_TEST_ONLY = "TEST_ONLY"
FASE_IMPL = "IMPL"


def percorso_della_fase(cartella: Path) -> Path | None:
    """Dove sta la fase per l'albero che contiene `cartella`, o `None` se non c'è
    un repository sotto — e allora non si scrive da nessuna parte."""
    try:
        detto = git("-C", str(cartella), "rev-parse", "--git-path", FILE_DELLA_FASE)
    except RuntimeError:
        return None
    if not detto or Path(detto).name != FILE_DELLA_FASE:
        return None  # sotto i test `git` torna "", e `Path("")` è la cartella corrente
    percorso = Path(detto)
    return percorso if percorso.is_absolute() else Path(cartella) / percorso


def fase_corrente(cartella: Path) -> str | None:
    """La fase del giro dell'albero in cui sta `cartella`. `None` quando non c'è
    un giro, o un repository.

    `cwd` arriva da Claude Code così com'è, e l'agente può essersi spostato in
    `frontend/` per lanciare `npm`: a risalire fino al worktree giusto ci pensa
    git.
    """
    file = percorso_della_fase(Path(cartella))
    if file is None or not file.is_file():
        return None
    return file.read_text(encoding="utf-8").strip()


def guardia_di_fase(fase: str | None, percorso: str) -> str | None:
    """Perché questa scrittura non si fa, o `None` se si fa.

    Torna una **ragione** e non un booleano perché è ciò che l'agente legge: un
    blocco che non spiega come procedere costa il turno che avrebbe risparmiato.
    """
    if fase is None:
        return None
    if Path(percorso).name == FILE_DELLA_FASE:
        return (f"{percorso}: la fase non la decidi tu. Il passaggio a {FASE_IMPL} lo "
                f"apre `asdlc_runner.py --chiedi-impl`, e solo se i test nuovi "
                f"falliscono davvero.")
    if fase == FASE_TEST_ONLY:
        if e_file_di_produzione(percorso):
            return (f"{percorso} è codice di produzione e il giro è in {FASE_TEST_ONLY}: "
                    f"qui si scrivono solo i test. Scrivi il test del comportamento che "
                    f"ti serve, poi `asdlc_runner.py --chiedi-impl`: se è rosso, la "
                    f"produzione si apre. Se il test passa già, quel comportamento c'è "
                    f"di suo e non è questo il commit in cui nasce.")
        return None
    if fase == FASE_IMPL:
        if e_file_di_test(percorso):
            return (f"{percorso} è un test e il giro è in {FASE_IMPL}: il verde si "
                    f"ottiene scrivendo il codice, non ammorbidendo l'asserzione. "
                    f"Se il test è davvero sbagliato, non chiamare `fatto`: chiama "
                    f"`fermati` e dillo.")
        return None
    return (f"fase «{fase}» sconosciuta in {FILE_DELLA_FASE}: la guardia si chiude. "
            f"Un file scritto a metà non vale come «nessun giro in corso».")


def linguaggio_del_test(percorso: str) -> str | None:
    """Chi sa eseguire quel test, e `None` se non è il runner.

    Gli `e2e/` tornano `None` e non è una dimenticanza: `npm run e2e` da un worktree
    punta a `localhost:8081`, cioè allo stack di un altro codice, e quel gate è della
    CI sulla PR (`ADR-0009`). Un rosso che il runner non può osservare non lo può
    nemmeno pretendere.
    """
    if percorso.startswith("e2e/"):
        return None
    if percorso.endswith(".py"):
        return "python"
    if percorso.endswith(SUFFISSI_VITEST):
        return "vitest"
    return None


class VoceDiCommit(NamedTuple):
    """Un file toccato da un commit. Su un rename `percorso` è il nome nuovo e
    `vecchio` quello da cui arriva; altrove `vecchio` è `None`.

    Il nome vecchio non è decorazione: il diff di un file traslocato si chiede a
    git nominando **tutti e due** i lati, perché con un pathspec solo il rename
    detection non si applica e il file risulta interamente aggiunto.
    """

    stato: str
    percorso: str
    vecchio: str | None


def voci_del_name_status(testo: str) -> list[VoceDiCommit]:
    """Le voci di un `--name-status`, da `git show` come da `git diff`.

    Una lettura sola per il commit e per l'albero di lavoro: il lucchetto *ex
    ante* e il gate del rosso devono vedere lo stesso rename, o il primo ferma un
    trasloco che il secondo lascia passare.
    """
    voci: list[VoceDiCommit] = []
    for riga in testo.splitlines():
        campi = riga.split("\t")
        if len(campi) >= 2 and campi[0]:
            vecchio = campi[1].strip() if campi[0].startswith("R") and len(campi) >= 3 else None
            voci.append(VoceDiCommit(campi[0], campi[-1].strip(), vecchio))
    return voci


def file_del_commit(sha: str) -> list[VoceDiCommit]:
    """Le voci di ogni file toccato dal commit, rename compresi.

    `-M` è scritto nel comando e non lasciato al default: `diff.renames` è vero
    da git 2.9, ma resta configurazione della macchina, e su un repository che la
    spegne il rename tornerebbe a leggersi come un file aggiunto più uno
    cancellato — senza che nessuno se ne accorga.
    """
    return voci_del_name_status(git("show", "--format=", "--name-status", "-M", sha))


def lati_del_diff(voce: VoceDiCommit) -> list[str]:
    """I pathspec con cui chiedere il diff di questa voce.

    Il lato vecchio entra solo se da lì i test **sarebbero stati contati**: è la
    condizione esatta che il ciclo delle nascite chiede sul lato nuovo, ed è ciò
    che regge tutto il resto. Un test traslocato non nasce perché il permesso
    l'aveva già chiesto il commit che l'ha creato; un file da cui non è mai nata
    una riga non l'ha mai chiesto. Un `git mv note.txt backend/tests/test_x.py` è
    un rename al 100% di similarità — sui due lati il diff non porta righe — e
    senza questa guardia i test dentro entrerebbero nella suite con zero
    nascite: il lucchetto *ex ante* non li ferma, perché un `.txt` non è né test
    né produzione e in `TEST_ONLY` si scrive. Sarebbe l'agente esaminato a
    scegliere quali suoi test vengono esaminati.

    `e_file_di_test` da sola non basta a dirlo, e chiederle solo quella è il
    buco che il giro 2 ha lasciato aperto: dice `True` per qualunque percorso
    sotto `tests/` — `backend/tests/note.txt` compreso — e per gli `e2e/`, cioè
    per file a cui `linguaggio_del_test` torna `None` e da cui il ciclo delle
    nascite non ha mai letto un nome. Le due domande insieme sono la simmetria
    con «il permesso l'aveva già chiesto il commit che l'ha creato».

    Col solo nome nuovo git non applica il rename detection e il file risulta
    interamente aggiunto: è esattamente la lettura che serve qui.

    Una funzione sola per il commit e per l'albero di lavoro, come
    `voci_del_name_status`: due copie di questa regola divergerebbero alla prima
    correzione, e il lucchetto fermerebbe ciò che il gate lascia passare.
    """
    if (voce.vecchio and e_file_di_test(voce.vecchio)
            and linguaggio_del_test(voce.vecchio) is not None):
        return [voce.vecchio, voce.percorso]
    return [voce.percorso]


def nomi_dei_test(diff: str, linguaggio: str) -> tuple[list[str], set[str]]:
    """I nomi di test aggiunti e quelli cancellati, dalle righe del diff."""
    regola = RE_TEST_PY if linguaggio == "python" else RE_TEST_JS
    aggiunti: list[str] = []
    tolti: set[str] = set()
    for riga in diff.splitlines():
        if riga.startswith(("+++", "---")) or riga[:1] not in ("+", "-"):
            continue
        trovato = regola.match(riga[1:])
        if trovato is None:
            continue
        nome = (trovato.group(1) if linguaggio == "python"
                else decodifica_escape(trovato.group(2)))
        if riga[0] == "+":
            aggiunti.append(nome)
        else:
            tolti.add(nome)
    return aggiunti, tolti


def test_nuovi_del_commit(sha: str, file: list[VoceDiCommit] | None = None) -> list[TestNuovo]:
    """I test che **nascono** in questo commit.

    Uno stesso nome cancellato e riaggiunto è un trasloco, non una nascita: è il
    caso del file di test riscritto per intero, e senza questa sottrazione il gate
    farebbe girare tutta la suite di quel commit per poi fermarla come nata verde.

    Il diff di un rename si chiede nominando **tutti e due** i lati. Con il solo
    nome nuovo git non applica il rename detection — per riconoscere una copia
    deve vedere da dove arriva — e il file risulta interamente aggiunto: da lì il
    gate leggeva una nascita per ogni test dentro un file semplicemente spostato.
    """
    nuovi: list[TestNuovo] = []
    for voce in (file if file is not None else file_del_commit(sha)):
        percorso = voce.percorso
        linguaggio = linguaggio_del_test(percorso) if e_file_di_test(percorso) else None
        if linguaggio is None:
            continue
        aggiunti, tolti = nomi_dei_test(
            git("show", "--format=", "--unified=0", "-M", sha, "--",
                *lati_del_diff(voce)), linguaggio
        )
        nuovi += [TestNuovo(percorso, n, linguaggio) for n in aggiunti if n not in tolti]
    return nuovi


def test_nuovi_dellalbero() -> list[TestNuovo]:
    """I test che nascono nell'**albero di lavoro**, rispetto a `HEAD`.

    Il gate del rosso legge un commit; il lucchetto deve leggere ciò che non è
    ancora committato, perché il permesso di implementare si chiede **prima** del
    commit — è tutto il punto della differenza fra impedire e accertare.

    I file non tracciati si cercano a parte: `git diff HEAD` non nomina un file
    appena creato, e il primo test di un modulo nuovo è il caso più comune di
    tutti. Per quelli il diff è il file intero, che è esattamente ciò che sono.

    I tracciati si leggono da un `--name-status`, non da un `--name-only`: senza
    lo stato il `git mv` in stage arriva qui come un percorso nuovo e basta, e il
    lucchetto chiede un rosso per test che esistono già da un altro commit.
    """
    tracciati = voci_del_name_status(git("diff", "HEAD", "-M", "--name-status"))
    non_tracciati = [VoceDiCommit("A", p, None)
                     for p in git("ls-files", "--others", "--exclude-standard").splitlines() if p]
    nuovi: list[TestNuovo] = []
    for voce in tracciati + non_tracciati:
        percorso = voce.percorso
        linguaggio = linguaggio_del_test(percorso) if e_file_di_test(percorso) else None
        if linguaggio is None:
            continue
        if voce in non_tracciati:
            sorgente = leggi_sorgente(REPO / percorso) or ""
            diff = "".join(f"+{riga}\n" for riga in sorgente.splitlines())
        else:
            diff = git("diff", "HEAD", "-M", "--unified=0", "--", *lati_del_diff(voce))
        aggiunti, tolti = nomi_dei_test(diff, linguaggio)
        nuovi += [TestNuovo(percorso, n, linguaggio) for n in aggiunti if n not in tolti]
    return nuovi


# Le tre letture che **non** sono un rosso osservato, con la ragione che le
# distingue. `nato verde` e `rosso non osservabile` sono due cose diverse: la prima
# dice che il codice c'era già, la seconda che lì il rosso non si poteva vedere. Il
# PBI-103 esiste per raccogliere i casi della seconda, e confonderli li perderebbe.
ESITI_MANCATI = {
    "verde": "nato verde: a quel commit il test passa, il codice c'era già",
    "saltato": "rosso non osservabile: a quel commit il test si salta",
    "nessuno": "rosso non isolabile: a quel commit il test non gira, e il gate non indovina",
}
MISTO = ("test e produzione nello stesso commit: il rosso non può essere esistito "
         "in mezzo a un commit solo, e basta il diff per dirlo")
# Ciò che la nota del giro dice quando `[gate_del_rosso].attivo = false`: chi
# rilegge `runs/tempi.csv` deve sapere che quel giro ha avuto un gate in meno.
NOTA_ROSSO_SPENTO = "gate del rosso spento da asdlc.toml"


def commit_da_esaminare(base: str, ref: str, visti: set[str]) -> list[str]:
    """I commit del branch dal più vecchio, saltando quelli di un giro precedente."""
    fuori = git("rev-list", "--reverse", f"{base}..{ref}")
    return [sha for sha in fuori.split() if sha not in visti]


@contextmanager
def worktree_usa_e_getta(sha: str):
    """Estrae un commit **fuori** dall'albero del giro, e lo smonta comunque vada.

    Fuori e non dentro: sotto l'albero del giro c'è l'agente che lavora, e un gate
    che gli sposta i file sotto rompe il lavoro che sta giudicando. Per la stessa
    ragione la cartella sta in `/tmp` e non in `REPO`, dove sporcherebbe il
    `git status` che il controllo d'igiene legge un istante dopo.
    """
    cartella = Path(tempfile.mkdtemp(prefix="ada-rosso-"))
    albero = cartella / "albero"
    try:
        git("worktree", "add", "--detach", "--quiet", str(albero), sha)
        for prestito in PRESTITI:
            sorgente, destinazione = REPO / prestito, albero / prestito
            if sorgente.exists() and not destinazione.exists() and destinazione.parent.is_dir():
                destinazione.symlink_to(sorgente)
        yield albero
    finally:
        try:
            git("worktree", "remove", "--force", str(albero))
        except RuntimeError as exc:  # smontarlo è igiene, non è il verdetto
            print(f"    ⚠️  worktree non smontato: {str(exc)[:200]}")
        shutil.rmtree(cartella, ignore_errors=True)


def id_pytest(sorgente: str, nome: str, relativo: str) -> str | None:
    """`file::Classe::test`, letto dall'AST del file **a quel commit**.

    Prende la sorgente e non un percorso, perché il file a quel commit si legge in
    due modi: dal worktree quando c'è, e da `git show sha:percorso` quando il gate
    ferma dal solo diff e non deve estrarre niente.

    E non `-k`, che seleziona per sottostringa: `test_somma` prenderebbe anche
    `test_somma_negativa`, e il rosso di un test vicino coprirebbe quello nato
    verde. `None` quando il nome non si trova — un test generato, o dentro un `if`:
    lì il gate non indovina, ferma e lo dice.
    """
    try:
        modulo = ast.parse(sorgente)
    except (SyntaxError, ValueError):
        return None
    definizioni = (ast.FunctionDef, ast.AsyncFunctionDef)
    trovati: list[str] = []
    for nodo in modulo.body:
        if isinstance(nodo, definizioni) and nodo.name == nome:
            trovati.append(f"{relativo}::{nome}")
        if isinstance(nodo, ast.ClassDef):
            for figlio in nodo.body:
                if isinstance(figlio, definizioni) and figlio.name == nome:
                    trovati.append(f"{relativo}::{nodo.name}::{nome}")
    # Due classi che definiscono un test omonimo sono normali, e il diff dice solo
    # che *un* `def` con quel nome è nato: quale delle due, non lo dice. Prendere il
    # primo è la scelta che sembra innocua e non lo è — il gate esegue il test
    # vecchio, lo trova verde, e stampa «nato verde» su un test che era rosso.
    return trovati[0] if len(trovati) == 1 else None


def dove_gira(percorso: str) -> tuple[str, str]:
    """La cartella da cui si lancia il test, e il suo percorso da lì.

    Sono le stesse di `GATE`: `pytest` da `backend`, `npm test` da `frontend`. Un
    test isolato che girasse da un'altra parte non sarebbe più lo stesso test — e un
    id scritto col prefisso `backend/` non si riesegue da `backend/`.
    """
    for radice in ("backend", "frontend"):
        if percorso.startswith(f"{radice}/"):
            return radice, percorso[len(radice) + 1:]
    return ".", percorso


def leggi_sorgente(percorso: Path) -> str | None:
    """Il file dal worktree, o `None` se a quel commit non c'era."""
    try:
        return percorso.read_text(encoding="utf-8")
    except OSError:
        return None


def sorgente_al_commit(sha: str, percorso: str) -> str | None:
    """Il file com'era a quel commit, dall'oggetto git e **senza worktree**."""
    try:
        return git("show", f"{sha}:{percorso}")
    except RuntimeError:
        return None


def etichetta_del_test(sorgente: str | None, t: TestNuovo, relativo: str) -> str:
    """L'id con cui quel test si riesegue a mano, dalla cartella da cui si esegue.

    Quando il nome non si trova nel file non si inventa un node id: si scrive in una
    forma che non finge di esserlo. Un `file::nome` che dà «not found» fa sembrare
    sbagliato il gate invece del commit, ed è il difetto che questa regola chiude.
    """
    if t.linguaggio != "python":
        return f"{relativo} -t {t.nome}"
    nodo = id_pytest(sorgente, t.nome, relativo) if sorgente is not None else None
    return nodo if nodo is not None else f"{relativo} → {t.nome}"


def etichette_al_commit(sha: str, nuovi: list[TestNuovo]) -> list[str]:
    """Gli id dei test nuovi di un commit, letti **senza estrarne niente**.

    È l'elenco che si porta dietro il commit misto, che ferma dal solo diff e deve
    restare così: `git show` dà il file di allora, e il criterio «ferma senza girare
    i test» resta intatto. Che l'id sia eseguibile conta lì quanto altrove — anzi di
    più, perché è il ramo del gate che si legge più spesso.
    """
    etichette: list[str] = []
    for t in nuovi:
        _, relativo = dove_gira(t.file)
        etichette.append(etichetta_del_test(sorgente_al_commit(sha, t.file), t, relativo))
    return etichette


@dataclass(frozen=True)
class ComandoDiProva:
    """Un comando che gira i test nuovi di un commit, e come se ne rilegge l'esito.

    `etichette` lega la **chiave** con cui l'esito torna indietro — il node id per
    pytest, il titolo per vitest — all'id con cui quel test si riesegue a mano. Per
    pytest sono la stessa cosa; per vitest no, perché `-t` filtra per nome dentro un
    file e l'id da riscrivere è `file -t nome`.
    """

    cartella: Path
    argv: list[str]
    linguaggio: str
    etichette: dict[str, str]
    rapporto: Path | None = None  # dove vitest scrive il suo json
    # chiave → il test da cui viene: serve a rigirarlo **da solo**, quando la
    # quarta lettura lo prova contro i mutanti uno alla volta.
    origine: dict[str, TestNuovo] = field(default_factory=dict)


def comandi_dei_test(albero: Path,
                     nuovi: list[TestNuovo]) -> tuple[list[ComandoDiProva], list[str]]:
    """I comandi che eseguono **soltanto** quei test, e i test che non si isolano.

    Un comando solo per i pytest di ogni cartella — costa un avvio di interprete —
    e uno per file per vitest, perché `-t` è un filtro per nome e non un elenco. Un
    comando solo, però, non vuol dire un verdetto solo: l'esito si rilegge per test
    (`esiti_del_comando`), o dodici test in un `pytest` diventerebbero un
    tutto-o-niente.

    Le **etichette** sono ciò che finisce nell'elenco del gate, e vanno scritte come
    si eseguono — un `file::nome` senza la classe che lo contiene dà «not found» a
    chi prova a rieseguirlo, e fa sembrare sbagliato il gate.
    """
    per_pytest: dict[Path, list[str]] = {}
    per_vitest: dict[tuple[Path, str], list[str]] = {}
    orfani: list[str] = []
    origine: dict[str, TestNuovo] = {}

    for t in nuovi:
        radice, relativo = dove_gira(t.file)
        cartella = albero / radice
        sorgente = leggi_sorgente(albero / t.file)
        if t.linguaggio == "python":
            nodo = id_pytest(sorgente, t.nome, relativo) if sorgente is not None else None
            if nodo is None:
                orfani.append(etichetta_del_test(sorgente, t, relativo))
                continue
            per_pytest.setdefault(cartella, []).append(nodo)
            origine[nodo] = t
        else:
            per_vitest.setdefault((cartella, relativo), []).append(t.nome)
            origine[t.nome] = t

    # `-v` e non `-q`: il conteggio finale è una somma e non dice **quale**, mentre
    # una riga per test dice nome ed esito. `--tb=no` perché il traceback qui non
    # serve — la coda che finisce nel rapporto è la stessa per tutti. `-rf` scrive
    # in fondo, per ogni test fallito, l'eccezione che l'ha fatto fallire: è ciò
    # che separa un'asserzione mancata da un `NameError` del codice mutato. E `-vv`
    # e non `-v`, perché con `-v` pytest taglia quel messaggio alla larghezza del
    # terminale, e con un node id lungo lo toglie del tutto.
    comandi: list[ComandoDiProva] = [
        ComandoDiProva(cartella, ["pytest", "--tb=no", "-vv", "-rf", *nodi], "python",
                       {nodo: nodo for nodo in nodi},
                       origine={nodo: origine[nodo] for nodo in nodi})
        for cartella, nodi in per_pytest.items()
    ]
    # Il json di vitest va in un file e non a schermo: `npm test` ci scrive sopra la
    # sua intestazione, e ritagliare un oggetto json da un output misto è un modo di
    # sbagliare in silenzio. Il file sta accanto al worktree e se ne va con lui.
    for numero, ((cartella, relativo), nomi) in enumerate(per_vitest.items()):
        rapporto = albero.parent / f"vitest-{numero}.json"
        comandi.append(ComandoDiProva(
            cartella,
            ["npm", "test", "--", relativo, "-t", "|".join(re.escape(n) for n in nomi),
             "--reporter=json", f"--outputFile={rapporto}"],
            "vitest", {nome: f"{relativo} -t {nome}" for nome in nomi}, rapporto,
            origine={nome: origine[nome] for nome in nomi}))
    return comandi, orfani


def leggi_esito(uscita: str) -> str:
    """`rosso` | `verde` | `saltato` | `nessuno`, dai conteggi che pytest e vitest
    scrivono tutti e due come «N passed», «N failed», «N skipped».

    Un **errore** conta come rosso: il caso più comune di test-first in Python è un
    `from app.x import y` che a quel commit non esiste ancora, e leggerlo come «non
    ha girato» fermerebbe proprio il ciclo fatto bene.

    Non si guarda l'exit code: `pytest` torna 0 anche con tutto saltato, e `vitest`
    torna 1 sia per un test rosso sia per un file che non ha trovato.
    """
    conti = Counter()
    for numero, voce in re.findall(r"(\d+) (passed|failed|skipped|error)", uscita):
        conti[voce] += int(numero)
    if conti["failed"] or conti["error"]:
        return "rosso"
    if conti["passed"]:
        return "verde"
    if conti["skipped"]:
        return "saltato"
    return "nessuno"


class GuastoDelGate(RuntimeError):
    """Il gate non ha potuto guardare: è rotto lo strumento, non il ciclo del Builder.

    Sono due diagnosi opposte e vanno tenute separate. «Il rosso non si è mai visto»
    accusa chi ha scritto i commit; un `pytest` che non parte accusa il `PATH` di
    chi ha lanciato il giro, e confonderle mette il rilievo più grave che il runner
    sappia emettere su tutti i commit del branch insieme, senza che chi legge il
    rapporto possa accorgersene.
    """


# I codici con cui pytest e vitest dicono qualcosa **sui test**: 0 tutto verde, 1
# fallimenti, 2 interrotto (l'errore di raccolta), 5 nessun test raccolto. Fuori da
# qui — `127` «comando non eseguibile», `4` «riga di comando sbagliata» — a parlare
# non è stato il test: è stato il gate, e va detto così.
CODICI_DEL_TEST = {"python": {0, 1, 2, 5}, "vitest": {0, 1}}

# Le quattro letture in ordine di forza. Un test parametrizzato — o un `it.each` —
# gira più volte sotto lo stesso nome: se un caso solo è rosso, quel test un momento
# in cui mordeva ce l'ha avuto, ed è tutto ciò che il gate chiede.
ORDINE_ESITI = ("nessuno", "saltato", "verde", "rosso")

# `pytest -v` scrive una riga per test: `file::Classe::test PASSED  [ 33%]`.
RE_ESITO_PYTEST = re.compile(
    r"^(\S+::\S+) (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b", re.MULTILINE)
# `file::test[caso]` → `file::test`: l'id che il gate ha chiesto è quello della
# funzione, e un test parametrizzato ne stampa uno per caso.
RE_PARAMETRO = re.compile(r"\[.*\]$")
# `pytest -rf` riepiloga ogni fallito come `FAILED file::test - messaggio`.
RE_RIEPILOGO_PYTEST = re.compile(r"^FAILED (\S+::\S+) - (.*)$", re.MULTILINE)
# Un'asserzione del test: l'`assert` che pytest riscrive, e il `Failed` di
# `pytest.fail` e di `pytest.raises` che non vede l'eccezione attesa.
TIPI_DI_ASSERZIONE = {"AssertionError", "Failed"}


def tipo_del_fallimento(messaggio: str) -> str:
    """Il tipo dell'eccezione, dal messaggio del riepilogo di `-rf`.

    Un `assert` riscritto da pytest senza messaggio suo non porta il tipo davanti
    — il messaggio è la sua espressione, `assert 1 == 2` — e lì il tipo è
    `AssertionError`. Tutto il resto comincia col nome della classe:
    `NameError: name 'righe' is not defined`, o solo `AssertionError`.
    """
    if messaggio == "assert" or messaggio.startswith("assert "):
        return "AssertionError"
    trovato = re.match(r"[A-Za-z_][\w.]*(?=:|$)", messaggio)
    return trovato.group(0) if trovato else ""


def tipi_dei_falliti(uscita: str) -> dict[str, str]:
    """Per ogni test `FAILED` di pytest, il tipo di eccezione che l'ha fatto
    fallire, per node id e **per caso**: il riepilogo di `-rf` ne scrive una riga
    ciascuno."""
    return {nodo: tipo_del_fallimento(messaggio)
            for nodo, messaggio in RE_RIEPILOGO_PYTEST.findall(uscita)}

ESITI_DI_PYTEST = {"PASSED": "verde", "XPASS": "verde",
                   "FAILED": "rosso", "ERROR": "rosso",
                   # `xfail` è un rosso già previsto: osservato non lo si vede, e
                   # sta con lo `skip` invece che col rosso vero.
                   "SKIPPED": "saltato", "XFAIL": "saltato"}
# `pending` e `todo` sono i due modi in cui vitest dice «non l'ho eseguito».
ESITI_DI_VITEST = {"passed": "verde", "failed": "rosso",
                   "skipped": "saltato", "pending": "saltato", "todo": "saltato"}


def piu_forte(uno: str, altro: str) -> str:
    return max(uno, altro, key=ORDINE_ESITI.index)


def esiti_di_pytest(uscita: str) -> dict[str, str]:
    """Il verdetto **per test**, dalle righe di `pytest -v`, per node id."""
    letti: dict[str, str] = {}
    for nodo, esito in RE_ESITO_PYTEST.findall(uscita):
        chiave = RE_PARAMETRO.sub("", nodo)
        letti[chiave] = piu_forte(letti.get(chiave, "nessuno"),
                                  ESITI_DI_PYTEST.get(esito, "nessuno"))
    return letti


def esiti_di_vitest(rapporto: Path | None) -> dict[str, str]:
    """Il verdetto per test, dal `--reporter=json` di vitest, per titolo.

    Un rapporto che non c'è torna **vuoto** e non «tutto verde»: chi non ha letto
    niente non ha visto niente, e allora vale l'esito del comando intero.
    """
    try:
        dati = json.loads(rapporto.read_text(encoding="utf-8"))
    except (AttributeError, OSError, ValueError):
        return {}
    letti: dict[str, str] = {}
    for file in dati.get("testResults", []):
        for caso in file.get("assertionResults", []):
            chiave = caso.get("title", "")
            letti[chiave] = piu_forte(letti.get(chiave, "nessuno"),
                                      ESITI_DI_VITEST.get(caso.get("status"), "nessuno"))
    return letti


def esito_dei_file_di_vitest(rapporto: Path | None) -> str:
    """`rosso` quando un file **non si è caricato**, `nessuno` in ogni altro caso.

    È il gemello frontend dell'errore di raccolta: un `import FoglioPage from
    './FoglioPage'` che a quel commit non esiste ancora fa fallire il file **prima**
    dei test, e allora non c'è nessun `assertionResult` da leggere. In Python quel
    caso è un rosso perché `pytest` scrive `1 error` e `leggi_esito` lo conta; col
    `--reporter=json` di vitest i conteggi non sono a schermo, e senza questa lettura
    lo stesso identico ciclo TDD risulta `nessuno` e ferma il gate.

    Solo quel caso, e non lo stato del file in generale: un file `passed` con zero
    test è il filtro `-t` che non ha matchato niente, e leggerlo come verde darebbe
    per girato un test che non è mai partito — il gate passerebbe in silenzio proprio
    dove non ha guardato.
    """
    try:
        dati = json.loads(rapporto.read_text(encoding="utf-8"))
    except (AttributeError, OSError, ValueError):
        return "nessuno"
    for file in dati.get("testResults", []):
        if file.get("status") == "failed" and not file.get("assertionResults"):
            return "rosso"
    return "nessuno"


def esiti_del_comando(c: ComandoDiProva) -> tuple[dict[str, str], str]:
    """Gira il comando e torna l'esito di **ogni** test che gli era stato chiesto.

    Un errore di **raccolta** — il `from app.x import y` che a quel commit non
    esiste ancora, cioè il rosso più comune del test-first — non stampa nessuna riga
    per test: lì vale l'esito del comando intero, che è la sola cosa che si sa. In
    vitest quell'esito non è nell'output ma nel json (`esito_dei_file_di_vitest`),
    perché il `--reporter=json` porta via da schermo anche i conteggi.
    """
    try:
        codice, uscita = esegui(c.argv, c.cartella, timeout=1800)
    except subprocess.TimeoutExpired:
        # Un timeout lo dicono i test: a quel commit non terminano, e il gate non
        # indovina. Lo strumento ha girato — quindi non è un guasto.
        codice, uscita = 0, "i test non terminano a quel commit"
    letti = esiti_di_pytest(uscita) if c.linguaggio == "python" else esiti_di_vitest(c.rapporto)
    complessivo = leggi_esito(uscita)
    if c.linguaggio == "vitest" and complessivo == "nessuno":
        complessivo = esito_dei_file_di_vitest(c.rapporto)
    if complessivo == "nessuno" and codice not in CODICI_DEL_TEST[c.linguaggio]:
        raise GuastoDelGate(f"`{' '.join(c.argv)}` in {c.cartella} → uscita {codice}\n"
                            f"{uscita.strip()[-1000:]}")
    return {chiave: letti.get(chiave, complessivo) for chiave in c.etichette}, uscita


# --- La quarta lettura: il test nato verde passa se morde (PBI-105) ------------
#
# «Nato verde» è una prova di processo, e ha un falso positivo sistematico: la
# guardia che il Critic ordina su un comportamento che c'è già nasce verde per
# forza. La domanda di sostanza — *se guasto il codice che copre, se ne accorge?* —
# si misura: si mutano le righe di produzione che il branch ha cambiato e si rigira
# quel test. Un mutante ucciso è la prova che il test guarda quelle righe.

@dataclass(frozen=True)
class Mutante:
    """Una riga guastata: dov'è, com'era, come diventa. `dopo` vuoto = cancellata,
    anche quando nel file al suo posto si scrive `pass` (`sorgente_del_mutante`)."""

    riga: int   # 1-based, come nel file
    prima: str
    dopo: str


# Gli scambi, per occorrenza: `(regola, sostituto)`. Ognuno inverte un confronto o
# una congiunzione, cioè cambia il **verso** di una decisione senza toccarne la
# forma — il guasto più piccolo che un test può essere chiamato ad accorgersi.
SCAMBI: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"==="), "!=="), (re.compile(r"!=="), "==="),
    # Il doppio uguale che **non** è un pezzo del triplo: `===` letto anche come
    # `==` darebbe `!===`, che non compila e non prova niente.
    (re.compile(r"(?<![=!<>])==(?!=)"), "!="), (re.compile(r"(?<!=)!=(?!=)"), "=="),
    (re.compile(r"&&"), "||"), (re.compile(r"\|\|"), "&&"),
    (re.compile(r"\band\b"), "or"), (re.compile(r"\bor\b"), "and"),
    (re.compile(r"\bTrue\b"), "False"), (re.compile(r"\bFalse\b"), "True"),
    (re.compile(r"\btrue\b"), "false"), (re.compile(r"\bfalse\b"), "true"),
    # Il confronto di confine. Le frecce `=>` e `->` e gli shift `<<` `>>` hanno
    # lo stesso segno e non decidono niente.
    (re.compile(r"(?<![<=!>-])<(?![<=])"), "<="), (re.compile(r"(?<!<)<=(?!=)"), "<"),
    (re.compile(r"(?<![>=!<-])>(?![>=])"), ">="), (re.compile(r"(?<!>)>=(?!=)"), ">"),
]

# Ciò che non si cancella: una riga senza niente oltre la punteggiatura, un
# commento, e una riga che **apre** — un blocco in Python, una parentesi o una
# graffa in TypeScript. Toglierle rompe la sintassi e basta, e un guasto di forma
# non è una prova che il test morda: è solo un test rigirato a vuoto.
#
# E una riga a livello di modulo, senza indentazione: dichiara, non decide. La
# prima prova sul caso vero (pbi-333-giro4) ha nominato come mutante ucciso
# l'`import { … } from '../lib/nav'` di `AppLayout.tsx` — un guasto di
# **esistenza**, che ogni test che rende il componente uccide, compreso uno che
# non guarda niente. Le decisioni stanno dentro i corpi, ed è lì che si cancella.
RE_COMMENTO = re.compile(r"^\s*(#|//|/\*|\*)")
RE_APRE = re.compile(r"[:({\[]\s*$")


def si_puo_cancellare(testo: str) -> bool:
    return (re.search(r"[A-Za-z0-9]", testo) is not None
            and testo[:1].isspace()
            and RE_COMMENTO.match(testo) is None
            and RE_APRE.search(testo) is None)


# `@@ -a,b +c,d @@`: le righe **nuove** partono da `c` e sono `d` (una, se manca).
RE_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


def righe_cambiate(base: str, sha: str) -> dict[str, set[int]]:
    """Per ogni file di **produzione** che il branch ha cambiato fino a `sha`, le
    righe nuove o toccate, numerate come nel file a quel commit.

    `base...sha` e non `base..sha`: il diff parte dal merge-base, così un `main`
    andato avanti nel frattempo non entra nel conto come se fosse del branch.
    Una riga tolta non c'è più da guastare, e un file di soli `-` non compare.
    """
    righe: dict[str, set[int]] = {}
    for percorso in git("diff", "--name-only", f"{base}...{sha}").splitlines():
        if not percorso or not e_file_di_produzione(percorso):
            continue
        diff = git("diff", "--unified=0", f"{base}...{sha}", "--", percorso)
        nuove: set[int] = set()
        for inizio, quante in RE_HUNK.findall(diff):
            nuove.update(range(int(inizio), int(inizio) + (int(quante) if quante else 1)))
        if nuove:
            righe[percorso] = nuove
    return righe


def mutanti_del_sorgente(sorgente: str, righe: set[int]) -> list[Mutante]:
    """I mutanti delle sole `righe` (1-based) di `sorgente`, in ordine di riga.

    Sulle righe cambiate e non su tutto il file: è il codice che quel giro ha
    scritto, ed è l'unico di cui i suoi test rispondono. La cancellazione è
    l'operatore più forte e vale in tutti e due i linguaggi; una riga di sola
    punteggiatura non si cancella, perché romperebbe la sintassi e basta, e un
    guasto di forma non è una prova che il test morda.
    """
    mutanti: list[Mutante] = []
    for numero, testo in enumerate(sorgente.splitlines(), start=1):
        if numero not in righe:
            continue
        if si_puo_cancellare(testo):
            mutanti.append(Mutante(numero, testo, ""))
        for regola, sostituto in SCAMBI:
            for trovato in regola.finditer(testo):
                dopo = testo[:trovato.start()] + sostituto + testo[trovato.end():]
                mutanti.append(Mutante(numero, testo, dopo))
    return mutanti


def descrizione_del_mutante(percorso: str, m: Mutante) -> str:
    """`file:riga  `prima` → `dopo``, com'è scritto nel rapporto: chi legge deve
    poter aprire quella riga e vedere il guasto che il test ha sentito."""
    dopo = f"`{m.dopo.strip()}`" if m.dopo.strip() else "riga cancellata"
    return f"{percorso}:{m.riga}  `{m.prima.strip()}` → {dopo}"


def falliti_per_asserzione(c: ComandoDiProva, uscita: str) -> set[str]:
    """Le chiavi dei test che hanno **girato e fallito**, e solo quelle.

    È la lettura stretta, diversa da `esiti_del_comando`: lì un errore di raccolta
    vale come rosso di tutto il comando, perché il `from app.x import y` che non
    esiste ancora è il rosso più comune del test-first. Qui vale il contrario. Un
    mutante che rompe la sintassi fa fallire *tutto* — l'errore di raccolta di
    pytest, il file che vitest non carica — e nessuna riga per test lo dice: non è
    il test che ha morso, è il file che non c'è più. Contare quelli farebbe
    passare ogni guardia, perché cancellare una riga a caso rompe la sintassi una
    volta su tre. E l'`ERROR` per test — la fixture che esplode — sta dalla stessa
    parte: il test non è arrivato all'asserzione.

    Né ci arriva il `FAILED` per un'eccezione del codice — un `NameError` perché la
    riga cancellata definiva un nome: è un guasto di esistenza, e lo uccide anche
    un test che non guarda niente (la #254, PBI-365). In pytest il tipo si legge
    dal riepilogo di `-rf`, e conta solo un `AssertionError` o un `Failed`: un
    `FAILED` di cui il riepilogo non dice il tipo non è un'asserzione misurata.
    """
    if c.linguaggio == "python":
        return {RE_PARAMETRO.sub("", nodo)
                for nodo, tipo in tipi_dei_falliti(uscita).items()
                if tipo in TIPI_DI_ASSERZIONE}
    try:
        dati = json.loads(c.rapporto.read_text(encoding="utf-8"))
    except (AttributeError, OSError, ValueError):
        return set()
    return {caso.get("title", "")
            for file in dati.get("testResults", [])
            for caso in file.get("assertionResults", []) if caso.get("status") == "failed"}


UCCISO = "ucciso per asserzione"
PER_ECCEZIONE = "fallito per eccezione"
SOPRAVVISSUTO = "sopravvissuto"
# vitest scrive `failed` sia per un `expect` mancato sia per un'eccezione del
# codice, e le matcher di jest-dom non lanciano tutte `AssertionError`: lì vale la
# regola di prima, e chi legge il rapporto deve saperlo (PBI-365, decisione 5).
TIPO_NON_MISURATO = "tipo non misurato per vitest"


def morde(c: ComandoDiProva, chiave: str) -> tuple[str, str]:
    """Com'è andato il test `chiave`, rigirato com'è adesso l'albero: `(esito,
    tipo)`, con l'esito fra `UCCISO`, `PER_ECCEZIONE` e `SOPRAVVISSUTO`.

    Morde solo se fallisce **per asserzione**. Il rapporto di vitest si toglie
    prima di girare: se il mutante fa morire il processo prima di scriverlo,
    resterebbe quello del giro prima a dire il falso. Un test che non termina
    sotto il mutante non ha morso: ha girato a vuoto.
    """
    if c.rapporto is not None:
        c.rapporto.unlink(missing_ok=True)
    try:
        _, uscita = esegui(c.argv, c.cartella, timeout=600)
    except subprocess.TimeoutExpired:
        return SOPRAVVISSUTO, ""
    # I tipi di **questo** test, un caso per riga se è parametrico.
    tipi = [tipo for nodo, tipo in tipi_dei_falliti(uscita).items()
            if c.linguaggio == "python" and RE_PARAMETRO.sub("", nodo) == chiave]
    if chiave not in falliti_per_asserzione(c, uscita):
        return (PER_ECCEZIONE, tipi[0]) if tipi else (SOPRAVVISSUTO, "")
    if c.linguaggio != "python":
        return UCCISO, TIPO_NON_MISURATO
    return UCCISO, next(tipo for tipo in tipi if tipo in TIPI_DI_ASSERZIONE)


def quarta_lettura(albero: Path, base: str, sha: str, comando: ComandoDiProva,
                   chiave: str) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
    """Il test nato verde, rigirato contro i mutanti delle righe del branch.

    Torna la prova del primo mutante che lo fa fallire per asserzione, e tutte le
    prove fatte fino a lì: `{"mutante", "esito", "tipo"}`, una per mutante, perché
    chi legge il rapporto veda anche quelli sopravvissuti e quelli falliti per
    eccezione (PBI-365). `None` quando nessuno lo uccide: quel test non guarda le
    righe che il branch ha scritto, e la lettura resta «nato verde».

    Un mutante alla volta, nello stesso worktree in cui il test è stato visto
    verde: il file si riscrive con la riga guasta, il test gira da solo, e si esce
    al primo kill perché uno basta — il gate chiede che il test osservi le righe
    nuove, non che le copra tutte.
    """
    test = comando.origine[chiave]
    da_solo, _ = comandi_dei_test(albero, [test])
    prove: list[dict[str, str]] = []
    for percorso, righe in righe_cambiate(base, sha).items():
        if linguaggio_del_file(percorso) != test.linguaggio:
            continue  # un test Python non morde un .ts, e rigirarlo lì è tempo perso
        file = albero / percorso
        sorgente = leggi_sorgente(file)
        if sorgente is None:
            continue
        try:
            for m in mutanti_del_sorgente(sorgente, righe):
                guasto = sorgente_del_mutante(percorso, sorgente, m)
                if guasto is None:
                    continue
                file.write_text(guasto, encoding="utf-8")
                esito, tipo = morde(da_solo[0], chiave)
                prove.append({"mutante": descrizione_del_mutante(percorso, m),
                              "esito": esito, "tipo": tipo})
                if esito == UCCISO:
                    return prove[-1], prove
        finally:
            # Com'era, sempre: il test nato verde dopo questo legge lo stesso file,
            # e i suoi mutanti devono nascere dal sorgente e non dall'ultimo guasto.
            file.write_text(sorgente, encoding="utf-8")
    return None, prove


def sorgente_del_mutante(percorso: str, sorgente: str, m: Mutante) -> str | None:
    """Il file con la riga guasta, o `None` se non compila: non si prova nemmeno.

    La cancellazione di una riga Python che è l'unica istruzione del suo blocco —
    il `return` dentro un `if` — lascia il blocco vuoto, e il file non compila. Lì
    la riga si sostituisce con `pass` alla stessa indentazione (PBI-365): il blocco
    resta valido e ciò che la riga fa sparisce. È lo stesso mutante, non un altro —
    `m.dopo` resta vuoto e il rapporto dice «riga cancellata» — e se non compila
    neanche così, da quella riga non nasce nessuna cancellazione. TypeScript non ha
    `pass`, e la sua cancellazione resta com'era.
    """
    righe_del_file = sorgente.splitlines(keepends=True)
    candidati = [m.dopo]
    if not m.dopo and percorso.endswith(".py"):
        rientro = m.prima[:len(m.prima) - len(m.prima.lstrip())]
        candidati.append(rientro + "pass")
    for dopo in candidati:
        guasto = "".join(righe_del_file[:m.riga - 1] + [dopo + "\n"] + righe_del_file[m.riga:])
        if compila(percorso, guasto):
            return guasto
    return None


def linguaggio_del_file(percorso: str) -> str | None:
    """Chi può vedere un guasto in quel file: `python`, `vitest`, o nessuno."""
    if percorso.endswith(".py"):
        return "python"
    if Path(percorso).suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        return "vitest"
    return None


def compila(percorso: str, sorgente: str) -> bool:
    """`False` se il mutante ha rotto la sintassi di un file Python: non si prova
    nemmeno. Un `def` rimasto vuoto — se non basta neanche il `pass` di
    `sorgente_del_mutante` — fa fallire un test che importa il modulo **dentro** il
    proprio corpo come un `FAILED` suo, mentre non è il test che ha morso, è il
    file che non c'è più. Per TypeScript decide
    vitest, che un file rotto non lo carica e non scrive nessun esito per test.
    """
    if not percorso.endswith(".py"):
        return True
    try:
        compile(sorgente, percorso, "exec")
    except SyntaxError:
        return False
    return True


# Quanti test dell'elenco si scrivono per esteso. Oltre, si conta il resto: un
# nome tagliato a metà non si ritrova, e chi legge lo prende per un difetto del gate.
TEST_IN_ELENCO = 4


def voce_mancata(sha: str, titolo: str, test: list[str], esito: str, coda: str) -> dict[str, str]:
    resto = len(test) - TEST_IN_ELENCO
    return {"commit": sha[:7], "titolo": titolo, "esito": esito, "coda": coda[-2000:],
            "test": ", ".join(test[:TEST_IN_ELENCO]) + (f" e altri {resto}" if resto > 0 else "")}


def esamina_il_commit(sha: str, titolo: str, nuovi: list[TestNuovo], base: str,
                      morsi: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    """Estrae il commit e ci gira dentro i suoi test nuovi. Attende il rosso.

    Un test nato verde ha la quarta lettura prima di finire fra i mancati: se
    morde un mutante delle righe del branch, va in `morsi` — commit, test, mutante,
    tipo del fallimento e le prove fatte fino al kill — e non ferma niente.
    """
    mancati: list[dict[str, str]] = []
    morsi = morsi if morsi is not None else []
    with worktree_usa_e_getta(sha) as albero:
        comandi, orfani = comandi_dei_test(albero, nuovi)
        if orfani:
            mancati.append(voce_mancata(sha, titolo, orfani, ESITI_MANCATI["nessuno"],
                                        "il nome non si trova nel file a quel commit"))
        for comando in comandi:
            esiti, coda = esiti_del_comando(comando)
            # Una voce per **lettura**, non una per comando: «nato verde» e «rosso
            # non osservabile» sono due domande diverse e vanno davanti a chi legge
            # separate, anche quando escono dallo stesso `pytest`.
            per_lettura: dict[str, list[str]] = defaultdict(list)
            for chiave, etichetta in comando.etichette.items():
                if esiti[chiave] == "rosso":
                    continue
                lettura = ESITI_MANCATI[esiti[chiave]]
                if esiti[chiave] == "verde":
                    ucciso, prove = quarta_lettura(albero, base, sha, comando, chiave)
                    if ucciso is not None:
                        morsi.append({"commit": sha[:7], "titolo": titolo,
                                      "test": etichetta, "mutante": ucciso["mutante"],
                                      "tipo": ucciso["tipo"], "prove": prove})
                        continue
                    lettura = lettura_del_verde(prove)
                per_lettura[lettura].append(etichetta)
            for lettura, elenco in per_lettura.items():
                mancati.append(voce_mancata(sha, titolo, elenco, lettura, coda))
    return mancati


def descrizione_del_morso(m: dict, rientro: str) -> str:
    """La riga «nato verde, ma morde» con il mutante **e** il tipo, e sotto le
    prove fatte fino al kill, una per riga: `mutante: esito (tipo)`."""
    tipo = f" ({m['tipo']})" if m.get("tipo") else ""
    righe = [f"{rientro}→ nato verde, ma morde: {m['mutante']}{tipo}"]
    for p in m.get("prove", []):
        tipo = f" ({p['tipo']})" if p["tipo"] else ""
        righe.append(f"{rientro}  · {p['mutante']}: {p['esito']}{tipo}")
    return "\n".join(righe)


def lettura_del_verde(prove: list[dict[str, str]]) -> str:
    """Cosa si scrive di un nato verde dopo la quarta lettura.

    Con dei mutanti provati la lettura è più forte di «il codice c'era già»: dice
    che il test **non guarda** le righe che il branch ha scritto. Senza — il branch
    non ha righe di produzione, o i suoi mutanti non compilano — resta quella di
    prima, e lo dice: zero provati non è «nessuno lo fa fallire».

    I mutanti che l'hanno fatto fallire per eccezione si contano a parte, col tipo:
    chi legge un «non morde» deve vedere che un guasto il test l'ha sentito, e
    perché non conta (PBI-365).
    """
    if not prove:
        return f"{ESITI_MANCATI['verde']} — e nessun mutante da provare sulle righe cambiate"
    quanti = "1 mutante provato" if len(prove) == 1 else f"{len(prove)} mutanti provati"
    lettura = (f"nato verde e non morde: a quel commit il test passa, e {quanti} sulle "
               f"righe che il branch ha cambiato non lo fanno fallire")
    tipi = [p["tipo"] for p in prove if p["esito"] == PER_ECCEZIONE]
    if tipi:
        lettura += (f" per asserzione; {len(tipi)} {PER_ECCEZIONE} "
                    f"({', '.join(sorted(set(tipi)))}), che non è un morso")
    return lettura


def gate_del_rosso(base: str | None = None, ref: str = "HEAD",
                   visti: set[str] | None = None,
                   morsi: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    """I commit del branch in cui un test è nato senza essere mai stato rosso.

    `base` è il ramo di `asdlc.toml` se non è detto: un default scritto nella
    firma si congelerebbe all'import, e un TOML di prova non lo muoverebbe.

    Lista vuota = il gate passa. `visti` è l'insieme dei commit già guardati e viene
    **riempito**: il gate sta dentro un ciclo che può ripetersi cinque volte, e
    rigirare ogni volta la storia intera moltiplicherebbe il tempo macchina per le
    revisioni. `morsi` si riempie allo stesso modo, con i test nati verdi che hanno
    ucciso un mutante: passano, e il rapporto deve dire perché.

    Non si ferma al primo mancato: chi legge deve avere l'elenco intero — commit,
    test, esito — perché la lettura la fa una persona, e una persona decide meglio
    su tre casi che su uno.
    """
    base = base if base is not None else BASE
    visti = visti if visti is not None else set()
    mancati: list[dict[str, str]] = []
    for sha in commit_da_esaminare(base, ref, visti):
        visti.add(sha)
        file = file_del_commit(sha)
        nuovi = test_nuovi_del_commit(sha, file)
        if not nuovi:
            continue  # un refactor non porta test nuovi, e la regola morde su quelli
        titolo = git("show", "--no-patch", "--format=%s", sha)
        produzione = [v.percorso for v in file if e_file_di_produzione(v.percorso)]
        if produzione:
            mancati.append(voce_mancata(sha, titolo, etichette_al_commit(sha, nuovi),
                                        MISTO, ", ".join(produzione[:10])))
            continue
        mancati += esamina_il_commit(sha, titolo, nuovi, base, morsi)
    return mancati


def revisione_critica(pbi_path: Path) -> Verdetto:
    """Sessione NUOVA, modello diverso, sola lettura: il Critic non è il Builder."""
    print("    critic … ", end="", flush=True)
    try:
        percorso = pbi_path.relative_to(REPO)
    except ValueError:
        percorso = pbi_path
    # Scrive il prompt su file per evitare limiti di lunghezza degli argomenti CLI
    prompt_file, file_esito = file_dell_invocazione("critic")
    prompt_file.write_text(PROMPT_CRITIC.format(pbi_path=percorso), encoding="utf-8")
    _, out, dichiarato, registro = invoca_agente("critic", CRITIC, prompt_file, file_esito)

    # Un Critic che non emette un verdetto non ha giudicato: è un'invocazione fallita, e
    # trattarla come "NON PRONTO" rimanda il Builder a correggere violazioni che nessuno
    # ha trovato. Un guasto dello strumento deve somigliare a un guasto, non a un giudizio:
    # è `senza esito`, come per il Builder, e non più un'eccezione (`ADR-0027`).
    if dichiarato is None:
        print("SENZA ESITO")
        return Verdetto("senza esito", "", out, registro)

    # Il sospeso senza domanda non arriva fin qui: lo rifiuta lo strumento. Il
    # rapporto è il riepilogo della chiamata; per il sospeso, che non ne ha, il
    # testo finale entra come contesto per chi legge, e non decide niente.
    if dichiarato["esito"] == "fermati":
        verdetto = Verdetto("sospeso", dichiarato["domanda"], out, registro)
    else:
        verdetto = Verdetto(dichiarato["verdetto"], "", dichiarato["riepilogo"], registro)
    print(verdetto.esito.upper())
    return verdetto


# Il limite documentato di GitHub per il corpo di un commento, in caratteri. Un
# rapporto più lungo si divide in commenti consecutivi, e non si tronca (PBI-371).
LIMITE_COMMENTO_GITHUB = 65_536


def parti_del_commento(titolo: str, testo: str,
                       limite: int = LIMITE_COMMENTO_GITHUB) -> list[str]:
    """Il testo in commenti da al più `limite` caratteri, senza perderne uno.

    Se sta in un commento resta com'è. Altrimenti ogni parte comincia con
    «**titolo · parte i di k**» e una riga vuota, e le parti, una dopo l'altra,
    ridanno il testo intero. La testata più lunga è quella con `i = k`: si
    ricalcola `k` finché il passo che le lascia posto non cambia più."""
    if len(testo) <= limite:
        return [testo]
    k = 1
    while True:
        passo = limite - len(f"**{titolo} · parte {k} di {k}**\n\n")
        necessarie = -(-len(testo) // passo)
        if necessarie <= k:
            break
        k = necessarie
    pezzi = [testo[i:i + passo] for i in range(0, len(testo), passo)]
    return [f"**{titolo} · parte {i} di {len(pezzi)}**\n\n{pezzo}"
            for i, pezzo in enumerate(pezzi, 1)]


def commenta_i_rapporti(url: str, e: Esito) -> None:
    """Un commento sulla PR per ogni revisione del Critic, in ordine, col testo
    intero del suo file (PBI-371): chi decide il merge lo legge lì, e non in
    `runs/` dentro il worktree del runner. Il corpo passa da un file, perché un
    argomento di 65.536 caratteri accentati sfiora il limite di un argomento."""
    with tempfile.TemporaryDirectory() as cartella:
        for r in e.rapporti_critic:
            testo = Path(r["percorso"]).read_text(encoding="utf-8")
            titolo = f"Critic — revisione {r['revisione']} — {r['verdetto']}"
            for i, parte in enumerate(parti_del_commento(titolo, testo)):
                corpo = Path(cartella) / f"{r['revisione']}-{i}.md"
                corpo.write_text(parte, encoding="utf-8")
                esegui(["gh", "pr", "comment", url, "--body-file", str(corpo)],
                       REPO, timeout=300)


def apri_pr(pbi: str, pbi_path: Path, branch: str, e: Esito) -> str:
    """Apre la PR e si ferma lì: il merge è dell'umano (micro-commits §5).

    È **qui** che il branch arriva su `origin`, e in nessun altro punto della
    strada buona: un ramo pubblicato prima che il Critic abbia parlato è una
    promessa fatta su lavoro che nessuno ha ancora accettato, e su PBI-324 quella
    promessa è stata riscossa con un merge di un terzo del lavoro (difetto 18).

    E la PR si apre solo se su `origin` c'è **`HEAD`**, cioè ciò che i gate hanno
    misurato: lo si chiede al remoto con `ls-remote`, non a un remote-tracking.
    Su PBI-358 (difetto 30) il push è riuscito e ha mandato un ref fermo
    diciannove commit indietro, e la PR #237 è nata su un `(RED)` con il giro
    `fatto`. Se i due sha non coincidono il giro chiude `fermato` e li nomina.
    Se il remoto non risponde, cosa ci sia sopra non si sa: è la stessa promessa
    non verificata, e chiude allo stesso modo — **senza alzare**, perché
    un'eccezione qui registrerebbe `rosso` e zero commit un giro già pubblicato.
    """
    if not pubblica(branch):
        # L'esito resta quello che era: un push mancato non disfa il giro, ma la
        # riga del registro lo deve dire — il log da solo non lo guarda nessuno.
        e.nota = " · ".join(t for t in (e.nota, NON_PUBBLICATO) if t)
        return ""
    head = su_origin = None
    try:
        head = git("rev-parse", "HEAD")
        fuori = git("ls-remote", REMOTO, f"refs/heads/{branch}").split()
        su_origin = fuori[0] if fuori else ""
    except RuntimeError as exc:
        print(f"    ⚠️  {REMOTO} non verificabile: {str(exc)[:200]}")
    if su_origin is None or su_origin != head:
        visto = ("non verificabile" if su_origin is None
                 else su_origin or "assente")
        diagnosi = (f"PR non aperta: su {REMOTO} {branch} è {visto}, "
                    f"i gate hanno misurato HEAD {head or 'illeggibile'}")
        print(f"    ⚠️  {diagnosi}")
        e.stato = "fermato"
        e.nota = " · ".join(t for t in (diagnosi, e.nota) if t)
        return ""
    corpo = (
        f"Esecuzione automatica di `{pbi_path.relative_to(REPO)}` "
        f"(`tools/asdlc_runner.py`).\n\n"
        + (f"Gate deterministici verdi · **Review Gate saltato** (`--senza-critic`): "
           f"di questo lavoro non esiste una lettura avversariale, e la revisione è "
           f"tutta qui.\n"
           if e.critic_saltato else
           f"Gate deterministici verdi · revisione avversariale PASS.\n")
        + f"Tempo macchina: **{hms(e.durata_s)}** "
        f"(agente {hms(e.tempi['builder'] + e.tempi['critic'])}, gate {hms(e.tempi['gate'])}).\n\n"
        f"Manca l'unica cosa che uno script non può dare: **l'accettazione umana**.\n"
        f"Prima del merge, guarda: i criteri di verifica del PBI, il diff fuori scope, "
        f"e se la spec è stata aggiornata dove il comportamento è cambiato."
    )
    code, out = esegui(
        ["gh", "pr", "create",
         "--title", f"{pbi}: {pbi_path.stem.split('-', 2)[-1].replace('-', ' ')}",
         "--body", corpo, "--base", RAMO_PRINCIPALE, "--head", branch],
        REPO, timeout=300,
    )
    if code != 0:
        print(f"    ⚠️  PR non aperta: {out.strip()[:200]}")
        return ""
    # Per **forma**, non per posizione: `gh` scrive l'URL sull'ultima riga finché
    # non ha altro da dire, e un avviso di aggiornamento basta a far finire nella
    # colonna `pr` del registro una frase che non è un indirizzo (difetto 12).
    # Se non c'è un URL la colonna resta vuota: una colonna che mente costa più
    # di una che tace.
    url = re.search(r"https://\S+/pull/\d+", out)
    if url is None:
        print(f"    ⚠️  PR aperta ma senza URL riconoscibile: {out.strip()[:200]}")
        return ""
    commenta_i_rapporti(url.group(0), e)
    return url.group(0)


def crea_branch(pbi: str) -> str:
    """Il branch del PBI, sempre dal ramo di base fresco — `BASE`, `origin/main`.

    ``git switch -c`` parte da dove si trova, e dove si trova è il branch del PBI
    precedente: due PBI nella stessa invocazione producevano branch **impilati**,
    col diff del secondo che conteneva il lavoro del primo. È il motivo per cui
    `ada-notte.sh` esiste come ciclo esterno invece di passare i PBI al runner in
    un colpo solo.

    Si ramifica **dal ramo remoto**, senza estrarre il `main` locale. Non è un
    dettaglio di stile: il runner gira nel worktree `ada-run`, e un branch si può
    estrarre in un worktree solo. `main` sta quasi sempre estratto nel repository
    principale, quindi `git switch main` là dentro fallirebbe con *«already used
    by worktree»* — e ``git()`` alza, cioè il PBI morirebbe prima di cominciare.

    Scrivere il punto di partenza dentro il comando toglie anche l'altra domanda:
    non c'è un `main` locale da allineare, quindi non c'è il caso in cui è
    disallineato.
    """
    git("fetch", REMOTO, RAMO_PRINCIPALE)
    branch = nome_libero(pbi, rami_su_origin(pbi) | rami_locali(pbi))
    git("switch", "-c", branch, BASE)
    return branch


def rami_su_origin(pbi: str) -> set[str]:
    """I rami che `origin` ha già per questo PBI.

    Si chiede al remoto perché è l'unico posto in cui un giro fallito lascia
    traccia per tutti: `chiudi()` pubblica su ogni stato che interrompe, e il
    rilancio deve vedere quel nome occupato anche da un albero che non c'era.
    """
    fuori = git("ls-remote", "--heads", REMOTO, f"{ramo_del_pbi(pbi)}*")
    return {r.split("refs/heads/")[-1].strip() for r in fuori.splitlines() if "refs/heads/" in r}


def rami_locali(pbi: str) -> set[str]:
    """E quelli che ha già il repository in cui `switch -c` sta per scrivere.

    Difetto 29 di PBI-102, su PBI-335 la sera del 02/09/2026: il giro è morto in
    **zero secondi** su *«esiste già un ramo denominato pbi/pbi-335»*, e su
    `origin` quel ramo non c'era — mergiato e cancellato giorni prima. Era
    rimasto in `ada-run`, col solo commit che aveva scritto il documento del PBI.

    Chiedere solo al remoto reggeva su una premessa che `ada-run` non soddisfa:
    *«il worktree è appena stato creato»*. È un albero di lunga vita, e colleziona
    i rami di ogni sessione che ci ha lavorato dentro — comprese quelle che il
    runner non ha mai visto. I rami sono del repository, non del worktree: li
    vede anche un giro che gira in un albero staccato.
    """
    dentro = git("branch", "--list", f"{ramo_del_pbi(pbi)}*", "--format=%(refname:short)")
    return {r.strip() for r in dentro.splitlines() if r.strip()}


def ramo_del_pbi(pbi: str) -> str:
    """`pbi/pbi-322` da `PBI-322`: `[git].prefisso_ramo` più il numero, letto
    dal modello `[backlog].id`. È **l'unico** posto in cui la forma del ramo si
    compone, e `asdlc_coda.py` la rilegge dalla stessa configurazione: prima le
    due forme stavano in cinque punti, e PBI-353 ne ha corrette tre insieme
    mentre la quarta teneva ferma la coda per sette ore."""
    numero = CFG.backlog.numero(pbi)
    if numero is None:
        raise ValueError(f"{pbi} non è un id secondo `[backlog].id = {CFG.backlog.id!r}`")
    return CFG.git.ramo_del_pbi(numero)


def nome_libero(pbi: str, presi: set[str]) -> str:
    """`pbi/pbi-322`, e se è occupato `pbi/pbi-322-giro2`.

    Il nome del branch era fisso, e un giro fallito lo lasciava occupato su
    `origin`: il rilancio o moriva su *«esiste già un ramo»*, o — peggio — ci
    scriveva sopra una storia diversa e il push finale si prendeva un
    `non-fast-forward` a lavoro fatto. Difetto 16 di PBI-102, misurato su PBI-322
    la notte del 26→27/08.

    `presi` sono i nomi che `switch -c` non può prendere, e arrivano da due posti:
    `origin` e il repository locale. Uno solo dei due non basta — il difetto 29 è
    stato esattamente questo.

    Il numero è del **giro**, non del PBI: dice quante volte ci si è provati, che
    è l'informazione che serve a chi apre la lista dei rami.
    """
    base = ramo_del_pbi(pbi)
    if base not in presi:
        return base
    n = 2
    while f"{base}-giro{n}" in presi:
        n += 1
    return f"{base}-giro{n}"


# Ciò che la nota del giro dice quando `pubblica()` torna False: stato e commit
# restano quelli che erano, e questa è la riga che lo fa sapere al registro.
NON_PUBBLICATO = "branch non pubblicato: i commit restano nel worktree"


def pubblica(branch: str) -> bool:
    """Manda il branch su `origin`. Non alza mai: pubblicare è l'ultimo gesto.

    Due cose, che sono le due cause del difetto 18. **`--force-with-lease`**
    perché il branch è nostro e fra un giro e l'altro può essere stato riscritto —
    un rebase, un `commit --amend` sui messaggi — e un push semplice si prende il
    `non-fast-forward` che su PBI-324 ha ucciso il processo con quattro giri di
    lavoro dentro. Il lease non è `--force` cieco: se qualcun altro ha scritto su
    quel ramo il push si rifiuta lo stesso, che è la sola cosa da proteggere.

    E **non alza**: un push che fallisce è una brutta notizia, non una ragione per
    buttare via l'ora precedente. Chi legge il log la trova scritta, chi la
    chiama la riporta nella nota del giro (`NON_PUBBLICATO`), e i commit
    restano nel worktree.

    Si manda **`HEAD`**, non il ref del ramo, quando i due divergono (difetto 30):
    `HEAD` è ciò che gate, gate del rosso e Critic hanno guardato, e il worktree
    del runner è staccato per progetto — su PBI-358 il ref era rimasto diciannove
    commit indietro, ed è quello che è finito su `origin`. Quando coincidono il
    comando resta quello di sempre. Dopo il push da `HEAD` il ref locale si
    riallinea con `branch -f`: in un albero staccato nessuno lo sposta, e il giro
    dopo troverebbe un ramo locale che dice una cosa e un remoto che ne dice
    un'altra. Con `HEAD` attaccato non serve, ed è bene: `branch -f` rifiuta di
    muovere un ramo estratto. Se lo rifiuta lo stesso — il ramo estratto in un
    terzo worktree — il push è comunque riuscito, e l'etichetta rimasta indietro
    si dichiara nel log invece di far sembrare fallita la pubblicazione.
    """
    try:
        etichetta = git("rev-parse", f"refs/heads/{branch}")
        if git("rev-parse", "HEAD") == etichetta:
            git("push", "--force-with-lease", "-u", REMOTO, branch)
            return True
        git("push", "--force-with-lease", "-u", REMOTO, f"HEAD:refs/heads/{branch}")
    except RuntimeError as exc:
        print(f"    ⚠️  branch non pubblicato: {str(exc)[:200]}")
        print(f"       i commit restano in locale su {branch}: `git push` a mano quando "
              f"hai guardato cosa c'è sul remoto.")
        return False
    try:
        git("branch", "-f", branch, "HEAD")
    except RuntimeError as exc:
        print(f"    ⚠️  HEAD pubblicato, ma il ref locale {branch} è rimasto indietro a "
              f"{etichetta[:12]}: {str(exc)[:200]}")
    return True


def trova_pbi(pbi: str) -> Path | None:
    """Il file del PBI come lo vede il ramo di base, non come lo vede il worktree.

    Il runner gira in `ada-run`, un albero che resta fermo al commit su cui
    qualcuno l'ha messo l'ultima volta. Il branch invece nasce **sempre** da
    `BASE` (`crea_branch`): un PBI mergiato dopo quell'ultimo `switch` c'è
    dove il lavoro si farà e non c'è dove lo si cercava. Il giro chiudeva
    «saltato (PBI inesistente)» — venti secondi, nessun commit, e il file sotto
    il naso. Difetto 7 di PBI-102, ricaduto due volte.

    Il `fetch` è lo stesso che farebbe `crea_branch` un attimo dopo, e costa una
    chiamata: cercare su un `origin/main` vecchio sarebbe lo stesso difetto con
    un altro nome.

    Se il remoto non risponde si **ripiega sull'albero estratto** e lo si dice:
    un fetch che non parte non è una ragione per non fare un PBI che si ha già
    in casa. È l'unico caso in cui l'albero decide, ed è dichiarato a schermo.
    """
    numero = CFG.backlog.numero(pbi)
    if numero is None:
        return None  # non è un id di questo progetto: `[backlog].id` dice la forma
    forma = CFG.backlog.glob_del_file(numero)
    try:
        git("fetch", REMOTO, RAMO_PRINCIPALE)
        voci = git("ls-tree", "--name-only", BASE, f"{BACKLOG}/").splitlines()
    except RuntimeError as exc:
        print(f"    ⚠️  {BASE} non raggiungibile ({str(exc)[:120]}): "
              f"cerco {pbi} nell'albero estratto")
        return next(REPO.glob(f"{BACKLOG}/{forma}"), None)

    nome = next((v.strip() for v in voci if fnmatch(Path(v.strip()).name, forma)), None)
    return REPO / nome if nome else None


def salva_il_traceback(pbi: str) -> Path:
    """Il traceback dell'eccezione in corso in un file di `LOG_DIR`, accanto al
    log del giro. `.log` perché `runs/*.log` è ignorato da git: un file nuovo in
    `runs/` sporcherebbe l'albero del giro dopo."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    file = LOG_DIR / f"{timestamp}_{pbi}_traceback.log"
    file.write_text(traceback.format_exc(), encoding="utf-8")
    return file


def scrivi_rapporto_critic(run: str, pbi: str, revisione: int, verdetto: Verdetto) -> Path:
    """Il rapporto di una revisione del Critic, intero, nel suo file di `LOG_DIR`:
    `<run>-<PBI>-critic-<n>.md` (PBI-371). Nel JSON del giro stava tagliato agli
    ultimi 6000 caratteri, e un rapporto più lungo perdeva la testa.

    In testa il verdetto e l'ora. Il rapporto di un sospeso è la sua domanda, con
    il testo finale del Critic sotto come contesto, come in PBI-367."""
    ora = datetime.now().isoformat(timespec="seconds")
    domanda = f"## Domanda\n\n{verdetto.domanda}\n\n## Contesto\n\n" if verdetto.domanda else ""
    file = LOG_DIR / f"{run}-{pbi}-critic-{revisione}.md"
    file.write_text(
        f"# Critic — revisione {revisione} — {verdetto.esito}\n\n{ora}\n\n"
        f"{domanda}{verdetto.rapporto}\n",
        encoding="utf-8",
    )
    return file


def esegui_pbi(
    pbi: str, attivi: set[str], dry: bool, con_pr: bool, con_critic: bool = True,
    run: str = "",
) -> Esito:
    run = run or datetime.now().strftime("%Y%m%d-%H%M%S")
    pbi_path = trova_pbi(pbi)
    if pbi_path is None:
        return Esito(pbi, "saltato", nota=f"PBI inesistente in {BACKLOG}/ su {BASE}")

    print(f"\n=== {pbi} — {pbi_path.name}")
    prompt = PROMPT_BUILDER.format(pbi_path=pbi_path.relative_to(REPO))
    if dry:
        print(prompt)
        return Esito(pbi, "saltato", nota="dry-run")

    if git("status", "--porcelain"):
        return Esito(pbi, "fermato", nota="albero di lavoro sporco: committa o pulisci prima")

    # Il controllo guarda **tutto** l'albero, senza eccezioni. `runs/` è stato
    # escluso finché il runner scriveva `runs/tempi.csv` a fine invocazione: da
    # quando quel file è versionato, ogni giro rendeva sporco il successivo, e
    # l'eccezione era la toppa. `ADR-0020` ha tolto la causa — il registro esce
    # dai branch — quindi torna a valere la regola intera: ciò che non è
    # committato non esiste, e non si parte sopra al lavoro di qualcun altro.
    e = Esito(pbi, "rosso", iniziato=datetime.now().isoformat(timespec="seconds"))
    t0 = time.monotonic()
    branch = crea_branch(pbi)
    apri_la_fase()

    def conta_commit() -> int:
        """`BASE..HEAD` — il ramo remoto — e non `main..HEAD`: da quando il main
        locale del worktree non si estrae più, resta indietro di giorni e
        conterebbe come commit del PBI tutto ciò che main ha ricevuto nel
        frattempo."""
        try:
            return int(git("rev-list", "--count", f"{BASE}..HEAD") or 0)
        except (RuntimeError, ValueError):
            return e.commit  # un conteggio mancato non cancella quello di prima

    def dichiara(testo: str) -> None:
        """Una cosa che il giro dice di sé nella nota — un gate in meno — e che
        deve restare leggibile in `runs/tempi.csv` qualunque sia l'esito."""
        e.nota = " · ".join(t for t in (e.nota, testo) if t)

    def chiudi(stato: str, nota: str = "") -> Esito:
        # Il conteggio sta **qui** e non dopo il giro dei gate: ogni uscita
        # anticipata — il `fermati` del Builder, l'albero che resta sporco — scriveva
        # `commit = 0` mentre sul branch c'era il lavoro. Su PBI-209 erano otto
        # commit e 2.174 righe, e la colonna del registro diceva zero: è quella
        # che si guarda per decidere se un branch fermato si butta (difetto 10).
        chiudi_la_fase()
        e.commit = conta_commit()
        e.stato, e.durata_s = stato, time.monotonic() - t0
        e.finito = datetime.now().isoformat(timespec="seconds")
        if nota:
            # La diagnosi davanti, e dietro ciò che il giro aveva già dichiarato di
            # sé — un gate spento, il Critic saltato: la fermata non lo cancella.
            e.nota = " · ".join(t for t in (nota, e.nota) if t)
        # Un giro che si ferma ha comunque prodotto commit, e lasciarli solo nel
        # worktree vuol dire non farli guardare a nessuno: su PBI-320 sono rimasti
        # lì, su PBI-322 li ha salvati a mano una persona prima di chiudere il
        # terminale. Difetto 8 di PBI-102. Sulla strada buona non si pubblica qui:
        # a quello ci pensa `apri_pr`, una volta sola.
        if stato in STATI_CHE_INTERROMPONO and not pubblica(branch):
            dichiara(NON_PUBBLICATO)
        print(f"    tempo: {hms(e.durata_s)} "
              f"(builder {hms(e.tempi['builder'])} · gate {hms(e.tempi['gate'])} · "
              f"critic {hms(e.tempi['critic'])})")
        return e

    # Il giro sta in un `try` perché ogni strada d'uscita passi da `chiudi()`:
    # un'eccezione — il timeout di un gate, un guasto dentro il gate del rosso —
    # usciva da qui, la raccoglieva la rete di `main()`, e il ramo restava solo
    # nel worktree con i commit non contati. Senza ramo su `origin` il tick
    # rilanciava lo stesso PBI (difetto 37). La rete di `main()` resta, come
    # ultima difesa e non come strada.
    try:
        # I commit già passati sotto il gate del rosso. Vive fuori dal ciclo delle
        # revisioni apposta: alla seconda revisione i commit del primo giro sono gli
        # stessi, e rigirarne i test moltiplicherebbe il tempo macchina per le revisioni.
        visti: set[str] = set()

        for revisione in range(MAX_REVISIONI + 1):
            e.revisioni = revisione

            # --- Builder + Quality Gate (deterministico) ---
            verde = False
            rossi: list[tuple[str, str]] = []  # se l'agente non arriva mai ai gate, resta vuoto
            # Ogni revisione apre una sessione nuova; i ritentativi **dentro** la revisione la
            # continuano. Sono due situazioni opposte servite dallo stesso flag: un gate rosso
            # è "hai sbagliato una riga", e rileggere tutto il repository per quello è il modo
            # più costoso di dirlo; un NON PRONTO è "il giudice ha respinto il lavoro", e lì la
            # finestra vecchia è il problema — dopo quattro giri di discussione sullo Scope
            # contiene le ragioni per cui l'agente si era convinto di poterlo allargare
            # (`decisions/ADR-0015`, *Dove entra*). Prima `e.tentativi`, che non si azzera mai,
            # faceva valere la regola del gate rosso anche fra le revisioni.
            primo_del_giro = True
            # Due contatori locali alla revisione, e uno cumulativo che va nel registro.
            # `e.tentativi` non si azzera mai — è la fatica totale, ed è ciò che si legge in
            # `runs/tempi.csv` — quindi non può essere lui a decidere quando smettere: farebbe
            # valere il tetto dei gate **fra** le revisioni, e alla terza il Builder non avrebbe
            # più un giro. È lo stesso equivoco che ADR-0015 ha già tolto una volta.
            gate_falliti = igiene = 0
            while gate_falliti < MAX_TENTATIVI:
                print(f"  builder — giro {e.tentativi + igiene + 1}")
                # Scrive il prompt su file per evitare limiti di lunghezza degli argomenti CLI
                prompt_file, file_esito = file_dell_invocazione("builder")
                prompt_file.write_text(prompt, encoding="utf-8")
                cmd = BUILDER + ([] if primo_del_giro else ["-c"])
                primo_del_giro = False
                with misura(e, "builder"):
                    invocazione = invoca_agente("builder", cmd, prompt_file, file_esito)
                e.invocazioni.append(invocazione.registro)
                dichiarato = invocazione.dichiarato

                # Senza una chiamata valida il Builder non ha detto niente che si possa
                # leggere, qualunque cosa ci sia nel suo testo: si chiude qui, senza
                # igiene e senza gate. Un limite d'uso con l'albero sporco spendeva i
                # tre giri d'igiene (difetto 27); ora costa un lancio (`ADR-0027`).
                if dichiarato is None:
                    return chiudi("senza esito", nota_senza_esito(invocazione.registro))
                if dichiarato["esito"] == "fermati":
                    e.domanda = dichiarato["domanda"]
                    return chiudi("fermato", f"domanda dell'agente: {una_riga(e.domanda)}")

                # Come all'ingresso, e per la stessa ragione: niente eccezioni da quando
                # il registro non si scrive più dal branch (`ADR-0020`).
                if sporco := git("status", "--porcelain"):
                    # Non committato = non esiste: niente da giudicare, niente da ripristinare.
                    # Il giro si conta fra quelli d'igiene: `e.tentativi` è la pazienza sui
                    # **gate**, e spenderla qui vorrebbe dire togliere al lavoro vero i giri
                    # che gli servivano (PBI-208, notte del 24/08).
                    igiene += 1
                    if igiene >= MAX_IGIENE:
                        return chiudi(
                            "fermato",
                            f"l'albero resta sporco dopo {MAX_IGIENE} giri del Builder: "
                            f"il lavoro c'è ma non è committato ({sporco.splitlines()[0][:120]})",
                        )
                    prompt = PROMPT_IGIENE.format(sporco=sporco[:1500])
                    continue

                e.tentativi += 1
                gate_falliti += 1

                with misura(e, "gate"):
                    rossi = gira_gate(attivi)
                if not rossi:
                    verde = True
                    break
                prompt = PROMPT_RIPROVA.format(esiti="\n\n".join(f"## {n}\n{o}" for n, o in rossi))

            e.commit = conta_commit()
            if not verde:
                e.gate_rossi = [{"gate": n, "coda": o[-2000:]} for n, o in rossi]
                for g in e.gate_rossi:
                    print(f"    ── {g['gate']} ──\n{g['coda']}")
                return chiudi("rosso", "gate ancora rossi dopo i tentativi previsti")

            # --- Quality Gate, seconda domanda: quei test sono mai stati rossi? ---
            # Sta qui e non prima: finché i quattro sono rossi il lavoro non è finito, e
            # non ha senso chiedere di un ciclo che potrebbe non essere ancora chiuso.
            print("    gate del rosso … ", end="", flush=True)
            morsi: list[dict[str, str]] = []
            senza_rosso: list[dict[str, str]] = []
            if not GATE_DEL_ROSSO_ATTIVO:
                # La valvola del livello 4 rinviato (PBI-358, decisione 7): un progetto
                # il cui runner di test il gate non sa leggere tiene gli altri due gate.
                # Degradato, ma ancora ASDLC — e lo **dichiara**, a schermo e nella nota
                # che va nel rapporto e in `runs/tempi.csv`: un gate che si indebolisce
                # in silenzio è la prima cosa che `AUTOMAZIONE.md` vieta.
                print("spento (asdlc.toml)")
                if NOTA_ROSSO_SPENTO not in e.nota:
                    dichiara(NOTA_ROSSO_SPENTO)
            else:
                t_rosso = time.monotonic()
                try:
                    with misura(e, "gate"):
                        senza_rosso = gate_del_rosso(visti=visti, morsi=morsi)
                except GuastoDelGate as guasto:
                    # Un gate rotto è un gate **rosso**, non un ciclo mancato: qui non si
                    # accusa nessun commit, perché il gate non ne ha guardato nessuno.
                    print(f"GUASTO ({hms(time.monotonic() - t_rosso)})")
                    print(f"    ── gate del rosso ──\n{guasto}")
                    return chiudi("rosso", f"il gate del rosso non ha potuto girare: {guasto}")
                print(f"{'FERMA' if senza_rosso else 'verde'} ({hms(time.monotonic() - t_rosso)})")
            # I nati verdi che mordono si scrivono **prima** dell'eventuale fermata: sono
            # passati, e il rapporto lo dice anche quando un altro commit ferma il giro.
            e.test_che_mordono += morsi
            for m in morsi:
                print(f"    ── {m['commit']} {m['titolo']} ──\n"
                      f"       {m['test']}\n{descrizione_del_morso(m, '       ')}")
            if senza_rosso:
                # `fermato` e non un rilievo da chiudere in un giro di revisione: il ciclo
                # mancato è **ex ante**, e nessuna fix lo annulla. Mandare il Builder a
                # rimediare vorrebbe dire spendere una revisione su una cosa che non si
                # corregge — e poi far leggere lo stesso elenco a una persona.
                e.commit_senza_rosso = senza_rosso
                for m in senza_rosso:
                    print(f"    ── {m['commit']} {m['titolo']} ──\n"
                          f"       {m['test']}\n       → {m['esito']}")
                return chiudi(
                    "fermato",
                    f"il rosso non si è mai visto su {len(senza_rosso)} commit "
                    f"({', '.join(m['commit'] for m in senza_rosso[:5])}): elenco nel rapporto "
                    f"del giro. Il ciclo mancato è ex ante e nessuna fix lo annulla",
                )

            # --- Review Gate (probabilistico, sessione separata) ---
            # Si può togliere, e allora **si dichiara**: `critic_s = 0` non spiega se
            # stesso — è la lezione di `gate_s = 0` su PBI-208, letto come «gate
            # rosso» invece che «i gate non sono mai girati». Chi rilegge il registro
            # deve sapere che quel giro ha avuto due gate su tre, non tre.
            if not con_critic:
                e.critic_saltato = True
                dichiara("critic saltato (--senza-critic): revisione umana alla PR")
                print("    critic … saltato (--senza-critic)")
                break

            with misura(e, "critic"):
                verdetto = revisione_critica(pbi_path)
            if verdetto.registro is not None:
                e.invocazioni.append(verdetto.registro)
            rapporto = verdetto.rapporto
            file = scrivi_rapporto_critic(run, pbi, revisione, verdetto)
            e.rapporti_critic.append(
                {"revisione": revisione, "verdetto": verdetto.esito, "percorso": str(file)})
            if verdetto.esito == "pass":
                break
            if verdetto.esito == "senza esito":
                return chiudi("senza esito", nota_senza_esito(verdetto.registro))
            if verdetto.esito == "sospeso":
                # Non si consuma una revisione e non si richiama il Critic: la sua
                # diagnosi non cambia riprovando, perché ciò che manca non è nel
                # repository. Riprovare qui è esattamente ciò che è costato a PBI-203
                # cinque giri e 1h26m per tornare al punto di partenza.
                e.domanda = verdetto.domanda
                return chiudi("sospeso", f"domanda del critic: {una_riga(verdetto.domanda)}")
            if revisione == MAX_REVISIONI:
                # **Non convergente, non respinto.** Sono due diagnosi diverse e confonderle
                # manda a correggere la cosa sbagliata: `respinto` dice che il PBI era scritto
                # male, `non convergente` che il lavoro non si è chiuso e serve una persona.
                # Chi legge runs/tempi.csv deve poter distinguere un PBI difficile da uno mal
                # posto, altrimenti il registro misura la fatica e non la causa.
                return chiudi("non convergente",
                              f"{MAX_REVISIONI + 1} revisioni senza convergere — i rilievi "
                              f"del Critic in {LOG_DIR / f'{run}-{pbi}-critic-*.md'}. "
                              f"Serve una lettura umana.")
            # Relativo come nel primo giro: è lo stesso percorso che il Builder ha già
            # letto, e un assoluto qui lo farebbe sembrare un altro file. Il rapporto
            # va intero: tagliato, il Builder non leggeva i primi rilievi (PBI-371).
            prompt = PROMPT_RIMEDIO.format(
                rapporto=rapporto, pbi_path=pbi_path.relative_to(REPO)
            )

        print(f"    commit sul branch: {e.commit} · "
              f"file: {git('diff', '--name-only', f'{BASE}...HEAD')}")
        chiudi("fatto")
    except Exception as exc:  # noqa: BLE001 — si cattura per chiudere, non per tacere
        traceback.print_exc()
        e.file_traceback = str(salva_il_traceback(pbi))
        interruzione = f"{type(exc).__name__}: {exc}"
        try:
            return chiudi("rosso", f"eccezione nel giro: {interruzione}"[:300])
        except Exception as guasto:  # noqa: BLE001
            # Una chiusura che fallisce non si inghiotte: sale alla rete di
            # `main()`, e la nota dice perché e che cosa aveva interrotto il giro.
            raise RuntimeError(
                f"chiusura del giro fallita: {type(guasto).__name__}: {guasto} "
                f"(il giro era stato interrotto da {interruzione})"[:300]
            ) from guasto

    # --- Acceptance Gate (umano): si apre la PR, non si mergia ---
    if con_pr:
        e.pr = apri_pr(pbi, pbi_path, branch, e)
        if e.pr:
            print(f"    PR aperta: {e.pr}")
    return e


def riga_di_registro(run: str, e: dict) -> dict:
    """Un esito del rapporto JSON nella riga del registro. Le colonne sono `COLONNE_CSV`."""
    tempi = e.get("tempi", {})
    return {
        "run": run, "pbi": e["pbi"], "stato": e["stato"],
        "iniziato": e.get("iniziato", ""), "finito": e.get("finito", ""),
        "durata_s": round(float(e.get("durata_s", 0.0)), 1),
        "durata_hms": hms(float(e.get("durata_s", 0.0))),
        "builder_s": round(float(tempi.get("builder", 0.0)), 1),
        "gate_s": round(float(tempi.get("gate", 0.0)), 1),
        "critic_s": round(float(tempi.get("critic", 0.0)), 1),
        "tentativi": e.get("tentativi", 0), "revisioni": e.get("revisioni", 0),
        "commit": e.get("commit", 0), "pr": e.get("pr", ""), "nota": e.get("nota", ""),
    }


def registra(cartella: Path) -> int:
    """Piega i rapporti dei giri in `runs/tempi.csv`. Si lancia **su `main`**, dopo il merge.

    `ADR-0020`. Il registro è versionato e append-only, e finché lo scriveva il
    giro finiva **dentro il branch del PBI**: due giri a cavallo di un merge
    scrivevano la stessa ultima riga, e la PR usciva `CONFLICTING` su un file che
    il PBI non aveva toccato. Il conflitto si risolveva tenendo tutte le righe —
    e una riga persa in un conflitto è un giro che non è mai esistito.

    La chiave è `(run, pbi)`: rilanciare il comando è innocuo, ed è ciò che lo
    rende usabile come gesto di routine dopo ogni merge. L'ordine è quello di
    `iniziato`, che è l'ordine in cui i giri sono accaduti — non quello in cui
    qualcuno si è ricordato di registrarli.

    Il commit non lo fa questo comando: le righe si guardano e si portano su
    `main` con la loro PR (`chore(ci): registra i giri`), che è dove la
    responsabilità è già umana.
    """
    rapporti = sorted(Path(cartella).glob("*.json"))
    if not rapporti:
        print(f"Nessun rapporto in {cartella}: niente da registrare.")
        return 1

    nuove: list[dict] = []
    for f in rapporti:
        try:
            dati = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  ⚠️  {f.name} illeggibile: lo salto")
            continue

        # Due forme, e la vecchia va letta: i rapporti scritti prima di
        # `apri_rapporto()` sono una **lista nuda di esiti**, senza `run` e senza
        # `stato`. Sono i giri già fatti, cioè esattamente ciò che questo comando
        # esiste per recuperare; il `run` lo dà il nome del file, che è il
        # timestamp con cui il giro è nato.
        if isinstance(dati, list):
            run, esiti = f.stem, dati
        elif isinstance(dati, dict):
            run, esiti = dati.get("run", f.stem), dati.get("esiti", [])
        else:
            print(f"  ⚠️  {f.name} non è un rapporto: lo salto")
            continue

        for e in esiti:
            # Un file storto non porta via gli altri: è la regola del lettore del
            # consuntivo — un lettore che esplode su una riga vecchia spegne la
            # pagina intera per una riga su seicento.
            if not isinstance(e, dict) or "pbi" not in e or "stato" not in e:
                print(f"  ⚠️  {f.name}: un esito senza pbi o senza stato, lo salto")
                continue
            # Niente tempo, niente riga: un `saltato` a zero sporcherebbe la media.
            if e["stato"] == "saltato":
                continue
            nuove.append(riga_di_registro(run, e))

    presenti: set[tuple[str, str]] = set()
    if CSV_TEMPI.exists():
        presenti = {(r["run"], r["pbi"])
                    for r in csv.DictReader(CSV_TEMPI.open(encoding="utf-8"))}
    nuove = [r for r in nuove if (r["run"], r["pbi"]) not in presenti]
    nuove.sort(key=lambda r: r["iniziato"])

    if not nuove:
        print(f"{CSV_TEMPI.name} è già aggiornato: {len(presenti)} righe, nessuna nuova.")
        return 0

    appendi_righe(nuove)
    for r in nuove:
        print(f"  + {r['run']}  {r['pbi']:<10} {r['stato']:<16} {r['durata_hms']:>9}")
    print(f"{len(nuove)} righe in {CSV_TEMPI}. Ora committale: "
          f"`git add {CSV_TEMPI.name}` e una PR chore(ci).")
    return 0


def appendi_righe(righe: list[dict]) -> None:
    """Append su `runs/tempi.csv`, con l'intestazione se il file nasce adesso."""
    CSV_TEMPI.parent.mkdir(exist_ok=True)
    nuovo = not CSV_TEMPI.exists()
    with CSV_TEMPI.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNE_CSV)
        if nuovo:
            w.writeheader()
        w.writerows(righe)


def riepilogo(tariffa: float | None) -> int:
    """Rilegge tutto lo storico dei tempi e lo somma. È la base della fattura."""
    if not CSV_TEMPI.exists():
        print(f"Nessun tempo registrato: {CSV_TEMPI.relative_to(REPO)} non esiste ancora.")
        return 1

    righe = list(csv.DictReader(CSV_TEMPI.open(encoding="utf-8")))
    per_pbi: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    # Gli stati non si sommano: un `fatto` e un `non convergente` con lo stesso
    # tempo di parete misurano la stessa fatica e raccontano due storie opposte.
    # La colonna «esiti» è ciò che quel tempo ha comprato.
    esiti_per_pbi: dict[str, Counter] = defaultdict(Counter)
    for r in righe:
        p = per_pbi[r["pbi"]]
        p["durata"] += float(r["durata_s"])
        p["agente"] += float(r["builder_s"]) + float(r["critic_s"])
        p["gate"] += float(r["gate_s"])
        p["esecuzioni"] += 1
        esiti_per_pbi[r["pbi"]][r.get("stato") or "?"] += 1

    def esiti(pbi: str) -> str:
        """`fatto·1 non convergente·1` — l'ordine è quello del conteggio."""
        return "  ".join(f"{stato}·{q}" for stato, q in esiti_per_pbi[pbi].most_common())

    print(f"\n{'PBI':<10} {'esec':>4} {'totale':>9} {'agente':>9} {'gate':>9}"
          + (f" {'costo':>10}" if tariffa else "") + "  esiti")
    print("-" * (44 + (11 if tariffa else 0)))
    tot = tot_agente = tot_gate = 0.0
    for pbi in sorted(per_pbi):
        d = per_pbi[pbi]
        tot, tot_agente, tot_gate = tot + d["durata"], tot_agente + d["agente"], tot_gate + d["gate"]
        riga = (f"{pbi:<10} {int(d['esecuzioni']):>4} {hms(d['durata']):>9} "
                f"{hms(d['agente']):>9} {hms(d['gate']):>9}")
        if tariffa:
            riga += f" {d['durata'] / 3600 * tariffa:>9.2f}€"
        print(f"{riga}  {esiti(pbi)}")
    print("-" * (44 + (11 if tariffa else 0)))
    riga = f"{'TOTALE':<10} {len(righe):>4} {hms(tot):>9} {hms(tot_agente):>9} {hms(tot_gate):>9}"
    if tariffa:
        riga += f" {tot / 3600 * tariffa:>9.2f}€"
    print(riga)

    # Il tempo di parete include i tentativi falliti e le attese: è il tempo davvero
    # occupato dalla macchina. Dirlo qui evita che la colonna venga letta per un'altra.
    tutti = Counter()
    for conteggi in esiti_per_pbi.values():
        tutti.update(conteggi)
    print("esiti: " + "  ".join(f"{stato}·{q}" for stato, q in tutti.most_common()))

    print(f"\nTotale = tempo di parete, tentativi falliti compresi. "
          f"«agente» = builder + critic, «gate» = test e build.")
    if tariffa:
        print(f"Tariffa applicata: {tariffa:.2f} €/h. Righe: {CSV_TEMPI.relative_to(REPO)}")
    return 0


def stampa_la_guardia_di_fase() -> int:
    """L'hook `PreToolUse` in forma di comando: JSON su stdin, `2` se si blocca.

    Perché `2` e non un JSON di rifiuto: sotto `--dangerously-skip-permissions`
    — cioè `bypassPermissions`, il modo in cui il runner lancia il Builder — la
    documentazione di Claude Code è netta, *«hooks remain active and can block
    via exit 2, but permissionDecision: "deny" does not block»*. Il sistema dei
    permessi è spento e l'hook è l'unico cancello rimasto: se sbaglia forma, non
    ferma niente e non lo dice a nessuno.

    Un guasto nostro **non** blocca. Un hook che esce `2` su un JSON che non sa
    leggere ferma ogni scrittura di ogni sessione aperta in questo repository, e
    la cura — modificare un file — è la cosa che ha appena vietato. Il confine
    invalicabile è il `pre-commit`; questo qui è il confine che *spiega*, e vale
    quanto vale la sua correttezza.
    """
    try:
        dato = json.loads(sys.stdin.read())
        percorso = (dato.get("tool_input") or {}).get("file_path")
        cartella = dato.get("cwd") or os.getcwd()
    except (json.JSONDecodeError, AttributeError, TypeError) as guasto:
        print(f"guardia di fase: stdin illeggibile ({guasto}), lascio passare", file=sys.stderr)
        return 0
    if not percorso:
        return 0  # non è una scrittura su un file: non ci riguarda
    ragione = guardia_di_fase(fase_corrente(Path(cartella)), percorso)
    if ragione is None:
        return 0
    print(ragione, file=sys.stderr)
    return 2


def test_nuovi_da_aprire() -> list[TestNuovo]:
    """I test su cui si chiede il permesso: quelli non ancora committati, e se non
    ce ne sono quelli dell'**ultimo commit**.

    Guardare solo l'albero non committato non chiudeva il ciclo: il commit RED,
    che la convenzione vuole e che il gate del rosso pretende di soli test,
    rendeva cieca la richiesta. Lo ha trovato il Builder al primo giro vero, il
    01/09, fermandosi con `STOP:` invece di inventarsi una via d'uscita.

    L'ultimo commit e basta, non tutto `BASE..HEAD`: dopo tre criteri i test dei
    primi due sono verdi, e la richiesta verrebbe rifiutata per «nato verde» su
    lavoro che il suo rosso l'aveva già avuto.
    """
    nuovi = test_nuovi_dellalbero()
    if nuovi:
        return nuovi
    if git("rev-list", "--count", f"{BASE}..HEAD") == "0":
        # Il branch nasce da `BASE`, quindi al primo `--chiedi-impl` di ogni giro
        # HEAD **è** il ramo di base: se lì l'ultimo commit fosse di soli test, il
        # Builder otterrebbe la produzione aperta senza aver scritto una riga.
        return []
    file = file_del_commit("HEAD")
    if any(e_file_di_produzione(v.percorso) for v in file):
        return []  # un commit misto non è un RED: il rosso non può essere esistito lì dentro
    return test_nuovi_del_commit("HEAD", file)


def chiedi_impl() -> int:
    """Il permesso di scrivere produzione, dato dal rosso e non dalla parola.

    Gira i test nati nell'albero e apre `IMPL` solo se **tutti** falliscono. Non
    è pignoleria sul singolo test: un test che passa al primo colpo dice che quel
    comportamento c'è già, e allora non è questo il commit in cui nasce — o è
    stato scritto in anticipo, che è la cosa che il lucchetto esiste per rendere
    impossibile.

    Le ragioni sono le stesse tre di `ESITI_MANCATI`, e non per pigrizia: chi
    legge il rifiuto qui e il rapporto del gate là deve trovare le stesse parole,
    o crederà di avere davanti due controlli diversi.
    """
    fase = fase_corrente(REPO)
    if fase != FASE_TEST_ONLY:
        print(f"Niente da aprire: il giro non è in {FASE_TEST_ONLY} "
              f"(fase: {fase or 'nessuna'}). Il permesso si chiede una volta per "
              f"comportamento, e il giro torna in {FASE_TEST_ONLY} dopo il commit.")
        return 1
    nuovi = test_nuovi_da_aprire()
    if not nuovi:
        print("Non c'è nessun test nuovo nell'albero, quindi nessun rosso da osservare. "
              "Scrivi prima il test del comportamento che ti serve.")
        return 1
    comandi, orfani = comandi_dei_test(REPO, nuovi)
    mancati: list[tuple[str, list[str]]] = []
    if orfani:
        mancati.append((ESITI_MANCATI["nessuno"], orfani))
    for comando in comandi:
        esiti, _ = esiti_del_comando(comando)
        per_lettura: dict[str, list[str]] = defaultdict(list)
        for chiave, etichetta in comando.etichette.items():
            if esiti[chiave] != "rosso":
                per_lettura[esiti[chiave]].append(etichetta)
        for esito, elenco in per_lettura.items():
            mancati.append((ESITI_MANCATI[esito], elenco))
    if mancati:
        print(f"Il permesso resta chiuso: su {len(nuovi)} test nuovi il rosso non "
              f"si è visto dappertutto.\n")
        for ragione, elenco in mancati:
            for etichetta in elenco:
                print(f"  {etichetta}")
            print(f"    → {ragione}\n")
        return 1
    percorso_della_fase(REPO).write_text(f"{FASE_IMPL}\n", encoding="utf-8")
    print(f"Rosso osservato su {len(nuovi)} test nuovi: la fase passa a {FASE_IMPL}. "
          f"Ora scrivi il minimo che li fa passare.")
    return 0


# Il `pre-commit` che il runner installa. Inerte fuori da un giro, come l'hook di
# Claude Code e per la stessa ragione: sta in `.git/hooks`, che i worktree di
# questo repository condividono, e non deve farsi sentire da chi non è in un giro.
GUARDIA_DEL_COMMIT = """#!/bin/sh
# Installato da tools/asdlc_runner.py (PBI-104): il commit non nasce fuori fase.
exec python3 "$(git rev-parse --show-toplevel)/tools/asdlc_runner.py" --guardia-commit
"""


def installa_la_guardia_del_commit() -> bool:
    """Mette il `pre-commit` al suo posto. `False` se ce n'era già uno.

    Un `pre-commit` di qualcun altro non si calpesta: potrebbe essere un
    formattatore, o la cura di qualcosa che non sappiamo. Chi lo trova occupato
    lo legge e decide — il lucchetto perde il suo secondo livello e resta il
    primo, che è meglio di un hook altrui cancellato in silenzio.
    """
    return installa_un_hook("pre-commit", GUARDIA_DEL_COMMIT)


def cartella_degli_hook() -> Path | None:
    """`.git/hooks` di questo albero, o `None` se non si riesce a dirlo.

    Il controllo sulla forma del percorso non è paranoia: sotto i test `git` è
    sostituito e torna la stringa vuota, `Path("")` è la cartella corrente, e i
    due hook finivano nella radice del repository vero. Un dubbio su dove si sta
    scrivendo si risolve non scrivendo.
    """
    try:
        detto = git("rev-parse", "--git-path", "hooks")
    except RuntimeError:
        return None
    if not detto or Path(detto).name != "hooks":
        return None
    cartella = Path(detto)
    return cartella if cartella.is_absolute() else REPO / cartella


def installa_un_hook(nome: str, corpo: str) -> bool:
    """Scrive un hook di git in `.git/hooks`, e `False` se ce n'era già uno."""
    cartella = cartella_degli_hook()
    if cartella is None:
        return False
    cartella.mkdir(parents=True, exist_ok=True)
    hook = cartella / nome
    if hook.exists():
        return False
    hook.write_text(corpo, encoding="utf-8")
    hook.chmod(0o755)
    return True


# Il `post-commit` che chiude il ciclo. Il Builder fa molti criteri in una
# sessione e fra un commit e l'altro il runner non c'è: se `IMPL` restasse aperta
# dopo il primo permesso, il comportamento successivo tornerebbe a nascere senza
# rosso. Chi vede ogni commit è git, quindi è git a riportare la fase indietro.
RITORNO_IN_TEST_ONLY = f"""#!/bin/sh
# Installato da tools/asdlc_runner.py (PBI-104): un commit chiude il ciclo.
fase="$(git rev-parse --git-path {FILE_DELLA_FASE})"
[ -f "$fase" ] && printf '{FASE_TEST_ONLY}\\n' > "$fase"
exit 0
"""


def installa_il_ritorno_in_test_only() -> bool:
    return installa_un_hook("post-commit", RITORNO_IN_TEST_ONLY)


def apri_la_fase() -> None:
    """Accende il lucchetto per questo giro: i due hook di git, e `TEST_ONLY`.

    L'hook di Claude Code non si installa qui — sta in `.claude/settings.json`,
    versionato, e c'è già. Questi due no: `.git/hooks` non è nel repository, e un
    albero appena clonato non li avrebbe.
    """
    if cartella_degli_hook() is None:
        return  # non c'è un repository sotto: non c'è un giro da lucchettare
    installa_la_guardia_del_commit()
    installa_il_ritorno_in_test_only()
    percorso_della_fase(REPO).write_text(f"{FASE_TEST_ONLY}\n", encoding="utf-8")


def chiudi_la_fase() -> None:
    """Spegne il lucchetto. Un worktree lasciato in fase è un worktree in cui la
    sessione dopo non può scrivere, e la diagnosi costerebbe più del giro."""
    file = percorso_della_fase(REPO)
    if file is not None:
        file.unlink(missing_ok=True)


def guardia_del_commit() -> int:
    """Il `pre-commit`: ciò che è in stage deve stare nella fase corrente.

    Guarda lo **stage** e non il modo in cui ci è arrivato, ed è la differenza
    che conta: `Edit`, `Write`, un heredoc da Bash, `sed -i` e una patch applicata
    a mano finiscono tutti nello stesso posto, e qui valgono uguale.
    """
    fase = fase_corrente(REPO)
    if fase is None:
        return 0
    ragioni = [r for percorso in git("diff", "--cached", "--name-only").splitlines()
               if percorso and (r := guardia_di_fase(fase, percorso))]
    if not ragioni:
        return 0
    print(f"Il commit non si fa: il giro è in {fase}.\n")
    for ragione in ragioni:
        print(f"  {ragione}\n")
    return 1


def stampa_il_gate_del_rosso(ref: str) -> int:
    """Il gate senza il giro intorno: `--gate-rosso [ref]`.

    Due usi che il gate dentro il giro non copre: provarlo su un branch già chiuso —
    è così che si guarda `pbi/pbi-330` — e rileggere un `fermato` senza rifare
    mezz'ora di Builder.
    """
    # `BASE..REF` oltre al solo `REF`: un branch già mergiato non ha più commit
    # fuori dal ramo di base, ed è lì che sta la prova sul caso vero — `pbi/pbi-330`
    # è entrato in main mentre PBI-103 lo usava come banco di prova.
    base, separatore, solo_ref = ref.partition("..")
    if not separatore:
        base, solo_ref = BASE, ref
    morsi: list[dict[str, str]] = []
    try:
        mancati = gate_del_rosso(base=base, ref=solo_ref, morsi=morsi)
    except GuastoDelGate as guasto:
        # `2` e non `1`: chi lancia il gate a mano deve distinguere «il rosso non
        # c'è stato» da «il gate non ha potuto guardare».
        print(f"Il gate non ha potuto guardare {base}..{solo_ref}: {guasto}")
        return 2
    if morsi:
        print(f"{len(morsi)} test nati verdi che mordono, in {base}..{solo_ref}:\n")
        for m in morsi:
            print(f"  {m['commit']}  {m['titolo']}\n    {m['test']}\n"
                  f"{descrizione_del_morso(m, '    ')}\n")
    if not mancati:
        print(f"Il rosso c'è stato: in {base}..{solo_ref} nessun test è nato verde.")
        return 0
    print(f"{len(mancati)} commit in cui il rosso non si è mai visto, in {base}..{solo_ref}:\n")
    for m in mancati:
        print(f"  {m['commit']}  {m['titolo']}\n    {m['test']}\n    → {m['esito']}\n")
    print("Il ciclo mancato è ex ante: nessuna fix lo annulla, la lettura la fa una persona.")
    return 1


def costruisci_parser() -> argparse.ArgumentParser:
    """I flag, in una funzione sua: così si possono provare senza eseguire un PBI."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("pbi", nargs="*", help="es. PBI-201 PBI-202")
    ap.add_argument("--e2e", action="store_true",
                    help="non fa più niente: il gate Playwright è della CI, non del runner "
                         "(ADR-0009, difetto 13 di PBI-102). Il flag resta per dirlo")
    ap.add_argument("--dry-run", action="store_true", help="stampa il prompt e non esegue niente")
    ap.add_argument("--no-pr", action="store_true", help="non aprire la PR (resta solo il branch locale)")
    ap.add_argument("--senza-critic", action="store_true",
                    help="salta il Review Gate: restano i gate deterministici e la PR. "
                         "Il giro lo dichiara in runs/tempi.csv")
    ap.add_argument("--continua-sui-rossi", action="store_true",
                    help="prosegui col PBI successivo anche se questo è rimasto rosso")
    ap.add_argument("--in-primo-piano", action="store_true",
                    help="non staccarsi dalla sessione: output a schermo e exit code. "
                         "Di default il giro si stacca e scrive in runs/<run>.log")
    ap.add_argument("--registra", nargs="?", const=str(LOG_DIR), metavar="CARTELLA",
                    help="non esegue niente: piega i rapporti runs/*.json in runs/tempi.csv. "
                         "Si lancia su main dopo il merge (ADR-0020)")
    ap.add_argument("--gate-rosso", nargs="?", const="HEAD", metavar="REF",
                    help=f"non esegue niente: cammina {BASE}..REF e dice in quali "
                         "commit un test è nato senza essere mai stato rosso")
    ap.add_argument("--guardia-commit", action="store_true",
                    help="non esegue niente: il pre-commit del giro — ciò che è in stage "
                         "deve stare nella fase corrente")
    ap.add_argument("--chiedi-impl", action="store_true",
                    help="non esegue un PBI: gira i test nati nell'albero e apre la fase "
                         "IMPL solo se li vede fallire")
    ap.add_argument("--guardia-fase", action="store_true",
                    help="non esegue niente: legge su stdin il JSON di un hook PreToolUse "
                         "e esce 2 se quella scrittura non si può fare nella fase corrente")
    ap.add_argument("--riepilogo", action="store_true",
                    help="non esegue niente: somma i tempi già registrati in runs/tempi.csv")
    ap.add_argument("--tariffa", type=float, metavar="EUR_ORA",
                    help="tariffa oraria: aggiunge la colonna del costo")
    return ap


def main() -> int:
    ap = costruisci_parser()
    a = ap.parse_args()

    if a.registra:
        return registra(Path(a.registra))
    if a.riepilogo:
        return riepilogo(a.tariffa)
    if a.guardia_commit:
        return guardia_del_commit()
    if a.chiedi_impl:
        if aggiunto := venv_sul_path():
            print(f"venv del worktree sul PATH: {aggiunto}")
        return chiedi_impl()
    if a.guardia_fase:
        return stampa_la_guardia_di_fase()
    if a.gate_rosso:
        # Il venv serve anche qui: i test di quel commit li fa girare `pytest`.
        if aggiunto := venv_sul_path():
            print(f"venv del worktree sul PATH: {aggiunto}")
        return stampa_il_gate_del_rosso(a.gate_rosso)
    if not a.pbi:
        ap.error("indica almeno un PBI, oppure usa --riepilogo")

    if a.e2e:
        # Il flag resta, e si ferma qui: cancellarlo darebbe un «unrecognized
        # arguments» a chi se lo ricorda, e quel messaggio non spiega niente.
        print("Non parto: il gate e2e non è del runner.\n"
              "`npm run e2e` da un worktree punta a localhost:8081 — lo stack del "
              "checkout principale, cioè `main` — e produce un rosso che parla di un "
              "altro codice: 33 minuti su PBI-320, col Critic mai chiamato.\n"
              "Gli E2E girano nella CI sulla PR, che lo stack lo costruisce dal branch "
              "(ADR-0009, .github/workflows/ci.yml). A mano, sullo stack del branch: "
              "e2e/README.md.")
        return 2

    if aggiunto := venv_sul_path():
        print(f"venv del worktree sul PATH: {aggiunto}")

    attivi: set[str] = set()
    run = datetime.now().strftime("%Y%m%d-%H%M%S")
    LOG_DIR.mkdir(exist_ok=True)
    esiti: list[Esito] = []

    # Il distacco sta **prima** del lucchetto, e non è un dettaglio d'ordine: il
    # `flock` vive nell'open file description del processo che l'ha preso, quindi
    # un padre che lo prendesse e poi morisse forkando se lo porterebbe via.
    if va_staccato(a.in_primo_piano, os.getpid(), os.getsid(0)):
        stacca(run)

    # I due controlli stanno **qui**, prima del primo PBI: presi a metà giro non
    # servono a niente, perché a quel punto l'albero è già scritto da due mani.
    with ExitStack() as albero:
        try:
            albero.enter_context(lucchetto())
        except AlberoOccupato as exc:
            print(f"Non parto: {exc}.\n"
                  "Il lucchetto è di un runner vivo — `ps aux | grep asdlc_runner` dice "
                  "quale.\nPer un secondo giro in parallelo serve un altro worktree, non "
                  "un altro processo.")
            return 2

        estranei = agenti_estranei(REPO)
        if estranei:
            print(f"Non parto: qualcun altro sta già lavorando in {REPO}.")
            for pid, cmd in estranei:
                print(f"  PID {pid} — {cmd[:100]}")
            print("Due agenti sullo stesso albero si sovrascrivono i file a vicenda e i "
                  "commit escono mescolati.\nChiudi quello di troppo, o dai a questo un "
                  "worktree suo.")
            return 2

        # Un `--dry-run` stampa il prompt e non esegue niente: pretendere i gate lì
        # vorrebbe dire non poter leggere un prompt su una macchina qualsiasi.
        if not a.dry_run and (mancano := gate_mancanti(attivi)):
            print(f"Non parto: {len(mancano)} gate su questa macchina non può girare — "
                  f"{', '.join(mancano)}.")
            print("Le dipendenze di test si installano da backend/requirements-dev.txt:\n"
                  "  backend/.venv/bin/pip install -r backend/requirements-dev.txt\n"
                  "Un gate che non gira lo si scopre in tre secondi qui, o in mezz'ora "
                  "dopo il Builder, su un rosso che sembra un errore del codice.")
            return 2

        # Il rapporto si apre **adesso**, non a giro finito: un giro che muore a metà
        # deve aver lasciato scritto che è esistito (difetto 20).
        apri_rapporto(run, list(a.pbi))

        for pbi in a.pbi:
            try:
                e = esegui_pbi(pbi, attivi, a.dry_run, con_pr=not a.no_pr,
                               con_critic=not a.senza_critic, run=run)
            except Exception as exc:  # noqa: BLE001 — qui si cattura per non perdere il resto
                # Un guasto dentro un PBI è un esito di **quel** PBI. Prima usciva
                # da `main()` col traceback e si portava via la sequenza intera, e
                # con lei i rilievi del Critic dei PBI già chiusi (difetto 17).
                # Lo stato è `rosso` perché è già nella regola che decide se
                # proseguire: non serve un'eccezione al posto di una regola.
                traceback.print_exc()
                e = Esito(pbi, "rosso", nota=f"eccezione nel runner: {exc}"[:300],
                          iniziato=datetime.now().isoformat(timespec="seconds"),
                          finito=datetime.now().isoformat(timespec="seconds"))
            esiti.append(e)
            # Ogni PBI concluso è già su disco quando parte il successivo.
            scrivi_rapporto(run, esiti, "in-corso")
            print(f"  → {e.stato}" + (f" ({e.nota})" if e.nota else ""))
            # Un PBI rosso, respinto o fermo su una domanda è un fatto da guardare, non da
            # superare: i PBI successivi molto spesso poggiano su questo.
            if e.stato in STATI_CHE_INTERROMPONO and not a.continua_sui_rossi:
                print("\nInterrotto. La catena dei PBI ha dipendenze dichiarate: proseguire su "
                      "una base rossa costa più di quanto risparmia.")
                break

        # Il registro **non** si scrive qui: siamo dentro il worktree del PBI, e
        # una riga in coda a un file versionato è il conflitto del difetto 19
        # (`ADR-0020`). Il giro lascia il suo rapporto; le righe entrano in `main`
        # dopo il merge, con `--registra`.
        rapporto = chiudi_rapporto(run, esiti)
        print(f"\nRegistro: `python3 tools/asdlc_runner.py --registra {LOG_DIR}` "
              f"su main, dopo il merge. Rapporto del giro: {rapporto}")
        totale = sum(e.durata_s for e in esiti)
        print(f"\n{len(esiti)} PBI · tempo totale {hms(totale)}"
              + (f" · {totale / 3600 * a.tariffa:.2f} €" if a.tariffa else ""))
        print(f"Rapporto: runs/{run}.json · tempi: runs/tempi.csv")
        return 0 if all(e.stato in ("fatto", "saltato") for e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
