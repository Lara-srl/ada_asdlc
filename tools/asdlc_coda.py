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

from dataclasses import dataclass


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


def prossimo(
    voci: list[Voce], mergiati: set[str], rami: set[str], occupato: bool
) -> Occupato | Barriera | Attende | Lancia | None:
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
    return None
