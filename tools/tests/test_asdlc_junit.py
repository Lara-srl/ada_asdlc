"""PBI-505: il lucchetto di fase legge i test JUnit.

Ogni classe è un criterio della *Verifica* del PBI. Nessun test lancia Maven e
nessuno usa la rete: `esegui()` si sostituisce con un finto che scrive i rapporti
di `dati/`.
"""

import importlib
import shutil
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

    def test_un_file_non_java_in_src_test_non_e_un_test_ne_produzione(self):
        # Non è un test (non regressione sulle nascite), e da PBI-515 non è
        # nemmeno produzione: sotto `src/test/` nessun file lo è.
        for percorso in ("src/test/helpers.py", "web/src/test/setup.ts"):
            assert not runner.e_file_di_test(percorso)
            assert not runner.e_file_di_produzione(percorso)


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


class TestUnaAnnotazioneSulleStessaRigaDelMetodo:
    """Criterio 2, rilievo del Critic: `@Test void a() { ... }` su una riga sola."""

    UNA_RIGA = """package it.x;

class SchemaIT {

    @Test void a() { new Foo().run(); }

    @Test @DisplayName("b") void b() { throw new IllegalStateException("x"); }

    void aiutante() {
    }
}
"""

    def test_nasce_il_metodo_della_riga_e_nessun_nome_fantasma(self):
        diff = "".join(f"+{riga}\n" for riga in self.UNA_RIGA.splitlines())

        aggiunti, tolti = runner.nomi_dei_test_junit(diff, "SchemaIT")

        assert aggiunti == ["SchemaIT#a", "SchemaIT#b"]
        assert tolti == set()


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


DATI = Path(__file__).resolve().parent / "dati" / "junit"


def scrive_i_rapporti(monkeypatch, *rapporti: tuple[str, str], codice: int = 0,
                      uscita: str = ""):
    """`esegui()` finto: non lancia niente, e lascia sotto la cartella di lancio i
    `(destinazione, file di dati)` dati, come farebbe Maven. `git` passa al vero
    `esegui()`: i test su un repository vero lo usano per leggere fase e commit."""
    vero = runner.esegui

    def finto(argv, cwd, **altri):
        if argv[0] == "git":
            return vero(argv, cwd, **altri)
        for destinazione, origine in rapporti:
            file = Path(cwd) / destinazione
            file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(DATI / origine, file)
        return codice, uscita

    monkeypatch.setattr(runner, "esegui", finto)


def comando_per(cartella: Path, *nomi: str):
    return runner.ComandoDiProva(cartella, ["./mvnw", "verify"], "junit",
                                 {nome: nome for nome in nomi})


class TestLEsitoSiLeggeDaiRapportiPerTest:
    """Criterio 5: surefire e failsafe, un esito per test (decisione 6)."""

    SCHEMA = "failsafe-reports/TEST-it.x.SchemaIT.xml"
    FOO = "surefire-reports/TEST-it.x.FooTest.xml"

    def esiti(self, monkeypatch, tmp_path, *nomi):
        scrive_i_rapporti(monkeypatch,
                          (f"target/{self.SCHEMA}", self.SCHEMA),
                          (f"target/{self.FOO}", self.FOO))
        esiti, _ = runner.esiti_del_comando(comando_per(tmp_path, *nomi))
        return esiti

    def test_un_caso_con_asserzione_mancata_e_rosso(self, monkeypatch, tmp_path):
        assert self.esiti(monkeypatch, tmp_path, "SchemaIT#a") == {"SchemaIT#a": "rosso"}

    def test_un_caso_passato_e_verde(self, monkeypatch, tmp_path):
        assert self.esiti(monkeypatch, tmp_path, "SchemaIT#b") == {"SchemaIT#b": "verde"}

    def test_un_caso_saltato_e_saltato(self, monkeypatch, tmp_path):
        assert self.esiti(monkeypatch, tmp_path, "SchemaIT#d") == {"SchemaIT#d": "saltato"}

    def test_un_test_senza_caso_e_nessuno(self, monkeypatch, tmp_path):
        assert self.esiti(monkeypatch, tmp_path, "SchemaIT#e") == {"SchemaIT#e": "nessuno"}

    def test_i_casi_di_un_parametrico_contano_per_il_metodo_e_vince_il_piu_forte(
            self, monkeypatch, tmp_path):
        assert self.esiti(monkeypatch, tmp_path, "SchemaIT#c") == {"SchemaIT#c": "rosso"}

    def test_un_errore_di_un_rapporto_di_surefire_e_rosso(self, monkeypatch, tmp_path):
        esiti = self.esiti(monkeypatch, tmp_path, "FooTest#f", "FooTest#g")

        assert esiti == {"FooTest#f": "verde", "FooTest#g": "rosso"}

    def test_i_rapporti_di_un_lancio_prima_non_si_leggono(self, monkeypatch, tmp_path):
        vecchio = tmp_path / "target" / self.SCHEMA
        vecchio.parent.mkdir(parents=True)
        shutil.copy(DATI / self.SCHEMA, vecchio)
        monkeypatch.setattr(runner, "esegui", lambda argv, cwd, **altri: (0, ""))

        esiti, _ = runner.esiti_del_comando(comando_per(tmp_path, "SchemaIT#a"))

        assert esiti == {"SchemaIT#a": "nessuno"}


class TestUnErroreDiCompilazioneValeRosso:
    """Criterio 6: il test che nomina una classe che non esiste ancora è il rosso
    più comune del test-first in Java, e Maven esce senza scrivere rapporti
    (decisione 8)."""

    USCITA = ("[ERROR] COMPILATION ERROR :\n"
              "[ERROR] /app/src/test/java/it/x/SchemaIT.java:[9,9] cannot find symbol\n"
              "[INFO] BUILD FAILURE\n")

    def test_vale_rosso_per_tutti_i_test_chiesti(self, monkeypatch, tmp_path):
        scrive_i_rapporti(monkeypatch, codice=1, uscita=self.USCITA)

        esiti, _ = runner.esiti_del_comando(comando_per(tmp_path, "SchemaIT#a", "AltraIT#m3"))

        assert esiti == {"SchemaIT#a": "rosso", "AltraIT#m3": "rosso"}

    def test_un_guasto_senza_rapporti_e_senza_compilazione_e_del_gate(
            self, monkeypatch, tmp_path):
        scrive_i_rapporti(monkeypatch, codice=1,
                          uscita="[ERROR] Could not resolve dependencies\n[INFO] BUILD FAILURE\n")

        with pytest.raises(runner.GuastoDelGate, match="Could not resolve dependencies"):
            runner.esiti_del_comando(comando_per(tmp_path, "SchemaIT#a"))


class TestChiediImplApreImplSuUnRedJunit:
    """Criterio 7: il giro di Java di `ada_planning`, fino in fondo. Il commit RED
    c'è, `[junit]` dichiara il comando, e i rapporti dicono rosso o verde."""

    def chiedi(self, repo, monkeypatch, esito):
        repo.commit("test(schema): lo schema ha le tabelle (RED)", {TEST_JAVA: SCHEMA_IT})
        runner.percorso_della_fase(repo.radice).write_text(f"{runner.FASE_TEST_ONLY}\n")
        monkeypatch.setattr(runner, "JUNIT_COMANDO", tuple(COMANDO_MAVEN))
        scrive_i_rapporti(monkeypatch, ("target/failsafe-reports/TEST-it.x.SchemaIT.xml",
                                        f"{esito}/failsafe-reports/TEST-it.x.SchemaIT.xml"),
                          codice=1 if esito == "rosso" else 0)
        return runner.chiedi_impl()

    def fase(self, repo):
        return runner.percorso_della_fase(repo.radice).read_text().strip()

    def test_con_il_rapporto_rosso_apre_impl(self, repo_java, monkeypatch):
        assert self.chiedi(repo_java, monkeypatch, "rosso") == 0
        assert self.fase(repo_java) == runner.FASE_IMPL

    def test_con_il_rapporto_verde_resta_in_test_only(self, repo_java, monkeypatch, capsys):
        assert self.chiedi(repo_java, monkeypatch, "verde") == 1
        assert self.fase(repo_java) == runner.FASE_TEST_ONLY
        assert "nato verde" in capsys.readouterr().out


# PBI-514: il diff vero di `d11525c` di `ada_planning`, e il file prima e dopo.
# Si salvano come `.diff` e `.txt`, mai come `.java`: sotto `tools/tests/` un
# `.java` sarebbe un test JUnit orfano (PBI-514, decisione 3).
TRIGGER_IT = "app/src/test/java/it/lais/interventi/db/TriggerGuastiIT.java"
TRIGGER_PRIMA = (DATI / "TriggerGuastiIT.prima.txt").read_text(encoding="utf-8")
TRIGGER_DOPO = (DATI / "TriggerGuastiIT.dopo.txt").read_text(encoding="utf-8")
TRIGGER_NATI = ["TriggerGuastiIT#unSitoConSoliStatiSospesiNonEGuastoMaESospeso",
                "TriggerGuastiIT#unSitoApertoChePerdeIlSuoUnicoGuastoDiventaSospesoEChiudeLEpisodio",
                "TriggerGuastiIT#unSitoSospesoCuiSiAggiungeUnGuastoDiventaApertoConUnEpisodio"]
TRIGGER_TOLTI = {
    "TriggerGuastiIT#unSitoConSoliGuastiNonPianificabiliESospeso",
    "TriggerGuastiIT#unSitoApertoChePerdeIlSuoUnicoGuastoPianificabileDiventaSospeso",
    "TriggerGuastiIT#unSitoSospesoCuiSiAggiungeUnGuastoPianificabileDiventaApertoNellStessoEpisodio",
}


class TestUnMetodoRinominatoSottoUnAnnotazioneDiContestoNasce:
    """PBI-514, criterio 1: il diff vero di `d11525c`, dove le annotazioni sono
    righe di contesto e cambia solo la riga del metodo."""

    def test_i_tre_metodi_rinominati_sono_aggiunti_e_i_tre_vecchi_tolti(self):
        diff = (DATI / "d11525c.diff").read_text(encoding="utf-8")

        aggiunti, tolti = runner.nomi_dei_test_junit(diff, "TriggerGuastiIT")

        assert aggiunti == TRIGGER_NATI
        assert tolti == TRIGGER_TOLTI


class TestTestNuoviDelCommitVedeIlCommitD11525c:
    """PBI-514, criterio 2: in un repository vero, col file prima e dopo."""

    def test_restituisce_i_tre_test_rinominati(self, repo_java):
        repo_java.commit("test(db): i trigger dei guasti", {TRIGGER_IT: TRIGGER_PRIMA})
        sha = repo_java.commit("test(db): solo GUASTO rende guasto il sito (RED)",
                               {TRIGGER_IT: TRIGGER_DOPO})

        nuovi = runner.test_nuovi_del_commit(sha)

        assert nuovi == [runner.TestNuovo(TRIGGER_IT, n, "junit") for n in TRIGGER_NATI]


class TestLaPosizioneDellAnnotazioneNonCambiaIlNome:
    """PBI-514, criterio 3: l'annotazione sul `+`, sul contesto o sulla stessa
    riga del metodo dà lo stesso nome; un metodo che il diff non tocca non nasce."""

    @pytest.mark.parametrize("diff, atteso", [
        pytest.param("+    @Test\n+    void m() {\n+    }\n",
                     (["X#m"], set()), id="annotazione-aggiunta"),
        pytest.param("     @ParameterizedTest\n"
                     "     @ValueSource(strings = {\"a\", \"b\"})\n"
                     "-    void vecchio(String s) {\n"
                     "+    void m(String s) {\n",
                     (["X#m"], {"X#vecchio"}), id="annotazione-di-contesto"),
        pytest.param("+    @Test void m() {\n+    }\n",
                     (["X#m"], set()), id="stessa-riga"),
        pytest.param("     @Test\n"
                     "     void m() {\n"
                     "-        assertEquals(1, valore());\n"
                     "+        assertEquals(2, valore());\n"
                     "     }\n",
                     ([], set()), id="non-toccato"),
    ])
    def test_il_nome_del_metodo(self, diff, atteso):
        assert runner.nomi_dei_test_junit(diff, "X") == atteso


class TestChiediImplApreImplSulRedDiD11525c:
    """PBI-514, criterio 5: il giro di PBI-015 di `ada_planning`, che col
    rapporto rosso restava in `TEST_ONLY` con «nessun test nuovo»."""

    RAPPORTO = "failsafe-reports/TEST-it.lais.interventi.db.TriggerGuastiIT.xml"

    def test_con_il_rapporto_rosso_apre_impl(self, repo_java, monkeypatch):
        repo_java.commit("test(db): i trigger dei guasti", {TRIGGER_IT: TRIGGER_PRIMA})
        repo_java.commit("test(db): solo GUASTO rende guasto il sito (RED)",
                         {TRIGGER_IT: TRIGGER_DOPO})
        fase = runner.percorso_della_fase(repo_java.radice)
        fase.write_text(f"{runner.FASE_TEST_ONLY}\n")
        monkeypatch.setattr(runner, "JUNIT_COMANDO", tuple(COMANDO_MAVEN))
        scrive_i_rapporti(monkeypatch, (f"target/{self.RAPPORTO}", f"rosso/{self.RAPPORTO}"),
                          codice=1)

        assert runner.chiedi_impl() == 0
        assert fase.read_text().strip() == runner.FASE_IMPL
