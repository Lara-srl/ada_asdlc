"""Il server dell'esito (`backlog/PBI-366`, `ADR-0027`).

Il runner ricava gli esiti degli agenti dal loro testo libero, e ogni forma nuova
che un modello ha scritto è costata una regola e un test: la citazione, il
grassetto, la domanda vuota, il `PASS` citato dentro un `NON PRONTO` (difetti 32,
34, 35 e 36 di `PBI-102`). Qui nasce il canale strutturato: un server MCP su stdio
con due strumenti, `fatto` e `fermati`, che scrive l'esito in un file nominato dal
runner. Il runner non lo usa ancora: lo collega `PBI-367`.

I test parlano col server come la CLI: un processo vero, JSON-RPC su righe da
stdin a stdout. Il modulo non si importa, così un file che non c'è è un'asserzione
che fallisce e non un errore di raccolta.
"""

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SORGENTE = REPO / "tools" / "asdlc_esito.py"


@pytest.fixture(autouse=True)
def db():
    return None


@pytest.fixture(autouse=True)
def clear_login_limiter():
    return None


@pytest.fixture(autouse=True)
def clear_event_bus():
    return None


def test_il_server_esiste_e_usa_solo_la_libreria_standard():
    """Il server si copia col runner in un altro progetto (`ADR-0017`) e la CLI
    lo lancia con il `python3` di sistema: niente `pip install` (decisione 5)."""
    assert SORGENTE.is_file(), f"{SORGENTE.relative_to(REPO)} non esiste"
    modulo = ast.parse(SORGENTE.read_text(encoding="utf-8"))
    importati = {
        (alias.name if isinstance(nodo, ast.Import) else nodo.module).split(".")[0]
        for nodo in ast.walk(modulo)
        if isinstance(nodo, (ast.Import, ast.ImportFrom))
        for alias in nodo.names
    }
    fuori = importati - sys.stdlib_module_names
    assert not fuori, f"import fuori dalla libreria standard: {sorted(fuori)}"
