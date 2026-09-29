"""Il progetto è la cartella di lavoro, non la cartella del codice (PBI-382).

Installato, il runner sta in site-packages (`ADR-0026`, decisione 3), e
`Path(__file__).parent.parent` non è più il repository. Qui il codice si copia
in una cartella temporanea **senza** `asdlc.toml` e si lancia da un'altra: se
leggesse il progetto da dove sta il suo sorgente, lo si vedrebbe.

I moduli si lanciano in un processo figlio, e non con `importlib` come negli
altri test: la cwd e l'import sono proprio ciò che si prova, e cambiarli nel
processo di pytest li cambierebbe a tutta la suite.
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULI = ("asdlc_runner.py", "asdlc_coda.py", "asdlc_config.py", "asdlc_esito.py")


def copia_il_codice(tmp_path: Path) -> Path:
    """I moduli in `<tmp>/codice/tools`, lontani da ogni `asdlc.toml`."""
    tools = tmp_path / "codice" / "tools"
    tools.mkdir(parents=True)
    for nome in MODULI:
        shutil.copy(REPO / "tools" / nome, tools / nome)
    return tools


def test_importare_runner_e_tick_non_legge_asdlc_toml(tmp_path):
    """Un modulo importato con la cwd in una cartella qualsiasi non fallisce: la
    configurazione si legge quando si lancia, non quando si importa."""
    tools = copia_il_codice(tmp_path)
    vuota = tmp_path / "vuota"
    vuota.mkdir()

    fatto = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(tools)!r}); import asdlc_runner, asdlc_coda"],
        cwd=vuota, capture_output=True, text=True, timeout=60,
    )

    assert fatto.returncode == 0, fatto.stderr


def tutti_i_file(cartella: Path) -> set[Path]:
    return {p.relative_to(cartella) for p in cartella.rglob("*")}


def lancia(tools: Path, modulo: str, argomenti: list[str], cwd: Path):
    """`-B`: il `__pycache__` accanto al codice copiato non è una scrittura del
    runner, e renderebbe cieco il confronto dei file."""
    return subprocess.run([sys.executable, "-B", str(tools / modulo), *argomenti],
                          cwd=cwd, capture_output=True, text=True, timeout=60)


def test_runner_e_tick_senza_asdlc_toml_dalla_cwd_in_su_escono_col_motivo(tmp_path):
    """Il messaggio nomina la cwd, e prima non c'è nient'altro: né il lucchetto sotto
    `runs/`, né un worktree, né il rapporto del giro."""
    tools = copia_il_codice(tmp_path)
    vuota = tmp_path / "vuota"
    vuota.mkdir()
    prima = tutti_i_file(tmp_path)

    for modulo, argomenti in (("asdlc_runner.py", ["PBI-1", "--in-primo-piano"]),
                              ("asdlc_coda.py", ["--dry-run"])):
        fatto = lancia(tools, modulo, argomenti, vuota)

        assert fatto.returncode != 0, modulo
        assert (f"nessun `asdlc.toml` da `{vuota}` in su: il runner si lancia dalla "
                "cartella di un progetto ASDLC") in fatto.stderr, (modulo, fatto.stderr)
        assert tutti_i_file(tmp_path) - prima == set(), modulo
