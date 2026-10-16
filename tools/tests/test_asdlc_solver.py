"""Il ruolo Solver nel server dell'esito (`backlog/PBI-507`, `ADR-0030`, R1-R3).

Il Solver è il terzo ruolo accanto a Builder e Critic: smista un giro fermato con uno
di tre strumenti, che il server dell'esito valida (`ADR-0027`).
"""

import importlib
import json
from pathlib import Path

esito = importlib.import_module("asdlc.esito")

STRUMENTI_DEL_SOLVER = {"risolvi", "segnala_limite_runner", "chiedi_a_francesco"}


def nomi(ruolo):
    return {s["name"] for s in esito.strumenti(ruolo)}


def test_il_solver_ha_i_suoi_tre_strumenti_e_gli_altri_ruoli_no():
    """R1: gli strumenti del Solver sono suoi e di nessun altro ruolo."""
    assert STRUMENTI_DEL_SOLVER <= nomi("solver")
    assert not STRUMENTI_DEL_SOLVER & nomi("builder")
    assert not STRUMENTI_DEL_SOLVER & nomi("critic")


def test_risolvi_rifiuta_un_evidenza_che_non_esiste_e_accetta_un_file_dell_albero(tmp_path, monkeypatch):
    """R2: `evidenza` nomina un file dell'albero, con un eventuale `:riga`."""
    monkeypatch.chdir(tmp_path)  # l'albero del giro è la cartella da cui parte il server
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "spec.md").write_text("x\n", encoding="utf-8")
    cartella = tmp_path / "esito"
    cartella.mkdir()

    rifiutata = esito.chiama("risolvi", {"risposta": "perché sì", "evidenza": "specs/non-c-e.md"},
                             "solver", str(cartella / "a.json"))
    assert rifiutata["isError"]
    assert not (cartella / "a.json").exists()

    accettata = esito.chiama("risolvi", {"risposta": "perché sì", "evidenza": "specs/spec.md:3"},
                             "solver", str(cartella / "b.json"))
    assert not accettata["isError"], accettata
    assert (cartella / "b.json").exists()


def albero_con_un_commit(tmp_path, monkeypatch):
    """Un repository git con un commit, e la cartella d'esito: l'albero del giro."""
    import subprocess
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


def test_segnala_limite_runner_con_una_causa_in_elenco_registra_il_limite(tmp_path, monkeypatch):
    """R3: causa dell'elenco `runner-*`, comando e output pieni, commit esistente."""
    sha, cartella = albero_con_un_commit(tmp_path, monkeypatch)
    monkeypatch.setenv("ASDLC_CAUSE", "runner-non-legge-junit,runner-altro")

    risposta = esito.chiama(
        "segnala_limite_runner",
        {"causa": "runner-non-legge-junit", "comando": "pytest -q", "output": "0 test",
         "commit": sha}, "solver", str(cartella / "a.json"))

    assert not risposta["isError"], risposta
    registrato = json.loads((cartella / "a.json").read_text(encoding="utf-8"))
    assert registrato["esito"] == "limite-del-runner"
    assert registrato["causa"] == "runner-non-legge-junit"


def test_segnala_limite_runner_rifiuta_causa_fuori_elenco_comando_o_output_vuoti_commit_sconosciuto(
        tmp_path, monkeypatch):
    """R3: quattro rifiuti, e nessun esito scritto."""
    sha, cartella = albero_con_un_commit(tmp_path, monkeypatch)
    monkeypatch.setenv("ASDLC_CAUSE", "runner-non-legge-junit")
    valido = {"causa": "runner-non-legge-junit", "comando": "pytest -q", "output": "0 test",
              "commit": sha}
    guasti = [
        {"causa": "runner-inventata"},
        {"comando": "  "},
        {"output": ""},
        {"commit": "0123456789abcdef0123456789abcdef01234567"},
    ]
    for numero, guasto in enumerate(guasti):
        file = cartella / f"{numero}.json"
        risposta = esito.chiama("segnala_limite_runner", {**valido, **guasto}, "solver", str(file))
        assert risposta["isError"], guasto
        assert not file.exists(), guasto
