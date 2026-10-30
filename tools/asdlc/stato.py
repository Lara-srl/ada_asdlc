"""`asdlc-stato`: ciò che il tick vede adesso, progetto per progetto (PBI-534).

È di sola lettura e non decide niente di suo: la decisione è quella di
`coda.decidi()`, raccontata da `coda.racconta()`, così il comando dice ciò che
farebbe il tick e non è una seconda verità.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from asdlc import coda


def voce_di(decisione: coda.Decisione) -> str | None:
    """La voce della coda su cui il tick si ferma: il PBI o il testo della barriera."""
    if isinstance(decisione, coda.Barriera):
        return decisione.testo
    return getattr(decisione, "pbi", None)


def stato_di(checkout: Path) -> dict:
    """Lo stato di un progetto. `coda` ha le costanti di un progetto solo: si
    configura con l'`asdlc.toml` di questo checkout prima di decidere."""
    coda.configura(coda.asdlc_config.carica(checkout))
    decisione = coda.decidi(checkout, coda.WORKTREE_DEL_RUNNER)
    return {
        "progetto": checkout.resolve().name,
        "decisione": coda.racconta(decisione),
        "voce": voce_di(decisione),
    }


def riga(dato: dict) -> str:
    return " · ".join([dato["progetto"], dato["decisione"], dato["voce"] or "-"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", type=Path, help="il checkout di un progetto")
    a = ap.parse_args(argv)
    print(riga(stato_di(a.repo)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
