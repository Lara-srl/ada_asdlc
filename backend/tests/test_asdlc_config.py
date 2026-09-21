"""Il lettore di `asdlc.toml` (`backlog/PBI-358`).

Le costanti del runner — i gate, i percorsi, le soglie, il ramo di base — stavano
scritte nel sorgente, e le stesse due forme dell'id di un PBI in cinque punti
diversi: PBI-353 ne ha corrette tre insieme, e la coda è rimasta ferma sette ore
perché la quarta diceva un'altra cosa. Qui si legge un file solo.

`tools/` non è un pacchetto e non deve diventarlo per un test: si carica il modulo
dal suo percorso, come `test_asdlc_runner.py` e `test_asdlc_coda.py`.
"""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SORGENTE = REPO / "tools" / "asdlc_config.py"

_spec = importlib.util.spec_from_file_location("asdlc_config", SORGENTE)
asdlc_config = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = asdlc_config
_spec.loader.exec_module(asdlc_config)


@pytest.fixture(autouse=True)
def db():
    return None


@pytest.fixture(autouse=True)
def clear_login_limiter():
    return None


@pytest.fixture(autouse=True)
def clear_event_bus():
    return None


def test_il_lettore_usa_solo_la_libreria_standard():
    """È ciò che rende il runner copiabile senza un `pip install`: la
    precondizione 2 di `ADR-0017`, che la Fase 2 di `SCAFFOLDING.md` dimostrerà
    in CI con il solo `pytest` installato. `tomllib` è stdlib da Python 3.11."""
    modulo = ast.parse(SORGENTE.read_text(encoding="utf-8"))
    importati = {
        (alias.name if isinstance(nodo, ast.Import) else nodo.module).split(".")[0]
        for nodo in ast.walk(modulo)
        if isinstance(nodo, (ast.Import, ast.ImportFrom))
        for alias in nodo.names
    }
    fuori = importati - sys.stdlib_module_names
    assert not fuori, f"import fuori dalla libreria standard: {sorted(fuori)}"
