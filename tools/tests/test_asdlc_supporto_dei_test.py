"""PBI-515: il lucchetto non chiude i file di supporto dei test.

Ogni classe è un criterio della *Verifica* del PBI. Sotto `src/test/` nessun file
è produzione, e uno scheletro vuoto — righe bianche e commenti — si crea in
`TEST_ONLY`.
"""

import importlib

import pytest

# `conftest.py` mette `tools/` sul `sys.path`: il runner è `asdlc.runner`.
runner = importlib.import_module("asdlc.runner")

SUPPORTO = "app/src/test/resources/genera.sh"
MIGRAZIONE = "tools/migrazione/riconcilia.sh"


class TestUnFileDiSupportoInSrcTestNonEProduzione:
    """Criterio 1: un `.sh` o un `.sql` sotto `src/test/` non è produzione e non è
    un test; fuori da `src/test/`, e in `src/main/…/test/`, la produzione resta."""

    @pytest.mark.parametrize("percorso, produzione", [
        (SUPPORTO, False),
        ("app/src/test/resources/schema.sql", False),
        (MIGRAZIONE, True),
        ("db/V9__x.sql", True),
        ("app/src/main/java/it/x/test/Foo.java", True),
    ])
    def test_sotto_src_test_nessun_file_e_produzione(self, percorso, produzione):
        assert runner.e_file_di_produzione(percorso) is produzione
        assert not runner.e_file_di_test(percorso)
