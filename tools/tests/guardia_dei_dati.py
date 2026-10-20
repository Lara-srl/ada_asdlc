"""La guardia di fine suite su `tools/tests/dati/` (PBI-518).

Un test che scrive nel progetto di prova lascia sporco l'albero del repository,
e il controllo dell'albero pulito ferma il giro (causa `test-senza-isolamento`).
"""

from pathlib import Path

DATI = Path(__file__).resolve().parent / "dati"


def elenco(cartella: Path) -> set[Path]:
    """I file e le cartelle sotto `cartella`, letti dal disco e non da `git
    status` (decisione 3): anche quelli che git ignora, che sono proprio quelli
    che le righe di `.gitignore` del progetto di prova nascondevano."""
    return set(cartella.rglob("*"))


def nati(prima: set[Path], dopo: set[Path]) -> list[str]:
    """I percorsi di `dopo` che in `prima` non c'erano, in ordine."""
    return sorted(str(p) for p in dopo - prima)
