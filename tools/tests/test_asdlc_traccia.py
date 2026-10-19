"""La traccia completa delle sessioni degli agenti e il controllo R4 (`backlog/PBI-511`).

Il runner lega ogni invocazione alla sua sessione di Claude Code con `--session-id`, ne copia
la traccia in `runs/` e la legge come fatto: mai il testo di un modello (`ADR-0027`).
"""

import importlib
import json
import re
from pathlib import Path

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


def sessione_finta(righe):
    """Un `jsonl` di sessione come lo scrive Claude Code: prompt, una risposta con
    `thinking`, una chiamata a strumento, il suo risultato, la risposta finale."""
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in righe)


RIGHE = [
    {"type": "user", "message": {"role": "user", "content": "il prompt"}},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "ragiono"},
        {"type": "tool_use", "id": "t1", "name": "Read",
         "input": {"file_path": "/x/asdlc.toml"}}]}},
    {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "contenuto"}]}},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "fatto"}]}},
]


def con_la_sessione(monkeypatch, tmp_path, righe):
    """`esegui` che, come `claude`, scrive la sessione sotto la cartella di Claude Code
    (finta) col nome dell'uuid ricevuto; `righe=None` è una sessione che non c'è."""
    cartella = tmp_path / "claude" / "progetto"
    cartella.mkdir(parents=True)
    monkeypatch.setattr(runner, "cartella_delle_sessioni", lambda: cartella, raising=False)
    interno = agente_finto({})

    def _esegui(cmd, cwd, timeout=7200, **k):
        if righe is not None:
            (cartella / f"{cmd[cmd.index('--session-id') + 1]}.jsonl").write_text(
                sessione_finta(righe), encoding="utf-8")
        return interno(cmd, cwd, timeout, **k)

    monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
    monkeypatch.setattr(runner, "esegui", _esegui)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("x", encoding="utf-8")
    return runner.invoca_agente("solver", runner.comando_del_solver(), prompt,
                                tmp_path / "esito.json")


def test_la_traccia_della_sessione_si_copia_intera_in_runs(monkeypatch, tmp_path):
    invocazione = con_la_sessione(monkeypatch, tmp_path, RIGHE)

    copia = Path(invocazione.registro["traccia"])
    assert copia.parent == tmp_path
    assert copia.read_text(encoding="utf-8") == sessione_finta(RIGHE)


def test_se_la_sessione_manca_il_rapporto_lo_dice_e_il_giro_non_si_ferma(monkeypatch, tmp_path):
    invocazione = con_la_sessione(monkeypatch, tmp_path, None)

    assert invocazione.registro["traccia"] is None
    assert invocazione.registro["traccia_nota"].startswith("sessione non trovata")
    assert invocazione.codice == 0
