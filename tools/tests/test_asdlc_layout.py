"""Il layout del progetto si legge, non si scrive a mano (`backlog/PBI-504`).

Il difetto 90 di `PBI-102`, con la causa `default-implicito`: `dove_gira()` aveva
scritte a mano le cartelle di aDa, `backend` e `frontend`, invece di leggerle dai
`cwd` dei gate di `GATE`. Nella stessa classe di difetto stanno i test che trovano
la radice del repository contando le cartelle da `tools/tests/`: la radice è quella
che `radice()` di `asdlc.config` trova risalendo fino ad `asdlc.toml`.
"""

import re
from pathlib import Path

import pytest

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
