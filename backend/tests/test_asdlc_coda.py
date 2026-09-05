"""Il tick della coda dei PBI (`backlog/PBI-350`).

Qui si guarda la **decisione**, non l'effetto: `prossimo()` è una funzione pura —
voci dentro, un esito fuori — e nessuno di questi test avvia un giro. Un test che
lancia il runner non è un test, è una notte.

`tools/` non è un pacchetto installato e non deve diventarlo per un test: si
carica il modulo dal suo percorso, come fa `test_importa_storico.py`.
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("asdlc_coda", REPO / "tools" / "asdlc_coda.py")
coda = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = coda
_spec.loader.exec_module(coda)


def test_un_giro_in_corso_rende_occupato_senza_guardare_la_coda():
    """La testa sarebbe da lanciare, e non si lancia lo stesso.

    Un albero, un agente: il 24→25/08 due agenti sullo stesso worktree sono
    costati un PBI intero, e qui il secondo lo avvierebbe `cron`, che non guarda
    lo schermo.
    """
    decisione = coda.prossimo(
        [coda.VocePbi("PBI-337")], mergiati=set(), rami=set(), occupato=True
    )

    assert decisione == coda.Occupato()
