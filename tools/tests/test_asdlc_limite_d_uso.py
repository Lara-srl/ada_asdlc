"""Il limite d'uso non ferma la coda (`backlog/PBI-519`).

Un `senza esito` dovuto al limite d'uso dell'account, con l'ora del reset
leggibile nello stderr della CLI, porta nel rapporto `riprendi_dopo`; il tick
aspetta quell'ora e rilancia il PBI con `--riprendi`, che riparte dalla punta del
ramo pubblicato. Gli agenti e l'orologio sono finti: nessun test lancia `claude`
né aspetta davvero.

Il runner e il tick si caricano per nome, `asdlc.runner` e `asdlc.coda`:
`conftest.py` mette `tools/` sul `sys.path` (PBI-383).
"""

import importlib
from datetime import datetime
from pathlib import Path

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"

runner = importlib.import_module("asdlc.runner")
# Come in `test_asdlc_runner.py`: la radice e la configurazione sono quelle del
# progetto di prova, e l'import non legge `asdlc.toml` (PBI-382, PBI-394).
runner.REPO = PROGETTO
runner.configura(runner.asdlc_config.carica(PROGETTO))


class TestLOraDiRipresa:
    """Criterio 2, decisione 3: la prima occorrenza dell'ora del reset successiva
    all'istante in cui l'uscita è stata scritta, più cinque minuti di margine."""

    def test_letta_prima_del_reset_e_oggi(self):
        scritta = datetime(2026, 10, 16, 17, 45)

        assert runner.ora_di_ripresa("7:50pm", scritta) == datetime(2026, 10, 16, 19, 55)

    def test_letta_dopo_il_reset_e_domani(self):
        scritta = datetime(2026, 10, 16, 21, 0)

        assert runner.ora_di_ripresa("7:50pm", scritta) == datetime(2026, 10, 17, 19, 55)
