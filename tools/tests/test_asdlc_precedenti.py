"""Il vocabolario delle cause `runner-*` e il registro dei precedenti (`backlog/PBI-506`).

Due elenchi che il Solver legge (`specs/solver-e-rilascio/spec.md`, R3 e R12): le
cause `runner-*` in `backlog/README.md`, e le decisioni che fanno precedente in
`backlog/PRECEDENTI.md`. Sono documenti del progetto che ospita la suite, non del
progetto di prova: i test li leggono apposta (`progetto_ospite`).
"""

import importlib
import re
from pathlib import Path

import pytest

REPO = importlib.import_module("asdlc.config").radice(Path(__file__).resolve().parent)

SEZIONE_RUNNER = "Le cause `runner-*`"
RIGA_SLUG = re.compile(r"^\|\s*`([^`]+)`\s*\|")


def _readme():
    return (REPO / "backlog" / "README.md").read_text(encoding="utf-8")


def _slug_della_tabella(testo):
    """Gli slug (prima colonna) delle righe di una tabella Markdown."""
    return [m.group(1) for m in map(RIGA_SLUG.match, testo.splitlines()) if m]


def _sezione_runner(testo):
    """Il corpo della sezione «Le cause `runner-*`», fino al titolo successivo."""
    righe = testo.splitlines()
    inizio = next(
        (i for i, r in enumerate(righe)
         if r.startswith("#") and SEZIONE_RUNNER in r), None)
    assert inizio is not None, f"manca la sezione «{SEZIONE_RUNNER}» in backlog/README.md"
    corpo = []
    for r in righe[inizio + 1:]:
        if r.startswith("#"):
            break
        corpo.append(r)
    return "\n".join(corpo)


@pytest.mark.progetto_ospite
def test_la_tabella_runner_porta_solo_slug_runner_e_il_primo():
    """Criterio 1. Ogni riga della sezione ha uno slug `runner-*`, e c'è il primo."""
    slug = _slug_della_tabella(_sezione_runner(_readme()))

    assert "runner-non-legge-junit" in slug
    assert [s for s in slug if not s.startswith("runner-")] == []


@pytest.mark.progetto_ospite
def test_nessuno_slug_runner_e_anche_una_causa_di_progetto():
    """Criterio 2. La tabella generale è tutto il README fuori dalla sezione `runner-*`."""
    testo = _readme()
    sezione = _sezione_runner(testo)
    generali = _slug_della_tabella(testo.replace(sezione, ""))
    runner = _slug_della_tabella(sezione)

    assert generali, "la tabella generale delle cause non si trova: il confronto sarebbe vuoto"
    assert runner
    assert sorted(set(generali) & set(runner)) == []
