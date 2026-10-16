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


def _perse(vecchio, nuovo):
    return importlib.import_module("asdlc.precedenti").righe_perse(vecchio, nuovo)


RIGA_A = "- 2026-10-15 · runner · un limite del runner si corregge con un PBI · PBI-505"
RIGA_B = "- 2026-10-16 · solver · la decisione B · ADR-0030"


def test_righe_perse_nessuna_riga_persa_se_il_nuovo_aggiunge():
    vecchio = f"# Registro\n\n{RIGA_A}\n"
    nuovo = f"# Registro\n\n{RIGA_A}\n{RIGA_B}\n"

    assert _perse(vecchio, nuovo) == []


def test_righe_perse_una_riga_cancellata_e_persa():
    vecchio = f"{RIGA_A}\n{RIGA_B}\n"
    nuovo = f"{RIGA_A}\n"

    assert _perse(vecchio, nuovo) == [RIGA_B]


def test_righe_perse_una_riga_riscritta_conta_come_persa():
    vecchio = f"{RIGA_A}\n"
    nuovo = f"{RIGA_A.replace('limite', 'difetto')}\n"

    assert _perse(vecchio, nuovo) == [RIGA_A]


def test_righe_perse_una_riga_barrata_che_sparisce_non_conta():
    barrata = "- ~~2026-10-14 · solver · decisione superata · PBI-1~~ → vedi sotto"
    vecchio = f"{barrata}\n{RIGA_A}\n"
    nuovo = f"{RIGA_A}\n"

    assert _perse(vecchio, nuovo) == []


@pytest.mark.progetto_ospite
def test_righe_perse_il_registro_aggiunto_in_un_secondo_commit_non_perde_righe(tmp_path):
    import subprocess

    def git(*args):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=tmp_path, check=True, capture_output=True, text=True).stdout

    registro = (REPO / "backlog" / "PRECEDENTI.md").read_text(encoding="utf-8")
    (tmp_path / "backlog").mkdir()
    file = tmp_path / "backlog" / "PRECEDENTI.md"
    git("init", "-q")
    file.write_text(registro, encoding="utf-8")
    git("add", ".")
    git("commit", "-q", "-m", "uno")
    file.write_text(registro + RIGA_B + "\n", encoding="utf-8")
    git("commit", "-q", "-am", "due")

    precedente = git("show", "HEAD~1:backlog/PRECEDENTI.md")
    attuale = file.read_text(encoding="utf-8")

    assert _perse(precedente, attuale) == []
    assert _perse(attuale, precedente) == [RIGA_B]
