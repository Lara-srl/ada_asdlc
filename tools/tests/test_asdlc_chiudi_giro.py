"""`asdlc-chiudi-giro`: un giro fermato si chiude con un comando (`backlog/PBI-385`).

Tre gruppi:

- **La testa nel rapporto** — `Esito.testa`, lo sha del ramo pubblicato su
  `origin`, che il runner scrive e il comando legge.
- **I rifiuti** — ciò che fa dire di no al comando prima di toccare qualsiasi cosa.
- **I sei passi** — pausa, tag, push del tag, ramo cancellato, `ff-only`, pausa
  tolta: nell'ordine, anche quando uno fallisce.

`HOME` è una cartella temporanea in ogni test (`home_finta`): la pausa vera,
`~/asdlc-tick.pausa`, ferma il tick della macchina, e un test che la creasse o la
togliesse spegnerebbe o riaccenderebbe il cron di chi li lancia.
"""

import importlib
import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

runner = importlib.import_module("asdlc.runner")
# L'import non legge `asdlc.toml` (PBI-382): lo si legge qui, come fa
# `test_asdlc_runner.py`, sulla radice di questo repository.
runner.REPO = REPO
runner.configura(runner.asdlc_config.carica(REPO))


@pytest.fixture(autouse=True)
def home_finta(tmp_path, monkeypatch):
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    return casa


def sh(cwd: Path, *args: str) -> str:
    fatto = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                            "-c", "init.defaultBranch=main", *args],
                           cwd=cwd, capture_output=True, text=True, check=True)
    return fatto.stdout.strip()


# --- La testa nel rapporto ---------------------------------------------------


def test_il_rapporto_di_un_giro_che_pubblica_porta_la_testa_che_sta_su_origin(
    tmp_path, monkeypatch
):
    """Decisione 1: `Esito.testa` è lo sha del ramo pubblicato su `origin`. È ciò
    su cui `asdlc-chiudi-giro` mette il tag, e senza il comando dovrebbe
    indovinarlo — il 25/09 il tag di `PBI-363` è finito sulla testa sbagliata.

    Con git vero: un remoto nudo, un clone, un commit del giro pubblicato."""
    remoto, noi = tmp_path / "remoto.git", tmp_path / "noi"
    sh(tmp_path, "init", "-q", "--bare", str(remoto))
    sh(tmp_path, "clone", "-q", str(remoto), str(noi))
    sh(noi, "commit", "-q", "--allow-empty", "-m", "base")
    sh(noi, "switch", "-q", "-c", "pbi/pbi-385")
    sh(noi, "commit", "-q", "--allow-empty", "-m", "del giro")
    monkeypatch.setattr(runner, "REPO", noi)
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path / "runs")
    esito = runner.Esito("PBI-385", "fermato")

    assert runner.pubblica("pbi/pbi-385", esito) is True
    rapporto = runner.scrivi_rapporto("20260930-211011-341864", [esito], "finito")

    su_origin = sh(noi, "ls-remote", "origin", "refs/heads/pbi/pbi-385").split()[0]
    scritto = json.loads(rapporto.read_text(encoding="utf-8"))["esiti"][0]
    assert scritto.get("testa") == su_origin
