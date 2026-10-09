"""Il layout del progetto si legge, non si scrive a mano (`backlog/PBI-504`).

Il difetto 90 di `PBI-102`, con la causa `default-implicito`: `dove_gira()` aveva
scritte a mano le cartelle di aDa, `backend` e `frontend`, invece di leggerle dai
`cwd` dei gate di `GATE`. Nella stessa classe di difetto stanno i test che trovano
la radice del repository contando le cartelle da `tools/tests/`: la radice è quella
che `radice()` di `asdlc.config` trova risalendo fino ad `asdlc.toml`.
"""

import importlib
import re
from pathlib import Path

import pytest

asdlc_config = importlib.import_module("asdlc.config")
runner = importlib.import_module("asdlc.runner")

TESTS = Path(__file__).resolve().parent

# `Path(__file__)`, con o senza `.resolve()`, seguito dall'indice dei suoi antenati.
# Il modello si compone a pezzi perché questo file non lo contenga, e non trovi sé
# stesso.
CONTA_LE_CARTELLE = re.compile(
    re.escape("Path(__file__)") + r"(?:\.resolve\(\))?" + re.escape(".parents" + "["))


@pytest.mark.progetto_ospite
def test_nessun_test_trova_la_radice_contando_le_cartelle():
    """Criterio 4. `conftest.py` resta fuori: mette `tools/` sul `sys.path`, e
    quel percorso è del pacchetto, non della radice (§Fuori scope)."""
    contano = sorted(
        f.name for f in TESTS.glob("*.py")
        if f.name != "conftest.py"
        and CONTA_LE_CARTELLE.search(f.read_text(encoding="utf-8")))

    assert contano == [], (
        "la radice si trova con `asdlc.config.radice()`, che risale fino ad "
        f"`asdlc.toml`, non contando le cartelle: {contano}")


def gate_in(*cartelle: str) -> list:
    """Un gate pytest per cartella: i test dichiarano `GATE` (decisione 5), e non
    leggono l'`asdlc.toml` del progetto di prova, che ha un solo gate in `.`."""
    return [asdlc_config.Gate(f"gate-{c}", ("python3", "-m", "pytest", "-q"), c)
            for c in cartelle]


class TestUnTestGiraDallaCartellaDelSuoGate:
    """Criterio 1: le cartelle sono i `cwd` dei gate di `GATE`."""

    def test_un_test_sotto_la_cartella_di_un_gate_gira_da_li(self, monkeypatch):
        monkeypatch.setattr(runner, "GATE", gate_in("servizio"))

        assert runner.dove_gira("servizio/tests/test_a.py") == ("servizio", "tests/test_a.py")

    def test_il_comando_isolato_parte_dalla_cartella_del_gate(self, monkeypatch, tmp_path):
        monkeypatch.setattr(runner, "GATE", gate_in("servizio"))
        albero = tmp_path / "albero"
        (albero / "servizio" / "tests").mkdir(parents=True)
        (albero / "servizio" / "tests" / "test_a.py").write_text(
            "def test_x():\n    assert True\n", encoding="utf-8")

        [comando], orfani = runner.comandi_dei_test(
            albero, [runner.TestNuovo("servizio/tests/test_a.py", "test_x", "python")])

        assert comando.cartella == albero / "servizio"
        assert list(comando.etichette.values()) == ["tests/test_a.py::test_x"]
        assert orfani == []


class TestBackendNonESpeciale:
    """Criterio 2: una cartella vale se è il `cwd` di un gate, e la prende solo un
    percorso che comincia con la cartella intera seguita da `/`."""

    def test_senza_un_gate_in_backend_il_test_gira_dalla_radice(self, monkeypatch):
        monkeypatch.setattr(runner, "GATE", gate_in("."))

        assert runner.dove_gira("backend/tests/test_a.py") == (".", "backend/tests/test_a.py")

    def test_un_gate_in_back_non_prende_backend(self, monkeypatch):
        monkeypatch.setattr(runner, "GATE", gate_in("back"))

        assert runner.dove_gira("backend/tests/test_a.py") == (".", "backend/tests/test_a.py")


class TestFraDueCartelleAnnidateVinceLaPiuLunga:
    """Criterio 3: un test sotto `app/web/` gira da `app/web` anche se c'è un gate
    in `app`, in qualunque ordine stiano i due gate in `GATE`."""

    @pytest.mark.parametrize("cartelle", [("app", "app/web"), ("app/web", "app")])
    def test_un_test_sotto_app_web_gira_da_app_web(self, monkeypatch, cartelle):
        monkeypatch.setattr(runner, "GATE", gate_in(*cartelle))

        assert runner.dove_gira("app/web/src/x.test.ts") == ("app/web", "src/x.test.ts")
