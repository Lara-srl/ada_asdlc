"""Le fixture comuni ai test di `tools/`.

Il runner si carica con `importlib` da `test_asdlc_runner.py` e si registra in
`sys.modules` come `asdlc_runner`: qui lo si cerca lì, al momento del test, senza
caricarne una seconda copia.
"""

import functools
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def log_dir_temporanea(tmp_path_factory, monkeypatch):
    """La `LOG_DIR` del runner in una cartella temporanea del test (PBI-370).

    I test che fanno girare `esegui_pbi` o `revisione_critica` con `esegui`
    sostituito scrivevano prompt, esiti e config MCP nella `runs/` vera, mescolati
    alle chiamate del runner: 124 file a ogni giro di `pytest tools/tests`. Una
    fixture `autouse` e non una correzione classe per classe, perché la classe di
    domani non se ne debba ricordare.

    Si sposta **ogni** costante del modulo che è un percorso sotto la `LOG_DIR`
    vera, non la sola `LOG_DIR`: `configura()` ne ricava altri, come `CSV_TEMPI`
    (decisione 2). E si rifà dopo ogni `configura()` chiamata dentro il test,
    perché riapplicare un `asdlc.toml` li ricalcola da `REPO`, cioè di nuovo
    sotto `runs/`.
    """
    runner = sys.modules.get("asdlc_runner")
    if runner is None:
        return
    vera = runner.LOG_DIR
    # Una cartella sua e non `tmp_path`: i test che guardano cosa c'è in
    # `tmp_path` non devono trovarci una `runs/` che non hanno creato.
    finta = tmp_path_factory.mktemp("runs")

    def sposta() -> None:
        for nome, valore in list(vars(runner).items()):
            if isinstance(valore, Path) and valore.is_relative_to(vera):
                monkeypatch.setattr(runner, nome, finta / valore.relative_to(vera))

    configura = runner.configura

    @functools.wraps(configura)
    def configura_e_sposta(cfg):
        configura(cfg)
        sposta()

    monkeypatch.setattr(runner, "configura", configura_e_sposta)
    sposta()
