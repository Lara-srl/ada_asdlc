"""Il rilascio a tick (`backlog/PBI-509`, `specs/solver-e-rilascio/spec.md` R5-R11).

Due metà che si provano separate: il tick di `asdlc` che mette il tag dopo il merge di
un PBI (R8, R9), e il tick del progetto che propone il pin e toglie la pausa (R10,
R11). `gh` è sostituito da un finto; nessun test usa la rete.

Il modulo si carica per nome, `asdlc.coda`: `conftest.py` mette `tools/` sul
`sys.path` (PBI-383).
"""

import importlib
import tomllib
from pathlib import Path

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"

config = importlib.import_module("asdlc.config")


def configurazione(sezione: str = ""):
    """La configurazione del progetto di prova con sopra la sezione data."""
    testo = (PROGETTO / "asdlc.toml").read_text(encoding="utf-8") + "\n" + sezione
    return config.interpreta(tomllib.loads(testo), "asdlc.toml")


def test_la_sezione_rilascio_ha_i_default_fork_e_prefisso_v():
    """Senza `[rilascio]` il remote del fork è `fork` e il tag comincia per `v`."""
    rilascio = configurazione().rilascio

    assert (rilascio.remote_fork, rilascio.prefisso_tag) == ("fork", "v")


def test_la_sezione_rilascio_si_legge_dal_toml():
    rilascio = configurazione('[rilascio]\nremote_fork = "mio"\nprefisso_tag = "rel-"\n').rilascio

    assert (rilascio.remote_fork, rilascio.prefisso_tag) == ("mio", "rel-")


# ---------------------------------------------------------------------------
# Lato `asdlc`: il tag dopo il merge (R8, R9)
# ---------------------------------------------------------------------------

import json
import subprocess

import pytest

coda = importlib.import_module("asdlc.coda")
coda.REPO = PROGETTO
coda.configura(coda.asdlc_config.carica(PROGETTO))

ESEGUI_VERO = coda.esegui


def git(cwd, *argomenti):
    return subprocess.run(["git", *argomenti], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def intestazione(rilascia: str | None) -> str:
    riga = f"rilascia: {rilascia}\n\n" if rilascia else ""
    return f"# PBI-600: un cambio al runner\n\n{riga}## Direttiva\n\nFai.\n"


class Mondo:
    """Un `origin` vero (bare), il checkout del tick e un `gh` finto.

    Il checkout sta su `main` con il tag `v0.3.0` sul commit prima del PBI mergiato.
    `gh` risponde con le PR mergiate e la CI di `main` che il test sceglie; ogni altro
    comando passa a `git` vero, e `--registra` è registrato col suo `cwd`.
    """

    def __init__(self, tmp_path, rilascia="patch", ci="success"):
        self.origin = tmp_path / "origin.git"
        self.repo = tmp_path / "checkout"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(tmp_path, "clone", "-q", str(self.origin), str(self.repo))
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "README.md").write_text("runner\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "base")
        git(self.repo, "tag", "v0.3.0")
        (self.repo / "backlog").mkdir()
        (self.repo / "backlog" / "PBI-600-un-cambio.md").write_text(intestazione(rilascia))
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "PBI-600: un cambio al runner")
        git(self.repo, "push", "-q", "origin", "main", "--tags")
        self.merge = git(self.repo, "rev-parse", "HEAD")
        self.ci = ci
        self.chiamate: list[tuple[list[str], Path]] = []

    def esegui(self, cmd, cwd):
        self.chiamate.append((list(cmd), Path(cwd)))
        if cmd[:3] == ["gh", "pr", "list"]:
            return 0, json.dumps([{"title": "PBI-600: un cambio al runner",
                                   "headRefName": "pbi/pbi-600",
                                   "mergeCommit": {"oid": self.merge}}])
        if cmd[:3] == ["gh", "run", "list"]:
            return 0, json.dumps([{"conclusion": self.ci, "headSha": self.merge}])
        if "--registra" in cmd:
            return 0, "registrato"
        return ESEGUI_VERO(cmd, cwd)

    def tag_su_origin(self):
        return sorted(git(self.origin, "tag", "--list").split())


@pytest.fixture
def mondo(tmp_path, monkeypatch):
    def crea(**kwargs):
        m = Mondo(tmp_path, **kwargs)
        monkeypatch.setattr(coda, "esegui", m.esegui)
        return m
    return crea


def test_un_pbi_con_rilascia_patch_mergiato_e_ci_verde_produce_il_tag(mondo):
    m = mondo(rilascia="patch")

    coda.rilascia(m.repo)

    assert m.tag_su_origin() == ["v0.3.0", "v0.3.1"]


def test_un_pbi_con_rilascia_minor_azzera_la_patch(mondo):
    m = mondo(rilascia="minor")

    coda.rilascia(m.repo)

    assert m.tag_su_origin() == ["v0.3.0", "v0.4.0"]


def test_senza_rilascia_non_c_e_tag(mondo):
    """Lo stesso scenario, ma il PBI non dichiara `rilascia:` (un PBI di documentazione)."""
    m = mondo(rilascia=None)

    coda.rilascia(m.repo)

    assert m.tag_su_origin() == ["v0.3.0"]


def test_con_la_ci_di_main_rossa_non_c_e_tag(mondo):
    m = mondo(rilascia="patch", ci="failure")

    coda.rilascia(m.repo)

    assert m.tag_su_origin() == ["v0.3.0"]


def test_se_un_tag_contiene_gia_il_merge_del_pbi_non_ne_mette_un_altro(mondo):
    """Il tick rigira ogni dieci minuti: il PBI già rilasciato non deve dare v0.3.2."""
    m = mondo(rilascia="patch")
    git(m.repo, "tag", "v0.3.1")
    git(m.repo, "push", "-q", "origin", "v0.3.1")

    coda.rilascia(m.repo)

    assert m.tag_su_origin() == ["v0.3.0", "v0.3.1"]


def test_il_rilascio_gira_in_un_worktree_separato_e_il_checkout_resta_pulito(mondo):
    m = mondo(rilascia="patch")
    prima = git(m.repo, "status", "--porcelain")

    coda.rilascia(m.repo)

    lavori = [(cmd, cwd) for cmd, cwd in m.chiamate
              if "--registra" in cmd or cmd[:2] == ["git", "tag"] and cmd[2:3] == ["v0.3.1"]]
    assert len(lavori) == 2, "il giro registra e mette il tag"
    cartelle = {cwd for _, cwd in lavori}
    assert len(cartelle) == 1 and m.repo.resolve() not in {c.resolve() for c in cartelle}, (
        "--registra e il tag girano nello stesso worktree, che non è il checkout")
    assert not cartelle.pop().exists(), "il worktree è tolto a fine passo"
    assert git(m.repo, "status", "--porcelain") == prima == ""
    assert git(m.repo, "worktree", "list").count("\n") == 0, "resta solo il checkout"
    assert m.tag_su_origin() == ["v0.3.0", "v0.3.1"]
