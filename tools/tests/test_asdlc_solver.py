"""Il ruolo Solver nel server dell'esito (`backlog/PBI-507`, `ADR-0030`, R1-R3).

Il Solver è il terzo ruolo accanto a Builder e Critic: smista un giro fermato con uno
di tre strumenti, che il server dell'esito valida (`ADR-0027`).
"""

import importlib
from pathlib import Path

esito = importlib.import_module("asdlc.esito")

STRUMENTI_DEL_SOLVER = {"risolvi", "segnala_limite_runner", "chiedi_a_francesco"}


def nomi(ruolo):
    return {s["name"] for s in esito.strumenti(ruolo)}


def test_il_solver_ha_i_suoi_tre_strumenti_e_gli_altri_ruoli_no():
    """R1: gli strumenti del Solver sono suoi e di nessun altro ruolo."""
    assert STRUMENTI_DEL_SOLVER <= nomi("solver")
    assert not STRUMENTI_DEL_SOLVER & nomi("builder")
    assert not STRUMENTI_DEL_SOLVER & nomi("critic")
