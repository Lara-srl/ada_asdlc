"""La guardia di fine suite su `tools/tests/dati/` (PBI-518)."""

import subprocess
import sys
import uuid
from pathlib import Path

import guardia_dei_dati

TESTS = Path(__file__).resolve().parent


def test_la_guardia_nomina_il_file_nato_nei_dati_anche_se_ignorato():
    """Criterio 2: il confronto fra l'elenco di prima e quello di dopo nomina il
    file nuovo, anche quando git lo ignora — `--*.json` in
    `dati/progetto/.gitignore`, una delle toppe che nascondevano il difetto — e
    due elenchi uguali non danno niente."""
    prima = guardia_dei_dati.elenco(guardia_dei_dati.DATI)
    nato = guardia_dei_dati.DATI / "progetto" / f"--guardia-{uuid.uuid4()}.json"
    try:
        nato.write_text("{}", encoding="utf-8")
        dopo = guardia_dei_dati.elenco(guardia_dei_dati.DATI)

        assert any(nato.name in riga for riga in guardia_dei_dati.nati(prima, dopo))
        assert guardia_dei_dati.nati(dopo, dopo) == []
    finally:
        nato.unlink(missing_ok=True)


def test_la_suite_esce_rossa_se_un_test_sporca_i_dati(tmp_path):
    """Criterio 3: un `pytest` con la guardia caricata (`-p`) e un test che scrive
    un file in `tools/tests/dati/` esce con un codice diverso da 0, e nomina il
    file. Il test sporco sta in `tmp_path`; il file che lascia nei dati lo
    cancella questo test, perché la guardia non cancella niente (decisione 4)."""
    sporco = guardia_dei_dati.DATI / f"sporco-{uuid.uuid4()}.txt"
    (tmp_path / "test_sporco.py").write_text(
        "from pathlib import Path\n\n\n"
        "def test_sporca():\n"
        f"    Path({str(sporco)!r}).write_text('x', encoding='utf-8')\n",
        encoding="utf-8")
    try:
        # La cwd è questa cartella perché `-p guardia_dei_dati` la trovi:
        # `python -m` mette la cwd sul `sys.path`.
        uscita = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "guardia_dei_dati",
             "-p", "no:cacheprovider", "--rootdir", str(tmp_path),
             str(tmp_path / "test_sporco.py")],
            cwd=TESTS, capture_output=True, text=True, timeout=120)
    finally:
        sporco.unlink(missing_ok=True)

    assert uscita.returncode != 0, uscita.stdout + uscita.stderr
    assert sporco.name in uscita.stdout + uscita.stderr
