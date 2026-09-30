"""Il rapporto del giro dice quale runner l'ha prodotto (`backlog/PBI-386`).

`runs/<run>.json` guadagna, al livello del giro, `"asdlc": {"versione", "sha"}`:
la versione del pacchetto installato, e lo sha del commit quando
l'installazione viene da git (`direct_url.json`, `vcs_info.commit_id`). Senza il
pacchetto installato, come sotto i test, sono tutti e due `null` e il giro non
fallisce (`ADR-0026`, decisione 4).

Il pacchetto installato è un varco come `git` ed `esegui`: qui lo sostituisce una
`dist-info` finta in una cartella temporanea, letta da `importlib.metadata`.
"""

import importlib
import importlib.metadata
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

runner = importlib.import_module("asdlc.runner")
runner.REPO = REPO
runner.configura(runner.asdlc_config.carica(REPO))


@pytest.fixture(autouse=True)
def db():
    return None


@pytest.fixture(autouse=True)
def clear_login_limiter():
    return None


@pytest.fixture(autouse=True)
def clear_event_bus():
    return None


def distribuzione(cartella: Path, versione: str, direct_url: dict | None):
    """Una `asdlc-<versione>.dist-info` in `cartella`, come la scrive `pip`."""
    info = cartella / f"asdlc-{versione}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: asdlc\nVersion: {versione}\n", encoding="utf-8")
    if direct_url is not None:
        (info / "direct_url.json").write_text(json.dumps(direct_url), encoding="utf-8")
    return importlib.metadata.PathDistribution(info)


def installato(monkeypatch, distribuita) -> None:
    monkeypatch.setattr(runner, "distribuzione_del_runner", lambda: distribuita,
                        raising=False)


def assente() -> None:
    raise importlib.metadata.PackageNotFoundError("asdlc")


# Le due scritture del rapporto: all'apertura del giro, e dopo ogni PBI.
SCRITTURE = [
    pytest.param(lambda: runner.apri_rapporto("20261001-000000-1", ["PBI-1"]), id="apri"),
    pytest.param(lambda: runner.scrivi_rapporto("20261001-000000-1", [], "in-corso"),
                 id="scrivi"),
]


def letto(percorso: Path) -> dict:
    return json.loads(percorso.read_text(encoding="utf-8"))


@pytest.mark.parametrize("scrivi", SCRITTURE)
def test_installato_da_git_il_rapporto_porta_versione_e_sha_del_commit(
    tmp_path, monkeypatch, scrivi,
):
    installato(monkeypatch, distribuzione(tmp_path, "1.2.0", {
        "url": "https://github.com/Lara-srl/asdlc.git",
        "vcs_info": {"vcs": "git", "requested_revision": "v1.2.0",
                     "commit_id": "c0ffee0000000000000000000000000000000386"},
    }))

    rapporto = letto(scrivi())

    assert rapporto.get("asdlc") == {
        "versione": "1.2.0", "sha": "c0ffee0000000000000000000000000000000386"}


@pytest.mark.parametrize("scrivi", SCRITTURE)
def test_installato_da_una_cartella_il_rapporto_porta_la_versione_e_lo_sha_null(
    tmp_path, monkeypatch, scrivi,
):
    """`pip install ./tools`: il `direct_url.json` c'è, ma dice una cartella e non
    un commit. Lo sha arriva con l'installazione da tag della Fase 5."""
    installato(monkeypatch, distribuzione(tmp_path, "1.0.0.dev0", {
        "url": "file:///home/chi/progetto/tools", "dir_info": {},
    }))

    rapporto = letto(scrivi())

    assert rapporto.get("asdlc") == {"versione": "1.0.0.dev0", "sha": None}


@pytest.mark.parametrize("scrivi", SCRITTURE)
def test_senza_il_pacchetto_installato_versione_e_sha_sono_null(monkeypatch, scrivi):
    monkeypatch.setattr(runner, "distribuzione_del_runner", assente, raising=False)

    rapporto = letto(scrivi())

    assert rapporto.get("asdlc") == {"versione": None, "sha": None}
