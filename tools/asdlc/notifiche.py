"""Le notifiche del tick su Slack, con un Incoming Webhook (`backlog/PBI-533`).

Un fermo si scopriva guardando: `runs/coda.log` di un progetto, una PR, un
`attende` che si ripete. Il 26/10 il tick di `ada_asdlc` ha scritto 84 volte lo
stesso `non lanciato` in 14 ore, e nessuno lo ha saputo. Qui il tick manda un
messaggio su Slack quando la sua decisione **cambia** verso uno stato che chiede
una persona, o che una persona vuole sapere: un messaggio per cambio, non uno
ogni dieci minuti.

L'evento si ricava dal tipo della decisione del tick, dall'ultimo esito del PBI e
dal sito del tick che scrive la riga, in codice, mai dal testo di un modello
(`ADR-0027`). Il webhook è un segreto: il suo indirizzo sta in
`~/.config/asdlc/slack-webhook`, fuori dai repository, e non esce mai dal
processo (decisione 5).
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Il tetto di una `POST` al webhook, in secondi (decisione 6): i test lo abbassano.
TIMEOUT = 10

# Il posto della memoria degli eventi che vengono dallo stato del tick: un fermo,
# una barriera, la coda finita, un guasto, il checkout non allineato, la pausa. Ne
# vale uno alla volta, e l'evento uguale al precedente non si rimanda.
STATO = "stato"


@dataclass(frozen=True)
class Evento:
    """Un messaggio da mandare. `tipo`, `pbi` e `motivo` sono la chiave con cui il
    tick riconosce lo stesso evento della volta prima (decisione 2); `testo` è ciò
    che arriva su Slack, nel campo `text` del JSON (decisione 7).

    `posto` è la casella della memoria in cui la chiave si ricorda: lo stato del
    tick ne ha una sola, ogni PR che aspetta una persona la sua, perché due PR
    ferme nello stesso tick non si rimandino a vicenda. `di_fila` è quante volte
    l'evento deve venire in tick consecutivi prima di mandare: due per il `non
    lanciato` dello stesso PBI, tre per il `guasto` della stessa sorgente."""

    tipo: str
    pbi: str
    motivo: str
    testo: str
    posto: str = STATO
    di_fila: int = 1


def file_del_webhook() -> Path:
    """`~/.config/asdlc/slack-webhook`, calcolato quando serve e non all'import, come
    `file_di_pausa()` del tick: i test spostano `HOME`. Non sta in `asdlc.toml`, che
    non porta percorsi di macchina, e lo leggono tutti i progetti della macchina
    (decisione 4)."""
    return Path.home() / ".config" / "asdlc" / "slack-webhook"


def file_della_memoria(repo: Path, cfg) -> Path:
    """`<registro>/notifiche.json` del checkout `repo`: gli ultimi eventi mandati e
    i conti di fila (decisione 2). La cartella del registro è ignorata da git."""
    return repo / cfg.registro.cartella / "notifiche.json"


def della_decisione(decisione, progetto: str, esito: dict | None, riga: str) -> Evento | None:
    """L'evento della decisione del tick, o `None` se non è un evento.

    `esito` è l'ultimo esito del PBI della decisione (`ultimo_esito()` del tick),
    o `None`; `riga` è la decisione come il tick la scrive nel log (`racconta()`).
    Il tipo della decisione si riconosce dal nome della classe e non con
    `isinstance`: il tick importa questo modulo, e un import all'indietro di
    `asdlc.coda` darebbe un'altra copia delle classi a un tick lanciato per percorso.
    """
    tipo = type(decisione).__name__
    if tipo == "Attende" and decisione.pr == ():
        motivo = (f"{esito.get('stato')} ({esito.get('motivo')})" if esito is not None
                  else "nessun rapporto del giro")
        domanda = (esito or {}).get("domanda")
        testo = f"⛔ {progetto}: {decisione.pbi} fermo — {motivo}"
        return Evento("fermo", decisione.pbi, motivo,
                      testo + (f" — domanda: {domanda}" if domanda else ""))
    if tipo == "AttendeLaPreverifica":
        motivo = f"preverifica, {decisione.rilievi} rilievi: correggi il PBI"
        return Evento("fermo", decisione.pbi, motivo,
                      f"⛔ {progetto}: {decisione.pbi} fermo — {motivo}")
    # Il guasto si conta per sorgente, e il testo resta fuori dalla chiave: l'uscita
    # di `gh` cambia da un tick all'altro (decisione 2).
    if (tipo == "Barriera" and decisione.guasto) or (tipo == "Attende" and decisione.pr is None):
        sorgente = "barriera" if tipo == "Barriera" else "pr"
        return Evento("guasto", "", sorgente, f"⚠️ {progetto}: il tick non riesce — {riga}",
                      di_fila=3)
    if tipo == "Barriera":
        return Evento("barriera", "", decisione.testo,
                      f"⏸️ {progetto}: barriera — {decisione.testo}")
    if tipo == "Finita":
        return Evento("finita", "", "", f"🏁 {progetto}: coda finita")
    return None


def non_lanciato(progetto: str, pbi: str, motivo: str) -> Evento:
    """Il `non lanciato` di `pbi`: si manda al secondo tick di fila sullo stesso PBI.
    Il motivo porta l'uscita di un comando e cambia da un tick all'altro, quindi
    resta fuori dalla chiave: «lo stesso» `non lanciato` è lo stesso PBI."""
    return Evento("non-lanciato", pbi, "", f"⛔ {progetto}: {pbi} non parte — {motivo}",
                  di_fila=2)


def pronto(progetto: str, numero, manca: str) -> Evento:
    """La PR `numero` che il tick non mergia e aspetta una persona, con la prima
    condizione di `ADR-0033` che manca."""
    return Evento("pronto", "", manca,
                  f"✅ {progetto}: PR #{numero} da mergiare a mano — {manca}",
                  posto=f"pr #{numero}")


def rilascio(progetto: str, pbi: str, tag: str) -> Evento:
    """Il tag che il tick ha tagliato per `pbi`: ogni tag è nuovo, e ha il suo posto."""
    return Evento("rilascio", pbi, tag, f"🏷️ {progetto}: {tag} da {pbi}", posto=f"tag {tag}")


def non_allineato(progetto: str, ragione: str) -> Evento:
    return Evento("non-allineato", "", ragione,
                  f"⚠️ {progetto}: checkout non allineato — {ragione}")


def reinstallazione(progetto: str, riga: str) -> Evento | None:
    """La reinstallazione fallita, dalla riga che `reinstalla()` del tick rende; una
    reinstallazione riuscita non è un evento."""
    prefisso = "reinstallazione fallita: "
    if not riga.startswith(prefisso):
        return None
    motivo = riga.removeprefix(prefisso)
    return Evento("reinstallazione", "", motivo,
                  f"⚠️ {progetto}: reinstallazione fallita — {motivo}")


def pausa(progetto: str, motivo: str) -> Evento:
    return Evento("pausa", "", motivo, f"⏸️ {progetto}: in pausa — {motivo}")


def rompi_le_file(repo: Path, cfg, decisione, evento: Evento | None) -> None:
    """Toglie dalla memoria i conti di fila che la decisione di questo tick
    interrompe (decisione 2). Il conto del `guasto` resta solo se la decisione è
    ancora un guasto; quello del `non lanciato` solo se la decisione è un lancio,
    perché il `non lanciato` arriva dopo, nello stesso tick: è la coppia
    `lancia` → `non lanciato` che si ripete, e il lancio non la deve azzerare."""
    if not cfg.notifiche.attive:
        return
    tieni = {evento.tipo} if evento is not None and evento.di_fila > 1 else set()
    if type(decisione).__name__ == "Lancia":
        tieni.add("non-lanciato")
    file = file_della_memoria(repo, cfg)
    memoria = leggi_memoria(file)
    conti = memoria.get("di_fila", {})
    rotti = [tipo for tipo in conti if tipo not in tieni]
    if rotti:
        for tipo in rotti:
            del conti[tipo]
        scrivi_memoria(file, memoria)


def leggi_memoria(file: Path) -> dict:
    try:
        memoria = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return memoria if isinstance(memoria, dict) else {}


def manda(repo: Path, cfg, evento: Evento | None) -> None:
    """Manda `evento` al webhook, se le notifiche sono accese, l'evento è fra quelli
    di `[notifiche].eventi`, è venuto `di_fila` volte e non è lo stesso evento
    dell'ultima volta nel suo posto; poi lo scrive nella memoria del checkout."""
    if evento is None or not cfg.notifiche.attive or evento.tipo not in cfg.notifiche.eventi:
        return
    file = file_della_memoria(repo, cfg)
    memoria = leggi_memoria(file)
    chiave = [evento.tipo, evento.pbi, evento.motivo]
    if evento.di_fila > 1:
        conti = memoria.setdefault("di_fila", {})
        conto = conti.get(evento.tipo, {})
        conti[evento.tipo] = {"chiave": chiave,
                              "conto": conto.get("conto", 0) + 1 if conto.get("chiave") == chiave
                              else 1}
        scrivi_memoria(file, memoria)
        if conti[evento.tipo]["conto"] < evento.di_fila:
            return
    mandati = memoria.setdefault("mandati", {})
    if mandati.get(evento.posto) == chiave:
        return
    url = file_del_webhook().read_text(encoding="utf-8").strip()
    richiesta = urllib.request.Request(
        url, data=json.dumps({"text": evento.testo}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(richiesta, timeout=TIMEOUT):
        pass
    mandati[evento.posto] = chiave
    scrivi_memoria(file, memoria)


def scrivi_memoria(file: Path, memoria: dict) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(memoria, ensure_ascii=False) + "\n", encoding="utf-8")
