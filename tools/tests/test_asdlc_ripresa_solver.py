"""Dopo `risolto` il runner rilancia il Builder (`backlog/PBI-517`).

Il Builder si ferma con una domanda (`fermati`), il Solver risponde `risolto`, e il
Builder riprende dentro lo stesso giro con la risposta davanti. Gli agenti sono finti
(`esegui()` sostituito) e nessun test lancia `claude`; la cartella delle sessioni di
Claude Code è sempre una cartella del test, mai `~/.claude`.
"""

import importlib
import json
from pathlib import Path

import pytest
from test_asdlc_runner import FATTO, elenco_backlog, fermati, ruolo_ed_esito

runner = importlib.import_module("asdlc.runner")

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"
runner.REPO = PROGETTO
runner.configura(runner.asdlc_config.carica(PROGETTO))

RISOLTO = {"esito": "risolto", "risposta": "usa la funzione che c'è già",
           "evidenza": "specs/solver-e-rilascio/spec.md"}


def git_pulito(*args: str) -> str:
    """Il `git` minimo di un giro: albero pulito, due commit, il ramo è `HEAD`."""
    if args[:2] == ("rev-list", "--count"):
        return "2"
    if args[:2] == ("ls-tree", "--name-only"):
        return elenco_backlog()
    return ""


def agente_con_stato(esiti: dict, sessioni: Path | None):
    """Un `esegui` che fa l'agente con un esito diverso a ogni chiamata dello stesso ruolo.

    `esiti` va da ruolo a lista: la chiamata n-esima di quel ruolo scrive l'n-esimo esito,
    e oltre la lista l'agente non chiama niente (`None` vale lo stesso). Con `sessioni`
    l'agente scrive lì il file della sessione col uuid di `--session-id`, come `claude`:
    senza, la traccia non si copia. I comandi ricevuti restano in `.comandi`."""
    comandi: list[list[str]] = []
    contati: dict[str, int] = {}

    def _esegui(cmd, cwd, timeout=7200, **k):
        comandi.append(cmd)
        ruolo, file_esito = ruolo_ed_esito(cmd)
        n = contati.get(ruolo, 0)
        contati[ruolo] = n + 1
        coda = esiti.get(ruolo, [])
        if file_esito is not None and n < len(coda) and coda[n] is not None:
            file_esito.write_text(json.dumps(coda[n], ensure_ascii=False), encoding="utf-8")
        if sessioni is not None and "--session-id" in cmd:
            (sessioni / f"{cmd[cmd.index('--session-id') + 1]}.jsonl").write_text(
                json.dumps({"type": "user", "message": {"role": "user", "content": "x"}}) + "\n",
                encoding="utf-8")
        return 0, ""

    _esegui.comandi = comandi
    return _esegui


@pytest.fixture
def giro(monkeypatch, tmp_path):
    """Un `esegui_pbi` con `LOG_DIR`, `git`, i gate, il Critic e la cartella delle sessioni
    finti. Rende la funzione che lancia il giro con gli esiti dati, e con la traccia delle
    sessioni o senza."""
    log = tmp_path / "runs"
    log.mkdir()
    sessioni = tmp_path / "claude" / "progetto"
    sessioni.mkdir(parents=True)
    monkeypatch.setattr(runner, "LOG_DIR", log)
    monkeypatch.setattr(runner, "cartella_delle_sessioni", lambda: sessioni)
    monkeypatch.setattr(runner, "git", git_pulito)
    monkeypatch.setattr(runner, "gira_gate", lambda attivi, base=None: [])
    monkeypatch.setattr(runner, "gate_del_rosso", lambda **k: [])
    critic: list[str] = []
    monkeypatch.setattr(runner, "revisione_critica",
                        lambda p, **_: critic.append("pass") or runner.Verdetto("pass", "", "ok"))

    def lancia(esiti, traccia=True):
        agente = agente_con_stato(esiti, sessioni if traccia else None)
        monkeypatch.setattr(runner, "esegui", agente)
        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)
        agente.critic = critic
        return esito, agente

    return lancia


def comandi_di(agente, ruolo):
    return [c for c in agente.comandi if ruolo_ed_esito(c)[0] == ruolo]


def test_dopo_risolto_il_builder_e_ripreso_e_il_giro_non_chiude_fermato(giro):
    """Criterio 1: il Builder chiama `fermati`, il Solver `risolto`, e il Builder parte
    una seconda volta nello stesso giro."""
    esito, agente = giro({"builder": [fermati("quale funzione?"), FATTO],
                          "solver": [RISOLTO]})

    assert len(comandi_di(agente, "builder")) == 2
    assert esito.stato != "fermato"


def test_la_ripresa_continua_la_sessione_dell_ultima_invocazione_del_builder(giro, monkeypatch):
    """Criterio 2: `--resume` con la sessione del Builder che ha chiamato `fermati`, e non
    `-c`, che continuerebbe l'ultima sessione dell'albero (quella del Solver). Un gate rosso
    prima del `fermati` fa sì che l'ultima invocazione del Builder non sia la prima."""
    gate = iter([[("pytest", "1 failed")]])
    monkeypatch.setattr(runner, "gira_gate", lambda attivi, base=None: next(gate, []))

    esito, agente = giro({"builder": [FATTO, fermati("quale funzione?"), FATTO],
                          "solver": [RISOLTO]})

    builder = comandi_di(agente, "builder")
    assert len(builder) == 3
    ripresa = builder[2]
    sessioni = [i["sessione"] for i in esito.invocazioni if i["ruolo"] == "builder"]
    assert ripresa.count("--resume") == 1
    assert ripresa[ripresa.index("--resume") + 1] == sessioni[1]
    assert ripresa.count("--fork-session") == 1
    assert ripresa.count("--session-id") == 1
    assert ripresa[ripresa.index("--session-id") + 1] == sessioni[2]
    assert "-c" not in ripresa


def test_il_prompt_della_ripresa_porta_domanda_e_risposta_da_valutare(giro):
    """Criterio 3: il prompt della ripresa ha la domanda del Builder, la risposta del Solver
    con la sua evidenza nel blocco «da valutare», e le graffe della risposta restano com'erano
    (la risposta è un valore di `.format()`, non il template)."""
    risposta = {"esito": "risolto", "risposta": "scrivi {\"chiave\": {valore}} nel dict",
                "evidenza": "specs/solver-e-rilascio/spec.md"}

    giro({"builder": [fermati("che forma ha {la voce}?"), FATTO], "solver": [risposta]})

    prompt = sorted(runner.LOG_DIR.glob("*_builder_prompt.txt"))[1].read_text(encoding="utf-8")
    assert "che forma ha {la voce}?" in prompt
    da_valutare = prompt[prompt.index("da valutare"):]
    assert "scrivi {\"chiave\": {valore}} nel dict" in da_valutare
    assert "specs/solver-e-rilascio/spec.md" in da_valutare
    assert "riprendi da dove ti sei fermato, nella fase in cui sei" in prompt


def test_senza_traccia_la_ripresa_riparte_pulita_col_pbi_e_lo_avvisa(giro):
    """Criterio 4: con `traccia` `None` un `--resume` fallirebbe. La ripresa parte da una
    sessione nuova, senza `--resume` né `-c`, e il prompt porta il PBI oltre a domanda e
    risposta; l'avviso sta nella nota del rapporto (`ADR-0008`)."""
    esito, agente = giro({"builder": [fermati("quale funzione?"), FATTO],
                          "solver": [RISOLTO]}, traccia=False)

    ripresa = comandi_di(agente, "builder")[1]
    assert "--resume" not in ripresa
    assert "-c" not in ripresa
    prompt = sorted(runner.LOG_DIR.glob("*_builder_prompt.txt"))[1].read_text(encoding="utf-8")
    assert "backlog/PBI-102-soglia-di-revisione-del-runner.md" in prompt
    assert "quale funzione?" in prompt
    assert RISOLTO["risposta"] in prompt
    rapporto = json.loads(runner.chiudi_rapporto("giro", [esito]).read_text(encoding="utf-8"))
    assert "avviso: la ripresa dopo risolto riparte da una sessione nuova" in (
        rapporto["esiti"][0]["nota"])
