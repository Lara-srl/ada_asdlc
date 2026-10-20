"""La pre-verifica dei PBI in codice (`backlog/PBI-520`).

`asdlc-runner PBI-N --preverifica` legge il file del PBI alla base e scrive un
rapporto: i rilievi di forma, che fanno uscire 1, e gli avvisi, che non cambiano
il codice d'uscita. Su `main` le funzioni e il flag non esistono: i test le
prendono con `getattr(runner, "…", None)` e un `assert`, così il rosso è per
asserzione e non un errore di import.

Il runner si carica per nome, `asdlc.runner`: `conftest.py` mette `tools/` sul
`sys.path` (PBI-383).
"""

import importlib
from pathlib import Path

import pytest

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"

runner = importlib.import_module("asdlc.runner")
# Come in `test_asdlc_runner.py`: la radice e la configurazione sono quelle del
# progetto di prova, e l'import non legge `asdlc.toml` (PBI-382, PBI-394).
runner.REPO = PROGETTO
runner.configura(runner.asdlc_config.carica(PROGETTO))


def pbi(scope: str | None = "- `backlog/PBI-520-la-preverifica-in-codice.md` — questo file.",
        verifica: str | None = "- [ ] **Un criterio.** Con la sua riga rientrata\n"
                               "      sotto (pytest).") -> str:
    """Il testo di un PBI col formato del backlog: lo Scope e la Verifica si tolgono
    passando `None`."""
    parti = ["# PBI-520: una prova\n", "## Direttiva\n", "Una direttiva.\n"]
    if scope is not None:
        parti.append(f"**Scope**\n\n{scope}\n")
    parti += ["## Dipendenze\n", "- Bloccato da: nessuno.\n"]
    if verifica is not None:
        parti.append(f"## Verifica\n\n{verifica}\n")
    parti += ["## Protocollo di rifinitura\n", "- [ ] una casella fuori dalla Verifica\n"]
    return "\n".join(parti)


@pytest.mark.parametrize(
    "testo, attesi",
    [
        pytest.param(pbi(verifica=None), 1, id="senza-verifica"),
        pytest.param(pbi(verifica="Solo prosa, nessuna casella."), 1, id="verifica-senza-criteri"),
        pytest.param(pbi(scope=None), 1, id="senza-scope"),
        pytest.param(pbi(scope="- `tools/asdlc/runner.py`"), 1, id="scope-senza-il-pbi"),
        pytest.param(pbi(scope="- `backlog/PBI-520-…md` — abbreviato"), 0, id="pbi-abbreviato"),
        pytest.param(pbi(scope="- `backlog/PBI-52-un-altro.md`"), 1, id="pbi-52-non-e-pbi-520"),
    ],
)
def test_i_quattro_rilievi_di_forma(testo, attesi):
    forma_del_pbi = getattr(runner, "forma_del_pbi", None)
    assert forma_del_pbi is not None, "runner.forma_del_pbi non esiste"

    rilievi = forma_del_pbi(testo, "PBI-520")

    assert len(rilievi) == attesi, rilievi
    assert all(r.domanda == "forma" and r.criterio is None for r in rilievi), rilievi
