"""Gli sprint nella coda (`backlog/PBI-539`, `ADR-0034`).

Il tick legge le intestazioni `### Sprint N — <risultato>` di `CODA.md` senza
cambiare l'ordine né le fermate della coda: avvisa nel log al lancio del primo PBI
di uno sprint, manda la revisione su Slack col risultato e i PBI fatti, e la
panoramica mostra la tabella degli sprint. Qui nessuna rete: `gh` è un finto, il
webhook il server di `test_asdlc_notifiche.py`.
"""

import importlib
import json
from pathlib import Path

import pytest

from test_asdlc_notifiche import (  # noqa: F401 — `tick_configurato` e `webhook` sono fixture
    mondo_finto, passi_sostituiti, progetto_finto, righe_del_log, tick_configurato, un_tick,
    webhook,
)

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


# --- Criterio 2: gli avvisi al lancio del primo PBI dello sprint --------------


# Lo sprint 1 di sei PBI, senza risultato e senza la barriera della sua revisione.
CODA_SPRINT_STORTO = "### Sprint 1 —\n\n" + "".join(f"- PBI-{n}\n" for n in range(1, 7))

AVVISI_DELLO_SPRINT_STORTO = (
    " — avviso, lo sprint 1 ha 6 PBI (al più 5)",
    " — avviso, lo sprint 1 non dice il risultato da mostrare",
    " — avviso, lo sprint 1 non finisce con la sua revisione",
)


@pytest.fixture
def home_in_tmp(tmp_path, monkeypatch):
    casa = tmp_path / "casa"
    casa.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(casa))


def tick_che_lancia(tmp_path, monkeypatch, pbi):
    """Un tick su `CODA_SPRINT_STORTO` con `decidi` che dà `Lancia(pbi)`: rende il
    checkout e i PBI che il tick ha lanciato."""
    repo, albero = progetto_finto(tmp_path, CODA_SPRINT_STORTO)
    lanciati = []
    passi_sostituiti(monkeypatch, decidi=lambda r, w: coda.Lancia(pbi),
                     lancia=lambda p, w, **k: lanciati.append(p))
    mondo_finto(monkeypatch)
    assert un_tick(repo, albero) == 0
    return repo, lanciati


def test_il_lancio_del_primo_pbi_dello_sprint_porta_gli_avvisi_e_parte(
        tmp_path, monkeypatch, home_in_tmp, tick_configurato):
    repo, lanciati = tick_che_lancia(tmp_path, monkeypatch, "PBI-1")

    righe = [r for r in righe_del_log(repo) if "PBI-1" in r]
    assert len(righe) == 1, righe_del_log(repo)
    for avviso in AVVISI_DELLO_SPRINT_STORTO:
        assert avviso in righe[0], righe[0]
    assert lanciati == ["PBI-1"]



def test_il_lancio_di_un_altro_pbi_dello_sprint_non_ripete_gli_avvisi(
        tmp_path, monkeypatch, home_in_tmp, tick_configurato):
    repo, lanciati = tick_che_lancia(tmp_path, monkeypatch, "PBI-2")

    assert not [r for r in righe_del_log(repo) if "sprint" in r], righe_del_log(repo)
    assert lanciati == ["PBI-2"]


# --- Criterio 3: la revisione va su Slack col risultato e i fatti -------------


PBI_1_MERGIATO = json.dumps([{"title": "PBI-1: il primo", "headRefName": "pbi/pbi-1",
                              "files": [{"path": "uno.py"}]}])


def test_la_revisione_dello_sprint_va_su_slack_col_risultato_e_i_fatti(
        tmp_path, monkeypatch, webhook, tick_configurato):
    """Una barriera qualunque manda il messaggio di sempre; quella della revisione
    dello sprint 1 dice lo sprint, il risultato e i PBI fatti, cioè mergiati."""
    repo, albero = progetto_finto(tmp_path, CODA_DEGLI_SPRINT)
    mondo_finto(monkeypatch, merged=(0, PBI_1_MERGIATO))
    decisioni = iter([coda.Barriera("pin"),
                      coda.Barriera("revisione dello sprint 1 con Jona: il PDF")])
    passi_sostituiti(monkeypatch, decidi=lambda r, w: next(decisioni))

    un_tick(repo, albero)
    un_tick(repo, albero)

    assert len(webhook.testi()) == 2, webhook.testi()
    di_sempre, revisione = webhook.testi()
    assert "barriera — pin" in di_sempre, di_sempre
    assert "sprint 1 pronto per la revisione" in revisione, revisione
    assert "il PDF" in revisione and "PBI-1" in revisione, revisione
    assert "PBI-2" not in revisione, revisione
