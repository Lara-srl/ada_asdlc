"""Il server dell'esito (`backlog/PBI-366`, `ADR-0027`).

Il runner ricava gli esiti degli agenti dal loro testo libero, e ogni forma nuova
che un modello ha scritto è costata una regola e un test: la citazione, il
grassetto, la domanda vuota, il `PASS` citato dentro un `NON PRONTO` (difetti 32,
34, 35 e 36 di `PBI-102`). Qui nasce il canale strutturato: un server MCP su stdio
con due strumenti, `fatto` e `fermati`, che scrive l'esito in un file nominato dal
runner. Il runner non lo usa ancora: lo collega `PBI-367`.

I test parlano col server come la CLI: un processo vero, JSON-RPC su righe da
stdin a stdout. Il modulo non si importa, così un file che non c'è è un'asserzione
che fallisce e non un errore di raccolta.
"""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SORGENTE = REPO / "tools" / "asdlc_esito.py"

# Una versione che il server non ha motivo di conoscere: deve rispondere con
# quella del client, non con una sua (decisione 5).
VERSIONE_DEL_CLIENT = "2099-01-01"


@pytest.fixture(autouse=True)
def db():
    return None


@pytest.fixture(autouse=True)
def clear_login_limiter():
    return None


@pytest.fixture(autouse=True)
def clear_event_bus():
    return None


def test_il_server_esiste_e_usa_solo_la_libreria_standard():
    """Il server si copia col runner in un altro progetto (`ADR-0017`) e la CLI
    lo lancia con il `python3` di sistema: niente `pip install` (decisione 5)."""
    assert SORGENTE.is_file(), f"{SORGENTE.relative_to(REPO)} non esiste"
    modulo = ast.parse(SORGENTE.read_text(encoding="utf-8"))
    importati = {
        (alias.name if isinstance(nodo, ast.Import) else nodo.module).split(".")[0]
        for nodo in ast.walk(modulo)
        if isinstance(nodo, (ast.Import, ast.ImportFrom))
        for alias in nodo.names
    }
    fuori = importati - sys.stdlib_module_names
    assert not fuori, f"import fuori dalla libreria standard: {sorted(fuori)}"


# --- Il varco: un processo vero, una riga JSON per messaggio -----------------


def richiesta(id_, metodo, parametri=None):
    messaggio = {"jsonrpc": "2.0", "id": id_, "method": metodo}
    if parametri is not None:
        messaggio["params"] = parametri
    return messaggio


def notifica(metodo):
    return {"jsonrpc": "2.0", "method": metodo}


def apertura():
    """Ciò che la CLI manda prima di tutto il resto."""
    return [
        richiesta(0, "initialize", {
            "protocolVersion": VERSIONE_DEL_CLIENT,
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        }),
        notifica("notifications/initialized"),
    ]


def parla(ruolo, esito, messaggi):
    """Manda `messaggi` al server, chiude stdin e torna le risposte per id.

    Una notifica non ha risposta: il server che ne desse una produrrebbe una
    riga senza id, e la si trova sotto `None`."""
    ambiente = {**os.environ, "ASDLC_RUOLO": ruolo, "ASDLC_ESITO": str(esito)}
    fatto = subprocess.run(
        [sys.executable, str(SORGENTE)],
        input="".join(json.dumps(m) + "\n" for m in messaggi),
        capture_output=True, text=True, env=ambiente, timeout=20,
    )
    assert fatto.returncode == 0, fatto.stderr
    risposte = {}
    for riga in fatto.stdout.splitlines():
        if riga.strip():
            risposta = json.loads(riga)
            risposte[risposta.get("id")] = risposta
    attese = {m["id"] for m in messaggi if "id" in m}
    assert attese <= set(risposte), f"richieste senza risposta: {sorted(attese - set(risposte))}"
    return risposte


# --- Il server parla MCP su stdio --------------------------------------------

SCHEMI_DEL_RUOLO = {
    "builder": {
        "fatto": ({"riepilogo"}, {"riepilogo"}),
        "fermati": ({"domanda"}, {"domanda"}),
    },
    "critic": {
        "fatto": ({"verdetto", "riepilogo"}, {"verdetto", "riepilogo"}),
        "fermati": ({"domanda"}, {"domanda"}),
    },
}


@pytest.mark.parametrize("ruolo", ["builder", "critic"])
def test_il_server_risponde_a_initialize_e_elenca_i_due_strumenti(ruolo, tmp_path):
    risposte = parla(ruolo, tmp_path / "esito.json",
                     [*apertura(), richiesta(1, "tools/list")])

    assert None not in risposte, "una notifica ha ricevuto una risposta"
    iniziale = risposte[0]["result"]
    assert iniziale["protocolVersion"] == VERSIONE_DEL_CLIENT
    assert "tools" in iniziale["capabilities"]
    assert iniziale["serverInfo"]["name"] == "asdlc"

    strumenti = {s["name"]: s for s in risposte[1]["result"]["tools"]}
    assert set(strumenti) == set(SCHEMI_DEL_RUOLO[ruolo])
    for nome, (proprieta, obbligatori) in SCHEMI_DEL_RUOLO[ruolo].items():
        schema = strumenti[nome]["inputSchema"]
        assert strumenti[nome]["description"]
        assert schema["type"] == "object"
        assert set(schema["properties"]) == proprieta
        assert set(schema["required"]) == obbligatori


def test_il_verdetto_del_critic_ha_due_valori_nello_schema(tmp_path):
    risposte = parla("critic", tmp_path / "esito.json",
                     [*apertura(), richiesta(1, "tools/list")])
    fatto = next(s for s in risposte[1]["result"]["tools"] if s["name"] == "fatto")
    assert fatto["inputSchema"]["properties"]["verdetto"]["enum"] == ["pass", "non pronto"]


def test_un_metodo_sconosciuto_riceve_un_errore_json_rpc(tmp_path):
    """Una richiesta senza risposta lascia la CLI in attesa."""
    risposte = parla("builder", tmp_path / "esito.json",
                     [*apertura(), richiesta(1, "resources/list")])
    assert risposte[1].get("error", {}).get("code") == -32601


def chiamata(id_, nome, argomenti):
    return richiesta(id_, "tools/call", {"name": nome, "arguments": argomenti})


def leggi_esito(esito):
    return json.loads(esito.read_text(encoding="utf-8"))


# --- Una chiamata valida scrive l'esito --------------------------------------

DOMANDA = "La spec dice due cose diverse sul netto.\nQuale vale?"
RAPPORTO = "Tre rilievi.\n1. manca un test\n2. un commento falso\n3. niente altro"


@pytest.mark.parametrize("ruolo, nome, argomenti, atteso", [
    pytest.param("builder", "fatto", {"riepilogo": "il server risponde"},
                 {"esito": "fatto", "riepilogo": "il server risponde"},
                 id="builder-fatto"),
    pytest.param("builder", "fermati", {"domanda": DOMANDA},
                 {"esito": "fermati", "domanda": DOMANDA},
                 id="builder-fermati"),
    pytest.param("critic", "fatto", {"verdetto": "pass", "riepilogo": RAPPORTO},
                 {"esito": "fatto", "verdetto": "pass", "riepilogo": RAPPORTO},
                 id="critic-pass"),
    pytest.param("critic", "fatto", {"verdetto": "non pronto", "riepilogo": RAPPORTO},
                 {"esito": "fatto", "verdetto": "non pronto", "riepilogo": RAPPORTO},
                 id="critic-non-pronto"),
    pytest.param("critic", "fermati", {"domanda": DOMANDA},
                 {"esito": "fermati", "domanda": DOMANDA},
                 id="critic-fermati"),
])
def test_una_chiamata_valida_scrive_l_esito(ruolo, nome, argomenti, atteso, tmp_path):
    esito = tmp_path / "esito.json"
    risposte = parla(ruolo, esito, [*apertura(), chiamata(1, nome, argomenti)])

    risultato = risposte[1].get("result", {})
    assert risultato.get("isError") is False
    assert risultato.get("content"), "il modello deve ricevere una conferma"
    assert esito.is_file(), "il file d'esito non è stato scritto"
    assert leggi_esito(esito) == atteso


def parole_della_risposta(risultato):
    return " ".join(c.get("text", "") for c in risultato.get("content", []))


# --- Un testo vuoto si rifiuta ------------------------------------------------


@pytest.mark.parametrize("ruolo, nome, argomenti, campo", [
    pytest.param("builder", "fermati", {"domanda": ""}, "domanda", id="domanda-vuota"),
    pytest.param("critic", "fermati", {"domanda": " \n\t "}, "domanda",
                 id="domanda-di-spazi"),
    pytest.param("builder", "fatto", {"riepilogo": ""}, "riepilogo", id="riepilogo-vuoto"),
])
def test_un_testo_vuoto_si_rifiuta_e_il_file_non_nasce(ruolo, nome, argomenti, campo,
                                                        tmp_path):
    """Il modello legge l'errore e richiama: deve sapere quale campo manca
    (nella prova del 24/09 l'ha riportato alla lettera)."""
    esito = tmp_path / "esito.json"
    risposte = parla(ruolo, esito, [*apertura(), chiamata(1, nome, argomenti)])

    risultato = risposte[1].get("result", {})
    assert risultato.get("isError") is True
    assert campo in parole_della_risposta(risultato)
    assert not esito.exists()


# --- Il verdetto del Critic è obbligatorio e chiuso ---------------------------


@pytest.mark.parametrize("argomenti", [
    pytest.param({"riepilogo": RAPPORTO}, id="critic-senza-verdetto"),
    pytest.param({"verdetto": "PASS con riserva", "riepilogo": RAPPORTO},
                 id="verdetto-fuori-elenco"),
])
def test_il_verdetto_del_critic_e_obbligatorio_e_chiuso(argomenti, tmp_path):
    """Nella prova del 24/09 (*critic-d*) la chiamata senza verdetto è arrivata
    al server così com'era: lo schema non la ferma, la ferma il server."""
    esito = tmp_path / "esito.json"
    risposte = parla("critic", esito, [*apertura(), chiamata(1, "fatto", argomenti)])

    risultato = risposte[1].get("result", {})
    assert risultato.get("isError") is True
    assert "verdetto" in parole_della_risposta(risultato)
    assert not esito.exists()
