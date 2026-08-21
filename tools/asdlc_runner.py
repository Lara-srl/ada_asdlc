#!/usr/bin/env python3
"""Esegue i PBI uno per volta: Builder → gate deterministici → Critic → PR.

Il principio è quello di `asdlc-skill/practices/workflow-as-code.md`: l'orchestrazione
è deterministica (branch, gate, retry, stop), probabilistico è solo ciò che richiede
intelligenza — scrivere il codice, e giudicarlo.

Tre livelli di verifica, come in `patterns/context-gates.md`, e sono tre cose diverse:

  1. Quality Gate  (deterministico) — pytest, tsc, eslint, vitest, e2e.
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

    python3 tools/asdlc_runner.py PBI-201 --e2e
    python3 tools/asdlc_runner.py PBI-201 PBI-203 --dry-run
    python3 tools/asdlc_runner.py --riepilogo --tariffa 90

⚠️ Da usare in un clone o in un worktree dedicato, mai sull'albero che stai guardando:
   l'agente gira in modalità non interattiva e scrive senza chiedere conferma.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG_DIR = REPO / "runs"
CSV_TEMPI = LOG_DIR / "tempi.csv"

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
    Gate("e2e", ["npm", "run", "e2e"], cwd="e2e", solo_se="e2e"),
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
- Formato: `tipo(scope): descrizione imperativa` in italiano, corpo con i dettagli.
- Resta dentro lo **scope** dichiarato dal PBI. Se ti serve toccare altro, fermati e dillo.
- Se il PBI cambia un contratto, aggiorna la spec NELLO STESSO commit del codice.
- Non lasciare modifiche non committate: ciò che non è committato non esiste.
- Non toccare .github/workflows/ (il push verrebbe rifiutato dal token).

Se incontri un'ambiguità che il protocollo di rifinitura non copre, NON scegliere in
silenzio: fermati, scrivi la domanda, e termina con la riga esatta

    STOP: <la domanda>

Quando hai finito, termina con la riga esatta

    FATTO: <riepilogo in una riga>
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
   aggiornata nello stesso commit del codice che ne cambia il comportamento?

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

PROMPT_RIMEDIO = """Il Critic ha respinto il lavoro. Rapporto:

{rapporto}

Chiudi ogni violazione, una alla volta, con un commit per rimedio. Se ritieni che una
violazione sia infondata, NON ignorarla: spiega perché nella risposta e lasciala aperta.
Termina con FATTO: oppure STOP: come prima.
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
    gate_rossi: list[str] = field(default_factory=list)
    # Tempi: il totale è il tempo di parete del PBI, il resto ne è la scomposizione.
    iniziato: str = ""
    finito: str = ""
    durata_s: float = 0.0
    tempi: dict[str, float] = field(default_factory=lambda: defaultdict(float))


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
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
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
    """Apre la PR e si ferma lì: il merge è dell'umano (micro-commits §5)."""
    git("push", "-u", "origin", branch)
    corpo = (
        f"Esecuzione automatica di `{pbi_path.relative_to(REPO)}` "
        f"(`tools/asdlc_runner.py`).\n\n"
        f"Gate deterministici verdi · revisione avversariale PASS.\n"
        f"Tempo macchina: **{hms(e.durata_s)}** "
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
    return out.strip().splitlines()[-1]


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
    branch = f"pbi/{pbi.lower()}"
    git("switch", "-c", branch, "origin/main")
    return branch


def esegui_pbi(pbi: str, attivi: set[str], dry: bool, con_pr: bool) -> Esito:
    pbi_path = next(REPO.glob(f"backlog/{pbi}-*.md"), None)
    if pbi_path is None:
        return Esito(pbi, "saltato", nota="PBI inesistente in backlog/")

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

    def chiudi(stato: str, nota: str = "") -> Esito:
        e.stato, e.durata_s = stato, time.monotonic() - t0
        e.finito = datetime.now().isoformat(timespec="seconds")
        if nota:
            e.nota = nota
        print(f"    tempo: {hms(e.durata_s)} "
              f"(builder {hms(e.tempi['builder'])} · gate {hms(e.tempi['gate'])} · "
              f"critic {hms(e.tempi['critic'])})")
        return e

    for revisione in range(MAX_REVISIONI + 1):
        e.revisioni = revisione

        # --- Builder + Quality Gate (deterministico) ---
        verde = False
        rossi: list[tuple[str, str]] = []  # se l'agente non arriva mai ai gate, resta vuoto
        for _ in range(MAX_TENTATIVI):
            e.tentativi += 1
            print(f"  builder — giro {e.tentativi}")
            # Il primo giro apre una sessione nuova (contesto pulito, è il punto); i giri
            # di correzione la continuano: rileggere tutto da capo per un gate rosso è il
            # modo più costoso di dire "hai sbagliato una riga".
            cmd = BUILDER + ([] if e.tentativi == 1 else ["-c"]) + [prompt]
            with misura(e, "builder"):
                _, out = esegui(cmd, REPO)

            if "STOP:" in out:
                domanda = out.split("STOP:")[-1].strip().splitlines()[0]
                return chiudi("fermato", f"domanda dell'agente: {domanda}")

            if sporco := git("status", "--porcelain"):
                # Non committato = non esiste: niente da giudicare, niente da ripristinare.
                prompt = (f"Ci sono modifiche non committate:\n{sporco[:1500]}\n"
                          f"Committale con micro-commit coerenti.")
                continue

            with misura(e, "gate"):
                rossi = gira_gate(attivi)
            if not rossi:
                verde = True
                break
            prompt = PROMPT_RIPROVA.format(esiti="\n\n".join(f"## {n}\n{o}" for n, o in rossi))

        # `origin/main` e non `main`: da quando non lo si estrae, il main locale del
        # worktree resta indietro, e conterebbe come «commit del PBI» tutto ciò che
        # main ha ricevuto nel frattempo.
        e.commit = int(git("rev-list", "--count", "origin/main..HEAD") or 0)
        if not verde:
            e.gate_rossi = [n for n, _ in rossi]
            return chiudi("rosso", "gate ancora rossi dopo i tentativi previsti")

        # --- Review Gate (probabilistico, sessione separata) ---
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
        prompt = PROMPT_RIMEDIO.format(rapporto=rapporto[-6000:])

    print(f"    commit sul branch: {e.commit} · "
          f"file: {git('diff', '--name-only', 'origin/main...HEAD')}")
    chiudi("fatto")

    # --- Acceptance Gate (umano): si apre la PR, non si mergia ---
    if con_pr:
        e.pr = apri_pr(pbi, pbi_path, branch, e)
        if e.pr:
            print(f"    PR aperta: {e.pr}")
    return e


def scrivi_tempi(run: str, esiti: list[Esito]) -> None:
    """Append su runs/tempi.csv: una riga per PBI eseguito, per la fatturazione."""
    LOG_DIR.mkdir(exist_ok=True)
    nuovo = not CSV_TEMPI.exists()
    with CSV_TEMPI.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNE_CSV)
        if nuovo:
            w.writeheader()
        for e in esiti:
            if e.stato == "saltato":
                continue  # niente tempo, niente riga: una riga a zero sporcherebbe la media
            w.writerow({
                "run": run, "pbi": e.pbi, "stato": e.stato,
                "iniziato": e.iniziato, "finito": e.finito,
                "durata_s": round(e.durata_s, 1), "durata_hms": hms(e.durata_s),
                "builder_s": round(e.tempi["builder"], 1),
                "gate_s": round(e.tempi["gate"], 1),
                "critic_s": round(e.tempi["critic"], 1),
                "tentativi": e.tentativi, "revisioni": e.revisioni,
                "commit": e.commit, "pr": e.pr, "nota": e.nota,
            })


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


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("pbi", nargs="*", help="es. PBI-201 PBI-202")
    ap.add_argument("--e2e", action="store_true", help="includi il gate Playwright (stack Docker su)")
    ap.add_argument("--dry-run", action="store_true", help="stampa il prompt e non esegue niente")
    ap.add_argument("--no-pr", action="store_true", help="non aprire la PR (resta solo il branch locale)")
    ap.add_argument("--continua-sui-rossi", action="store_true",
                    help="prosegui col PBI successivo anche se questo è rimasto rosso")
    ap.add_argument("--riepilogo", action="store_true",
                    help="non esegue niente: somma i tempi già registrati in runs/tempi.csv")
    ap.add_argument("--tariffa", type=float, metavar="EUR_ORA",
                    help="tariffa oraria: aggiunge la colonna del costo")
    a = ap.parse_args()

    if a.riepilogo:
        return riepilogo(a.tariffa)
    if not a.pbi:
        ap.error("indica almeno un PBI, oppure usa --riepilogo")

    attivi = {"e2e"} if a.e2e else set()
    run = datetime.now().strftime("%Y%m%d-%H%M%S")
    LOG_DIR.mkdir(exist_ok=True)
    esiti: list[Esito] = []

    for pbi in a.pbi:
        e = esegui_pbi(pbi, attivi, a.dry_run, con_pr=not a.no_pr)
        esiti.append(e)
        print(f"  → {e.stato}" + (f" ({e.nota})" if e.nota else ""))
        # Un PBI rosso, respinto o fermo su una domanda è un fatto da guardare, non da
        # superare: i PBI successivi molto spesso poggiano su questo.
        if e.stato in STATI_CHE_INTERROMPONO and not a.continua_sui_rossi:
            print("\nInterrotto. La catena dei PBI ha dipendenze dichiarate: proseguire su "
                  "una base rossa costa più di quanto risparmia.")
            break

    scrivi_tempi(run, esiti)
    (LOG_DIR / f"{run}.json").write_text(
        json.dumps([{k: v for k, v in e.__dict__.items() if k != "tempi"} | {"tempi": dict(e.tempi)}
                    for e in esiti], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    totale = sum(e.durata_s for e in esiti)
    print(f"\n{len(esiti)} PBI · tempo totale {hms(totale)}"
          + (f" · {totale / 3600 * a.tariffa:.2f} €" if a.tariffa else ""))
    print(f"Rapporto: runs/{run}.json · tempi: runs/tempi.csv")
    return 0 if all(e.stato in ("fatto", "saltato") for e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
