"""`asdlc-stato`: ciò che il tick vede adesso, progetto per progetto (PBI-534).

È di sola lettura e non decide niente di suo: la decisione è quella di
`coda.decidi()`, raccontata da `coda.racconta()`, così il comando dice ciò che
farebbe il tick e non è una seconda verità.
"""
from __future__ import annotations

import argparse
import json
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
    pbi = getattr(decisione, "pbi", None)
    esito = coda.ultimo_esito(coda.WORKTREE_DEL_RUNNER, pbi) if pbi else None
    return {
        "progetto": checkout.resolve().name,
        "decisione": coda.racconta(decisione),
        "voce": voce_di(decisione),
        # Lo stato e il motivo dell'ultimo rapporto del runner su quel PBI.
        "esito": ({"stato": esito.get("stato"), "motivo": esito.get("motivo")}
                  if esito is not None else None),
        # Gli URL delle PR aperte sul ramo del PBI, `None` se `gh` non risponde.
        "pr": list(pr) if pbi and (pr := coda.pr_sul_ramo(checkout, pbi)) is not None
        else None if pbi else [],
        "pausa": None,
        "allineato": None,
        "installato": None,
        "pin": None,
    }


def riga(dato: dict) -> str:
    esito = dato["esito"]
    pr = dato["pr"]
    return " · ".join([
        dato["progetto"],
        dato["decisione"],
        dato["voce"] or "-",
        f"{esito['stato']} {esito['motivo']}" if esito is not None else "-",
        "PR " + ("?" if pr is None else ", ".join(pr) or "-"),
    ])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", type=Path, help="il checkout di un progetto")
    ap.add_argument("--json", action="store_true",
                    help="un oggetto JSON per progetto invece della riga")
    a = ap.parse_args(argv)
    dati = [stato_di(a.repo)]
    if a.json:
        print(json.dumps(dati, ensure_ascii=False, indent=2))
    else:
        for dato in dati:
            print(riga(dato))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
