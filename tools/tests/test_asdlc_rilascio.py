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


# ---------------------------------------------------------------------------
# Lato progetto: il pin e la pausa (R10, R11)
# ---------------------------------------------------------------------------

A_MONTE = "Lara-srl/ada_asdlc"
INSTALLA_VECCHIO = "git+https://github.com/Lara-srl/ada_asdlc@v0.3.0"
TOML_DEL_PROGETTO = f"""\
[ambiente]
venv = ".venv"
installa = "{INSTALLA_VECCHIO}"

[junit]
comando = ["mvn", "-Dtest={{test}}"]
"""


class MondoProgetto:
    """Il checkout di un progetto con un PBI fermo che `attende:` un PBI di `asdlc`,
    un `origin` vero e un `gh` finto che racconta la PR a monte, i suoi tag e la PR del pin."""

    def __init__(self, tmp_path, stato_monte="MERGED", tag=("v0.4.0",), pin=None,
                 contiene="ahead"):
        self.origin = tmp_path / "progetto-origin.git"
        self.repo = tmp_path / "progetto"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(tmp_path, "clone", "-q", str(self.origin), str(self.repo))
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "asdlc.toml").write_text(TOML_DEL_PROGETTO)
        (self.repo / "backlog").mkdir()
        (self.repo / "backlog" / "PBI-700-il-pbi-fermo.md").write_text(
            f"# PBI-700: il PBI fermo\n\nattende: {A_MONTE}#PBI-505\n\n## Direttiva\n\nAspetta.\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "base")
        git(self.repo, "push", "-q", "origin", "main")
        self.stato_monte, self.tag, self.pin = stato_monte, list(tag), pin
        self.contiene = contiene
        self.chiamate: list[list[str]] = []

    def esegui(self, cmd, cwd):
        self.chiamate.append(list(cmd))
        if cmd[:3] == ["gh", "pr", "list"] and A_MONTE in cmd:
            return 0, json.dumps([{"number": 12, "title": "PBI-505: il runner", "headRefName":
                                   "pbi/pbi-505"}])
        if cmd[:3] == ["gh", "pr", "view"] and cmd[3] == "12":
            return 0, json.dumps({"state": self.stato_monte, "mergeCommit": {"oid": "abc"}})
        if cmd[:2] == ["gh", "api"] and cmd[2].endswith("/tags"):
            return 0, "\n".join(self.tag)
        if cmd[:2] == ["gh", "api"] and "/compare/" in cmd[2]:
            return 0, self.contiene
        if cmd[:3] == ["gh", "pr", "list"]:
            return 0, json.dumps([{"number": 40}] if self.pin else [])
        if cmd[:3] == ["gh", "pr", "view"] and cmd[3] == "40":
            return 0, json.dumps({"state": self.pin})
        if cmd[:3] == ["gh", "pr", "create"]:
            return 0, "https://github.com/x/y/pull/41"
        return ESEGUI_VERO(cmd, cwd)

    def rami_su_origin(self):
        return [r.strip() for r in git(self.origin, "branch", "--list").splitlines()
                if r.strip().lstrip("* ") != "main"]

    def comandi(self, *inizio):
        return [c for c in self.chiamate if c[:len(inizio)] == list(inizio)]


@pytest.fixture
def progetto(tmp_path, monkeypatch):
    def crea(**kwargs):
        m = MondoProgetto(tmp_path, **kwargs)
        monkeypatch.setattr(coda, "esegui", m.esegui)
        return m
    return crea


def test_un_pbi_fermo_con_attende_e_pr_a_monte_mergiata_con_tag_apre_la_pr_del_pin(progetto):
    m = progetto()

    coda.pin(m.repo)

    [ramo] = m.rami_su_origin()
    cambiati = git(m.origin, "diff", "--numstat", f"main...{ramo}").splitlines()
    assert [riga.split("\t")[2] for riga in cambiati] == ["asdlc.toml"], "solo asdlc.toml"
    assert cambiati[0].split("\t")[:2] == ["1", "1"], "una riga sola"
    nuovo = git(m.origin, "show", f"{ramo}:asdlc.toml")
    assert 'installa = "git+https://github.com/Lara-srl/ada_asdlc@v0.4.0"' in nuovo
    assert "[junit]" in nuovo, "il resto del file non si tocca"
    [crea] = m.comandi("gh", "pr", "create")
    assert crea[crea.index("--base") + 1] == "main"
    assert crea[crea.index("--head") + 1] == ramo


@pytest.mark.parametrize("situazione", [
    {"stato_monte": "OPEN"},
    {"stato_monte": "CLOSED"},
    {"tag": ()},
    {"contiene": "behind"},
], ids=["pr-aperta", "pr-chiusa-senza-merge", "nessun-tag", "il-tag-non-contiene-il-merge"])
def test_senza_pr_a_monte_mergiata_e_tag_che_la_contiene_non_si_apre_niente(progetto, situazione):
    m = progetto(**situazione)

    coda.pin(m.repo)

    assert m.rami_su_origin() == []
    assert m.comandi("gh", "pr", "create") == []
