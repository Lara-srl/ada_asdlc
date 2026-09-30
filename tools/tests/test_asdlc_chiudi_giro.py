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
import importlib.util
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


def test_guardia_un_rapporto_senza_testa_si_registra_ancora(tmp_path, monkeypatch):
    """Guardia dichiarata di PBI-385: i rapporti dei giri di prima non hanno
    `testa`, e `--registra` li deve piegare in `runs/tempi.csv` come prima. Il
    campo nuovo è del comando che chiude il giro, non del registro."""
    cartella = tmp_path / "runs"
    cartella.mkdir()
    (cartella / "20260927-100000-000001.json").write_text(json.dumps({
        "run": "20260927-100000-000001", "stato": "finito",
        "esiti": [{"pbi": "PBI-377", "stato": "fermato", "commit": 4,
                   "nota": "fermati: la domanda", "iniziato": "2026-09-27T10:00:00",
                   "finito": "2026-09-27T10:40:00", "durata_s": 2400.0,
                   "tempi": {"builder": 2000.0, "gate": 400.0}}],
    }), encoding="utf-8")
    monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")

    assert runner.registra(cartella) == 0

    righe = list(runner.csv.DictReader((tmp_path / "tempi.csv").open(encoding="utf-8")))
    assert [(r["run"], r["pbi"], r["stato"], r["commit"]) for r in righe] == [
        ("20260927-100000-000001", "PBI-377", "fermato", "4")]


# --- Il comando --------------------------------------------------------------


def test_il_modulo_di_asdlc_chiudi_giro_sta_nel_pacchetto():
    """Il punto d'ingresso `asdlc-chiudi-giro` di `tools/pyproject.toml` punta a
    `asdlc.chiudi_giro:main`: il modulo deve esserci, nel pacchetto `asdlc`."""
    assert importlib.util.find_spec("asdlc.chiudi_giro") is not None
