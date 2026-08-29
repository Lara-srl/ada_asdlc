#!/usr/bin/env python3
"""Esegue i PBI uno per volta: Builder → gate deterministici → Critic → PR.

Il principio è quello di `asdlc-skill/practices/workflow-as-code.md`: l'orchestrazione
è deterministica (branch, gate, retry, stop), probabilistico è solo ciò che richiede
intelligenza — scrivere il codice, e giudicarlo.

Tre livelli di verifica, come in `patterns/context-gates.md`, e sono tre cose diverse:

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
import csv
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG_DIR = REPO / "runs"
CSV_TEMPI = LOG_DIR / "tempi.csv"
# Il worktree è uno solo e non aveva un lucchetto: vedi `lucchetto()`.
LUCCHETTO = LOG_DIR / ".runner.lock"

# Chi, girando in questo albero, ci **scrive**. Un `tail -f` sul log o un `git log`
# aperto non sono un pericolo, e un controllo che grida sempre si impara a spegnere.
AGENTI = ("claude", "asdlc_runner")

# I flag di autonomia e di routing stanno qui, in un posto solo, così si vedono e si
# cambiano. ⚠️ Verifica i nomi con `claude --help`: cambiano fra versioni della CLI.
BUILDER = ["claude", "-p", "--dangerously-skip-permissions"]
# Model routing (patterns/model-routing.md): il giudizio costa più della generazione,
# e il Critic non scrive niente — solo lettura e `git diff`.
# ⚠️ `--allowedTools <tools...>` è **variadico**: se resta in coda si mangia il prompt,
# che viene concatenato subito dopo, e `-p` parte senza input. Il flag variadico non
# deve mai essere l'ultimo. Il Builder non ne soffre perché i suoi flag sono booleani.
CRITIC = ["claude", "-p", "--allowedTools", "Read,Grep,Glob,Bash(git diff:*)", "--model", "opus"]

MAX_TENTATIVI = 3   # gate rossi: oltre, il problema non è che l'agente non ci ha provato
# Giri spesi a **chiedere un commit**, contati a parte. Non sono la stessa cosa di un gate
# rosso — quello è «hai sbagliato una riga», questo è «il lavoro c'è ma non è durevole» —
# e sommarli è costato a PBI-208 tutti e tre i tentativi senza che un gate girasse mai:
# `git commit -am` non prende i file non tracciati, e la pagina che l'agente aveva scritto
# è rimasta fuori da ogni commit. Un tetto ci vuole lo stesso: un Builder che non riesce a
# committare non migliora girando, e senza numero girerebbe finché non finisce la notte.
MAX_IGIENE = 3
# Backstop, non criterio. Il criterio giusto è «smetti quando un giro non produce più
# niente di bloccante», e il Critic quel segnale lo emette già da sé — distingue una
# violazione da un «non è una violazione, ma va detto». È il runner a non leggerlo
# (PBI-102). Finché non lo legge, serve un numero, e questo è tarato su una misura:
# PBI-201 ha richiesto sei revisioni, e i due difetti peggiori — il criterio centrale
# che si skippava su ogni runner, una decisione autocertificata da chi ne beneficiava —
# sono usciti al quarto e al quinto giro. Con 2 il runner avrebbe chiuso prima di
# vederli, dichiarando «il PBI non era pronto»: vero e fuorviante insieme.
MAX_REVISIONI = 4

# Gli stati dopo i quali non si prosegue. `sospeso` sta qui insieme a `fermato`
# per la stessa ragione — sono tutti e due «fermo su una domanda» — e la domanda
# aperta è precisamente ciò che non si supera andando avanti.
# ⚠️ `respinto` non è assegnato da nessuna parte: PBI-102 lo ha sostituito con
# `non convergente` sul caso «revisioni esaurite», e la diagnosi che gli resterebbe —
# *il PBI non era pronto a partire*, riconosciuta al primo giro invece che all'ultimo —
# è il segnale che quel PBI ha proposto e rinviato (`BLOCCANTI: n`). Sta qui e non si
# toglie perché è un'intenzione, non codice morto: cancellarlo perderebbe la distinzione
# che PBI-102 ha introdotto, e chi legge `runs/tempi.csv` deve sapere che quello stato
# esiste e che nessuna run lo porta ancora.
STATI_CHE_INTERROMPONO = ("rosso", "respinto", "non convergente", "fermato", "sospeso")

COLONNE_CSV = [
    "run", "pbi", "stato", "iniziato", "finito", "durata_s", "durata_hms",
    "builder_s", "gate_s", "critic_s", "tentativi", "revisioni", "commit", "pr", "nota",
]


@dataclass
class Gate:
    nome: str
    comando: list[str]
    cwd: str = "."
    solo_se: str | None = None  # flag che lo accende (es. "e2e")


GATE: list[Gate] = [
    Gate("pytest", ["pytest", "-q"], cwd="backend"),
    Gate("tsc", ["npm", "run", "build"], cwd="frontend"),
    Gate("eslint", ["npm", "run", "lint"], cwd="frontend"),
    Gate("vitest", ["npm", "test"], cwd="frontend"),
    # Niente e2e qui: `npm run e2e` da un worktree punta a localhost:8081, che è
    # lo stack del checkout principale — cioè `main`, non il branch che si sta
    # costruendo. Lo stack andrebbe rialzato a ogni giro del Builder, e questo non
    # lo fa. Gli E2E li fa la CI sulla PR, che lo stack lo costruisce dal branch
    # (`ADR-0009`, difetto 13 di PBI-102).
]

PROMPT_BUILDER = """Sei l'ingegnere di questo repository. Lavori in ASDLC: la spec è lo stato, il PBI è il delta.

Leggi, in quest'ordine:
1. AGENTS.md — confini di giudizio e toolchain
2. {pbi_path} — il PBI da eseguire: direttiva, scope, verifica, protocollo di rifinitura
3. le spec e gli ADR che il PBI cita — sono puntatori, non decorazione

Esegui il PBI con queste regole non negoziabili:

- **TDD**: scrivi PRIMA il test che fallisce, poi il codice che lo fa passare.
- **Micro-commit**: committa dopo ogni pezzo che sta in piedi da solo — un test aggiunto,
  una funzione che compila, un modulo che passa il lint. Un PBI produce tipicamente 3-5
  commit. Non accumulare tutto in un commit finale: i commit sono i punti di ripristino,
  e uno solo non ripristina niente. **Non fare squash**: al merge ci pensa la PR.
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
- Resta dentro lo **scope** dichiarato dal PBI. Se ti serve toccare altro, fermati e dillo.
- Se il PBI cambia un contratto, aggiorna la spec NELLO STESSO commit del codice.
- Non lasciare modifiche non committate: ciò che non è committato non esiste.
- Non toccare .github/workflows/ (il push verrebbe rifiutato dal token).
- **Non pubblicare niente**: nessun `git push`, nessun `gh pr create`. Al branch e alla PR
  ci pensa il runner, quando il Critic ha finito. Un branch pushato a metà giro è una
  promessa fatta su lavoro che nessuno ha ancora accettato — su PBI-324 quella promessa è
  stata riscossa con un merge, e in `main` è entrato un terzo del lavoro con la sua
  checklist spuntata.

Se incontri un'ambiguità che il protocollo di rifinitura non copre, NON scegliere in
silenzio: fermati, scrivi la domanda, e termina con la riga esatta

    STOP: <la domanda>

Quando hai finito, termina con la riga esatta

    FATTO: <riepilogo in una riga>
"""

PROMPT_IGIENE = """Ci sono modifiche non committate:

{sporco}

Committale con micro-commit coerenti. **`git add` esplicito**, o `git add -A`: i file nuovi
non sono tracciati, e `git commit -am` li lascia fuori senza dire niente — è così che una
pagina intera è rimasta a un `git add` dal non esistere. Finché l'albero è sporco il lavoro
non è giudicabile e i gate non partono. Termina con FATTO: oppure STOP: come prima.
"""

PROMPT_RIPROVA = """I gate sono rossi. Output (troncato):

{esiti}

Correggi la causa, non il sintomo: se un test è sbagliato lo si corregge, se è giusto si
corregge il codice. Non disattivare test, non marcare skip, non allargare tolleranze.
Committa la correzione con un commit suo. Termina con FATTO: oppure STOP: come prima.
"""

PROMPT_CRITIC = """Sei un **Critic Agent** e fai una revisione avversariale secondo ASDLC.

Il tuo ruolo è scettico per costruzione: respingi il codice che viola la spec o i confini
di AGENTS.md **anche se funziona e anche se i test passano**. Preferisci un falso positivo
a un falso negativo. Non sei qui per essere utile: sei qui per trovare ciò che è sfuggito.

## Contratti da caricare
- `AGENTS.md` — i confini di giudizio (la costituzione di questo repository)
- `{pbi_path}` — direttiva, **scope**, criteri di verifica
- le spec e gli ADR che il PBI cita

## Artefatto da giudicare
Il diff del branch corrente: `git diff origin/main...HEAD`
I commit: `git log --oneline origin/main..HEAD`

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

## Formato di uscita
Se non ci sono violazioni, termina con la riga esatta:

    VERDETTO: PASS

Se invece trovi un rilievo che **nessuna correzione può chiudere** — perché la risposta è
di una persona: una decisione di dominio, un `CHIEDI` di AGENTS.md saltato, una violazione
*ex ante* che chi l'ha commessa non può annullare — non mandare il Builder a girare a
vuoto. Scrivi la domanda e termina con le due righe esatte:

    STOP: <la domanda per la persona>
    VERDETTO: SOSPESO

È la stessa diagnosi che il Builder produce quando incontra un'ambiguità, raggiunta
dall'altro lato. Un sospeso senza la riga `STOP:` non è una diagnosi: lascia una persona
davanti a un muro, e vale come guasto.

Altrimenti elenca ogni violazione come

    **N. [categoria]: descrizione breve**
    - Violato: <clausola della spec o di AGENTS.md>
    - Impatto: <perché conta>
    - Rimedio: <come si chiude>

e termina con la riga esatta:

    VERDETTO: NON PRONTO
"""

PROMPT_RIMEDIO = """Sei l'ingegnere di questo repository. Lavori in ASDLC: la spec è lo stato, il PBI è il delta.

Un giro precedente ha scritto del codice e il Critic lo ha respinto. **La sessione è
nuova: quello che sai è solo ciò che leggi qui sotto.** Rileggi, in quest'ordine:

1. AGENTS.md — confini di giudizio e toolchain
2. {pbi_path} — il PBI: direttiva, scope, verifica, protocollo di rifinitura
3. `git log --oneline origin/main..HEAD` e `git diff origin/main...HEAD` — il lavoro già
   fatto, che è tuo anche se non lo ricordi: non rifarlo e non disfarlo
4. le spec e gli ADR che il PBI e il rapporto citano

Rapporto del Critic:

{rapporto}

Chiudi ogni violazione, una alla volta, con **un commit per rimedio** e lo stesso formato
del resto del PBI (`tipo(scope): descrizione imperativa`, in italiano). Valgono tutte le
regole di prima: test-first, la spec nello stesso commit del codice che ne cambia il
comportamento, niente modifiche non committate.

**Un rilievo non si chiude spegnendo ciò che lo ha trovato.** Cancellare un test, allargare
una tolleranza o aggiungere uno `skip` fa passare il gate e disfa la cosa che il gate
proteggeva: se una violazione si chiude solo così, non è una violazione da chiudere ed è il
caso qui sotto.

Se ritieni che una violazione sia infondata, NON ignorarla: spiega perché nella risposta e
lasciala aperta. Termina con FATTO: oppure STOP: come prima.
"""


@dataclass
class Verdetto:
    """Cosa ha detto il Critic. Tre esiti, non due.

    ``non pronto`` e ``sospeso`` sembrano vicini e sono opposti: il primo dice
    «c'è del lavoro da fare», il secondo «il lavoro non può proseguire finché
    qualcuno non risponde». Confonderli manda il Builder a correggere ciò che
    nessuna correzione chiude — su PBI-203 sono stati quattro giri buttati.
    """

    esito: str  # pass | non pronto | sospeso
    domanda: str  # valorizzata solo su `sospeso`
    rapporto: str


@dataclass
class Esito:
    pbi: str
    # fatto | rosso | respinto | non convergente | fermato | sospeso | saltato
    #
    # `fermato` e `sospeso` sono tutti e due «aspetta una persona», e restano
    # distinti perché il rimedio è diverso: `fermato` arriva dal Builder e si
    # chiude riscrivendo il PBI che era ambiguo; `sospeso` arriva dal Critic e si
    # chiude rispondendo alla domanda.
    stato: str
    tentativi: int = 0
    revisioni: int = 0
    commit: int = 0
    nota: str = ""
    pr: str = ""
    rapporto_critic: str = ""
    # Il Review Gate è stato saltato (`--senza-critic`). Un booleano e non una
    # frase dentro `nota`: la nota la legge una persona, questo lo legge il corpo
    # della PR, che deve dire il vero senza doverla interpretare.
    critic_saltato: bool = False
    # Un dizionario per gate caduto — `{"gate": nome, "coda": ultimo output}` — e
    # non il solo nome: il verdetto senza la ragione obbliga a rifar girare la
    # suite per sapere quale test, o ad avere ancora il Builder sotto mano
    # (difetto 14). La coda ce l'abbiamo già: `gira_gate` la restituisce.
    gate_rossi: list[dict[str, str]] = field(default_factory=list)
    # Tempi: il totale è il tempo di parete del PBI, il resto ne è la scomposizione.
    iniziato: str = ""
    finito: str = ""
    durata_s: float = 0.0
    tempi: dict[str, float] = field(default_factory=lambda: defaultdict(float))


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
    """Mette `backend/.venv/bin` in testa al `PATH`, se c'è e non c'è già.

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
    bin_venv = REPO / "backend" / ".venv" / "bin"
    if not bin_venv.is_dir():
        return None
    if str(bin_venv) in os.environ.get("PATH", "").split(os.pathsep):
        return None
    os.environ["PATH"] = f"{bin_venv}{os.pathsep}{os.environ.get('PATH', '')}"
    return str(bin_venv)


def gate_mancanti(attivi: set[str]) -> list[str]:
    """I gate accesi il cui comando non esiste su questa macchina.

    `backend/requirements.txt` è il file del runtime e `pytest` non c'è: un
    worktree nuovo nasce senza il gate più importante, e senza questo controllo
    lo scopre dopo mezz'ora di Builder, su un gate rosso che sembra un errore del
    codice (difetto 21). Si guardano solo i gate accesi: `--e2e` spento non deve
    pretendere lo stack Playwright.
    """
    return [g.nome for g in GATE
            if (g.solo_se is None or g.solo_se in attivi)
            and shutil.which(g.comando[0]) is None]


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
    """
    LUCCHETTO.parent.mkdir(exist_ok=True)
    fd = LUCCHETTO.open("w")
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlberoOccupato(
                f"un altro runner sta già lavorando in {REPO} ({LUCCHETTO})"
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


def esegui(cmd: list[str], cwd: Path, timeout: int = 7200) -> tuple[int, str]:
    """Il varco verso il mondo. Un comando che non esiste torna `127`, non alza.

    `subprocess.run` alza `FileNotFoundError`, e l'eccezione saliva fino a
    `main()`: il processo moriva col traceback, senza riga nel registro e senza
    rapporto — un `pytest` non installato spegneva la sequenza invece di essere
    il gate rosso con la diagnosi più ovvia che ci sia (difetto 11). `127` è la
    convenzione della shell per «comando non trovato», e la nota dice quale.
    """
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        return 127, (f"comando non eseguibile: {cmd[0]} — {exc}\n"
                     f"le dipendenze dei gate stanno in backend/requirements-dev.txt")
    return p.returncode, (p.stdout + p.stderr)


def git(*args: str) -> str:
    code, out = esegui(["git", *args], REPO, timeout=120)
    if code != 0:
        raise RuntimeError(f"git {' '.join(args)} → {out}")
    return out.strip()


def gira_gate(attivi: set[str]) -> list[tuple[str, str]]:
    """Gate rossi con la coda del loro output. Lista vuota = tutto verde."""
    rossi: list[tuple[str, str]] = []
    for g in GATE:
        if g.solo_se and g.solo_se not in attivi:
            continue
        print(f"    gate {g.nome} … ", end="", flush=True)
        t0 = time.monotonic()
        code, out = esegui(g.comando, REPO / g.cwd, timeout=3600)
        print(f"{'verde' if code == 0 else 'ROSSO'} ({hms(time.monotonic() - t0)})")
        if code != 0:
            rossi.append((g.nome, out[-3000:]))
    return rossi


VERDETTI = {"VERDETTO: PASS": "pass",
            "VERDETTO: NON PRONTO": "non pronto",
            "VERDETTO: SOSPESO": "sospeso"}


def revisione_critica(pbi_path: Path) -> Verdetto:
    """Sessione NUOVA, modello diverso, sola lettura: il Critic non è il Builder."""
    print("    critic … ", end="", flush=True)
    try:
        percorso = pbi_path.relative_to(REPO)
    except ValueError:
        percorso = pbi_path
    _, out = esegui(CRITIC + [PROMPT_CRITIC.format(pbi_path=percorso)], REPO)

    # Un Critic che non emette un verdetto non ha giudicato: è un'invocazione fallita, e
    # trattarla come "NON PRONTO" rimanda il Builder a correggere violazioni che nessuno
    # ha trovato. Un guasto dello strumento deve somigliare a un guasto, non a un giudizio.
    esito = next((v for riga, v in VERDETTI.items() if riga in out), None)
    if esito is None:
        print("GUASTO")
        raise RuntimeError(f"il Critic non ha emesso un verdetto — output:\n{out[-2000:]}")

    domanda = ""
    if esito == "sospeso":
        if "STOP:" not in out:
            # Stessa regola del verdetto mancante, per la stessa ragione: sospendere
            # senza dire cosa si aspetta lascia una persona davanti a un muro, e un
            # muro non è una diagnosi.
            print("GUASTO")
            raise RuntimeError(
                f"il Critic ha sospeso senza scrivere la domanda — output:\n{out[-2000:]}"
            )
        domanda = out.split("STOP:")[-1].strip().splitlines()[0]

    print({"pass": "PASS", "non pronto": "NON PRONTO", "sospeso": "SOSPESO"}[esito])
    return Verdetto(esito, domanda, out)


def apri_pr(pbi: str, pbi_path: Path, branch: str, e: Esito) -> str:
    """Apre la PR e si ferma lì: il merge è dell'umano (micro-commits §5).

    È **qui** che il branch arriva su `origin`, e in nessun altro punto della
    strada buona: un ramo pubblicato prima che il Critic abbia parlato è una
    promessa fatta su lavoro che nessuno ha ancora accettato, e su PBI-324 quella
    promessa è stata riscossa con un merge di un terzo del lavoro (difetto 18).
    """
    if not pubblica(branch):
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
         "--body", corpo, "--base", "main", "--head", branch],
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
    return url.group(0)


def crea_branch(pbi: str) -> str:
    """Il branch del PBI, sempre da `origin/main` fresco.

    ``git switch -c`` parte da dove si trova, e dove si trova è il branch del PBI
    precedente: due PBI nella stessa invocazione producevano branch **impilati**,
    col diff del secondo che conteneva il lavoro del primo. È il motivo per cui
    `ada-notte.sh` esiste come ciclo esterno invece di passare i PBI al runner in
    un colpo solo.

    Si ramifica **da `origin/main`**, senza estrarre il `main` locale. Non è un
    dettaglio di stile: il runner gira nel worktree `ada-run`, e un branch si può
    estrarre in un worktree solo. `main` sta quasi sempre estratto nel repository
    principale, quindi `git switch main` là dentro fallirebbe con *«already used
    by worktree»* — e ``git()`` alza, cioè il PBI morirebbe prima di cominciare.

    Scrivere il punto di partenza dentro il comando toglie anche l'altra domanda:
    non c'è un `main` locale da allineare, quindi non c'è il caso in cui è
    disallineato.
    """
    git("fetch", "origin", "main")
    branch = nome_libero(pbi, rami_su_origin(pbi))
    git("switch", "-c", branch, "origin/main")
    return branch


def rami_su_origin(pbi: str) -> set[str]:
    """I rami che `origin` ha già per questo PBI.

    Si chiede al remoto e non al locale: il worktree del runner è appena stato
    creato, e di un giro fallito tre giorni fa non sa niente.
    """
    fuori = git("ls-remote", "--heads", "origin", f"pbi/{pbi.lower()}*")
    return {r.split("refs/heads/")[-1].strip() for r in fuori.splitlines() if "refs/heads/" in r}


def nome_libero(pbi: str, presi: set[str]) -> str:
    """`pbi/pbi-322`, e se è occupato `pbi/pbi-322-giro2`.

    Il nome del branch era fisso, e un giro fallito lo lasciava occupato su
    `origin`: il rilancio o moriva su *«esiste già un ramo»*, o — peggio — ci
    scriveva sopra una storia diversa e il push finale si prendeva un
    `non-fast-forward` a lavoro fatto. Difetto 16 di PBI-102, misurato su PBI-322
    la notte del 26→27/08.

    Il numero è del **giro**, non del PBI: dice quante volte ci si è provati, che
    è l'informazione che serve a chi apre la lista dei rami.
    """
    base = f"pbi/{pbi.lower()}"
    if base not in presi:
        return base
    n = 2
    while f"{base}-giro{n}" in presi:
        n += 1
    return f"{base}-giro{n}"


def pubblica(branch: str) -> bool:
    """Manda il branch su `origin`. Non alza mai: pubblicare è l'ultimo gesto.

    Due cose, che sono le due cause del difetto 18. **`--force-with-lease`**
    perché il branch è nostro e fra un giro e l'altro può essere stato riscritto —
    un rebase, un `commit --amend` sui messaggi — e un push semplice si prende il
    `non-fast-forward` che su PBI-324 ha ucciso il processo con quattro giri di
    lavoro dentro. Il lease non è `--force` cieco: se qualcun altro ha scritto su
    quel ramo il push si rifiuta lo stesso, che è la sola cosa da proteggere.

    E **non alza**: un push che fallisce è una brutta notizia, non una ragione per
    buttare via l'ora precedente. Chi legge il log la trova scritta, e i commit
    restano nel worktree.
    """
    try:
        git("push", "--force-with-lease", "-u", "origin", branch)
        return True
    except RuntimeError as exc:
        print(f"    ⚠️  branch non pubblicato: {str(exc)[:200]}")
        print(f"       i commit restano in locale su {branch}: `git push` a mano quando "
              f"hai guardato cosa c'è sul remoto.")
        return False


def trova_pbi(pbi: str) -> Path | None:
    """Il file del PBI come lo vede `origin/main`, non come lo vede il worktree.

    Il runner gira in `ada-run`, un albero che resta fermo al commit su cui
    qualcuno l'ha messo l'ultima volta. Il branch invece nasce **sempre** da
    `origin/main` (`crea_branch`): un PBI mergiato dopo quell'ultimo `switch` c'è
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
    try:
        git("fetch", "origin", "main")
        voci = git("ls-tree", "--name-only", "origin/main", "backlog/").splitlines()
    except RuntimeError as exc:
        print(f"    ⚠️  origin/main non raggiungibile ({str(exc)[:120]}): "
              f"cerco {pbi} nell'albero estratto")
        return next(REPO.glob(f"backlog/{pbi}-*.md"), None)

    nome = next((v.strip() for v in voci
                 if Path(v.strip()).name.startswith(f"{pbi}-") and v.strip().endswith(".md")), None)
    return REPO / nome if nome else None


def esegui_pbi(
    pbi: str, attivi: set[str], dry: bool, con_pr: bool, con_critic: bool = True
) -> Esito:
    pbi_path = trova_pbi(pbi)
    if pbi_path is None:
        return Esito(pbi, "saltato", nota="PBI inesistente in backlog/ su origin/main")

    print(f"\n=== {pbi} — {pbi_path.name}")
    prompt = PROMPT_BUILDER.format(pbi_path=pbi_path.relative_to(REPO))
    if dry:
        print(prompt)
        return Esito(pbi, "saltato", nota="dry-run")

    if git("status", "--porcelain", "--", ":(exclude)runs"):
        return Esito(pbi, "fermato", nota="albero di lavoro sporco: committa o pulisci prima")

    # `runs/` è escluso e non per comodità: il controllo esiste per non far partire
    # l'agente sopra al lavoro non committato di qualcun altro, e `runs/tempi.csv` è
    # la contabilità del runner, che il runner stesso scrive a fine invocazione.
    # Contarla renderebbe ogni giro il giro sporco del successivo.
    e = Esito(pbi, "rosso", iniziato=datetime.now().isoformat(timespec="seconds"))
    t0 = time.monotonic()
    branch = crea_branch(pbi)

    def conta_commit() -> int:
        """`origin/main..HEAD` e non `main..HEAD`: da quando il main locale del
        worktree non si estrae più, resta indietro di giorni e conterebbe come
        commit del PBI tutto ciò che main ha ricevuto nel frattempo."""
        try:
            return int(git("rev-list", "--count", "origin/main..HEAD") or 0)
        except (RuntimeError, ValueError):
            return e.commit  # un conteggio mancato non cancella quello di prima

    def chiudi(stato: str, nota: str = "") -> Esito:
        # Il conteggio sta **qui** e non dopo il giro dei gate: ogni uscita
        # anticipata — lo `STOP` del Builder, l'albero che resta sporco — scriveva
        # `commit = 0` mentre sul branch c'era il lavoro. Su PBI-209 erano otto
        # commit e 2.174 righe, e la colonna del registro diceva zero: è quella
        # che si guarda per decidere se un branch fermato si butta (difetto 10).
        e.commit = conta_commit()
        e.stato, e.durata_s = stato, time.monotonic() - t0
        e.finito = datetime.now().isoformat(timespec="seconds")
        if nota:
            e.nota = nota
        # Un giro che si ferma ha comunque prodotto commit, e lasciarli solo nel
        # worktree vuol dire non farli guardare a nessuno: su PBI-320 sono rimasti
        # lì, su PBI-322 li ha salvati a mano una persona prima di chiudere il
        # terminale. Difetto 8 di PBI-102. Sulla strada buona non si pubblica qui:
        # a quello ci pensa `apri_pr`, una volta sola.
        if stato in STATI_CHE_INTERROMPONO:
            pubblica(branch)
        print(f"    tempo: {hms(e.durata_s)} "
              f"(builder {hms(e.tempi['builder'])} · gate {hms(e.tempi['gate'])} · "
              f"critic {hms(e.tempi['critic'])})")
        return e

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
            cmd = BUILDER + ([] if primo_del_giro else ["-c"]) + [prompt]
            primo_del_giro = False
            with misura(e, "builder"):
                _, out = esegui(cmd, REPO)

            if "STOP:" in out:
                domanda = out.split("STOP:")[-1].strip().splitlines()[0]
                return chiudi("fermato", f"domanda dell'agente: {domanda}")

            # `runs/` escluso qui come all'ingresso, e per la stessa ragione: nella catena
            # il secondo PBI troverebbe la riga di registro del primo e si sentirebbe
            # chiedere di committare la contabilità del runner dentro il suo branch.
            if sporco := git("status", "--porcelain", "--", ":(exclude)runs"):
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

        # --- Review Gate (probabilistico, sessione separata) ---
        # Si può togliere, e allora **si dichiara**: `critic_s = 0` non spiega se
        # stesso — è la lezione di `gate_s = 0` su PBI-208, letto come «gate
        # rosso» invece che «i gate non sono mai girati». Chi rilegge il registro
        # deve sapere che quel giro ha avuto due gate su tre, non tre.
        if not con_critic:
            e.critic_saltato = True
            e.nota = "critic saltato (--senza-critic): revisione umana alla PR"
            print("    critic … saltato (--senza-critic)")
            break

        with misura(e, "critic"):
            verdetto = revisione_critica(pbi_path)
        rapporto = verdetto.rapporto
        e.rapporto_critic = rapporto[-6000:]
        if verdetto.esito == "pass":
            break
        if verdetto.esito == "sospeso":
            # Non si consuma una revisione e non si richiama il Critic: la sua
            # diagnosi non cambia riprovando, perché ciò che manca non è nel
            # repository. Riprovare qui è esattamente ciò che è costato a PBI-203
            # cinque giri e 1h26m per tornare al punto di partenza.
            return chiudi("sospeso", f"domanda del critic: {verdetto.domanda}")
        if revisione == MAX_REVISIONI:
            # **Non convergente, non respinto.** Sono due diagnosi diverse e confonderle
            # manda a correggere la cosa sbagliata: `respinto` dice che il PBI era scritto
            # male, `non convergente` che il lavoro non si è chiuso e serve una persona.
            # Chi legge runs/tempi.csv deve poter distinguere un PBI difficile da uno mal
            # posto, altrimenti il registro misura la fatica e non la causa.
            return chiudi("non convergente",
                          f"{MAX_REVISIONI + 1} revisioni senza convergere — ultimi rilievi "
                          f"del Critic nel rapporto JSON. Serve una lettura umana.")
        # Relativo come nel primo giro: è lo stesso percorso che il Builder ha già
        # letto, e un assoluto qui lo farebbe sembrare un altro file.
        prompt = PROMPT_RIMEDIO.format(
            rapporto=rapporto[-6000:], pbi_path=pbi_path.relative_to(REPO)
        )

    print(f"    commit sul branch: {e.commit} · "
          f"file: {git('diff', '--name-only', 'origin/main...HEAD')}")
    chiudi("fatto")

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
        for e in dati.get("esiti", []):
            # Niente tempo, niente riga: un `saltato` a zero sporcherebbe la media.
            if e.get("stato") == "saltato":
                continue
            nuove.append(riga_di_registro(dati.get("run", f.stem), e))

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
                               con_critic=not a.senza_critic)
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
