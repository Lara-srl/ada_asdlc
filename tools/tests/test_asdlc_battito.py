"""Il battito del tick (`backlog/PBI-510`, `ADR-0030` decisione 5).

A ogni passaggio il tick scrive l'ora in `~/asdlc-tick.battito`; al passaggio dopo,
se il distacco dal battito precedente supera la soglia, avvisa nel log. L'ora è un
parametro dei test: `coda.adesso` è sostituito, mai l'orologio vero. `decidi()` e
`lancia()` sono sostituiti come negli altri test del tick: nessun test parla con
`gh` o avvia un giro.

Il modulo si carica per nome, `asdlc.coda`: `conftest.py` mette `tools/` sul
`sys.path` (PBI-383).
"""

import datetime
import importlib
import tomllib
from pathlib import Path

import pytest

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"

coda = importlib.import_module("asdlc.coda")
coda.REPO = PROGETTO
coda.configura(coda.asdlc_config.carica(PROGETTO))

MEZZOGIORNO = datetime.datetime(2026, 10, 19, 12, 0, 0)


@pytest.fixture(autouse=True)
def mondo_finto(tmp_path, monkeypatch):
    """`HOME` in una cartella temporanea, e il tick senza contatti col mondo."""
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    for nome in ("allinea", "reinstalla", "indietro"):
        monkeypatch.setattr(coda, nome, lambda *a, **k: None, raising=False)
    monkeypatch.setattr(coda, "pin", lambda repo: [])
    monkeypatch.setattr(coda, "rilascia", lambda repo: [])
    monkeypatch.setattr(coda, "mancanze_dell_ambiente", lambda worktree: [], raising=False)
    return casa


def alle(monkeypatch, ora):
    """Il tick crede che sia `ora`."""
    monkeypatch.setattr(coda, "adesso", lambda: ora, raising=False)


def passaggio(tmp_path, monkeypatch, decisione=None):
    """Un passaggio del tick su un finto checkout; `decisione` di default è «finita»."""
    repo = tmp_path / "repo"
    (repo / "backlog").mkdir(parents=True, exist_ok=True)
    albero = tmp_path / "albero"
    albero.mkdir(exist_ok=True)
    monkeypatch.setattr(coda, "decidi", lambda repo, worktree: decisione or coda.Finita())
    monkeypatch.setattr(coda, "lancia", lambda pbi, worktree: None)
    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])
    return uscita, repo


def test_il_tick_scrive_il_battito_a_ogni_passaggio_anche_senza_lanciare_niente(
    mondo_finto, tmp_path, monkeypatch
):
    """Criterio 1. Con la coda finita il tick non lancia niente, e batte lo stesso:
    `~/asdlc-tick.battito` porta l'ora in ISO su una riga."""
    alle(monkeypatch, MEZZOGIORNO)

    uscita, _ = passaggio(tmp_path, monkeypatch)

    assert uscita == 0
    battito = mondo_finto / "asdlc-tick.battito"
    assert battito.read_text(encoding="utf-8") == "2026-10-19T12:00:00\n"



def test_il_tick_in_pausa_batte_lo_stesso(mondo_finto, tmp_path, monkeypatch):
    """Criterio 2, decisione 3. La pausa è un gesto, non un guasto: un tick fermo da
    un file di pausa scrive il battito come uno che lancia, e al ritorno non avvisa
    di un silenzio che non c'è stato."""
    (mondo_finto / "asdlc-tick.pausa").write_text("2026-10-19 11:00 a mano\n", encoding="utf-8")
    alle(monkeypatch, MEZZOGIORNO)

    uscita, repo = passaggio(tmp_path, monkeypatch)

    assert uscita == 0
    assert (repo / coda.LOG).read_text(encoding="utf-8").count("in pausa:") == 1
    assert (mondo_finto / "asdlc-tick.battito").read_text(encoding="utf-8") == "2026-10-19T12:00:00\n"


def battito_di(casa, ora):
    """Il battito che un passaggio precedente ha lasciato, all'ora data."""
    (casa / "asdlc-tick.battito").write_text(ora.isoformat(timespec="seconds") + "\n",
                                              encoding="utf-8")


def test_un_distacco_di_31_minuti_scrive_l_avviso_nel_log_e_a_schermo(
    mondo_finto, tmp_path, monkeypatch, capsys
):
    """Criterio 3, decisione 4. Il battito precedente è di 31 minuti prima, oltre la
    soglia di 30: il tick lo dice nel log e a schermo, prima di fare altro."""
    battito_di(mondo_finto, MEZZOGIORNO - datetime.timedelta(minutes=31))
    alle(monkeypatch, MEZZOGIORNO)

    uscita, repo = passaggio(tmp_path, monkeypatch)

    assert uscita == 0
    righe = (repo / coda.LOG).read_text(encoding="utf-8").splitlines()
    avvisi = [r for r in righe if "avviso" in r and "battito" in r]
    assert len(avvisi) == 1 and "31 minuti" in avvisi[0], righe
    assert avvisi[0].split("  ", 1)[1] in capsys.readouterr().out
    assert righe.index(avvisi[0]) == 0, righe


def test_l_avviso_viene_prima_delle_righe_del_pin(mondo_finto, tmp_path, monkeypatch):
    """Criterio 3, decisione 4, «prima di fare altro». Il pin ha qualcosa da dire e il
    battito precedente è di 31 minuti prima: la prima riga del log è l'avviso, la
    riga del pin viene dopo. Il battito non aspetta il pin, che parla con `git` e `gh`."""
    monkeypatch.setattr(coda, "pin", lambda repo: ["pin: qualcosa"])
    battito_di(mondo_finto, MEZZOGIORNO - datetime.timedelta(minutes=31))
    alle(monkeypatch, MEZZOGIORNO)

    _, repo = passaggio(tmp_path, monkeypatch)

    righe = (repo / coda.LOG).read_text(encoding="utf-8").splitlines()
    assert "avviso" in righe[0] and "battito" in righe[0], righe
    assert righe[1].endswith("  pin: qualcosa"), righe


def test_il_battito_si_scrive_anche_se_il_pin_solleva(mondo_finto, tmp_path, monkeypatch):
    """Criterio 1. Se `pin()` solleva, il passaggio cade ma il battito è già scritto:
    il passaggio dopo non avvisa di un silenzio falso."""
    def pin_rotto(repo):
        raise RuntimeError("gh non risponde")
    monkeypatch.setattr(coda, "pin", pin_rotto)
    alle(monkeypatch, MEZZOGIORNO)

    with pytest.raises(RuntimeError):
        passaggio(tmp_path, monkeypatch)

    assert (mondo_finto / "asdlc-tick.battito").read_text(encoding="utf-8") == "2026-10-19T12:00:00\n"




def test_il_distacco_avvisa_solo_oltre_la_soglia_29_30_e_31_minuti(
    mondo_finto, tmp_path, monkeypatch
):
    """Criterio 3, il confine. A 29 minuti il tick tace, a 30 esatti tace ancora
    («oltre» non è «alla» soglia), a 31 avvisa."""
    avvisati = {}
    for minuti in (29, 30, 31):
        battito_di(mondo_finto, MEZZOGIORNO - datetime.timedelta(minutes=minuti))
        alle(monkeypatch, MEZZOGIORNO)
        _, repo = passaggio(tmp_path / f"m{minuti}", monkeypatch)
        log = (repo / coda.LOG).read_text(encoding="utf-8")
        avvisati[minuti] = "battito precedente" in log

    assert avvisati == {29: False, 30: False, 31: True}


def test_un_battito_che_manca_non_e_un_avviso_e_il_primo_passaggio_lo_scrive(
    mondo_finto, tmp_path, monkeypatch, capsys
):
    """Criterio 4, decisione 2. Il primo passaggio assoluto non trova il file: è «mai
    partito», non una violazione. Il tick tace e lascia il suo primo battito."""
    alle(monkeypatch, MEZZOGIORNO)
    assert not (mondo_finto / "asdlc-tick.battito").exists()

    uscita, repo = passaggio(tmp_path, monkeypatch)

    assert uscita == 0
    assert "battito" not in (repo / coda.LOG).read_text(encoding="utf-8")
    assert "battito" not in capsys.readouterr().out
    assert (mondo_finto / "asdlc-tick.battito").read_text(encoding="utf-8") == "2026-10-19T12:00:00\n"


def configurazione(sezione: str = ""):
    """La configurazione del progetto di prova con sopra la sezione data."""
    testo = (PROGETTO / "asdlc.toml").read_text(encoding="utf-8") + "\n" + sezione
    return coda.asdlc_config.interpreta(tomllib.loads(testo), "asdlc.toml")


@pytest.fixture
def soglia_da_toml():
    """Il tick con la configurazione data, e quella di prova rimessa alla fine."""
    def configura(sezione):
        coda.configura(configurazione(sezione))
    yield configura
    coda.configura(coda.asdlc_config.carica(PROGETTO))


def test_la_soglia_si_legge_da_tick_nel_file_di_configurazione(
    mondo_finto, tmp_path, monkeypatch, soglia_da_toml
):
    """Criterio 5. Con `[tick].soglia_battito_minuti = 10`, 11 minuti di distacco
    avvisano: con la soglia fissa di 30 non succederebbe."""
    soglia_da_toml("[tick]\nsoglia_battito_minuti = 10\n")
    battito_di(mondo_finto, MEZZOGIORNO - datetime.timedelta(minutes=11))
    alle(monkeypatch, MEZZOGIORNO)

    _, repo = passaggio(tmp_path, monkeypatch)

    righe = (repo / coda.LOG).read_text(encoding="utf-8").splitlines()
    avvisi = [r for r in righe if "avviso" in r and "battito" in r]
    assert len(avvisi) == 1 and "11 minuti" in avvisi[0], righe


def test_l_avviso_non_ferma_il_tick_che_lancia_come_prima(mondo_finto, tmp_path, monkeypatch):
    """Criterio 6, `ADR-0008`. Dopo l'avviso il passaggio prosegue: la testa della
    coda parte, e il log ha l'avviso seguito dalla riga `lancia:`."""
    battito_di(mondo_finto, MEZZOGIORNO - datetime.timedelta(minutes=90))
    alle(monkeypatch, MEZZOGIORNO)
    lanciati = []
    repo = tmp_path / "repo"
    (repo / "backlog").mkdir(parents=True)
    albero = tmp_path / "albero"
    albero.mkdir()
    monkeypatch.setattr(coda, "decidi", lambda repo, worktree: coda.Lancia("PBI-337"))
    monkeypatch.setattr(coda, "lancia", lambda pbi, worktree: lanciati.append(pbi))

    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 0
    assert lanciati == ["PBI-337"]
    righe = (repo / coda.LOG).read_text(encoding="utf-8").splitlines()
    assert "avviso" in righe[0] and righe[1].endswith("  lancia: PBI-337"), righe
