#!/usr/bin/env python3
"""`asdlc-chiudi-giro PBI-XXX`: un giro fermato si chiude con un comando (PBI-385)."""
from __future__ import annotations

import sys
from pathlib import Path

# Lanciato per percorso, come il tick: `tools/` sul `sys.path`.
SORGENTE = Path(__file__).resolve().parent.parent
if str(SORGENTE) not in sys.path:
    sys.path.insert(0, str(SORGENTE))


def smista(argv: list[str] | None = None) -> int:
    return 0


def main(argv: list[str] | None = None) -> int:
    return smista(argv)


if __name__ == "__main__":
    raise SystemExit(main())
