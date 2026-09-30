"""Il runner è il pacchetto `asdlc`, in `tools/asdlc/` (PBI-383).

`conftest.py` mette `tools/` sul `sys.path`, e i moduli si trovano per nome:
`asdlc.runner`, `asdlc.coda`, `asdlc.config`, `asdlc.esito`.
"""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def trovato(nome: str):
    """La spec del modulo, o `None`. Senza il pacchetto `find_spec` di un
    sottomodulo alza invece di rispondere, e un errore non è un rosso."""
    try:
        return importlib.util.find_spec(nome)
    except ModuleNotFoundError:
        return None


@pytest.mark.parametrize("nome", ["asdlc.runner", "asdlc.coda", "asdlc.config", "asdlc.esito"])
def test_i_moduli_del_runner_si_trovano_nel_pacchetto_asdlc(nome):
    assert trovato(nome) is not None, nome


# --- Lanciati come script dalla radice del progetto --------------------------


def un_progetto_col_pacchetto(tmp_path: Path) -> Path:
    """Un progetto con la forma di aDa: il pacchetto in `tools/asdlc/`,
    l'`asdlc.toml` versionato, il PBI in `backlog/` e un `origin/main`.

    Non la radice vera: lì il lucchetto e `agenti_estranei()` vedono il giro
    che sta girando, e il lancio si rifiuta per una ragione che non è l'import.
    Il worktree del tick punta a una cartella che non c'è, e `gh` senza remoto
    dà la barriera: niente del lancio esce dalla cartella temporanea."""
    progetto = tmp_path / "progetto"
    pacchetto = progetto / "tools" / "asdlc"
    pacchetto.mkdir(parents=True)
    for sorgente in (REPO / "tools" / "asdlc").glob("*.py"):
        shutil.copy(sorgente, pacchetto / sorgente.name)
    shutil.copy(REPO / "asdlc.toml", progetto / "asdlc.toml")
    # Il percorso di macchina nel file locale, che è il suo posto (PBI-384).
    (progetto / "asdlc.local.toml").write_text(
        f'[worktree]\npercorso = "{tmp_path / "altro"}"\n', encoding="utf-8")
    (progetto / "backlog").mkdir()
    for pbi in (REPO / "backlog").glob("PBI-383-*.md"):
        shutil.copy(pbi, progetto / "backlog" / pbi.name)
    (progetto / "backlog" / "CODA.md").write_text("", encoding="utf-8")
    git = ["git", "-c", "user.name=prova", "-c", "user.email=prova@example.invalid"]
    for comando in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "progetto"],
                    ["update-ref", "refs/remotes/origin/main", "HEAD"]):
        subprocess.run([*git, *comando], cwd=progetto, check=True, capture_output=True)
    return progetto


def lancia_dalla_radice(progetto: Path, argomenti: list[str]):
    """Una sessione sua: il runner da leader di sessione non si stacca, e
    l'exit code è quello del giro."""
    return subprocess.run([sys.executable, *argomenti], cwd=progetto, capture_output=True,
                          text=True, timeout=60, start_new_session=True)


def test_il_runner_lanciato_dalla_radice_come_tools_asdlc_runner_fa_il_dry_run(tmp_path):
    progetto = un_progetto_col_pacchetto(tmp_path)

    fatto = lancia_dalla_radice(progetto, ["tools/asdlc/runner.py", "--dry-run", "PBI-383"])

    assert fatto.returncode == 0, fatto.stdout + fatto.stderr
    assert "backlog/PBI-383-il-runner-diventa-un-pacchetto.md" in fatto.stdout


def test_il_tick_lanciato_dalla_radice_come_tools_asdlc_coda_fa_il_dry_run(tmp_path):
    progetto = un_progetto_col_pacchetto(tmp_path)

    fatto = lancia_dalla_radice(progetto, ["tools/asdlc/coda.py", "--dry-run"])

    assert fatto.returncode == 0, fatto.stdout + fatto.stderr
