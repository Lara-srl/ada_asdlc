"""PBI-505: il lucchetto di fase legge i test JUnit.

Ogni classe è un criterio della *Verifica* del PBI. Nessun test lancia Maven e
nessuno usa la rete: `esegui()` si sostituisce con un finto che scrive i rapporti
di `dati/`.
"""

import importlib

# `conftest.py` mette `tools/` sul `sys.path`: il runner è `asdlc.runner`.
runner = importlib.import_module("asdlc.runner")


class TestUnFileInSrcTestEUnTestJunit:
    """Criterio 1: `src/test/` è test, `src/main/` è produzione."""

    TEST = "app/src/test/java/it/x/SchemaIT.java"
    PRODUZIONE = "app/src/main/java/it/x/Foo.java"

    def test_il_linguaggio_di_un_file_in_src_test_e_junit(self):
        assert runner.linguaggio_del_test(self.TEST) == "junit"

    def test_un_file_in_src_test_e_un_file_di_test(self):
        assert runner.e_file_di_test(self.TEST)

    def test_un_file_in_src_main_e_produzione(self):
        assert runner.e_file_di_produzione(self.PRODUZIONE)

    def test_una_cartella_test_dentro_src_main_non_fa_un_test(self):
        assert runner.e_file_di_produzione("app/src/main/java/it/x/test/Foo.java")
