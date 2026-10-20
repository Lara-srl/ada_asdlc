#!/usr/bin/env python3
"""Il server dell'esito: l'esito di un agente è una chiamata a strumento (`ADR-0027`).

Un server MCP su stdio, in sola libreria standard, con due strumenti: `fatto` e
`fermati` (il Solver ne ha tre, `PBI-507`, e il Lettore tre, `PBI-521`). Il modello li chiama, il server valida e scrive l'esito nel file che il
runner gli ha nominato. Il runner legge quel file, e non più il testo libero
dell'agente (`backlog/PBI-366`; lo collega `PBI-367`).

Il trasporto è quello stdio di MCP: un messaggio JSON-RPC per riga, in entrata
su stdin e in uscita su stdout. Il runner lo configura con due variabili:

    ASDLC_RUOLO   `builder`, `critic`, `solver` o `lettore`: cambia lo schema di `fatto`, o gli strumenti
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
import re
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

NOME = "asdlc"
VERSIONE = "1"

RUOLI = ["builder", "critic", "solver", "lettore"]
VERDETTI = ["pass", "non pronto"]


def _testo(descrizione: str) -> dict:
    return {"type": "string", "description": descrizione}


STRUMENTI_DEL_SOLVER = [
    {
        "name": "risolvi",
        "description": ("Risolve il blocco con una risposta e la sua fonte. La prima "
                        "chiamata valida è definitiva."),
        "inputSchema": {"type": "object",
                        "properties": {"risposta": _testo("La risposta al blocco."),
                                       "evidenza": _testo("Il file che la prova, "
                                                          "`percorso` o `percorso:riga`.")},
                        "required": ["risposta", "evidenza"]},
    },
    {
        "name": "segnala_limite_runner",
        "description": ("Segnala un limite del runner, con la riproduzione. La prima "
                        "chiamata valida è definitiva."),
        "inputSchema": {"type": "object",
                        "properties": {"causa": _testo("La causa `runner-*`."),
                                       "comando": _testo("Il comando che riproduce."),
                                       "output": _testo("L'output sbagliato."),
                                       "commit": _testo("Il commit in cui si vede."),
                                       "pbi": _testo("Il testo completo del PBI a monte: "
                                                     "titolo, Direttiva con Scope, Verifica.")},
                        "required": ["causa", "comando", "output", "commit", "pbi"]},
    },
    {
        "name": "chiedi_a_francesco",
        "description": ("Chiede a Francesco una decisione che il Solver non può prendere. "
                        "La prima chiamata valida è definitiva."),
        "inputSchema": {"type": "object",
                        "properties": {"domanda": _testo("La domanda, per intero.")},
                        "required": ["domanda"]},
    },
]

# Le sette domande del Lettore (`ADR-0031`, decisione 1): rosso sulla base, GREEN
# scrivibile, test che contraddice, albero sporcato, esecuzione, decisione lasciata,
# nomi veri.
DOMANDE_DEL_LETTORE = ["R", "F", "T", "A", "E", "D", "N"]

STRUMENTI_DEL_LETTORE = [
    {
        "name": "rilievo",
        "description": ("Registra un rilievo: solo ciò che fermerebbe il giro, con la "
                        "prova. Si può chiamare più volte."),
        "inputSchema": {"type": "object",
                        "properties": {"domanda": {"type": "string",
                                                   "enum": DOMANDE_DEL_LETTORE,
                                                   "description": "La domanda a cui risponde."},
                                       "criterio": {"type": "integer", "minimum": 0,
                                                    "description": "Il criterio della Verifica, "
                                                                   "0 per il PBI intero."},
                                       "testo": _testo("Il rilievo, per intero."),
                                       "evidenza": _testo("Il file che lo prova, "
                                                          "`percorso` o `percorso:riga`.")},
                        "required": ["domanda", "criterio", "testo", "evidenza"]},
    },
    {
        "name": "sonda",
        "description": ("Propone il test RED di un criterio, già scritto nell'albero: lo "
                        "esegue il runner. Si può chiamare più volte."),
        "inputSchema": {"type": "object",
                        "properties": {"criterio": {"type": "integer", "minimum": 1,
                                                    "description": "Il criterio della Verifica."},
                                       "file": _testo("Il file del test, dalla radice."),
                                       "nome": _testo("Il nome del test nel file.")},
                        "required": ["criterio", "file", "nome"]},
    },
    {
        "name": "letto",
        "description": ("Chiude la lettura con il riepilogo. È definitiva: dopo, rilievo "
                        "e sonda si rifiutano."),
        "inputSchema": {"type": "object",
                        "properties": {"riepilogo": _testo("Il riepilogo della lettura.")},
                        "required": ["riepilogo"]},
    },
]


def strumenti(ruolo: str) -> list[dict]:
    """Gli strumenti con lo schema del ruolo: `fatto` e `fermati` per Builder e
    Critic, i tre esiti del Solver per il Solver (`PBI-507`), i tre del Lettore per il
    Lettore (`PBI-521`). Lo schema è per il modello: la CLI non lo fa rispettare, e le
    regole le applica il server (`ADR-0027`, decisione 3)."""
    if ruolo == "solver":
        return STRUMENTI_DEL_SOLVER
    if ruolo == "lettore":
        return STRUMENTI_DEL_LETTORE
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


def chiama(nome, argomenti, ruolo: str, esito: str) -> dict:
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
    if ruolo == "solver":
        if nome not in ("risolvi", "segnala_limite_runner", "chiedi_a_francesco"):
            return _contenuto(f"Lo strumento {nome!r} non è del Solver: chiama risolvi, "
                              "segnala_limite_runner o chiedi_a_francesco.", errore=True)
        if not isinstance(argomenti, dict):
            return _contenuto(f"Gli argomenti di {nome} non sono un oggetto: richiama "
                              f"{nome} con i campi per nome.", errore=True)
        return {"risolvi": _risolvi, "segnala_limite_runner": _segnala_limite,
                "chiedi_a_francesco": _chiedi_a_francesco}[nome](argomenti, esito)
    if ruolo == "lettore":
        if nome == "letto":
            return _letto(argomenti, esito)
        return _accumula(nome, argomenti, esito)
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
    # Un surrogato isolato passa `json.loads` ma non si scrive in UTF-8: si
    # rifiuta qui, prima del temporaneo, e non come errore interno (`PBI-372`).
    try:
        testo.encode("utf-8")
    except UnicodeEncodeError:
        return _contenuto(f"Il campo «{campo}» contiene un carattere non valido: "
                          f"riscrivilo e richiama {nome}.", errore=True)
    if ruolo == "critic" and nome == "fatto" and argomenti.get("verdetto") not in VERDETTI:
        return _contenuto(f"Il campo «verdetto» vale {argomenti.get('verdetto')!r}: deve "
                          f"essere uno fra {VERDETTI}. Richiama fatto con il verdetto.",
                          errore=True)
    dichiarato = {"esito": nome}
    if ruolo == "critic" and nome == "fatto":
        dichiarato["verdetto"] = argomenti["verdetto"]
    dichiarato[campo] = testo
    return _scrivi(dichiarato, nome, esito)


def _scrivi(dichiarato: dict, nome: str, esito: str) -> dict:
    """Scrive `dichiarato` nel file `esito` se è la prima chiamata valida."""
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


def _file_dell_albero(evidenza: str) -> bool:
    """Se `evidenza`, `percorso` o `percorso:riga`, nomina un file dell'albero: la
    cartella da cui parte il server (`PBI-507`, R2)."""
    percorso = re.sub(r":\d+$", "", evidenza.strip())
    # Relativo alla radice del progetto (decisione 3): un assoluto, o un `../` che esce
    # dall'albero, esiste ma non è una fonte del repository.
    radice = Path.cwd().resolve()
    return (not os.path.isabs(percorso) and Path(percorso).resolve().is_relative_to(radice)
            and os.path.isfile(percorso))


def _risolvi(argomenti: dict, esito: str) -> dict:
    """`risolvi`: la risposta porta come `evidenza` un file che esiste nell'albero
    del giro, con un eventuale `:riga` (`PBI-507`, R2). L'albero è la cartella da
    cui parte il server."""
    risposta, evidenza = argomenti.get("risposta"), argomenti.get("evidenza")
    for campo, valore in (("risposta", risposta), ("evidenza", evidenza)):
        if not isinstance(valore, str) or not valore.strip():
            return _contenuto(f"Il campo «{campo}» è vuoto o non è testo: scrivilo e "
                              "richiama risolvi.", errore=True)
    if not _file_dell_albero(evidenza):
        return _contenuto(f"L'evidenza {evidenza!r} non è un file dell'albero: nomina "
                          "il file che prova la risposta e richiama risolvi.", errore=True)
    return _scrivi({"esito": "risolto", "risposta": risposta, "evidenza": evidenza},
                   "risolvi", esito)


def _chiedi_a_francesco(argomenti: dict, esito: str) -> dict:
    """`chiedi_a_francesco`: l'esito `intento`, con la domanda per intero."""
    domanda = argomenti.get("domanda")
    if not isinstance(domanda, str) or not domanda.strip():
        return _contenuto("Il campo «domanda» è vuoto o non è testo: scrivilo e "
                          "richiama chiedi_a_francesco.", errore=True)
    return _scrivi({"esito": "intento", "domanda": domanda}, "chiedi_a_francesco", esito)


def _segnala_limite(argomenti: dict, esito: str) -> dict:
    """`segnala_limite_runner`: registra il limite del runner con la sua
    riproduzione (`PBI-507`, R3)."""
    dichiarato = {"esito": "limite-del-runner"}
    for campo in ("causa", "comando", "output", "commit", "pbi"):
        valore = argomenti.get(campo)
        if not isinstance(valore, str) or not valore.strip():
            return _contenuto(f"Il campo «{campo}» è vuoto o non è testo: scrivilo e "
                              "richiama segnala_limite_runner.", errore=True)
        dichiarato[campo] = valore
    if not os.environ.get("ASDLC_CLONE", "").strip():
        return _contenuto("Il progetto non dichiara `[rilascio].clone`: la PR a monte non si "
                          "può aprire. Non richiamare segnala_limite_runner; usa "
                          "chiedi_a_francesco.", errore=True)
    cause = [c.strip() for c in os.environ.get("ASDLC_CAUSE", "").split(",") if c.strip()]
    if dichiarato["causa"].strip() not in cause:
        return _contenuto(f"La causa {dichiarato['causa']!r} non è nell'elenco "
                          f"{cause}: scegline una e richiama segnala_limite_runner.",
                          errore=True)
    esiste = subprocess.run(["git", "cat-file", "-e", f"{dichiarato['commit'].strip()}^{{commit}}"],
                            capture_output=True).returncode == 0
    if not esiste:
        return _contenuto(f"Il commit {dichiarato['commit']!r} non esiste nell'albero: "
                          "nomina quello in cui il limite si vede e richiama "
                          "segnala_limite_runner.", errore=True)
    return _scrivi(dichiarato, "segnala_limite_runner", esito)


# I campi di `rilievo` e `sonda` che finiscono nella lettura, nell'ordine dello schema.
CAMPI_DEL_LETTORE = {"rilievo": ("domanda", "criterio", "testo", "evidenza"),
                     "sonda": ("criterio", "file", "nome")}


def _accumula(nome: str, argomenti: dict, esito: str) -> dict:
    """`rilievo` e `sonda`: una riga JSON per chiamata in `<esito>.lettura.jsonl`,
    `{"strumento", ...argomenti}` (`PBI-521`, decisione 2). Non chiudono la lettura.

    Le regole sono quelle della decisione 1: la domanda è una delle sette, il criterio
    un intero (almeno 0 per un rilievo, che con 0 vale per il PBI intero; almeno 1 per
    una sonda), i testi pieni, l'evidenza e il file della sonda file dell'albero. Se il
    file sia un test lo decide il runner. Dopo `letto` la lettura è chiusa."""
    if os.path.exists(esito):
        return _contenuto(f"La lettura è già chiusa con letto: {nome} non cambia niente.",
                          errore=True)
    for campo in CAMPI_DEL_LETTORE[nome]:
        valore = argomenti.get(campo)
        if campo == "criterio":
            minimo = 1 if nome == "sonda" else 0
            if not isinstance(valore, int) or isinstance(valore, bool) or valore < minimo:
                return _contenuto(f"Il campo «criterio» vale {valore!r}: deve essere un "
                                  f"intero, almeno {minimo}. Richiama {nome}.", errore=True)
        elif not isinstance(valore, str) or not valore.strip():
            return _contenuto(f"Il campo «{campo}» è vuoto o non è testo: scrivilo e "
                              f"richiama {nome}.", errore=True)
    if nome == "rilievo" and argomenti["domanda"] not in DOMANDE_DEL_LETTORE:
        return _contenuto(f"La domanda {argomenti['domanda']!r} non è una fra "
                          f"{DOMANDE_DEL_LETTORE}: scegline una e richiama rilievo.",
                          errore=True)
    campo = "evidenza" if nome == "rilievo" else "file"
    if not _file_dell_albero(argomenti[campo]):
        return _contenuto(f"Il campo «{campo}» vale {argomenti[campo]!r}, che non è un file "
                          f"dell'albero: nomina un file che c'è e richiama {nome}.",
                          errore=True)
    riga ={"strumento": nome, **{c: argomenti.get(c) for c in CAMPI_DEL_LETTORE[nome]}}
    with open(f"{esito}.lettura.jsonl", "a", encoding="utf-8") as lettura:
        lettura.write(json.dumps(riga, ensure_ascii=False) + "\n")
    return _contenuto(f"Registrato: {nome}.", errore=False)


def _letto(argomenti: dict, esito: str) -> dict:
    """`letto`: l'esito definitivo della lettura, con i rilievi e le sonde letti dal
    `.jsonl` in questo momento (`PBI-521`, decisione 2)."""
    rilievi: list[dict] = []
    sonde: list[dict] = []
    try:
        with open(f"{esito}.lettura.jsonl", encoding="utf-8") as lettura:
            for riga in lettura:
                if riga.strip():
                    voce = json.loads(riga)
                    strumento = voce.pop("strumento")
                    (rilievi if strumento == "rilievo" else sonde).append(voce)
    except FileNotFoundError:
        pass
    return _scrivi({"esito": "letto", "riepilogo": argomenti.get("riepilogo"),
                    "rilievi": rilievi, "sonde": sonde}, "letto", esito)


def registra(nome, argomenti, esito: str) -> None:
    """Una riga del log per chiamata, prima di validarla: anche quelle
    rifiutate ci finiscono. La riga si scrive in ASCII, così un surrogato
    isolato negli argomenti non fa fallire la scrittura (`PBI-372`)."""
    riga = {"ora": datetime.now().astimezone().isoformat(), "nome": nome,
            "argomenti": argomenti}
    with open(f"{esito}.chiamate.jsonl", "a", encoding="utf-8") as log:
        log.write(json.dumps(riga) + "\n")


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
    # Il default vale solo per un campo assente o `null`: `or {}` cambierebbe
    # in un oggetto anche `[]`, `""`, `0` e `false`, che vanno rifiutati.
    parametri = messaggio.get("params")
    if parametri is None:
        parametri = {}
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
        nome, argomenti = parametri.get("name"), parametri.get("arguments")
        if argomenti is None:
            argomenti = {}
        registra(nome, argomenti, esito)
        risultato = chiama(nome, argomenti, ruolo, esito)
    else:
        return _errore(messaggio["id"], -32601, f"metodo sconosciuto: {metodo}")
    return {"jsonrpc": "2.0", "id": messaggio["id"], "result": risultato}


def _risposta_alla_riga(riga: str, ruolo: str, esito: str) -> str | None:
    """La riga da scrivere su stdout per una riga letta, o `None` se non ha
    risposta. La rete avvolge tutta la gestione, parse e serializzazione
    comprese: un'eccezione che nessuno ha previsto non esce dal ciclo di
    lettura. Va su stderr, e la richiesta riceve `-32603`; una notifica non ha
    risposta nemmeno così (`PBI-372`, decisione 6).

    Il parse rifiuta con `-32700` anche ciò che non è un `JSONDecodeError`: una
    riga annidata oltre la ricorsione, un intero oltre il limite di cifre. La
    risposta si scrive in ASCII, così un surrogato isolato ripetuto dal
    messaggio non fa cadere la scrittura."""
    messaggio = None
    try:
        try:
            messaggio = json.loads(riga)
        except (ValueError, RecursionError) as errore:
            risposta = _errore(None, -32700, f"la riga non è JSON: {errore}")
        else:
            risposta = rispondi(messaggio, ruolo, esito)
        return None if risposta is None else json.dumps(risposta)
    except Exception as errore:
        traceback.print_exc(file=sys.stderr)
        if isinstance(messaggio, dict) and "id" not in messaggio:
            return None
        id_ = messaggio.get("id") if isinstance(messaggio, dict) else None
        return json.dumps(_errore(id_, -32603, f"errore interno del server: {errore}"))


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
    # Dei byte che non sono UTF-8 diventano surrogati isolati invece di far
    # cadere la lettura: fuori da una stringa la riga si rifiuta come non JSON,
    # dentro un campo li rifiuta `chiama()`, e il testo non si altera in
    # silenzio come farebbe un carattere di sostituzione (`PBI-372`).
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(errors="surrogateescape")
    for riga in sys.stdin:
        if not riga.strip():
            continue
        risposta = _risposta_alla_riga(riga, ruolo, esito)
        if risposta is not None:
            sys.stdout.write(risposta + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
