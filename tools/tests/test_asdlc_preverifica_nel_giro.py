"""La pre-verifica nel giro, e il tick che non rilancia un PBI da correggere
(`backlog/PBI-522`, `ADR-0031` decisioni 4 e 7).

Con `[preverifica].attiva` il giro legge il PBI alla base prima di creare il ramo:
con un rilievo chiude `fermato` col motivo `preverifica`, senza ramo, commit, PR né
Solver. I test accendono la sezione solo per sé (decisione 5): nel pacchetto è spenta
di default, e i giri degli altri test restano quelli di prima.

Nessun test lancia `claude`: il Builder e il Lettore sono finti. Il giro gira su un
clone vero con un remoto bare, perché «`git branch` invariato» si misura solo con
`git` vero.
"""

import dataclasses
import importlib
import tomllib
from pathlib import Path

import pytest
from test_asdlc_preverifica import clone_con_la_base, pbi_610, sh
from test_asdlc_runner import ruolo_ed_esito

runner = importlib.import_module("asdlc.runner")
config = importlib.import_module("asdlc.config")

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"
FILE_DEL_PBI = "backlog/PBI-610-una-prova.md"


def sezione_preverifica(testo: str = ""):
    """La sezione `[preverifica]` della configurazione del progetto di prova con sopra `testo`."""
    toml = (PROGETTO / "asdlc.toml").read_text(encoding="utf-8") + "\n" + testo
    return config.interpreta(tomllib.loads(toml), "asdlc.toml").preverifica


def accendi(monkeypatch, lettore: bool) -> None:
    """`[preverifica] attiva = true` per questo test soltanto: `Config` è `frozen`."""
    monkeypatch.setattr(runner, "CFG", dataclasses.replace(
        runner.CFG, preverifica=sezione_preverifica(
            f"[preverifica]\nattiva = true\nlettore = {'true' if lettore else 'false'}\n")))


def giro_sul_clone(tmp_path, monkeypatch, testo_del_pbi: str):
    """Un clone con `testo_del_pbi` come PBI-610 alla base, e il giro pronto a partire:
    il Builder e il Solver finti, che si ricordano di essere stati chiamati, e la
    pubblicazione e la fase sostituite. Rende il clone e l'elenco dei ruoli invocati,
    nell'ordine."""
    clone, _ = clone_con_la_base(tmp_path, {"modulo.py": "def somma(a, b):\n    return a + b\n",
                                            FILE_DEL_PBI: testo_del_pbi})
    monkeypatch.setattr(runner, "REPO", clone)
    monkeypatch.setattr(runner, "apri_la_fase", lambda base="": None)
    monkeypatch.setattr(runner, "pubblica", lambda branch, e=None: True)
    monkeypatch.setattr(runner, "smista_il_blocco",
                        lambda e, *a, **k: e.solver.append({"esito": "senza esito"}))
    vero = runner.esegui
    ruoli: list[str] = []

    def _esegui(cmd, cwd, timeout=7200, **k):
        if cmd[:1] == ["git"]:
            return vero(cmd, cwd, timeout, **k)
        ruoli.append(ruolo_ed_esito(cmd)[0])
        return 0, ""

    monkeypatch.setattr(runner, "esegui", _esegui)
    return clone, ruoli


# --- La sezione `[preverifica]` (decisione 1) ---------------------------------


def test_la_sezione_preverifica_e_spenta_di_default_e_col_lettore():
    preverifica = sezione_preverifica()

    assert (preverifica.attiva, preverifica.lettore) == (False, True)


@pytest.mark.parametrize(
    "testo, attesi",
    [
        pytest.param("attiva = true\nlettore = false\n", (True, False), id="senza-lettore"),
        pytest.param("attiva = true\n", (True, True), id="lettore-di-default"),
    ],
)
def test_la_sezione_preverifica_si_legge_dall_asdlc_toml(testo, attesi):
    preverifica = sezione_preverifica(f"[preverifica]\n{testo}")

    assert (preverifica.attiva, preverifica.lettore) == attesi


# --- Criterio 1: con un rilievo il giro si ferma prima del ramo ---------------


def test_con_un_rilievo_il_giro_si_ferma_prima_del_ramo(tmp_path, monkeypatch):
    senza_verifica = pbi_610().replace("## Verifica", "## Altro")
    clone, ruoli = giro_sul_clone(tmp_path, monkeypatch, senza_verifica)
    accendi(monkeypatch, lettore=False)
    rami = sh(clone, "branch")
    base = sh(clone, "rev-parse", "origin/main")

    e = runner.esegui_pbi("PBI-610", attivi=set(), dry=False, con_pr=False, run="giro")

    assert (e.motivo, e.stato) == ("preverifica", "fermato"), e.nota
    assert e.sha_pbi == sh(clone, "rev-parse", f"{base}:{FILE_DEL_PBI}")
    assert e.rilievi_preverifica == 1
    assert ruoli == [], "con un rilievo nessun agente parte"
    assert sh(clone, "branch") == rami, "con un rilievo il ramo non nasce"
    assert e.solver == [], "il Solver non parte"
    rapporto = runner.LOG_DIR / "giro-PBI-610-preverifica.json"
    assert rapporto.exists(), list(runner.LOG_DIR.iterdir())
    assert "rilievi: 1" in e.nota and str(rapporto) in e.nota, e.nota
