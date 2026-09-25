"""Le fixture comuni ai test di `tools/`.

Il runner si carica con `importlib` da `test_asdlc_runner.py` e si registra in
`sys.modules` come `asdlc_runner`: qui lo si cerca lì, al momento del test, senza
caricarne una seconda copia.
"""

import sys

import pytest


@pytest.fixture(autouse=True)
def log_dir_temporanea(tmp_path_factory, monkeypatch):
    """La `LOG_DIR` del runner in una cartella temporanea del test (PBI-370).

    I test che fanno girare `esegui_pbi` o `revisione_critica` con `esegui`
    sostituito scrivevano prompt, esiti e config MCP nella `runs/` vera, mescolati
    alle chiamate del runner: 124 file a ogni giro di `pytest tools/tests`. Una
    fixture `autouse` e non una correzione classe per classe, perché la classe di
    domani non se ne debba ricordare.
    """
    runner = sys.modules.get("asdlc_runner")
    if runner is None:
        return
    # Una cartella sua e non `tmp_path`: i test che guardano cosa c'è in
    # `tmp_path` non devono trovarci una `runs/` che non hanno creato.
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path_factory.mktemp("runs"))
