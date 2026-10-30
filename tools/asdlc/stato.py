"""`asdlc-stato`: ciò che il tick vede adesso, progetto per progetto (PBI-534).

È di sola lettura e non decide niente di suo: la decisione è quella di
`coda.decidi()`, raccontata da `coda.racconta()`, così il comando dice ciò che
farebbe il tick e non è una seconda verità.
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

from asdlc import coda


class ElencoIlleggibile(Exception):
    """L'elenco dei progetti manca o non si legge: il comando esce 2."""


def file_dei_progetti() -> Path:
    """`~/.config/asdlc/progetti.toml`: l'elenco è di macchina, come la pausa, e
    sta fuori dai repository. Calcolato quando serve: i test spostano `HOME`."""
    return Path.home() / ".config" / "asdlc" / "progetti.toml"


def progetti() -> list[Path]:
    """I checkout di `progetti.toml` (`checkout = [...]`), nell'ordine del file."""
    file = file_dei_progetti()
    try:
        checkout = tomllib.loads(file.read_text(encoding="utf-8")).get("checkout")
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as illeggibile:
        raise ElencoIlleggibile(f"l'elenco dei progetti {file} non si legge — "
                                f"{illeggibile}") from None
    if not isinstance(checkout, list) or not all(isinstance(c, str) for c in checkout):
        raise ElencoIlleggibile(f"l'elenco dei progetti {file} non ha `checkout = "
                                "[\"/percorso\", …]`")
    return [Path(c).expanduser() for c in checkout]


def nome_di(checkout: Path) -> str:
    """Il nome del progetto è la cartella del suo checkout (decisione 1)."""
    return checkout.resolve().name


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
        "progetto": nome_di(checkout),
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


NON_RAGGIUNGIBILE = "non raggiungibile"


def stato_o_guasto(checkout: Path) -> dict:
    """`stato_di()`, o il progetto «non raggiungibile» col motivo: un progetto che
    non si legge non ferma gli altri (decisione 4, `ADR-0008`). Le altre chiavi
    restano `None`."""
    try:
        return stato_di(checkout)
    except Exception as guasto:  # noqa: BLE001 — qualunque guasto è di quel progetto
        motivo = coda.in_una_riga(str(guasto) or type(guasto).__name__)
        return {"progetto": nome_di(checkout),
                "decisione": f"{NON_RAGGIUNGIBILE} — {motivo}",
                "voce": None, "esito": None, "pr": None, "pausa": None,
                "allineato": None, "installato": None, "pin": None}


def riga(dato: dict) -> str:
    if dato["decisione"].startswith(NON_RAGGIUNGIBILE):
        return f"{dato['progetto']} · {dato['decisione']}"
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
    ap.add_argument("nome", nargs="?",
                    help="il progetto da mostrare, cioè la cartella del suo checkout; "
                         "senza, tutti quelli di ~/.config/asdlc/progetti.toml")
    ap.add_argument("--repo", type=Path,
                    help="il checkout di un progetto, senza passare dall'elenco")
    ap.add_argument("--json", action="store_true",
                    help="un oggetto JSON per progetto invece della riga")
    a = ap.parse_args(argv)
    if a.repo is not None:
        checkout = [a.repo]
    else:
        try:
            checkout = progetti()
        except ElencoIlleggibile as guasto:
            print(f"asdlc-stato: {guasto}", file=sys.stderr)
            return 2
        if a.nome is not None:
            checkout = [c for c in checkout if nome_di(c) == a.nome]
            if not checkout:
                print(f"asdlc-stato: nessun progetto «{a.nome}» in {file_dei_progetti()}",
                      file=sys.stderr)
                return 2
    dati = [stato_o_guasto(c) for c in checkout]
    if a.json:
        print(json.dumps(dati, ensure_ascii=False, indent=2))
    else:
        for dato in dati:
            print(riga(dato))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
