"""La guardia di fine suite su `tools/tests/dati/` (PBI-518)."""

import uuid

import guardia_dei_dati


def test_la_guardia_nomina_il_file_nato_nei_dati_anche_se_ignorato():
    """Criterio 2: il confronto fra l'elenco di prima e quello di dopo nomina il
    file nuovo, anche quando git lo ignora — `--*.json` in
    `dati/progetto/.gitignore`, una delle toppe che nascondevano il difetto — e
    due elenchi uguali non danno niente."""
    prima = guardia_dei_dati.elenco(guardia_dei_dati.DATI)
    nato = guardia_dei_dati.DATI / "progetto" / f"--guardia-{uuid.uuid4()}.json"
    try:
        nato.write_text("{}", encoding="utf-8")
        dopo = guardia_dei_dati.elenco(guardia_dei_dati.DATI)

        assert any(nato.name in riga for riga in guardia_dei_dati.nati(prima, dopo))
        assert guardia_dei_dati.nati(dopo, dopo) == []
    finally:
        nato.unlink(missing_ok=True)
