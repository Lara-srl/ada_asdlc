"""PBI-515: il lucchetto non chiude i file di supporto dei test.

Ogni classe è un criterio della *Verifica* del PBI. Sotto `src/test/` nessun file
è produzione, e uno scheletro vuoto — righe bianche e commenti — si crea in
`TEST_ONLY`.
"""

import importlib

import pytest

from test_asdlc_runner import RepoDiProva

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


class TestInTestOnlyIlFileDiSupportoSiScrive:
    """Criterio 4: la guardia di fase in `TEST_ONLY` lascia scrivere lo script di
    supporto sotto `src/test/` e continua a chiudere quello di `tools/migrazione/`."""

    @pytest.mark.parametrize("percorso, bloccato", [(SUPPORTO, False), (MIGRAZIONE, True)])
    def test_la_guardia_lascia_il_supporto_e_chiude_la_migrazione(self, percorso, bloccato):
        ragione = runner.guardia_di_fase(runner.FASE_TEST_ONLY, percorso)

        assert (ragione is not None) is bloccato


@pytest.fixture
def repo_in_test_only(tmp_path, monkeypatch):
    """Un repository vero con la fase `TEST_ONLY` scritta: il `pre-commit` legge lo
    stage con `git`, e lo stage non si finge."""
    radice = tmp_path / "repo"
    radice.mkdir()
    repo = RepoDiProva(radice)
    monkeypatch.setattr(runner, "REPO", radice)
    runner.percorso_della_fase(radice).write_text(f"{runner.FASE_TEST_ONLY}\n")
    return repo


def metti_in_stage(repo, percorso, contenuto):
    f = repo.radice / percorso
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(contenuto, encoding="utf-8")
    repo._git("add", percorso)


class TestUnoScheletroVuotoPassaDalPreCommit:
    """Criterio 6: in `TEST_ONLY` il `pre-commit` lascia passare uno scheletro di
    produzione fatto di righe bianche e commenti, e chiude il file che ha una riga
    di codice."""

    @pytest.mark.parametrize("percorso, contenuto, uscita", [
        (MIGRAZIONE, "#!/bin/sh\n# riconcilia le pratiche\n\n# da scrivere\n", 0),
        ("db/V9__x.sql", "", 0),
        ("db/V9__x.sql", "-- ricalcola tutti\n\n-- da scrivere\n", 0),
        (MIGRAZIONE, "#!/bin/sh\n# riconcilia le pratiche\necho riconcilia\n", 1),
        ("db/V9__x.sql", "-- ricalcola tutti\nSELECT 1;\n", 1),
    ], ids=["sh-di-commenti", "sql-vuoto", "sql-di-commenti", "sh-con-codice", "sql-con-codice"])
    def test_lo_scheletro_passa_e_il_codice_resta_chiuso(
            self, repo_in_test_only, capsys, percorso, contenuto, uscita):
        metti_in_stage(repo_in_test_only, percorso, contenuto)

        assert runner.guardia_del_commit() == uscita
        assert (percorso in capsys.readouterr().out) is bool(uscita)
