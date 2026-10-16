"""La guardia di processo del Solver (`backlog/PBI-508`, `ADR-0030` decisione 4, R4-R7 e R13).

Che il Solver abbia rispettato le regole lo dice il codice, leggendo il rapporto, git e `gh`:
mai un modello (`ADR-0027`). La guardia segnala e non blocca (`ADR-0008`).
"""

import importlib

from test_asdlc_solver import giro_fermato  # noqa: F401 — è una fixture

runner = importlib.import_module("asdlc.runner")

INTESTAZIONE = "## Guardia di processo"


def righe_della_guardia(e):
    return e.guardia.splitlines()


def test_la_riga_r4_e_non_eseguita_con_il_rinvio_a_pbi_511():
    """R4: la traccia delle letture è di `PBI-511`; fin lì la riga è sempre `non eseguita`."""
    e = runner.Esito("PBI-102", "fermato", solver=[{"esito": "senza esito", "uscita": ""}])

    runner.guardia_del_solver(e)

    assert righe_della_guardia(e)[0] == INTESTAZIONE
    assert "R4: non eseguita (PBI-511)" in righe_della_guardia(e)


def test_un_giro_fermato_con_il_solver_porta_la_sezione_e_chiude_come_prima(giro_fermato):  # noqa: F811
    """Il giro non si ferma per la guardia: lo stato è quello del blocco."""
    esito, _ = giro_fermato({}, {"solver": "boh"})

    assert esito.stato == "fermato"
    assert "R4: non eseguita (PBI-511)" in esito.guardia.splitlines()


def test_un_giro_senza_solver_non_ha_la_sezione():
    e = runner.Esito("PBI-102", "fatto")

    runner.guardia_del_solver(e)

    assert e.guardia == ""
