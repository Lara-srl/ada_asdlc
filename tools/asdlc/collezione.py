"""Il plugin di pytest che scrive la collezione in un dato (PBI-396, decisione 3).

Si carica con `-p asdlc.collezione --asdlc-collezione=<file>`, accanto a
`--collect-only`: a fine sessione scrive nel file un JSON con i nodeid raccolti
e i file che pytest non ha potuto raccogliere, di cui il runner legge i nomi
dall'AST (decisione 4).
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

# Ciò che la sessione raccoglie, in un processo che ne ha una sola: un rapporto di
# raccolta non porta la sua configurazione, e lo stato sta qui.
RACCOLTA: dict[str, list[str]] = {"nodi": [], "non_raccolti": []}


def pytest_addoption(parser):
    parser.addoption(OPZIONE, dest="asdlc_collezione", default=None,
                     help="il file JSON in cui scrivere la collezione (asdlc)")


def pytest_configure(config):
    RACCOLTA["nodi"], RACCOLTA["non_raccolti"] = [], []


def pytest_collectreport(report):
    """Un file che non si raccoglie — il RED che importa ciò che non c'è ancora
    — è un rapporto di raccolta fallito: il nodeid di un modulo, o di una
    classe dentro un modulo, comincia col percorso del file."""
    if not report.failed:
        return
    file = report.nodeid.split("::")[0]
    if file and file not in RACCOLTA["non_raccolti"]:
        RACCOLTA["non_raccolti"].append(file)


def pytest_collection_finish(session):
    RACCOLTA["nodi"] = [item.nodeid for item in session.items]


def pytest_sessionfinish(session):
    destinazione = session.config.getoption("asdlc_collezione")
    if not destinazione:
        return
    Path(destinazione).write_text(json.dumps(RACCOLTA), encoding="utf-8")
