"""La pausa per progetto (`backlog/PBI-535`).

Accanto alla pausa globale, `~/asdlc-tick.pausa`, che ferma ogni tick della
macchina, il tick guarda un file di pausa **del progetto**: `<registro>/pausa`
nel checkout, calcolato dal `repo` e non dal `LOG` che `conftest.py` sposta.

Qui nessun test parla col mondo: `decidi()` e `lancia()` registrano di essere
stati chiamati, e i passi del tick che toccano il checkout sono sostituiti.
"""

import importlib
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
