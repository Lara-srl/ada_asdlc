"""La pausa per progetto (`backlog/PBI-535`).

Accanto alla pausa globale, `~/asdlc-tick.pausa`, che ferma ogni tick della
macchina, il tick guarda un file di pausa **del progetto**: `<registro>/pausa`
nel checkout, calcolato dal `repo` e non dal `LOG` che `conftest.py` sposta.

Qui nessun test parla col mondo: `decidi()` e `lancia()` registrano di essere
stati chiamati, e i passi del tick che toccano il checkout sono sostituiti.
"""

import contextlib
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

coda = importlib.import_module("asdlc.coda")
# L'import non legge `asdlc.toml` (PBI-382): la configurazione è quella del
# progetto di prova, come in `test_asdlc_coda.py`, col registro in `runs/`.
PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"
coda.REPO = PROGETTO
coda.configura(coda.asdlc_config.carica(PROGETTO))


@pytest.fixture(autouse=True)
def home_finta(tmp_path, monkeypatch):
    """`HOME` in `tmp_path`: la pausa globale di chi lancia i test non entra qui,
    e un test che la crea non ferma il cron vero."""
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    return casa


@pytest.fixture(autouse=True)
def passi_sostituiti(monkeypatch):
    """Il battito, il pin, l'allineamento, la reinstallazione e la verifica
    dell'ambiente non sono sotto prova: non fanno niente."""
    monkeypatch.setattr(coda, "batti", lambda repo: None)
    monkeypatch.setattr(coda, "pin", lambda repo: [])
    for nome in ("allinea", "reinstalla", "indietro"):
        monkeypatch.setattr(coda, nome, lambda *a, **k: None)
    monkeypatch.setattr(coda, "mancanze_dell_ambiente", lambda worktree: [])


@pytest.fixture
def chiamati(monkeypatch):
    """`decidi()` e `lancia()` che registrano di essere stati chiamati; la
    decisione è sempre di lanciare il PBI in testa."""
    registro: list[str] = []
    monkeypatch.setattr(coda, "decidi", lambda repo, worktree: (
        registro.append("decidi") or coda.Lancia("PBI-337")))
    monkeypatch.setattr(coda, "lancia", lambda pbi, worktree, **k: registro.append(
        f"lancia {pbi}"))
    return registro


def un_checkout(tmp_path: Path, nome: str = "repo") -> tuple[Path, Path]:
    """Un finto checkout con una voce da lanciare in `backlog/CODA.md`, e il
    worktree del runner accanto."""
    repo = tmp_path / nome
    (repo / "backlog").mkdir(parents=True)
    (repo / "backlog" / "CODA.md").write_text("- PBI-337\n", encoding="utf-8")
    albero = tmp_path / f"albero-{nome}"
    albero.mkdir()
    return repo, albero


def pausa_del_progetto_in(repo: Path, riga: str) -> Path:
    """Il file `<repo>/<registro>/pausa` con `riga`, come lo scriverebbe `--pausa`."""
    file = repo / coda.CFG.registro.cartella / "pausa"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(riga + "\n", encoding="utf-8")
    return file


def righe_del_log(repo: Path) -> list[str]:
    return (repo / coda.LOG).read_text(encoding="utf-8").splitlines()


# --- Criterio 1: con la pausa del progetto il tick non lancia e lo dice ---------


def test_con_la_pausa_del_progetto_il_tick_non_lancia_e_lo_scrive_nel_log(
        tmp_path, chiamati):
    """PBI-535, criterio 1 (decisioni 1 e 2). Il file `<registro>/pausa` del
    checkout ferma il tick come la pausa globale: niente decisione, niente
    lancio, e in `coda.log` la riga `in pausa: (progetto) <riga del file>`."""
    repo, albero = un_checkout(tmp_path)
    pausa_del_progetto_in(repo, "2026-10-31 10:00 prova")

    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 0
    assert chiamati == []
    righe = righe_del_log(repo)
    assert len(righe) == 1, righe
    assert righe[0].endswith("  in pausa: (progetto) 2026-10-31 10:00 prova"), righe


# --- Criterio 2: `--pausa` e `--togli-pausa` creano e tolgono il file ----------


@contextlib.contextmanager
def tenuto_da_un_figlio(file: Path):
    """Un processo figlio che prende il `flock` su `file` e lo tiene finché il
    blocco `with` non finisce: il lucchetto del tick lo tiene un tick in corso."""
    file.parent.mkdir(parents=True, exist_ok=True)
    figlio = subprocess.Popen(
        [sys.executable, "-c",
         "import fcntl, sys\n"
         "f = open(sys.argv[1], 'w')\n"
         "fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
         "print('preso', flush=True)\n"
         "sys.stdin.read()\n",
         str(file)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert figlio.stdout.readline().strip() == "preso"
        yield
    finally:
        figlio.stdin.close()
        figlio.wait(timeout=10)


def test_pausa_e_togli_pausa_creano_e_tolgono_il_file_senza_decidere(tmp_path, chiamati):
    """PBI-535, criterio 2 (decisione 3). `--pausa MOTIVO` scrive il file del
    progetto col motivo ed esce 0; `--togli-pausa` lo toglie, e senza file esce 0
    lo stesso. Nessuno dei due decide o lancia."""
    repo, albero = un_checkout(tmp_path)
    file = repo / coda.CFG.registro.cartella / "pausa"

    assert coda.smista(["--repo", str(repo), "--worktree", str(albero),
                        "--pausa", "prova"]) == 0
    assert file.exists()
    assert "prova" in file.read_text(encoding="utf-8")

    assert coda.smista(["--repo", str(repo), "--worktree", str(albero),
                        "--togli-pausa"]) == 0
    assert not file.exists()

    assert coda.smista(["--repo", str(repo), "--worktree", str(albero),
                        "--togli-pausa"]) == 0
    assert not file.exists()
    assert chiamati == []


def test_pausa_col_lucchetto_del_tick_tenuto_esce_2_e_non_scrive_il_file(
        tmp_path, chiamati, capsys):
    """PBI-535, criterio 2 (decisione 3). Il flag prende il lucchetto del tick,
    come `asdlc-chiudi-giro`: se lo tiene un tick in corso esce 2, lo dice, e il
    file non c'è."""
    repo, albero = un_checkout(tmp_path)
    file = repo / coda.CFG.registro.cartella / "pausa"

    with tenuto_da_un_figlio(repo / coda.LUCCHETTO_DEL_TICK):
        uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero),
                              "--pausa", "prova"])

    assert uscita == 2
    assert not file.exists()
    assert chiamati == []
    uscite = capsys.readouterr()
    assert ("è tenuto: un tick è in corso in questo checkout: riprova fra un minuto."
            in uscite.out + uscite.err)


# --- Criterio 3: la pausa di un progetto non ferma un altro ---------------------


def test_guardia_la_pausa_di_un_progetto_non_ferma_un_altro(tmp_path, chiamati):
    """PBI-535, criterio 3. Due checkout, la pausa solo nel primo: il tick del
    primo non lancia, quello del secondo sì. La pausa del progetto si legge dal
    `repo` del tick, non da un posto comune ai due."""
    fermo, albero_fermo = un_checkout(tmp_path, "fermo")
    libero, albero_libero = un_checkout(tmp_path, "libero")
    pausa_del_progetto_in(fermo, "2026-10-31 10:00 prova")

    assert coda.smista(["--repo", str(fermo), "--worktree", str(albero_fermo)]) == 0
    assert chiamati == []

    assert coda.smista(["--repo", str(libero), "--worktree", str(albero_libero)]) == 0
    assert chiamati == ["decidi", "lancia PBI-337"]


# --- Criterio 4: la pausa globale vale ancora, e `--togli-pausa` non la toglie --


def test_guardia_la_pausa_globale_vale_ancora_e_togli_pausa_non_la_toglie(
        tmp_path, home_finta, chiamati):
    """PBI-535, criterio 4 (decisioni 2 e 4). Con la pausa globale e quella del
    progetto il tick non lancia e scrive **una** riga, la globale. `--togli-pausa`
    toglie solo il file del progetto: `~/asdlc-tick.pausa` resta, e il tick dopo
    è ancora fermo, con la riga globale."""
    repo, albero = un_checkout(tmp_path)
    globale = home_finta / "asdlc-tick.pausa"
    globale.write_text("2026-10-31 09:00 asdlc-chiudi-giro PBI-7\n", encoding="utf-8")
    del_progetto = pausa_del_progetto_in(repo, "2026-10-31 10:00 prova")

    assert coda.smista(["--repo", str(repo), "--worktree", str(albero)]) == 0
    assert chiamati == []
    righe = righe_del_log(repo)
    assert len(righe) == 1, righe
    assert righe[0].endswith("  in pausa: 2026-10-31 09:00 asdlc-chiudi-giro PBI-7"), righe

    assert coda.smista(["--repo", str(repo), "--worktree", str(albero),
                        "--togli-pausa"]) == 0
    assert not del_progetto.exists()
    assert globale.read_text(encoding="utf-8") == "2026-10-31 09:00 asdlc-chiudi-giro PBI-7\n"

    assert coda.smista(["--repo", str(repo), "--worktree", str(albero)]) == 0
    assert chiamati == []
    righe = righe_del_log(repo)
    assert len(righe) == 2, righe
    assert righe[1].endswith("  in pausa: 2026-10-31 09:00 asdlc-chiudi-giro PBI-7"), righe
