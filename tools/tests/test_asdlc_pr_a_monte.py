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
coda = importlib.import_module("asdlc.coda")
runner.REPO = PROGETTO
runner.configura(runner.asdlc_config.carica(PROGETTO))
coda.REPO = PROGETTO
coda.configura(coda.asdlc_config.carica(PROGETTO))

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
        if cmd[:3] == ["gh", "pr", "view"]:
            pr = next(p for p in self.pr_aperte if p["url"] == cmd[3])
            return 0, json.dumps({"title": pr["title"], "headRefName": pr["headRefName"]})
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


def test_una_causa_gia_a_monte_nel_backlog_non_apre_un_secondo_pbi(a_monte):
    """R6 (criterio 3): se `backlog/` di `asdlc` ha già un PBI con la stessa causa, non nasce
    né un ramo né una PR, e il risultato cita quel PBI."""
    mondo = a_monte()
    (mondo.clone / "backlog" / "PBI-511-uno.md").write_text(
        "# PBI-511: uno\n\n**Causa:** runner-x\n", encoding="utf-8")
    git(mondo.clone, "commit", "-qam", "il PBI 511 ha la causa")
    git(mondo.clone, "push", "-q", "origin", "main")

    pbi, url = runner.apri_pr_a_monte(dichiarato_del_limite())

    assert pbi == "PBI-511"
    assert not mondo.comandi("gh", "pr", "create")
    assert mondo.rami(mondo.fork) == ["main"], "sul fork non nasce nessun ramo"


def test_una_causa_gia_in_una_pr_aperta_non_apre_un_secondo_pbi(a_monte):
    """R6 (criterio 3): se una PR aperta di `asdlc` cita la stessa causa, non nasce né un
    ramo né una PR, e il risultato cita quella PR con il suo URL."""
    esistente = f"https://github.com/{ASDLC}/pull/40"
    mondo = a_monte(pr_aperte=[{"number": 40, "title": "PBI-600: altro", "url": esistente,
                                "body": "**Causa:** runner-x\n", "headRefName": "pbi/pbi-600"}])

    pbi, url = runner.apri_pr_a_monte(dichiarato_del_limite())

    assert (pbi, url) == ("PR #40", esistente)
    assert not mondo.comandi("gh", "pr", "create")
    assert mondo.rami(mondo.fork) == ["main"], "sul fork non nasce nessun ramo"


# ---------------------------------------------------------------------------
# Dopo la PR il progetto è in attesa: la riga `attende:` e la pausa (criterio 4)
# ---------------------------------------------------------------------------


def smista_un_limite(tmp_path, monkeypatch, mondo, dichiarato, commit_rifiutato=False):
    """`smista_il_blocco` su un PBI fermo, con un Solver che dichiara `dichiarato`.
    Rende il file del PBI fermo; `HOME` è in `tmp_path`, dove vive la pausa. Con
    `commit_rifiutato` un hook `pre-commit` fa fallire ogni commit dopo il primo."""
    (tmp_path / "log").mkdir()
    (tmp_path / "backlog").mkdir()
    pbi_fermo = tmp_path / "backlog" / "PBI-400-fermo.md"
    pbi_fermo.write_text("# PBI-400: fermo\n", encoding="utf-8")
    # Il worktree del giro: un repository vero sul ramo del PBI fermo.
    git(tmp_path, "init", "-q", "-b", "pbi/pbi-400")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "add", "backlog")
    git(tmp_path, "commit", "-qm", "il PBI fermo")
    if commit_rifiutato:
        hook = tmp_path / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path / "casa"))
    (tmp_path / "casa").mkdir()
    monkeypatch.setattr(runner, "REPO", tmp_path)
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path / "log")
    monkeypatch.setattr(runner, "invoca_agente", lambda *a, **k: runner.Invocazione(
        0, "", dichiarato, {"ruolo": "solver"}))
    avvisi = []
    runner.smista_il_blocco(runner.Esito(pbi="PBI-400", stato="fermato"), pbi_fermo, "rosso",
                            "x", avvisi.append)
    return pbi_fermo


def test_dopo_la_pr_il_pbi_fermo_attende_il_pbi_a_monte_e_la_pausa_esiste(a_monte, tmp_path,
                                                                           monkeypatch):
    """Decisione 4 (criterio 4): il PBI fermo riceve `attende: <repo>#<PBI>` del PBI appena
    aperto e il tick va in pausa."""
    mondo = a_monte()

    pbi_fermo = smista_un_limite(tmp_path, monkeypatch, mondo, dichiarato_del_limite())

    assert f"attende: {ASDLC}#PBI-513" in pbi_fermo.read_text(encoding="utf-8").splitlines()
    assert (tmp_path / "casa" / "asdlc-tick.pausa").exists()


def test_con_una_causa_gia_in_una_pr_il_pbi_fermo_attende_il_pbi_di_quella_pr(a_monte, tmp_path,
                                                                              monkeypatch):
    """Criterio 4, causa già a monte: la riga `attende:` nomina il PBI della PR esistente
    (quello del titolo), e la pausa esiste lo stesso; nessuna PR nuova."""
    esistente = f"https://github.com/{ASDLC}/pull/40"
    mondo = a_monte(pr_aperte=[{"number": 40, "title": "PBI-600: altro", "url": esistente,
                                "body": "**Causa:** runner-x\n", "headRefName": "pbi/pbi-600"}])

    pbi_fermo = smista_un_limite(tmp_path, monkeypatch, mondo, dichiarato_del_limite())

    assert f"attende: {ASDLC}#PBI-600" in pbi_fermo.read_text(encoding="utf-8").splitlines()
    assert (tmp_path / "casa" / "asdlc-tick.pausa").exists()
    assert not mondo.comandi("gh", "pr", "create")


def test_la_riga_attende_e_in_un_commit_del_ramo_e_il_worktree_resta_pulito(a_monte, tmp_path,
                                                                           monkeypatch):
    """Giro 3, decisione (a): la riga non resta come modifica nel worktree del runner, ma
    sta in un commit del ramo del PBI fermo."""
    mondo = a_monte()

    smista_un_limite(tmp_path, monkeypatch, mondo, dichiarato_del_limite())

    assert git(tmp_path, "status", "--porcelain", "--", "backlog") == ""
    nel_commit = git(tmp_path, "show", "HEAD:backlog/PBI-400-fermo.md").splitlines()
    assert f"attende: {ASDLC}#PBI-513" in nel_commit


def test_se_il_commit_fallisce_non_resta_la_riga_ne_il_worktree_sporco_ne_la_pausa(
        a_monte, tmp_path, monkeypatch):
    """Giro 3, rilievo 1: un passo che fallisce non scrive né la riga né la pausa (spec,
    «Dopo la PR»); il worktree resta pulito."""
    mondo = a_monte()

    with pytest.raises(RuntimeError):  # il chiamante di `smista_il_blocco` ne fa un avviso
        smista_un_limite(tmp_path, monkeypatch, mondo, dichiarato_del_limite(),
                         commit_rifiutato=True)

    pbi_fermo = tmp_path / "backlog" / "PBI-400-fermo.md"
    assert "attende:" not in pbi_fermo.read_text(encoding="utf-8")
    assert git(tmp_path, "status", "--porcelain") == ""
    assert not (tmp_path / "casa" / "asdlc-tick.pausa").exists()


def test_la_riga_scritta_dal_runner_e_quella_che_attese_legge_dal_ramo_su_origin(
        a_monte, tmp_path, monkeypatch):
    """La catena intera: il runner committa la riga, il ramo arriva su `origin` e il checkout
    del progetto, su `main` e senza la riga, la legge con `coda.attese()`."""
    mondo = a_monte()
    origin = tmp_path / "progetto-origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    smista_un_limite(tmp_path, monkeypatch, mondo, dichiarato_del_limite())
    git(tmp_path, "remote", "add", "origin", str(origin))
    git(tmp_path, "push", "-q", "origin", "HEAD:refs/heads/pbi/pbi-400")
    tick = tmp_path / "tick"
    git(tmp_path, "clone", "-q", str(origin), str(tick))
    git(tick, "fetch", "-q", "origin")

    assert coda.attese(tick) == [("PBI-400-fermo.md", ASDLC, "PBI-513")]


def test_il_prompt_del_solver_spiega_il_campo_pbi_di_segnala_limite_runner():
    """Decisione 1: il Solver scrive il testo del PBI a monte, e il prompt gli dice come."""
    voce = next(r for r in runner.prompt_del_pacchetto("solver").split("\n\n")
                if "`segnala_limite_runner`" in r)

    assert "`pbi`" in voce
    assert "Scope" in voce and "Verifica" in voce
