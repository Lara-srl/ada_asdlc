#!/usr/bin/env python3
"""Il server dell'esito: l'esito di un agente è una chiamata a strumento (`ADR-0027`).

Un server MCP su stdio, in sola libreria standard, con due strumenti: `fatto` e
`fermati`. Il modello li chiama, il server valida e scrive l'esito nel file che il
runner gli ha nominato. Il runner legge quel file, e non più il testo libero
dell'agente (`backlog/PBI-366`; lo collega `PBI-367`).

Il trasporto è quello stdio di MCP: un messaggio JSON-RPC per riga, in entrata
su stdin e in uscita su stdout. Il runner lo configura con due variabili:

    ASDLC_RUOLO   `builder` o `critic`: cambia lo schema di `fatto`
    ASDLC_ESITO   il file in cui scrivere l'esito
"""

import json
import os
import sys

NOME = "asdlc"
VERSIONE = "1"

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
            "description": descrizione_fatto,
            "inputSchema": {"type": "object", "properties": proprieta_fatto,
                            "required": list(proprieta_fatto)},
        },
        {
            "name": "fermati",
            "description": ("Fermati con una domanda per una persona, quando non puoi "
                            "decidere da solo."),
            "inputSchema": {"type": "object",
                            "properties": {"domanda": _testo("La domanda, per intero.")},
                            "required": ["domanda"]},
        },
    ]


def rispondi(messaggio: dict, ruolo: str) -> dict | None:
    """La risposta a un messaggio, o `None` per una notifica, che non ne ha."""
    if "id" not in messaggio:
        return None
    metodo = messaggio.get("method")
    parametri = messaggio.get("params") or {}
    if metodo == "initialize":
        risultato = {
            "protocolVersion": parametri.get("protocolVersion"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": NOME, "version": VERSIONE},
        }
    elif metodo == "tools/list":
        risultato = {"tools": strumenti(ruolo)}
    else:
        return {"jsonrpc": "2.0", "id": messaggio["id"],
                "error": {"code": -32601, "message": f"metodo sconosciuto: {metodo}"}}
    return {"jsonrpc": "2.0", "id": messaggio["id"], "result": risultato}


def main() -> int:
    ruolo = os.environ.get("ASDLC_RUOLO", "builder")
    for riga in sys.stdin:
        if not riga.strip():
            continue
        risposta = rispondi(json.loads(riga), ruolo)
        if risposta is not None:
            sys.stdout.write(json.dumps(risposta, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
