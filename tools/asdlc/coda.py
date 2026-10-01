#!/usr/bin/env python3
"""Il tick della coda: guarda lo stato, decide **una** cosa e finisce.

Fra il merge di un PBI e il lancio del successivo passano ore in cui non succede
niente, e il tempo morto non è il comando da digitare: è l'attesa che qualcuno
torni al terminale. Questo è il processo breve che `cron` chiama a intervalli
regolari per togliere quell'attesa (`backlog/PBI-350`).

Quello che **non** fa, ed è la riga che lo tiene dentro i suoi confini: non
mergia — il merge è il terzo gate, il confine dell'accountability, e non è
delegabile (`runner.py:17`) — e non decide cosa entra in coda. La coda la
scrive Francesco a mano in `backlog/CODA.md`; il tick è un esecutore d'ordini già
dati, e non ne inventa nessuno.

La decisione è separata dagli effetti: `prossimo()` è una funzione pura, ed è la
sola cosa che i test guardano.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO

# Il checkout da cui si legge la coda e si interroga `origin`: il primo antenato
# della cwd che contiene `asdlc.toml`, trovato da `main()` (PBI-382). Non la
# cartella di questo file: installato, il codice sta in site-packages. È l'unico
# percorso che non sta in `asdlc.toml` — un percorso assoluto in un file
# versionato è il difetto che la configurazione toglie.
REPO: Path

# Il tick è un modulo del pacchetto `asdlc`, in `tools/asdlc/` (PBI-383), e si
# lancia ancora per percorso, come il runner: `tools/` va sul `sys.path`, o
# `asdlc.config` non si trova. Qui conta dove sta il codice, non dove sta il
# progetto.
SORGENTE = Path(__file__).resolve().parent.parent
if str(SORGENTE) not in sys.path:
    sys.path.insert(0, str(SORGENTE))
from asdlc import config as asdlc_config  # noqa: E402
# La ricerca degli eseguibili e delle versioni è la stessa del runner: il tick la
# fa prima di lanciare, sullo stesso `asdlc.toml` (PBI-384).
from asdlc import runner as asdlc_runner  # noqa: E402

# Le costanti che seguono nascono da `asdlc.toml`, in `configura()`: è lo stesso
# file che legge il runner, quindi il tick e il runner non possono più dire due
# forme diverse dello stesso id (PBI-353).
CFG: asdlc_config.Config
# Il worktree in cui il runner lavora, default di `--worktree`. È diverso dal
# checkout perché `ada-run` cambia ramo sotto i piedi a ogni giro.
WORKTREE_DEL_RUNNER: Path      # `[worktree].percorso`
# Il log del tick. Sotto `runs/`, dove `*.log` è già ignorato da git: un file
# non ignorato in quella cartella renderebbe sporco il giro che sta per partire.
LOG: Path                      # `[registro].cartella` / coda.log
# Dove il runner tiene il lucchetto del suo albero (`lucchetto()`, `NOME_LUCCHETTO`).
LUCCHETTO: Path                # `[registro].cartella` / .runner.lock
# Il lucchetto del tick, nel checkout da cui si legge la coda: lo prendono il
# tick e `asdlc-chiudi-giro` (PBI-392, `lucchetto_del_tick()`).
LUCCHETTO_DEL_TICK: Path       # `[registro].cartella` / .tick.lock
BACKLOG: str                   # `[backlog].cartella`
CODA: Path                     # `[backlog].coda`, relativo al checkout
BASE: str                      # `[git].base`
REMOTO: str                    # `origin`, da `BASE`
PREFISSO_RAMO: str             # `[git].prefisso_ramo`
# Il venv in cui è installato il runner, assoluto: il tick lancia
# `<pacchetto>/bin/asdlc-runner`, mai la copia di lavoro dell'albero (PBI-384).
PACCHETTO: Path | None         # `[ambiente].pacchetto`


@dataclass(frozen=True)
class VocePbi:
    """Una riga `- PBI-337` della coda: un PBI da lanciare."""

    pbi: str


@dataclass(frozen=True)
class VoceBarriera:
    """Una riga `- ‖ testo` della coda: un gesto umano che deve venire prima."""

    testo: str


Voce = VocePbi | VoceBarriera


@dataclass(frozen=True)
class Occupato:
    """Un giro è già in corso: il tick finisce senza toccare niente."""


@dataclass(frozen=True)
class Finita:
    """La coda è tutta in `main`: non c'è più niente da lanciare."""


@dataclass(frozen=True)
class Barriera:
    """La coda si ferma qui, e questo è ciò che aspetta."""

    testo: str


@dataclass(frozen=True)
class Attende:
    """Il giro di questo PBI c'è già stato e si è fermato: tocca a un umano.

    `pr` sono le PR aperte sul ramo del PBI, `None` se `gh` non ha risposto alla
    ricerca: è ciò che la riga dice a chi la legge (PBI-381, decisione 3).
    """

    pbi: str
    pr: tuple[str, ...] | None = ()


@dataclass(frozen=True)
class Lancia:
    """C'è un PBI pronto da far partire, ed è questo."""

    pbi: str


Decisione = Occupato | Finita | Barriera | Attende | Lancia

# Le due sole forme che sono una voce, e nient'altro della pagina lo è. Le regole
# sono ancorate a tutta la riga di proposito: `backlog/CODA.md` è insieme il
# documento e l'ingresso del programma, e la sua prosa **nomina** le voci — la
# legenda in cima le cita fra apici inversi, la sezione «Fuori dalla coda» scrive
# in grassetto i PBI che non ci sono. Una regola larga le prenderebbe per ordini.
# La forma dell'id viene dal modello `[backlog].id`, in `configura()`.
RE_PBI: re.Pattern[str]
RE_BARRIERA = re.compile(r"^-\s+‖\s*(.+?)\s*$")


def leggi_voci(testo: str) -> list[Voce]:
    """Le voci di `CODA.md`, nell'ordine del file. Tutto il resto è prosa."""
    voci: list[Voce] = []
    for riga in testo.splitlines():
        if (pbi := RE_PBI.match(riga)) is not None:
            voci.append(VocePbi(pbi.group(1)))
        elif (barriera := RE_BARRIERA.match(riga)) is not None:
            voci.append(VoceBarriera(barriera.group(1)))
    return voci


def prossimo(
    voci: list[Voce], mergiati: set[str], rami: set[str], occupato: bool
) -> Decisione:
    """Cosa fare adesso, dato lo stato del mondo.

    Il controllo del giro in corso sta **prima** di tutto: un albero, un agente.
    Quando c'è già qualcuno al lavoro la coda non si guarda nemmeno, perché
    qualunque cosa dicesse porterebbe a un secondo agente sullo stesso worktree.
    """
    if occupato:
        return Occupato()
    for voce in voci:
        # La barriera ferma il giro dove sta: ciò che aspetta è un gesto umano, e
        # nessuna voce dietro di lei può scavalcarlo.
        if isinstance(voce, VoceBarriera):
            return Barriera(voce.testo)
        # Un PBI in `main` è finito, e la sua voce è spenta: il ramo che si è
        # lasciato dietro non conta più niente, perché un ramo su `origin` parla
        # solo in assenza di merge.
        if voce.pbi in mergiati:
            continue
        # Il runner pubblica il ramo su ogni stato che interrompe (`chiudi()`):
        # un ramo senza merge è un giro già fatto e fermo, e ciò che manca è un
        # gesto umano. Rilanciarlo darebbe due rami sullo stesso PBI.
        if voce.pbi in rami:
            return Attende(voce.pbi)
        return Lancia(voce.pbi)
    return Finita()


def esegui(cmd: list[str], cwd: Path) -> tuple[int, str]:
    """Il varco verso il mondo, e l'unico: è il punto che i test sostituiscono.

    Un comando che non esiste torna `127` — la convenzione della shell — invece
    di alzare: qui un guasto dello strumento deve diventare una decisione che lo
    dichiara, non un traceback in un log che nessuno sta guardando.
    """
    try:
        finito = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as guasto:
        return 127, f"comando non eseguibile: {cmd[0]} — {guasto}"
    return finito.returncode, finito.stdout + finito.stderr


# I due modi in cui una PR nomina il suo PBI: il titolo che `apri_pr()` costruisce
# e il ramo che `crea_branch()` chiede a `nome_libero()`. Il secondo copre i giri
# intitolati con la convenzione vecchia, `feat(scope): PBI-XXX — …`, e arriva col
# suffisso del giro (`pbi/pbi-338-giro3`) quando un primo giro c'era già. Le tre
# regole nascono in `configura()` dal modello dell'id e dal prefisso del ramo.
RE_TITOLO_PR: re.Pattern[str]
RE_RAMO_PR: re.Pattern[str]
# Lo stesso ramo letto da `git ls-remote`, che lo rende col prefisso dei ref.
RE_RAMO_PBI: re.Pattern[str]


def configura(cfg: asdlc_config.Config) -> None:
    """Le costanti di modulo, dalla configurazione: una volta da `main()`, e i
    test la richiamano con un `asdlc.toml` di prova. Restano nomi di modulo per
    la stessa ragione del runner — è ciò che i test sostituiscono."""
    global CFG, WORKTREE_DEL_RUNNER, LOG, LUCCHETTO, BACKLOG, CODA, BASE, REMOTO
    global PREFISSO_RAMO, RE_PBI, RE_TITOLO_PR, RE_RAMO_PR, RE_RAMO_PBI, PACCHETTO
    global LUCCHETTO_DEL_TICK
    CFG = cfg
    WORKTREE_DEL_RUNNER = cfg.worktree.percorso
    LOG = Path(cfg.registro.cartella) / "coda.log"
    LUCCHETTO = Path(cfg.registro.cartella) / ".runner.lock"
    LUCCHETTO_DEL_TICK = Path(cfg.registro.cartella) / ".tick.lock"
    BACKLOG = cfg.backlog.cartella
    CODA = Path(cfg.backlog.coda)
    BASE, REMOTO = cfg.git.base, cfg.git.remoto
    PREFISSO_RAMO = cfg.git.prefisso_ramo
    PACCHETTO = cfg.ambiente.pacchetto
    id_pbi = asdlc_config.regex_del_modello(cfg.backlog.id).pattern
    ramo = re.escape(PREFISSO_RAMO) + r"(\d+)"
    RE_PBI = re.compile(rf"^-\s+({id_pbi})\s*$")
    RE_TITOLO_PR = re.compile(rf"^\s*({id_pbi})\s*:")
    RE_RAMO_PR = re.compile(rf"^{ramo}")
    RE_RAMO_PBI = re.compile(rf"refs/heads/{ramo}")


class Guasto(RuntimeError):
    """Il mondo non ha risposto: il tick non lancia, e scrive cosa è successo."""


# Quante PR mergiate si chiedono a `gh` in un colpo. Larga di proposito — al
# 06/09/2026 le PR mergiate del repository sono 186 — perché il tick non ha un
# cursore per scelta: rifà la domanda da zero a ogni giro, e una finestra stretta
# la riempirebbe subito.
LIMITE_PR = 1000

# Quanti file per PR rende `gh pr list --json files`. Non è una scelta nostra e
# non si alza: è il tetto dell'API, e una PR che lo raggiunge ha un elenco che
# può essere tagliato. Vale come limite e non come misura, quindi il confronto è
# `>=`: un elenco più lungo sarebbe già arrivato tagliato a cento.
LIMITE_FILE = 100


def pbi_nominato(pr: dict) -> str | None:
    """Il PBI che la PR nomina — nel titolo o nel nome del ramo — o `None`.

    I due sono in *or* perché sono due modi di dire la stessa cosa, e ciascuno
    copre ciò che l'altro perde: il titolo prende le implementazioni fatte a mano
    da rami che non sono `pbi/` (#158, PBI-104 da `ci/`), il ramo prende i giri
    del runner intitolati con la convenzione vecchia, `feat(scope): PBI-XXX — …`.

    Il ramo si legge dal record della PR e non da git: `headRefName` regge alla
    potatura del ramo — verificato il 09/09 su #207 e #206 — mentre lo squash in
    git il ramo lo perde davvero, ed è per quello che era stato scartato.
    """
    if (dal_titolo := RE_TITOLO_PR.match(pr.get("title", ""))) is not None:
        return dal_titolo.group(1)
    if (dal_ramo := RE_RAMO_PR.match(pr.get("headRefName", ""))) is not None:
        return CFG.backlog.id_di(dal_ramo.group(1))
    return None


def tocca_codice(pr: dict) -> bool:
    """La PR ha cambiato qualcosa **fuori** da `backlog/`?

    È la domanda che distingue la PR che *accoda* un PBI da quella che lo *fa*:
    la prima scrive il file del PBI e la sua riga in `CODA.md`, e non tocca
    nient'altro. Il titolo le due specie non le distingue, e il 09/09 la #215 ha
    spento la voce di PBI-352 nell'istante in cui la scriveva.

    Un elenco che non dice cosa la PR ha toccato si legge come **sì**, cioè come
    la PR che spende il PBI. Sono tre silenzi: il campo che `gh` non rende, la PR
    senza file, e l'elenco lungo esattamente `LIMITE_FILE`, che può essere
    tagliato. È il fail-closed di PBI-350 col segno tenuto dalla parte giusta —
    non rilanciare un PBI che potrebbe già essere in `main`.
    """
    percorsi = pr.get("files") or []
    if not percorsi or len(percorsi) >= LIMITE_FILE:
        return True
    return any(not f.get("path", "").startswith(f"{BACKLOG}/") for f in percorsi)


def pbi_mergiati(repo: Path) -> set[str]:
    """I PBI già in `main`: quelli che una PR mergiata **nomina e ha implementato**.

    Due condizioni: la PR nomina il PBI — nel titolo o nel ramo, `pbi_nominato()`
    — e ha cambiato qualcosa fuori da `backlog/` (`tocca_codice()`). Il titolo da
    solo dice che una PR *parla* di un PBI, non che lo fa, e la PR che lo accoda
    ne parla per prima.

    L'elenco pieno è un guasto e non un dato. `gh` non risponde mai «non lo so»:
    una PR fuori dalla finestra semplicemente non c'è, e qui diventerebbe «non
    mergiato» — che su una voce il cui ramo è stato potato dopo il merge vuol
    dire `Lancia`, cioè il rilancio di un PBI già in `main`. Allargare la
    finestra non lo toglie: una finestra grande resta una finestra.
    """
    codice, uscita = esegui(
        ["gh", "pr", "list", "--state", "merged",
         "--limit", str(LIMITE_PR), "--json", "title,headRefName,files"],
        repo,
    )
    if codice != 0:
        raise Guasto(f"gh non risponde (uscita {codice}): {uscita.strip()[:200]}")
    try:
        elenco = json.loads(uscita)
    except ValueError as illeggibile:
        raise Guasto(f"gh ha risposto qualcosa che non è JSON: {illeggibile}") from None
    if len(elenco) >= LIMITE_PR:
        raise Guasto(
            f"gh ha reso {len(elenco)} PR mergiate, cioè tutta la finestra di "
            f"{LIMITE_PR} che gli è stata chiesta: l'elenco può essere tagliato, e un "
            "PBI già in main che non ci compaia si rilancerebbe. Alza LIMITE_PR in "
            "tools/asdlc/coda.py."
        )
    return {
        nome
        for pr in elenco
        if (nome := pbi_nominato(pr)) is not None and tocca_codice(pr)
    }


def pbi_con_ramo(repo: Path) -> set[str]:
    """I PBI per cui `origin` ha già un ramo, col suffisso di un secondo giro o senza.

    Si chiede al remoto perché è l'unico posto in cui un giro fallito lascia
    traccia per tutti, ed è la stessa lettura di `rami_su_origin()`.
    """
    # La cartella del prefisso e basta — `refs/heads/pbi/*` — e non tutti i rami.
    cartella = PREFISSO_RAMO.rpartition("/")[0]
    codice, uscita = esegui(
        ["git", "-C", str(repo), "ls-remote", "--heads", REMOTO, f"refs/heads/{cartella}/*"],
        repo,
    )
    if codice != 0:
        raise Guasto(f"git non parla con {REMOTO} (uscita {codice}): {uscita.strip()[:200]}")
    return {CFG.backlog.id_di(numero) for numero in RE_RAMO_PBI.findall(uscita)}


def pr_sul_ramo(repo: Path, pbi: str) -> tuple[str, ...] | None:
    """Gli URL delle PR aperte sui rami del PBI, col suffisso di un secondo giro
    o senza, letti dal JSON di `gh`; `None` se `gh` non risponde. Non ripiega su
    niente: la riga segnala e il tick passa (`ADR-0008`, PBI-381 decisione 3)."""
    codice, uscita = esegui(
        ["gh", "pr", "list", "--state", "open",
         "--limit", str(LIMITE_PR), "--json", "url,headRefName"],
        repo,
    )
    if codice != 0:
        return None
    try:
        elenco = json.loads(uscita)
    except ValueError:
        return None
    return tuple(
        pr["url"]
        for pr in elenco
        if (ramo := RE_RAMO_PR.match(pr.get("headRefName", ""))) is not None
        and CFG.backlog.id_di(ramo.group(1)) == pbi
    )


# L'intestazione di una sezione di domande dentro un PBI.
RE_DOMANDE = re.compile(r"^#+[^\S\n]*❓.*$", re.MULTILINE)


def avviso_domande(repo: Path, pbi: str) -> str:
    """L'intestazione della sezione `❓` di quel PBI, o `""` se non ce n'è.

    È un **avviso**, e la differenza è tutta lì: un grep cieco direbbe che
    PBI-340 non si può lanciare, e avrebbe torto — la sua sezione `❓` è un
    protocollo di rifinitura già deciso, mentre quella di PBI-349 era una
    domanda aperta. I due si distinguono leggendoli, e il cancello vero è
    altrove: mettere un PBI in coda è dichiarare che le sue domande sono
    chiuse. Il tick non rifà quella verifica perché non può — la stampa e
    lancia lo stesso (`ADR-0008`).
    """
    numero = CFG.backlog.numero(pbi)
    if numero is None:
        return ""
    for file in sorted((repo / BACKLOG).glob(CFG.backlog.glob_del_file(numero))):
        trovato = RE_DOMANDE.search(file.read_text(encoding="utf-8"))
        if trovato is not None:
            return trovato.group(0).strip()
    return ""


def giro_in_corso(worktree: Path) -> bool:
    """C'è già un runner al lavoro in quell'albero?

    Si guarda se il lucchetto è **tenuto**, non se il file c'è: `lucchetto()` lo
    apre e ci mette sopra un `flock`, ma non lo cancella all'uscita, quindi il
    file sopravvive a ogni giro. Letto come presenza, il primo giro della storia
    spegnerebbe la coda per sempre — che è il modo più silenzioso di non fare
    niente. Il `flock` invece è dell'open file description: il kernel lo rilascia
    quando il processo muore, comunque muoia, ed è esattamente la domanda «c'è
    qualcuno adesso».

    Un lucchetto che non si riesce nemmeno ad aprire conta come tenuto: nel
    dubbio non si lancia (PBI-350, punto 8).

    Il lucchetto è l'unica prova (PBI-373). Chi lavora nell'albero e ha
    `asdlc_runner` nel comando non è per questo un runner: un poller o un
    Monitor di Claude lo sembravano, e fermavano il tick (difetto 47 di PBI-102).
    """
    file = worktree / LUCCHETTO
    if file.exists():
        try:
            with file.open("r+") as fd:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return True
                fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            return True
    return False


def lucchetto_del_tick(repo: Path) -> IO[str] | None:
    """Il file di `<repo>/runs/.tick.lock` col `flock` preso, o `None` se lo tiene
    già qualcun altro: un altro tick, o `asdlc-chiudi-giro` (PBI-392).

    Senza aspettare (`LOCK_NB`): chi lo trova tenuto esce, e il tick dopo arriva
    fra dieci minuti. Come il lucchetto del runner è un `flock`, del processo e
    non del file — il kernel lo rilascia quando il descrittore si chiude o il
    processo muore, e un file rimasto su disco senza nessuno che lo tiene non
    ferma niente (`PBI-373`, difetto 9). Il descrittore che Python apre non è
    ereditabile: il runner lanciato dal tick non se lo porta via.
    """
    file = repo / LUCCHETTO_DEL_TICK
    file.parent.mkdir(parents=True, exist_ok=True)
    aperto = file.open("w")
    try:
        fcntl.flock(aperto, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        aperto.close()
        return None
    return aperto


def decidi(repo: Path, worktree: Path) -> Decisione:
    """La decisione di questo tick, sullo stato che il mondo racconta adesso.

    `repo` è il checkout principale, da cui si legge la coda e si interroga
    `origin`; `worktree` è l'albero in cui il runner lavora. Sono due percorsi
    diversi perché il tick non gira dentro l'albero che comanda: quello cambia
    ramo sotto i piedi a ogni giro, e un programma che leggesse il proprio
    codice da lì si riscriverebbe a metà tick.

    Il giro in corso si guarda **prima** di ogni domanda al mondo: davanti a un
    albero occupato non c'è risposta di `gh` che cambi la decisione.

    Fail-closed su tutto ciò che sta fuori: `gh` che non risponde, la coda che non
    si legge, un `git` che alza. Un tick che sbaglia per eccesso di prudenza costa
    dieci minuti fino al tick dopo; uno che lancia sul dubbio costa un giro e un
    ramo da ripulire. Fa eccezione la ricerca delle PR di un PBI in attesa: lì non
    c'è niente da lanciare, e un `gh` muto si scrive nella riga (PBI-381).
    """
    if giro_in_corso(worktree):
        return Occupato()
    file_coda = repo / CODA
    try:
        voci = leggi_voci(file_coda.read_text(encoding="utf-8"))
        mergiati, rami = pbi_mergiati(repo), pbi_con_ramo(repo)
    except OSError as illeggibile:
        return Barriera(f"la coda non si legge — {file_coda.name}: {illeggibile}")
    except Guasto as guasto:
        return Barriera(str(guasto))
    decisione = prossimo(voci, mergiati, rami, occupato=False)
    # Solo sull'attesa: la riga dice cosa c'è sul ramo, e la PR nata senza URL
    # si ritrova qui senza riscrivere il registro del giro (PBI-381).
    if isinstance(decisione, Attende):
        return Attende(decisione.pbi, pr_sul_ramo(repo, decisione.pbi))
    return decisione


def preflight() -> list[list[str]]:
    """Il pre-flight del lancio a mano, nell'ordine in cui va fatto.

    Il registro dei tempi si rimette a posto per primo: il controllo d'igiene
    del runner guarda tutto l'albero senza eccezioni, e `runs/tempi.csv` sporco
    fermerebbe il giro prima di cominciare. Ci si stacca sul ramo di base di
    `asdlc.toml`, lo stesso da cui il runner ramifica: su un altro, il branch
    nascerebbe da una base vecchia. Una funzione e non una costante, perché il
    ramo e il registro si leggono quando si lancia, non all'import.
    """
    return [
        ["git", "checkout", "--", f"{CFG.registro.cartella}/{CFG.registro.tempi}"],
        ["git", "fetch", REMOTO],
        ["git", "switch", "--detach", BASE],
    ]


# Quanto si aspetta, dopo che il comando del runner è tornato, prima di chiedere
# all'albero se il giro è vivo. Il runner si stacca con un `fork` e il padre esce
# `0` subito, quindi quando `esegui()` torna il figlio esiste **comunque** —
# anche quello che sta per rifiutarsi. La domanda va fatta dopo che i rifiuti
# hanno avuto il tempo di succedere, e succedono tutti in meno di un secondo: il
# lucchetto, `agenti_estranei()`, i gate, il controllo d'igiene sul primo PBI. Un
# giro vero invece dura un'ora, e passati quindici secondi è ancora lì.
ATTESA_DEL_DISTACCO = 15.0


def runner_installato() -> Path:
    """`<pacchetto>/bin/asdlc-runner`, per percorso assoluto: il cron ha il `PATH`
    minimo, e il runner che lavora è quello installato, non il sorgente
    dell'albero che il giro sta per cambiare (`ADR-0026`, decisione 3)."""
    if PACCHETTO is None:
        raise Guasto("asdlc.toml non dichiara `[ambiente].pacchetto`: non so quale "
                     "runner lanciare")
    return PACCHETTO / "bin" / "asdlc-runner"


def mancanze_dell_ambiente(worktree: Path) -> list[str]:
    """Ciò che manca perché il runner possa partire in `worktree`, una riga per
    mancanza; vuota se non manca niente (PBI-384, decisione 7).

    Il runner installato, `<pacchetto>/bin/asdlc-runner`, e l'ambiente che il
    runner stesso verificherebbe all'avvio: gli `[ambiente].eseguibili` nel venv
    del worktree o sul `PATH`, alla versione di `[ambiente].minimi`. Il runner li
    guarda anche lui, ma dopo il distacco, e lì la ragione finisce in un log che
    il tick non legge.
    """
    mancanze: list[str] = []
    if PACCHETTO is None:
        mancanze.append("ambiente mancante: asdlc.toml non dichiara `[ambiente].pacchetto`, "
                        "il venv in cui è installato il runner")
    else:
        comando = runner_installato()
        if not (comando.is_file() and os.access(comando, os.X_OK)):
            mancanze.append(f"ambiente mancante: `{comando}` non c'è o non è eseguibile — "
                            "`pip install ./tools` nel venv del pacchetto")
    ambiente = CFG.ambiente
    mancanze += asdlc_runner.eseguibili_mancanti(ambiente.eseguibili, ambiente.venv, worktree)
    mancanze += asdlc_runner.versioni_sotto_il_minimo(ambiente.minimi, ambiente.venv, worktree)
    return mancanze


def lancia(pbi: str, worktree: Path) -> None:
    """Il pre-flight e poi il runner, tutto dentro il worktree del runner.

    È lo stesso lancio che si fa a mano, e le sue tre righe vivevano in una
    memoria di sessione: qui diventano codice versionato — la stessa correzione
    che il 25/08 ha fatto rientrare nel runner ciò che stava in `ada-notte.sh`,
    fuori dal repository, dove nessuno lo vedeva.

    Il runner si stacca da sé in una sessione sua, quindi questa chiamata torna
    in pochi secondi e il tick finisce: un tick che aspettasse la fine del giro
    sarebbe il processo di un'ora che `cron` ritrova al giro dopo.

    Una riga del pre-flight che fallisce alza, e il runner non parte: se `git
    fetch` non prende `origin`, lo `switch --detach` finisce su un `origin/main`
    di ieri e il ramo nascerebbe su una base vecchia.

    Il codice d'uscita del runner copre ciò che succede **prima** del distacco, e
    solo quello: `--e2e`, un argomento che argparse rifiuta, un `asdlc-runner`
    che nel venv del pacchetto non c'è. Dopo non copre più niente, perché `stacca()` esce
    dal padre con `os._exit(0)` prima del lucchetto, di `agenti_estranei()` e del
    controllo d'igiene — e l'ordine è deliberato, il `flock` vive nell'open file
    description e un padre che lo prendesse e poi forkasse se lo porterebbe via.
    Così una gara sull'albero, un file sporco o un PBI senza file in `backlog/`
    fanno uscire male il **figlio**, e quel codice finisce in `runs/<run>.log`.

    Per quelli non si legge un codice: si guarda l'albero. Passata l'attesa del
    distacco, o lì dentro c'è un giro vivo, o il giro non è partito — e allora si
    alza, perché altrimenti nel log resterebbe «lancia», con un riprova a ogni
    tick e nessuna diagnosi da nessuna parte.
    """
    for comando in preflight():
        codice, uscita = esegui(comando, worktree)
        if codice != 0:
            raise Guasto(
                f"il pre-flight si è fermato su `{' '.join(comando)}` "
                f"(uscita {codice}): {uscita.strip()[:200]}"
            )
    codice, uscita = esegui([str(runner_installato()), pbi], worktree)
    if codice != 0:
        raise Guasto(
            f"il runner non è partito su {pbi} (uscita {codice}): {uscita.strip()[:200]}"
        )
    time.sleep(ATTESA_DEL_DISTACCO)
    if not giro_in_corso(worktree):
        raise Guasto(
            f"il runner si è staccato e poi si è fermato su {pbi}: in {worktree} non "
            "c'è nessun giro vivo. Il perché è nell'ultimo runs/*.log dell'albero — "
            "una gara sul lucchetto, un file sporco, un PBI senza file in backlog/."
        )


def racconta(decisione: Decisione) -> str:
    """La decisione in una riga, che è la forma in cui va a schermo e nel log."""
    match decisione:
        case Occupato():
            return "occupato: un giro è già in corso, non tocco niente"
        case Finita():
            return "finita: in coda non resta niente da lanciare"
        case Barriera(testo):
            return f"barriera: {testo}"
        case Attende(pbi, pr):
            sul_ramo = ("GitHub non ha risposto: PR da verificare" if pr is None
                        else f"PR {', '.join(pr)}" if pr
                        else "nessuna PR sul ramo: crearla o rilanciare")
            return f"attende: {pbi} ha un ramo su origin e non è in main — {sul_ramo}"
        case Lancia(pbi):
            return f"lancia: {pbi}"
    return f"decisione senza nome: {decisione}"


def scrivi_nel_log(repo: Path, riga: str) -> None:
    """Una riga in coda a `runs/coda.log`, con l'ora davanti.

    Il tick gira senza nessuno davanti: senza questa riga, l'unico modo di
    sapere perché la coda è ferma sarebbe rifare il giro a mano.
    """
    file = repo / LOG
    file.parent.mkdir(exist_ok=True)
    with file.open("a", encoding="utf-8") as log:
        log.write(f"{datetime.now().isoformat(timespec='seconds')}  {riga}\n")


def file_di_pausa() -> Path:
    """`~/asdlc-tick.pausa`, calcolato quando serve e non all'import: i test
    spostano `HOME` (PBI-385, decisione 5). Non sta in `asdlc.toml`, che non
    porta percorsi di macchina, e vale per ogni tick dell'utente su questa
    macchina, di qualsiasi progetto."""
    return Path.home() / "asdlc-tick.pausa"


def pausa() -> str | None:
    """La riga del file di pausa — data, ora e ragione — o `None` se il tick non
    è in pausa.

    Il tick non si spegne più commentando la sua riga nel crontab: cron lancia
    dalla tabella che ha caricato, e fra la modifica e il `RELOAD` il tick
    lanciava con la riga vecchia (difetto 69 di PBI-102). Il file lo legge il
    tick stesso a ogni passaggio, e non c'è una seconda fonte da aspettare.

    Un file che c'è ma non si legge è pausa lo stesso: chi l'ha creato voleva
    il tick fermo, e la riga lo dice al posto della ragione.
    """
    file = file_di_pausa()
    if not file.exists():
        return None
    try:
        return file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as illeggibile:
        return f"{file} c'è ma non si legge — {illeggibile}"


def fermo_in_pausa(repo: Path) -> bool:
    """Il tick è in pausa? Se sì lo dice a schermo e in `coda.log`, con la riga
    del file: chi legge il log deve vedere perché non è successo niente.
    `smista()` lo chiede due volte, prima di `decidi()` e prima di `lancia()`."""
    if (motivo := pausa()) is None:
        return False
    riga = f"in pausa: {motivo}"
    print(riga)
    scrivi_nel_log(repo, riga)
    return True


def main(argv: list[str] | None = None) -> int:
    """Un tick: legge `asdlc.toml`, poi guarda, decide una cosa, la fa, e finisce.

    La configurazione si legge qui e non all'import (PBI-382): un modulo
    importato non deve leggere niente.
    """
    try:
        # Fuori da un progetto ci si ferma qui, prima del lucchetto e di ogni
        # scrittura: il runner non ha niente da fare, e lo dice.
        radice = asdlc_config.radice(Path.cwd())
        configura(asdlc_config.carica(radice))
    except asdlc_config.ErroreDiConfigurazione as guasto:
        sys.exit(f"asdlc_coda: {guasto}")
    global REPO
    REPO = radice
    return smista(argv)


def smista(argv: list[str] | None = None) -> int:
    """`main()` a configurazione già letta: i test la chiamano da qui, coi nomi
    di modulo che hanno sostituito."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", type=Path, default=REPO,
                    help="il checkout da cui si legge la coda e si interroga origin")
    ap.add_argument("--worktree", type=Path, default=WORKTREE_DEL_RUNNER,
                    help="l'albero in cui gira il runner")
    ap.add_argument("--dry-run", action="store_true",
                    help="stampa la decisione senza eseguirla")
    a = ap.parse_args(argv)

    if a.repo.resolve() == a.worktree.resolve():
        print(f"Non parto: --repo e --worktree sono lo stesso albero ({a.repo}).\n"
              "Il tick non gira dentro l'albero che comanda: quello cambia ramo a ogni "
              "giro, e il pre-flight lo sposterebbe sotto i piedi al processo che lo sta "
              "eseguendo. Lancialo dal checkout principale, con --worktree sull'albero "
              "del runner.")
        return 2

    # Il lucchetto del tick prima della prima lettura della pausa, tenuto fino
    # alla fine: anche per il pre-flight, l'avvio del runner e l'attesa del
    # distacco. Senza, `asdlc-chiudi-giro` trovava libero il lucchetto del runner
    # e faceva i suoi passi mentre questo tick lanciava (difetto 70 di PBI-102).
    tenuto = lucchetto_del_tick(a.repo)
    if tenuto is None:
        riga = ("occupato: il lucchetto del tick è tenuto — un altro tick o "
                "asdlc-chiudi-giro")
        print(riga)
        scrivi_nel_log(a.repo, riga)
        return 0
    with tenuto:
        return passaggio(a)


def passaggio(a: argparse.Namespace) -> int:
    """Il tick col suo lucchetto in mano: la pausa, la decisione, il lancio."""
    # La pausa prima di ogni domanda al mondo, e prima anche del `--dry-run`, che
    # deve dire ciò che un tick vero farebbe: niente (PBI-385, decisione 5).
    if fermo_in_pausa(a.repo):
        return 0

    decisione = decidi(a.repo, a.worktree)
    riga = racconta(decisione)
    # L'avviso accompagna il lancio e non lo trattiene: la sezione ❓ di un PBI
    # in coda è quasi sempre un protocollo di rifinitura già deciso, e chi lo
    # ha messo in coda ha già dichiarato chiuse le sue domande. Qui si osserva
    # e si segnala (`ADR-0008`).
    if isinstance(decisione, Lancia) and (avviso := avviso_domande(a.repo, decisione.pbi)):
        riga += f" — avviso, il PBI ha una sezione di domande: «{avviso}»"
    print(riga)
    scrivi_nel_log(a.repo, riga)
    # Le domande al mondo le ha già fatte `decidi()`, ed è giusto così: senza
    # `gh` non ci sarebbe nessuna decisione da leggere. Qui si ferma ciò che
    # **cambia** lo stato — il pre-flight, che sposta il worktree su un altro
    # ramo, e il runner.
    if isinstance(decisione, Lancia) and not a.dry_run:
        # L'ambiente prima del pre-flight: senza il runner o senza ciò che i gate
        # lanciano, il giro si fermerebbe dopo aver spostato il worktree. Tutte le
        # mancanze in una riga, perché il log ne ha una per tick.
        if mancanze := mancanze_dell_ambiente(a.worktree):
            prefisso = "ambiente mancante: "
            riga = prefisso + "; ".join(m.removeprefix(prefisso) for m in mancanze)
            print(riga)
            scrivi_nel_log(a.repo, riga)
            return 1
        # La seconda lettura, subito prima del lancio: la pausa può essere nata
        # mentre questo tick decideva, e chi l'ha creata sta chiudendo un giro.
        if fermo_in_pausa(a.repo):
            return 0
        try:
            lancia(decisione.pbi, a.worktree)
        except Guasto as guasto:
            # Da `cron` un'eccezione non la legge nessuno: nel log resterebbe la
            # riga che dice «lancia», cioè il contrario di quel che è successo.
            print(guasto)
            scrivi_nel_log(a.repo, f"non lanciato: {guasto}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
