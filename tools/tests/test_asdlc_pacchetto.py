"""Il runner è il pacchetto `asdlc`, in `tools/asdlc/` (PBI-383).

`conftest.py` mette `tools/` sul `sys.path`, e i moduli si trovano per nome:
`asdlc.runner`, `asdlc.coda`, `asdlc.config`, `asdlc.esito`.
"""

import importlib.util

import pytest


def trovato(nome: str):
    """La spec del modulo, o `None`. Senza il pacchetto `find_spec` di un
    sottomodulo alza invece di rispondere, e un errore non è un rosso."""
    try:
        return importlib.util.find_spec(nome)
    except ModuleNotFoundError:
        return None


@pytest.mark.parametrize("nome", ["asdlc.runner", "asdlc.coda", "asdlc.config", "asdlc.esito"])
def test_i_moduli_del_runner_si_trovano_nel_pacchetto_asdlc(nome):
    assert trovato(nome) is not None, nome
