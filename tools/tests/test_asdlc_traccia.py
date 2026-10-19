"""La traccia completa delle sessioni degli agenti e il controllo R4 (`backlog/PBI-511`).

Il runner lega ogni invocazione alla sua sessione di Claude Code con `--session-id`, ne copia
la traccia in `runs/` e la legge come fatto: mai il testo di un modello (`ADR-0027`).
"""

import importlib
import re

from test_asdlc_runner import agente_finto

runner = importlib.import_module("asdlc.runner")

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def lancia(monkeypatch, tmp_path, ruolo, comando):
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
    agente = agente_finto({})
    monkeypatch.setattr(runner, "esegui", agente)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("x", encoding="utf-8")
    invocazione = runner.invoca_agente(ruolo, comando, prompt, tmp_path / "esito.json")
    return invocazione, agente.comandi[0]


def test_ogni_ruolo_riceve_un_session_id_e_il_registro_lo_riporta(monkeypatch, tmp_path):
    for ruolo, comando in (("builder", runner.BUILDER), ("critic", runner.CRITIC),
                           ("solver", runner.comando_del_solver())):
        invocazione, cmd = lancia(monkeypatch, tmp_path, ruolo, comando)

        dato = cmd[cmd.index("--session-id") + 1]
        assert UUID.match(dato), ruolo
        assert invocazione.registro["sessione"] == dato, ruolo
