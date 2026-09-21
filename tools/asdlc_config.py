"""Il lettore di `asdlc.toml`: i gate, i percorsi, le soglie e il ramo del runner.

Solo libreria standard, di proposito: `tomllib` è stdlib da Python 3.11, e un
runner che si legge la configurazione senza un `pip install` è un runner che si
copia in un altro progetto così com'è (`ADR-0017`, precondizione 2).
"""
from __future__ import annotations

from pathlib import Path


def carica(repo: Path) -> None:
    """Legge `asdlc.toml` dalla radice `repo`. Ancora vuoto: nasce con PBI-358."""
    return None
