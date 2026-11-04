"""Gli sprint nella coda (`backlog/PBI-539`, `ADR-0034`).

Il tick legge le intestazioni `### Sprint N — <risultato>` di `CODA.md` senza
cambiare l'ordine né le fermate della coda: avvisa nel log al lancio del primo PBI
di uno sprint, manda la revisione su Slack col risultato e i PBI fatti, e la
panoramica mostra la tabella degli sprint. Qui nessuna rete: `gh` è un finto, il
webhook il server di `test_asdlc_notifiche.py`.
"""

import importlib
from pathlib import Path

coda = importlib.import_module("asdlc.coda")

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"
coda.configura(coda.asdlc_config.carica(PROGETTO))

# La coda del criterio 1: una voce prima di ogni sprint, uno sprint col risultato e
# la sua revisione, uno senza risultato né revisione, e un'intestazione qualunque
# che chiude l'ultimo.
CODA_DEGLI_SPRINT = (
    "# Coda\n\n"
    "- PBI-0\n\n"
    "### Sprint 1 — il PDF\n\n"
    "- PBI-1\n"
    "- PBI-2\n"
    "- ‖ revisione dello sprint 1 con Jona: il PDF\n\n"
    "### Sprint 2 —\n\n"
    "- PBI-3\n\n"
    "## Note\n\n"
    "- PBI-9\n"
)


# --- Criterio 1: `leggi_sprint` legge gli sprint ------------------------------


def test_leggi_sprint_legge_numero_risultato_pbi_e_revisione():
    sprint = coda.leggi_sprint(CODA_DEGLI_SPRINT)

    assert sprint == [
        coda.Sprint(1, "il PDF", ("PBI-1", "PBI-2"),
                    "revisione dello sprint 1 con Jona: il PDF"),
        coda.Sprint(2, "", ("PBI-3",), None),
    ]
    dentro = {pbi for s in sprint for pbi in s.pbi}
    assert "PBI-0" not in dentro and "PBI-9" not in dentro
    # Le voci e il loro ordine non cambiano: le intestazioni restano prosa per `leggi_voci()`.
    assert coda.leggi_voci(CODA_DEGLI_SPRINT) == [
        coda.VocePbi("PBI-0"), coda.VocePbi("PBI-1"), coda.VocePbi("PBI-2"),
        coda.VoceBarriera("revisione dello sprint 1 con Jona: il PDF"),
        coda.VocePbi("PBI-3"), coda.VocePbi("PBI-9"),
    ]


def test_una_coda_senza_intestazioni_non_ha_sprint():
    assert coda.leggi_sprint("# Coda\n\n- PBI-1\n- ‖ pin\n") == []


def test_un_intestazione_di_sprint_scritta_male_chiude_lo_sprint_prima():
    testo = "### Sprint 1 — uno\n- PBI-1\n### Sprint tre\n- PBI-2\n"

    assert coda.leggi_sprint(testo) == [coda.Sprint(1, "uno", ("PBI-1",), None)]
