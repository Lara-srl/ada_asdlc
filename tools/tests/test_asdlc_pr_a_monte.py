"""La PR a monte del Solver (`backlog/PBI-512`, `specs/solver-e-rilascio/spec.md` R5 e R6).

Quando il Solver segnala un limite del runner, il sistema apre il PBI a monte: un ramo su
un fork di `asdlc` e una PR da lì, mai una scrittura su `main`. `gh` e `git` sono
sostituiti da finti; nessun test usa la rete.
"""

import dataclasses
import importlib
import json
import subprocess
import tomllib
from pathlib import Path

import pytest

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"

config = importlib.import_module("asdlc.config")
esito = importlib.import_module("asdlc.esito")
runner = importlib.import_module("asdlc.runner")
runner.REPO = PROGETTO
runner.configura(runner.asdlc_config.carica(PROGETTO))

TESTO_DEL_PBI = "# PBI-900: il limite\n\n## Direttiva\n\nCorreggi.\n\n**Scope**\n\n- `tools/asdlc/x.py`\n"


def configurazione(sezione: str = ""):
    """La configurazione del progetto di prova con sopra la sezione data."""
    testo = (PROGETTO / "asdlc.toml").read_text(encoding="utf-8") + "\n" + sezione
    return config.interpreta(tomllib.loads(testo), "asdlc.toml")


def test_senza_la_chiave_clone_la_sezione_rilascio_non_ha_un_clone():
    """Il clone di `asdlc` non si deduce da altro: senza chiave è `None`."""
    assert configurazione().rilascio.clone is None


def test_la_chiave_clone_della_sezione_rilascio_si_legge_dal_toml():
    rilascio = configurazione('[rilascio]\nclone = "/home/x/asdlc"\n').rilascio

    assert rilascio.clone == "/home/x/asdlc"


def albero_con_un_commit(tmp_path, monkeypatch):
    """Un repository git con un commit e la cartella d'esito: l'albero del giro."""
    monkeypatch.chdir(tmp_path)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["init", "-q"], check=True)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(git + ["add", "a.txt"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "uno"], check=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True,
                         text=True).stdout.strip()
    cartella = tmp_path / "esito"
    cartella.mkdir()
    return sha, cartella


def limite(sha, **altri):
    return {"causa": "runner-x", "comando": "pytest -q", "output": "0 test", "commit": sha,
            "pbi": TESTO_DEL_PBI, **altri}


def test_lo_strumento_del_limite_ha_il_campo_pbi_obbligatorio():
    """Decisione 1: il testo del PBI a monte lo scrive il Solver, in un campo suo."""
    schema = next(s for s in esito.strumenti("solver")
                  if s["name"] == "segnala_limite_runner")["inputSchema"]

    assert "pbi" in schema["properties"]
    assert "pbi" in schema["required"]


def test_senza_clone_la_pr_non_si_apre_e_lo_strumento_rende_un_errore(tmp_path, monkeypatch):
    """Decisione 3: senza `[rilascio].clone` (la variabile `ASDLC_CLONE` non c’è) il Solver
    riceve l'errore, nomina la chiave, e nessun esito si scrive."""
    sha, cartella = albero_con_un_commit(tmp_path, monkeypatch)
    monkeypatch.setenv("ASDLC_CAUSE", "runner-x")
    monkeypatch.delenv("ASDLC_CLONE", raising=False)

    risposta = esito.chiama("segnala_limite_runner", limite(sha), "solver",
                            str(cartella / "a.json"))

    assert risposta["isError"]
    assert "[rilascio].clone" in risposta["content"][0]["text"]
    assert not (cartella / "a.json").exists()


def test_con_il_clone_l_esito_porta_il_testo_del_pbi_e_senza_pbi_si_rifiuta(tmp_path, monkeypatch):
    sha, cartella = albero_con_un_commit(tmp_path, monkeypatch)
    monkeypatch.setenv("ASDLC_CAUSE", "runner-x")
    monkeypatch.setenv("ASDLC_CLONE", str(tmp_path))

    senza = esito.chiama("segnala_limite_runner", limite(sha, pbi="  "), "solver",
                         str(cartella / "a.json"))
    con = esito.chiama("segnala_limite_runner", limite(sha), "solver", str(cartella / "b.json"))

    assert senza["isError"] and not (cartella / "a.json").exists()
    assert not con["isError"], con
    assert json.loads((cartella / "b.json").read_text(encoding="utf-8"))["pbi"] == TESTO_DEL_PBI


def test_il_server_del_solver_riceve_il_clone_in_asdlc_clone(monkeypatch, tmp_path):
    """Il clone viaggia da `[rilascio].clone` alla variabile `ASDLC_CLONE`; senza chiave
    la variabile non c’è."""
    monkeypatch.setattr(runner, "PACCHETTO", tmp_path)
    con = dataclasses.replace(runner.CFG, rilascio=config.Rilascio(clone="/home/x/asdlc"))
    monkeypatch.setattr(runner, "CFG", con)
    percorso = runner.config_del_server("solver", tmp_path / "esito.json")
    ambiente = json.loads(percorso.read_text(encoding="utf-8"))["mcpServers"]["asdlc"]["env"]
    assert ambiente["ASDLC_CLONE"] == "/home/x/asdlc"

    monkeypatch.setattr(runner, "CFG", dataclasses.replace(con, rilascio=config.Rilascio()))
    percorso = runner.config_del_server("solver", tmp_path / "esito2.json")
    ambiente = json.loads(percorso.read_text(encoding="utf-8"))["mcpServers"]["asdlc"]["env"]
    assert "ASDLC_CLONE" not in ambiente


# ---------------------------------------------------------------------------
# La PR a monte (R5): ramo sul fork, base `main`, numero successivo, riga di coda
# ---------------------------------------------------------------------------

ESEGUI_VERO = runner.esegui
ASDLC = "Lara-srl/ada_asdlc"


def git(cwd, *argomenti):
    return subprocess.run(["git", *argomenti], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


class MondoAMonte:
    """Un clone di `asdlc` con un `origin` e un `fork` veri (due repository nudi in locale)
    e un `gh` finto: racconta il nome del repository, le PR aperte e rende un URL alla
    creazione. Ogni comando emesso resta in `.chiamate`."""

    def __init__(self, tmp_path, pr_aperte=(), backlog=("PBI-511-uno.md", "PBI-512-due.md")):
        self.origin, self.fork = tmp_path / "origin.git", tmp_path / "fork.git"
        self.clone = tmp_path / "asdlc"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.fork))
        git(tmp_path, "clone", "-q", str(self.origin), str(self.clone))
        git(self.clone, "config", "user.email", "t@t")
        git(self.clone, "config", "user.name", "t")
        (self.clone / "backlog").mkdir()
        for nome in backlog:
            (self.clone / "backlog" / nome).write_text(f"# {nome}\n", encoding="utf-8")
        (self.clone / "backlog" / "CODA.md").write_text(
            "# La coda\n\n- PBI-511\n- PBI-512\n\nProsa.\n", encoding="utf-8")
        git(self.clone, "add", ".")
        git(self.clone, "commit", "-qm", "base")
        git(self.clone, "push", "-q", "origin", "main")
        git(self.clone, "remote", "add", "fork", str(self.fork))
        git(self.clone, "push", "-q", "fork", "main")
        self.pr_aperte, self.chiamate = list(pr_aperte), []

    def esegui(self, cmd, cwd, timeout=7200, **k):
        self.chiamate.append(list(cmd))
        if cmd[:3] == ["gh", "repo", "view"]:
            return 0, ASDLC
        if cmd[:3] == ["gh", "pr", "list"]:
            return 0, json.dumps(self.pr_aperte)
        if cmd[:3] == ["gh", "pr", "create"]:
            return 0, f"https://github.com/{ASDLC}/pull/77"
        return ESEGUI_VERO(cmd, cwd, timeout, **k)

    def comandi(self, *inizio):
        return [c for c in self.chiamate if c[:len(inizio)] == list(inizio)]

    def rami(self, repo):
        return sorted(r.strip().lstrip("* ") for r in git(repo, "branch", "--list").splitlines())


@pytest.fixture
def a_monte(tmp_path, monkeypatch):
    def crea(**kwargs):
        mondo = MondoAMonte(tmp_path, **kwargs)
        monkeypatch.setattr(runner, "esegui", mondo.esegui)
        monkeypatch.setattr(runner, "CFG", dataclasses.replace(
            runner.CFG, rilascio=config.Rilascio(clone=str(mondo.clone))))
        return mondo
    return crea


def dichiarato_del_limite(**altri):
    return {"esito": "limite-del-runner", "causa": "runner-x", "comando": "pytest -q",
            "output": "0 test", "commit": "abc1234", "pbi": TESTO_DEL_PBI, **altri}


def test_il_limite_apre_un_ramo_sul_fork_e_una_pr_verso_main_col_pbi_successivo(a_monte):
    """R5 (criterio 1): il ramo atterra sul fork e non su `origin`; la PR ha `main` per base;
    il PBI ha il numero successivo a quelli di `backlog/` e la riga entra in `backlog/CODA.md`."""
    mondo = a_monte()

    pbi, url = runner.apri_pr_a_monte(dichiarato_del_limite())

    assert (pbi, url) == ("PBI-513", f"https://github.com/{ASDLC}/pull/77")
    assert mondo.rami(mondo.fork) == ["main", "pbi/pbi-513"]
    assert mondo.rami(mondo.origin) == ["main"], "su origin non si scrive niente"
    file = next(f for f in git(mondo.fork, "ls-tree", "-r", "--name-only", "pbi/pbi-513").split()
                if f.startswith("backlog/PBI-513"))
    testo = git(mondo.fork, "show", f"pbi/pbi-513:{file}")
    assert testo.startswith("# PBI-513: il limite\n") and "Correggi." in testo
    assert "- PBI-513" in git(mondo.fork, "show", "pbi/pbi-513:backlog/CODA.md").splitlines()
    (creazione,) = mondo.comandi("gh", "pr", "create")
    assert creazione[creazione.index("--base") + 1] == "main"
    assert creazione[creazione.index("--head") + 1].endswith("pbi/pbi-513")
    assert "PBI-513" in creazione[creazione.index("--title") + 1]
    assert not mondo.comandi("gh", "pr", "merge")
