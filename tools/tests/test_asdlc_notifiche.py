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


# --- Criterio 2: ogni evento ha il suo messaggio ------------------------------


def progetto_finto(tmp_path: Path, coda_md: str = "- PBI-7\n",
                   notifiche_toml: str = NOTIFICHE_ACCESE) -> tuple[Path, Path]:
    """Il checkout `ada_nlt` senza `git`, letto dal tick, e il worktree del runner:
    i passi del tick che parlano col mondo li sostituisce il test."""
    repo = tmp_path / "ada_nlt"
    (repo / "backlog").mkdir(parents=True)
    (repo / "asdlc.toml").write_text(toml_del_progetto(notifiche_toml), encoding="utf-8")
    (repo / "backlog" / "CODA.md").write_text(coda_md, encoding="utf-8")
    (repo / "backlog" / "PBI-7-la-somma.md").write_text(
        "# PBI-7: la somma\n\nrilascia: patch\n", encoding="utf-8")
    albero = tmp_path / "albero"
    albero.mkdir()
    coda.configura(coda.asdlc_config.carica(repo))
    return repo, albero


def mondo_finto(monkeypatch, *, merged=(0, "[]"), aperte=(0, "[]")):
    """`esegui()` finto: `gh pr list` rende `merged` o `aperte`, `gh run list` una CI
    verde, ogni altro comando esce `0` senza dire niente."""

    def esegui(cmd, cwd):
        if cmd[:3] == ["gh", "pr", "list"]:
            return merged if "merged" in cmd else aperte
        if cmd[:3] == ["gh", "run", "list"]:
            return 0, json.dumps([{"conclusion": "success"}])
        if cmd[0] == "gh":
            raise AssertionError(f"gh non previsto: {cmd}")
        return 0, ""

    monkeypatch.setattr(coda, "esegui", esegui)


def passi_sostituiti(monkeypatch, **sostituti):
    """I passi del tick che non sono sotto prova, sostituiti: il battito e il pin
    non fanno niente, il checkout è allineato e il pacchetto installato. Ogni
    altro passo si dà per nome."""
    passi = {"batti": lambda r: None, "pin": lambda r: [],
             "allinea": lambda r: None, "reinstalla": lambda r, w: None,
             "lancia": lambda pbi, w, **k: None}
    passi.update(sostituti)
    for nome, finto in passi.items():
        monkeypatch.setattr(coda, nome, finto)


def scenario_non_lanciato(tmp_path, monkeypatch):
    def non_parte(pbi, worktree, **k):
        raise coda.Guasto("il pre-flight si è fermato su `git fetch origin` (uscita 128): "
                          f"fatal: rete assente {tmp_path.name}")
    passi_sostituiti(monkeypatch, decidi=lambda r, w: coda.Lancia("PBI-7"), lancia=non_parte)
    mondo_finto(monkeypatch)


def scenario_pronto(tmp_path, monkeypatch):
    passi_sostituiti(monkeypatch, decidi=lambda r, w: coda.Occupato())
    mondo_finto(monkeypatch, aperte=(0, json.dumps([{
        "number": 12, "title": "una PR a mano", "headRefName": "feature/x", "files": [],
        "statusCheckRollup": [], "mergeable": "MERGEABLE"}])))


def scenario_rilascio(tmp_path, monkeypatch):
    import contextlib
    passi_sostituiti(monkeypatch, decidi=lambda r, w: coda.Occupato())
    mondo_finto(monkeypatch, merged=(0, json.dumps([{
        "title": "PBI-7: la somma", "headRefName": "pbi/pbi-7",
        "mergeCommit": {"oid": "a" * 40}, "files": [{"path": "somma.py"}]}])))
    (tmp_path / "rilascio").mkdir()
    monkeypatch.setattr(coda.asdlc_runner, "worktree_di_rilascio",
                        lambda repo, base: contextlib.nullcontext(tmp_path / "rilascio"))


def scenario_barriera(tmp_path, monkeypatch):
    # La barriera scritta in `CODA.md`, letta da `decidi()` vero.
    passi_sostituiti(monkeypatch)
    mondo_finto(monkeypatch)


def scenario_finita(tmp_path, monkeypatch):
    passi_sostituiti(monkeypatch, decidi=lambda r, w: coda.Finita())
    mondo_finto(monkeypatch)


def scenario_guasto_di_gh(tmp_path, monkeypatch):
    # `decidi()` vero, con `gh` che non risponde: una `Barriera` nata da un `Guasto`.
    passi_sostituiti(monkeypatch)
    mondo_finto(monkeypatch, merged=(1, "HTTP 502: Bad Gateway"))


def scenario_guasto_delle_pr(tmp_path, monkeypatch):
    # `Attende` con `pr is None`: `gh` muto sulla ricerca delle PR del ramo.
    passi_sostituiti(monkeypatch, decidi=lambda r, w: coda.Attende("PBI-7", None))
    mondo_finto(monkeypatch)


def scenario_non_allineato(tmp_path, monkeypatch):
    passi_sostituiti(monkeypatch, allinea=lambda r: f"il checkout {r} è su «pbi/pbi-7», non su main")
    mondo_finto(monkeypatch)


def scenario_reinstallazione(tmp_path, monkeypatch):
    passi_sostituiti(monkeypatch, reinstalla=lambda r, w: (
        "reinstallazione fallita: ERROR: No matching distribution found for asdlc"))
    mondo_finto(monkeypatch)


def scenario_pausa(tmp_path, monkeypatch):
    passi_sostituiti(monkeypatch)
    mondo_finto(monkeypatch)
    (Path.home() / "asdlc-tick.pausa").write_text(
        "2026-10-31 10:00 chiudo a mano il giro di PBI-7\n", encoding="utf-8")


def scenario_fermo_in_preverifica(tmp_path, monkeypatch):
    passi_sostituiti(monkeypatch, decidi=lambda r, w: coda.AttendeLaPreverifica("PBI-7", 3))
    mondo_finto(monkeypatch)


@pytest.mark.parametrize("scenario, coda_md, tick, attesi", [
    (scenario_non_lanciato, "- PBI-7\n", 2,
     ["⛔ ada_nlt: PBI-7 non parte — ", "git fetch origin"]),
    (scenario_pronto, "- PBI-7\n", 1,
     ["✅ ada_nlt: PR #12 da mergiare a mano — il ramo feature/x non è di un giro del runner"]),
    (scenario_rilascio, "- PBI-7\n", 1, ["🏷️ ada_nlt: v0.0.1 da PBI-7"]),
    (scenario_barriera, "- ‖ firma il contratto\n- PBI-7\n", 1,
     ["⏸️ ada_nlt: barriera — firma il contratto"]),
    (scenario_finita, "- PBI-7\n", 1, ["🏁 ada_nlt: coda finita"]),
    (scenario_guasto_di_gh, "- PBI-7\n", 3,
     ["⚠️ ada_nlt: il tick non riesce — ", "gh non risponde (uscita 1)"]),
    (scenario_guasto_delle_pr, "- PBI-7\n", 3,
     ["⚠️ ada_nlt: il tick non riesce — ", "GitHub non ha risposto"]),
    (scenario_non_allineato, "- PBI-7\n", 1,
     ["⚠️ ada_nlt: checkout non allineato — ", "è su «pbi/pbi-7», non su main"]),
    (scenario_reinstallazione, "- PBI-7\n", 1,
     ["⚠️ ada_nlt: reinstallazione fallita — ERROR: No matching distribution found"]),
    (scenario_pausa, "- PBI-7\n", 1,
     ["⏸️ ada_nlt: in pausa — 2026-10-31 10:00 chiudo a mano il giro di PBI-7"]),
    (scenario_fermo_in_preverifica, "- PBI-7\n", 1,
     ["⛔ ada_nlt: PBI-7 fermo — preverifica, 3 rilievi"]),
], ids=["non-lanciato", "pronto", "rilascio", "barriera", "finita", "guasto-gh-muto",
        "guasto-pr-senza-risposta", "non-allineato", "reinstallazione", "pausa",
        "fermo-in-preverifica"])
def test_ogni_evento_ha_il_suo_messaggio(tmp_path, monkeypatch, webhook, tick_configurato,
                                         scenario, coda_md, tick, attesi):
    """PBI-533, criterio 2 (decisione 3). La sorgente della tabella dà il testo
    atteso, col progetto e il PBI o il motivo. `non-lanciato` manda al secondo tick
    di fila sullo stesso PBI, `guasto` al terzo: la `POST` arriva solo lì."""
    repo, albero = progetto_finto(tmp_path, coda_md)
    scenario(tmp_path, monkeypatch)

    for _ in range(tick - 1):
        un_tick(repo, albero)
        assert webhook.ricevuti == [], webhook.testi()
    un_tick(repo, albero)

    assert len(webhook.ricevuti) == 1, webhook.testi()
    for atteso in attesi:
        assert atteso in webhook.testi()[0], webhook.testi()
        assert atteso in webhook.testi()[0], webhook.testi()


def test_un_evento_fuori_da_eventi_non_manda_niente(tmp_path, monkeypatch, webhook,
                                                     tick_configurato):
    """PBI-533, criterio 2 (decisione 8): `[notifiche].eventi` sceglie quali eventi
    mandare. Un progetto che chiede solo `fermo` non riceve la coda finita, mentre
    con l'elenco di default la riceve."""
    repo, albero = progetto_finto(
        tmp_path, notifiche_toml='[notifiche]\nattive = true\neventi = ["fermo"]\n')
    passi_sostituiti(monkeypatch, decidi=lambda r, w: coda.Finita())
    mondo_finto(monkeypatch)

    un_tick(repo, albero)

    assert webhook.ricevuti == [], webhook.testi()
