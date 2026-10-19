"""La PR a monte del Solver (`backlog/PBI-512`, `specs/solver-e-rilascio/spec.md` R5 e R6).

Quando il Solver segnala un limite del runner, il sistema apre il PBI a monte: un ramo su
un fork di `asdlc` e una PR da lì, mai una scrittura su `main`. `gh` e `git` sono
sostituiti da finti; nessun test usa la rete.
"""

import dataclasses
import importlib
import json
import subprocess
import tomllib
from pathlib import Path

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"

config = importlib.import_module("asdlc.config")
esito = importlib.import_module("asdlc.esito")
runner = importlib.import_module("asdlc.runner")

TESTO_DEL_PBI = "# PBI-900: il limite\n\n## Direttiva\n\nCorreggi.\n\n**Scope**\n\n- `tools/asdlc/x.py`\n"


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


def albero_con_un_commit(tmp_path, monkeypatch):
    """Un repository git con un commit e la cartella d'esito: l'albero del giro."""
    monkeypatch.chdir(tmp_path)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["init", "-q"], check=True)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(git + ["add", "a.txt"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "uno"], check=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True,
                         text=True).stdout.strip()
    cartella = tmp_path / "esito"
    cartella.mkdir()
    return sha, cartella


def limite(sha, **altri):
    return {"causa": "runner-x", "comando": "pytest -q", "output": "0 test", "commit": sha,
            "pbi": TESTO_DEL_PBI, **altri}


def test_lo_strumento_del_limite_ha_il_campo_pbi_obbligatorio():
    """Decisione 1: il testo del PBI a monte lo scrive il Solver, in un campo suo."""
    schema = next(s for s in esito.strumenti("solver")
                  if s["name"] == "segnala_limite_runner")["inputSchema"]

    assert "pbi" in schema["properties"]
    assert "pbi" in schema["required"]


def test_senza_clone_la_pr_non_si_apre_e_lo_strumento_rende_un_errore(tmp_path, monkeypatch):
    """Decisione 3: senza `[rilascio].clone` (la variabile `ASDLC_CLONE` non c’è) il Solver
    riceve l'errore, nomina la chiave, e nessun esito si scrive."""
    sha, cartella = albero_con_un_commit(tmp_path, monkeypatch)
    monkeypatch.setenv("ASDLC_CAUSE", "runner-x")
    monkeypatch.delenv("ASDLC_CLONE", raising=False)

    risposta = esito.chiama("segnala_limite_runner", limite(sha), "solver",
                            str(cartella / "a.json"))

    assert risposta["isError"]
    assert "[rilascio].clone" in risposta["content"][0]["text"]
    assert not (cartella / "a.json").exists()


def test_con_il_clone_l_esito_porta_il_testo_del_pbi_e_senza_pbi_si_rifiuta(tmp_path, monkeypatch):
    sha, cartella = albero_con_un_commit(tmp_path, monkeypatch)
    monkeypatch.setenv("ASDLC_CAUSE", "runner-x")
    monkeypatch.setenv("ASDLC_CLONE", str(tmp_path))

    senza = esito.chiama("segnala_limite_runner", limite(sha, pbi="  "), "solver",
                         str(cartella / "a.json"))
    con = esito.chiama("segnala_limite_runner", limite(sha), "solver", str(cartella / "b.json"))

    assert senza["isError"] and not (cartella / "a.json").exists()
    assert not con["isError"], con
    assert json.loads((cartella / "b.json").read_text(encoding="utf-8"))["pbi"] == TESTO_DEL_PBI


def test_il_server_del_solver_riceve_il_clone_in_asdlc_clone(monkeypatch, tmp_path):
    """Il clone viaggia da `[rilascio].clone` alla variabile `ASDLC_CLONE`; senza chiave
    la variabile non c’è."""
    monkeypatch.setattr(runner, "PACCHETTO", tmp_path)
    con = dataclasses.replace(runner.CFG, rilascio=config.Rilascio(clone="/home/x/asdlc"))
    monkeypatch.setattr(runner, "CFG", con)
    percorso = runner.config_del_server("solver", tmp_path / "esito.json")
    ambiente = json.loads(percorso.read_text(encoding="utf-8"))["mcpServers"]["asdlc"]["env"]
    assert ambiente["ASDLC_CLONE"] == "/home/x/asdlc"

    monkeypatch.setattr(runner, "CFG", dataclasses.replace(con, rilascio=config.Rilascio()))
    percorso = runner.config_del_server("solver", tmp_path / "esito2.json")
    ambiente = json.loads(percorso.read_text(encoding="utf-8"))["mcpServers"]["asdlc"]["env"]
    assert "ASDLC_CLONE" not in ambiente
