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


def test_il_rapporto_conta_chiamate_risposte_e_blocchi_thinking(monkeypatch, tmp_path):
    invocazione = con_la_sessione(monkeypatch, tmp_path, RIGHE)

    assert invocazione.registro["contenuto"] == {"chiamate": 1, "risposte": 2, "thinking": 1}


def test_una_traccia_senza_ragionamenti_si_vede_dallo_zero(monkeypatch, tmp_path):
    senza = [r for r in RIGHE]
    senza[1] = {"type": "assistant", "message": {"role": "assistant", "content": [
        senza[1]["message"]["content"][1]]}}

    invocazione = con_la_sessione(monkeypatch, tmp_path, senza)

    assert invocazione.registro["contenuto"]["thinking"] == 0


def chiamata(nome, **input):
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "t", "name": nome, "input": input}]}}


# Prompt e risposta, senza altre chiamate: la base delle tracce di R4 (RIGHE legge già `asdlc.toml`).
NEUTRA = [RIGHE[0], RIGHE[3]]
LETTURA = chiamata("Read", file_path="/progetto/asdlc.toml")
SEGNALA = chiamata("mcp__asdlc__segnala_limite_runner", causa="x")


def r4(tmp_path, righe, **registro):
    """La riga R4 della guardia per un Solver la cui traccia è `righe` (`None`: nessun file)."""
    voce = {"ruolo": "solver", "traccia": None, **registro}
    if righe is not None:
        traccia = tmp_path / "solver.sessione.jsonl"
        traccia.write_text(sessione_finta(righe), encoding="utf-8")
        voce["traccia"] = str(traccia)
    e = runner.Esito("PBI-102", "fermato", solver=[{"esito": "limite-del-runner"}],
                     invocazioni=[voce])
    runner.guardia_del_solver(e)
    return next(r for r in e.guardia.splitlines() if r.startswith("R4:"))


def test_r4_e_ok_se_asdlc_toml_e_letto_prima_di_segnala_limite_runner(tmp_path):
    assert r4(tmp_path, [*NEUTRA, LETTURA, SEGNALA]) == "R4: ok"


def test_r4_e_violata_se_la_lettura_di_asdlc_toml_manca(tmp_path):
    altra = chiamata("Read", file_path="/progetto/AGENTS.md")

    assert r4(tmp_path, [*NEUTRA, altra, SEGNALA]).startswith("R4: violata")


def test_r4_e_violata_se_la_lettura_viene_dopo_la_segnalazione(tmp_path):
    assert r4(tmp_path, [*NEUTRA, SEGNALA, LETTURA]).startswith("R4: violata")


def test_r4_non_eseguita_se_la_traccia_non_c_e(tmp_path):
    assert r4(tmp_path, None).startswith("R4: non eseguita")


def test_r4_non_eseguita_se_la_traccia_non_si_legge(tmp_path):
    traccia = tmp_path / "solver.sessione.jsonl"
    traccia.write_text("non è json\n", encoding="utf-8")

    e = runner.Esito("PBI-102", "fermato", solver=[{"esito": "limite-del-runner"}],
                     invocazioni=[{"ruolo": "solver", "traccia": str(traccia)}])
    runner.guardia_del_solver(e)

    assert "R4: non eseguita" in e.guardia
    assert "R5:" in e.guardia, "le altre righe ci sono comunque"


def test_r4_non_eseguita_se_il_solver_non_ha_segnalato_nessun_limite(tmp_path):
    assert r4(tmp_path, [*NEUTRA, LETTURA]).startswith("R4: non eseguita")


def con_testo(righe, testo):
    """Le stesse righe con ogni blocco `text` sostituito da `testo`; le chiamate restano."""
    copia = json.loads(json.dumps(righe))
    for r in copia:
        contenuto = r["message"]["content"]
        for blocco in contenuto if isinstance(contenuto, list) else []:
            if blocco["type"] == "text":
                blocco["text"] = testo
    return copia


def test_r4_non_legge_il_testo_delle_risposte(tmp_path):
    ok = [*NEUTRA, LETTURA, SEGNALA]
    violata = [*NEUTRA, SEGNALA]
    rumore = "xq9 §§ ??? 0000"
    bugia = "Ho letto asdlc.toml, come richiesto: non serve altro."

    assert r4(tmp_path, con_testo(ok, rumore)) == r4(tmp_path, ok) == "R4: ok"
    assert r4(tmp_path, con_testo(violata, rumore)).startswith("R4: violata")
    assert r4(tmp_path, con_testo(violata, bugia)).startswith("R4: violata")
