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

    python3 tools/asdlc/runner.py PBI-201
    python3 tools/asdlc/runner.py PBI-313 --senza-critic   # due gate su tre, e lo dichiara
    python3 tools/asdlc/runner.py PBI-201 PBI-203 --dry-run
    python3 tools/asdlc/runner.py --riepilogo --tariffa 90

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
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from fnmatch import fnmatch
import importlib.metadata
from importlib import resources
from pathlib import Path
from typing import Callable, Iterable, Iterator, NamedTuple

# La radice del progetto: il primo antenato della cwd che contiene `asdlc.toml`,
# trovato da `main()` (PBI-382). Non la cartella di questo file: installato, il
# codice sta in site-packages (`ADR-0026`, decisione 3).
REPO: Path

# Il runner è un modulo del pacchetto `asdlc`, in `tools/asdlc/` (PBI-383), e si
# lancia ancora per percorso finché non ci sono i comandi (PBI-384): `tools/` va
# sul `sys.path`, o `asdlc.config` non si trova. Qui conta dove sta il codice,
# non dove sta il progetto.
SORGENTE = Path(__file__).resolve().parent.parent
if str(SORGENTE) not in sys.path:
    sys.path.insert(0, str(SORGENTE))
from asdlc import config as asdlc_config  # noqa: E402

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
# `[ambiente].pacchetto`, assoluto: il venv in cui è installato il runner. Ogni
# comando che il runner lancia o fa lanciare è `<pacchetto>/bin/<comando>`.
PACCHETTO: Path | None
ESEGUIBILI: tuple[str, ...]  # `[ambiente].eseguibili`
JUNIT_COMANDO: tuple[str, ...] | None  # `[junit].comando`, con `{test}` (PBI-505)
MINIMI: dict[str, int]       # `[ambiente].minimi`
PRESTITI: tuple[str, ...]  # `[ambiente].prestiti`
# Il worktree è uno solo e non aveva un lucchetto: vedi `lucchetto()`. Qui c'è il
# **nome** del file e non il suo percorso: la cartella è `LOG_DIR`, e un percorso
# calcolato qui la congelerebbe all'import — chi sposta `LOG_DIR` (i test di
# `main()`, che girano su `tmp_path`) si ritroverebbe il lucchetto rimasto
# indietro nel `runs/` vero, cioè un test che misura se sul PC c'è un runner vivo.
NOME_LUCCHETTO = ".runner.lock"

# Chi, girando in questo albero, ci **scrive**. Un `tail -f` sul log o un `git log`
# aperto non sono un pericolo, e un controllo che grida sempre si impara a spegnere.
# Il runner in tre forme: `asdlc-runner`, il comando installato (PBI-384),
# `asdlc/runner.py` dal sorgente del pacchetto (PBI-383), e `asdlc_runner` com'era
# lanciato prima del trasloco.
AGENTI = ("claude", "asdlc-runner", "asdlc_runner", "asdlc/runner.py")

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

# Il Solver (`PBI-507`, decisione 12) legge soltanto: nessun `Bash`, nessuna scrittura,
# e i tre strumenti con cui smista il blocco. Il modello è `[solver].modello`.
def comando_del_solver() -> list[str]:
    return ["claude", "-p", "--allowedTools",
            "Read,Grep,Glob,mcp__asdlc__risolvi,mcp__asdlc__segnala_limite_runner,"
            "mcp__asdlc__chiedi_a_francesco", "--model", CFG.solver.modello]


# Il Lettore (`PBI-521`, decisione 3) legge il PBI e scrive le sonde nel suo albero usa e
# getta: `Write` ed `Edit` sì, `Bash` no, perché le sonde le esegue il runner. Il modello
# è `[lettore].modello`.
def comando_del_lettore() -> list[str]:
    return ["claude", "-p", "--allowedTools",
            "Read,Grep,Glob,Write,Edit,mcp__asdlc__rilievo,mcp__asdlc__sonda,mcp__asdlc__letto",
            "--model", CFG.lettore.modello]


# I motivi d'uscita di un giro fermato che il Solver smista: il `fermati` del Builder, il
# `sospeso` del Critic, e un agente dell'uno o dell'altro senza nessuna chiamata valida.
BLOCCHI = ("domanda-del-builder", "builder-senza-esito", "domanda-del-critic",
           "critic-senza-esito")

# Il server dell'esito (`PBI-366`, `ADR-0027`) è il comando installato accanto
# al runner, `<pacchetto>/bin/asdlc-esito` (PBI-384). I ruoli sono i suoi: un
# altro valore lo ferma all'avvio.
SERVER_DELL_ESITO = "asdlc-esito"
RUOLI = ("builder", "critic", "solver", "lettore")

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

# Le vie d'uscita di un giro, una riga ciascuna: `motivo → (stato, testo)`
# (PBI-375, causa `diagnosi-confusa` di PBI-102). Gli stati sono otto e le uscite
# di più: `fermato` valeva per cinque situazioni e `rosso` per tre, e chi legge
# il rapporto le distingueva solo dal testo libero della nota. Il motivo le
# distingue, e lo stato si ricava da qui, non si scrive a mano. Un'uscita nuova è
# una riga nuova, con il suo caso in `TestOgniUscitaHaIlSuoMotivo`.
USCITE: dict[str, tuple[str, str]] = {
    # Prima del giro: il ramo non c'è ancora.
    "pbi-inesistente": ("saltato", "PBI inesistente nel backlog della base del giro"),
    "dry-run": ("saltato", "dry-run: il prompt a schermo, nessun giro"),
    "albero-sporco-all-ingresso": ("fermato",
                                   "albero di lavoro sporco: committa o pulisci prima"),
    # La pre-verifica (PBI-522): un rilievo si corregge nel PBI; un Lettore senza
    # `letto` no, e il tick lo riprende come un limite d'uso. Nessuno dei due va al Solver.
    "preverifica": ("fermato", "pre-verifica: il PBI ha dei rilievi prima del ramo"),
    "lettore-senza-esito": ("senza esito", "il lettore non ha fatto nessuna chiamata valida"),
    "origin-muto": ("fermato", "il ramo non è nato"),
    # Il Builder.
    "builder-senza-esito": ("senza esito", "il builder non ha fatto nessuna chiamata valida"),
    "domanda-del-builder": ("fermato", "domanda dell'agente"),
    "albero-sporco-dopo-igiene": ("fermato", "il lavoro c'è ma non è committato"),
    # I gate: il codice sbagliato, lo strumento guasto, il ciclo mancato.
    "ref-diverso-da-head": ("fermato", "gate non girati: il ramo non è HEAD"),
    "gate-rossi": ("rosso", "gate ancora rossi dopo i tentativi previsti"),
    "gate-del-rosso-guasto": ("rosso", "il gate del rosso non ha potuto girare"),
    "rosso-mai-visto": ("fermato", "il rosso non si è mai visto: il ciclo mancato è ex ante "
                                   "e nessuna fix lo annulla"),
    # Il Critic.
    "critic-senza-esito": ("senza esito", "il critic non ha fatto nessuna chiamata valida"),
    "domanda-del-critic": ("sospeso", "domanda del critic"),
    "revisioni-esaurite": ("non convergente",
                           "revisioni senza convergere: serve una lettura umana"),
    # Il runner guasto, che non è il lavoro sbagliato (difetto 11).
    "eccezione-nel-giro": ("rosso", "eccezione nel giro"),
    "fatto": ("fatto", "giro chiuso"),
    # Dopo il giro, in `apri_pr()`.
    "head-non-su-origin": ("fermato", "PR non aperta: su origin non c'è l'HEAD misurato"),
}


def uscita(motivo: str, dettaglio: str = "") -> tuple[str, str]:
    """Lo stato e la nota di una via d'uscita: `<motivo>: <testo> — <dettaglio>`.
    Un motivo che non è in `USCITE` alza: la tabella è chiusa."""
    if motivo not in USCITE:
        raise ValueError(f"motivo d'uscita fuori dalla tabella USCITE: {motivo!r} — "
                         f"un'uscita nuova è una riga nuova, con il suo caso nel test")
    stato, testo = USCITE[motivo]
    return stato, f"{motivo}: {testo}" + (f" — {dettaglio}" if dettaglio else "")

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
    """Le costanti di modulo, dalla configurazione. Si chiama una volta, da
    `main()`, e i test la richiamano con un `asdlc.toml` di prova.

    Restano **nomi di modulo** e non attributi di un oggetto: 36 punti dei test
    fanno `monkeypatch.setattr(runner, …)` su queste costanti, e spostarle
    dentro un oggetto costruito in `main()` li romperebbe tutti (PBI-358,
    decisione 1). Il guadagno — un posto solo — è lo stesso.
    """
    global CFG, GATE, LOG_DIR, CSV_TEMPI, BACKLOG, VENV, PRESTITI, PACCHETTO, ESEGUIBILI
    global MINIMI
    global MAX_TENTATIVI, MAX_IGIENE, MAX_REVISIONI, MINUTI_BUILDER, MINUTI_CRITIC
    global BASE, REMOTO, RAMO_PRINCIPALE, PROMPT_CRITIC, PROMPT_RIMEDIO, GUARDIA_DEL_COMMIT
    global PROMPT_BUILDER, PROMPT_IGIENE, PROMPT_RIPROVA, MODELLO_CRITIC, MODELLO_RIMEDIO
    global GATE_DEL_ROSSO_ATTIVO, JUNIT_COMANDO
    CFG = cfg
    JUNIT_COMANDO = cfg.junit.comando
    GATE = list(cfg.gate)
    # `false` spegne la seconda domanda del Quality Gate — e il giro lo scrive.
    GATE_DEL_ROSSO_ATTIVO = cfg.gate_del_rosso.attivo

    # Il ramo di base, come **nome**. Dentro un giro vale una volta sola: il giro lo
    # risolve in uno sha all'inizio (`base_del_giro`, PBI-374), e da lì nascono il
    # branch, il conteggio dei commit, il gate del rosso e il diff che il Critic
    # legge. Il nome resta per ciò che sta fuori dal giro, come `--gate-rosso`.
    BASE, REMOTO, RAMO_PRINCIPALE = cfg.git.base, cfg.git.remoto, cfg.git.ramo
    # Ogni prompt è quello del pacchetto con in coda le aggiunte del progetto per
    # il suo ruolo, se ci sono (PBI-386): si ricompone da capo a ogni chiamata,
    # così una seconda `configura()` non accoda due volte.
    aggiunte = aggiunte_del_progetto(cfg.prompt.aggiunte)
    PROMPT_IGIENE = prompt_del_pacchetto("igiene") + aggiunte["igiene"]
    PROMPT_RIPROVA = prompt_del_pacchetto("riprova") + aggiunte["riprova"]
    MODELLO_CRITIC = prompt_del_pacchetto("critic") + aggiunte["critic"]
    MODELLO_RIMEDIO = prompt_del_pacchetto("rimedio") + aggiunte["rimedio"]
    # I prompt che nominano il ramo lo prendono da qui, e non da una riga scritta a
    # mano: un prompt che dice all'agente un ramo diverso da quello su cui il gate
    # misura è una bugia che costa un giro. `{pbi_path}` e `{rapporto}` restano a
    # chi chiama, che li riempie a ogni giro. L'aggiunta si accoda **dopo** il
    # primo `.format()`: è scappata per uno solo, quello di chi chiama.
    PROMPT_CRITIC = prompt_del_pacchetto("critic").format(
        base=BASE, pbi_path="{pbi_path}") + aggiunte["critic"]
    PROMPT_RIMEDIO = prompt_del_pacchetto("rimedio").format(
        base=BASE, pbi_path="{pbi_path}", rapporto="{rapporto}") + aggiunte["rimedio"]

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
    # Il venv del runner installato, già assoluto: `carica()` lo risolve dalla
    # radice comune, quindi è lo stesso da ogni worktree.
    PACCHETTO = cfg.ambiente.pacchetto
    # Ciò che deve esserci sul `PATH` dei gate prima di partire (`mancanze_dell_ambiente`).
    ESEGUIBILI = cfg.ambiente.eseguibili
    # E la versione principale sotto cui un eseguibile non basta.
    MINIMI = cfg.ambiente.minimi
    # Il `pre-commit` col percorso del runner installato: senza `pacchetto` il
    # percorso è vuoto, e l'hook lo dice e lascia passare.
    GUARDIA_DEL_COMMIT = MODELLO_DELLA_GUARDIA_DEL_COMMIT.format(
        runner=PACCHETTO / "bin" / "asdlc-runner" if PACCHETTO else "")
    # Il Builder chiede `--chiedi-impl` al runner installato, per percorso
    # assoluto, non al sorgente dell'albero che sta cambiando.
    PROMPT_BUILDER = MODELLO_BUILDER.format(
        pbi_path="{pbi_path}",
        runner=PACCHETTO / "bin" / "asdlc-runner" if PACCHETTO else "asdlc-runner"
    ) + aggiunte["builder"]

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


def prompt_del_pacchetto(ruolo: str) -> str:
    """Il testo del prompt di `ruolo`, dal file `asdlc/prompt/<ruolo>.md` del
    pacchetto.

    I prompt sono dati del pacchetto e non costanti del sorgente (PBI-386,
    `ADR-0026` decisione 2): viaggiano con l'installazione, e il runner
    installato li legge da site-packages. Il testo è quello che passa per
    `.format()`, segnaposto compresi."""
    return (resources.files("asdlc") / "prompt" / f"{ruolo}.md").read_text(encoding="utf-8")


# Il titolo sotto cui le aggiunte del progetto seguono il prompt del pacchetto.
TITOLO_DELLE_AGGIUNTE = "## Aggiunte del progetto"


def aggiunte_del_progetto(cartella: Path | None) -> dict[str, str]:
    """Per ogni ruolo, ciò che si accoda al suo prompt: il titolo e il file
    `<ruolo>.md` della cartella delle aggiunte, o niente se il file non c'è.

    Un progetto **estende** i prompt del pacchetto e non li sostituisce
    (`ADR-0026`, decisione 2). Il file è testo e non un modello: le graffe si
    raddoppiano, e il `.format()` di chi chiama le rende come sono scritte."""
    aggiunte = dict.fromkeys(asdlc_config.RUOLI_DEI_PROMPT, "")
    if cartella is None:
        return aggiunte
    for ruolo in aggiunte:
        file = cartella / f"{ruolo}.md"
        if file.is_file():
            testo = file.read_text(encoding="utf-8").replace("{", "{{").replace("}", "}}")
            aggiunte[ruolo] = f"\n{TITOLO_DELLE_AGGIUNTE}\n\n{testo}"
    return aggiunte


# Il testo del pacchetto, all'import. `configura()` riscrive l'igiene, la riprova
# e i due modelli con in coda le aggiunte del progetto.
MODELLO_BUILDER = prompt_del_pacchetto("builder")
PROMPT_IGIENE = prompt_del_pacchetto("igiene")
PROMPT_RIPROVA = prompt_del_pacchetto("riprova")
# Il testo che segue `PROMPT_BUILDER` quando il giro riprende dopo il limite d'uso
# (`--riprendi`, PBI-519, decisione 7): si aggiunge, non sostituisce.
PROMPT_RIPRENDI = prompt_del_pacchetto("riprendi")
# I due prompt che nominano il ramo di base sono **modelli**: `PROMPT_CRITIC` e
# `PROMPT_RIMEDIO` nascono in `configura()`, col ramo di `asdlc.toml` al posto di
# `{base}` e `{pbi_path}` / `{rapporto}` lasciati a chi chiama.
MODELLO_CRITIC = prompt_del_pacchetto("critic")
MODELLO_RIMEDIO = prompt_del_pacchetto("rimedio")

PROMPT_BUILDER: str  # `MODELLO_BUILDER` col runner installato dentro e le aggiunte, da `configura()`
PROMPT_CRITIC: str   # `MODELLO_CRITIC` col ramo di base dentro, da `configura()`
PROMPT_RIMEDIO: str  # idem, da `MODELLO_RIMEDIO`


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
    # La via d'uscita, una chiave di `USCITE`: è lei a dare lo stato (PBI-375).
    motivo: str = ""
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
    # Un esito per giro del Solver (`PBI-507`): `{"esito", ...}` come il server lo ha
    # scritto, o `{"esito": "senza esito", "uscita"}` se non ha chiamato niente.
    solver: list[dict] = field(default_factory=list)
    # I giri Solver↔Builder di questo PBI, contando quelli dei rapporti di prima
    # (`PBI-507`, decisione 10): il tetto è `[solver].giri_massimi`.
    giri_solver: int = 0
    # Le riprese del Builder dopo un `risolto` del Solver in questo giro (`PBI-517`,
    # decisione 11); le loro invocazioni stanno in `invocazioni`.
    riprese_solver: int = 0
    # La sezione `## Guardia di processo` (`PBI-508`): una riga per regola, `ok`, `violata`
    # o `non eseguita`. Vuota se il Solver non ha girato.
    guardia: str = ""
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
    # Rami, alberi e file com'erano all'inizio del giro e come sono alla fine:
    # `{"inizio": inventario(), "fine": inventario()}` (PBI-363, decisione 7).
    inventario: dict = field(default_factory=dict)
    # Lo sha da cui discende il giro: il commit su cui si è letto il PBI, da cui è
    # nato il branch e contro cui si contano i commit (PBI-374, decisione 1).
    base: str = ""
    # Lo sha del ramo pubblicato su `origin`, letto con `ls-remote` dopo il push:
    # è la testa su cui `asdlc-chiudi-giro` mette il tag (PBI-385, decisione 1).
    # Vuoto se il giro non ha pubblicato, o se `origin` non ha risposto.
    testa: str = ""
    # Dopo un `senza esito` per il limite d'uso con l'ora del reset leggibile: da
    # quando il tick può riprendere il PBI, data e ora locali in ISO (PBI-519,
    # decisione 3). Vuoto per ogni altro esito.
    riprendi_dopo: str = ""
    # Il ramo su cui il giro ha lavorato: `--riprendi` riparte da `origin/<ramo>`
    # dell'ultimo rapporto, che può essere un `-giroK` (PBI-519, decisione 6).
    ramo: str = ""
    # Le riprese dopo il limite d'uso fatte per questo PBI, contando quelle dei
    # rapporti di prima: il tetto lo applica il tick (PBI-519, decisione 8).
    riprese_limite: int = 0
    # Dopo un `preverifica`: lo sha del blob del file del PBI che la pre-verifica ha
    # letto, e quanti rilievi ha trovato. Il tick non rilancia il PBI finché su `main`
    # lo sha è lo stesso (PBI-522, decisioni 4 e 6).
    sha_pbi: str = ""
    rilievi_preverifica: int = 0


def distribuzione_del_runner() -> importlib.metadata.Distribution:
    """Il pacchetto `asdlc` installato. Alza `PackageNotFoundError` se non lo è,
    come sotto i test, che girano dal sorgente."""
    return importlib.metadata.distribution("asdlc")


def identita_del_runner() -> dict[str, str | None]:
    """Quale runner sta girando: `{"versione", "sha"}` (PBI-386, `ADR-0026`
    decisione 4). Prende il posto di `PROVENIENZA.md`.

    La versione è quella del pacchetto installato; lo sha è il commit da cui
    l'ha installato `pip`, e c'è solo se l'installazione viene da git
    (`direct_url.json`, `vcs_info.commit_id`). Con `pip install ./tools` lo sha
    è `None`; senza il pacchetto installato lo sono tutti e due, e il giro va
    avanti lo stesso."""
    try:
        distribuzione = distribuzione_del_runner()
    except importlib.metadata.PackageNotFoundError:
        return {"versione": None, "sha": None}
    # Un'installazione da un indice o da una wheel il file non lo scrive.
    provenienza = json.loads(distribuzione.read_text("direct_url.json") or "{}")
    return {"versione": distribuzione.version,
            "sha": provenienza.get("vcs_info", {}).get("commit_id")}


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
                    "pbi": pbi, "asdlc": identita_del_runner()},
                   indent=2, ensure_ascii=False),
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
            "asdlc": identita_del_runner(),
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


def mancanze_dell_ambiente() -> list[str]:
    """Ciò che manca perché un giro possa partire, una riga per mancanza, tutte
    insieme e non la prima; vuota se non manca niente (PBI-384).

    Il runner deve girare dal venv che `asdlc.toml` dichiara, `[ambiente].pacchetto`:
    il runner che lavora è quello installato, non il sorgente dell'albero
    (`ADR-0026`, decisione 3). Non si ripiega sul percorso dell'albero. Si guarda
    `sys.executable` così com'è, senza risolverlo: in un venv è un collegamento
    all'interprete di sistema, e risolto uscirebbe dal venv.

    Poi gli hook: devono trovare il runner installato (`gli_hook_trovano_il_runner`).
    Poi l'ambiente dei gate: il venv di `[ambiente].venv` deve esistere, e gli
    `[ambiente].eseguibili` si devono trovare lì o sul `PATH`, con la versione
    principale che `[ambiente].minimi` chiede.
    """
    mancanze: list[str] = []
    if PACCHETTO is None:
        mancanze.append("ambiente mancante: asdlc.toml non dichiara `[ambiente].pacchetto`, "
                        "il venv in cui è installato il runner")
    else:
        if not Path(sys.executable).is_relative_to(PACCHETTO):
            mancanze.append(f"ambiente mancante: il runner gira da `{sys.executable}`, "
                            f"`asdlc.toml` dichiara `{PACCHETTO}`")
        mancanze += gli_hook_trovano_il_runner()
    if not (REPO / VENV).is_dir():
        mancanze.append(f"ambiente mancante: il venv `{VENV}` non c'è")
    mancanze += eseguibili_mancanti(ESEGUIBILI, VENV, REPO)
    mancanze += versioni_sotto_il_minimo(MINIMI, VENV, REPO)
    return mancanze


def gli_hook_trovano_il_runner() -> list[str]:
    """Le mancanze per cui le due guardie di un giro non lancerebbero il runner
    installato, `<pacchetto>/bin/asdlc-runner` (PBI-384, decisione 6).

    Gli hook che lasciano passare vanno bene per le persone, non per i giri: un
    Builder senza guardia di fase, o un commit senza guardia, è un giro che non
    parte. Il comando deve esistere ed essere eseguibile: la guardia di fase della
    sessione lo lancia, e `impostazioni_della_sessione()` la genera da questo
    stesso percorso, quindi il controllo sul comando vale anche per lei.

    Il `pre-commit` si guarda e non si scrive: lo installa `apri_la_fase()`, dopo
    il lucchetto, col testo di `GUARDIA_DEL_COMMIT`, che lancia quel percorso.
    Uno assente o del runner lo lancerà — il nostro con un testo diverso si
    riscrive (PBI-388). Uno altrui PBI-388 non lo tocca, ed è una mancanza: se
    lancia un `asdlc-runner` o `--guardia-commit`, è la guardia di un altro
    runner.
    """
    mancanze: list[str] = []
    comando = comando_del_pacchetto("asdlc-runner")
    if not (comando.is_file() and os.access(comando, os.X_OK)):
        mancanze.append(f"ambiente mancante: `{comando}` non c'è o non è eseguibile, e gli "
                        "hook del giro non trovano il runner — "
                        f"`pip install {CFG.ambiente.installa}` nel venv del pacchetto")
    cartella = cartella_degli_hook()
    hook = cartella / "pre-commit" if cartella is not None else None
    if hook is None or not hook.is_file():
        return mancanze
    testo = hook.read_text(encoding="utf-8", errors="replace")
    if e_un_hook_del_runner(testo):
        return mancanze
    if "asdlc-runner" in testo or "--guardia-commit" in testo:
        mancanze.append(f"ambiente mancante: il `pre-commit` in `{cartella}` non lancia "
                        f"`{comando}`, e il giro non parte con la guardia del commit di un "
                        "altro runner — PBI-388 non riscrive un hook altrui")
    else:
        mancanze.append(f"ambiente mancante: il `pre-commit` in `{cartella}` non è del runner, "
                        "e il giro non parte senza la guardia del commit — PBI-388 non "
                        "riscrive un hook altrui")
    return mancanze


def versioni_sotto_il_minimo(minimi: dict[str, int], venv: str, radice: Path) -> list[str]:
    """Gli eseguibili la cui versione principale, il primo numero di
    `<eseguibile> --version`, sta sotto il minimo; una riga ciascuno con ciò che
    hanno risposto. Uno che non si trova non si nomina qui: è di
    `eseguibili_mancanti()`."""
    percorso = os.pathsep.join([str(radice / venv / "bin"), os.environ.get("PATH", "")])
    mancanze: list[str] = []
    for nome, minimo in minimi.items():
        trovato = shutil.which(nome, path=percorso)
        if trovato is None:
            continue
        try:
            detto = subprocess.run([trovato, "--version"], capture_output=True, text=True,
                                   timeout=30)
            risposta = (detto.stdout + detto.stderr).strip()
        except (OSError, subprocess.SubprocessError) as guasto:
            risposta = str(guasto)
        numero = re.search(r"\d+", risposta)
        if numero is None or int(numero.group()) < minimo:
            versione = numero.group() if numero else "illeggibile"
            mancanze.append(f"ambiente mancante: `{nome}` {versione}, il minimo è {minimo} "
                            f"(`{nome} --version`: {risposta})")
    return mancanze


def eseguibili_mancanti(eseguibili: Iterable[str], venv: str, radice: Path) -> list[str]:
    """Gli eseguibili che non si trovano né nel `bin` del venv né sul `PATH`, una
    riga ciascuno con dove li si è cercati. Il `PATH` è quello che vedranno i
    gate: `venv_sul_path()` mette il venv davanti, e qui lo si mette a mano per
    chi — il tick, `conftest.py` — non l'ha fatto (PBI-384, decisione 7)."""
    percorso = os.pathsep.join([str(radice / venv / "bin"), os.environ.get("PATH", "")])
    return [f"ambiente mancante: `{nome}` (cercato in `{venv}/bin` e sul `PATH`)"
            for nome in eseguibili if shutil.which(nome, path=percorso) is None]


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


def file_toccati(base: str | None = None) -> set[str]:
    """I file che il branch ha cambiato rispetto alla base, `<base>...HEAD`
    come per i mutanti: un `main` andato avanti nel frattempo non entra.

    Di un rename entrano i due lati: un file uscito da un percorso accende il
    gate di quel percorso, e `--name-only` ne dava solo il nuovo (PBI-387)."""
    base = base if base is not None else BASE
    voci = voci_del_name_status(git("diff", "--name-status", "-M", f"{base}...HEAD"))
    return {p for voce in voci for p in (voce.vecchio, voce.percorso) if p}


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
           flussi: tuple[Path, Path] | None = None,
           ambiente: dict[str, str] | None = None) -> tuple[int, str]:
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

    Con `ambiente`, quelle variabili si aggiungono all'ambiente del runner per
    questo comando soltanto: `ASDLC_GIRO=1` per la sessione del Builder.
    """
    env = {**os.environ, **ambiente} if ambiente else None
    try:
        if flussi is not None:
            return esegui_su_file(cmd, cwd, timeout, flussi, env)
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           env=env)
    except FileNotFoundError as exc:
        return 127, (f"comando non eseguibile: {cmd[0]} — {exc}\n"
                     f"le dipendenze dei gate stanno in backend/requirements-dev.txt")
    return p.returncode, (p.stdout + p.stderr)


@contextmanager
def worktree_di_rilascio(repo: Path, riferimento: str):
    """Un worktree staccato a `riferimento`, in una cartella temporanea fuori da `repo`,
    che si toglie all'uscita anche se il corpo alza (`PBI-509`, R9). Rende il percorso.
    Il checkout del tick non cambia ramo né stato: è lì che ci sono le persone."""
    cartella = Path(tempfile.mkdtemp(prefix="asdlc-rilascio-")) / "albero"
    codice, uscita = esegui(["git", "worktree", "add", "--detach", str(cartella), riferimento],
                            repo, timeout=300)
    if codice != 0:
        shutil.rmtree(cartella.parent, ignore_errors=True)
        raise RuntimeError(f"`git worktree add` è uscito {codice}: {uscita.strip()[:200]}")
    try:
        yield cartella
    finally:
        esegui(["git", "worktree", "remove", "--force", str(cartella)], repo, timeout=300)
        shutil.rmtree(cartella.parent, ignore_errors=True)


class TettoSuperato(Exception):
    """Una chiamata scaduta: il codice d'uscita del processo ucciso, e l'uscita
    parziale che i file dei flussi hanno raccolto."""

    def __init__(self, codice: int, uscita: str):
        super().__init__(f"tetto superato (codice {codice})")
        self.codice, self.uscita = codice, uscita


# I secondi fra il `SIGTERM` al gruppo di una chiamata scaduta e il `SIGKILL`.
ATTESA_DOPO_SIGTERM = 5


def esegui_su_file(cmd: list[str], cwd: Path, timeout: float,
                   flussi: tuple[Path, Path],
                   env: dict[str, str] | None = None) -> tuple[int, str]:
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
                             start_new_session=True, env=env)
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


def comando_del_pacchetto(nome: str) -> Path:
    """`<pacchetto>/bin/<nome>`, il percorso assoluto di un comando installato.

    Mai il nome nudo: il cron ha il `PATH` minimo. Mai il file dell'albero: il
    runner che lavora è quello installato (`ADR-0026`, decisione 3). Senza
    `[ambiente].pacchetto` alza `ValueError`, prima di ogni lancio."""
    if PACCHETTO is None:
        raise ValueError(f"asdlc.toml non dichiara `[ambiente].pacchetto`: non so dove "
                         f"sta `{nome}`")
    return PACCHETTO / "bin" / nome


def config_del_server(ruolo: str | None, esito: Path | None) -> Path:
    """Scrive la config MCP che fa partire il server dell'esito per questa
    invocazione, accanto al suo file d'esito, e ne torna il percorso.

    Un ruolo che non è `builder`, `critic`, `solver` o `lettore`, o un file d'esito mancante,
    sollevano `ValueError` **prima** del lancio. Il server si fermerebbe da sé
    all'avvio, ma dentro un giro quella fermata arriverebbe come un agente
    senza esito, dopo i minuti del Builder (PBI-367, decisione 4).

    Il file d'esito non si crea qui: lo crea il server alla prima chiamata
    valida, collegando al nome un temporaneo già scritto con `os.link`, e un
    file già presente la rifiuterebbe.
    """
    if ruolo not in RUOLI:
        raise ValueError(f"ruolo {ruolo!r}: il server dell'esito conosce solo {RUOLI}")
    if esito is None:
        raise ValueError(f"il {ruolo} non ha un file d'esito in cui il server possa scrivere")
    config = esito.with_suffix(".mcp.json")
    ambiente = {"ASDLC_RUOLO": ruolo, "ASDLC_ESITO": str(esito)}
    if ruolo == "solver":
        # Le cause `runner-*` che il server accetta: la lista del progetto, senza
        # rete (`PBI-507`, decisione 8).
        ambiente["ASDLC_CAUSE"] = ",".join(CFG.solver.cause)
        # Il clone di `asdlc` da cui si apre la PR a monte (`PBI-512`): senza chiave la
        # variabile manca e lo strumento rifiuta la chiamata.
        if CFG.rilascio.clone:
            ambiente["ASDLC_CLONE"] = CFG.rilascio.clone
    config.write_text(json.dumps({"mcpServers": {"asdlc": {
        "command": str(comando_del_pacchetto(SERVER_DELL_ESITO)),
        "args": [],
        "env": ambiente,
    }}}, indent=2, ensure_ascii=False), encoding="utf-8")
    return config


# Chi è dentro un giro: `fase-tdd.sh`, l'hook delle sessioni delle persone, con
# questa variabile tace, perché la guardia del giro è quella che segue.
AMBIENTE_DEL_GIRO = {"ASDLC_GIRO": "1"}


def impostazioni_della_sessione(esito: Path) -> Path:
    """Scrive le impostazioni della sessione del Builder accanto al suo file
    d'esito, `<esito>.settings.json`, e ne torna il percorso: l'hook
    `PreToolUse` della guardia di fase, su `Edit|Write`, che lancia il runner
    installato, `<pacchetto>/bin/asdlc-runner --guardia-fase` (PBI-384,
    decisione 3). La guardia di un giro non è mai la copia di lavoro che il
    Builder sta cambiando (`ADR-0026`, decisione 3)."""
    comando = f"{shlex.quote(str(comando_del_pacchetto('asdlc-runner')))} --guardia-fase"
    impostazioni = esito.with_suffix(".settings.json")
    impostazioni.write_text(json.dumps({"hooks": {"PreToolUse": [{
        "matcher": "Edit|Write",
        "hooks": [{"type": "command", "command": comando}],
    }]}}, indent=2, ensure_ascii=False), encoding="utf-8")
    return impostazioni


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


def cartella_delle_sessioni(cwd: Path | None = None) -> Path:
    """Dove Claude Code scrive le sessioni lanciate da `cwd`, e senza da `REPO`:
    `~/.claude/projects/<percorso>`, col percorso della cartella di lavoro in cui ogni
    carattere non alfanumerico è un `-`. Il Lettore parte dal suo albero usa e getta, e la
    sua sessione sta sotto il percorso di quello (PBI-521)."""
    cartella = cwd or REPO
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(cartella))


def copia_la_traccia(sessione: str, destinazione: Path, registro: dict,
                     cwd: Path | None = None) -> None:
    """Copia il `jsonl` della sessione accanto ai file del giro e ne scrive il percorso in
    `registro["traccia"]`. La cartella di Claude Code è fuori dal repository e può essere
    ripulita (PBI-511, decisione 2). Se il file non c'è o non si copia, `traccia` è `None` e
    `traccia_nota` dice perché: il giro non si ferma (`ADR-0008`). La sessione si cerca fra
    quelle di `cwd`, la cartella da cui l'agente è partito; senza, fra quelle di `REPO`."""
    # Senza `cwd` la chiamata resta senza argomenti, com'era prima di PBI-521.
    sessioni = cartella_delle_sessioni() if cwd is None else cartella_delle_sessioni(cwd)
    sorgente = sessioni / f"{sessione}.jsonl"
    try:
        shutil.copyfile(sorgente, destinazione)
    except OSError as guasto:
        registro["traccia"] = None
        registro["traccia_nota"] = f"sessione non trovata o non copiabile: {sorgente} ({guasto})"
        return
    registro["traccia"] = str(destinazione)
    try:
        registro["contenuto"] = contenuto_della_traccia(destinazione)
    except (OSError, ValueError) as guasto:
        registro["traccia_nota"] = f"traccia copiata ma non leggibile ({guasto})"


def blocchi_della_traccia(percorso: Path) -> Iterator[tuple[str, str, dict]]:
    """I blocchi di una traccia di sessione nell'ordine in cui sono avvenuti, come
    `(ruolo, id del messaggio, blocco)`; senza id, il numero di riga. Il contenuto di un messaggio testuale è una
    stringa, e vale un blocco `text`. Una riga che non è JSON alza `ValueError`."""
    for numero, riga in enumerate(percorso.read_text(encoding="utf-8").splitlines()):
        if not riga.strip():
            continue
        messaggio = json.loads(riga).get("message")
        if not isinstance(messaggio, dict):
            continue
        contenuto = messaggio.get("content")
        if isinstance(contenuto, str):
            contenuto = [{"type": "text", "text": contenuto}]
        for blocco in contenuto if isinstance(contenuto, list) else []:
            if isinstance(blocco, dict):
                yield messaggio.get("role", ""), messaggio.get("id") or f"riga {numero}", blocco


def contenuto_della_traccia(percorso: Path) -> dict[str, int]:
    """Cosa contiene la traccia: chiamate a strumento (`tool_use`), risposte (messaggi
    dell'assistente, contati per id: Claude Code scrive un blocco per riga) e blocchi
    `thinking`. Uno zero in `thinking` dice che la sessione non porta ragionamenti."""
    risposte: set[str] = set()
    conto = {"chiamate": 0, "thinking": 0}
    for ruolo, id_messaggio, blocco in blocchi_della_traccia(percorso):
        if ruolo == "assistant":
            risposte.add(id_messaggio)
            if blocco.get("type") == "tool_use":
                conto["chiamate"] += 1
            elif blocco.get("type") == "thinking":
                conto["thinking"] += 1
    return {"chiamate": conto["chiamate"], "risposte": len(risposte),
            "thinking": conto["thinking"]}


def invoca_agente(ruolo: str | None, comando: list[str], prompt: Path,
                  esito: Path | None, cwd: Path | None = None) -> Invocazione:
    """Lancia un agente con il server dell'esito accanto, e legge l'esito.

    `--mcp-config` è variadico come `--allowedTools`: lo chiude
    `--strict-mcp-config`, un flag booleano, e il prompt viene dopo. Nella
    prima prova il prompt in coda a `--mcp-config` è stato preso per un'altra
    config, e `-p` è partito senza input.

    La chiamata ha un tetto per ruolo: `MINUTI_BUILDER`, `[lettore].minuti` per il
    Lettore (PBI-521), `MINUTI_CRITIC` per gli altri.
    Scaduto, l'esito è `None` anche se l'agente ne aveva dichiarato uno: non ha
    finito, e il giro chiude `senza esito` (PBI-369, decisione 3). Il registro
    porta allora `tetto_minuti`, che è ciò che la nota dice.

    Ogni invocazione riceve `--session-id` con un uuid nuovo, che il registro riporta in
    `sessione` (PBI-511, decisione 1), e a fine invocazione ne copia la traccia accanto ai
    file del giro (`copia_la_traccia`, decisione 2). La CLI accetta `--session-id` con
    `-c` o `--resume` solo insieme a `--fork-session`, e il runner lo aggiunge soltanto
    lì: il rilancio continua il contesto e scrive sotto il uuid nuovo (PBI-513).

    Il Builder riceve con `--settings` la guardia di fase del giro, e
    `ASDLC_GIRO=1` nell'ambiente (`impostazioni_della_sessione`, PBI-384).

    L'agente parte da `cwd`, e senza da `REPO`: il Lettore lavora nel suo albero usa e
    getta (`PBI-521`, decisione 3), e il server dell'esito lo eredita. La traccia si cerca
    fra le sessioni di quella cartella.
    """
    config = config_del_server(ruolo, esito)
    della_sessione: list[str] = []
    ambiente: dict[str, str] | None = None
    if ruolo == "builder":
        della_sessione = ["--settings", str(impostazioni_della_sessione(esito))]
        ambiente = AMBIENTE_DEL_GIRO
    sessione = str(uuid.uuid4())
    if "-c" in comando or "--resume" in comando:
        della_sessione.append("--fork-session")
    fuori, dentro = Path(f"{esito}.stdout"), Path(f"{esito}.stderr")
    minuti = {"builder": MINUTI_BUILDER, "lettore": CFG.lettore.minuti}.get(ruolo, MINUTI_CRITIC)
    scaduto = False
    t0 = time.monotonic()
    try:
        codice, uscita = esegui(comando + della_sessione + ["--session-id", sessione]
                                + ["--mcp-config", str(config), "--strict-mcp-config",
                                   f"@{prompt}"], cwd or REPO, timeout=minuti * 60,
                                flussi=(fuori, dentro), ambiente=ambiente)
    except TettoSuperato as tetto:
        codice, uscita, scaduto = tetto.codice, tetto.uscita, True
    registro = {"ruolo": ruolo, "codice": codice,
                "durata_s": round(time.monotonic() - t0, 1), "stdout": str(fuori),
                "stderr": str(dentro), "chiamate": f"{esito}.chiamate.jsonl",
                "sessione": sessione}
    if scaduto:
        registro["tetto_minuti"] = minuti
    copia_la_traccia(sessione, Path(f"{esito}.sessione.jsonl"), registro, cwd)
    dichiarato = None if scaduto else esito_dichiarato(esito)
    return Invocazione(codice, uscita, dichiarato, registro)


# Ciò che la CLI risponde quando l'account esaurisce il limite d'uso, e l'ora del
# reset dentro quella frase: «You've hit your session limit · resets 1:30am» (giro
# 5 di PBI-333, 02/09/2026). Stanno nel sorgente e non in `asdlc.toml`: cambiano
# quando cambia l'agente, non il progetto (PBI-363, decisione 5). È un testo letto
# da uno strumento, un'eccezione dichiarata: se la CLI esporrà l'ora in un campo,
# si leggerà da lì.
FRASE_DEL_LIMITE = re.compile(r"You've hit your \w+ limit")
ORA_DEL_RESET = re.compile(r"resets\s+(\d{1,2}(?::\d{2})?\s?[ap]m)", re.IGNORECASE)


def limite_d_uso(uscita: str) -> str:
    """Ciò che la nota aggiunge quando l'uscita porta la frase del limite d'uso,
    o `""`. La lettura aggiunge e non cambia niente (PBI-363, decisione 3)."""
    if not FRASE_DEL_LIMITE.search(uscita):
        return ""
    if ora := ORA_DEL_RESET.search(uscita):
        return f"limite d'uso dell'account, reset alle {ora.group(1)}"
    # Un'ora inventata è peggio di un'ora mancante: chi legge `runs/tempi.csv`
    # la userebbe (decisione 4).
    return "limite d'uso dell'account, ora del reset non leggibile"


# Il margine dopo l'ora del reset: la CLI la scrive al minuto, e un rilancio
# sull'ora esatta troverebbe il limite ancora chiuso (PBI-519, decisione 3).
MARGINE_DEL_RESET = timedelta(minutes=5)


def ora_di_ripresa(ora: str, scritta: datetime) -> datetime:
    """Quando si può riprendere: la prima occorrenza di `ora` («7:50pm», «3am»)
    successiva a `scritta`, l'istante in cui l'uscita è stata scritta, più
    `MARGINE_DEL_RESET`. Il fuso è quello del runner (PBI-519, decisione 3)."""
    lettura = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s?([ap]m)", ora.strip(), re.IGNORECASE)
    ore, minuti, meridiano = int(lettura.group(1)), int(lettura.group(2) or 0), lettura.group(3)
    ore = ore % 12 + (12 if meridiano.lower() == "pm" else 0)
    reset = scritta.replace(hour=ore, minute=minuti, second=0, microsecond=0)
    if reset <= scritta:
        reset += timedelta(days=1)
    return reset + MARGINE_DEL_RESET


def riprendi_dopo_il_limite(registro: dict) -> str:
    """`riprendi_dopo` di un `senza esito`: l'ora di ripresa in ISO se il file di
    stderr dell'invocazione porta la frase del limite con l'ora del reset, o `""`
    (PBI-519, decisione 1). Lo stdout è testo del modello e non conta (`ADR-0027`),
    e con codice d'uscita 0 la CLI non si è fermata sul limite.
    L'istante in cui l'uscita è stata scritta è quello del file di stderr, e
    senza quel file non c'è ripresa: il giro chiude come prima."""
    if registro["codice"] == 0:
        return ""
    dentro = Path(registro["stderr"])
    try:
        uscita = dentro.read_text(encoding="utf-8", errors="replace")
        scritta = datetime.fromtimestamp(dentro.stat().st_mtime)
    except OSError:
        return ""
    if not FRASE_DEL_LIMITE.search(uscita) or not (ora := ORA_DEL_RESET.search(uscita)):
        return ""
    return ora_di_ripresa(ora.group(1), scritta).isoformat(timespec="minutes")


def nota_senza_esito(registro: dict, uscita: str = "") -> str:
    """La nota di un `senza esito`: chi non ha chiamato, o chi è scaduto, dove
    guardare e, se l'uscita dell'agente lo dice, il limite d'uso con l'ora del
    reset."""
    if "tetto_minuti" in registro:
        chi = f"tetto di {registro['tetto_minuti']:g} minuti superato ({registro['ruolo']})"
    else:
        chi = f"il {registro['ruolo']} non ha chiamato né fatto né fermati"
    nota = (f"{chi} · "
            f"codice d'uscita {registro['codice']} · stdout {registro['stdout']} · "
            f"stderr {registro['stderr']}")
    return " · ".join(t for t in (nota, limite_d_uso(uscita)) if t)


def git(*args: str) -> str:
    code, out = esegui(["git", *args], REPO, timeout=120)
    if code != 0:
        raise RuntimeError(f"git {' '.join(args)} → {out}")
    return out.strip()


def gira_gate(attivi: set[str], base: str | None = None) -> list[tuple[str, str]]:
    """Gate rossi con la coda del loro output. Lista vuota = tutto verde.

    `attivi` sono i nomi dei gate accesi a prescindere dal diff — oggi nessuno.
    Il diff si chiede a git solo se un gate ha `solo_se_tocca`: gli altri non
    ne hanno bisogno, e un `git diff` a vuoto è una chiamata in più da finta.
    """
    rossi: list[tuple[str, str]] = []
    toccati = file_toccati(base) if any(g.solo_se_tocca for g in GATE) else set()
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
ESTENSIONI_CODICE = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sql", ".sh",
                     ".java"}

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
    nome: str       # `Classe::funzione` dalla collezione (python), o il titolo (vitest)
    linguaggio: str  # python | vitest | junit


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
    # JUnit: la sequenza `src/test/` di Maven, e non una cartella `test` qualunque
    # (PBI-505, decisione 1): `src/main/java/.../test/Foo.java` è produzione. Solo
    # i `.java` sono test: un `src/test/setup.ts` o `helpers.py` non nasce come test
    # (non regressione), e non è nemmeno produzione (PBI-515).
    if nome.endswith(".java") and sotto_src_test(percorso):
        return True
    return (nome.startswith("test_") and nome.endswith(".py")) or nome.endswith("_test.py")


def sotto_src_test(percorso: str) -> bool:
    """Il percorso sta sotto la sequenza `src/test/` di Maven (PBI-505, decisione 1)."""
    parti = Path(percorso).parts
    return any(parti[i:i + 2] == ("src", "test") for i in range(len(parti) - 1))


def e_file_di_produzione(percorso: str) -> bool:
    """Codice che non è un test. È la metà del criterio che ferma PBI-328.

    Sotto `src/test/` nessun file è produzione, qualunque estensione (PBI-515,
    decisione 1): uno script che rigenera le fixture è supporto dei test, e il
    lucchetto lo lascia scrivere in `TEST_ONLY` come scrive i test.
    """
    if sotto_src_test(percorso):
        return False
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
# Accanto alla fase, e per la stessa strada, lo sha di base del giro: è da lì che
# `--chiedi-impl` conta i commit del ramo (PBI-380, decisione 3).
FILE_DELLA_BASE = "asdlc-base"
# E nello stesso posto il percorso della cartella delle collezioni di pytest del
# giro, un JSON per sha. La cartella sta nella `LOG_DIR`, non qui: al giro 1 di
# PBI-396 ne sono rimaste dieci in `.git/worktrees/ada-run/`, accanto a una fase
# che il runner installato non conosceva. Quella della base la scrive
# `apri_la_fase()`, quelle dei commit del ramo chi le legge per primo (PBI-396,
# decisione 5).
CARTELLA_DELLE_COLLEZIONI = "asdlc-collezioni"
FASE_TEST_ONLY = "TEST_ONLY"
FASE_IMPL = "IMPL"


def percorso_della_fase(cartella: Path, nome: str = FILE_DELLA_FASE) -> Path | None:
    """Dove sta la fase per l'albero che contiene `cartella`, o `None` se non c'è
    un repository sotto — e allora non si scrive da nessuna parte. Con `nome`
    un altro file dello stesso posto: la base del giro, o dove stanno le sue
    collezioni."""
    try:
        detto = git("-C", str(cartella), "rev-parse", "--git-path", nome)
    except RuntimeError:
        return None
    if not detto or Path(detto).name != nome:
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


# Il segno del commento di riga per estensione (PBI-515, decisione 5): un `#` in
# un `.sql` non è un commento. Le estensioni con `//` hanno anche i blocchi `/* … */`.
COMMENTO_DI_RIGA = {".sh": "#", ".py": "#", ".sql": "--",
                    **dict.fromkeys((".java", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"), "//")}
RE_BLOCCO_DI_COMMENTO = re.compile(r"/\*.*?\*/", re.DOTALL)


def e_scheletro_vuoto(percorso: str, contenuto: str) -> bool:
    """Il contenuto è fatto solo di righe bianche e commenti (PBI-515, decisione 4):
    uno scheletro così non anticipa nessun comportamento, e il rosso resta quello
    del test. Il commento è quello del linguaggio del file (decisione 5)."""
    segno = COMMENTO_DI_RIGA.get(Path(percorso).suffix)
    if segno == "//":
        contenuto = RE_BLOCCO_DI_COMMENTO.sub("", contenuto)
    return all(not riga.strip() or (segno is not None and riga.strip().startswith(segno))
               for riga in contenuto.splitlines())


def guardia_di_fase(fase: str | None, percorso: str,
                    contenuto: str | None = None) -> str | None:
    """Perché questa scrittura non si fa, o `None` se si fa.

    Torna una **ragione** e non un booleano perché è ciò che l'agente legge: un
    blocco che non spiega come procedere costa il turno che avrebbe risparmiato.

    `contenuto` è il file intero, quando chi chiede lo conosce: in `TEST_ONLY`
    uno scheletro vuoto di produzione si scrive (PBI-515, decisione 4). Senza
    contenuto la produzione resta chiusa.
    """
    if fase is None:
        return None
    if Path(percorso).name == FILE_DELLA_FASE:
        return (f"{percorso}: la fase non la decidi tu. Il passaggio a {FASE_IMPL} lo "
                f"apre `tools/asdlc/runner.py --chiedi-impl`, e solo se i test nuovi "
                f"falliscono davvero.")
    if fase == FASE_TEST_ONLY:
        if e_file_di_produzione(percorso) and not (
                contenuto is not None and e_scheletro_vuoto(percorso, contenuto)):
            return (f"{percorso} è codice di produzione e il giro è in {FASE_TEST_ONLY}: "
                    f"qui si scrivono solo i test. Scrivi il test del comportamento che "
                    f"ti serve, poi `tools/asdlc/runner.py --chiedi-impl`: se è rosso, la "
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
    if percorso.endswith(".java"):
        return "junit"
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

    Da PBI-396 serve alla sola lettura di vitest. Per Python la nascita si legge
    dalla collezione di pytest: i test di un `note.txt` diventato file di test
    nascono perché il genitore non li ha, senza guardare il diff.
    """
    if (voce.vecchio and e_file_di_test(voce.vecchio)
            and linguaggio_del_test(voce.vecchio) is not None):
        return [voce.vecchio, voce.percorso]
    return [voce.percorso]


def nomi_dei_test(diff: str) -> tuple[list[str], set[str]]:
    """I titoli dei test vitest aggiunti e quelli cancellati, dalle righe del
    diff. Per Python la nascita si legge dalla collezione (PBI-396)."""
    aggiunti: list[str] = []
    tolti: set[str] = set()
    for riga in diff.splitlines():
        if riga.startswith(("+++", "---")) or riga[:1] not in ("+", "-"):
            continue
        trovato = RE_TEST_JS.match(riga[1:])
        if trovato is None:
            continue
        nome = decodifica_escape(trovato.group(2))
        if riga[0] == "+":
            aggiunti.append(nome)
        else:
            tolti.add(nome)
    return aggiunti, tolti


# Le annotazioni che fanno di un metodo un test JUnit (PBI-505, decisione 3), e la
# dichiarazione di un metodo: modificatori e tipo di ritorno, poi il nome e `(`.
RE_ANNOTAZIONE_JUNIT = re.compile(r"^\s*@(?:Test|ParameterizedTest|RepeatedTest)\b")
RE_METODO_JAVA = re.compile(r"^\s*(?:[\w<>\[\],.?]+\s+)+(\w+)\s*\(")
# Un'annotazione in testa a una riga, con gli argomenti fra parentesi se ci sono.
RE_ANNOTAZIONE_IN_TESTA = re.compile(r"^\s*@\w+(?:\([^)]*\))?")
# Le righe di contesto del diff di un test JUnit: il file intero, perché
# l'annotazione di un metodo rinominato è una riga che il diff non cambia, e
# quante ne stiano sopra il metodo non lo dice nessuno (PBI-514).
CONTESTO_JUNIT = 1_000_000


def nomi_dei_test_junit(diff: str, classe: str) -> tuple[list[str], set[str]]:
    """I nomi `Classe#metodo` dei test JUnit aggiunti e quelli tolti, dalle righe
    del diff (PBI-505, decisione 3): il metodo che segue un'annotazione `@Test`,
    `@ParameterizedTest` o `@RepeatedTest`, anche con argomenti e con altre
    annotazioni in mezzo, o sulla stessa riga del metodo.

    Un'annotazione di una riga di **contesto** vale per tutti e due i lati: il
    metodo che la segue è un test se la sua riga è `+` o `-`, come nel test
    rinominato sotto un `@ParameterizedTest` che non cambia (PBI-514, decisione
    1). Un metodo di contesto chiude l'attesa senza nascere: il diff non lo tocca."""
    aggiunti: list[str] = []
    tolti: set[str] = set()
    attesa = {"+": False, "-": False}
    for riga in diff.splitlines():
        if riga.startswith(("+++", "---")) or riga[:1] not in ("+", "-", " "):
            continue
        segno, testo = riga[0], riga[1:]
        lati = tuple(attesa) if segno == " " else (segno,)
        trovato = None
        if RE_ANNOTAZIONE_JUNIT.match(testo):
            for lato in lati:
                attesa[lato] = True
            resto = testo
            while (iniziale := RE_ANNOTAZIONE_IN_TESTA.match(resto)) is not None:
                resto = resto[iniziale.end():]
            trovato = RE_METODO_JAVA.match(resto)
        elif any(attesa[lato] for lato in lati) and not testo.lstrip().startswith("@"):
            trovato = RE_METODO_JAVA.match(testo)
        if trovato is None:
            continue
        for lato in lati:
            attesa[lato] = False
        nome = f"{classe}#{trovato.group(1)}"
        if segno == "+":
            aggiunti.append(nome)
        elif segno == "-":
            tolti.add(nome)
    return aggiunti, tolti


# --- La collezione di pytest: quali test esistono in un albero (PBI-396) --------


class Raccolta(NamedTuple):
    """Ciò che il plugin `asdlc_collezione` ha scritto: i nodeid raccolti e i
    file che non si raccolgono, relativi al `--rootdir` del comando."""

    nodi: list[str]
    non_raccolti: list[str]


@contextmanager
def plugin_della_collezione():
    """Il `PYTHONPATH` da cui pytest importa il plugin `asdlc_collezione`.

    I gate girano col venv del progetto, dove il pacchetto del runner non è
    installato. Si mette sul percorso una cartella con dentro il solo modulo del
    plugin, con un link, e non la cartella che lo contiene: nel venv del runner
    quella è `site-packages`, e porterebbe nei test del progetto ogni altra
    libreria del runner. Il plugin sta accanto al pacchetto `asdlc`, nel
    sorgente come installato (`py-modules`), e non dentro: il pacchetto del
    runner sul percorso metterebbe in ombra l'`asdlc` dell'albero esaminato
    (PBI-396, decisione 3; difetto 84 di PBI-102).
    """
    plugin = Path(__file__).resolve().parent.parent / "asdlc_collezione.py"
    with tempfile.TemporaryDirectory(prefix="asdlc-plugin-") as cartella:
        (Path(cartella) / plugin.name).symlink_to(plugin)
        yield os.pathsep.join(filter(None, [cartella, os.environ.get("PYTHONPATH")]))


def raccolta_di_pytest(cartella: Path, comando: list[str]) -> Raccolta:
    """La collezione del `comando` di pytest lanciato da `cartella`, con
    `--collect-only` e il plugin (PBI-396, decisione 3). Il `--rootdir` è la
    cartella di lancio, come per i test che il gate esegue (PBI-391)."""
    with tempfile.TemporaryDirectory(prefix="asdlc-collezione-") as tmp, \
            plugin_della_collezione() as percorso:
        dato = Path(tmp) / "collezione.json"
        argv = [*comando, "--collect-only", "-p", "asdlc_collezione",
                f"--asdlc-collezione={dato}", f"--rootdir={Path(cartella).resolve()}"]
        codice, uscita = esegui(argv, cartella, timeout=TETTO_DEI_TEST,
                                ambiente={"PYTHONPATH": percorso})
        try:
            letto = json.loads(dato.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GuastoDelGate(f"`{' '.join(argv)}` in {cartella} → uscita {codice}, "
                                f"collezione non scritta in {dato}\n"
                                f"{uscita.strip()[-1000:]}") from exc
    return Raccolta(list(letto["nodi"]), list(letto["non_raccolti"]))


def nome_del_nodo(nodo: str) -> tuple[str, str]:
    """`(file, nome)` di un nodeid di pytest (PBI-396, decisione 2): il file
    relativo al `--rootdir`, e il resto senza il suffisso `[…]` della
    parametrizzazione, che può contenere a sua volta un `::` — `Classe::funzione`,
    `Esterna::Interna::funzione`, o `funzione` fuori da una classe."""
    percorso, _, resto = nodo.partition("::")
    return percorso, resto.partition("[")[0]


def nomi_dallast(sorgente: str) -> list[str]:
    """I nomi dei test di un file che pytest non raccoglie, letti col parser
    (PBI-396, decisione 4): le funzioni `test*` a livello di modulo e quelle
    dentro le classi `Test*`, annidate comprese, nella forma di `nome_del_nodo`.

    Valgono i predefiniti di pytest: `python_functions`, `python_classes` e
    `python_files` di una configurazione non si leggono qui (PBI-396, §Fuori
    scope). Un sorgente che non si analizza non ha nomi.
    """
    try:
        modulo = ast.parse(sorgente)
    except (SyntaxError, ValueError):
        return []

    def dentro(corpo: list[ast.stmt], classi: list[str]) -> list[str]:
        nomi: list[str] = []
        for nodo in corpo:
            if (isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and nodo.name.startswith("test")):
                nomi.append("::".join([*classi, nodo.name]))
            elif isinstance(nodo, ast.ClassDef) and nodo.name.startswith("Test"):
                nomi += dentro(nodo.body, [*classi, nodo.name])
        return nomi

    return dentro(modulo.body, [])


def collezione_dellalbero(albero: Path) -> dict[str, str]:
    """I test Python che esistono in `albero`, per nome, ognuno col suo file
    dalla radice del repository: la collezione dei gate di pytest di
    `asdlc.toml`, ognuno lanciato dal suo `cwd` (PBI-396, decisione 3). I casi
    di un test parametrizzato fanno un nome solo. I file che pytest non
    raccoglie hanno i nomi letti dall'AST, in quell'albero (decisione 4)."""
    nomi: dict[str, str] = {}
    for g in GATE:
        if "pytest" not in g.comando:
            continue
        raccolta = raccolta_di_pytest(albero / g.cwd, list(g.comando))
        for nodo in raccolta.nodi:
            percorso, nome = nome_del_nodo(nodo)
            nomi.setdefault(nome, (Path(g.cwd) / percorso).as_posix())
        for percorso in raccolta.non_raccolti:
            sorgente = leggi_sorgente(albero / g.cwd / percorso)
            for nome in nomi_dallast(sorgente or ""):
                nomi.setdefault(nome, (Path(g.cwd) / percorso).as_posix())
    return nomi


def cartella_delle_collezioni() -> Path | None:
    """La cartella della `LOG_DIR` in cui il giro tiene le sue collezioni, letta
    dal file che `apri_la_fase()` lascia accanto alla fase. `None` fuori da un
    giro (PBI-396, decisione 5)."""
    file = percorso_della_fase(REPO, CARTELLA_DELLE_COLLEZIONI)
    if file is None or not file.is_file():
        return None
    detto = file.read_text(encoding="utf-8").strip()
    return Path(detto) if detto else None


def collezione_al_commit(sha: str,
                         memoria: dict[str, dict[str, str]] | None = None) -> dict[str, str]:
    """La collezione del commit `sha`, nel suo albero usa e getta.

    Dentro un giro si tiene nella cartella di `cartella_delle_collezioni()`, e
    non si ricalcola: la base vale per tutto il giro, e un commit non cambia
    (PBI-396, decisione 5). Fuori da un giro si calcola e non si scrive: non
    c'è un `chiudi_la_fase()` che la tolga.

    In `memoria`, se c'è, la collezione resta per sha anche fuori da un giro:
    il gate del rosso ne passa una per tutta la sua passata, e il genitore di
    un commit è il commit prima, o la base. Così ogni albero si raccoglie una
    volta sola, e non tre per commit (PBI-396, decisione 9).

    Una chiave di cache del runner è uno sha risolto, mai un riferimento
    (PBI-397): `HEAD`, un ramo, `origin/main` si risolvono con `git rev-parse`
    prima di diventare il nome del file o la voce della `memoria`. Con `"HEAD"`
    come chiave, un secondo `--chiedi-impl` rileggeva la collezione di un `HEAD`
    di prima. Un riferimento che non si risolve alza, e non si ripiega sul nome.
    """
    sha = git("rev-parse", "--verify", f"{sha}^{{commit}}")
    if memoria is not None and sha in memoria:
        return memoria[sha]
    cartella = cartella_delle_collezioni()
    file = cartella / f"{sha}.json" if cartella is not None else None
    if file is not None and file.is_file():
        collezione = json.loads(file.read_text(encoding="utf-8"))
    else:
        with worktree_usa_e_getta(sha) as albero:
            collezione = collezione_dellalbero(albero)
        if file is not None:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(collezione), encoding="utf-8")
    if memoria is not None:
        memoria[sha] = collezione
    return collezione


def nascite_python(collezione: dict[str, str], genitore: dict[str, str],
                   base: dict[str, str]) -> list[TestNuovo]:
    """La regola della nascita di un test Python, una per il gate e per il
    lucchetto (PBI-396, decisione 1): nasce ciò che c'è nella `collezione` e non
    in quella del `genitore` né in quella della `base`. Un test tolto da un file
    e scritto in un altro ha lo stesso nome dall'una e dall'altra parte, e non
    nasce; un nome che c'è alla base non nasce mai nel ramo, anche se un commit
    del ramo lo aveva tolto."""
    return [TestNuovo(file, nome, "python") for nome, file in collezione.items()
            if nome not in genitore and nome not in base]


def spostamenti_python(collezione: dict[str, str], genitore: dict[str, str],
                       base: dict[str, str]) -> list[str]:
    """I test che non nascono e cambiano file: c'erano nel `genitore`, o alla
    `base`, in un file diverso da quello dove stanno nella `collezione`. È ciò che
    `nascite_python` lascia fuori, contato perché il gate lo scriva (PBI-396,
    decisione 7)."""
    return [nome for nome, file in collezione.items()
            if genitore.get(nome, base.get(nome, file)) != file]


def tocca_un_test_python(voce: VoceDiCommit) -> bool:
    """Se la voce tocca un file di test Python, su uno dei suoi due lati: solo un
    commit così chiede la collezione (PBI-396, decisione 6)."""
    return any(p is not None and e_file_di_test(p) and linguaggio_del_test(p) == "python"
               for p in (voce.percorso, voce.vecchio))


def genitore_del_commit(sha: str) -> str | None:
    """Il primo genitore di `sha`, o `None` per il primo commit della storia."""
    try:
        return git("rev-parse", "--verify", "--quiet", f"{sha}^") or None
    except RuntimeError:
        return None


def base_del_commit(base: str, sha: str) -> str | None:
    """Il commit da cui il ramo di `sha` si è staccato da `base`: la base contro
    cui si decide una nascita. `None` se le due storie non si incontrano."""
    try:
        return git("merge-base", base, sha) or None
    except RuntimeError:
        return None


def test_nuovi_del_commit(sha: str, file: list[VoceDiCommit] | None = None,
                          base: str | None = None,
                          spostati: list[str] | None = None,
                          collezioni: dict[str, dict[str, str]] | None = None
                          ) -> list[TestNuovo]:
    """I test che **nascono** in questo commit del ramo che parte da `base`, il
    ramo di `asdlc.toml` se non è detto. In `spostati`, se c'è, si aggiungono i
    test Python che il commit ha spostato di file (`spostamenti_python`). In
    `collezioni`, se c'è, si tengono le collezioni già lette, per sha, da una
    chiamata all'altra (`collezione_al_commit`, PBI-396, decisione 9).

    Per i test Python la nascita si legge dalla collezione di pytest
    (`nascite_python`, PBI-396): un nome che c'era nel genitore o alla base non
    nasce, in qualunque file finisca. Il diff, file per file, non vedeva un test tolto da
    un file e scritto in un altro senza `git mv` (difetto 81 di PBI-102).

    Per vitest e JUnit (PBI-505) la nascita si legge ancora dal diff. Uno stesso
    nome cancellato e riaggiunto è un trasloco, non una nascita: è il caso del file di test
    riscritto per intero, e senza questa sottrazione il gate farebbe girare tutta
    la suite di quel commit per poi fermarla come nata verde. Il diff di un rename
    si chiede nominando **tutti e due** i lati. Con il solo nome nuovo git non
    applica il rename detection — per riconoscere una copia deve vedere da dove
    arriva — e il file risulta interamente aggiunto: da lì il gate leggeva una
    nascita per ogni test dentro un file semplicemente spostato.
    """
    voci = file if file is not None else file_del_commit(sha)
    nuovi: list[TestNuovo] = []
    for voce in voci:
        percorso = voce.percorso
        linguaggio = linguaggio_del_test(percorso) if e_file_di_test(percorso) else None
        if linguaggio not in ("vitest", "junit"):
            continue
        diff = diff_del_file(voce, "show", "--format=", sha, lati=lati_del_diff(voce),
                             contesto=CONTESTO_JUNIT if linguaggio == "junit" else 0)
        aggiunti, tolti = (nomi_dei_test_junit(diff, Path(percorso).stem)
                           if linguaggio == "junit" else nomi_dei_test(diff))
        nuovi += [TestNuovo(percorso, n, linguaggio) for n in aggiunti if n not in tolti]
    if any(tocca_un_test_python(v) for v in voci):
        genitore = genitore_del_commit(sha)
        alla_base = base_del_commit(base if base is not None else BASE, sha)
        tre = (collezione_al_commit(sha, collezioni),
               collezione_al_commit(genitore, collezioni) if genitore else {},
               collezione_al_commit(alla_base, collezioni) if alla_base else {})
        nuovi += nascite_python(*tre)
        if spostati is not None:
            spostati += spostamenti_python(*tre)
    return nuovi


def base_del_lucchetto() -> str:
    """La base da cui il lucchetto conta: lo sha che `apri_la_fase()` lascia
    accanto alla fase, e fuori da un giro il ramo di `asdlc.toml` (PBI-380,
    decisione 3)."""
    file = percorso_della_fase(REPO, FILE_DELLA_BASE)
    return (file.read_text(encoding="utf-8").strip()
            if file is not None and file.is_file() else "") or BASE


def test_nuovi_dellalbero() -> list[TestNuovo]:
    """I test che nascono nell'**albero di lavoro**, rispetto a `HEAD`.

    Il gate del rosso legge un commit; il lucchetto deve leggere ciò che non è
    ancora committato, perché il permesso di implementare si chiede **prima** del
    commit — è tutto il punto della differenza fra impedire e accertare.

    Per Python la regola è quella del gate, `nascite_python` (PBI-396, decisione
    1): il commit è l'albero di lavoro, il genitore è `HEAD`, e la base è quella
    del giro. Per vitest e JUnit (PBI-505) si legge il diff.

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
        if linguaggio not in ("vitest", "junit"):
            continue
        if voce in non_tracciati:
            sorgente = leggi_sorgente(REPO / percorso) or ""
            diff = "".join(f"+{riga}\n" for riga in sorgente.splitlines())
        else:
            diff = diff_del_file(voce, "diff", "HEAD", lati=lati_del_diff(voce))
        aggiunti, tolti = (nomi_dei_test_junit(diff, Path(percorso).stem)
                           if linguaggio == "junit" else nomi_dei_test(diff))
        nuovi += [TestNuovo(percorso, n, linguaggio) for n in aggiunti if n not in tolti]
    if any(tocca_un_test_python(v) for v in tracciati + non_tracciati):
        testa = git("rev-parse", "HEAD")
        alla_base = base_del_commit(base_del_lucchetto(), testa)
        nuovi += nascite_python(collezione_dellalbero(REPO), collezione_al_commit(testa),
                                collezione_al_commit(alla_base) if alla_base else {})
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


# Gli alberi usa e getta montati e smontati da quando il processo è partito. Il
# giro ne legge la differenza fra l'inizio e la fine (PBI-363, decisione 6): se
# una strada salta lo smontaggio, i due numeri divergono anche senza un avviso.
USA_E_GETTA: Counter[str] = Counter()


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
        USA_E_GETTA["montati"] += 1
        for prestito in PRESTITI:
            sorgente, destinazione = REPO / prestito, albero / prestito
            if sorgente.exists() and not destinazione.exists() and destinazione.parent.is_dir():
                destinazione.symlink_to(sorgente)
        yield albero
    finally:
        try:
            git("worktree", "remove", "--force", str(albero))
            USA_E_GETTA["smontati"] += 1
        except RuntimeError as exc:  # smontarlo è igiene, non è il verdetto
            print(f"    ⚠️  worktree non smontato: {str(exc)[:200]}")
        shutil.rmtree(cartella, ignore_errors=True)


def id_pytest(sorgente: str, nome: str, relativo: str) -> str | None:
    """`file::Classe::test`, letto dall'AST del file **a quel commit**.

    Prende la sorgente e non un percorso, perché il file a quel commit si legge in
    due modi: dal worktree quando c'è, e da `git show sha:percorso` quando il gate
    ferma dal solo diff e non esegue niente.

    Il `nome` di un test Python nato viene dalla collezione e porta già le sue
    classi, `Classe::funzione` (PBI-396, decisione 2): si cerca quel cammino. Un
    nome senza `::` si cerca a livello di modulo e dentro le classi.

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
    if "::" in nome:
        # Il nome della collezione porta già le sue classi (PBI-396, decisione 2):
        # si segue quel cammino, e non si cerca altrove.
        *classi, funzione = nome.split("::")
        corpo = modulo.body
        for classe in classi:
            dentro = [n for n in corpo if isinstance(n, ast.ClassDef) and n.name == classe]
            if len(dentro) != 1:
                return None
            corpo = dentro[0].body
        uniche = [n for n in corpo if isinstance(n, definizioni) and n.name == funzione]
        return f"{relativo}::{nome}" if len(uniche) == 1 else None
    trovati: list[str] = []
    for nodo in modulo.body:
        if isinstance(nodo, definizioni) and nodo.name == nome:
            trovati.append(f"{relativo}::{nome}")
        if isinstance(nodo, ast.ClassDef):
            for figlio in nodo.body:
                if isinstance(figlio, definizioni) and figlio.name == nome:
                    trovati.append(f"{relativo}::{nodo.name}::{nome}")
    # Due classi che definiscono un test omonimo sono normali, e un nome senza le
    # classi dice solo che *un* `def` con quel nome è nato: quale, non lo dice. Prendere il
    # primo è la scelta che sembra innocua e non lo è — il gate esegue il test
    # vecchio, lo trova verde, e stampa «nato verde» su un test che era rosso.
    return trovati[0] if len(trovati) == 1 else None


def caso_junit(chiave: str) -> tuple[str, str]:
    """`(classname, name)` con cui pytest scrive nel `--junitxml` il test di node
    id `chiave`, senza parametro nel `name` (PBI-390, decisione 2).

    È la trasformazione di pytest scritta qui, e non importata da
    `_pytest.junitxml`, che è privato: il percorso con i `/` diventati punti e
    senza `.py`, e le classi unite da punti dietro, fanno il `classname`.
    """
    percorso, *classi, nome = chiave.split("::")
    modulo = re.sub(r"\.py$", "", percorso.replace("/", "."))
    return ".".join([modulo, *classi]), nome


def dove_gira(percorso: str) -> tuple[str, str]:
    """La cartella da cui si lancia il test, e il suo percorso da lì.

    Le cartelle sono i `cwd` dei gate di `GATE`, tolto `.` (PBI-504), e fra due
    annidate vince la più lunga. Un test isolato che girasse da un'altra parte non
    sarebbe più lo stesso test — e un id scritto col prefisso `backend/` non si
    riesegue da `backend/`.
    """
    cartelle = sorted((g.cwd for g in GATE if g.cwd != "."), key=len, reverse=True)
    for radice in cartelle:
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
    pytest, il titolo per vitest, `Classe#metodo` per JUnit — all'id con cui quel test si riesegue a mano. Per
    pytest sono la stessa cosa; per vitest no, perché `-t` filtra per nome dentro un
    file e l'id da riscrivere è `file -t nome`.
    """

    cartella: Path
    argv: list[str]
    linguaggio: str
    etichette: dict[str, str]
    rapporto: Path | None = None  # dove vitest scrive il suo json, pytest il JUnit
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
    tutto-o-niente. Per JUnit un comando per cartella, quello di `[junit].comando`
    con `{test}` sostituito (PBI-505): senza la sezione i test JUnit sono orfani.

    Le **etichette** sono ciò che finisce nell'elenco del gate, e vanno scritte come
    si eseguono — un `file::nome` senza la classe che lo contiene dà «not found» a
    chi prova a rieseguirlo, e fa sembrare sbagliato il gate.
    """
    per_pytest: dict[Path, list[str]] = {}
    per_vitest: dict[tuple[Path, str], list[str]] = {}
    per_junit: dict[Path, list[str]] = {}
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
        elif t.linguaggio == "junit":
            # Senza `[junit]` il runner non indovina un comando (PBI-505, decisione 5).
            if JUNIT_COMANDO is None:
                orfani.append(t.nome)
                continue
            per_junit.setdefault(cartella, []).append(t.nome)
            origine[t.nome] = t
        else:
            per_vitest.setdefault((cartella, relativo), []).append(t.nome)
            origine[t.nome] = t

    # L'esito per test e il tipo di ogni fallimento vengono dal `--junitxml`, in un
    # file accanto al worktree come il json di vitest (PBI-390, decisione 1): le
    # righe di `-vv` e il riepilogo di `-rf` si leggevano con regex che un
    # parametro con uno spazio non combaciava. `-vv` e `-rf` restano per chi legge
    # la coda nel rapporto del giro, e non si leggono più: `-rf` scrive in fondo,
    # per ogni test fallito, l'eccezione che l'ha fatto fallire, e `-vv` non taglia
    # quel messaggio alla larghezza del terminale. `--tb=no` perché il traceback qui
    # non serve — la coda che finisce nel rapporto è la stessa per tutti.
    # `--rootdir` è la cartella di lancio perché `caso_junit()` ricava il caso dal
    # node id relativo a quella: lasciato a pytest, il rootdir lo decide il primo
    # file di configurazione che trova — un `tools/pyproject.toml` anche senza
    # `[tool.pytest.ini_options]` — e nessun caso combacia più con la sua chiave
    # (PBI-391, difetto 67 di PBI-102).
    comandi: list[ComandoDiProva] = []
    for numero, (cartella, nodi) in enumerate(per_pytest.items()):
        rapporto = albero.parent / f"pytest-{numero}.xml"
        comandi.append(ComandoDiProva(
            cartella, ["pytest", "--tb=no", "-vv", "-rf", f"--rootdir={cartella.resolve()}",
                       f"--junitxml={rapporto}", *nodi],
            "python", {nodo: nodo for nodo in nodi}, rapporto,
            origine={nodo: origine[nodo] for nodo in nodi}))
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
    for cartella, nomi in per_junit.items():
        comandi.append(ComandoDiProva(
            cartella, [a.replace("{test}", sintassi_del_test(nomi)) for a in JUNIT_COMANDO],
            "junit", {nome: nome for nome in nomi},
            origine={nome: origine[nome] for nome in nomi}))
    return comandi, orfani


def sintassi_del_test(nomi: list[str]) -> str:
    """`Classe#m1+m2,Altra#m3`: i `Classe#metodo` raggruppati per classe, nella
    sintassi di `-Dtest=` di Maven (PBI-505, decisione 4)."""
    per_classe: dict[str, list[str]] = {}
    for nome in nomi:
        classe, _, metodo = nome.partition("#")
        per_classe.setdefault(classe, []).append(metodo)
    return ",".join(f"{classe}#{'+'.join(metodi)}" for classe, metodi in per_classe.items())


def radice_del_junit(rapporto: Path | None) -> ET.Element:
    """La radice del `--junitxml` di pytest. Un rapporto che manca o non si legge
    è `GuastoDelGate`, col percorso atteso (PBI-390, decisione 5)."""
    try:
        return ET.parse(rapporto).getroot()
    except (TypeError, OSError, ET.ParseError) as exc:
        raise GuastoDelGate(f"rapporto di pytest assente o illeggibile: {rapporto} "
                            f"({type(exc).__name__}: {str(exc)[:200]})") from exc


def casi_delle_chiavi(radice: ET.Element,
                      chiavi: Iterable[str]) -> list[tuple[str, ET.Element]]:
    """I `testcase` del JUnit che appartengono alle `chiavi` chieste, ognuno con
    la sua. Il caso si lega alla chiave con `caso_junit()`, e il parametro del
    `name` si toglie: un test parametrico ha un caso per parametro, tutti suoi."""
    per_caso = {caso_junit(chiave): chiave for chiave in chiavi}
    trovati: list[tuple[str, ET.Element]] = []
    for caso in radice.iter("testcase"):
        chiave = per_caso.get((caso.get("classname", ""),
                               caso.get("name", "").partition("[")[0]))
        if chiave is not None:
            trovati.append((chiave, caso))
    return trovati


def leggi_esito(rapporto: Path | None) -> str:
    """L'esito di pytest per le chiavi che nel `--junitxml` non hanno un caso loro:
    `rosso` quando pytest non ha raccolto un modulo, `nessuno` in ogni altro caso.

    L'errore di raccolta è il caso col `classname` vuoto e un `<error>` (PBI-390,
    decisione 5): il caso più comune di test-first in Python è un `from app.x
    import y` che a quel commit non esiste ancora, e leggerlo come «non ha
    girato» fermerebbe proprio il ciclo fatto bene. I totali del comando non
    decidono per un test, come per vitest (PBI-376, decisione 2).

    Non si guarda l'exit code: `pytest` torna 0 anche con tutto saltato.

    Un rapporto che manca o non si legge è `GuastoDelGate`, col percorso atteso:
    il gate non ha guardato niente, e «nessuno» accuserebbe il Builder di un
    rosso mancato (PBI-390, decisione 5).
    """
    for caso in radice_del_junit(rapporto).iter("testcase"):
        if not caso.get("classname") and caso.find("error") is not None:
            return "rosso"
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

# Un'asserzione del test: l'`assert` che pytest riscrive, e il `Failed` di
# `pytest.fail` e di `pytest.raises` che non vede l'eccezione attesa.
TIPI_DI_ASSERZIONE = {"AssertionError", "Failed"}


def tipo_del_fallimento(messaggio: str) -> str:
    """Il tipo dell'eccezione, dal `message` del `<failure>` nel JUnit: la stessa
    forma che scrive il riepilogo di `-rf` (PBI-390, decisione 4).

    Un `assert` riscritto da pytest senza messaggio suo non porta il tipo davanti
    — il messaggio è la sua espressione, `assert 1 == 2` — e lì il tipo è
    `AssertionError`. Tutto il resto comincia col nome della classe:
    `NameError: name 'righe' is not defined`, o solo `AssertionError`.
    """
    if messaggio == "assert" or messaggio.startswith("assert "):
        return "AssertionError"
    trovato = re.match(r"[A-Za-z_][\w.]*(?=:|$)", messaggio)
    return trovato.group(0) if trovato else ""


def tipi_dei_falliti(rapporto: Path | None, chiavi: Iterable[str]) -> dict[str, list[str]]:
    """Per ogni chiave con un caso `<failure>` nel JUnit di pytest, il tipo di
    eccezione che l'ha fatto fallire, uno **per caso** se è parametrico. Un
    `<error>` non porta un tipo: il test non è arrivato all'asserzione (PBI-390,
    decisione 4)."""
    tipi: dict[str, list[str]] = defaultdict(list)
    for chiave, caso in casi_delle_chiavi(radice_del_junit(rapporto), chiavi):
        fallimento = caso.find("failure")
        if fallimento is not None:
            tipi[chiave].append(tipo_del_fallimento(fallimento.get("message", "")))
    return dict(tipi)

# `pending` e `todo` sono i due modi in cui vitest dice «non l'ho eseguito».
ESITI_DI_VITEST = {"passed": "verde", "failed": "rosso",
                   "skipped": "saltato", "pending": "saltato", "todo": "saltato"}


def piu_forte(uno: str, altro: str) -> str:
    return max(uno, altro, key=ORDINE_ESITI.index)


def esito_del_caso(caso: ET.Element) -> str:
    """L'esito di un `testcase` del JUnit, dal suo figlio (PBI-390, decisione 3):
    `<failure>` o `<error>` è rosso, `<skipped>` è saltato, nessuno dei tre è
    verde. Anche `xfail` scrive `<skipped>`: è un rosso già previsto, osservato
    non lo si vede, e sta con lo `skip` invece che col rosso vero."""
    if caso.find("failure") is not None or caso.find("error") is not None:
        return "rosso"
    if caso.find("skipped") is not None:
        return "saltato"
    return "verde"


def esiti_di_pytest(rapporto: Path | None, chiavi: Iterable[str]) -> dict[str, str]:
    """Il verdetto **per test**, dal `--junitxml` di pytest, per le `chiavi` chieste.

    Un test parametrico vale il più forte dei suoi casi (`casi_delle_chiavi`).
    Un rapporto che non c'è torna **vuoto**, come per vitest: il `GuastoDelGate`
    lo alza `leggi_esito`.
    """
    try:
        radice = radice_del_junit(rapporto)
    except GuastoDelGate:
        return {}
    letti: dict[str, str] = {}
    for chiave, caso in casi_delle_chiavi(radice, chiavi):
        letti[chiave] = piu_forte(letti.get(chiave, "nessuno"), esito_del_caso(caso))
    return letti


def esiti_di_vitest(rapporto: Path | None) -> dict[str, str]:
    """Il verdetto per test, dal `--reporter=json` di vitest, per titolo.

    Un rapporto che non c'è torna **vuoto** e non «tutto verde»: chi non ha letto
    niente non ha visto niente, e allora vale l'esito del comando intero — che
    per un rapporto che manca è `GuastoDelGate` (`esito_dei_file_di_vitest`).
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
    caso è un rosso perché il JUnit di pytest ha il caso dell'errore di raccolta e
    `leggi_esito` lo legge; col
    `--reporter=json` di vitest i conteggi non sono a schermo, e senza questa lettura
    lo stesso identico ciclo TDD risulta `nessuno` e ferma il gate.

    Solo quel caso, e non lo stato del file in generale: un file `passed` con zero
    test è il filtro `-t` che non ha matchato niente, e leggerlo come verde darebbe
    per girato un test che non è mai partito — il gate passerebbe in silenzio proprio
    dove non ha guardato.

    Un rapporto che manca o non si legge è `GuastoDelGate`, col percorso atteso:
    il gate non ha guardato niente, e «nessuno» accuserebbe il Builder di un
    rosso mancato (PBI-376, decisione 3; difetto 25).
    """
    try:
        dati = json.loads(rapporto.read_text(encoding="utf-8"))
    except (AttributeError, OSError, ValueError) as exc:
        raise GuastoDelGate(f"rapporto di vitest assente o illeggibile: {rapporto} "
                            f"({type(exc).__name__}: {str(exc)[:200]})") from exc
    for file in dati.get("testResults", []):
        if file.get("status") == "failed" and not file.get("assertionResults"):
            return "rosso"
    return "nessuno"


# Dove Maven scrive i `TEST-*.xml`: surefire per i test unitari, failsafe per
# quelli di integrazione, sotto la cartella di lancio (PBI-505, decisione 6).
CARTELLE_DEI_RAPPORTI_JUNIT = ("target/surefire-reports", "target/failsafe-reports")


def rapporti_di_junit(cartella: Path) -> list[Path]:
    return [file for rapporti in CARTELLE_DEI_RAPPORTI_JUNIT
            for file in sorted((cartella / rapporti).glob("TEST-*.xml"))]


def esiti_di_junit(cartella: Path, chiavi: Iterable[str]) -> dict[str, str]:
    """Il verdetto **per test** dai rapporti di surefire e failsafe sotto `cartella`
    (PBI-505, decisione 6). Un caso è di una chiave `Classe#metodo` se il suo
    `classname` finisce con `.Classe` e il `name` è il metodo, o comincia con il
    metodo seguito da `(` o `[` (i parametrici di JUnit 5). Un test vale il più
    forte dei suoi casi; senza casi non ha una voce."""
    attese = [(chiave, *chiave.partition("#")[::2]) for chiave in chiavi]
    letti: dict[str, str] = {}
    for file in rapporti_di_junit(cartella):
        try:
            radice = ET.parse(file).getroot()
        except (OSError, ET.ParseError):
            continue
        for caso in radice.iter("testcase"):
            classe, nome = caso.get("classname", ""), caso.get("name", "")
            for chiave, atteso, metodo in attese:
                if ((classe == atteso or classe.endswith(f".{atteso}"))
                        and (nome == metodo or nome.startswith((f"{metodo}(", f"{metodo}[")))):
                    letti[chiave] = piu_forte(letti.get(chiave, "nessuno"), esito_del_caso(caso))
    return letti


# Il tetto di un comando di prova, in secondi.
TETTO_DEI_TEST = 1800


def esiti_del_comando(c: ComandoDiProva) -> tuple[dict[str, str], str]:
    """Gira il comando e torna l'esito di **ogni** test che gli era stato chiesto.

    Un errore di **raccolta** — il `from app.x import y` che a quel commit non
    esiste ancora, cioè il rosso più comune del test-first — non scrive un caso
    per test: lì vale l'esito del comando intero, che è la sola cosa che si sa.
    Quell'esito viene dal rapporto e non dallo schermo, e non sono i totali:
    i totali di tutto il comando darebbero a `B` senza una voce sua l'esito di
    `A`. Resta il solo modulo che pytest non raccoglie (`leggi_esito`, PBI-390,
    decisione 5) e il solo file che vitest non carica (`esito_dei_file_di_vitest`,
    PBI-376, decisione 2). Per JUnit l'esito viene dai `TEST-*.xml` di Maven sotto
    la cartella di lancio, tolti prima di lanciare (`esiti_di_junit`, PBI-505).
    """
    if c.rapporto is not None:
        # Il percorso del rapporto resta fra una misura e l'altra (in `apri` è
        # `REPO.parent`): un vitest o un pytest che esce senza scriverlo
        # lascerebbe leggere l'esito di un commit misurato prima. Tolto qui, il
        # file che si legge dopo è di questo comando, o manca (PBI-376,
        # decisione 3; PBI-390, decisione 1).
        c.rapporto.unlink(missing_ok=True)
    if c.linguaggio == "junit":
        # Maven scrive i suoi rapporti sotto la cartella di lancio e li lascia lì:
        # quelli di un lancio prima sarebbero l'esito di un altro commit (decisione 6).
        for vecchio in rapporti_di_junit(c.cartella):
            vecchio.unlink()
    try:
        codice, uscita = esegui(c.argv, c.cartella, timeout=TETTO_DEI_TEST)
    except subprocess.TimeoutExpired as exc:
        # vitest fermato prima della fine il rapporto non lo scrive, e un
        # rapporto che manca è un guasto del gate (PBI-376, decisioni 3 e 5).
        if c.linguaggio == "vitest":
            raise GuastoDelGate(
                f"vitest scaduto dopo {TETTO_DEI_TEST} secondi: `{' '.join(c.argv)}` "
                f"in {c.cartella}, rapporto non scritto in {c.rapporto}") from exc
        # Per pytest un timeout lo dicono i test: a quel commit non terminano, e
        # il gate non indovina. Lo strumento ha girato — quindi non è un guasto,
        # e il rapporto che pytest non ha scritto non si cerca (PBI-390, §Fuori
        # scope).
        return {chiave: "nessuno" for chiave in c.etichette}, "i test non terminano a quel commit"
    if c.linguaggio == "junit":
        letti = esiti_di_junit(c.cartella, c.etichette)
        # Maven che non compila esce senza rapporti: il rosso del test-first che
        # nomina una classe non ancora scritta (PBI-505, decisione 8).
        complessivo = "rosso" if "COMPILATION ERROR" in uscita else "nessuno"
        # Un'uscita non zero senza rapporti e senza compilazione fallita non l'ha
        # detta un test: il gate non ha guardato (decisione 8).
        if complessivo == "nessuno" and codice != 0 and not rapporti_di_junit(c.cartella):
            raise GuastoDelGate(f"`{' '.join(c.argv)}` in {c.cartella} → uscita {codice}\n"
                                f"{uscita.strip()[-1000:]}")
        return {chiave: letti.get(chiave, complessivo) for chiave in c.etichette}, uscita
    letti = (esiti_di_pytest(c.rapporto, c.etichette) if c.linguaggio == "python"
             else esiti_di_vitest(c.rapporto))
    complessivo = (leggi_esito(c.rapporto) if c.linguaggio == "python"
                   else esito_dei_file_di_vitest(c.rapporto))
    if complessivo == "nessuno" and codice not in CODICI_DEL_TEST[c.linguaggio]:
        raise GuastoDelGate(f"`{' '.join(c.argv)}` in {c.cartella} → uscita {codice}\n"
                            f"{uscita.strip()[-1000:]}")
    return {chiave: letti.get(chiave, complessivo) for chiave in c.etichette}, uscita


# --- La quarta lettura: il test nato verde passa se morde (PBI-105) ------------
#
# «Nato verde» è una prova di processo, e ha un falso positivo sistematico: la
# guardia che il Critic ordina su un comportamento che c'è già nasce verde per
# forza. La domanda di sostanza — *se guasto il codice che copre, se ne accorge?* —
# si misura: si mutano le funzioni di produzione che il branch ha toccato (PBI-378)
# e si rigira quel test. Un mutante ucciso è la prova che il test guarda quel codice.

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


def diff_del_file(voce: VoceDiCommit, *dove: str, lati: list[str] | None = None,
                  contesto: int = 0) -> str:
    """Il diff di una voce, su `dove` — `("diff", "base...sha")`,
    `("show", "--format=", sha)`, `("diff", "HEAD")`. È l'unico posto del runner
    che chiede a git il diff di un file (PBI-387). È `--unified=0` se `contesto`
    non dice altre righe di contesto: JUnit le chiede per leggere le annotazioni che
    il diff non cambia (PBI-514).

    Un rename si chiede nominando **tutti e due** i lati: con il solo percorso
    nuovo git non applica il rename detection, e il file risulta aggiunto per
    intero (difetti 31 e 61 di PBI-102). `-M` è scritto e non lasciato a
    `diff.renames`, come in `file_del_commit`. `lati` sostituisce i due lati
    quando la regola è un'altra: per i test la dà `lati_del_diff`.

    Un rename che **entra** in produzione — il lato vecchio non è produzione, il
    nuovo sì — si chiede col solo percorso nuovo, cioè come un file aggiunto per
    intero: un `git mv nota.txt backend/app/x.py` non porta hunk, e il modulo
    entrerebbe senza una riga e senza un RED (difetto 63, PBI-389). Il confine
    lo decide `e_file_di_produzione`; con `lati` esplicito la regola non vale.
    """
    if lati is None:
        lati = [voce.percorso]
        entra = (not e_file_di_produzione(voce.vecchio or voce.percorso)
                 and e_file_di_produzione(voce.percorso))
        if voce.vecchio and not entra:
            lati.insert(0, voce.vecchio)
    return git(*dove, f"--unified={contesto}", "-M", "--", *lati)


def hunk_di_produzione(base: str, sha: str) -> dict[str, list[tuple[int, int]]]:
    """Per ogni file di **produzione** che il branch ha cambiato fino a `sha`, gli
    hunk come `(inizio, quante)` nella numerazione del file a quel commit.

    `base...sha` e non `base..sha`: il diff parte dal merge-base, così un `main`
    andato avanti nel frattempo non entra nel conto come se fosse del branch.

    La chiave è il percorso a `sha`, anche per un file spostato: è lì che le
    righe sono numerate. Un rename senza cambi fra due file di produzione non
    porta hunk, e nessuna sua funzione entra nel perimetro; uno che entra in
    produzione da fuori porta il file intero (`diff_del_file`, PBI-389).
    """
    hunk: dict[str, list[tuple[int, int]]] = {}
    for voce in voci_del_name_status(git("diff", "--name-status", "-M", f"{base}...{sha}")):
        if not e_file_di_produzione(voce.percorso):
            continue
        diff = diff_del_file(voce, "diff", f"{base}...{sha}")
        hunk[voce.percorso] = [(int(inizio), int(quante) if quante else 1)
                               for inizio, quante in RE_HUNK.findall(diff)]
    return hunk


def righe_cambiate(base: str, sha: str) -> dict[str, set[int]]:
    """Per ogni file di produzione, le righe nuove o toccate. Una riga tolta non
    c'è più da guastare, e un file di soli `-` non compare: dove si è cancellato
    lo dice `cancellazioni`."""
    righe: dict[str, set[int]] = {}
    for percorso, elenco in hunk_di_produzione(base, sha).items():
        nuove = {n for inizio, quante in elenco for n in range(inizio, inizio + quante)}
        if nuove:
            righe[percorso] = nuove
    return righe


def cancellazioni(base: str, sha: str) -> dict[str, set[int]]:
    """Per ogni file di produzione, la posizione degli hunk di sole cancellazioni
    (`+c,0`): la riga `c` del file a quel commit, quella dopo cui si è cancellato.
    Non è una riga da guastare, ma dice quale funzione il branch ha toccato."""
    posizioni: dict[str, set[int]] = {}
    for percorso, elenco in hunk_di_produzione(base, sha).items():
        dove = {inizio for inizio, quante in elenco if quante == 0}
        if dove:
            posizioni[percorso] = dove
    return posizioni


def funzioni_del_modulo(albero: ast.AST) -> list[tuple[str, int, int]]:
    """Ogni `def` e `async def` del modulo come `(nome, prima, ultima)`, col nome
    qualificato dalle classi e dalle funzioni che la contengono: `Classe.metodo`."""
    trovate: list[tuple[str, int, int]] = []

    def visita(nodo: ast.AST, prefisso: str) -> None:
        for figlio in ast.iter_child_nodes(nodo):
            if isinstance(figlio, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                nome = prefisso + figlio.name
                if not isinstance(figlio, ast.ClassDef):
                    trovate.append((nome, figlio.lineno, figlio.end_lineno or figlio.lineno))
                visita(figlio, nome + ".")
            else:
                visita(figlio, prefisso)

    visita(albero, "")
    return trovate


def righe_del_perimetro(percorso: str, sorgente: str, righe: set[int],
                        posizioni: set[int]) -> tuple[set[int], list[str]]:
    """Le righe da mutare di un file — tutte quelle delle funzioni toccate, e le
    righe cambiate che stanno fuori da ogni funzione — e le voci del rapporto:
    `<percorso>::<funzione> (dal diff)` per ogni funzione toccata (PBI-378).

    Una funzione è toccata se contiene una riga cambiata o la posizione di una
    cancellazione, e vale la più interna — un metodo, una funzione annidata — dai
    `lineno`/`end_lineno` dell'AST. Un file che non è Python, o un `.py` che a quel
    commit non si analizza, resta per riga, e la sua voce dice perché.
    """
    if not percorso.endswith(".py"):
        return righe, [f"{percorso} (per riga: non è Python)"]
    try:
        funzioni = funzioni_del_modulo(ast.parse(sorgente))
    except SyntaxError:
        return righe, [f"{percorso} (per riga: il file non si analizza)"]
    perimetro: set[int] = set()
    voci: list[str] = []
    for riga in sorted(righe | posizioni):
        dentro = [f for f in funzioni if f[1] <= riga <= f[2]]
        if dentro:
            nome, prima, ultima = max(dentro, key=lambda f: f[1])
            perimetro.update(range(prima, ultima + 1))
            voce = f"{percorso}::{nome} (dal diff)"
            if voce not in voci:
                voci.append(voce)
        elif riga in righe:
            perimetro.add(riga)
    return perimetro, voci


def righe_delle_docstring(sorgente: str) -> set[int]:
    """Le righe delle docstring di modulo, classe e funzione, dall'AST: il primo
    enunciato del corpo, se è una costante stringa. Cancellarne la prosa non cambia
    niente, e un mutante che ogni guardia sopravvive non prova niente (PBI-378).
    Un sorgente che non è Python valido — un `.ts` — non ne ha."""
    try:
        albero = ast.parse(sorgente)
    except SyntaxError:
        return set()
    righe: set[int] = set()
    for nodo in ast.walk(albero):
        if not isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)) or not nodo.body:
            continue
        primo = nodo.body[0]
        if (isinstance(primo, ast.Expr) and isinstance(primo.value, ast.Constant)
                and isinstance(primo.value.value, str)):
            righe.update(range(primo.lineno, (primo.end_lineno or primo.lineno) + 1))
    return righe


def mutanti_del_sorgente(sorgente: str, righe: set[int]) -> list[Mutante]:
    """I mutanti delle sole `righe` (1-based) di `sorgente`, in ordine di riga.

    Sulle righe del perimetro (`righe_del_perimetro`) e non su tutto il file: è il
    codice che quel giro ha toccato, ed è l'unico di cui i suoi test rispondono.
    La cancellazione è l'operatore più forte e vale in tutti e due i linguaggi; una riga di sola
    punteggiatura non si cancella, perché romperebbe la sintassi e basta, e un
    guasto di forma non è una prova che il test morda. Le righe di una docstring
    non danno mutanti, in nessun perimetro (`righe_delle_docstring`).
    """
    mutanti: list[Mutante] = []
    docstring = righe_delle_docstring(sorgente)
    for numero, testo in enumerate(sorgente.splitlines(), start=1):
        if numero not in righe or numero in docstring:
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


def falliti_per_asserzione(c: ComandoDiProva) -> set[str]:
    """Le chiavi dei test che hanno **girato e fallito**, e solo quelle.

    È la lettura stretta, diversa da `esiti_del_comando`: lì un errore di raccolta
    vale come rosso di tutto il comando, perché il `from app.x import y` che non
    esiste ancora è il rosso più comune del test-first. Qui vale il contrario. Un
    mutante che rompe la sintassi fa fallire *tutto* — l'errore di raccolta di
    pytest, il file che vitest non carica — e nessun caso per test lo dice: non è
    il test che ha morso, è il file che non c'è più. Contare quelli farebbe
    passare ogni guardia, perché cancellare una riga a caso rompe la sintassi una
    volta su tre. E l'`<error>` per test — la fixture che esplode — sta dalla
    stessa parte: il test non è arrivato all'asserzione.

    Né ci arriva il `FAILED` per un'eccezione del codice — un `NameError` perché la
    riga cancellata definiva un nome: è un guasto di esistenza, e lo uccide anche
    un test che non guarda niente (la #254, PBI-365). In pytest il tipo si legge
    dal `<failure>` del JUnit (PBI-390), e conta solo un `AssertionError` o un
    `Failed`: un fallimento di cui il rapporto non dice il tipo non è
    un'asserzione misurata.
    """
    if c.linguaggio == "python":
        return {chiave for chiave, tipi in tipi_dei_falliti(c.rapporto, c.etichette).items()
                if any(tipo in TIPI_DI_ASSERZIONE for tipo in tipi)}
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

    Morde solo se fallisce **per asserzione**. Il rapporto — il json di vitest,
    il JUnit di pytest — si toglie prima di girare: se il mutante fa morire il
    processo prima di scriverlo, resterebbe quello del giro prima a dire il
    falso. Per pytest un rapporto che manca è `GuastoDelGate` (PBI-390,
    decisione 5). Un test che non termina sotto il mutante non ha morso: ha
    girato a vuoto.
    """
    if c.rapporto is not None:
        c.rapporto.unlink(missing_ok=True)
    try:
        esegui(c.argv, c.cartella, timeout=600)
    except subprocess.TimeoutExpired:
        return SOPRAVVISSUTO, ""
    # I tipi di **questo** test, uno per caso se è parametrico.
    tipi = (tipi_dei_falliti(c.rapporto, [chiave]).get(chiave, [])
            if c.linguaggio == "python" else [])
    if chiave not in falliti_per_asserzione(c):
        return (PER_ECCEZIONE, tipi[0]) if tipi else (SOPRAVVISSUTO, "")
    if c.linguaggio != "python":
        return UCCISO, TIPO_NON_MISURATO
    return UCCISO, next(tipo for tipo in tipi if tipo in TIPI_DI_ASSERZIONE)


# `Guardia-su: backend/app/m.py::Classe.metodo`, una per riga nel corpo del commit.
RE_GUARDIA_SU = re.compile(r"^Guardia-su:\s*(\S+?)::(\S+)\s*$", re.MULTILINE)


def funzione_nominata(sorgente: str, nome: str) -> tuple[int, int] | None:
    """Le righe `(prima, ultima)` di `funzione` o `Classe.metodo` nel modulo, o
    `None` se lì non c'è o il sorgente non si analizza."""
    try:
        albero = ast.parse(sorgente)
    except SyntaxError:
        return None
    return next(((prima, ultima) for trovato, prima, ultima in funzioni_del_modulo(albero)
                 if trovato == nome), None)


def funzioni_nominate(albero: Path, sha: str
                      ) -> tuple[dict[str, dict[str, set[int]]], list[str]]:
    """Le funzioni che il commit nomina con `Guardia-su:`, per file e per nome con
    le loro righe, cercate nel file a quel commit; e una nota per ogni nome che non
    si trova (PBI-378, decisione 3: si segnala, non si blocca — `ADR-0008`).

    Entra solo codice di produzione dentro il worktree. Un test che nomina sé
    stesso muore del proprio `==`→`!=` e passerebbe sempre; un percorso assoluto,
    con `..` o dietro un link farebbe scrivere i mutanti fuori dal worktree
    usa-e-getta. Lì va una nota, come per il nome non trovato."""
    nominate: dict[str, dict[str, set[int]]] = defaultdict(dict)
    note: list[str] = []
    for percorso, nome in RE_GUARDIA_SU.findall(git("show", "--no-patch", "--format=%B", sha)):
        dentro = (albero / percorso).resolve().is_relative_to(albero.resolve())
        if not (dentro and e_file_di_produzione(percorso)):
            note.append(f"{percorso}::{nome} (funzione nominata fuori dalla produzione)")
            continue
        sorgente =leggi_sorgente(albero / percorso) if percorso.endswith(".py") else None
        trovata = funzione_nominata(sorgente, nome) if sorgente is not None else None
        if trovata is None:
            note.append(f"{percorso}::{nome} (funzione nominata non trovata)")
            continue
        nominate[percorso][nome] = set(range(trovata[0], trovata[1] + 1))
    return dict(nominate), note


def quarta_lettura(albero: Path, base: str, sha: str, comando: ComandoDiProva,
                   chiave: str, nominate: dict[str, dict[str, set[int]]] | None = None,
                   perimetro: list[str] | None = None
                   ) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
    """Il test nato verde, rigirato contro i mutanti delle funzioni che il branch
    ha toccato.

    Torna la prova del primo mutante che lo fa fallire per asserzione, e tutte le
    prove fatte fino a lì: `{"mutante", "esito", "tipo"}`, una per mutante, perché
    chi legge il rapporto veda anche quelli sopravvissuti e quelli falliti per
    eccezione (PBI-365). `None` quando nessuno lo uccide: quel test non guarda il
    codice che il branch ha toccato, e la lettura resta «nato verde».

    Un mutante alla volta, nello stesso worktree in cui il test è stato visto
    verde: il file si riscrive con la riga guasta, il test gira da solo, e si esce
    al primo kill perché uno basta — il gate chiede che il test osservi il codice
    toccato, non che lo copra tutto. `nominate` sono le funzioni che il commit
    nomina con `Guardia-su:` (`funzioni_nominate`): entrano nel perimetro anche se
    il branch non le tocca. `perimetro`, se c'è, si riempie con le funzioni mutate
    e da dove sono entrate — `dal diff` o `nominata` — e con i file rimasti per
    riga e il perché, **prima** di mutare, così il
    rapporto lo dice intero anche quando si esce al primo kill (PBI-378).
    """
    test = comando.origine[chiave]
    da_solo, _ = comandi_dei_test(albero, [test])
    prove: list[dict[str, str]] = []
    perimetro = perimetro if perimetro is not None else []
    cambiate, cancellate = righe_cambiate(base, sha), cancellazioni(base, sha)
    nominate = nominate or {}
    piano: list[tuple[str, Path, str, set[int]]] = []
    for percorso in sorted(cambiate.keys() | cancellate.keys() | nominate.keys()):
        if linguaggio_del_file(percorso) != test.linguaggio:
            continue  # un test Python non morde un .ts, e rigirarlo lì è tempo perso
        file = albero / percorso
        sorgente = leggi_sorgente(file)
        if sorgente is None:
            continue
        righe, voci = righe_del_perimetro(percorso, sorgente, cambiate.get(percorso, set()),
                                          cancellate.get(percorso, set()))
        perimetro += voci
        for nome, sue in nominate.get(percorso, {}).items():
            perimetro.append(f"{percorso}::{nome} (nominata)")
            righe = righe | sue
        piano.append((percorso, file, sorgente, righe))
    for percorso, file, sorgente, righe in piano:
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


class Punta:
    """La punta del ramo, dove si riprova la guardia che non morde al suo commit
    (PBI-393, revisione del 01/10 di `ADR-0022`).

    Il worktree si estrae alla prima guardia che ne ha bisogno e vale per tutte
    quelle della stessa chiamata di `gate_del_rosso()`; se nessuna ne ha bisogno
    non si estrae. Lo smonta la `pila` del gate, comunque vada.
    """

    def __init__(self, ref: str, pila: ExitStack):
        self.ref = ref
        self.sha = ""
        self._pila = pila
        self._albero: Path | None = None

    def albero(self) -> Path:
        if self._albero is None:
            # `^{commit}`: un ramo fermato si conserva come tag annotato, e lo
            # sha dell'oggetto tag nel rapporto non si ritrova in `git log`.
            self.sha = git("rev-parse", f"{self.ref}^{{commit}}")
            self._albero = self._pila.enter_context(worktree_usa_e_getta(self.sha))
        return self._albero


NON_SI_TROVA_ALLA_PUNTA = "alla punta il test non si trova"
NON_VERDE_ALLA_PUNTA = "alla punta il test non è verde"


def morso_alla_punta(punta: Punta, base: str, sha: str, test: TestNuovo
                     ) -> tuple[dict[str, str] | None, list[dict[str, str]], list[str], str]:
    """La quarta lettura della guardia sull'albero della punta, con il perimetro di
    `base...punta` più le funzioni che il commit `sha` della guardia nomina con
    `Guardia-su:`, cercate nell'albero della punta (decisione 3): `(ucciso,
    prove, perimetro)` come `quarta_lettura()`, e il perché se alla punta non si
    è potuta fare.

    Il test si cerca con lo stesso file e lo stesso nome, e non altrove (decisione
    4). Deve essere verde: un test rosso lo fa fallire ogni mutante, e non è un morso.
    """
    albero = punta.albero()
    comandi, _ = comandi_dei_test(albero, [test])
    if not comandi:
        return None, [], [], NON_SI_TROVA_ALLA_PUNTA
    [comando] = comandi
    [chiave] = comando.etichette
    esiti, _ = esiti_del_comando(comando)
    if esiti[chiave] != "verde":
        return None, [], [], NON_VERDE_ALLA_PUNTA
    nominate, note = funzioni_nominate(albero, sha)
    perimetro: list[str] = []
    ucciso, prove = quarta_lettura(albero, base, punta.sha, comando, chiave, nominate,
                                   perimetro)
    return ucciso, prove, perimetro + note, ""


def esamina_il_commit(sha: str, titolo: str, nuovi: list[TestNuovo], base: str,
                      morsi: list[dict[str, str]] | None = None,
                      punta: Punta | None = None) -> list[dict[str, str]]:
    """Estrae il commit e ci gira dentro i suoi test nuovi. Attende il rosso.

    Un test nato verde ha la quarta lettura prima di finire fra i mancati: se
    morde un mutante delle funzioni toccate dal branch, va in `morsi` — commit, test, mutante,
    tipo del fallimento e le prove fatte fino al kill — e non ferma niente. Se lì
    non morde, e c'è la `punta`, si riprova sull'albero della punta: il morso di lì
    va in `morsi` con `"dove": "punta"` (PBI-393).
    """
    mancati: list[dict[str, str]] = []
    morsi = morsi if morsi is not None else []
    with worktree_usa_e_getta(sha) as albero:
        nominate, note = funzioni_nominate(albero, sha)
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
                    perimetro: list[str] = []
                    ucciso, prove = quarta_lettura(albero, base, sha, comando, chiave,
                                                   nominate, perimetro)
                    perimetro += note
                    if ucciso is not None:
                        morsi.append({"commit": sha[:7], "titolo": titolo,
                                      "test": etichetta, "mutante": ucciso["mutante"],
                                      "tipo": ucciso["tipo"], "prove": prove,
                                      "perimetro": perimetro, "dove": "commit"})
                        continue
                    if punta is not None:
                        ucciso, alla_punta, suo, assente = morso_alla_punta(
                            punta, base, sha, comando.origine[chiave])
                        if ucciso is not None:
                            morsi.append({"commit": sha[:7], "titolo": titolo,
                                          "test": etichetta, "mutante": ucciso["mutante"],
                                          "tipo": ucciso["tipo"], "prove": alla_punta,
                                          "perimetro": suo, "dove": "punta",
                                          "punta": punta.sha[:7]})
                            continue
                        lettura = lettura_dei_due_alberi(prove, perimetro, punta.sha,
                                                         alla_punta, suo, assente)
                    else:
                        lettura = lettura_del_verde(prove, perimetro)
                per_lettura[lettura].append(etichetta)
            for lettura, elenco in per_lettura.items():
                mancati.append(voce_mancata(sha, titolo, elenco, lettura, coda))
    return mancati


def descrizione_del_morso(m: dict, rientro: str) -> str:
    """La riga «nato verde, ma morde» con il mutante **e** il tipo, e sotto le
    prove fatte fino al kill, una per riga: `mutante: esito (tipo)`."""
    tipo = f" ({m['tipo']})" if m.get("tipo") else ""
    righe = [f"{rientro}→ nato verde, non morde al suo commit, morde alla punta "
             f"`{m['punta']}`: {m['mutante']}{tipo}" if m.get("dove") == "punta" else
             f"{rientro}→ nato verde, ma morde: {m['mutante']}{tipo}"]
    if m.get("perimetro"):
        righe.append(f"{rientro}  perimetro: {', '.join(m['perimetro'])}")
    for p in m.get("prove", []):
        tipo = f" ({p['tipo']})" if p["tipo"] else ""
        righe.append(f"{rientro}  · {p['mutante']}: {p['esito']}{tipo}")
    return "\n".join(righe)


def lettura_del_verde(prove: list[dict[str, str]], perimetro: list[str] | None = None) -> str:
    """Cosa si scrive di un nato verde dopo la quarta lettura.

    Con dei mutanti provati la lettura è più forte di «il codice c'era già»: dice
    che il test **non guarda** le funzioni che il branch ha toccato. Senza — il
    branch non ha righe di produzione, o i suoi mutanti non compilano — resta quella
    di prima, e lo dice: zero provati non è «nessuno lo fa fallire».

    I mutanti che l'hanno fatto fallire per eccezione si contano a parte, col tipo:
    chi legge un «non morde» deve vedere che un guasto il test l'ha sentito, e
    perché non conta (PBI-365). E il `perimetro`, se c'è, chiude la lettura: chi
    legge «non morde» deve vedere dove il gate ha guardato (PBI-378).
    """
    if not prove:
        return f"{ESITI_MANCATI['verde']} — e {misura_dei_mutanti(prove, perimetro)}"
    return (f"nato verde e non morde: a quel commit il test passa, e "
            f"{misura_dei_mutanti(prove, perimetro)}")


def misura_dei_mutanti(prove: list[dict[str, str]], perimetro: list[str] | None) -> str:
    """I mutanti provati in un albero, quelli falliti per eccezione col tipo, e il
    perimetro: la parte di `lettura_del_verde()` che si ripete per ogni albero."""
    if not prove:
        misura = "nessun mutante da provare nel perimetro"
    else:
        quanti = "1 mutante provato" if len(prove) == 1 else f"{len(prove)} mutanti provati"
        misura = f"{quanti} nelle funzioni che il branch ha toccato non lo fanno fallire"
        tipi = [p["tipo"] for p in prove if p["esito"] == PER_ECCEZIONE]
        if tipi:
            misura += (f" per asserzione; {len(tipi)} {PER_ECCEZIONE} "
                       f"({', '.join(sorted(set(tipi)))}), che non è un morso")
    if perimetro:
        misura += f"; perimetro: {', '.join(perimetro)}"
    return misura


def lettura_dei_due_alberi(prove: list[dict[str, str]], perimetro: list[str], punta: str,
                           alla_punta: list[dict[str, str]], suo: list[str],
                           assente: str = "") -> str:
    """La lettura della guardia che non morde né al suo commit né alla punta: una
    sola, che nomina tutti e due gli alberi (PBI-393, decisione 5). Se alla punta
    il test non si è potuto provare, `assente` dice perché (decisione 4)."""
    return (f"nato verde e non morde, né al suo commit né alla punta `{punta[:7]}`: "
            f"al suo commit: {misura_dei_mutanti(prove, perimetro)}; "
            + (assente or f"alla punta: {misura_dei_mutanti(alla_punta, suo)}"))


def gate_del_rosso(base: str | None = None, ref: str = "HEAD",
                   visti: set[str] | None = None,
                   morsi: list[dict[str, str]] | None = None,
                   spostati: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    """I commit del branch in cui un test è nato senza essere mai stato rosso.

    `base` è il ramo di `asdlc.toml` se non è detto: un default scritto nella
    firma si congelerebbe all'import, e un TOML di prova non lo muoverebbe.

    Lista vuota = il gate passa. `visti` è l'insieme dei commit già guardati e viene
    **riempito**: il gate sta dentro un ciclo che può ripetersi cinque volte, e
    rigirare ogni volta la storia intera moltiplicherebbe il tempo macchina per le
    revisioni. `morsi` si riempie allo stesso modo, con i test nati verdi che hanno
    ucciso un mutante: passano, e il rapporto deve dire perché. E `spostati`, coi
    commit che spostano test Python di file: non nascono, e chi legge deve vedere
    che la regola ha agito (PBI-396, decisione 7).

    Non si ferma al primo mancato: chi legge deve avere l'elenco intero — commit,
    test, esito — perché la lettura la fa una persona, e una persona decide meglio
    su tre casi che su uno.
    """
    base = base if base is not None else BASE
    visti = visti if visti is not None else set()
    mancati: list[dict[str, str]] = []
    # Le collezioni di pytest lette in questa passata, per sha: il genitore di un
    # commit è il commit prima, o la base, e si raccoglie una volta (PBI-396,
    # decisione 9).
    collezioni: dict[str, dict[str, str]] = {}
    with ExitStack() as pila:
        punta = Punta(ref, pila)
        for sha in commit_da_esaminare(base, ref, visti):
            visti.add(sha)
            file = file_del_commit(sha)
            suoi: list[str] = []
            nuovi = test_nuovi_del_commit(sha, file, base, suoi, collezioni)
            if suoi and spostati is not None:
                spostati.append({"commit": sha[:7], "spostati": str(len(suoi)),
                                 "titolo": git("show", "--no-patch", "--format=%s", sha)})
            if not nuovi:
                continue  # un refactor non porta test nuovi, e la regola morde su quelli
            titolo = git("show", "--no-patch", "--format=%s", sha)
            produzione = [v.percorso for v in file if e_file_di_produzione(v.percorso)]
            if produzione:
                mancati.append(voce_mancata(sha, titolo, etichette_al_commit(sha, nuovi),
                                            MISTO, ", ".join(produzione[:10])))
                continue
            mancati += esamina_il_commit(sha, titolo, nuovi, base, morsi, punta)
    return mancati


def gate_per_il_critic(attivi: set[str], morsi: list[dict], base: str | None = None) -> str:
    """Ciò che i gate hanno misurato, per il prompt del Critic (PBI-371, decisione 6).

    Il Critic non esegue niente: senza questo testo, su PBI-365, è andato a
    cercarsi il log del giro. Si chiama dopo i gate verdi e il gate del rosso
    passato, quindi i gate che hanno girato sono verdi."""
    toccati = file_toccati(base) if any(g.solo_se_tocca for g in GATE) else set()
    righe = ["", "## I gate di questo giro", "",
             "Misurati dal runner su `HEAD`, prima di chiamarti.", ""]
    for g in GATE:
        righe.append(f"- `{g.nome}`: verde" if acceso(g, attivi, toccati) else
                     f"- `{g.nome}`: non girato, il diff non tocca {', '.join(g.solo_se_tocca)}")
    righe.append("- gate del rosso: " + ("verde" if GATE_DEL_ROSSO_ATTIVO else
                                         "spento da asdlc.toml"))
    if morsi:
        righe += ["", "Test nati verdi che il gate del rosso ha lasciato passare perché "
                  "mordono un mutante:", ""]
        for m in morsi:
            righe += [f"- `{m['commit']}` {m['titolo']}", f"  {m['test']}",
                      descrizione_del_morso(m, "  ")]
    return "\n".join(righe) + "\n"


def revisione_critica(pbi_path: Path, gate: str = "", base: str | None = None) -> Verdetto:
    """Sessione NUOVA, modello diverso, sola lettura: il Critic non è il Builder.
    `gate` è ciò che i gate del giro hanno misurato, in coda al prompt; `base` lo
    sha del giro, da cui il Critic legge il diff (PBI-374)."""
    print("    critic … ", end="", flush=True)
    try:
        percorso = pbi_path.relative_to(REPO)
    except ValueError:
        percorso = pbi_path
    # Scrive il prompt su file per evitare limiti di lunghezza degli argomenti CLI
    prompt_file, file_esito = file_dell_invocazione("critic")
    prompt_file.write_text(MODELLO_CRITIC.format(base=base if base is not None else BASE,
                                                 pbi_path=percorso) + gate,
                           encoding="utf-8")
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
    argomento di 65.536 caratteri accentati sfiora il limite di un argomento.

    Un commento che non parte non ferma niente: la PR è aperta, i file restano,
    e la nota dice quali revisioni mancano e perché (`ADR-0008`). Vale anche per
    un `gh` in timeout e per un file che non si legge, **senza alzare**: qui la
    nota nomina le revisioni mancate, mentre un'eccezione arriverebbe a
    `esegui_pbi()` come «dopo la chiusura» generico, e i commenti dopo il primo
    non partirebbero."""
    mancate: list[str] = []
    ragione = ""

    def mancata(r: dict, perche: str) -> None:
        nonlocal ragione
        print(f"    ⚠️  commento della revisione {r['revisione']} non partito: {perche}")
        if str(r["revisione"]) not in mancate:
            mancate.append(str(r["revisione"]))
        ragione = ragione or perche

    with tempfile.TemporaryDirectory() as cartella:
        for r in e.rapporti_critic:
            try:
                testo = Path(r["percorso"]).read_text(encoding="utf-8")
            except OSError as exc:
                mancata(r, str(exc)[:200])
                continue
            titolo = f"Critic — revisione {r['revisione']} — {r['verdetto']}"
            for i, parte in enumerate(parti_del_commento(titolo, testo)):
                corpo = Path(cartella) / f"{r['revisione']}-{i}.md"
                try:
                    corpo.write_text(parte, encoding="utf-8")
                    code, out = esegui(["gh", "pr", "comment", url, "--body-file", str(corpo)],
                                       REPO, timeout=300)
                except (subprocess.TimeoutExpired, OSError) as exc:
                    code, out = 1, str(exc)
                if code != 0:
                    mancata(r, out.strip()[:200])
    if mancate:
        nota = (f"rapporto del Critic non commentato sulla PR (revisioni {', '.join(mancate)}): "
                f"{ragione} — i file restano in {LOG_DIR}")
        e.nota = " · ".join(t for t in (e.nota, nota) if t)


def pr_aperte(branch: str) -> list[str] | None:
    """Gli URL delle PR aperte sul ramo, letti dal JSON di `gh pr list` e non dal
    suo testo (PBI-381, decisione 1). `None` se `gh` non ha risposto — un errore,
    un timeout, un'uscita che non è JSON — perché lì non si sa se una PR c'è."""
    try:
        code, uscita = esegui(
            ["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "url"],
            REPO, timeout=300,
        )
        if code != 0:
            print(f"    ⚠️  gh pr list non risponde: {uscita.strip()[:200]}")
            return None
        return [pr["url"] for pr in json.loads(uscita)]
    except (subprocess.TimeoutExpired, ValueError) as exc:
        print(f"    ⚠️  gh pr list non risponde: {str(exc)[:200]}")
        return None


def adotta_pr(aperte: list[str], come: str, e: Esito) -> str:
    """La PR che la ricerca ha trovato sul ramo diventa quella del giro: l'URL
    nell'esito, i commenti del Critic, e `come` nella nota. Con più di una non se
    ne sceglie nessuna, e la nota le nomina tutte (PBI-381, decisione 4)."""
    if len(aperte) > 1:
        e.nota = " · ".join(t for t in (
            e.nota, f"{len(aperte)} PR aperte sul ramo, nessuna scelta: {', '.join(aperte)}"
        ) if t)
        return ""
    e.nota = " · ".join(t for t in (e.nota, come) if t)
    # Nell'esito prima dei commenti: se da lì sale un'eccezione, la PR esiste già
    # e l'esito la deve nominare (PBI-377, decisione 5).
    e.pr = aperte[0]
    commenta_i_rapporti(e.pr, e)
    return e.pr


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
    `fatto`. Se i due sha non coincidono il giro chiude `head-non-su-origin`, e
    la nota li nomina. Se il remoto non risponde — un errore o un **timeout**,
    come in `base_del_giro()` — cosa ci sia sopra non si sa: è la stessa promessa
    non verificata, e chiude allo stesso modo, con la testa «non verificabile» e
    **senza alzare**: un'eccezione che sale a `esegui_pbi()` si scrive soltanto
    in fondo alla nota, e non produce lo stato che dice cosa c'è su `origin`.
    Un push che scade non arriva fin qui: `pubblica()` torna `False`, e la nota
    porta `NON_PUBBLICATO` con `PUSH_SCADUTO` (PBI-377, decisioni 2 e 3).
    """
    if not pubblica(branch, e):
        # L'esito resta quello che era: un push mancato non disfa il giro, ma la
        # riga del registro lo deve dire — il log da solo non lo guarda nessuno.
        e.nota = " · ".join(t for t in (e.nota, NON_PUBBLICATO) if t)
        return ""
    head = su_origin = None
    try:
        head = git("rev-parse", "HEAD")
        fuori = git("ls-remote", REMOTO, f"refs/heads/{branch}").split()
        su_origin = fuori[0] if fuori else ""
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"    ⚠️  {REMOTO} non verificabile: {str(exc)[:200]}")
    if su_origin is None or su_origin != head:
        visto = ("non verificabile" if su_origin is None
                 else su_origin or "assente")
        visti = (f"su {REMOTO} {branch} è {visto}, "
                 f"i gate hanno misurato HEAD {head or 'illeggibile'}")
        print(f"    ⚠️  PR non aperta: {visti}")
        # La diagnosi di `head-non-su-origin` **prende il posto** di quella del
        # giro chiuso, non le si mette davanti (PBI-380, decisione 1): si toglie
        # la testa «<motivo>: <testo>», e resta il suo dettaglio — l'avviso della
        # base — con ciò che il giro aveva dichiarato di sé, una volta.
        resto = e.nota
        if e.motivo in USCITE:
            prima = f"{e.motivo}: {USCITE[e.motivo][1]}"
            if resto.startswith(prima):
                resto = resto.removeprefix(prima).removeprefix(" — ").removeprefix(" · ")
        e.stato, diagnosi = uscita("head-non-su-origin", visti)
        e.motivo = "head-non-su-origin"
        e.nota = " · ".join(t for t in (diagnosi, resto) if t)
        return ""
    # Prima di creare si cerca: una PR nata da un giro precedente, o da un
    # `gh pr create` morto dopo averla aperta, non ne deve far nascere un'altra
    # (PBI-381, decisione 1).
    aperte = pr_aperte(branch)
    if aperte is None:
        # Senza una risposta non si crea: sarebbe il doppione che la ricerca
        # toglie, la stessa regola di `crea_branch()` con `OriginMuto`.
        e.nota = " · ".join(
            t for t in (e.nota, "PR non aperta: GitHub non ha risposto alla ricerca") if t)
        return ""
    if aperte:
        return adotta_pr(aperte, "PR già aperta sul ramo", e)
    corpo = (
        f"Esecuzione automatica di `{pbi_path.relative_to(REPO)}` "
        f"(`tools/asdlc/runner.py`).\n\n"
        + (f"Gate deterministici verdi · **Review Gate saltato** (`--senza-critic`): "
           f"di questo lavoro non esiste una lettura avversariale, e la revisione è "
           f"tutta qui.\n"
           if e.critic_saltato else
           f"Gate deterministici verdi · revisione avversariale del diff PASS.\n")
        + f"Tempo macchina: **{hms(e.durata_s)}** "
        f"(agente {hms(e.tempi['builder'] + e.tempi['critic'])}, gate {hms(e.tempi['gate'])}).\n\n"
        f"Manca l'unica cosa che uno script non può dare: **l'accettazione umana**.\n"
        f"Prima del merge, guarda: i criteri di verifica del PBI, il diff fuori scope, "
        f"e se la spec è stata aggiornata dove il comportamento è cambiato."
    )
    try:
        code, out = esegui(
            ["gh", "pr", "create",
             "--title", f"{pbi}: {pbi_path.stem.split('-', 2)[-1].replace('-', ' ')}",
             "--body", corpo, "--base", RAMO_PRINCIPALE, "--head", branch],
            REPO, timeout=300,
        )
    except subprocess.TimeoutExpired:
        print("    ⚠️  gh pr create scaduto: cerco la PR sul ramo")
        come = "PR ritrovata dopo timeout"
    else:
        if code != 0:
            print(f"    ⚠️  PR non aperta: {out.strip()[:200]}")
            return ""
        come = ""
    # L'URL della PR creata lo dice il JSON di `gh pr list`: `gh pr create` non
    # ha `--json`, e nella sua uscita stdout e stderr sono mescolati — un avviso
    # che cita un'altra PR ha la stessa forma (PBI-376, decisione 1). Se il
    # client è morto la PR può essere nata lo stesso su GitHub: la ricerca è una
    # sola in tutti e due i casi (PBI-381, decisione 2), e l'uscita del create
    # non si legge nemmeno quando la ricerca non trova niente.
    if ritrovate := pr_aperte(branch):
        return adotta_pr(ritrovate, come, e)
    # Se non si trova, o `gh` tace, la colonna resta vuota — una colonna che
    # mente costa più di una che tace — e la nota lo dice: la riga del tick
    # risolve.
    e.nota = " · ".join(t for t in (e.nota, "PR forse aperta, da verificare") if t)
    return ""


class ChiusuraFallita(RuntimeError):
    """`chiudi()` ha alzato: sale alla rete di `main()` con il motivo che stava
    chiudendo, e il messaggio dice perché (PBI-375, decisione 3)."""

    def __init__(self, motivo: str, dettaglio: str, guasto: BaseException):
        super().__init__(f"chiusura del giro fallita ({motivo}): {type(guasto).__name__}: "
                         f"{guasto} (il giro chiudeva: {dettaglio})"[:300])
        self.motivo = motivo


class OriginMuto(RuntimeError):
    """`origin` non ha risposto alla domanda sui rami già presi: il nome del
    branch non si può scegliere (difetto 52 di PBI-102)."""


def crea_branch(pbi: str, base: str) -> str:
    """Il branch del PBI, sempre dalla base del giro: lo sha che `base_del_giro`
    ha preso da `origin/main` appena aggiornato.

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

    Qui non si fa un altro `fetch`: con due, un merge fra l'uno e l'altro faceva
    leggere il PBI su un commit e nascere il ramo da un altro (PBI-374).

    Se `origin` non risponde alla domanda sui nomi presi si alza `OriginMuto`:
    la domanda è sul presente, e senza risposta non si sa. Non si inventa un
    nome e non si ripiega sui rami locali, che sarebbe scegliere una fonte in
    silenzio (PBI-374, decisione 7).
    """
    try:
        su_origin = rami_su_origin(pbi)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        raise OriginMuto(f"{REMOTO} non ha risposto a ls-remote, e senza risposta non si "
                         f"sa se il nome del ramo è libero: ramo non creato "
                         f"({str(exc)[:120]})") from exc
    branch = nome_libero(pbi, su_origin | rami_locali(pbi))
    git("switch", "-c", branch, base)
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


def inventario() -> dict:
    """Ciò che sta intorno al giro, in tre voci (PBI-363, decisione 7).

    - `rami`: i `pbi/pbi-*` locali e quelli su `origin`, chiesti con `ls-remote` e
      non al tracking, che resta indietro;
    - `alberi`: i percorsi di `git worktree list`, compresi gli usa e getta
      `ada-rosso-*` di un gate;
    - `file`: ciò che `git status --ignored` elenca — i non tracciati, gli ignorati
      e i tracciati modificati — contato per cartella.

    Il giro lo fa all'inizio e alla fine, e non tocca niente di ciò che trova.
    Osserva e non decide (`ADR-0008`): una voce che `git` non sa dire diventa
    `{"errore": …}`, e le altre si leggono lo stesso. Anche quando `git` scade:
    `ls-remote` va in rete, e `esegui` lascia salire `TimeoutExpired`. Alla fine
    del giro l'inventario sta prima di `pubblica`, e un'eccezione qui lasciava il
    ramo fuori da `origin` (difetti 8 e 37 di PBI-102).
    """
    voci = {"rami": rami_dell_inventario, "alberi": alberi_dell_inventario,
            "file": file_dell_inventario}
    fotografia: dict = {}
    for voce, leggi in voci.items():
        try:
            fotografia[voce] = leggi()
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            fotografia[voce] = {"errore": str(exc)[:300]}
    return fotografia


def rami_dell_inventario() -> dict[str, list[str]]:
    prefisso = f"{CFG.git.prefisso_ramo}*"
    locali = git("branch", "--list", prefisso, "--format=%(refname:short)")
    remoti = git("ls-remote", "--heads", REMOTO, prefisso)
    return {"locali": sorted(r.strip() for r in locali.splitlines() if r.strip()),
            "origin": sorted(r.split("refs/heads/")[-1].strip()
                             for r in remoti.splitlines() if "refs/heads/" in r)}


def alberi_dell_inventario() -> list[str]:
    return [r.removeprefix("worktree ").strip()
            for r in git("worktree", "list", "--porcelain").splitlines()
            if r.startswith("worktree ")]


def file_dell_inventario() -> dict[str, int]:
    """Ciò che `git status --ignored` elenca — i non tracciati, gli ignorati e i
    tracciati modificati — contato per cartella di primo livello; `.` è la radice."""
    file: Counter[str] = Counter()
    for riga in git("status", "--ignored", "--porcelain").splitlines():
        percorso = riga[3:].strip()
        if percorso:
            file[percorso.split("/")[0] if "/" in percorso else "."] += 1
    return dict(sorted(file.items()))


def residui(fotografia: dict, pbi: str) -> list[str]:
    """Ciò che l'inventario d'inizio trova dei giri prima (PBI-363, decisione 7):
    gli alberi usa e getta `ada-rosso-*`, i rami di questo PBI, locali o su
    `origin`, e le cartelle con file ignorati o non tracciati fuori dal registro.
    Si nominano e non si toccano: non sono del giro."""
    voci: list[str] = []
    alberi = fotografia.get("alberi")
    if isinstance(alberi, list):
        voci += [f"albero {a}" for a in alberi if "ada-rosso-" in a]
    ramo = ramo_del_pbi(pbi)
    for dove, rami in fotografia.get("rami", {}).items():
        if isinstance(rami, list):
            voci += [f"ramo {r} ({dove})" for r in rami
                     if r == ramo or r.startswith(f"{ramo}-")]
    file = fotografia.get("file", {})
    if "errore" not in file:
        voci += [f"file {c} ({n})" for c, n in file.items() if c != CFG.registro.cartella]
    return voci


def lasciato(inizio: dict, fine: dict, ramo: str) -> list[str]:
    """Ciò che l'inventario di fine ha in più di quello d'inizio, una voce per
    cosa: `albero …`, `ramo …`, `file <cartella> +n` (PBI-363, decisione 8). Una
    voce che una delle due fotografie non ha saputo leggere non si confronta.

    Resta fuori ciò che il giro lascia per contratto: il suo `ramo`, locale e su
    `origin`, e i suoi file nella cartella del registro — rapporto, log, prompt.
    Segnalati in ogni nota, renderebbero la nota rumore."""
    voci: list[str] = []
    prima, dopo = inizio.get("alberi"), fine.get("alberi")
    if isinstance(prima, list) and isinstance(dopo, list):
        voci += [f"albero {a}" for a in dopo if a not in prima]
    prima, dopo = inizio.get("rami", {}), fine.get("rami", {})
    for dove in ("locali", "origin"):
        if isinstance(prima.get(dove), list) and isinstance(dopo.get(dove), list):
            voci += [f"ramo {r} ({dove})" for r in dopo[dove]
                     if r not in prima[dove] and r != ramo]
    prima, dopo = inizio.get("file", {}), fine.get("file", {})
    if "errore" not in prima and "errore" not in dopo:
        voci += [f"file {c} +{n - prima.get(c, 0)}" for c, n in dopo.items()
                 if n > prima.get(c, 0) and c != CFG.registro.cartella]
    return voci


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


def ramo_diverso_da_head(branch: str) -> tuple[str, str] | None:
    """`(ref, head)` se `refs/heads/<branch>` non è `HEAD`, `None` se coincidono.

    Ciò che si sta per misurare o mandare deve essere ciò che il ramo dice
    (PBI-374, decisioni 4 e 5). Su PBI-358 il pre-flight rieseguito a giro
    partito ha staccato `HEAD` dal ramo, e i due sono andati ognuno per conto
    suo per ventiquattro commit (difetto 30)."""
    head = git("rev-parse", "HEAD")
    ref = git("rev-parse", f"refs/heads/{branch}")
    return None if ref == head else (ref, head)


# Ciò che la nota del giro dice quando `pubblica()` torna False: stato e commit
# restano quelli che erano, e questa è la riga che lo fa sapere al registro.
NON_PUBBLICATO = "branch non pubblicato: i commit restano nel worktree"
# E quando il push è scaduto invece di fallire, questa le va accanto (PBI-377).
PUSH_SCADUTO = "push in timeout, stato di origin da verificare"


def testa_su_origin(branch: str) -> str:
    """Lo sha di `refs/heads/<branch>` su `origin`, chiesto al remoto con
    `ls-remote`; `""` se non c'è o se il remoto non risponde. Non alza: la
    chiama `pubblica()`, che non alza mai (PBI-385, decisione 1)."""
    try:
        fuori = git("ls-remote", REMOTO, f"refs/heads/{branch}").split()
    except (RuntimeError, subprocess.TimeoutExpired):
        return ""
    return fuori[0] if fuori else ""


def pubblica(branch: str, e: Esito | None = None) -> bool:
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
    restano nel worktree. Un push che **scade** torna `False` allo stesso modo,
    e nella nota di `e` lascia in più `PUSH_SCADUTO`: su `origin` il ramo può
    esserci arrivato lo stesso (PBI-377, decisione 2).

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
    si dichiara invece di far sembrare fallita la pubblicazione.

    La divergenza si scrive anche nella nota di `e`, non solo a schermo (PBI-374,
    decisione 5): dopo la verifica prima dei gate può capitare solo se il ref si
    è mosso dopo l'ultimo gate, e deve lasciare traccia nel registro.

    Dopo un push riuscito `e.testa` prende lo sha che `origin` ha davvero sul
    ramo (`testa_su_origin()`): è la testa che `asdlc-chiudi-giro` legge dal
    rapporto (PBI-385, decisione 1).
    """
    try:
        diversi = ramo_diverso_da_head(branch)
        if diversi is None:
            git("push", "--force-with-lease", "-u", REMOTO, branch)
        else:
            git("push", "--force-with-lease", "-u", REMOTO, f"HEAD:refs/heads/{branch}")
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"    ⚠️  branch non pubblicato: {str(exc)[:200]}")
        print(f"       i commit restano in locale su {branch}: `git push` a mano quando "
              f"hai guardato cosa c'è sul remoto.")
        # Un push fallito dice «su origin non c'è»; uno scaduto dice «non si sa»:
        # il push è atomico per ref, e il remoto può averlo ricevuto anche se il
        # client è morto. Chi legge la nota deve guardare prima di rifarlo.
        if isinstance(exc, subprocess.TimeoutExpired) and e is not None:
            e.nota = " · ".join(t for t in (e.nota, PUSH_SCADUTO) if t)
        return False
    if e is not None:
        e.testa = testa_su_origin(branch)
    if diversi is None:
        return True
    etichetta, head = diversi
    nota = f"pubblicato HEAD {head} al posto del ramo {branch}, che era {etichetta}"
    try:
        git("branch", "-f", branch, "HEAD")
        nota += ": ref riallineato"
    except RuntimeError as exc:
        print(f"    ⚠️  HEAD pubblicato, ma il ref locale {branch} è rimasto indietro a "
              f"{etichetta[:12]}: {str(exc)[:200]}")
        nota += ": il ref locale è rimasto indietro"
    print(f"    ⚠️  {nota}")
    if e is not None:
        e.nota = " · ".join(t for t in (e.nota, nota) if t)
    return True


def base_del_giro() -> tuple[str, str]:
    """Lo sha da cui discende tutto il giro, e l'avviso se il `fetch` non ha
    risposto (PBI-374, decisioni 1 e 3).

    Un `fetch`, poi `rev-parse` di `BASE`: una volta, all'inizio del giro. Prima
    la base era un nome che ogni funzione risolveva per conto suo, e fra un
    `fetch` e l'altro un merge faceva leggere il PBI su un commit e nascere il
    ramo da un altro — la causa `due-fonti` di otto difetti di PBI-102.

    Se il remoto non risponde si prende lo sha dell'`origin/main` che si ha, e lo
    si dice: un fetch che non parte non è una ragione per non fare un PBI che si
    ha già in casa. L'avviso lo stampa questa funzione, e il giro lo scrive nella
    nota."""
    avviso = ""
    try:
        git("fetch", REMOTO, RAMO_PRINCIPALE)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        avviso = (f"fetch di {BASE} non riuscito, il giro parte dal {BASE} che c'era "
                  f"({str(exc)[:120]})")
        print(f"    ⚠️  {avviso}")
    return git("rev-parse", BASE), avviso


def trova_pbi(pbi: str, base: str) -> Path | None:
    """Il file del PBI come lo vede la base del giro, non come lo vede il worktree.

    Il runner gira in `ada-run`, un albero che resta fermo al commit su cui
    qualcuno l'ha messo l'ultima volta. Il branch invece nasce **sempre** dalla
    base (`crea_branch`): un PBI mergiato dopo quell'ultimo `switch` c'è
    dove il lavoro si farà e non c'è dove lo si cercava. Il giro chiudeva
    «saltato (PBI inesistente)» — venti secondi, nessun commit, e il file sotto
    il naso. Difetto 7 di PBI-102, ricaduto due volte.

    Si cerca sullo **stesso sha** da cui il ramo nascerà, e non nell'albero
    estratto nemmeno quando il `fetch` non ha risposto: sarebbero di nuovo due
    fonti (PBI-374, decisione 3).
    """
    numero = CFG.backlog.numero(pbi)
    if numero is None:
        return None  # non è un id di questo progetto: `[backlog].id` dice la forma
    forma = CFG.backlog.glob_del_file(numero)
    voci = git("ls-tree", "--name-only", base, f"{BACKLOG}/").splitlines()

    nome = next((v.strip() for v in voci if fnmatch(Path(v.strip()).name, forma)), None)
    return REPO / nome if nome else None


@dataclass
class Rilievo:
    """Un difetto del PBI che la pre-verifica trova prima del giro (PBI-520). I
    rilievi di forma hanno `domanda = "forma"` e nessun criterio."""
    domanda: str
    criterio: int | None
    testo: str
    evidenza: str = ""
    # `senza esito` per un rilievo di una lettura che non ha chiamato `letto`
    # (PBI-521, decisione 2); negli altri il campo non va nel rapporto.
    lettore: str | None = None


def voce_del_rilievo(r: Rilievo) -> dict:
    """Il rilievo come va nel rapporto: `lettore` solo quando c'è."""
    return {k: v for k, v in vars(r).items() if k != "lettore" or v is not None}


RE_CRITERIO = re.compile(r"^\s*- \[[ x]\]")


def sezione_della_verifica(testo: str) -> str | None:
    """Il corpo della `## Verifica`, fino alla `## ` successiva; `None` se manca."""
    verifica = re.search(r"^## Verifica\b[^\n]*(.*?)(?=^## |\Z)", testo, re.S | re.M)
    return verifica.group(1) if verifica else None


def criteri_del_pbi(testo: str) -> list[str]:
    """I testi dei criteri della `## Verifica`, ognuno con le sue righe rientrate
    (PBI-520, decisione 3). Una riga non vuota col rientro del criterio, o meno,
    lo chiude."""
    criteri: list[list[str]] = []
    aperto, rientro = False, 0
    for riga in (sezione_della_verifica(testo) or "").splitlines():
        if RE_CRITERIO.match(riga):
            criteri.append([riga])
            aperto, rientro = True, len(riga) - len(riga.lstrip())
        elif aperto and (not riga.strip() or len(riga) - len(riga.lstrip()) > rientro):
            criteri[-1].append(riga)
        elif riga.strip():
            aperto = False
    return ["\n".join(c).strip() for c in criteri]


def forma_del_pbi(testo: str, pbi: str) -> list[Rilievo]:
    """I rilievi di forma, senza git (PBI-520, decisione 2): la `Verifica` che
    manca o non ha criteri, lo **Scope** che manca o non nomina il file del PBI."""
    rilievi: list[Rilievo] = []
    if sezione_della_verifica(testo) is None:
        rilievi.append(Rilievo("forma", None, "manca la sezione `## Verifica`"))
    elif not criteri_del_pbi(testo):
        rilievi.append(Rilievo("forma", None, "la `## Verifica` non ha criteri `- [ ]`"))
    scope = blocco_dello_scope(testo)
    if scope is None:
        rilievi.append(Rilievo("forma", None, "manca il blocco **Scope**"))
    elif not re.search(rf"{re.escape(BACKLOG)}/{re.escape(pbi)}(?!\d)", scope):
        rilievi.append(Rilievo("forma", None,
                               f"lo **Scope** non nomina `{BACKLOG}/{pbi}`, il file del PBI"))
    return rilievi


def percorsi_dello_scope(testo: str) -> list[tuple[str, str]]:
    """I percorsi fra apici inversi dello Scope, con la loro riga: quelli con una
    `/` e senza spazi, `*`, `<`, `>`, `{`, `}` né `…` (PBI-520, decisione 5)."""
    return [(percorso, riga)
            for riga in (blocco_dello_scope(testo) or "").splitlines()
            for percorso in re.findall(r"`([^`]+)`", riga)
            if "/" in percorso and not set(percorso) & set(" *<>{}…")]


def avvisi_della_base(testo: str, pbi: str, base: str) -> list[str]:
    """Gli avvisi della pre-verifica, letti alla `base` (PBI-520, decisione 5):
    non fermano niente, li legge il Lettore. Un percorso dello Scope che alla base
    non c'è e la cui riga non lo dice nuovo, una dipendenza di `Bloccato da:` che
    alla base non c'è o ha un `- [ ]` nella sua Verifica, uno Scope di soli test."""
    avvisi: list[str] = []
    percorsi = percorsi_dello_scope(testo)
    for percorso, riga in percorsi:
        if "nuov" in riga:
            continue
        code, _ = esegui(["git", "cat-file", "-e", f"{base}:{percorso.rstrip('/')}"], REPO,
                         timeout=120)
        if code != 0:
            avvisi.append(f"lo Scope nomina `{percorso}`, che alla base non c'è e non è detto nuovo")
    for riga in re.findall(r"^.*Bloccato da:.*$", testo, re.M):
        for dipendenza in dict.fromkeys(re.findall(r"PBI-\d+", riga)):
            file = trova_pbi(dipendenza, base)
            if file is None:
                avvisi.append(f"la dipendenza {dipendenza} alla base non c'è")
                continue
            sorgente = git("show", f"{base}:{file.relative_to(REPO).as_posix()}")
            if any(c.startswith("- [ ]") for c in criteri_del_pbi(sorgente)):
                avvisi.append(f"la dipendenza {dipendenza} ha un criterio non spuntato")
    pbi_stesso = re.compile(rf"{re.escape(BACKLOG)}/{re.escape(pbi)}(?!\d)")
    altri = [p for p, _ in percorsi if not pbi_stesso.match(p) and not p.endswith("/")]
    if altri and all(e_file_di_test(p) for p in altri):
        avvisi.append("lo Scope nomina solo file di test")
    return avvisi


def esegui_le_sonde(albero: Path,
                    sonde: list[dict]) -> tuple[list[dict], list[Rilievo], list[str]]:
    """Esegue le sonde del Lettore nell'albero alla base, con gli strumenti di
    `--chiedi-impl` (`PBI-521`, decisione 4): ogni sonda col suo esito, e un rilievo `R`
    col testo di `ESITI_MANCATI` per ogni sonda che non è rossa.

    Una sonda su un file che non è un test non si esegue, e il suo esito è `nessuno`: il
    server non lo può sapere, perché non importa il runner. Un orfano di
    `comandi_dei_test()`, il test che non si isola, torna alla sua sonda dal file: la sua
    etichetta comincia col percorso da cui il test gira (per JUnit è il nome).

    Un `GuastoDelGate` dice che lo strumento non ha guardato, non che il criterio nasce
    verde: le sonde di quel comando hanno esito `guasto`, nessun rilievo, e un avviso
    `sonda del criterio N: gate guasto`, che torna al terzo posto."""
    nuovi = [TestNuovo(s["file"], s["nome"], linguaggio_del_test(s["file"])) for s in sonde]
    esiti: dict[TestNuovo, str] = {t: "nessuno" for t in nuovi if t.linguaggio is None}
    eseguibili = [t for t in nuovi if t.linguaggio is not None]
    comandi, orfani = comandi_dei_test(albero, eseguibili)
    for etichetta in orfani:
        for test in eseguibili:
            if etichetta.startswith(f"{dove_gira(test.file)[1]} ") or etichetta == test.nome:
                esiti[test] = "nessuno"
    for comando in comandi:
        try:
            letti, _ = esiti_del_comando(comando)
        except GuastoDelGate:
            letti = {chiave: "guasto" for chiave in comando.origine}
        for chiave, esito in letti.items():
            esiti[comando.origine[chiave]] = esito
    eseguite: list[dict] = []
    rilievi: list[Rilievo] = []
    avvisi: list[str] = []
    for sonda, test in zip(sonde, nuovi):
        esito = esiti[test]
        eseguite.append({"criterio": sonda["criterio"], "file": sonda["file"],
                         "nome": sonda["nome"], "esito": esito})
        if esito == "guasto":
            avvisi.append(f"sonda del criterio {sonda['criterio']}: gate guasto")
        elif esito != "rosso":
            rilievi.append(Rilievo("R", sonda["criterio"], ESITI_MANCATI[esito],
                                   f"{sonda['file']}::{sonda['nome']}"))
    return eseguite, rilievi, avvisi


RE_GUARDIA = re.compile(r"guardia|nato\s+verde", re.IGNORECASE)


def criteri_senza_sonda(testo: str, sonde: list[dict]) -> list[str]:
    """Un avviso per ogni criterio della `Verifica` che non ha una sonda (PBI-521,
    decisione 5): non è un rilievo, perché il rosso di quel criterio non è stato
    provato, non smentito. Un criterio guardia non ha sonda, e non ha l'avviso: è
    guardia se il suo testo intero, righe rientrate comprese, dice «guardia» o «nato
    verde», senza distinguere maiuscole e minuscole."""
    provati = {s["criterio"] for s in sonde}
    return [f"criterio {numero} senza sonda"
            for numero, criterio in enumerate(criteri_del_pbi(testo), start=1)
            if numero not in provati and not RE_GUARDIA.search(criterio)]


def rilievi_senza_esito(file_esito: Path) -> list[Rilievo]:
    """I rilievi che il server ha accumulato in `<esito>.lettura.jsonl` per una lettura
    che non ha chiamato `letto`, marcati `senza esito` (PBI-521, decisione 2)."""
    try:
        righe = Path(f"{file_esito}.lettura.jsonl").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    voci = [json.loads(r) for r in righe if r.strip()]
    return [Rilievo(v["domanda"], v["criterio"], v["testo"], v["evidenza"],
                    lettore="senza esito") for v in voci if v.get("strumento") == "rilievo"]


def lettura_del_lettore(percorso: str, base: str,
                        avvisi: list[str]) -> tuple[str, list[Rilievo], list[dict], list[str]]:
    """Il Lettore sul PBI `percorso` (`PBI-521`, `ADR-0031` decisioni 1-3): lo lancia in un
    albero usa e getta alla `base`, che è il suo `cwd` e si smonta comunque vada, e dopo
    `letto` ne esegue le sonde lì dentro. Torna lo stato della lettura, i rilievi del
    Lettore e delle sonde, le sonde col loro esito e gli avvisi dei gate guasti. Senza `letto` la lettura è
    `senza esito`: i rilievi accumulati entrano lo stesso, le sonde non si eseguono."""
    prompt, file_esito = file_dell_invocazione("lettore")
    prompt.write_text(prompt_del_pacchetto("lettore").format(
        pbi_path=percorso, avvisi="\n".join(f"- {a}" for a in avvisi) or "- nessuno"),
        encoding="utf-8")
    with worktree_usa_e_getta(base) as albero:
        invocazione = invoca_agente("lettore", comando_del_lettore(), prompt, file_esito,
                                    cwd=albero)
        dichiarato = invocazione.dichiarato
        if dichiarato is None:
            return "senza esito", rilievi_senza_esito(file_esito), [], []
        rilievi = [Rilievo(**r) for r in dichiarato["rilievi"]]
        sonde, dalle_sonde, guasti = esegui_le_sonde(albero, dichiarato["sonde"])
    return "letto", rilievi + dalle_sonde, sonde, guasti


def scrivi_la_preverifica(pbi: str, base: str, percorso: str, run: str,
                          lettore: bool) -> tuple[Path, dict, list[Rilievo]]:
    """Legge il PBI `percorso` alla `base` e scrive `LOG_DIR/<run>-<PBI>-preverifica.json`
    (PBI-520, decisioni 1, 7 e 8): rende il rapporto, il suo contenuto e i rilievi. La
    usano `--preverifica` e il giro (PBI-522). Il rapporto non ha `esiti`, e i lettori
    dei rapporti lo ignorano.

    Con `lettore` (PBI-521) legge anche il Lettore e ne esegue le sonde: i suoi rilievi e
    quelli delle sonde vanno nella stessa lista, e il rapporto dice in `lettore` come è
    finita la lettura (`null` senza Lettore) e in `sonde` gli esiti."""
    testo = git("show", f"{base}:{percorso}")
    rilievi = forma_del_pbi(testo, pbi)
    avvisi = avvisi_della_base(testo, pbi, base)
    stato_della_lettura: str | None = None
    sonde: list[dict] = []
    if lettore:
        stato_della_lettura, dal_lettore, sonde, guasti = lettura_del_lettore(percorso, base,
                                                                             avvisi)
        rilievi += dal_lettore
        avvisi += guasti + criteri_senza_sonda(testo, sonde)
    LOG_DIR.mkdir(exist_ok=True)
    rapporto = LOG_DIR / f"{run}-{pbi}-preverifica.json"
    contenuto = {
        "pbi": pbi,
        "base": base,
        "sha_pbi": git("rev-parse", f"{base}:{percorso}"),
        "criteri": len(criteri_del_pbi(testo)),
        "rilievi": [voce_del_rilievo(r) for r in rilievi],
        "avvisi": avvisi,
        "lettore": stato_della_lettura,
        "sonde": sonde,
    }
    rapporto.write_text(json.dumps(contenuto, ensure_ascii=False, indent=2), encoding="utf-8")
    return rapporto, contenuto, rilievi


def preverifica(pbi: str, lettore: bool = False) -> int:
    """`asdlc-runner PBI-N --preverifica` (PBI-520, decisioni 1, 7 e 8): legge il PBI
    alla base del giro e scrive `LOG_DIR/<run>-<PBI>-preverifica.json`. Esce 1 se c'è
    un rilievo, 0 altrimenti: gli avvisi non contano. Non crea rami né commit e non
    cambia la fase.

    Con `lettore` (`--lettore`, PBI-521) legge anche il Lettore e ne esegue le sonde.
    Una lettura `senza esito` esce 1 anche senza rilievi."""
    base, _ = base_del_giro()
    file = trova_pbi(pbi, base)
    if file is None:
        print(f"{pbi}: alla base {base[:10]} non c'è il file del PBI.")
        return 2
    run = datetime.now().strftime("%Y%m%d-%H%M%S")
    rapporto, contenuto, rilievi = scrivi_la_preverifica(
        pbi, base, file.relative_to(REPO).as_posix(), run, lettore)
    sonde, avvisi = contenuto["sonde"], contenuto["avvisi"]
    stato_della_lettura = contenuto["lettore"]
    for s in sonde:
        print(f"  sonda del criterio {s['criterio']}: {s['file']}::{s['nome']} → {s['esito']}")
    for r in rilievi:
        print(f"  rilievo ({r.domanda}): {r.testo}")
    for a in avvisi:
        print(f"  avviso: {a}")
    if stato_della_lettura == "senza esito":
        print("  il Lettore non ha chiamato letto: la lettura è senza esito")
    print(f"{pbi}: {len(rilievi)} rilievi, {len(avvisi)} avvisi. Rapporto: {rapporto}")
    return 1 if rilievi or stato_della_lettura == "senza esito" else 0


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
    run: str = "", riprendi: bool = False,
) -> Esito:
    run = run or datetime.now().strftime("%Y%m%d-%H%M%S")
    # La base del giro, una volta: da qui in poi nessuno fa più `fetch`, e ogni
    # lettura nomina questo sha e non `BASE` (PBI-374).
    base, avviso = base_del_giro()

    def motiva(e: Esito, motivo: str, dettaglio: str = "") -> Esito:
        """Il motivo nell'esito, con lo stato che `USCITE` gli dà e la sua nota
        davanti a ciò che il giro aveva già dichiarato di sé.

        L'avviso della base entra qui, nel dettaglio, e non nella nota d'inizio
        del giro: così lo porta anche un'uscita che arriva prima che il giro
        esista (PBI-375, decisione 6)."""
        dettaglio = " · ".join(t for t in (dettaglio, avviso) if t)
        e.stato, diagnosi = uscita(motivo, dettaglio)
        e.motivo = motivo
        e.nota = " · ".join(t for t in (diagnosi, e.nota) if t)
        return e

    pbi_path = trova_pbi(pbi, base)
    if pbi_path is None:
        return motiva(Esito(pbi, "", base=base), "pbi-inesistente",
                      f"in {BACKLOG}/ su {BASE} ({base[:12]})")

    print(f"\n=== {pbi} — {pbi_path.name}")
    prompt = PROMPT_BUILDER.format(pbi_path=pbi_path.relative_to(REPO))
    if riprendi:
        prompt += PROMPT_RIPRENDI
    if dry:
        print(prompt)
        return motiva(Esito(pbi, ""), "dry-run")

    if git("status", "--porcelain"):
        return motiva(Esito(pbi, ""), "albero-sporco-all-ingresso")

    # Il controllo guarda **tutto** l'albero, senza eccezioni. `runs/` è stato
    # escluso finché il runner scriveva `runs/tempi.csv` a fine invocazione: da
    # quando quel file è versionato, ogni giro rendeva sporco il successivo, e
    # l'eccezione era la toppa. `ADR-0020` ha tolto la causa — il registro esce
    # dai branch — quindi torna a valere la regola intera: ciò che non è
    # committato non esiste, e non si parte sopra al lavoro di qualcun altro.

    # La pre-verifica (PBI-522, `ADR-0031` decisione 4): prima dell'inventario e del
    # ramo, sul PBI alla base, col Lettore se `[preverifica].lettore` lo chiede. Con un
    # rilievo il giro chiude qui, senza ramo, commit, PR né Solver: il rimedio è
    # correggere il PBI. Una ripresa non la rifà: il PBI è già passato da qui, e il suo
    # ramo c'è già.
    if CFG.preverifica.attiva and not riprendi:
        rapporto, letto, rilievi = scrivi_la_preverifica(
            pbi, base, pbi_path.relative_to(REPO).as_posix(), run,
            lettore=CFG.preverifica.lettore)
        if rilievi:
            return motiva(Esito(pbi, "", base=base, sha_pbi=letto["sha_pbi"],
                                rilievi_preverifica=len(rilievi)),
                          "preverifica", f"rilievi: {len(rilievi)}, nel rapporto {rapporto}")

    e = Esito(pbi, "rosso", iniziato=datetime.now().isoformat(timespec="seconds"),
              base=base)
    t0 = time.monotonic()
    # Prima del ramo: un ramo di questo PBI lasciato da un giro prima è un residuo
    # da nominare, e dopo `crea_branch` non si distinguerebbe dal nostro.
    e.inventario["inizio"] = inventario()
    contati = Counter(USA_E_GETTA)
    # Solo nel log, non nella nota: fra i file ignorati ci sono sempre il venv e
    # `node_modules`, e in `runs/tempi.csv` sarebbero rumore a ogni riga.
    if trovati := residui(e.inventario["inizio"], pbi):
        print(f"    residui dei giri prima (non li tocco): {', '.join(trovati)}")
    # Il ramo nasce dopo `chiudi()`, perché anche un ramo che non nasce passi da
    # lì (difetto 52): finché è `None` non c'è niente da pubblicare.
    branch: str | None = None

    def conta_commit() -> int:
        """`<base>..HEAD` — lo sha da cui il ramo è nato — e non `main..HEAD`: da
        quando il main locale del worktree non si estrae più, resta indietro di
        giorni e conterebbe come commit del PBI tutto ciò che main ha ricevuto nel
        frattempo. E non `origin/main..HEAD`, che si sposta a ogni `fetch` di
        chiunque nel repository (PBI-374)."""
        try:
            return int(git("rev-list", "--count", f"{base}..HEAD") or 0)
        except (RuntimeError, ValueError):
            return e.commit  # un conteggio mancato non cancella quello di prima

    def dichiara(testo: str) -> None:
        """Una cosa che il giro dice di sé nella nota — un gate in meno — e che
        deve restare leggibile in `runs/tempi.csv` qualunque sia l'esito."""
        e.nota = " · ".join(t for t in (e.nota, testo) if t)

    def chiudi(motivo: str, dettaglio: str = "") -> Esito:
        # Il conteggio sta **qui** e non dopo il giro dei gate: ogni uscita
        # anticipata — il `fermati` del Builder, l'albero che resta sporco — scriveva
        # `commit = 0` mentre sul branch c'era il lavoro. Su PBI-209 erano otto
        # commit e 2.174 righe, e la colonna del registro diceva zero: è quella
        # che si guarda per decidere se un branch fermato si butta (difetto 10).
        chiudi_la_fase()
        e.commit = conta_commit()
        e.inventario["fine"] = inventario()
        e.inventario["usa_e_getta"] = conto = {k: USA_E_GETTA[k] - contati[k]
                                               for k in ("montati", "smontati")}
        # Contare vale anche quando la strada che lascia il residuo non si riesce a
        # riprodurre: un albero appeso che si vede nella nota non si perde in /tmp.
        resti = lasciato(e.inventario["inizio"], e.inventario["fine"], branch or "")
        if (persi := conto["montati"] - conto["smontati"]) > 0:
            resti.append(f"{persi} albero usa e getta montato e non smontato" if persi == 1
                         else f"{persi} alberi usa e getta montati e non smontati")
        if resti:
            print(f"    ⚠️  il giro lascia: {', '.join(resti)}")
            dichiara(f"il giro lascia: {', '.join(resti)}")
        e.durata_s = time.monotonic() - t0
        e.finito = datetime.now().isoformat(timespec="seconds")
        # La diagnosi davanti, e dietro ciò che il giro aveva già dichiarato di
        # sé — un gate spento, il Critic saltato: la fermata non lo cancella.
        motiva(e, motivo, dettaglio)
        # Un giro che si ferma ha comunque prodotto commit, e lasciarli solo nel
        # worktree vuol dire non farli guardare a nessuno: su PBI-320 sono rimasti
        # lì, su PBI-322 li ha salvati a mano una persona prima di chiudere il
        # terminale. Difetto 8 di PBI-102. Sulla strada buona non si pubblica qui:
        # a quello ci pensa `apri_pr`, una volta sola. E un ramo che non è nato,
        # perché `origin` non ha risposto, non ha niente da pubblicare.
        if e.stato in STATI_CHE_INTERROMPONO and branch and not pubblica(branch, e):
            dichiara(NON_PUBBLICATO)
        print(f"    tempo: {hms(e.durata_s)} "
              f"(builder {hms(e.tempi['builder'])} · gate {hms(e.tempi['gate'])} · "
              f"critic {hms(e.tempi['critic'])})")
        return e

    contatore_letto = False

    def smista(motivo: str, dettaglio: str) -> dict | None:
        """Il blocco al Solver, e l'esito che il Solver ha scritto in questa chiamata; `None`
        se non è partito (il tetto) o non ha scritto niente. Un suo guasto è un avviso
        (`ADR-0008`) e non salta `chiudi()`, che è la strada d'uscita di ogni giro fermato
        (difetto 37)."""
        nonlocal contatore_letto
        prima = len(e.solver)
        try:
            # Il contatore si legge da disco una volta per giro (PBI-517, decisione 9).
            rileggi, contatore_letto = not contatore_letto, True
            smista_il_blocco(e, pbi_path, motivo, dettaglio, dichiara, rileggi=rileggi)
        except Exception as guasto:  # noqa: BLE001 — si registra, non si tace
            traceback.print_exc()
            e.file_traceback = str(salva_il_traceback(pbi))
            dichiara(f"avviso: il Solver è fallito: {type(guasto).__name__}: {guasto}"[:300])
        return e.solver[-1] if len(e.solver) > prima else None

    def giro() -> tuple[str, str]:
        """Builder, gate e Critic. Torna il motivo d'uscita e il dettaglio, e non
        chiude: la chiusura è di chi lo chiama, una volta sola (PBI-375)."""
        nonlocal prompt
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
            # Il comando della ripresa dopo un `risolto` del Solver, per la sola invocazione
            # che segue: poi i rilanci tornano a `-c` (PBI-517, decisione 6).
            ripresa: list[str] | None = None
            while gate_falliti < MAX_TENTATIVI:
                print(f"  builder — giro {e.tentativi + igiene + 1}")
                # Scrive il prompt su file per evitare limiti di lunghezza degli argomenti CLI
                prompt_file, file_esito = file_dell_invocazione("builder")
                prompt_file.write_text(prompt, encoding="utf-8")
                cmd = ripresa or BUILDER + ([] if primo_del_giro else ["-c"])
                primo_del_giro, ripresa = False, None
                with misura(e, "builder"):
                    invocazione = invoca_agente("builder", cmd, prompt_file, file_esito)
                e.invocazioni.append(invocazione.registro)
                dichiarato = invocazione.dichiarato

                # Senza una chiamata valida il Builder non ha detto niente che si possa
                # leggere, qualunque cosa ci sia nel suo testo: si chiude qui, senza
                # igiene e senza gate. Un limite d'uso con l'albero sporco spendeva i
                # tre giri d'igiene (difetto 27); ora costa un lancio (`ADR-0027`).
                if dichiarato is None:
                    e.riprendi_dopo = riprendi_dopo_il_limite(invocazione.registro)
                    return "builder-senza-esito", nota_senza_esito(invocazione.registro,
                                                                    invocazione.uscita)
                if dichiarato["esito"] == "fermati":
                    e.domanda = dichiarato["domanda"]
                    # La domanda va al Solver qui, dentro il giro: con `risolto` il
                    # Builder riprende, con ogni altro esito il giro si ferma (PBI-517).
                    risposta = smista("domanda-del-builder", una_riga(e.domanda))
                    if risposta is None or risposta["esito"] != "risolto":
                        return "domanda-del-builder", una_riga(e.domanda)
                    e.riprese_solver += 1
                    # Domanda e risposta entrano come valori di `.format()`: le loro graffe
                    # non si interpretano (decisione 8).
                    prompt = prompt_del_pacchetto("ripresa-dopo-risolto").format(
                        domanda=e.domanda, risposta=risposta["risposta"],
                        evidenza=risposta["evidenza"])
                    if invocazione.registro.get("traccia"):
                        # La sessione del Builder che ha chiamato `fermati`, e non `-c`:
                        # l'ultima sessione dell'albero è quella del Solver. `--session-id`
                        # e `--fork-session` li aggiunge `invoca_agente()`.
                        ripresa = BUILDER + ["--resume", invocazione.registro["sessione"]]
                    else:
                        # Senza traccia la sessione non c'è, e `--resume` fallirebbe: si
                        # riparte da una sessione nuova, col PBI davanti (decisione 7).
                        ripresa = list(BUILDER)
                        prompt = (PROMPT_BUILDER.format(pbi_path=pbi_path.relative_to(REPO))
                                  + "\n\n" + prompt)
                        dichiara("avviso: la ripresa dopo risolto riparte da una sessione "
                                 "nuova, senza la traccia del Builder "
                                 f"({invocazione.registro.get('traccia_nota', '')})"[:300])
                    continue

                # Come all'ingresso, e per la stessa ragione: niente eccezioni da quando
                # il registro non si scrive più dal branch (`ADR-0020`).
                if sporco := git("status", "--porcelain"):
                    # Non committato = non esiste: niente da giudicare, niente da ripristinare.
                    # Il giro si conta fra quelli d'igiene: `e.tentativi` è la pazienza sui
                    # **gate**, e spenderla qui vorrebbe dire togliere al lavoro vero i giri
                    # che gli servivano (PBI-208, notte del 24/08).
                    igiene += 1
                    if igiene >= MAX_IGIENE:
                        return (
                            "albero-sporco-dopo-igiene",
                            f"l'albero resta sporco dopo {MAX_IGIENE} giri del Builder "
                            f"({sporco.splitlines()[0][:120]})",
                        )
                    prompt = PROMPT_IGIENE.format(sporco=sporco[:1500])
                    continue

                e.tentativi += 1
                gate_falliti += 1

                # Un gate che misura un `HEAD` diverso dal ramo misura un lavoro che il
                # ramo non contiene: non si gira, e la diagnosi è quella che `apri_pr()`
                # dà per `origin` (PBI-374, decisione 4).
                if diversi := ramo_diverso_da_head(branch):
                    ref, head = diversi
                    return "ref-diverso-da-head", f"il ramo {branch} è {ref}, HEAD è {head}"

                with misura(e, "gate"):
                    rossi = gira_gate(attivi, base)
                if not rossi:
                    verde = True
                    break
                prompt = PROMPT_RIPROVA.format(esiti="\n\n".join(f"## {n}\n{o}" for n, o in rossi))

            e.commit = conta_commit()
            if not verde:
                e.gate_rossi = [{"gate": n, "coda": o[-2000:]} for n, o in rossi]
                for g in e.gate_rossi:
                    print(f"    ── {g['gate']} ──\n{g['coda']}")
                return "gate-rossi", ""

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
                        senza_rosso = gate_del_rosso(base=base, visti=visti, morsi=morsi)
                except GuastoDelGate as guasto:
                    # Un gate rotto è un gate **rosso**, non un ciclo mancato: qui non si
                    # accusa nessun commit, perché il gate non ne ha guardato nessuno.
                    print(f"GUASTO ({hms(time.monotonic() - t_rosso)})")
                    print(f"    ── gate del rosso ──\n{guasto}")
                    return "gate-del-rosso-guasto", str(guasto)
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
                return (
                    "rosso-mai-visto",
                    f"{len(senza_rosso)} commit "
                    f"({', '.join(m['commit'] for m in senza_rosso[:5])}): elenco nel rapporto "
                    f"del giro",
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
                verdetto = revisione_critica(
                    pbi_path, gate=gate_per_il_critic(attivi, e.test_che_mordono, base),
                    base=base)
            if verdetto.registro is not None:
                e.invocazioni.append(verdetto.registro)
            rapporto = verdetto.rapporto
            file = scrivi_rapporto_critic(run, pbi, revisione, verdetto)
            e.rapporti_critic.append(
                {"revisione": revisione, "verdetto": verdetto.esito, "percorso": str(file)})
            if verdetto.esito == "pass":
                break
            if verdetto.esito == "senza esito":
                e.riprendi_dopo = riprendi_dopo_il_limite(verdetto.registro)
                return "critic-senza-esito", nota_senza_esito(verdetto.registro,
                                                              verdetto.rapporto)
            if verdetto.esito == "sospeso":
                # Non si consuma una revisione e non si richiama il Critic: la sua
                # diagnosi non cambia riprovando, perché ciò che manca non è nel
                # repository. Riprovare qui è esattamente ciò che è costato a PBI-203
                # cinque giri e 1h26m per tornare al punto di partenza.
                e.domanda = verdetto.domanda
                return "domanda-del-critic", una_riga(verdetto.domanda)
            if revisione == MAX_REVISIONI:
                # **Non convergente, non respinto.** Sono due diagnosi diverse e confonderle
                # manda a correggere la cosa sbagliata: `respinto` dice che il PBI era scritto
                # male, `non convergente` che il lavoro non si è chiuso e serve una persona.
                # Chi legge runs/tempi.csv deve poter distinguere un PBI difficile da uno mal
                # posto, altrimenti il registro misura la fatica e non la causa.
                return ("revisioni-esaurite",
                        f"{MAX_REVISIONI + 1} revisioni, i rilievi del Critic in "
                        f"{LOG_DIR / f'{run}-{pbi}-critic-*.md'}")
            # Relativo come nel primo giro: è lo stesso percorso che il Builder ha già
            # letto, e un assoluto qui lo farebbe sembrare un altro file. Il rapporto
            # va intero: tagliato, il Builder non leggeva i primi rilievi (PBI-371).
            prompt = MODELLO_RIMEDIO.format(
                base=base, rapporto=rapporto, pbi_path=pbi_path.relative_to(REPO)
            )

        # L'elenco dello Scope di ADR-0015: di un rename i due lati, come il gate
        # con `solo_se_tocca` — `--name-only` dava il solo nuovo (PBI-389).
        toccati = "\n".join(sorted(file_toccati(base)))
        print(f"    commit sul branch: {e.commit} · file: {toccati}")
        return "fatto", ""

    try:
        if riprendi:
            branch = riprendi_il_ramo(pbi)
            e.riprese_limite = riprese_limite_fatte(pbi) + 1
        else:
            branch = crea_branch(pbi, base)
        e.ramo = branch
    except OriginMuto as muto:
        print(f"    ⚠️  {muto}")
        motivo, dettaglio = "origin-muto", str(muto)
    else:
        apri_la_fase(base)
        # Il giro sta in un `try` perché ogni strada d'uscita passi da `chiudi()`:
        # un'eccezione — il timeout di un gate, un guasto dentro il gate del rosso
        # — usciva da qui, la raccoglieva la rete di `main()`, e il ramo restava
        # solo nel worktree con i commit non contati. Senza ramo su `origin` il
        # tick rilanciava lo stesso PBI (difetto 37). La rete di `main()` resta,
        # come ultima difesa e non come strada.
        try:
            motivo, dettaglio = giro()
        except Exception as exc:  # noqa: BLE001 — si cattura per chiudere, non per tacere
            traceback.print_exc()
            e.file_traceback = str(salva_il_traceback(pbi))
            motivo, dettaglio = "eccezione-nel-giro", f"{type(exc).__name__}: {exc}"[:300]

    # La chiusura sta **fuori** dal `try` del giro, e gira una volta (difetto 48):
    # quando stava dentro, un push che falliva chiudendo un `sospeso` finiva
    # nell'`except`, che richiudeva `rosso` — e la seconda chiusura, riuscita,
    # cancellava lo stato vero. Una chiusura che fallisce non si inghiotte e non
    # si riprova: sale alla rete di `main()` con il motivo che stava chiudendo.
    # Un `senza esito` per il limite d'uso con l'ora del reset leggibile non ha niente
    # da decidere: il tick aspetta il reset e riprende, e il Solver non parte
    # (PBI-519, decisione 4).
    # Il `fermati` del Builder il Solver lo ha già smistato dentro `giro()`, e una
    # seconda chiamata qui lo farebbe girare due volte (PBI-517, decisione 2). Gli
    # altri blocchi si smistano qui, una volta, e non riprendono.
    if motivo in BLOCCHI and motivo != "domanda-del-builder" and not e.riprendi_dopo:
        smista(motivo, dettaglio)
    # La guardia gira ogni volta che il Solver ha scritto, qualunque sia il motivo
    # finale: dopo una ripresa può essere `fatto` (PBI-517, decisione 3). Senza
    # Solver `guardia_del_solver()` non scrive niente.
    guardia_del_solver(e, dichiara=dichiara)
    try:
        chiudi(motivo, dettaglio)
    except Exception as guasto:  # noqa: BLE001
        raise ChiusuraFallita(motivo, dettaglio, guasto) from guasto
    if motivo != "fatto":
        return e

    # --- Acceptance Gate (umano): si apre la PR, non si mergia ---
    # Dopo `chiudi()` l'esito esiste, e un'eccezione non lo sostituisce: gli si
    # aggiunge in fondo alla nota. Usciva da qui, e la rete di `main()` scriveva
    # un `rosso` nuovo al posto del giro chiuso, con stato, commit, rapporti del
    # Critic e invocazioni persi (difetto 50). Il `try` è per l'imprevisto: i
    # guasti della pubblicazione hanno il loro stato dentro `apri_pr()`.
    if con_pr:
        try:
            e.pr = apri_pr(pbi, pbi_path, branch, e)
        except Exception as exc:  # noqa: BLE001 — si aggiunge all'esito, non si tace
            traceback.print_exc()
            e.file_traceback = str(salva_il_traceback(pbi))
            dichiara(f"dopo la chiusura: {type(exc).__name__}: {exc}"[:300])
        if e.pr:
            print(f"    PR aperta: {e.pr}")
    return e


def esiti_dei_rapporti(pbi: str) -> list[tuple[str, dict]]:
    """Gli esiti di `pbi` nei rapporti di `LOG_DIR`, ognuno col `run` del suo
    rapporto. Un file che non è un rapporto, o che non si legge, non conta."""
    trovati: list[tuple[str, dict]] = []
    for file in LOG_DIR.glob("*.json"):
        try:
            rapporto = json.loads(file.read_text(encoding="utf-8"))
            trovati += [(str(rapporto.get("run", "")), x) for x in rapporto.get("esiti", [])
                        if x.get("pbi") == pbi]
        except (OSError, ValueError, AttributeError, TypeError):
            continue
    return trovati


def riprese_limite_fatte(pbi: str) -> int:
    """Le riprese dopo il limite d'uso già contate per `pbi`: il più alto
    `riprese_limite` dei suoi esiti nei rapporti (PBI-519, decisione 8)."""
    return max([0] + [x.get("riprese_limite", 0) for _, x in esiti_dei_rapporti(pbi)])


def riprendi_il_ramo(pbi: str) -> str:
    """Il ramo dell'ultimo giro di `pbi`, estratto alla punta di `origin/<ramo>`:
    la ripresa continua su quello stesso ramo, e i commit nuovi avanzano di
    fast-forward (PBI-519, decisione 6). L'ultimo è l'esito col `run` più recente.

    `switch -C` e non `-c`: un ramo locale con quel nome, rimasto da un giro
    prima, si riallinea alla punta pubblicata invece di far fallire il giro."""
    esiti = esiti_dei_rapporti(pbi)
    ramo = max(esiti, key=lambda r: r[0])[1].get("ramo") if esiti else None
    if not ramo:
        raise RuntimeError(f"--riprendi: nessun rapporto di {pbi} in {LOG_DIR} porta il ramo")
    git("switch", "-C", ramo, f"{REMOTO}/{ramo}")
    return ramo


def giri_solver_fatti(pbi: str) -> int:
    """I giri Solver già contati per `pbi` nei rapporti di `LOG_DIR`: il più alto
    `giri_solver` che un esito di quel PBI porta. Un file che non è un rapporto, o
    che non si legge, non conta (`PBI-507`, decisione 10)."""
    fatti = 0
    for file in LOG_DIR.glob("*.json"):
        try:
            esiti = json.loads(file.read_text(encoding="utf-8")).get("esiti", [])
            fatti = max([fatti] + [x.get("giri_solver", 0) for x in esiti
                                   if x.get("pbi") == pbi])
        except (OSError, ValueError, AttributeError, TypeError):
            continue
    return fatti


RE_PBI_DEL_BACKLOG = re.compile(r"^PBI-(\d+)")
RE_RIGA_DI_CODA = re.compile(r"^- (PBI-\d+|‖)")


def passo_a_monte(cmd: list[str], cwd: Path) -> str:
    """Un passo verso `asdlc`: l'uscita, o `RuntimeError` che nomina il comando se esce ≠ 0."""
    codice, uscita = esegui(cmd, cwd, timeout=300)
    if codice != 0:
        raise RuntimeError(f"`{' '.join(cmd[:3])}` è uscito {codice}: {una_riga(uscita)[:200]}")
    return uscita.strip()


def pbi_a_monte_numerato(testo: str, numero: int, causa: str) -> tuple[str, str]:
    """Il testo del Solver col numero dato nell'intestazione e la riga `**Causa:**` (R6 la
    cerca lì), e il nome del file `PBI-NNN-<titolo>.md`. Il resto resta com'è."""
    righe = testo.strip().splitlines()
    titolo = re.sub(r"^#\s*(PBI-\d+\s*:\s*)?", "", righe[0]).strip()
    corpo = righe[1:]
    if not any(re.match(rf"\*\*Causa:\*\*\s*{re.escape(causa)}(?![\w-])", r) for r in corpo):
        corpo = ["", f"**Causa:** {causa}", *corpo]
    parole = re.sub(r"[^a-z0-9]+", "-", titolo.lower()).strip("-")[:50].strip("-")
    return "\n".join([f"# PBI-{numero}: {titolo}", *corpo]) + "\n", f"PBI-{numero}-{parole}.md"


def apri_pr_a_monte(dichiarato: dict) -> tuple[str, str]:
    """Apre il PBI a monte (`PBI-512`, R5): un ramo sul fork di `asdlc` e una PR da lì verso
    `main`, mai una scrittura su `main`. Il testo del PBI è quello del Solver, col numero
    successivo a quelli di `backlog/` del clone `[rilascio].clone` e la riga in `CODA.md`.
    Se un PBI di `backlog/` o una PR aperta porta già la stessa causa (R6) non apre niente e
    rende quel PBI con l'URL vuoto, o `PR #N` con il suo URL. Rende il PBI a monte e l'URL della PR; un passo che esce ≠ 0 alza `RuntimeError`."""
    clone, fork = Path(CFG.rilascio.clone), CFG.rilascio.remote_fork
    passo_a_monte(["git", "fetch", "origin"], clone)
    nome_repo = passo_a_monte(["gh", "repo", "view", "--json", "nameWithOwner", "-q",
                               ".nameWithOwner"], clone)
    with worktree_di_rilascio(clone, "origin/main") as albero:
        causa = re.escape(dichiarato["causa"])
        for file in sorted((albero / "backlog").glob("PBI-*.md")):
            if re.search(rf"\*\*Causa:\*\*\s*{causa}(?![\w-])", file.read_text(encoding="utf-8")):
                return f"PBI-{RE_PBI_DEL_BACKLOG.match(file.name).group(1)}", ""
        aperte = json.loads(passo_a_monte(
            ["gh", "pr", "list", "--repo", nome_repo, "--state", "open", "--limit",
             str(LIMITE_PR_R6), "--json", "number,title,body,url"], albero))
        for pr in aperte:
            if re.search(rf"(?<![\w-]){causa}(?![\w-])", f"{pr['title']}\n{pr['body']}"):
                return f"PR #{pr['number']}", pr["url"]
        presenti = [int(m.group(1)) for f in (albero / "backlog").glob("PBI-*.md")
                    if (m := RE_PBI_DEL_BACKLOG.match(f.name))]
        numero = max(presenti, default=0) + 1
        pbi = f"PBI-{numero}"
        testo, nome_file = pbi_a_monte_numerato(dichiarato["pbi"], numero, dichiarato["causa"])
        (albero / "backlog" / nome_file).write_text(testo, encoding="utf-8")
        coda = albero / "backlog" / "CODA.md"
        righe = coda.read_text(encoding="utf-8").splitlines() if coda.exists() else []
        dopo = max([i for i, r in enumerate(righe) if RE_RIGA_DI_CODA.match(r)], default=len(righe) - 1)
        righe.insert(dopo + 1, f"- {pbi}")
        coda.write_text("\n".join(righe) + "\n", encoding="utf-8")
        titolo = testo.splitlines()[0].removeprefix("# ")
        ramo = f"pbi/pbi-{numero}"
        passo_a_monte(["git", "switch", "-c", ramo], albero)
        passo_a_monte(["git", "add", "-A"], albero)
        passo_a_monte(["git", "commit", "-m", f"docs(backlog): apri {titolo}\n\n"
                       f"Limite del runner, causa {dichiarato['causa']}."], albero)
        passo_a_monte(["git", "push", fork, ramo], albero)
        url_fork = passo_a_monte(["git", "remote", "get-url", fork], albero)
        proprietario = re.search(r"github\.com[:/]([^/]+)/", url_fork)
        testa = f"{proprietario.group(1)}:{ramo}" if proprietario else ramo
        corpo = (f"**Causa:** {dichiarato['causa']}\n\nComando: `{dichiarato['comando']}`\n"
                 f"Commit: {dichiarato['commit']}\n\n```\n{dichiarato['output']}\n```\n")
        url = passo_a_monte(["gh", "pr", "create", "--repo", nome_repo, "--base", "main",
                             "--head", testa, "--title", titolo, "--body", corpo], albero)
    return pbi, url


def smista_il_blocco(e: Esito, pbi_path: Path, motivo: str, dettaglio: str,
                     dichiara, rileggi: bool = True) -> None:
    """Lancia il Solver sul blocco di un giro fermato e ne registra l'esito in
    `e.solver` (`PBI-507`, decisione 11). Oltre `[solver].giri_massimi` giri per lo
    stesso PBI non parte, e lo dichiara: avviso e non blocco (`ADR-0008`). A un limite del
    runner apre il PBI a monte e mette il progetto in attesa (`PBI-512`).

    Il contatore si legge dai rapporti su disco con `rileggi`, cioè alla prima chiamata
    del giro; dalle successive cresce in `e.giri_solver`, perché il rapporto del giro in
    corso non ha esiti e non le vedrebbe (`PBI-517`, decisione 9)."""
    if rileggi:
        e.giri_solver = giri_solver_fatti(e.pbi)
    if e.giri_solver >= CFG.solver.giri_massimi:
        dichiara(f"avviso: tetto dei giri del Solver raggiunto ({e.giri_solver} di "
                 f"{CFG.solver.giri_massimi}), il Solver non parte")
        return
    e.giri_solver += 1
    prompt, file_esito = file_dell_invocazione("solver")
    prompt.write_text(prompt_del_pacchetto("solver").format(
        pbi_path=pbi_path.relative_to(REPO), blocco=f"{motivo}: {dettaglio}"),
        encoding="utf-8")
    invocazione = invoca_agente("solver", comando_del_solver(), prompt, file_esito)
    e.invocazioni.append(invocazione.registro)
    dichiarato = invocazione.dichiarato
    e.solver.append(dichiarato if dichiarato is not None
                    else {"esito": "senza esito", "uscita": invocazione.uscita})
    if dichiarato is not None and dichiarato["esito"] == "intento":
        dichiara(f"avviso: il Solver chiede a Francesco: {una_riga(dichiarato['domanda'])}")
    if dichiarato is not None and dichiarato["esito"] == "limite-del-runner":
        metti_in_attesa_del_pbi_a_monte(pbi_path, dichiarato)


def metti_in_attesa_del_pbi_a_monte(pbi_path: Path, dichiarato: dict) -> None:
    """Apre il PBI a monte e mette il progetto in attesa (`PBI-512`, decisione 4): scrive nel
    PBI fermo `attende: <repo>#<PBI>` (formato di `PBI-509`), la committa sul ramo del giro
    (il worktree resta pulito e `chiudi()` pubblica il ramo: `coda.attese()` la legge da
    lì) e crea la pausa del tick."""
    pbi_a_monte, url = apri_pr_a_monte(dichiarato)
    clone = Path(CFG.rilascio.clone)
    repo = passo_a_monte(["gh", "repo", "view", "--json", "nameWithOwner", "-q",
                          ".nameWithOwner"], clone)
    if pbi_a_monte.startswith("PR #"):  # la causa è già in una PR aperta: il suo PBI è nel titolo
        vista = json.loads(passo_a_monte(["gh", "pr", "view", url, "--repo", repo, "--json",
                                          "title,headRefName"], clone))
        nominato = re.search(r"PBI-\d+", f"{vista['title']} {vista['headRefName']}")
        if nominato is None:
            raise RuntimeError(f"la PR {url} non nomina il suo PBI")
        pbi_a_monte = nominato.group(0)
    originale = pbi_path.read_text(encoding="utf-8")
    pbi_path.write_text(f"{originale.rstrip(chr(10))}\n\nattende: {repo}#{pbi_a_monte}\n",
                        encoding="utf-8")
    relativo = str(pbi_path.relative_to(REPO))
    fermo = re.match(r"PBI-\d+", pbi_path.name)
    try:
        git("add", relativo)
        git("commit", "-m", f"chore(coda): {fermo.group(0) if fermo else pbi_path.stem} "
            f"attende {repo}#{pbi_a_monte}")
    except RuntimeError:
        # Un passo fallito non lascia la riga né nello stage né nel file (spec, «Dopo la PR»).
        esegui(["git", "reset", "-q", "HEAD", "--", relativo], REPO)
        pbi_path.write_text(originale, encoding="utf-8")
        raise
    # Lo stesso file di `coda.file_di_pausa()`: `coda` importa il runner, non il contrario.
    (Path.home() / "asdlc-tick.pausa").write_text(
        f"{datetime.now():%Y-%m-%d %H:%M} PR a monte {pbi_a_monte}\n", encoding="utf-8")


@dataclass(frozen=True)
class AMonte:
    """I fatti della PR a monte che la guardia controlla (`PBI-508`): il clone di `asdlc`,
    il ramo della PR e la sua base, il PBI che porta (percorso nel clone) e la `causa`."""

    repo: Path
    ramo: str
    base: str
    pbi: str
    causa: str
    # La testa della PR sta su un fork (`isCrossRepository` di `gh pr view`); `None` se il
    # fatto non c'è, e allora R5 è `non eseguita` e non `ok`.
    da_un_fork: bool | None = None


def controllo_r5(a_monte: AMonte) -> str:
    """R5: la PR parte da un ramo di un fork che non è `main` né la sua base, e non tocca
    `AGENTS.md` né file esistenti di `decisions/` (`git diff --name-status --no-renames` contro la base: uno spostamento è una cancellazione
    più un'aggiunta, e la cancellazione di `AGENTS.md` o di un ADR si vede)."""
    if a_monte.ramo in ("main", a_monte.base):
        return f"R5: violata (la PR parte da {a_monte.ramo})"
    if a_monte.da_un_fork is None:
        return "R5: non eseguita (non si sa se la testa della PR sta su un fork)"
    if not a_monte.da_un_fork:
        return f"R5: violata (la testa {a_monte.ramo} non sta su un fork ma in asdlc)"
    code, uscita = esegui(["git", "diff", "--name-status", "--no-renames",
                           f"{a_monte.base}...{a_monte.ramo}"],
                          a_monte.repo, timeout=120)
    if code != 0:
        return f"R5: non eseguita (git non risponde: {una_riga(uscita)[:100]})"
    toccati = []
    for riga in uscita.splitlines():
        stato, _, percorso = riga.partition("\t")
        if percorso == "AGENTS.md" or (percorso.startswith("decisions/") and stato != "A"):
            toccati.append(percorso)
    if toccati:
        return f"R5: violata (la PR tocca {', '.join(toccati)})"
    return "R5: ok"


# `gh pr list` taglia in silenzio al limite (30 se non glielo si dà): una lista piena non dice
# di aver visto tutte le PR aperte.
LIMITE_PR_R6 = 1000


def controllo_r6(a_monte: AMonte) -> str:
    """R6: nessun altro PBI in `backlog/` né PR aperta in `asdlc` con la stessa `causa`.
    Il PBI e la PR del giro stesso non contano. La causa si confronta a parola intera:
    `runner-xy` e `runner-x-due` non sono `runner-x`."""
    causa = re.escape(a_monte.causa)
    for file in sorted((a_monte.repo / "backlog").glob("PBI-*.md")):
        if file.relative_to(a_monte.repo).as_posix() == a_monte.pbi:
            continue
        if re.search(rf"\*\*Causa:\*\*\s*{causa}(?![\w-])", file.read_text(encoding="utf-8")):
            return f"R6: violata (la causa {a_monte.causa} è già in {file.name})"
    code, uscita = esegui(["gh", "pr", "list", "--state", "open", "--limit", str(LIMITE_PR_R6),
                           "--json", "number,title,body,headRefName"], a_monte.repo, timeout=300)
    if code != 0:
        return f"R6: non eseguita (gh non risponde: {una_riga(uscita)[:100]})"
    aperte = json.loads(uscita)
    if len(aperte) >= LIMITE_PR_R6:
        return f"R6: non eseguita (lista troncata a {LIMITE_PR_R6} PR)"
    for pr in aperte:
        if (pr["headRefName"] != a_monte.ramo
                and re.search(rf"(?<![\w-]){causa}(?![\w-])", f"{pr['title']}\n{pr['body']}")):
            return f"R6: violata (la causa {a_monte.causa} è già nella PR #{pr['number']})"
    return "R6: ok"


def blocco_dello_scope(testo: str) -> str | None:
    """Le righe del blocco `**Scope**` di un PBI, fino al grassetto o alla `## `
    successivi; `None` se il blocco non c'è. La leggono `controllo_r7()` e la
    pre-verifica (PBI-520, decisione 4)."""
    scope = re.search(r"^\*\*Scope\*\*\s*\n(.*?)(?=^\*\*|^## |\Z)", testo, re.S | re.M)
    return scope.group(1) if scope else None


def controllo_r7(a_monte: AMonte) -> str:
    """R7: lo Scope del PBI a monte non elenca file del progetto. Si legge il PBI sul ramo
    della PR. Ogni percorso fra apici inversi in una riga dello Scope è del progetto se la
    riga dice «del progetto» (per `asdlc.toml`, che esiste in entrambi), oppure se né il
    percorso né la sua prima cartella stanno nell'albero di `asdlc` al ramo della PR
    (`git ls-tree`): la prova sta nei fatti e non nella formula del Solver. Un file nuovo
    in una cartella che il runner ha già non è del progetto."""
    code, testo = esegui(["git", "show", f"{a_monte.ramo}:{a_monte.pbi}"], a_monte.repo,
                         timeout=120)
    if code != 0:
        return f"R7: non eseguita (git non risponde: {una_riga(testo)[:100]})"
    code, albero = esegui(["git", "ls-tree", "-r", "--name-only", a_monte.ramo], a_monte.repo,
                          timeout=120)
    if code != 0:
        return f"R7: non eseguita (git non risponde: {una_riga(albero)[:100]})"
    file_del_runner = set(albero.splitlines())
    cartelle_del_runner = {f.split("/")[0] for f in file_del_runner if "/" in f}
    file_del_progetto = []
    for riga in (blocco_dello_scope(testo) or "").splitlines():
        for percorso in re.findall(r"`([^`]+)`", riga):
            fuori_dall_albero = (percorso not in file_del_runner
                                 and percorso.split("/")[0] not in cartelle_del_runner)
            if "del progetto" in riga or fuori_dall_albero:
                file_del_progetto.append(percorso)
    if file_del_progetto:
        return f"R7: violata (lo Scope elenca {', '.join(file_del_progetto)} del progetto)"
    return "R7: ok"


def controlla(regola: str, controllo: Callable[[AMonte], str], a_monte: AMonte | None) -> str:
    """Un controllo che non può girare — nessuna PR, un comando che scade, un `gh` che scrive
    prima del JSON, un file illeggibile — è `non eseguita` e non un'eccezione: la guardia sta
    prima di `chiudi()` (difetto 37) e non deve saltarla."""
    if a_monte is None:
        return f"{regola}: non eseguita (nessuna PR a monte)"
    try:
        return controllo(a_monte)
    except Exception as guasto:  # noqa: BLE001 — si registra come riga, non si tace
        return f"{regola}: non eseguita ({type(guasto).__name__}: {una_riga(str(guasto))[:100]})"


SEGNALA_LIMITE = "mcp__asdlc__segnala_limite_runner"


def controllo_r4(e: Esito) -> str:
    """R4: il Solver ha letto `asdlc.toml` prima di `segnala_limite_runner`. Lo dice la
    traccia della sua sessione, nell'ordine delle chiamate a strumento (`PBI-511`): mai il
    testo di una risposta (`ADR-0027`)."""
    voci = [v for v in e.invocazioni if v.get("ruolo") == "solver" and v.get("traccia")]
    if not voci:
        return "R4: non eseguita (nessuna traccia utile del Solver)"
    letto = False
    for ruolo, _, blocco in blocchi_della_traccia(Path(voci[-1]["traccia"])):
        if ruolo != "assistant" or blocco.get("type") != "tool_use":
            continue
        if blocco["name"] == SEGNALA_LIMITE:
            return "R4: ok" if letto else "R4: violata (asdlc.toml non letto prima della segnalazione)"
        if blocco["name"] == "Read":
            letto = letto or Path(blocco["input"].get("file_path", "")).name == "asdlc.toml"
    return "R4: non eseguita (nessuna segnalazione nella traccia)"


def controlla_r4(e: Esito) -> str:
    """R4 con la stessa rete di `controlla`: una traccia assente o illeggibile non ferma la
    guardia."""
    try:
        return controllo_r4(e)
    except Exception as guasto:  # noqa: BLE001 — si registra come riga, non si tace
        return f"R4: non eseguita ({type(guasto).__name__}: {una_riga(str(guasto))[:100]})"


def guardia_del_solver(e: Esito, a_monte: AMonte | None = None,
                       dichiara: Callable[[str], None] | None = None) -> None:
    """Scrive in `e.guardia` l'esito dei controlli di processo sul Solver (`PBI-508`,
    `ADR-0030` decisione 4, R13). Li fa il codice, leggendo i fatti; la guardia segnala
    e non blocca (`ADR-0008`). Se il Solver non ha girato, la sezione non c'è. Senza la
    PR a monte (`a_monte`) i controlli che la leggono sono `non eseguita`. Ogni riga che non
    è `ok` è anche un avviso, passato a `dichiara` (R13: «nel rapporto e nell'avviso»)."""
    if not e.solver:
        return
    r5, r6, r7 = (controlla(regola, controllo, a_monte) for regola, controllo in
                  (("R5", controllo_r5), ("R6", controllo_r6), ("R7", controllo_r7)))
    righe = [controlla_r4(e), r5, r6, r7]
    e.guardia = "\n".join(["## Guardia di processo", *righe])
    if dichiara is not None:
        for riga in righe:
            if not riga.endswith(": ok"):
                dichiara(f"avviso: guardia di processo — {riga}")


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
        ingresso = dato.get("tool_input") or {}
        percorso = ingresso.get("file_path")
        # Solo un `Write` porta il file intero: un `Edit` ne mostra un pezzo, e su
        # un pezzo non si sa se il file resta uno scheletro (PBI-515, decisione 6).
        contenuto = ingresso.get("content") if dato.get("tool_name") == "Write" else None
        cartella = dato.get("cwd") or os.getcwd()
    except (json.JSONDecodeError, AttributeError, TypeError) as guasto:
        print(f"guardia di fase: stdin illeggibile ({guasto}), lascio passare", file=sys.stderr)
        return 0
    if not percorso:
        return 0  # non è una scrittura su un file: non ci riguarda
    ragione = guardia_di_fase(fase_corrente(Path(cartella)), percorso, contenuto)
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

    L'ultimo commit e basta, non tutto `<base>..HEAD`: dopo tre criteri i test dei
    primi due sono verdi, e la richiesta verrebbe rifiutata per «nato verde» su
    lavoro che il suo rosso l'aveva già avuto.

    I commit del ramo si contano dallo sha di base del giro, che `apri_la_fase()`
    lascia accanto alla fase, e non da `BASE`: un `origin/main` che riceve il ramo
    stesso con un merge veloce renderebbe `BASE..HEAD` vuoto (PBI-380, decisione
    3). Fuori da un giro lo sha non c'è, e si ripiega su `BASE`.
    """
    nuovi = test_nuovi_dellalbero()
    if nuovi:
        return nuovi
    base = base_del_lucchetto()
    if git("rev-list", "--count", f"{base}..HEAD") == "0":
        # Il branch nasce dalla base, quindi al primo `--chiedi-impl` di ogni giro
        # HEAD **è** la base: se lì l'ultimo commit fosse di soli test, il
        # Builder otterrebbe la produzione aperta senza aver scritto una riga.
        return []
    file = file_del_commit("HEAD")
    if any(e_file_di_produzione(v.percorso) for v in file):
        return []  # un commit misto non è un RED: il rosso non può essere esistito lì dentro
    return test_nuovi_del_commit("HEAD", file, base)


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
# Lancia il runner installato, `<pacchetto>/bin/asdlc-runner`, col percorso
# assoluto scritto dentro da `configura()` (PBI-384, decisione 5): mai il sorgente
# dell'albero, che è la copia di lavoro del Builder. Il `pre-commit` è anche
# delle persone: se il comando non c'è il commit passa, con un avviso (ADR-0008).
MODELLO_DELLA_GUARDIA_DEL_COMMIT = """#!/bin/sh
# Installato dal runner ASDLC (PBI-104): il commit non nasce fuori fase.
runner="{runner}"
[ -x "$runner" ] && exec "$runner" --guardia-commit
echo "guardia del lucchetto: runner non trovato in $runner" >&2
exit 0
"""
GUARDIA_DEL_COMMIT: str  # il modello col runner del pacchetto dentro, da `configura()`


def installa_la_guardia_del_commit() -> bool:
    """Mette il `pre-commit` al suo posto. `False` se ce n'era già uno altrui, o
    il nostro con lo stesso testo.

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


# La riga che segue lo shebang di un hook del runner, nella forma di oggi e in
# quella di prima di PBI-388, che nominava un percorso che `PBI-383` sposta.
MARCATORI_DEGLI_HOOK = ("# Installato dal runner ASDLC (PBI-104):",
                        "# Installato da tools/asdlc_runner.py (PBI-104):")


def e_un_hook_del_runner(testo: str) -> bool:
    """Se l'hook l'ha scritto il runner: lo shebang, e sotto uno dei marcatori."""
    righe = testo.splitlines()
    return len(righe) > 1 and righe[0].startswith("#!") \
        and righe[1].startswith(MARCATORI_DEGLI_HOOK)


def installa_un_hook(nome: str, corpo: str) -> bool:
    """Scrive un hook di git in `.git/hooks`, e `False` se ce n'era già uno
    altrui, o il nostro con lo stesso testo. Il nostro con un testo diverso si
    riscrive (PBI-388): è l'unico modo in cui un cambio del testo arriva agli
    alberi in cui l'hook c'è già."""
    cartella = cartella_degli_hook()
    if cartella is None:
        return False
    cartella.mkdir(parents=True, exist_ok=True)
    hook = cartella / nome
    if hook.exists():
        testo = hook.read_text(encoding="utf-8", errors="replace")
        if testo == corpo or not e_un_hook_del_runner(testo):
            return False
    hook.write_text(corpo, encoding="utf-8")
    hook.chmod(0o755)
    return True


# Il `post-commit` che chiude il ciclo. Il Builder fa molti criteri in una
# sessione e fra un commit e l'altro il runner non c'è: se `IMPL` restasse aperta
# dopo il primo permesso, il comportamento successivo tornerebbe a nascere senza
# rosso. Chi vede ogni commit è git, quindi è git a riportare la fase indietro.
RITORNO_IN_TEST_ONLY = f"""#!/bin/sh
# Installato dal runner ASDLC (PBI-104): un commit chiude il ciclo.
fase="$(git rev-parse --git-path {FILE_DELLA_FASE})"
[ -f "$fase" ] && printf '{FASE_TEST_ONLY}\\n' > "$fase"
exit 0
"""


def installa_il_ritorno_in_test_only() -> bool:
    return installa_un_hook("post-commit", RITORNO_IN_TEST_ONLY)


def apri_la_fase(base: str = "") -> None:
    """Accende il lucchetto per questo giro: i due hook di git, e `TEST_ONLY`.
    Accanto alla fase lascia lo sha di base del giro, per `--chiedi-impl`, e il
    percorso della cartella della `LOG_DIR` dove sta la collezione di pytest
    della base, che vale per tutto il giro (PBI-396, decisione 5). La cartella
    porta l'ora dell'apertura, come i file del giro accanto.

    Una collezione che non si legge non ferma l'apertura: il giro non è ancora
    nel suo `try`, e un'eccezione qui lascerebbe la fase aperta. Non solo un
    `GuastoDelGate`: un worktree che non si crea, una raccolta oltre il tetto,
    un JSON senza `nodi` alzano altro. Chi ne ha bisogno la ricalcola, e il
    guasto esce lì, dove il giro lo gestisce.

    L'hook di Claude Code non si installa qui: la guardia di fase del Builder la
    scrive `impostazioni_della_sessione()` a ogni sessione, e gli arriva con
    `--settings`. Questi due sì: `.git/hooks` non è nel repository, e un albero
    appena clonato non li avrebbe.
    """
    if cartella_degli_hook() is None:
        return  # non c'è un repository sotto: non c'è un giro da lucchettare
    installa_la_guardia_del_commit()
    installa_il_ritorno_in_test_only()
    percorso_della_fase(REPO).write_text(f"{FASE_TEST_ONLY}\n", encoding="utf-8")
    if base:
        percorso_della_fase(REPO, FILE_DELLA_BASE).write_text(f"{base}\n", encoding="utf-8")
        aperta = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        collezioni = (LOG_DIR / f"{aperta}_collezioni").resolve()
        percorso_della_fase(REPO, CARTELLA_DELLE_COLLEZIONI).write_text(
            f"{collezioni}\n", encoding="utf-8")
        try:
            collezione_al_commit(base)
        except Exception as guasto:  # noqa: BLE001 — qualunque guasto, vedi sopra
            print(f"    ⚠️  collezione della base non scritta: {str(guasto)[:300]}")


def chiudi_la_fase() -> None:
    """Spegne il lucchetto. Un worktree lasciato in fase è un worktree in cui la
    sessione dopo non può scrivere, e la diagnosi costerebbe più del giro. Con
    la fase se ne va la base del giro: fuori da un giro si conta da `BASE`. E se
    ne va la cartella delle collezioni del giro, nella `LOG_DIR` (PBI-396,
    decisione 5)."""
    collezioni = cartella_delle_collezioni()
    if collezioni is not None:
        shutil.rmtree(collezioni, ignore_errors=True)
    for nome in (FILE_DELLA_FASE, FILE_DELLA_BASE, CARTELLA_DELLE_COLLEZIONI):
        file = percorso_della_fase(REPO, nome)
        if file is not None:
            file.unlink(missing_ok=True)


def contenuto_in_stage(percorso: str) -> str | None:
    """Il file com'è **in stage** (`git show :percorso`), o `None` se lì non c'è:
    il lato vecchio di un rename, una cancellazione — o se non è testo: una fixture
    binaria alzava `UnicodeDecodeError` e piantava il `pre-commit` (PBI-515,
    decisione 6). Senza contenuto la produzione resta chiusa, il resto passa."""
    try:
        return git("show", f":{percorso}")
    except (RuntimeError, UnicodeDecodeError):
        return None


def guardia_del_commit() -> int:
    """Il `pre-commit`: ciò che è in stage deve stare nella fase corrente.

    Guarda lo **stage** e non il modo in cui ci è arrivato, ed è la differenza
    che conta: `Edit`, `Write`, un heredoc da Bash, `sed -i` e una patch applicata
    a mano finiscono tutti nello stesso posto, e qui valgono uguale.

    Un rename in stage si giudica sui due lati: il vecchio è la cancellazione
    di quel percorso, il nuovo un'aggiunta. `--name-only` dava il solo nuovo, e
    in `IMPL` un test spostato in `nota.txt` passava come un file qualsiasi.

    Il contenuto si legge dallo stage, ed è lì che uno scheletro vuoto si
    riconosce (PBI-515, decisione 6): se riceve una riga di codice torna
    produzione, e il commit si ferma come prima (decisione 7).
    """
    fase = fase_corrente(REPO)
    if fase is None:
        return 0
    voci = voci_del_name_status(git("diff", "--cached", "--name-status", "-M"))
    percorsi = [p for voce in voci for p in (voce.vecchio, voce.percorso) if p]
    ragioni = [r for percorso in percorsi
               if (r := guardia_di_fase(fase, percorso, contenuto_in_stage(percorso)))]
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
    spostati: list[dict[str, str]] = []
    try:
        mancati = gate_del_rosso(base=base, ref=solo_ref, morsi=morsi, spostati=spostati)
    except GuastoDelGate as guasto:
        # `2` e non `1`: chi lancia il gate a mano deve distinguere «il rosso non
        # c'è stato» da «il gate non ha potuto guardare».
        print(f"Il gate non ha potuto guardare {base}..{solo_ref}: {guasto}")
        return 2
    if spostati:
        print(f"{len(spostati)} commit che spostano test Python di file, in "
              f"{base}..{solo_ref}: non nascono, e non chiedono un rosso.\n")
        for s in spostati:
            print(f"  {s['commit']}  {s['titolo']}\n    spostati: {s['spostati']}\n")
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
    """I flag, in una funzione sua: così si possono provare senza eseguire un PBI.

    Si costruisce anche senza configurazione, per `--help` fuori da un progetto:
    il ramo di base e la cartella del registro li dice allora la chiave del TOML.
    """
    base = globals().get("BASE", "[git].base")
    log_dir = globals().get("LOG_DIR", "[registro].cartella")
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
    ap.add_argument("--riprendi", action="store_true",
                    help="riprendi il PBI dopo il limite d'uso: il giro riparte dalla punta "
                         "del ramo dell'ultimo rapporto, non dalla base (PBI-519)")
    ap.add_argument("--continua-sui-rossi", action="store_true",
                    help="prosegui col PBI successivo anche se questo è rimasto rosso")
    ap.add_argument("--in-primo-piano", action="store_true",
                    help="non staccarsi dalla sessione: output a schermo e exit code. "
                         "Di default il giro si stacca e scrive in runs/<run>.log")
    ap.add_argument("--registra", nargs="?", const=str(log_dir), metavar="CARTELLA",
                    help="non esegue niente: piega i rapporti runs/*.json in runs/tempi.csv. "
                         "Si lancia su main dopo il merge (ADR-0020)")
    ap.add_argument("--gate-rosso", nargs="?", const="HEAD", metavar="REF",
                    help=f"non esegue niente: cammina {base}..REF e dice in quali "
                         "commit un test è nato senza essere mai stato rosso")
    ap.add_argument("--preverifica", action="store_true",
                    help="non esegue il PBI: ne legge il file alla base e scrive in "
                         f"{log_dir} i rilievi di forma e gli avvisi. Esce 1 con un "
                         "rilievo (PBI-520)")
    ap.add_argument("--lettore", action="store_true",
                    help="con --preverifica: lancia anche il Lettore, che risponde alle sette "
                         "domande in un albero usa e getta alla base e scrive le sonde, i "
                         "test RED dei criteri. Una sonda verde è un rilievo R (PBI-521)")
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
    """Il punto d'ingresso: legge `asdlc.toml` e poi fa ciò che chiedono i flag.

    La configurazione si legge qui e non all'import (PBI-382): un modulo
    importato non deve leggere niente. `asdlc.toml` è obbligatorio, e un file
    che manca o non si legge ferma con un messaggio e non con un traceback: lo
    legge chi ha appena perso l'uso di `git commit`, perché il `pre-commit`
    esegue questo file a ogni commit.
    """
    try:
        # Fuori da un progetto ci si ferma qui, prima del lucchetto e di ogni
        # scrittura: il runner non ha niente da fare, e lo dice.
        radice = asdlc_config.radice(Path.cwd())
        # `configura()` compone i percorsi da `REPO`: la radice va messa prima.
        global REPO
        REPO = radice
        configura(asdlc_config.carica(REPO))
    except asdlc_config.ErroreDiConfigurazione as guasto:
        # `--help` risponde anche fuori da un progetto: è il primo comando che si
        # prova dopo `pip install ./tools` (PBI-384).
        if {"-h", "--help"} & set(sys.argv[1:]):
            costruisci_parser().print_help()
            return 0
        sys.exit(f"asdlc_runner: {guasto}")
    return smista()


def smista() -> int:
    """`main()` a configurazione già letta: i test la chiamano da qui, coi nomi
    di modulo che hanno sostituito."""
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
    if a.preverifica:
        # Prima dell'ambiente, del distacco e del lucchetto, come `--gate-rosso`: non
        # tocca l'albero, e il codice d'uscita resta a chi lo lancia (decisione 7).
        return max(preverifica(pbi, lettore=a.lettore) for pbi in a.pbi)

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

    # L'ambiente si verifica prima del distacco e del lucchetto: un giro che non
    # può girare si dice qui, con l'uscita che il tick legge, e non a metà del
    # Builder. Un `--dry-run` stampa il prompt e basta, e non lo pretende.
    if not a.dry_run and (mancanze := mancanze_dell_ambiente()):
        print("Non parto:")
        for mancanza in mancanze:
            print(f"  {mancanza}")
        return 2

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
                  "Il lucchetto è di un runner vivo — `ps aux | grep asdlc/runner` dice "
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
                               con_critic=not a.senza_critic, run=run,
                               riprendi=a.riprendi)
            except Exception as exc:  # noqa: BLE001 — qui si cattura per non perdere il resto
                # Un guasto dentro un PBI è un esito di **quel** PBI. Prima usciva
                # da `main()` col traceback e si portava via la sequenza intera, e
                # con lei i rilievi del Critic dei PBI già chiusi (difetto 17).
                # Lo stato è `rosso` perché è già nella regola che decide se
                # proseguire: non serve un'eccezione al posto di una regola. Una
                # `ChiusuraFallita` porta il motivo che stava chiudendo, e il
                # rapporto lo ha anche nel suo campo; ogni altra eccezione no
                # (PBI-380, decisione 2).
                traceback.print_exc()
                e = Esito(pbi, "rosso", nota=f"eccezione nel runner: {exc}"[:300],
                          motivo=exc.motivo if isinstance(exc, ChiusuraFallita) else "",
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
        print(f"\nRegistro: `python3 tools/asdlc/runner.py --registra {LOG_DIR}` "
              f"su main, dopo il merge. Rapporto del giro: {rapporto}")
        totale = sum(e.durata_s for e in esiti)
        print(f"\n{len(esiti)} PBI · tempo totale {hms(totale)}"
              + (f" · {totale / 3600 * a.tariffa:.2f} €" if a.tariffa else ""))
        print(f"Rapporto: runs/{run}.json · tempi: runs/tempi.csv")
        return 0 if all(e.stato in ("fatto", "saltato") for e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
