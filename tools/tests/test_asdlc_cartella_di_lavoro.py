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
