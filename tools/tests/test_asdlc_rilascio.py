"""Il rilascio a tick (`backlog/PBI-509`, `specs/solver-e-rilascio/spec.md` R5-R11).

Due metà che si provano separate: il tick di `asdlc` che mette il tag dopo il merge di
un PBI (R8, R9), e il tick del progetto che propone il pin e toglie la pausa (R10,
R11). `gh` è sostituito da un finto; nessun test usa la rete.

Il modulo si carica per nome, `asdlc.coda`: `conftest.py` mette `tools/` sul
`sys.path` (PBI-383).
"""

import importlib
import tomllib
from pathlib import Path

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"

config = importlib.import_module("asdlc.config")


def configurazione(sezione: str = ""):
    """La configurazione del progetto di prova con sopra la sezione data."""
    testo = (PROGETTO / "asdlc.toml").read_text(encoding="utf-8") + "\n" + sezione
    return config.interpreta(tomllib.loads(testo), "asdlc.toml")


def test_la_sezione_rilascio_ha_i_default_fork_e_prefisso_v():
    """Senza `[rilascio]` il remote del fork è `fork` e il tag comincia per `v`."""
    rilascio = configurazione().rilascio

    assert (rilascio.remote_fork, rilascio.prefisso_tag) == ("fork", "v")


def test_la_sezione_rilascio_si_legge_dal_toml():
    rilascio = configurazione('[rilascio]\nremote_fork = "mio"\nprefisso_tag = "rel-"\n').rilascio

    assert (rilascio.remote_fork, rilascio.prefisso_tag) == ("mio", "rel-")
