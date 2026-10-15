"""PBI-505: il lucchetto di fase legge i test JUnit.

Ogni classe è un criterio della *Verifica* del PBI. Nessun test lancia Maven e
nessuno usa la rete: `esegui()` si sostituisce con un finto che scrive i rapporti
di `dati/`.
"""

import importlib

import pytest

from test_asdlc_runner import RepoDiProva

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


@pytest.fixture
def repo_java(tmp_path, monkeypatch):
    """Un repository vero con la forma di un progetto Maven: `app/src/{main,test}`."""
    radice = tmp_path / "repo"
    radice.mkdir()
    repo = RepoDiProva(radice)
    monkeypatch.setattr(runner, "REPO", radice)
    monkeypatch.setattr(runner, "GATE", [
        runner.Gate("maven", ("./mvnw", "verify"), "app"),
    ])
    return repo


TEST_JAVA = "app/src/test/java/it/x/SchemaIT.java"
FOO_JAVA = "app/src/main/java/it/x/Foo.java"

SCHEMA_IT = """package it.x;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;

class SchemaIT {

    @Test
    void a() {
        assertEquals(1, 2);
    }

    @Test
    @DisplayName("la seconda")
    void b() {
    }

    @ParameterizedTest
    @ValueSource(strings = {"x", "y"})
    void c(String valore) {
    }

    void aiutante() {
    }
}
"""


class TestLaNascitaDeiTestJunitSiLegge:
    """Criterio 2: dall'albero di lavoro, per un file non tracciato."""

    def test_un_file_non_tracciato_nasce_con_i_suoi_tre_test(self, repo_java):
        f = repo_java.radice / TEST_JAVA
        f.parent.mkdir(parents=True)
        f.write_text(SCHEMA_IT, encoding="utf-8")

        nuovi = runner.test_nuovi_dellalbero()

        assert sorted(nuovi, key=lambda t: t.nome) == [
            runner.TestNuovo(TEST_JAVA, f"SchemaIT#{n}", "junit") for n in "abc"]


class TestIlCommitRedJunitSiVedeDalRipiegoSuHead:
    """Criterio 3: `test_nuovi_da_aprire()` legge l'ultimo commit se l'albero è
    pulito, ed è il percorso che sul giro del PBI-002 ha risposto «nessun test»."""

    def test_un_commit_di_soli_test_restituisce_i_suoi_tre_test(self, repo_java):
        repo_java.commit("test(schema): lo schema ha le tabelle (RED)", {TEST_JAVA: SCHEMA_IT})

        nuovi = runner.test_nuovi_da_aprire()

        assert sorted(nuovi, key=lambda t: t.nome) == [
            runner.TestNuovo(TEST_JAVA, f"SchemaIT#{n}", "junit") for n in "abc"]
