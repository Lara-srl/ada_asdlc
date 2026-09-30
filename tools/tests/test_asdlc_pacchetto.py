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
    # Tutto il pacchetto e non i soli `.py`: i prompt sono file suoi (PBI-386).
    shutil.copytree(REPO / "tools" / "asdlc", pacchetto, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
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


# --- I comandi installabili (PBI-384) ----------------------------------------


COMANDI = ("asdlc-runner", "asdlc-coda", "asdlc-esito")


def installa_in_un_venv_pulito(tmp_path: Path) -> Path:
    """`pip install` di una **copia** di `tools/` in un venv nuovo, e il venv.

    Una copia: la build scrive `build/` e `asdlc.egg-info/` accanto al sorgente,
    e nel repository vero sporcherebbe l'albero del giro."""
    sorgente = tmp_path / "sorgente"
    shutil.copytree(REPO / "tools" / "asdlc", sorgente / "asdlc",
                    ignore=shutil.ignore_patterns("__pycache__"))
    if (REPO / "tools" / "pyproject.toml").exists():
        shutil.copy(REPO / "tools" / "pyproject.toml", sorgente / "pyproject.toml")
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True,
                   capture_output=True, timeout=120)

    installato = subprocess.run(
        [str(venv / "bin" / "pip"), "install", "-q", "--disable-pip-version-check",
         str(sorgente)], capture_output=True, text=True, timeout=600)

    assert installato.returncode == 0, installato.stdout + installato.stderr
    return venv


def test_pip_install_di_tools_in_un_venv_pulito_mette_i_tre_comandi_e_il_runner_risponde(
    tmp_path,
):
    """`pip install ./tools` è l'installazione del runner (`ADR-0026`, decisione 3):
    non editabile, in un venv suo. I tre punti d'ingresso finiscono nel `bin/`, e
    `asdlc-runner --help` risponde anche da una cartella che non è un progetto."""
    venv = installa_in_un_venv_pulito(tmp_path)

    for comando in COMANDI:
        assert (venv / "bin" / comando).is_file(), comando
    fuori = tmp_path / "fuori"
    fuori.mkdir()
    aiuto = subprocess.run([str(venv / "bin" / "asdlc-runner"), "--help"], cwd=fuori,
                           capture_output=True, text=True, timeout=60)
    assert aiuto.returncode == 0, aiuto.stdout + aiuto.stderr
    assert "--chiedi-impl" in aiuto.stdout


# --- I prompt come dati del pacchetto (PBI-386) ------------------------------


# Il ruolo e il nome del modulo che ne porta il testo, prima di `configura()`.
PROMPT_DEI_RUOLI = (("builder", "MODELLO_BUILDER"), ("igiene", "PROMPT_IGIENE"),
                    ("riprova", "PROMPT_RIPROVA"), ("critic", "MODELLO_CRITIC"),
                    ("rimedio", "MODELLO_RIMEDIO"))

LEGGI_I_PROMPT = f"""
from importlib.resources import files
from asdlc import runner
cartella = files("asdlc") / "prompt"
for ruolo, nome in {PROMPT_DEI_RUOLI!r}:
    assert getattr(runner, nome) == (cartella / f"{{ruolo}}.md").read_text(encoding="utf-8"), ruolo
print(runner.__file__)
"""


def test_il_runner_installato_legge_i_prompt_dal_pacchetto_senza_il_sorgente_accanto(tmp_path):
    """I cinque prompt sono file di `asdlc/prompt/` e viaggiano col pacchetto: il
    runner installato li legge da lì, lanciato da una cartella in cui il
    sorgente non c'è (`ADR-0026`, decisione 2)."""
    venv = installa_in_un_venv_pulito(tmp_path)
    fuori = tmp_path / "fuori"
    fuori.mkdir()

    letto = subprocess.run([str(venv / "bin" / "python"), "-c", LEGGI_I_PROMPT], cwd=fuori,
                           capture_output=True, text=True, timeout=60)

    assert letto.returncode == 0, letto.stdout + letto.stderr
    assert letto.stdout.strip().startswith(str(venv)), (
        "il runner che ha letto i prompt è quello installato, non il sorgente")
