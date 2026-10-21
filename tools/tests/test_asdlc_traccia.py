"""La traccia completa delle sessioni degli agenti e il controllo R4 (`backlog/PBI-511`).

Il runner lega ogni invocazione alla sua sessione di Claude Code con `--session-id`, ne copia
la traccia in `runs/` e la legge come fatto: mai il testo di un modello (`ADR-0027`).
"""

import importlib
import json
import re
from pathlib import Path

import pytest

from test_asdlc_runner import TestLaSessioneRuotaFraLeRevisioni, agente_finto, git_finto  # noqa: F401

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


def lanci_del_builder(monkeypatch):
    """I comandi del Builder in un giro con un gate rosso e poi verde (`PBI-513`): il primo
    lancio, il rilancio dopo il rosso con `-c`, e il primo della revisione dopo un NON PRONTO."""
    comandi: list[list[str]] = []
    TestLaSessioneRuotaFraLeRevisioni().scenario(monkeypatch, comandi)
    runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)
    return comandi


def test_il_rilancio_del_builder_porta_c_fork_session_e_session_id(monkeypatch, git_finto):
    rilancio = lanci_del_builder(monkeypatch)[1]

    assert "-c" in rilancio
    assert "--fork-session" in rilancio
    assert UUID.match(rilancio[rilancio.index("--session-id") + 1])


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


def test_r4_e_non_eseguita_se_la_traccia_non_si_legge_e_le_altre_righe_ci_sono(tmp_path):
    traccia = tmp_path / "solver.sessione.jsonl"
    traccia.write_text("questo non è JSON\n", encoding="utf-8")
    e = runner.Esito("PBI-102", "fermato", solver=[{"esito": "limite-del-runner"}],
                     invocazioni=[{"ruolo": "solver", "traccia": str(traccia)}])

    runner.guardia_del_solver(e)

    righe = e.guardia.splitlines()
    assert next(r for r in righe if r.startswith("R4:")).startswith("R4: non eseguita")
    assert [r[:2] for r in righe[1:]] == ["R4", "R5", "R6", "R7"]


def test_r4_e_non_eseguita_se_la_traccia_non_segnala_alcun_limite(tmp_path):
    assert r4(tmp_path, [*NEUTRA, LETTURA]).startswith("R4: non eseguita")


def con_testo(testo, righe):
    """Le stesse righe con ogni blocco `text` e `thinking` sostituito da `testo`."""
    copia = json.loads(json.dumps(righe))
    for riga in copia:
        contenuto = riga["message"]["content"]
        if isinstance(contenuto, list):
            for blocco in contenuto:
                for chiave in ("text", "thinking"):
                    if chiave in blocco:
                        blocco[chiave] = testo
    return copia


def test_r4_non_legge_il_testo_delle_risposte_ma_solo_le_chiamate(tmp_path):
    parlato = {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "ho letto asdlc.toml"}]}}
    corretta = [*NEUTRA, parlato, LETTURA, SEGNALA]
    scorretta = [*NEUTRA, parlato, SEGNALA]

    assert r4(tmp_path, con_testo("zxq kjh 123", corretta)) == "R4: ok"
    assert r4(tmp_path, con_testo("ho letto asdlc.toml", scorretta)).startswith("R4: violata")


def test_la_prima_invocazione_del_giro_non_porta_fork_session_ne_c(monkeypatch, git_finto):
    primo = lanci_del_builder(monkeypatch)[0]

    assert "--session-id" in primo
    assert "-c" not in primo
    assert "--fork-session" not in primo


@pytest.mark.parametrize("ruolo", ["builder", "critic"])
@pytest.mark.parametrize("continua", [[], ["-c"], ["--resume", "abc"]],
                         ids=["primo", "rilancio-c", "rilancio-resume"])
def test_session_id_con_c_o_resume_esce_sempre_con_fork_session(monkeypatch, tmp_path,
                                                                 ruolo, continua):
    comando = {"builder": runner.BUILDER, "critic": runner.CRITIC}[ruolo] + continua

    _, cmd = lancia(monkeypatch, tmp_path, ruolo, comando)

    assert "--session-id" in cmd
    if "-c" in cmd or "--resume" in cmd:
        assert "--fork-session" in cmd


# --- I token di ogni giro (`backlog/PBI-516`) ---------------------------------

TRACCIA_CON_TOKEN = Path(__file__).resolve().parent / "dati" / "traccia_con_token.jsonl"


def test_una_traccia_si_somma_e_la_riga_api_request_blob_si_salta():
    token, modello = runner.token_della_traccia(TRACCIA_CON_TOKEN)

    assert token == {"input": 9, "output": 600, "cache_creazione": 6000,
                     "cache_lettura": 60000}
    assert modello == "claude-opus-5-5"


def messaggio(id_messaggio, uso, modello="claude-opus-5-5", testo="x"):
    """Una riga `assistant` di Claude Code con il suo `message.usage`: `uso` sono i quattro
    contatori nell'ordine input, output, creazione e lettura della cache."""
    return {"type": "assistant", "message": {
        "id": id_messaggio, "role": "assistant", "model": modello,
        "content": [{"type": "text", "text": testo}],
        "usage": dict(zip(runner.CONTATORI_DEI_TOKEN.values(), uso))}}


def test_un_messaggio_ripetuto_su_due_righe_conta_una_volta_con_l_uso_dell_ultima(tmp_path):
    traccia = tmp_path / "s.sessione.jsonl"
    traccia.write_text(sessione_finta([messaggio("msg_1", (1, 10, 100, 1000), testo="a"),
                                       messaggio("msg_1", (2, 20, 200, 2000), testo="b")]),
                       encoding="utf-8")

    token, _ = runner.token_della_traccia(traccia)

    assert token == {"input": 2, "output": 20, "cache_creazione": 200, "cache_lettura": 2000}


def test_la_cronologia_del_fork_non_si_conta_due_volte_nel_token_dell_esito(tmp_path):
    prima = [messaggio("msg_1", (1, 10, 100, 1000)), messaggio("msg_2", (2, 20, 200, 2000))]
    fork = [*prima, messaggio("msg_3", (3, 30, 300, 3000)), messaggio("msg_4", (4, 40, 400, 4000))]
    invocazioni = []
    for nome, righe in (("primo", prima), ("rilancio", fork)):
        traccia = tmp_path / f"{nome}.sessione.jsonl"
        traccia.write_text(sessione_finta(righe), encoding="utf-8")
        invocazioni.append({"ruolo": "builder", "traccia": str(traccia)})

    assert runner.token_dell_esito(invocazioni) == [
        {"ruolo": "builder", "modello": "claude-opus-5-5", "input": 10, "output": 100,
         "cache_creazione": 1000, "cache_lettura": 10000}]
