"""La PR a monte del Solver (`backlog/PBI-512`, `specs/solver-e-rilascio/spec.md` R5 e R6).

Quando il Solver segnala un limite del runner, il sistema apre il PBI a monte: un ramo su
un fork di `asdlc` e una PR da lì, mai una scrittura su `main`. `gh` e `git` sono
sostituiti da finti; nessun test usa la rete.
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


def test_senza_la_chiave_clone_la_sezione_rilascio_non_ha_un_clone():
    """Il clone di `asdlc` non si deduce da altro: senza chiave è `None`."""
    assert configurazione().rilascio.clone is None


def test_la_chiave_clone_della_sezione_rilascio_si_legge_dal_toml():
    rilascio = configurazione('[rilascio]\nclone = "/home/x/asdlc"\n').rilascio

    assert rilascio.clone == "/home/x/asdlc"
