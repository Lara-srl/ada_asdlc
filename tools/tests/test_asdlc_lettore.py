"""Il Lettore e la sonda del rosso (`backlog/PBI-521`, `ADR-0031`).

Il Lettore è il quarto ruolo: legge il PBI contro la base, risponde alle sette
domande con `rilievo`, propone con `sonda` i test RED dei criteri e chiude con
`letto`. Le sonde le esegue il runner, in un albero usa e getta alla base: una
sonda verde è un rilievo R deciso dal codice, non dal modello.

Nessun test lancia `claude`: il Lettore è finto, e scrive nel suo `cwd` e nei file
della decisione 2 ciò che il server scriverebbe. Su `main` il ruolo, gli strumenti
e il flag non esistono, quindi i criteri nascono rossi per asserzione.
"""

import importlib
import json
from pathlib import Path

esito = importlib.import_module("asdlc.esito")


def nomi(ruolo):
    return {s["name"] for s in esito.strumenti(ruolo)}


def righe_della_lettura(file: Path) -> list[dict]:
    lettura = Path(f"{file}.lettura.jsonl")
    if not lettura.exists():
        return []
    return [json.loads(r) for r in lettura.read_text(encoding="utf-8").splitlines() if r.strip()]


# --- Criterio 1: il server accetta e accumula gli strumenti del Lettore -------

RILIEVO_R = {"domanda": "R", "criterio": 2, "testo": "il criterio 2 è già vero su main",
             "evidenza": "modulo.py:1"}
RILIEVO_N = {"domanda": "N", "criterio": 0, "testo": "il PBI cita una funzione che non c'è",
             "evidenza": "modulo.py"}
SONDA = {"criterio": 1, "file": "test_sonda.py", "nome": "test_la_somma"}


def albero_del_lettore(tmp_path, monkeypatch) -> Path:
    """L'albero da cui parte il server, con un modulo e un test, e il file d'esito
    in una cartella accanto."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "modulo.py").write_text("def somma(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "test_sonda.py").write_text("def test_la_somma():\n    pass\n", encoding="utf-8")
    cartella = tmp_path / "esito"
    cartella.mkdir()
    return cartella / "lettore.json"


def test_il_server_accetta_e_accumula_gli_strumenti_del_lettore(tmp_path, monkeypatch):
    file = albero_del_lettore(tmp_path, monkeypatch)

    assert {"rilievo", "sonda", "letto"} <= nomi("lettore")
    for nome, argomenti in (("rilievo", RILIEVO_R), ("rilievo", RILIEVO_N), ("sonda", SONDA)):
        risposta = esito.chiama(nome, argomenti, "lettore", str(file))
        assert not risposta["isError"], (nome, risposta)
    assert not file.exists(), "rilievo e sonda si accumulano, non chiudono la lettura"
    assert righe_della_lettura(file) == [{"strumento": "rilievo", **RILIEVO_R},
                                         {"strumento": "rilievo", **RILIEVO_N},
                                         {"strumento": "sonda", **SONDA}]

    letto = esito.chiama("letto", {"riepilogo": "due rilievi e una sonda"}, "lettore", str(file))

    assert not letto["isError"], letto
    assert json.loads(file.read_text(encoding="utf-8")) == {
        "esito": "letto", "riepilogo": "due rilievi e una sonda",
        "rilievi": [RILIEVO_R, RILIEVO_N], "sonde": [SONDA]}
