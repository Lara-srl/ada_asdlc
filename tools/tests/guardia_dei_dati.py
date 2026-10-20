"""La guardia di fine suite su `tools/tests/dati/` (PBI-518).

Un test che scrive nel progetto di prova lascia sporco l'albero del repository,
e il controllo dell'albero pulito ferma il giro (causa `test-senza-isolamento`).
"""

from pathlib import Path

DATI = Path(__file__).resolve().parent / "dati"


def elenco(cartella: Path) -> set[Path]:
    """I file e le cartelle sotto `cartella`."""
    return set()


def nati(prima: set[Path], dopo: set[Path]) -> list[str]:
    """I percorsi di `dopo` che in `prima` non c'erano."""
    return []
