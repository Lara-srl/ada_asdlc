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
import json
import shutil
import tomllib
from datetime import datetime
from pathlib import Path

import pytest
from test_asdlc_preverifica import clone_con_la_base, pbi_610, sh
from test_asdlc_runner import ruolo_ed_esito

runner = importlib.import_module("asdlc.runner")
config = importlib.import_module("asdlc.config")
coda = importlib.import_module("asdlc.coda")

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"
# Come in `test_asdlc_coda.py`: la radice e la configurazione del tick sono quelle del
# progetto di prova.
coda.REPO = PROGETTO
coda.configura(coda.asdlc_config.carica(PROGETTO))
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


LETTO = {"esito": "letto", "riepilogo": "letto", "rilievi": [], "sonde": []}
LIMITE = "You've hit your session limit · resets 7:50pm\n"


def giro_sul_clone(tmp_path, monkeypatch, testo_del_pbi: str, esiti: dict | None = None,
                   uscite: dict | None = None):
    """Un clone con `testo_del_pbi` come PBI-610 alla base, e il giro pronto a partire:
    gli agenti e il Solver finti, che si ricordano di essere stati chiamati, e la
    pubblicazione e la fase sostituite. Un agente scrive nel suo file d'esito ciò che
    `esiti` dà al suo ruolo, come il server dopo una chiamata valida; un ruolo assente
    non chiama niente. `uscite` dà a un ruolo il codice d'uscita e lo stderr della CLI,
    scritto nel file dei flussi; senza, esce 0 e muto. Rende il clone e l'elenco dei
    ruoli invocati, nell'ordine."""
    clone, _ = clone_con_la_base(tmp_path, {"modulo.py": "def somma(a, b):\n    return a + b\n",
                                            FILE_DEL_PBI: testo_del_pbi})
    monkeypatch.setattr(runner, "REPO", clone)
    monkeypatch.setattr(runner, "apri_la_fase", lambda base="": None)
    monkeypatch.setattr(runner, "pubblica", lambda branch, e=None: True)
    monkeypatch.setattr(runner, "smista_il_blocco",
                        lambda e, *a, **k: e.solver.append({"esito": "senza esito"}))
    vero = runner.esegui
    ruoli: list[str] = []

    def _esegui(cmd, cwd, timeout=7200, flussi=None, **k):
        if cmd[:1] == ["git"]:
            return vero(cmd, cwd, timeout, flussi=flussi, **k)
        ruolo, file_esito = ruolo_ed_esito(cmd)
        ruoli.append(ruolo)
        if (esiti or {}).get(ruolo) is not None:
            file_esito.write_text(json.dumps(esiti[ruolo]), encoding="utf-8")
        codice, dentro = (uscite or {}).get(ruolo, (0, ""))
        if flussi is not None:
            flussi[0].write_text("", encoding="utf-8")
            flussi[1].write_text(dentro, encoding="utf-8")
        return codice, dentro

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


# --- Criterio 2: col Lettore acceso, il Lettore gira prima del Builder --------


def test_col_lettore_acceso_il_lettore_gira_una_volta_prima_del_builder(tmp_path, monkeypatch):
    _, ruoli = giro_sul_clone(tmp_path, monkeypatch, pbi_610(), {"lettore": LETTO})
    accendi(monkeypatch, lettore=True)

    runner.esegui_pbi("PBI-610", attivi=set(), dry=False, con_pr=False, run="giro")

    assert ruoli.count("lettore") == 1, ruoli
    assert ruoli[:2] == ["lettore", "builder"], ruoli


# --- Criterio 3: un Lettore senza esito non è un PBI da correggere ------------


def giro_col_lettore_sul_limite(tmp_path, monkeypatch):
    """Un giro di PBI-610 il cui Lettore esce 1 col limite d'uso nello stderr e non
    chiama `letto`: l'esito, il clone, i ruoli invocati e i rami di prima."""
    clone, ruoli = giro_sul_clone(tmp_path, monkeypatch, pbi_610(),
                                  uscite={"lettore": (1, LIMITE)})
    accendi(monkeypatch, lettore=True)
    rami = sh(clone, "branch")
    e = runner.esegui_pbi("PBI-610", attivi=set(), dry=False, con_pr=False, run="giro")
    return e, clone, ruoli, rami


def tick_dopo_il_giro(tmp_path, monkeypatch, e) -> tuple[Path, Path]:
    """Il checkout del tick con PBI-610 in coda, e il worktree del runner col rapporto del
    giro `e` nel suo registro. Su `origin` nessun ramo e nessuna PR. Rende i due alberi."""
    repo, albero = tmp_path / "tick", tmp_path / "albero"
    (repo / "backlog").mkdir(parents=True)
    (repo / "backlog" / "CODA.md").write_text("- PBI-610\n", encoding="utf-8")
    registro = albero / coda.CFG.registro.cartella
    registro.mkdir(parents=True)
    shutil.copy(runner.chiudi_rapporto("giro", [e]), registro)
    monkeypatch.setattr(coda, "esegui", lambda cmd, cwd: (0, "[]" if cmd[0] == "gh" else ""))
    return repo, albero


def test_un_lettore_fermo_sul_limite_d_uso_chiude_lettore_senza_esito_con_riprendi_dopo(
        tmp_path, monkeypatch):
    e, clone, ruoli, rami = giro_col_lettore_sul_limite(tmp_path, monkeypatch)

    assert (e.motivo, e.stato) == ("lettore-senza-esito", "senza esito"), e.nota
    assert e.riprendi_dopo, "il limite d'uso con l'ora leggibile porta riprendi_dopo"
    assert datetime.fromisoformat(e.riprendi_dopo) > datetime.now()
    assert ruoli == ["lettore"], "senza la lettura il Builder non parte"
    assert sh(clone, "branch") == rami, "il ramo non nasce"
    assert e.solver == [], "il Solver non parte"


def test_il_tick_aspetta_il_reset_di_un_lettore_senza_esito(tmp_path, monkeypatch):
    e, _, _, _ = giro_col_lettore_sul_limite(tmp_path, monkeypatch)
    repo, albero = tick_dopo_il_giro(tmp_path, monkeypatch, e)

    decisione = coda.decidi(repo, albero)

    assert isinstance(decisione, coda.AttendeIlReset), (
        f"{decisione}: un Lettore fermo sul limite d'uso si riprende dopo il reset"
    )
