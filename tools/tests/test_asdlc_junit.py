"""PBI-505: il lucchetto di fase legge i test JUnit.

Ogni classe è un criterio della *Verifica* del PBI. Nessun test lancia Maven e
nessuno usa la rete: `esegui()` si sostituisce con un finto che scrive i rapporti
di `dati/`.
"""

import importlib
import tomllib
from pathlib import Path

import pytest

from test_asdlc_runner import RepoDiProva

# `conftest.py` mette `tools/` sul `sys.path`: il runner è `asdlc.runner`.
runner = importlib.import_module("asdlc.runner")
config = importlib.import_module("asdlc.config")

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"
COMANDO_MAVEN = ["./mvnw", "-B", "verify", "-Dtest={test}", "-Dit.test={test}",
                 "-Dsurefire.failIfNoSpecifiedTests=false",
                 "-Dfailsafe.failIfNoSpecifiedTests=false"]


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

    def test_un_commit_che_tocca_anche_produzione_non_e_un_rosso(self, repo_java):
        repo_java.commit("feat(schema): lo schema e il suo test", {
            TEST_JAVA: SCHEMA_IT, FOO_JAVA: "package it.x;\n\nclass Foo {\n}\n"})

        assert runner.test_nuovi_da_aprire() == []


def configurazione(sezione_junit: str):
    """La configurazione del progetto di prova con sopra la sezione `[junit]` data."""
    testo = (PROGETTO / "asdlc.toml").read_text(encoding="utf-8") + "\n" + sezione_junit
    return config.interpreta(tomllib.loads(testo), "asdlc.toml")


class TestIlComandoIsolaITestERispettaJunit:
    """Criterio 4: il comando lo dichiara il progetto in `[junit]`; senza, il test
    JUnit è un orfano e nessun comando parte (decisioni 4 e 5)."""

    ALTRO_JAVA = "app/src/test/java/it/x/AltraIT.java"
    NUOVI = [runner.TestNuovo(TEST_JAVA, "SchemaIT#a", "junit"),
             runner.TestNuovo(TEST_JAVA, "SchemaIT#b", "junit"),
             runner.TestNuovo(ALTRO_JAVA, "AltraIT#m3", "junit")]

    @pytest.fixture(autouse=True)
    def gate_in_app(self, monkeypatch):
        monkeypatch.setattr(runner, "GATE", [runner.Gate("maven", ("./mvnw",), "app")])

    def test_la_sezione_si_legge_dal_toml(self):
        cfg = configurazione('[junit]\ncomando = ["./mvnw", "verify", "-Dtest={test}"]\n')

        assert cfg.junit.comando == ("./mvnw", "verify", "-Dtest={test}")

    def test_con_la_sezione_un_comando_per_cartella_con_i_test_sostituiti(
            self, monkeypatch, tmp_path):
        monkeypatch.setattr(runner, "JUNIT_COMANDO", tuple(COMANDO_MAVEN))

        comandi, orfani = runner.comandi_dei_test(tmp_path, self.NUOVI)

        [comando] = comandi
        assert orfani == []
        assert comando.cartella == tmp_path / "app"
        assert comando.linguaggio == "junit"
        assert comando.argv == [a.replace("{test}", "SchemaIT#a+b,AltraIT#m3")
                                for a in COMANDO_MAVEN]
        assert comando.etichette == {n.nome: n.nome for n in self.NUOVI}

    def test_senza_la_sezione_i_test_sono_orfani_e_nessun_comando_parte(
            self, monkeypatch, tmp_path):
        monkeypatch.setattr(runner, "JUNIT_COMANDO", None)

        comandi, orfani = runner.comandi_dei_test(tmp_path, self.NUOVI)

        assert comandi == []
        assert orfani == ["SchemaIT#a", "SchemaIT#b", "AltraIT#m3"]

    @pytest.mark.parametrize("sezione", [
        '[junit]\ncomando = ["./mvnw", "verify"]\n',
        '[junit]\ncomando = ["./mvnw", "-Dtest={test}"]\nrapporti = "target"\n',
        '[junit]\n',
    ])
    def test_una_sezione_sbagliata_e_un_errore_di_configurazione(self, sezione):
        with pytest.raises(config.ErroreDiConfigurazione):
            configurazione(sezione)
