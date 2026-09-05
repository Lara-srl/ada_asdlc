"""Il tick della coda dei PBI (`backlog/PBI-350`).

Qui si guarda la **decisione**, non l'effetto: `prossimo()` è una funzione pura —
voci dentro, un esito fuori — e nessuno di questi test avvia un giro. Un test che
lancia il runner non è un test, è una notte.

`tools/` non è un pacchetto installato e non deve diventarlo per un test: si
carica il modulo dal suo percorso, come fa `test_importa_storico.py`.
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("asdlc_coda", REPO / "tools" / "asdlc_coda.py")
coda = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = coda
_spec.loader.exec_module(coda)


def test_un_giro_in_corso_rende_occupato_senza_guardare_la_coda():
    """La testa sarebbe da lanciare, e non si lancia lo stesso.

    Un albero, un agente: il 24→25/08 due agenti sullo stesso worktree sono
    costati un PBI intero, e qui il secondo lo avvierebbe `cron`, che non guarda
    lo schermo.
    """
    decisione = coda.prossimo(
        [coda.VocePbi("PBI-337")], mergiati=set(), rami=set(), occupato=True
    )

    assert decisione == coda.Occupato()


def test_la_testa_della_coda_senza_ramo_su_origin_si_lancia():
    """Nessun giro in corso, il PBI in testa non è mai partito: si lancia."""
    decisione = coda.prossimo(
        [coda.VocePbi("PBI-337")], mergiati=set(), rami=set(), occupato=False
    )

    assert decisione == coda.Lancia("PBI-337")


def test_la_testa_gia_mergiata_si_consuma_e_tocca_alla_voce_dopo():
    """È il gesto per cui il tick esiste: il merge del 337 fa partire il 338.

    Il ramo che il 337 si è lasciato dietro non lo trattiene: un ramo su `origin`
    parla solo **in assenza** di merge (PBI-350, punto 1).
    """
    decisione = coda.prossimo(
        [coda.VocePbi("PBI-337"), coda.VocePbi("PBI-338")],
        mergiati={"PBI-337"},
        rami={"PBI-337"},
        occupato=False,
    )

    assert decisione == coda.Lancia("PBI-338")


def test_la_testa_con_un_ramo_su_origin_e_senza_merge_si_attende():
    """Il giro c'è già stato e non è finito in `main`: tocca a un umano.

    `chiudi()` pubblica su ogni stato che interrompe, quindi un ramo su `origin`
    senza merge è un giro fermo — mai un giro da rifare. È il test che impedisce
    il doppione: rilanciarlo di notte darebbe due rami sullo stesso PBI e il
    lavoro fermo resterebbe fermo.
    """
    decisione = coda.prossimo(
        [coda.VocePbi("PBI-337"), coda.VocePbi("PBI-338")],
        mergiati=set(),
        rami={"PBI-337"},
        occupato=False,
    )

    assert decisione == coda.Attende("PBI-337")


def test_una_barriera_ferma_la_coda_e_le_voci_dopo_non_si_guardano():
    """Il PBI dietro la barriera sarebbe lanciabile, e non si lancia.

    Una riga `‖` non è un PBI: è un gesto umano che deve venire prima. Senza
    questo esito la prima voce non-PBI della coda diventerebbe un PBI
    inesistente lanciato di notte.
    """
    decisione = coda.prossimo(
        [coda.VoceBarriera("la ripassata dell'import"), coda.VocePbi("PBI-337")],
        mergiati=set(),
        rami=set(),
        occupato=False,
    )

    assert decisione == coda.Barriera("la ripassata dell'import")


def test_una_coda_tutta_mergiata_e_finita():
    """Non c'è più niente da lanciare, e non è un guasto: è un lotto chiuso."""
    decisione = coda.prossimo(
        [coda.VocePbi("PBI-337"), coda.VocePbi("PBI-338")],
        mergiati={"PBI-337", "PBI-338"},
        rami=set(),
        occupato=False,
    )

    assert decisione == coda.Finita()
