"""Le fixture comuni ai test di `tools/`.

Il runner si carica per nome da `test_asdlc_runner.py`, e sta in `sys.modules`
come `asdlc.runner`: qui lo si cerca lì, al momento del test, senza
caricarne una seconda copia.
"""

import functools
import sys
from pathlib import Path

import pytest

# `tools/` sul `sys.path`, una volta per tutta la suite: il runner è il pacchetto
# `asdlc` (PBI-383), e i test lo caricano per nome.
TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

# Il progetto di prova su cui girano questi test (PBI-394, decisione 1): il loro
# `asdlc.toml`, e non quello del progetto che li ospita, che nel repository
# `asdlc` non ci sarà.
PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"

# Ciò che i test di questa cartella lanciano per nome in un sottoprocesso: il gate
# del rosso gira `pytest` in un worktree di `git`. `gh`, `npm` e `node` i test li
# sostituiscono con dei finti, e non si chiedono: la CI non li deve avere.
USATI_DAI_TEST = ("git", "pytest")


def pytest_configure(config):
    # La guardia di fine suite su `dati/` (PBI-518), per ogni `pytest` che
    # raccoglie questa cartella: il gate e la CI compresi.
    config.pluginmanager.import_plugin("guardia_dei_dati")
    config.addinivalue_line(
        "markers",
        "progetto_ospite: il test legge apposta un file del progetto che ospita la "
        "suite — la coda vera, l'hook di fase, la KB, il suo asdlc.toml — e non il "
        "progetto di prova (PBI-394, decisione 2; PBI-395, decisione 10)")


def pytest_sessionstart(session):
    """L'ambiente dei test, prima della raccolta (PBI-384, decisione 8).

    Senza `pytest` sul `PATH` dei sottoprocessi ogni test del gate del rosso
    moriva da sé con un'uscita 127: 19 `GuastoDelGate` nel difetto 60 di
    PBI-102, e la causa andava dedotta. Qui si cerca `git` e `pytest` come li
    cerca il runner — nel venv di `[ambiente].venv`, poi sul `PATH` — e la
    sessione si ferma con le mancanze, una riga ciascuna.

    Il venv è quello del progetto di prova, che uno suo non ce l'ha: i due si
    cercano sul `PATH`, come nel repository `asdlc` (PBI-394, decisione 6).

    Un `asdlc.toml` che non si legge, o un lettore che alza, non ferma niente qui:
    lo diranno i test che lo leggono. Il gate del rosso rigira questi test contro
    i mutanti di `asdlc.config` e di `asdlc.runner`, e un'eccezione qui dentro
    interromperebbe pytest prima del rapporto JUnit, che è ciò che il gate legge:
    il mutante diventerebbe un guasto del gate invece di un test che fallisce.
    """
    try:
        from asdlc import config as asdlc_config
        from asdlc import runner as asdlc_runner

        venv = asdlc_config.carica(PROGETTO).ambiente.venv
        mancanze = asdlc_runner.eseguibili_mancanti(USATI_DAI_TEST, venv, PROGETTO)
    except Exception:  # noqa: BLE001 — vedi sopra: qui non si ferma per un guasto
        return
    if mancanze:
        pytest.exit("\n".join(mancanze))


@pytest.fixture(autouse=True)
def log_dir_temporanea(tmp_path_factory, monkeypatch):
    """La `LOG_DIR` del runner in una cartella temporanea del test (PBI-370).

    I test che fanno girare `esegui_pbi` o `revisione_critica` con `esegui`
    sostituito scrivevano prompt, esiti e config MCP nella `runs/` vera, mescolati
    alle chiamate del runner: 124 file a ogni giro di `pytest tools/tests`. Una
    fixture `autouse` e non una correzione classe per classe, perché la classe di
    domani non se ne debba ricordare.

    Si sposta **ogni** costante del modulo che è un percorso sotto la `LOG_DIR`
    vera, non la sola `LOG_DIR`: `configura()` ne ricava altri, come `CSV_TEMPI`
    (decisione 2). E si rifà dopo ogni `configura()` chiamata dentro il test,
    perché riapplicare un `asdlc.toml` li ricalcola da `REPO`, cioè di nuovo
    sotto `runs/`.
    """
    # Una cartella sua e non `tmp_path`: i test che guardano cosa c'è in
    # `tmp_path` non devono trovarci una `runs/` che non hanno creato.
    finta = tmp_path_factory.mktemp("runs")
    sposta_il_log_del_tick(finta, monkeypatch)
    runner = sys.modules.get("asdlc.runner")
    # Importato da `pytest_sessionstart` ma non configurato: nessun file di test
    # lo usa, e non ha una `LOG_DIR` da spostare.
    vera = getattr(runner, "LOG_DIR", None)
    if vera is None:
        return

    def sposta() -> None:
        for nome, valore in list(vars(runner).items()):
            if isinstance(valore, Path) and valore.is_relative_to(vera):
                monkeypatch.setattr(runner, nome, finta / valore.relative_to(vera))

    configura = runner.configura

    @functools.wraps(configura)
    def configura_e_sposta(cfg):
        configura(cfg)
        sposta()

    monkeypatch.setattr(runner, "configura", configura_e_sposta)
    sposta()


def sposta_il_log_del_tick(finta: Path, monkeypatch) -> None:
    """Il `LOG` del tick nella stessa cartella temporanea (PBI-382, decisione 6).

    Il tick lo scrive in `repo / LOG`, con `LOG` relativo: un test che lo chiama
    in-process sul checkout vero scriverebbe nel `runs/coda.log` vero, che è la
    classe del difetto 38. Un `LOG` assoluto vince sul `repo` davanti, qualunque
    sia. E si rifà dopo ogni `configura()`, perché `main()` la chiama e rimette il
    `LOG` relativo di `asdlc.toml`.
    """
    coda = sys.modules.get("asdlc.coda")
    if coda is None:
        return

    def sposta() -> None:
        monkeypatch.setattr(coda, "LOG", finta / "coda.log")

    configura = coda.configura

    @functools.wraps(configura)
    def configura_e_sposta(cfg):
        configura(cfg)
        sposta()

    monkeypatch.setattr(coda, "configura", configura_e_sposta)
    sposta()
