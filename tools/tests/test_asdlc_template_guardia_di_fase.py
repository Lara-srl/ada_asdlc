"""La guardia di fase di `template/`: il criterio 5 di `backlog/PBI-501`, uscito
dal PBI al giro 1 (difetto 97 di `PBI-102`) e fatto a mano.

Sta in un file suo, e non in `test_asdlc_template.py`, perché nasce in una PR
accanto ai giri di `PBI-501` e `PBI-502`, che scrivono in quel file.
"""

import importlib
import os
from pathlib import Path

import pytest

asdlc_config = importlib.import_module("asdlc.config")


def radice() -> Path:
    return asdlc_config.radice(Path(__file__).resolve().parent)


@pytest.mark.progetto_ospite
@pytest.mark.parametrize("relativo", [".claude/hooks/fase-tdd.sh", ".claude/settings.json"])
def test_la_guardia_di_fase_del_template_e_quella_di_questo_repository(relativo):
    """Una copia è una seconda fonte: il test la tiene uguale, e una correzione
    all'hook di qui senza la copia diventa rossa (PBI-501, decisione 7)."""
    copia = radice() / "template" / relativo
    assert copia.is_file(), copia

    assert copia.read_bytes() == (radice() / relativo).read_bytes()
    if copia.suffix == ".sh":
        assert os.access(copia, os.X_OK), copia
