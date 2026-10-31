"""Le notifiche del tick su Slack, con un Incoming Webhook (`backlog/PBI-533`).

Un fermo si scopriva guardando: `runs/coda.log` di un progetto, una PR, un
`attende` che si ripete. Il 26/10 il tick di `ada_asdlc` ha scritto 84 volte lo
stesso `non lanciato` in 14 ore, e nessuno lo ha saputo. Qui il tick manda un
messaggio su Slack quando la sua decisione **cambia** verso uno stato che chiede
una persona: un messaggio per cambio, non uno ogni dieci minuti.

L'evento si ricava dal tipo della decisione del tick e dall'ultimo esito del PBI,
in codice, mai dal testo di un modello (`ADR-0027`). Il webhook è un segreto: il
suo indirizzo sta in `~/.config/asdlc/slack-webhook`, fuori dai repository, e non
esce mai dal processo (decisione 5).
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Il tetto di una `POST` al webhook, in secondi (decisione 6): i test lo abbassano.
TIMEOUT = 10


@dataclass(frozen=True)
class Evento:
    """Un messaggio da mandare. `tipo`, `pbi` e `motivo` sono la chiave con cui il
    tick riconosce lo stesso evento del tick prima (decisione 2); `testo` è ciò
    che arriva su Slack, nel campo `text` del JSON (decisione 7)."""

    tipo: str
    pbi: str
    motivo: str
    testo: str


def file_del_webhook() -> Path:
    """`~/.config/asdlc/slack-webhook`, calcolato quando serve e non all'import, come
    `file_di_pausa()` del tick: i test spostano `HOME`. Non sta in `asdlc.toml`, che
    non porta percorsi di macchina, e lo leggono tutti i progetti della macchina
    (decisione 4)."""
    return Path.home() / ".config" / "asdlc" / "slack-webhook"


def file_della_memoria(repo: Path, cfg) -> Path:
    """`<registro>/notifiche.json` del checkout `repo`: l'ultimo evento mandato
    (decisione 2). La cartella del registro è ignorata da git."""
    return repo / cfg.registro.cartella / "notifiche.json"


def della_decisione(decisione, progetto: str, esito: dict | None) -> Evento | None:
    """L'evento della decisione del tick, o `None` se non è un evento.

    `esito` è l'ultimo esito del PBI della decisione (`ultimo_esito()` del tick),
    o `None`. Il tipo della decisione si riconosce dal nome della classe e non con
    `isinstance`: il tick importa questo modulo, e un import all'indietro di
    `asdlc.coda` darebbe un'altra copia delle classi a un tick lanciato per percorso.
    """
    if type(decisione).__name__ == "Attende" and decisione.pr == ():
        motivo = (f"{esito.get('stato')} ({esito.get('motivo')})" if esito is not None
                  else "nessun rapporto del giro")
        domanda = (esito or {}).get("domanda")
        testo = f"⛔ {progetto}: {decisione.pbi} fermo — {motivo}"
        return Evento("fermo", decisione.pbi, motivo,
                      testo + (f" — domanda: {domanda}" if domanda else ""))
    return None


def leggi_memoria(file: Path) -> dict:
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def manda(repo: Path, cfg, evento: Evento | None) -> None:
    """Manda `evento` al webhook, se le notifiche sono accese e non è lo stesso
    evento dell'ultima volta; poi lo scrive nella memoria del checkout."""
    if evento is None or not cfg.notifiche.attive:
        return
    file = file_della_memoria(repo, cfg)
    memoria = leggi_memoria(file)
    chiave = [evento.tipo, evento.pbi, evento.motivo]
    if memoria.get("ultimo") == chiave:
        return
    url = file_del_webhook().read_text(encoding="utf-8").strip()
    richiesta = urllib.request.Request(
        url, data=json.dumps({"text": evento.testo}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(richiesta, timeout=TIMEOUT):
        pass
    memoria["ultimo"] = chiave
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(memoria, ensure_ascii=False) + "\n", encoding="utf-8")
