"""Le notifiche del tick su Slack, con un Incoming Webhook (`backlog/PBI-533`).

Il tick manda un messaggio quando la sua decisione **cambia** verso uno stato che
chiede una persona, o che una persona vuole sapere. Qui nessuna rete: il webhook
è un server HTTP finto su `127.0.0.1`, e il suo indirizzo sta nel file
`~/.config/asdlc/slack-webhook` di una `HOME` in `tmp_path`.

I test lavorano su un repository temporaneo in `tmp_path`, mai sul progetto di
prova di `tools/tests/dati/`: `<registro>/notifiche.json` non sporca l'albero.
"""

import importlib
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

coda = importlib.import_module("asdlc.coda")
notifiche = importlib.import_module("asdlc.notifiche")
# L'import non legge `asdlc.toml` (PBI-382): la configurazione di partenza è quella
# del progetto di prova, come in `test_asdlc_coda.py`; ogni test la cambia con
# quella del suo repository temporaneo, e `tick_configurato` la rimette.
PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"
coda.REPO = PROGETTO
coda.configura(coda.asdlc_config.carica(PROGETTO))


# --- Il webhook finto ---------------------------------------------------------


class WebhookFinto:
    """Un Incoming Webhook su `127.0.0.1`: tiene il JSON di ogni `POST` e risponde
    `codice` (Slack risponde `200` con `ok`), dopo `ritardo` secondi."""

    def __init__(self):
        self.ricevuti: list[dict] = []
        self.codice = 200
        self.ritardo = 0.0
        finto = self

        class Gestore(BaseHTTPRequestHandler):
            def do_POST(self):
                lunghezza = int(self.headers.get("Content-Length", 0))
                finto.ricevuti.append(json.loads(self.rfile.read(lunghezza)))
                if finto.ritardo:
                    threading.Event().wait(finto.ritardo)
                try:
                    self.send_response(finto.codice)
                    self.end_headers()
                    self.wfile.write(b"ok")
                except OSError:
                    pass

            def log_message(self, *argomenti):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Gestore)
        self.server.daemon_threads = True
        self.url = (f"http://127.0.0.1:{self.server.server_address[1]}"
                    "/services/T000/B000/segreto-del-webhook")
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def testi(self) -> list[str]:
        return [messaggio["text"] for messaggio in self.ricevuti]

    def chiudi(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def webhook(tmp_path, monkeypatch):
    """Il server finto, con la `HOME` in `tmp_path` e il file del webhook che porta
    il suo indirizzo, una riga sola e permessi `600` (decisione 4)."""
    casa = tmp_path / "casa"
    monkeypatch.setenv("HOME", str(casa))
    finto = WebhookFinto()
    file = casa / ".config" / "asdlc" / "slack-webhook"
    file.parent.mkdir(parents=True)
    file.write_text(finto.url + "\n", encoding="utf-8")
    file.chmod(0o600)
    yield finto
    finto.chiudi()


# --- Il progetto temporaneo ---------------------------------------------------


NOTIFICHE_ACCESE = '[notifiche]\nattive = true\n'


def toml_del_progetto(notifiche_toml: str = NOTIFICHE_ACCESE) -> str:
    """Un `asdlc.toml` minimo per il tick, con la sezione `[notifiche]` data."""
    return (
        '[git]\nbase = "origin/main"\nprefisso_ramo = "pbi/pbi-"\n\n'
        '[backlog]\ncartella = "backlog"\ncoda = "backlog/CODA.md"\nid = "PBI-{n}"\n'
        'file = "PBI-{n}-{slug}.md"\n\n'
        '[registro]\ncartella = "runs"\ntempi = "tempi.csv"\n\n'
        '[ambiente]\nvenv = ".venv"\npacchetto = ".venv-asdlc"\ninstalla = "./tools"\n'
        'prestiti = []\n\n'
        '[worktree]\npercorso = "../albero"\n\n'
        '[soglie]\ntentativi = 3\nigiene = 3\nrevisioni = 4\n\n'
        '[gate_del_rosso]\nattivo = true\n\n'
        '[[gate]]\nnome = "test"\ncomando = ["python3", "-m", "pytest", "-q"]\ncwd = "."\n\n'
        + notifiche_toml
    )


def git(cartella: Path, *argomenti: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=prova", "-c", "user.email=prova@example.com",
         "-c", "init.defaultBranch=main", *argomenti],
        cwd=cartella, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def tick_configurato(monkeypatch):
    """Rimette la configurazione del tick di prima, alla fine del test: i test
    del tick in `test_asdlc_coda.py` la danno per letta dal progetto di prova."""
    di_prima = coda.CFG
    for nome in ("allinea", "reinstalla", "indietro"):
        monkeypatch.setattr(coda, nome, lambda *a, **k: None)
    monkeypatch.setattr(coda, "mancanze_dell_ambiente", lambda worktree: [])
    yield
    coda.configura(di_prima)


def progetto_con_un_ramo(tmp_path: Path, pbi_numero: str = "7",
                         notifiche_toml: str = NOTIFICHE_ACCESE) -> Path:
    """Il checkout `ada_nlt` di un progetto con un `origin` locale, che ha `main` e
    il ramo del PBI senza merge: la coda lo dà in attesa. Rende il checkout, già
    letto dal tick."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(origin))
    repo = tmp_path / "ada_nlt"
    repo.mkdir()
    git(repo, "init")
    (repo / "asdlc.toml").write_text(toml_del_progetto(notifiche_toml), encoding="utf-8")
    (repo / "backlog").mkdir()
    (repo / "backlog" / "CODA.md").write_text(f"- PBI-{pbi_numero}\n", encoding="utf-8")
    (repo / "backlog" / f"PBI-{pbi_numero}-la-somma.md").write_text(
        f"# PBI-{pbi_numero}: la somma\n", encoding="utf-8")
    (repo / ".gitignore").write_text("runs/\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "il progetto")
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "switch", "-q", "-c", f"pbi/pbi-{pbi_numero}")
    (repo / "somma.py").write_text("# la somma\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "la somma")
    git(repo, "push", "-q", "origin", f"pbi/pbi-{pbi_numero}")
    git(repo, "switch", "-q", "main")
    git(repo, "fetch", "-q", "origin")
    coda.configura(coda.asdlc_config.carica(repo))
    return repo


def albero_col_rapporto(tmp_path: Path, pbi: str, stato: str = "fermato",
                        motivo: str = "builder-fermato",
                        domanda: str = "Il totale è lordo o netto?") -> Path:
    """Il worktree del runner, col rapporto del giro di `pbi` chiuso `stato`."""
    albero = tmp_path / "albero"
    (albero / "runs").mkdir(parents=True)
    (albero / "runs" / "20261030-101500.json").write_text(json.dumps({
        "run": "20261030-101500", "stato": "finito",
        "esiti": [{"pbi": pbi, "stato": stato, "motivo": motivo, "domanda": domanda,
                   "ramo": f"pbi/pbi-{pbi.removeprefix('PBI-')}"}],
    }), encoding="utf-8")
    return albero


def gh_senza_pr(monkeypatch):
    """`gh` finto, senza PR né aperte né mergiate; `git` resta quello vero, sul
    repository temporaneo e sul suo `origin` locale."""
    vero = coda.esegui

    def esegui(cmd, cwd):
        if cmd[:3] == ["gh", "pr", "list"]:
            return 0, "[]"
        if cmd[0] == "gh":
            raise AssertionError(f"gh non previsto: {cmd}")
        return vero(cmd, cwd)

    monkeypatch.setattr(coda, "esegui", esegui)


def un_tick(repo: Path, albero: Path) -> int:
    return coda.smista(["--repo", str(repo), "--worktree", str(albero)])


# --- Criterio 1: un fermo manda un messaggio, uno solo ------------------------


def test_un_fermo_manda_un_messaggio_uno_solo(tmp_path, monkeypatch, webhook, tick_configurato):
    """PBI-533, criterio 1. Il ramo del PBI su `origin`, nessuna PR e un rapporto
    `fermato`: il tick decide `Attende` senza PR, ed è un fermo. Il primo tick fa
    una `POST` col progetto, il PBI e il motivo; il secondo, con la stessa
    situazione, non ne fa: un messaggio per cambio, non uno ogni dieci minuti."""
    repo = progetto_con_un_ramo(tmp_path)
    albero = albero_col_rapporto(tmp_path, "PBI-7")
    gh_senza_pr(monkeypatch)

    assert un_tick(repo, albero) == 0

    assert len(webhook.ricevuti) == 1, webhook.ricevuti
    testo = webhook.testi()[0]
    assert "ada_nlt" in testo and "PBI-7" in testo, testo
    assert "builder-fermato" in testo, testo
    assert "Il totale è lordo o netto?" in testo, testo

    assert un_tick(repo, albero) == 0

    assert len(webhook.ricevuti) == 1, webhook.testi()
