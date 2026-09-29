"""I test del runner ASDLC stanno in `tools/tests/`, fuori dall'applicazione
(`backlog/PBI-360`).

Due cose che il trasloco deve rendere vere, e che nessun altro test guarda:

- **Il gate `asdlc` esiste e gira fra gli altri.** Il gate `pytest` lancia
  `cd backend && pytest -q`: appena i test escono da lì, smette di eseguirli. Se
  `asdlc.toml` non li riprende con un gate suo, il giro si certifica verde su una
  suite che non gira più.
- **Nessuna connessione a un database.** `backend/tests/conftest.py` monta uno
  SQLite in memoria per ogni test, `autouse`; i test del runner non toccano un
  database e fuori da lì non devono pagarlo. La sonda li gira in un processo suo,
  con `sqlite3.dbapi2.connect` contato: è la porta da cui passa quella fixture —
  SQLAlchemy apre SQLite da `dbapi2`, non da `sqlite3.connect`.

Il runner si carica dal suo percorso in `tools/asdlc/` con un nome suo, e non
per nome come negli altri file di questa cartella: vedi sotto.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUI = Path(__file__).resolve()

# Un nome suo in `sys.modules`: `test_asdlc_runner.py` registra il runner come
# `asdlc.runner` e lo riconfigura nei suoi test, e questo modulo non glielo tocca.
_spec = importlib.util.spec_from_file_location(
    "asdlc_runner_del_gate", REPO / "tools" / "asdlc" / "runner.py"
)
runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner
_spec.loader.exec_module(runner)
# L'import non legge `asdlc.toml` (PBI-382): la configurazione è quella del
# repository di questo file.
runner.REPO = REPO
runner.configura(runner.asdlc_config.carica(REPO))


def test_gira_gate_esegue_cinque_comandi_e_il_quinto_e_la_suite_asdlc(monkeypatch):
    chiamati: list[tuple[list[str], Path]] = []
    monkeypatch.setattr(
        runner, "esegui",
        lambda cmd, cwd, timeout=0: chiamati.append((list(cmd), Path(cwd))) or (0, ""),
    )

    assert runner.gira_gate(set()) == []

    assert len(chiamati) == 5, [cmd for cmd, _ in chiamati]
    assert chiamati[4] == (["python3", "-m", "pytest", "-q", "tools/tests"], REPO / ".")


# Il processo figlio conta le connessioni SQLite intorno a un `pytest`
# di questa cartella, e le stampa **dopo** che pytest ha finito: la riga è sua,
# non si confonde con l'output dei test.
SONDA = """
import sqlite3, sqlite3.dbapi2, sys
import pytest

aperte = []
_connect = sqlite3.dbapi2.connect

def _contata(*a, **k):
    aperte.append(a[:1])
    return _connect(*a, **k)

sqlite3.connect = sqlite3.dbapi2.connect = _contata
esito = pytest.main(sys.argv[1:])
print(f"CONNESSIONI APERTE: {len(aperte)}")
sys.exit(esito)
"""


def test_i_test_di_tools_tests_non_aprono_connessioni_a_un_database():
    fatto = subprocess.run(
        [sys.executable, "-c", SONDA, "-q", "-p", "no:cacheprovider",
         str(QUI.parent), "-k", "not non_aprono_connessioni"],
        cwd=REPO, capture_output=True, text=True, timeout=600,
    )
    uscita = fatto.stdout + fatto.stderr

    assert "CONNESSIONI APERTE: 0" in uscita, uscita[-3000:]
    assert fatto.returncode == 0, uscita[-3000:]
    assert " passed" in uscita, uscita[-3000:]
