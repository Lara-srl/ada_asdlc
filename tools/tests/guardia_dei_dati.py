"""La guardia di fine suite su `tools/tests/dati/` (PBI-518).

Un test che scrive nel progetto di prova lascia sporco l'albero del repository,
e il controllo dell'albero pulito ferma il giro (causa `test-senza-isolamento`).
La guardia elenca i dati a inizio sessione e a fine sessione: se a fine
sessione c'è un file o una cartella che prima non c'era, la suite esce rossa e
li nomina. Non cancella niente (decisione 4): il file lo cancella o lo ignora
chi corregge il test che l'ha scritto.

È un plugin di pytest: `conftest.py` lo carica per tutta la suite, e un
`pytest` qualsiasi lo carica con `-p guardia_dei_dati`.
"""

import sys
from pathlib import Path

import pytest

DATI = Path(__file__).resolve().parent / "dati"

PRIMA = pytest.StashKey[set]()


def elenco(cartella: Path) -> set[Path]:
    """I file e le cartelle sotto `cartella`, letti dal disco e non da `git
    status` (decisione 3): anche quelli che git ignora, che sono proprio quelli
    che le righe di `.gitignore` del progetto di prova nascondevano."""
    return set(cartella.rglob("*"))


def nati(prima: set[Path], dopo: set[Path]) -> list[str]:
    """I percorsi di `dopo` che in `prima` non c'erano, in ordine."""
    return sorted(str(p) for p in dopo - prima)


def pytest_sessionstart(session):
    session.config.stash[PRIMA] = elenco(DATI)


def pytest_sessionfinish(session):
    prima = session.config.stash.get(PRIMA, None)
    if prima is None:
        return
    nuovi = nati(prima, elenco(DATI))
    if not nuovi:
        return
    righe = [f"Percorsi nuovi in {DATI} a fine suite ({len(nuovi)}): un test scrive "
             "fuori dalla sua cartella temporanea (PBI-518).",
             *(f"  {p}" for p in nuovi)]
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write("\n")
        reporter.write_sep("=", "guardia dei dati", red=True)
        for riga in righe:
            reporter.write_line(riga)
    else:
        print("\n".join(righe), file=sys.stderr)
    if session.exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
