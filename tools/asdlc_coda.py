#!/usr/bin/env python3
"""Il tick della coda: guarda lo stato, decide **una** cosa e finisce.

Fra il merge di un PBI e il lancio del successivo passano ore in cui non succede
niente, e il tempo morto non è il comando da digitare: è l'attesa che qualcuno
torni al terminale. Questo è il processo breve che `cron` chiama a intervalli
regolari per togliere quell'attesa (`backlog/PBI-350`).

Quello che **non** fa, ed è la riga che lo tiene dentro i suoi confini: non
mergia — il merge è il terzo gate, il confine dell'accountability, e non è
delegabile (`asdlc_runner.py:17`) — e non decide cosa entra in coda. La coda la
scrive Francesco a mano in `backlog/CODA.md`; il tick è un esecutore d'ordini già
dati, e non ne inventa nessuno.

La decisione è separata dagli effetti: `prossimo()` è una funzione pura, ed è la
sola cosa che i test guardano.
"""
from __future__ import annotations

import fcntl
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Dove il runner tiene il lucchetto del suo albero (`lucchetto()`, `NOME_LUCCHETTO`).
LUCCHETTO = Path("runs") / ".runner.lock"
# La cartella dei processi. È una costante e non un argomento perché la
# attraversano tre chiamate di fila, e sotto i test si sostituisce qui.
PROC = Path("/proc")


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
    """Il giro di questo PBI c'è già stato e si è fermato: tocca a un umano."""

    pbi: str


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
RE_PBI = re.compile(r"^-\s+(PBI-\d+)\s*$")
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


# Il titolo che `apri_pr()` costruisce, e il ramo che `crea_branch()` chiede a
# `nome_libero()`: `pbi/pbi-338`, o `pbi/pbi-338-giro2` se il primo giro c'era già.
RE_TITOLO_PR = re.compile(r"^\s*(PBI-\d+)\s*:")
RE_RAMO_PBI = re.compile(r"refs/heads/pbi/pbi-(\d+)")


def pbi_mergiati(repo: Path) -> set[str]:
    """I PBI già in `main`, letti dai **titoli** delle PR mergiate.

    Dal titolo e non dal nome del ramo: lo squash il ramo lo perde, e un PBI
    entrato in `main` con uno squash resterebbe per sempre da lanciare.
    """
    _, uscita = esegui(
        ["gh", "pr", "list", "--state", "merged", "--limit", "200", "--json", "title"],
        repo,
    )
    return {
        trovato.group(1)
        for pr in json.loads(uscita)
        if (trovato := RE_TITOLO_PR.match(pr.get("title", "")))
    }


def pbi_con_ramo(repo: Path) -> set[str]:
    """I PBI per cui `origin` ha già un ramo, col suffisso di un secondo giro o senza.

    Si chiede al remoto perché è l'unico posto in cui un giro fallito lascia
    traccia per tutti, ed è la stessa lettura di `rami_su_origin()`.
    """
    _, uscita = esegui(
        ["git", "-C", str(repo), "ls-remote", "--heads", "origin", "refs/heads/pbi/*"],
        repo,
    )
    return {f"PBI-{numero}" for numero in RE_RAMO_PBI.findall(uscita)}


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
    return runner_vivo(worktree)


def runner_vivo(worktree: Path) -> bool:
    """Un processo del runner che lavora in quell'albero, lucchetto o no.

    È la rete sotto al lucchetto, e serve per il caso che è successo davvero:
    una sessione avviata a mano, che il lucchetto del runner non lo prende e
    nemmeno lo guarda. L'unico segnale comune ai due è **dove** lavorano, cioè
    `/proc/<pid>/cwd`, ed è la stessa lettura di `agenti_estranei()`.

    È un controllo Linux e non si scusa di esserlo: il tick gira sul PC di
    sviluppo. Dove `/proc` non c'è la cartella non si legge e resta il lucchetto,
    che è il controllo primario.
    """
    albero = worktree.resolve()
    try:
        cartelle = list(PROC.iterdir())
    except OSError:
        return False
    for cartella in cartelle:
        if not cartella.name.isdigit():
            continue
        try:
            dove = (cartella / "cwd").resolve()
            comando = (cartella / "cmdline").read_bytes()
        except OSError:
            continue  # un processo che finisce mentre lo leggiamo, o di un altro utente
        if dove != albero and albero not in dove.parents:
            continue
        if b"asdlc_runner" in comando:
            return True
    return False


def decidi(repo: Path, worktree: Path) -> Decisione:
    """La decisione di questo tick, sullo stato che il mondo racconta adesso.

    `repo` è il checkout principale, da cui si legge la coda e si interroga
    `origin`; `worktree` è l'albero in cui il runner lavora. Sono due percorsi
    diversi perché il tick non gira dentro l'albero che comanda: quello cambia
    ramo sotto i piedi a ogni giro, e un programma che leggesse il proprio
    codice da lì si riscriverebbe a metà tick.

    Il giro in corso si guarda **prima** di ogni domanda al mondo: davanti a un
    albero occupato non c'è risposta di `gh` che cambi la decisione.
    """
    if giro_in_corso(worktree):
        return Occupato()
    voci = leggi_voci((repo / "backlog" / "CODA.md").read_text(encoding="utf-8"))
    return prossimo(voci, pbi_mergiati(repo), pbi_con_ramo(repo), occupato=False)
