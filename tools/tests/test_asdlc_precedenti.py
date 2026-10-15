"""Il vocabolario delle cause `runner-*` e il registro dei precedenti (`backlog/PBI-506`).

Due elenchi che il Solver legge (`specs/solver-e-rilascio/spec.md`, R3 e R12): le
cause `runner-*` in `backlog/README.md`, e le decisioni che fanno precedente in
`backlog/PRECEDENTI.md`. Sono documenti del progetto che ospita la suite, non del
progetto di prova: i test li leggono apposta (`progetto_ospite`).
"""

import importlib
import re
import subprocess
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


RIGA_REGISTRO = re.compile(
    r"^- (\d{4}-\d{2}-\d{2}) · ([^·]+) · ([^·]+) · (\S[^·]*)$")


def _righe_del_registro(testo):
    return [r for r in testo.splitlines() if r.startswith("- ")]


@pytest.mark.progetto_ospite
def test_il_registro_esiste_e_ogni_riga_ha_il_formato():
    """Criterio 3. `- AAAA-MM-GG · causa o ruolo · sentenza · riferimento`."""
    registro = REPO / "backlog" / "PRECEDENTI.md"

    assert registro.is_file(), "manca backlog/PRECEDENTI.md"
    righe = _righe_del_registro(registro.read_text(encoding="utf-8"))
    assert righe, "il registro non ha nessuna riga"
    storte = [r for r in righe if not RIGA_REGISTRO.match(r)]
    assert storte == [], f"righe fuori formato: {storte}"


def _righe_sparite(prima, dopo):
    """Le righe del registro non barrate che c'erano `prima` e `dopo` non ci sono più.

    Una riga barrata resta la stessa riga: `- ~~testo~~`, con la citazione della nuova dopo.
    """
    righe = _righe_del_registro(dopo)
    return [r for r in _righe_del_registro(prima)
            if not r.startswith("- ~~")
            and not any(d == r or d.startswith(f"- ~~{r[2:]}~~") for d in righe)]


def _git(cartella, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cartella, check=True, capture_output=True, text=True).stdout


def _registro_in_due_commit(tmp_path, prima, dopo):
    """Un repository di prova con il registro in due commit; ritorna i due testi come git li rende."""
    _git(tmp_path, "init", "-q")
    registro = tmp_path / "PRECEDENTI.md"
    registro.write_text(prima, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "--no-verify", "-m", "uno")
    registro.write_text(dopo, encoding="utf-8")
    _git(tmp_path, "commit", "-q", "--no-verify", "-am", "due")
    return _git(tmp_path, "show", "HEAD~1:PRECEDENTI.md"), _git(tmp_path, "show", "HEAD:PRECEDENTI.md")


RIGA_A = "- 2026-10-15 · runner-* · si corregge con un PBI · PBI-505"
RIGA_B = "- 2026-10-16 · solver · tetto di 3 giri · ADR-0030"


@pytest.mark.parametrize("dopo, sparite", [
    pytest.param(f"{RIGA_B}\n", [RIGA_A], id="riga-cancellata"),
    pytest.param(f"{RIGA_A}\n{RIGA_B}\n", [], id="riga-aggiunta"),
    pytest.param(f"- ~~{RIGA_A[2:]}~~ superata da ADR-0031\n", [], id="riga-barrata"),
])
def test_il_registro_e_solo_in_aggiunta_in_un_repository_di_prova(tmp_path, dopo, sparite):
    """Criterio 4. Una riga non barrata che sparisce fra due commit è un errore."""
    prima, dopo = _registro_in_due_commit(tmp_path, f"{RIGA_A}\n", dopo)

    assert _righe_sparite(prima, dopo) == sparite


@pytest.mark.progetto_ospite
def test_il_registro_non_perde_righe_rispetto_a_origin_main():
    """Criterio 4. Il registro del ramo contro quello di `origin/main`."""
    base = subprocess.run(
        ["git", "show", "origin/main:backlog/PRECEDENTI.md"],
        cwd=REPO, capture_output=True, text=True)
    attuale = (REPO / "backlog" / "PRECEDENTI.md").read_text(encoding="utf-8")

    # Prima del merge del PBI il file su origin/main non c'è: niente da perdere.
    assert _righe_sparite(base.stdout if base.returncode == 0 else "", attuale) == []
