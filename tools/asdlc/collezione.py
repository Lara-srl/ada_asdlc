"""Il plugin di pytest che scrive la collezione in un dato (PBI-396, decisione 3).

Si carica con `-p asdlc.collezione --asdlc-collezione=<file>`, accanto a
`--collect-only`: a fine sessione scrive nel file un JSON con i nodeid raccolti.
Il runner decide da lì quali test nascono in un commit, e non dall'output di
`-q`, dove un id con uno spazio o con un `::` nella parametrizzazione si
spezzerebbe nel punto sbagliato.

Il file si scrive in `pytest_sessionfinish` e non in `pytest_collection_finish`:
un percorso che non esiste ferma pytest prima della fine della raccolta, e il
runner deve trovare lo stesso una collezione, vuota.
"""

import json
from pathlib import Path

OPZIONE = "--asdlc-collezione"


def pytest_addoption(parser):
    parser.addoption(OPZIONE, dest="asdlc_collezione", default=None,
                     help="il file JSON in cui scrivere la collezione (asdlc)")


def pytest_configure(config):
    config._asdlc_nodi = []


def pytest_collection_finish(session):
    session.config._asdlc_nodi = [item.nodeid for item in session.items]


def pytest_sessionfinish(session):
    config = session.config
    destinazione = config.getoption("asdlc_collezione")
    if not destinazione:
        return
    Path(destinazione).write_text(
        json.dumps({"nodi": getattr(config, "_asdlc_nodi", [])}), encoding="utf-8")
