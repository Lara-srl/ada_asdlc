"""Il server dell'esito (`backlog/PBI-366`, `ADR-0027`).

Il runner ricava gli esiti degli agenti dal loro testo libero, e ogni forma nuova
che un modello ha scritto è costata una regola e un test: la citazione, il
grassetto, la domanda vuota, il `PASS` citato dentro un `NON PRONTO` (difetti 32,
34, 35 e 36 di `PBI-102`). Qui nasce il canale strutturato: un server MCP su stdio
con due strumenti, `fatto` e `fermati`, che scrive l'esito in un file nominato dal
runner. Il runner non lo usa ancora: lo collega `PBI-367`.

I test parlano col server come la CLI: un processo vero, JSON-RPC su righe da
stdin a stdout. Il modulo non si importa in cima al file, così un file che non c'è
è un'asserzione che fallisce e non un errore di raccolta. Lo carica dal percorso
solo chi deve sostituirne una funzione (`PBI-372`): un guasto che il processo vero
non sa produrre a comando.
"""

import ast
import importlib.util
import io
import json
import os
import subprocess
import sys
from datetime import datetime
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


@pytest.mark.parametrize("ruolo", [
    pytest.param("critico", id="refuso"),
    pytest.param("Critic", id="maiuscola"),
    pytest.param(None, id="assente"),
])
def test_un_ruolo_sconosciuto_ferma_il_server_all_avvio(ruolo, tmp_path):
    """Un ruolo che non è `builder` né `critic` non deve valere come builder: il
    Critic potrebbe dichiarare `fatto` senza verdetto. Il server si ferma, e
    `PBI-367` lo legge come «senza esito»."""
    esito = tmp_path / "esito.json"
    ambiente = {k: v for k, v in os.environ.items() if k != "ASDLC_RUOLO"}
    ambiente["ASDLC_ESITO"] = str(esito)
    if ruolo is not None:
        ambiente["ASDLC_RUOLO"] = ruolo
    messaggi = [*apertura(), richiesta(1, "tools/call",
                                       {"name": "fatto", "arguments": {"riepilogo": "x"}})]
    fatto = subprocess.run(
        [sys.executable, str(SORGENTE)],
        input="".join(json.dumps(m) + "\n" for m in messaggi),
        capture_output=True, text=True, env=ambiente, timeout=20,
    )

    assert fatto.returncode != 0
    assert "ASDLC_RUOLO" in fatto.stderr
    assert "Traceback" not in fatto.stderr
    assert not fatto.stdout.strip()
    assert not esito.exists()


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


@pytest.mark.parametrize("ruolo, nome, argomenti, atteso", [
    pytest.param("builder", "fermati", {"domanda": DOMANDA, "esito": "fatto"},
                 {"esito": "fermati", "domanda": DOMANDA},
                 id="fermati-con-esito-fatto"),
    pytest.param("builder", "fatto", {"riepilogo": "finito", "verdetto": "pass"},
                 {"esito": "fatto", "riepilogo": "finito"},
                 id="builder-fatto-con-verdetto"),
    pytest.param("critic", "fermati", {"domanda": DOMANDA, "verdetto": "pass"},
                 {"esito": "fermati", "domanda": DOMANDA},
                 id="critic-fermati-con-verdetto"),
])
def test_nel_file_d_esito_entrano_solo_i_campi_dello_schema(ruolo, nome, argomenti,
                                                            atteso, tmp_path):
    """La CLI non fa rispettare lo schema (*critic-d*): un campo in più scelto dal
    modello non deve riscrivere l'esito né portarci un verdetto che il ruolo non ha.
    Nel log, invece, la chiamata resta intera."""
    esito = tmp_path / "esito.json"
    risposte = parla(ruolo, esito, [*apertura(), chiamata(1, nome, argomenti)])

    assert risposte[1].get("result", {}).get("isError") is False
    assert leggi_esito(esito) == atteso
    riga = json.loads(Path(f"{esito}.chiamate.jsonl").read_text(encoding="utf-8"))
    assert riga["argomenti"] == argomenti


def test_uno_strumento_sconosciuto_si_rifiuta_e_il_file_non_nasce(tmp_path):
    esito = tmp_path / "esito.json"
    risposte = parla("builder", esito,
                     [*apertura(), chiamata(1, "altro", {"riepilogo": "finito"})])

    risultato = risposte[1].get("result", {})
    assert risultato.get("isError") is True
    assert "altro" in parole_della_risposta(risultato)
    assert not esito.exists()


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


# --- La prima chiamata valida è definitiva ------------------------------------


@pytest.mark.parametrize("prima, seconda", [
    pytest.param(("fatto", {"riepilogo": "finito"}), ("fermati", {"domanda": "e ora?"}),
                 id="fatto-poi-fermati"),
    pytest.param(("fermati", {"domanda": "e ora?"}), ("fatto", {"riepilogo": "finito"}),
                 id="fermati-poi-fatto"),
])
def test_la_seconda_chiamata_si_rifiuta_e_il_file_resta_quello_della_prima(
        prima, seconda, tmp_path):
    esito = tmp_path / "esito.json"
    risposte = parla("builder", esito, [
        *apertura(), chiamata(1, *prima), chiamata(2, *seconda),
    ])

    assert risposte[1].get("result", {}).get("isError") is False
    rifiuto = risposte[2].get("result", {})
    assert rifiuto.get("isError") is True
    assert "già dichiarato" in parole_della_risposta(rifiuto)
    assert leggi_esito(esito) == {"esito": prima[0], **prima[1]}


# --- Ogni chiamata finisce nel log --------------------------------------------


def test_ogni_chiamata_finisce_nel_log_comprese_quelle_rifiutate(tmp_path):
    """Il log è ciò che resta di una chiamata rifiutata: senza, un esito arrivato
    al secondo tentativo non dice che ce n'è stato un primo."""
    esito = tmp_path / "esito.json"
    chiamate = [
        ("fatto", {"riepilogo": RAPPORTO}),
        ("fatto", {"verdetto": "non pronto", "riepilogo": RAPPORTO}),
        ("fermati", {"domanda": DOMANDA}),
    ]
    parla("critic", esito, [
        *apertura(), *(chiamata(i, *c) for i, c in enumerate(chiamate, start=1)),
    ])

    log = Path(f"{esito}.chiamate.jsonl")
    assert log.is_file(), "il log delle chiamate non è stato scritto"
    righe = [json.loads(r) for r in log.read_text(encoding="utf-8").splitlines()]
    assert [(r["nome"], r["argomenti"]) for r in righe] == chiamate
    for riga in righe:
        datetime.fromisoformat(riga["ora"])


# --- Il server non cade mai (`PBI-372`) ---------------------------------------


def parla_a_righe(ruolo, esito, righe):
    """Come `parla`, ma con righe già scritte, anche non JSON o in byte che non
    sono UTF-8: torna il processo finito, con stdout e stderr in testo, e la
    lista delle risposte, comprese quelle con `id` nullo."""
    ambiente = {**os.environ, "ASDLC_RUOLO": ruolo, "ASDLC_ESITO": str(esito)}
    fatto = subprocess.run(
        [sys.executable, str(SORGENTE)],
        input=b"".join((riga if isinstance(riga, bytes) else riga.encode("utf-8")) + b"\n"
                       for riga in righe),
        capture_output=True, env=ambiente, timeout=20,
    )
    fatto.stdout = fatto.stdout.decode("utf-8")
    fatto.stderr = fatto.stderr.decode("utf-8", errors="replace")
    risposte = [json.loads(r) for r in fatto.stdout.splitlines() if r.strip()]
    return fatto, risposte


def _json(messaggio):
    return json.dumps(messaggio)


@pytest.mark.parametrize("riga, id_atteso, codice", [
    pytest.param("{non è json", None, -32700, id="riga-non-json"),
    pytest.param(_json([1, 2]), None, -32600, id="messaggio-lista"),
    pytest.param(_json(42), None, -32600, id="messaggio-numero"),
    pytest.param(_json({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": ["fatto", {"riepilogo": "x"}]}),
                 1, -32600, id="params-lista"),
])
def test_un_messaggio_non_valido_riceve_un_errore_e_il_server_risponde_ancora(
        riga, id_atteso, codice, tmp_path):
    """Difetto 39 e decisioni 1-2 di `PBI-372`: su `main` la riga non JSON, il
    numero e i `params` in lista facevano cadere il processo, e la lista si
    ignorava senza risposta."""
    _risponde_con_un_errore_e_poi_ancora(riga, id_atteso, codice, tmp_path)


@pytest.mark.parametrize("riga, id_atteso, codice", [
    pytest.param("[" * 100_000, None, -32700, id="riga-annidata-oltre-la-ricorsione"),
    pytest.param('{"jsonrpc": "2.0", "id": ' + "1" * 5000 + ', "method": "tools/list"}',
                 None, -32700, id="id-di-cinquemila-cifre"),
    pytest.param(_json({"jsonrpc": "2.0", "id": 1, "method": "\ud800"}),
                 1, -32601, id="metodo-con-surrogato-isolato"),
    pytest.param(b"\xff\xfe non UTF-8", None, -32700, id="byte-non-utf8"),
])
def test_un_guasto_nel_parse_nella_scrittura_o_nella_lettura_riceve_un_errore_e_il_server_risponde_ancora(
        riga, id_atteso, codice, tmp_path):
    """Decisioni 1 e 6 di `PBI-372`, dal Critic sulla prima versione: la rete
    avvolgeva solo `rispondi()`. La riga annidata e l'`id` di cinquemila cifre
    cadevano nel parse con un'eccezione che non è `JSONDecodeError`, il
    surrogato isolato nella scrittura su stdout, i byte non UTF-8 nella lettura
    di stdin."""
    _risponde_con_un_errore_e_poi_ancora(riga, id_atteso, codice, tmp_path)


def _risponde_con_un_errore_e_poi_ancora(riga, id_atteso, codice, tmp_path):
    esito = tmp_path / "esito.json"
    fatto, risposte = parla_a_righe("builder", esito, [
        *map(_json, apertura()), riga, _json(richiesta(2, "tools/list")),
    ])

    assert "Traceback" not in fatto.stderr, fatto.stderr
    assert fatto.returncode == 0
    errori = [r for r in risposte if r.get("id") == id_atteso and "error" in r]
    assert [e["error"]["code"] for e in errori] == [codice]
    elenco = next((r for r in risposte if r.get("id") == 2), {})
    assert elenco.get("result", {}).get("tools"), "dopo l'errore tools/list non risponde"
    assert not esito.exists()


def test_un_arguments_che_non_e_un_oggetto_si_rifiuta_e_finisce_nel_log(tmp_path):
    """Difetto 40, decisione 3: la chiamata si rifiuta con `isError`, come ogni
    chiamata non valida, e il server resta vivo."""
    esito = tmp_path / "esito.json"
    fatto, risposte = parla_a_righe("builder", esito, [
        *map(_json, apertura()),
        _json(chiamata(1, "fatto", ["il riepilogo"])),
        _json(richiesta(2, "tools/list")),
    ])

    assert "Traceback" not in fatto.stderr, fatto.stderr
    per_id = {r.get("id"): r for r in risposte}
    rifiuto = per_id.get(1, {}).get("result", {})
    assert rifiuto.get("isError") is True
    assert parole_della_risposta(rifiuto)
    assert not esito.exists()
    righe = Path(f"{esito}.chiamate.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(r)["argomenti"] for r in righe] == [["il riepilogo"]]
    assert per_id.get(2, {}).get("result", {}).get("tools")



@pytest.mark.parametrize("params", [
    pytest.param([], id="lista-vuota"),
    pytest.param("", id="stringa-vuota"),
    pytest.param(0, id="zero"),
    pytest.param(False, id="false"),
])
def test_dei_params_vuoti_o_falsi_che_non_sono_un_oggetto_ricevono_invalid_request(
        params, tmp_path):
    """Rilievo 2 del Critic su `PBI-372`, decisione 2: `params or {}` cambiava
    in `{}` i valori falsi prima del controllo, e la chiamata arrivava allo
    strumento come «lo strumento None non esiste» invece di ricevere -32600."""
    riga = _json({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params})
    _risponde_con_un_errore_e_poi_ancora(riga, 1, -32600, tmp_path)


@pytest.mark.parametrize("argomenti", [
    pytest.param([], id="lista-vuota"),
    pytest.param("", id="stringa-vuota"),
    pytest.param(0, id="zero"),
    pytest.param(False, id="false"),
])
def test_degli_arguments_vuoti_o_falsi_si_rifiutano_come_non_oggetto_e_nel_log_restano_come_arrivati(
        argomenti, tmp_path):
    """Rilievo 2 del Critic su `PBI-372`, decisione 3 e difetto 41:
    `arguments or {}` cambiava in `{}` i valori falsi, il rifiuto diceva «è
    vuoto» invece di «non un oggetto», e nel log finiva `{}` al posto di ciò
    che il modello aveva mandato."""
    esito = tmp_path / "esito.json"
    risposte = parla("builder", esito, [*apertura(), chiamata(1, "fatto", argomenti)])

    risultato = risposte[1].get("result", {})
    assert risultato.get("isError") is True
    parole = parole_della_risposta(risultato)
    assert "non un oggetto" in parole
    assert "vuoto" not in parole
    assert not esito.exists()
    righe = Path(f"{esito}.chiamate.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(r)["argomenti"] for r in righe] == [argomenti]


def test_una_chiamata_con_un_surrogato_isolato_negli_argomenti_finisce_nel_log(tmp_path):
    """Rilievo 1 del Critic sul secondo giro di `PBI-372`, decisione 3: il log si
    scriveva in UTF-8 e un surrogato isolato lo faceva fallire con
    `UnicodeEncodeError`, così la chiamata non ci finiva."""
    esito = tmp_path / "esito.json"
    argomenti = {"riepilogo": "\ud800 finito"}
    parla_a_righe("builder", esito, [
        *map(_json, apertura()), _json(chiamata(1, "fatto", argomenti)),
    ])

    log = Path(f"{esito}.chiamate.jsonl")
    righe = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    assert [json.loads(r)["argomenti"] for r in righe] == [argomenti]


@pytest.mark.parametrize("nome, argomenti, campo", [
    pytest.param("fatto", {"riepilogo": "\ud800 finito"}, "riepilogo", id="riepilogo"),
    pytest.param("fermati", {"domanda": "e ora? \udfff"}, "domanda", id="domanda"),
])
def test_un_campo_con_un_surrogato_isolato_si_rifiuta_dicendolo(nome, argomenti, campo,
                                                               tmp_path):
    """Rilievo 1 del Critic sul secondo giro di `PBI-372`, `ADR-0027` §3: il
    file d'esito si scrive in UTF-8, il surrogato faceva fallire la scrittura e
    il modello riceveva -32603 con un messaggio di codec invece di un rifiuto
    che dice cosa correggere."""
    esito = tmp_path / "esito.json"
    fatto, risposte = parla_a_righe("builder", esito, [
        *map(_json, apertura()), _json(chiamata(1, nome, argomenti)),
        _json(richiesta(2, "tools/list")),
    ])

    assert "Traceback" not in fatto.stderr, fatto.stderr
    per_id = {r.get("id"): r for r in risposte}
    risultato = per_id.get(1, {}).get("result", {})
    assert risultato.get("isError") is True, per_id.get(1)
    assert f"«{campo}» contiene un carattere non valido" in parole_della_risposta(risultato)
    assert not esito.exists()
    assert per_id.get(2, {}).get("result", {}).get("tools")


@pytest.mark.parametrize("nome, campo", [
    pytest.param("fatto", "riepilogo", id="riepilogo"),
    pytest.param("fermati", "domanda", id="domanda"),
])
def test_dei_byte_non_utf8_dentro_un_campo_si_rifiutano_dicendolo(nome, campo, tmp_path):
    """Rilievo 1 del Critic sul terzo giro di `PBI-372`, `ADR-0027` §3: stdin
    si leggeva con `errors="replace"`, e dei byte non UTF-8 dentro una stringa
    diventavano U+FFFD in una riga JSON valida. Il file d'esito si scriveva con
    un testo che il modello non aveva mandato, e senza nessun rifiuto."""
    esito = tmp_path / "esito.json"
    riga = (b'{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": '
            b'{"name": "' + nome.encode() + b'", "arguments": {"' + campo.encode()
            + b'": "ok \xff"}}}')
    fatto, risposte = parla_a_righe("builder", esito, [
        *map(_json, apertura()), riga, _json(richiesta(2, "tools/list")),
    ])

    assert "Traceback" not in fatto.stderr, fatto.stderr
    per_id = {r.get("id"): r for r in risposte}
    risultato = per_id.get(1, {}).get("result", {})
    assert risultato.get("isError") is True, per_id.get(1)
    assert f"«{campo}» contiene un carattere non valido" in parole_della_risposta(risultato)
    assert not esito.exists()
    assert per_id.get(2, {}).get("result", {}).get("tools")


@pytest.mark.parametrize("nome, argomenti, campo", [
    pytest.param("fatto", {"riepilogo": 42}, "riepilogo", id="riepilogo-numero"),
    pytest.param("fermati", {"domanda": ["e ora?"]}, "domanda", id="domanda-lista"),
])
def test_un_campo_che_non_e_testo_si_rifiuta_dicendolo(nome, argomenti, campo, tmp_path):
    """Difetto 41, decisione 4: il rifiuto diceva «è vuoto», e il modello
    cercava il problema nel posto sbagliato."""
    esito = tmp_path / "esito.json"
    risposte = parla("builder", esito, [*apertura(), chiamata(1, nome, argomenti)])

    risultato = risposte[1].get("result", {})
    assert risultato.get("isError") is True
    parole = parole_della_risposta(risultato)
    assert f"«{campo}» non è testo" in parole
    assert "vuoto" not in parole
    assert not esito.exists()


@pytest.mark.parametrize("valore", [
    pytest.param(None, id="esito-mancante"),
    pytest.param("", id="esito-vuoto"),
])
def test_un_asdlc_esito_mancante_ferma_il_server_all_avvio(valore):
    """Difetto 42, decisione 5: si ferma come per un ruolo sbagliato, con un
    messaggio che nomina la variabile e senza traceback."""
    ambiente = {k: v for k, v in os.environ.items() if k != "ASDLC_ESITO"}
    ambiente["ASDLC_RUOLO"] = "builder"
    if valore is not None:
        ambiente["ASDLC_ESITO"] = valore
    fatto = subprocess.run(
        [sys.executable, str(SORGENTE)],
        input="".join(_json(m) + "\n" for m in apertura()),
        capture_output=True, text=True, env=ambiente, timeout=20,
    )

    assert fatto.returncode == 2
    assert "ASDLC_ESITO" in fatto.stderr
    assert "Traceback" not in fatto.stderr
    assert not fatto.stdout.strip()


def carica_il_server():
    specifica = importlib.util.spec_from_file_location("asdlc_esito", SORGENTE)
    modulo = importlib.util.module_from_spec(specifica)
    specifica.loader.exec_module(modulo)
    return modulo


def parla_in_processo(server, monkeypatch, capsys, esito, messaggi):
    """Fa girare `main()` del modulo caricato, con stdin e ambiente sostituiti:
    torna il codice d'uscita, le risposte e lo stderr."""
    monkeypatch.setenv("ASDLC_RUOLO", "builder")
    monkeypatch.setenv("ASDLC_ESITO", str(esito))
    monkeypatch.setattr(sys, "stdin",
                        io.StringIO("".join(_json(m) + "\n" for m in messaggi)))
    uscita = server.main()
    catturato = capsys.readouterr()
    risposte = [json.loads(r) for r in catturato.out.splitlines() if r.strip()]
    return uscita, risposte, catturato.err


def test_un_eccezione_non_prevista_diventa_un_errore_interno_e_il_server_continua(
        monkeypatch, capsys, tmp_path):
    """Decisione 6 di `PBI-372`: il principio è «non cade mai», non «non cade nei
    casi elencati». Un guasto che nessuno ha previsto risponde `-32603` all'`id`
    del messaggio, finisce su stderr, e il messaggio dopo ha la sua risposta."""
    server = carica_il_server()

    def guasto(*_argomenti, **_nominali):
        raise RuntimeError("guasto di prova")

    monkeypatch.setattr(server, "chiama", guasto)
    uscita, risposte, stderr = parla_in_processo(server, monkeypatch, capsys,
                                                  tmp_path / "esito.json", [
        *apertura(), chiamata(1, "fatto", {"riepilogo": "finito"}),
        richiesta(2, "tools/list"),
    ])

    assert uscita == 0
    per_id = {r.get("id"): r for r in risposte}
    assert per_id.get(1, {}).get("error", {}).get("code") == -32603
    assert per_id.get(2, {}).get("result", {}).get("tools")
    assert "guasto di prova" in stderr


def test_una_scrittura_interrotta_non_lascia_il_file_d_esito(monkeypatch, tmp_path):
    """Decisione 7 di `PBI-372`: su `main` il file nasceva con `O_EXCL` e poi si
    riempiva. Ucciso fra i due passi, il server lasciava `{"esito": "fa`, che il
    runner non legge, e ogni richiamata si rifiutava come «già dichiarato»."""
    server = carica_il_server()
    esito = tmp_path / "esito.json"

    def muore_a_meta(_oggetto, file, **_nominali):
        file.write('{"esito": "fa')
        file.flush()
        raise KeyboardInterrupt("ucciso a metà della scrittura")

    with monkeypatch.context() as sostituzioni:
        sostituzioni.setattr(json, "dump", muore_a_meta)
        with pytest.raises(KeyboardInterrupt):
            server.chiama("fatto", {"riepilogo": "finito"}, "builder", str(esito))

    assert not esito.exists(), f"resta un file a metà: {esito.read_text()!r}"
    assert not list(tmp_path.iterdir()), "il temporaneo non si è cancellato"
    risultato = server.chiama("fatto", {"riepilogo": "finito"}, "builder", str(esito))
    assert risultato["isError"] is False, parole_della_risposta(risultato)
    assert leggi_esito(esito) == {"esito": "fatto", "riepilogo": "finito"}
    assert [f.name for f in tmp_path.iterdir()] == ["esito.json"]


@pytest.mark.parametrize("nome, argomenti, campo", [
    pytest.param("fatto", {"riepilogo": ""}, "riepilogo", id="riepilogo-vuoto"),
    pytest.param("fermati", {"domanda": " \n\t "}, "domanda", id="domanda-di-spazi"),
    pytest.param("fatto", {}, "riepilogo", id="riepilogo-assente"),
])
def test_un_testo_vuoto_si_rifiuta_ancora_come_vuoto(nome, argomenti, campo, tmp_path):
    """Guardia di `PBI-372`: il rifiuto «non è testo» (decisione 4) non deve
    prendersi anche la stringa vuota, di soli spazi o assente, che restano «è
    vuoto». Le altre guardie della Verifica ci sono già:
    `test_un_ruolo_sconosciuto_ferma_il_server_all_avvio` e
    `test_la_seconda_chiamata_si_rifiuta_e_il_file_resta_quello_della_prima`."""
    esito = tmp_path / "esito.json"
    risposte = parla("builder", esito, [*apertura(), chiamata(1, nome, argomenti)])

    risultato = risposte[1].get("result", {})
    assert risultato.get("isError") is True
    parole = parole_della_risposta(risultato)
    assert f"«{campo}» è vuoto" in parole
    assert "non è testo" not in parole
    assert not esito.exists()
