"""L'ambiente dei test di `tools/` si verifica prima della raccolta (PBI-384).

I test del gate del rosso lanciano `pytest` e `git` in sottoprocessi, per nome.
Senza `pytest` sul `PATH` ognuno di loro moriva con un'uscita 127, e il difetto
60 di PBI-102 ne ha contati 19, un `GuastoDelGate` alla volta. `conftest.py` li
cerca in `pytest_sessionstart` e ferma la sessione con un messaggio solo.
"""

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = importlib.import_module("asdlc.config").radice(Path(__file__).resolve().parent)


def test_senza_pytest_sul_path_dei_sottoprocessi_la_suite_si_ferma_all_avvio_con_un_messaggio(
    tmp_path,
):
    """Il pacchetto, `conftest.py` e il progetto di prova, il cui `.venv` non c'è:
    il `PATH` ha solo `git`, e `pytest` si lancia come modulo dell'interprete, come fa il gate
    `asdlc`. Il test di prova passerebbe, se la suite partisse."""
    progetto = tmp_path / "progetto"
    shutil.copytree(REPO / "tools" / "asdlc", progetto / "tools" / "asdlc",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (progetto / "tools" / "tests").mkdir()
    shutil.copy(REPO / "tools" / "tests" / "conftest.py",
                progetto / "tools" / "tests" / "conftest.py")
    (progetto / "tools" / "tests" / "test_prova.py").write_text(
        "def test_prova():\n    assert True\n", encoding="utf-8")
    # Il progetto di prova, da cui `conftest.py` legge il venv (PBI-394).
    shutil.copytree(REPO / "tools" / "tests" / "dati" / "progetto",
                    progetto / "tools" / "tests" / "dati" / "progetto")
    solo_git = tmp_path / "bin"
    solo_git.mkdir()
    (solo_git / "git").symlink_to(shutil.which("git"))

    fatto = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tools/tests"],
        cwd=progetto, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PATH": str(solo_git)})

    uscita = fatto.stdout + fatto.stderr
    assert fatto.returncode != 0, uscita
    # `pytest.exit` scrive il suo messaggio una volta per flusso, su stdout e su
    # stderr: un messaggio solo è uno per flusso, non uno per test.
    assert fatto.stdout.count("ambiente mancante") == 1, uscita
    assert "ambiente mancante: `pytest` (cercato in `.venv/bin` e sul `PATH`)" in uscita
    assert "passed" not in uscita, "la raccolta non comincia"
