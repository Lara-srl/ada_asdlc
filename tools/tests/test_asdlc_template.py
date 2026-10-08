"""I modelli di `template/` (`backlog/PBI-500`).

`template/` è la cartella che un progetto nuovo copia alla nascita. Questi test
leggono quella del repository che li ospita, non il progetto di prova: per questo
portano il marcatore `progetto_ospite`. Delle intestazioni conta l'ordine, e si
confrontano come lista; il testo sotto è libero, salvo dove un criterio lo dice.
"""

import importlib
import re
from pathlib import Path

import pytest

asdlc_config = importlib.import_module("asdlc.config")

RE_INTESTAZIONE = re.compile(r"^#+ .*$", re.MULTILINE)


def template() -> Path:
    return asdlc_config.radice(Path(__file__).resolve().parent) / "template"


def intestazioni(testo: str) -> list[str]:
    return RE_INTESTAZIONE.findall(testo)


@pytest.mark.progetto_ospite
def test_il_modello_dei_pbi_ha_le_sezioni_del_formato_nell_ordine():
    percorso = template() / "backlog" / "TEMPLATE.md"
    assert percorso.is_file(), percorso

    testo = percorso.read_text(encoding="utf-8")
    titolo, *sezioni = intestazioni(testo)

    assert titolo.startswith("# PBI-XXX: ")
    assert sezioni == [
        "## Direttiva",
        "## ✅ Deciso",
        "## Il giro N, e cosa si riprende",
        "## Dipendenze",
        "## Contesto",
        "## Verifica",
        "## Protocollo di rifinitura",
    ]
    direttiva = testo.split("## Direttiva", 1)[1].split("\n## ", 1)[0]
    assert "**Scope**" in direttiva.splitlines()
    assert "backlog/PBI-XXX-" in direttiva.split("**Scope**", 1)[1]
    verifica = testo.split("## Verifica", 1)[1].split("\n## ", 1)[0].splitlines()
    assert any(riga.startswith("- [ ]") for riga in verifica)
    assert any(riga.startswith("**Non regressione:**") for riga in verifica)


@pytest.mark.progetto_ospite
def test_il_modello_degli_adr_porta_la_firma_vuota_e_le_quattro_domande():
    percorso = template() / "decisions" / "TEMPLATE.md"
    assert percorso.is_file(), percorso

    testo = percorso.read_text(encoding="utf-8")
    titolo, *sezioni = intestazioni(testo)

    assert titolo.startswith("# ADR-NNNN: ")
    assert "**Ratificata da** … **il** …" in testo.split("\n## ", 1)[0]
    assert sezioni == [
        "## Contesto",
        "## Decisione",
        "## Conseguenze",
        "## Alternative considerate",
    ]
    decisione = testo.split("## Decisione", 1)[1].split("\n## ", 1)[0]
    voci = re.findall(r"^\d+\. (.*)$", decisione, re.MULTILINE)
    domande = ["cosa si controlla", "quando", "cosa conta come prova", "cosa succede se manca"]
    assert len(voci) == len(domande), voci
    assert [v.startswith(f"**{d}**") for v, d in zip(voci, domande)] == [True] * 4, voci


@pytest.mark.progetto_ospite
def test_il_modello_delle_spec_ha_le_sezioni_di_quello_di_partenza_senza_le_fasi():
    percorso = template() / "specs" / "TEMPLATE.md"
    assert percorso.is_file(), percorso

    testo = percorso.read_text(encoding="utf-8")
    titolo, *sezioni = intestazioni(testo)

    assert titolo.startswith("# Feature: ")
    assert sezioni == [
        "## Blueprint",
        "### Contesto",
        "### Architettura",
        "### Vincoli",
        "## Contratto",
        "### Definition of Done",
        "### Guardie di regressione",
        "### Scenari",
        "### Domande aperte",
    ]
    assert "Fase:" not in testo
    assert "e2e/contract.ts" not in testo


VIETATI = ("/home/", "/Users/", "~/", "aDa", "Barbara", "Oltre3D", "Carrozzeria")


@pytest.mark.progetto_ospite
def test_guardia_template_non_porta_percorsi_di_macchina_ne_nomi_di_ada():
    """Non regressione di PBI-500, ereditata dai PBI di `template/` che vengono
    dopo. Ne restano fuori, per nome, le copie degli ADR di metodo
    (`template/decisions/ADR-*.md`, PBI-502): nominano aDa perché è lì che le
    regole sono nate. Una cartella vuota non guarda niente, quindi un file ci
    deve essere."""
    radice = template()
    file = [p for p in sorted(radice.rglob("*"))
            if p.is_file() and not p.relative_to(radice).match("decisions/ADR-*.md")]

    assert file, f"{radice} non ha file"
    trovati = [(str(p.relative_to(radice)), v) for p in file
               for v in VIETATI if v in p.read_text(encoding="utf-8")]
    assert trovati == []
