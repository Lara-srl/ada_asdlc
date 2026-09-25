#!/usr/bin/env python3
"""Il server dell'esito: l'esito di un agente è una chiamata a strumento (`ADR-0027`).

Un server MCP su stdio, in sola libreria standard, con due strumenti: `fatto` e
`fermati`. Il modello li chiama, il server valida e scrive l'esito nel file che il
runner gli ha nominato. Il runner legge quel file, e non più il testo libero
dell'agente (`backlog/PBI-366`; lo collega `PBI-367`).

Il trasporto è quello stdio di MCP: un messaggio JSON-RPC per riga, in entrata
su stdin e in uscita su stdout. Il runner lo configura con due variabili:

    ASDLC_RUOLO   `builder` o `critic`: cambia lo schema di `fatto`
    ASDLC_ESITO   il file in cui scrivere l'esito; accanto, `<esito>.chiamate.jsonl`
                  registra ogni chiamata, valida o rifiutata

Il server non esce per un ingresso che non si aspetta (`PBI-372`): una riga che
non è JSON, un messaggio o dei `params` che non sono un oggetto ricevono un
errore JSON-RPC, una chiamata con argomenti sbagliati un `isError`, e un guasto
che nessuno ha previsto un `-32603` con il traceback su stderr. Si ferma
all'avvio, con un messaggio su stderr e l'uscita 2, solo se una delle due
variabili lo rende inutilizzabile.
"""

import json
import os
import sys
import tempfile
import traceback
from datetime import datetime

NOME = "asdlc"
VERSIONE = "1"

RUOLI = ["builder", "critic"]
VERDETTI = ["pass", "non pronto"]


def _testo(descrizione: str) -> dict:
    return {"type": "string", "description": descrizione}


def strumenti(ruolo: str) -> list[dict]:
    """I due strumenti con lo schema del ruolo. Lo schema è per il modello: la
    CLI non lo fa rispettare, e le regole le applica il server (`ADR-0027`,
    decisione 3)."""
    proprieta_fatto = {"riepilogo": _testo("Il riepilogo del lavoro fatto.")}
    descrizione_fatto = "Dichiara che il lavoro è finito."
    if ruolo == "critic":
        proprieta_fatto = {
            "verdetto": {"type": "string", "enum": VERDETTI,
                         "description": "Il verdetto sulla revisione."},
            "riepilogo": _testo("Il rapporto della revisione, per intero."),
        }
        descrizione_fatto = "Dichiara il verdetto della revisione, con il rapporto."
    return [
        {
            "name": "fatto",
            "description": descrizione_fatto + " La prima chiamata valida è definitiva.",
            "inputSchema": {"type": "object", "properties": proprieta_fatto,
                            "required": list(proprieta_fatto)},
        },
        {
            "name": "fermati",
            "description": ("Fermati con una domanda per una persona, quando non puoi "
                            "decidere da solo. La prima chiamata valida è definitiva."),
            "inputSchema": {"type": "object",
                            "properties": {"domanda": _testo("La domanda, per intero.")},
                            "required": ["domanda"]},
        },
    ]


def _contenuto(testo: str, errore: bool) -> dict:
    return {"content": [{"type": "text", "text": testo}], "isError": errore}


# Il tipo ricevuto con il nome che ha in JSON, per il rifiuto di un campo che
# non è testo: è il nome che il modello ha scritto.
TIPI_JSON = {int: "un numero", float: "un numero", bool: "un booleano",
             list: "una lista", dict: "un oggetto"}


def chiama(nome: str, argomenti: dict, ruolo: str, esito: str) -> dict:
    """Scrive l'esito della chiamata nel file `esito`: l'oggetto che il runner
    leggerà, con il nome dello strumento sotto `esito` e i campi dello schema accanto.

    Una chiamata che non passa la validazione riceve `isError` con il motivo, e
    il file non si scrive: il modello legge l'errore e può richiamare. La prima
    chiamata valida è definitiva, e il file non è mai a metà: si scrive un
    temporaneo nella stessa cartella e lo si collega al nome definitivo con
    `os.link`, che fallisce se il nome c'è già. Dopo la prima, ogni chiamata si
    rifiuta e lo lascia com'è. Il temporaneo finisce in `.json`, così uno che
    sopravvive a un server ucciso lo ignora `runs/*.json` (`PBI-372`, decisione 7).

    Nel file entrano solo i campi dello schema del ruolo: la CLI non lo fa
    rispettare, e un argomento in più non deve riscrivere l'esito."""
    if nome not in ("fatto", "fermati"):
        return _contenuto(f"Lo strumento {nome!r} non esiste: chiama fatto o fermati.",
                          errore=True)
    if not isinstance(argomenti, dict):
        ricevuto = TIPI_JSON.get(type(argomenti), "un valore")
        return _contenuto(f"Gli argomenti di {nome} sono {ricevuto}, non un oggetto: "
                          f"richiama {nome} con i campi per nome.", errore=True)
    campo = "domanda" if nome == "fermati" else "riepilogo"
    testo = argomenti.get(campo)
    if testo is not None and not isinstance(testo, str):
        return _contenuto(f"Il campo «{campo}» non è testo: è "
                          f"{TIPI_JSON.get(type(testo), 'un valore')}. Scrivilo come "
                          f"testo e richiama {nome}.", errore=True)
    if testo is None or not testo.strip():
        return _contenuto(f"Il campo «{campo}» è vuoto: scrivilo e richiama {nome}.",
                          errore=True)
    if ruolo == "critic" and nome == "fatto" and argomenti.get("verdetto") not in VERDETTI:
        return _contenuto(f"Il campo «verdetto» vale {argomenti.get('verdetto')!r}: deve "
                          f"essere uno fra {VERDETTI}. Richiama fatto con il verdetto.",
                          errore=True)
    dichiarato = {"esito": nome}
    if ruolo == "critic" and nome == "fatto":
        dichiarato["verdetto"] = argomenti["verdetto"]
    dichiarato[campo] = testo
    cartella, nome_esito = os.path.split(os.path.abspath(esito))
    descrittore, temporaneo = tempfile.mkstemp(dir=cartella, prefix=f"{nome_esito}.",
                                               suffix=".json")
    try:
        os.chmod(temporaneo, 0o644)
        with os.fdopen(descrittore, "w", encoding="utf-8") as file:
            json.dump(dichiarato, file, ensure_ascii=False)
        os.link(temporaneo, esito)
    except FileExistsError:
        return _contenuto("Esito già dichiarato: la prima chiamata valida è "
                          "definitiva, e questa non cambia niente.", errore=True)
    finally:
        os.unlink(temporaneo)
    return _contenuto(f"Esito registrato: {nome}.", errore=False)


def registra(nome: str, argomenti: dict, esito: str) -> None:
    """Una riga del log per chiamata, prima di validarla: anche quelle
    rifiutate ci finiscono."""
    riga = {"ora": datetime.now().astimezone().isoformat(), "nome": nome,
            "argomenti": argomenti}
    with open(f"{esito}.chiamate.jsonl", "a", encoding="utf-8") as log:
        log.write(json.dumps(riga, ensure_ascii=False) + "\n")


def _errore(id_, codice: int, testo: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": codice, "message": testo}}


def rispondi(messaggio, ruolo: str, esito: str) -> dict | None:
    """La risposta a un messaggio, o `None` per una notifica, che non ne ha.

    Un messaggio o dei `params` che non sono un oggetto ricevono `-32600`, con
    l'`id` del messaggio se si legge (`PBI-372`, decisione 2)."""
    if not isinstance(messaggio, dict):
        return _errore(None, -32600, "il messaggio non è un oggetto JSON")
    if "id" not in messaggio:
        return None
    metodo = messaggio.get("method")
    parametri = messaggio.get("params") or {}
    if not isinstance(parametri, dict):
        return _errore(messaggio["id"], -32600, "i params non sono un oggetto JSON")
    if metodo == "initialize":
        risultato = {
            "protocolVersion": parametri.get("protocolVersion"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": NOME, "version": VERSIONE},
        }
    elif metodo == "tools/list":
        risultato = {"tools": strumenti(ruolo)}
    elif metodo == "tools/call":
        nome, argomenti = parametri.get("name"), parametri.get("arguments") or {}
        registra(nome, argomenti, esito)
        risultato = chiama(nome, argomenti, ruolo, esito)
    else:
        return _errore(messaggio["id"], -32601, f"metodo sconosciuto: {metodo}")
    return {"jsonrpc": "2.0", "id": messaggio["id"], "result": risultato}


def _rispondi_senza_cadere(messaggio, ruolo: str, esito: str) -> dict | None:
    """`rispondi()` con la rete sotto: un'eccezione che nessuno ha previsto non
    esce dal ciclo di lettura. Va su stderr, e la richiesta riceve `-32603`; una
    notifica non ha risposta nemmeno così (`PBI-372`, decisione 6)."""
    try:
        return rispondi(messaggio, ruolo, esito)
    except Exception as errore:
        traceback.print_exc(file=sys.stderr)
        if isinstance(messaggio, dict) and "id" not in messaggio:
            return None
        id_ = messaggio.get("id") if isinstance(messaggio, dict) else None
        return _errore(id_, -32603, f"errore interno del server: {errore}")


def main() -> int:
    # Un ruolo sbagliato che valesse come builder toglierebbe al Critic il
    # verdetto obbligatorio: meglio un server che non parte, che il runner legge
    # come «senza esito» (`ADR-0027`, §Fuori da questa decisione).
    ruolo = os.environ.get("ASDLC_RUOLO")
    if ruolo not in RUOLI:
        print(f"ASDLC_RUOLO vale {ruolo!r}: deve essere uno fra {RUOLI}.",
              file=sys.stderr)
        return 2
    # Senza file d'esito il server non ha dove scrivere: si ferma come per il
    # ruolo, non con un `KeyError` (`PBI-372`, decisione 5).
    esito = os.environ.get("ASDLC_ESITO", "")
    if not esito.strip():
        print("ASDLC_ESITO manca o è vuota: deve nominare il file dell'esito.",
              file=sys.stderr)
        return 2
    for riga in sys.stdin:
        if not riga.strip():
            continue
        try:
            messaggio = json.loads(riga)
        except json.JSONDecodeError as errore:
            risposta = _errore(None, -32700, f"la riga non è JSON: {errore}")
        else:
            risposta = _rispondi_senza_cadere(messaggio, ruolo, esito)
        if risposta is not None:
            sys.stdout.write(json.dumps(risposta, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
