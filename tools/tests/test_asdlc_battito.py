"""Il battito del tick (`backlog/PBI-510`, `ADR-0030` decisione 5).

A ogni passaggio il tick scrive l'ora in `~/asdlc-tick.battito`; al passaggio dopo,
se il distacco dal battito precedente supera la soglia, avvisa nel log. L'ora è un
parametro dei test: `coda.adesso` è sostituito, mai l'orologio vero. `decidi()` e
`lancia()` sono sostituiti come negli altri test del tick: nessun test parla con
`gh` o avvia un giro.

Il modulo si carica per nome, `asdlc.coda`: `conftest.py` mette `tools/` sul
`sys.path` (PBI-383).
"""

import datetime
import importlib
from pathlib import Path

import pytest

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"

coda = importlib.import_module("asdlc.coda")
coda.REPO = PROGETTO
coda.configura(coda.asdlc_config.carica(PROGETTO))

MEZZOGIORNO = datetime.datetime(2026, 10, 19, 12, 0, 0)


@pytest.fixture(autouse=True)
def mondo_finto(tmp_path, monkeypatch):
    """`HOME` in una cartella temporanea, e il tick senza contatti col mondo."""
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    for nome in ("allinea", "reinstalla", "indietro"):
        monkeypatch.setattr(coda, nome, lambda *a, **k: None, raising=False)
    monkeypatch.setattr(coda, "pin", lambda repo: [])
    monkeypatch.setattr(coda, "rilascia", lambda repo: [])
    monkeypatch.setattr(coda, "mancanze_dell_ambiente", lambda worktree: [], raising=False)
    return casa


def alle(monkeypatch, ora):
    """Il tick crede che sia `ora`."""
    monkeypatch.setattr(coda, "adesso", lambda: ora, raising=False)


def passaggio(tmp_path, monkeypatch, decisione=None):
    """Un passaggio del tick su un finto checkout; `decisione` di default è «finita»."""
    repo = tmp_path / "repo"
    (repo / "backlog").mkdir(parents=True, exist_ok=True)
    albero = tmp_path / "albero"
    albero.mkdir(exist_ok=True)
    monkeypatch.setattr(coda, "decidi", lambda repo, worktree: decisione or coda.Finita())
    monkeypatch.setattr(coda, "lancia", lambda pbi, worktree: None)
    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])
    return uscita, repo


def test_il_tick_scrive_il_battito_a_ogni_passaggio_anche_senza_lanciare_niente(
    mondo_finto, tmp_path, monkeypatch
):
    """Criterio 1. Con la coda finita il tick non lancia niente, e batte lo stesso:
    `~/asdlc-tick.battito` porta l'ora in ISO su una riga."""
    alle(monkeypatch, MEZZOGIORNO)

    uscita, _ = passaggio(tmp_path, monkeypatch)

    assert uscita == 0
    battito = mondo_finto / "asdlc-tick.battito"
    assert battito.read_text(encoding="utf-8") == "2026-10-19T12:00:00\n"
