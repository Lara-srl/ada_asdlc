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

    def __init__(self, tmp_path, rilascia="patch", ci="success", files=None):
        self.files = files
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
            pr = {"title": "PBI-600: un cambio al runner",
                  "headRefName": "pbi/pbi-600",
                  "mergeCommit": {"oid": self.merge}}
            if self.files is not None:
                pr["files"] = [{"path": p} for p in self.files]
            # Come `gh`, rende solo i campi che `--json` chiede.
            chiesti = cmd[cmd.index("--json") + 1].split(",") if "--json" in cmd else list(pr)
            return 0, json.dumps([{k: v for k, v in pr.items() if k in chiesti}])
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


def test_una_pr_che_nomina_il_pbi_e_tocca_solo_backlog_non_rilascia(mondo):
    m = mondo(rilascia="minor", files=["backlog/PBI-600-un-cambio.md", "backlog/CODA.md"])

    righe = coda.rilascia(m.repo)

    assert righe == []
    assert m.tag_su_origin() == ["v0.3.0"]
    assert not any(c[:2] == ["git", "tag"] and c[2] != "--contains" and c[2] != "--list"
                   for c, _ in m.chiamate)


def test_una_pr_che_nomina_il_pbi_e_tocca_codice_rilascia_come_prima(mondo):
    m = mondo(rilascia="minor", files=["backlog/PBI-600-un-cambio.md", "tools/asdlc/x.py"])

    righe = coda.rilascia(m.repo)

    assert righe == ["rilascio: PBI-600 → v0.4.0"]
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
                 contiene="ahead", mergiato=False):
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
        self.contiene, self.mergiato = contiene, mergiato
        # Il giro fermo del PBI: un ramo su origin, e nessuna PR del PBI in main.
        git(self.repo, "push", "-q", "origin", "main:refs/heads/pbi/pbi-700")
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
        if cmd[:3] == ["gh", "pr", "list"] and "--state" in cmd and "merged" in cmd:
            return 0, json.dumps([{"title": "PBI-700: il pbi fermo", "headRefName":
                                   "pbi/pbi-700", "files": [{"path": "src/a.py"}]}]
                                 if self.mergiato else [])
        if cmd[:3] == ["gh", "pr", "list"]:
            return 0, json.dumps([{"number": 40}] if self.pin else [])
        if cmd[:3] == ["gh", "pr", "view"] and cmd[3] == "40":
            return 0, json.dumps({"state": self.pin})
        if cmd[:3] == ["gh", "pr", "create"]:
            return 0, "https://github.com/x/y/pull/41"
        return ESEGUI_VERO(cmd, cwd)

    def rami_su_origin(self):
        return [r.strip() for r in git(self.origin, "branch", "--list").splitlines()
                if r.strip().lstrip("* ") not in ("main", "pbi/pbi-700")]

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


@pytest.fixture
def pausa_del_progetto(tmp_path, monkeypatch):
    """`HOME` in una cartella temporanea con la pausa del tick già messa (PBI-385)."""
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    file = casa / "asdlc-tick.pausa"
    file.write_text("2026-10-16 10:00 in attesa di Lara-srl/ada_asdlc#PBI-505\n")
    return file


def test_la_pausa_si_toglie_a_pr_del_pin_mergiata_verificata_con_gh_pr_view(
        progetto, pausa_del_progetto):
    m = progetto(pin="MERGED")

    coda.pin(m.repo)

    assert not pausa_del_progetto.exists()
    assert m.comandi("gh", "pr", "view", "40"), "lo stato si chiede a gh pr view"
    assert m.comandi("gh", "pr", "create") == [], "la PR del pin c'è già: non se ne apre un'altra"


@pytest.mark.parametrize("stato", ["OPEN", "CLOSED"])
def test_con_la_pr_del_pin_aperta_o_chiusa_senza_merge_la_pausa_resta(
        progetto, pausa_del_progetto, stato):
    m = progetto(pin=stato)

    coda.pin(m.repo)

    assert pausa_del_progetto.exists()
    assert m.comandi("gh", "pr", "create") == []


def test_un_pbi_con_attende_gia_in_main_non_apre_niente_e_non_tocca_la_pausa(
        progetto, pausa_del_progetto):
    """Il file del PBI resta in `backlog/` per sempre, con la sua riga `attende:`: il tick
    guarda solo i PBI fermi, cioè col ramo su origin e senza merge (R10)."""
    m = progetto(pin="MERGED", mergiato=True)

    coda.pin(m.repo)

    assert pausa_del_progetto.exists()
    assert m.rami_su_origin() == []
    assert m.comandi("gh", "pr", "create") == []


def test_nessun_gh_pr_merge_esce_da_rilascia_ne_da_pin(mondo, progetto):
    """R10-R11: il merge è sempre di Francesco. Si eseguono davvero i due passi, in uno
    scenario che rilascia e in uno che apre il pin, e si guardano i comandi emessi."""
    rilascio = mondo()
    assert coda.rilascia(rilascio.repo) == ["rilascio: PBI-600 → v0.3.1"]
    assert rilascio.tag_su_origin() == ["v0.3.0", "v0.3.1"], "lo scenario deve rilasciare"

    apertura = progetto()
    assert coda.pin(apertura.repo)
    assert apertura.comandi("gh", "pr", "create"), "lo scenario deve aprire il pin"

    emessi = [c for c, _ in rilascio.chiamate] + apertura.chiamate
    assert emessi and not [c for c in emessi if c[:3] == ["gh", "pr", "merge"]]


# ---------------------------------------------------------------------------
# Il tick li chiama
# ---------------------------------------------------------------------------

@pytest.fixture
def tick(tmp_path, monkeypatch):
    """Un `smista()` con rilascio e pin sostituiti da registratori, e la decisione `Finita`."""
    repo = tmp_path / "tick"
    (repo / "backlog").mkdir(parents=True)
    (repo / "backlog" / "CODA.md").write_text("", encoding="utf-8")
    albero = tmp_path / "albero"
    albero.mkdir()
    casa = tmp_path / "casa-tick"
    casa.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    chiamati: list[str] = []
    monkeypatch.setattr(coda, "allinea", lambda repo: chiamati.append("allinea"))
    monkeypatch.setattr(coda, "reinstalla", lambda repo, albero: None)
    monkeypatch.setattr(coda, "decidi", lambda repo, albero: coda.Finita())
    monkeypatch.setattr(coda, "rilascia", lambda repo: chiamati.append("rilascia")
                        or ["rilascio: PBI-600 → v0.3.1"], raising=False)
    monkeypatch.setattr(coda, "pin", lambda repo: chiamati.append("pin")
                        or ["pin: PBI-700 — PR del pin a v0.4.0"], raising=False)

    def gira(*argomenti):
        return coda.smista(["--repo", str(repo), "--worktree", str(albero), *argomenti])
    gira.chiamati, gira.repo, gira.casa = chiamati, repo, casa
    return gira


def test_il_tick_rilascia_dopo_aver_allineato_e_scrive_le_righe_nel_log(tick, capsys):
    assert tick() == 0

    assert tick.chiamati.index("allinea") < tick.chiamati.index("rilascia")
    assert "rilascio: PBI-600 → v0.3.1" in capsys.readouterr().out
    log = (tick.repo / coda.LOG).read_text(encoding="utf-8")
    assert "rilascio: PBI-600 → v0.3.1" in log and "pin: PBI-700" in log


def test_il_pin_gira_anche_con_il_tick_in_pausa_perche_e_lui_a_toglierla(tick):
    (tick.casa / "asdlc-tick.pausa").write_text("in attesa del pin\n")

    tick()

    assert "pin" in tick.chiamati
    assert "rilascia" not in tick.chiamati, "il rilascio no: chi ha messo la pausa lavora a mano"


def test_il_dry_run_non_rilascia_e_non_apre_il_pin_ma_il_tick_senza_opzione_si(tick):
    assert tick("--dry-run") == 0
    con_dry_run = list(tick.chiamati)
    tick.chiamati.clear()

    assert tick() == 0

    assert "rilascia" not in con_dry_run and "pin" not in con_dry_run
    assert "rilascia" in tick.chiamati and "pin" in tick.chiamati


# ---------------------------------------------------------------------------
# Un errore non ferma il tick (ADR-0008)
# ---------------------------------------------------------------------------

def test_un_json_illeggibile_nel_pin_diventa_un_avviso_e_non_un_errore(progetto, monkeypatch):
    m = progetto()
    originale = m.esegui
    monkeypatch.setattr(coda, "esegui", lambda cmd, cwd: (0, "<html>502</html>")
                        if cmd[:3] == ["gh", "pr", "list"] and A_MONTE in cmd
                        else originale(cmd, cwd))

    righe = coda.pin(m.repo)

    assert len(righe) == 1 and righe[0].startswith("pin: avviso")
    assert m.rami_su_origin() == []


def test_un_worktree_che_non_si_crea_nel_rilascio_diventa_un_avviso(mondo, monkeypatch):
    m = mondo()

    def non_si_crea(repo, riferimento):
        raise RuntimeError("`git worktree add` è uscito 128")
    monkeypatch.setattr(coda.asdlc_runner, "worktree_di_rilascio", non_si_crea)

    righe = coda.rilascia(m.repo)

    assert len(righe) == 1 and righe[0].startswith("rilascio: avviso")
    assert m.tag_su_origin() == ["v0.3.0"]


# ---------------------------------------------------------------------------
# Un passo che fallisce non si dichiara riuscito (ADR-0008)
# ---------------------------------------------------------------------------

def fallisce(m, monkeypatch, inizio):
    """Il finto di `m` con un comando che esce 1 finché `rotto` è vero; rende il comando
    che lo aggiusta."""
    stato = {"rotto": True}
    originale = m.esegui

    def esegui(cmd, cwd):
        if stato["rotto"] and cmd[:len(inizio)] == inizio:
            return 1, "rifiutato"
        return originale(cmd, cwd)
    monkeypatch.setattr(coda, "esegui", esegui)
    return lambda: stato.update(rotto=False)


def test_un_git_push_del_tag_fallito_e_un_avviso_e_il_tick_dopo_riprova(mondo, monkeypatch):
    m = mondo(rilascia="patch")
    ripara = fallisce(m, monkeypatch, ["git", "push"])

    righe = coda.rilascia(m.repo)

    assert len(righe) == 1 and righe[0].startswith("rilascio: avviso"), righe
    assert "→" not in righe[0]
    assert m.tag_su_origin() == ["v0.3.0"]
    assert git(m.repo, "tag", "--list").split() == ["v0.3.0"], "nessun tag locale che fermi il tick dopo"

    ripara()
    assert coda.rilascia(m.repo) == ["rilascio: PBI-600 → v0.3.1"]
    assert m.tag_su_origin() == ["v0.3.0", "v0.3.1"]


@pytest.mark.parametrize("rotto", [["git", "push"], ["gh", "pr", "create"]],
                         ids=["git-push", "gh-pr-create"])
def test_un_passo_del_pin_fallito_e_un_avviso_e_il_tick_dopo_riprova(progetto, monkeypatch, rotto):
    m = progetto()
    ripara = fallisce(m, monkeypatch, rotto)

    righe = coda.pin(m.repo)

    assert len(righe) == 1 and righe[0].startswith("pin: avviso"), righe
    assert "PR del pin a" not in righe[0]
    assert m.rami_su_origin() == [], "nessun ramo a metà su origin"

    ripara()
    [riga] = coda.pin(m.repo)
    assert riga.endswith("PR del pin a v0.4.0")
    assert len(m.rami_su_origin()) == 1


def test_un_git_commit_del_pin_fallito_non_lascia_il_ramo_locale_e_il_tick_dopo_riprova(progetto, monkeypatch):
    m = progetto()
    ripara = fallisce(m, monkeypatch, ["git", "commit"])

    righe = coda.pin(m.repo)

    assert len(righe) == 1 and righe[0].startswith("pin: avviso"), righe
    assert "PR del pin a" not in righe[0]
    assert git(m.repo, "branch", "--list", "pin/*").strip() == "", "nessun ramo locale a metà"
    assert m.rami_su_origin() == []

    ripara()
    [riga] = coda.pin(m.repo)
    assert riga.endswith("PR del pin a v0.4.0")
    assert len(m.rami_su_origin()) == 1


# ---------------------------------------------------------------------------
# `attese()` legge anche i rami `pbi/*` su origin (`PBI-512`, giro 3, decisione (d))
# ---------------------------------------------------------------------------

def checkout_con_la_riga_solo_sul_ramo(tmp_path):
    """Un checkout su `main` senza `attende:`, e un ramo `pbi/pbi-700` su origin che la ha."""
    origin, repo = tmp_path / "attese-origin.git", tmp_path / "attese"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(repo))
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "backlog").mkdir()
    (repo / "backlog" / "PBI-700-il-pbi-fermo.md").write_text(
        "# PBI-700: il PBI fermo\n\n## Direttiva\n\nAspetta.\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "checkout", "-q", "-b", "pbi/pbi-700")
    (repo / "backlog" / "PBI-700-il-pbi-fermo.md").write_text(
        f"# PBI-700: il PBI fermo\n\nattende: {A_MONTE}#PBI-505\n\n## Direttiva\n\nAspetta.\n")
    git(repo, "commit", "-qam", "attende")
    git(repo, "push", "-q", "origin", "pbi/pbi-700")
    git(repo, "checkout", "-q", "main")
    return repo


def test_attese_legge_la_riga_che_sta_solo_sul_ramo_pbi_di_origin(tmp_path):
    repo = checkout_con_la_riga_solo_sul_ramo(tmp_path)

    assert coda.attese(repo) == [("PBI-700-il-pbi-fermo.md", A_MONTE, "PBI-505")]


def test_attese_conta_una_volta_sola_il_pbi_con_la_riga_in_main_e_sul_ramo(progetto):
    m = progetto()
    # Il ramo del PBI fermo ha un commit oltre main che cambia il suo file lasciando la stessa
    # riga `attende:`: è `--no-merged` e il file compare nel diff, quindi `attese()` lo legge
    # davvero e la terna arriva due volte a `raccogli`.
    file = m.repo / "backlog" / "PBI-700-il-pbi-fermo.md"
    git(m.repo, "checkout", "-q", "-b", "ramo-fermo")
    file.write_text(file.read_text() + "\nUna riga in più.\n")
    git(m.repo, "commit", "-qam", "il ramo cambia il file, la riga resta")
    git(m.repo, "push", "-q", "-f", "origin", "ramo-fermo:refs/heads/pbi/pbi-700")
    git(m.repo, "checkout", "-q", "main")
    git(m.repo, "fetch", "-q", "origin")

    assert coda.attese(m.repo) == [("PBI-700-il-pbi-fermo.md", A_MONTE, "PBI-505")]


def test_attese_non_legge_i_rami_gia_in_main_ne_le_copie_vecchie_di_altri_pbi(tmp_path):
    """Giro 3, rilievo 2 (decisione (d): i rami `pbi/*` «non ancora in `main`»). Un ramo già
    mergiato, con la riga di un PBI poi cambiata in `main`, e un ramo vivo che parte da prima
    del cambio e tocca solo il suo file, non riportano il bersaglio superato."""
    origin, repo = tmp_path / "vecchi-origin.git", tmp_path / "vecchi"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(repo))
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    scrivi = lambda nome, riga: (repo / "backlog" / nome).write_text(  # noqa: E731
        f"# {nome}\n\n{riga}\n\n## Direttiva\n\nAspetta.\n")
    (repo / "backlog").mkdir()
    scrivi("PBI-700-fermo.md", f"attende: {A_MONTE}#PBI-501")
    scrivi("PBI-701-mergiato.md", "")
    scrivi("PBI-702-vivo.md", "")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "checkout", "-q", "-b", "pbi/pbi-702")
    scrivi("PBI-702-vivo.md", f"attende: {A_MONTE}#PBI-502")
    git(repo, "commit", "-qam", "il vivo attende")
    git(repo, "push", "-q", "origin", "pbi/pbi-702")
    git(repo, "checkout", "-q", "main")
    git(repo, "checkout", "-q", "-b", "pbi/pbi-701")
    scrivi("PBI-701-mergiato.md", f"attende: {A_MONTE}#PBI-503")
    git(repo, "commit", "-qam", "il mergiato attende")
    git(repo, "push", "-q", "origin", "pbi/pbi-701")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--ff-only", "pbi/pbi-701")
    scrivi("PBI-701-mergiato.md", "")
    scrivi("PBI-700-fermo.md", f"attende: {A_MONTE}#PBI-601")
    git(repo, "commit", "-qam", "main cambia i bersagli")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin")

    assert sorted(coda.attese(repo)) == [
        ("PBI-700-fermo.md", A_MONTE, "PBI-601"),
        ("PBI-702-vivo.md", A_MONTE, "PBI-502"),
    ]


# ---------------------------------------------------------------------------
# `rilascia: major` (PBI-530, criterio 3)
# ---------------------------------------------------------------------------

def test_rilascia_major_alza_la_prima_cifra_e_azzera_le_altre_due():
    assert coda.prossimo_tag(["v0.9.2"], "major") == "v1.0.0"
    assert coda.rilascia_del_pbi("# PBI-1: x\n\nrilascia: major\n\n## Direttiva\n") == "major"


# ---------------------------------------------------------------------------
# Il merge del tick (PBI-530, ADR-0033)
# ---------------------------------------------------------------------------

PBI_7 = """# PBI-7: un cambio al runner

## Direttiva

Fai.

**Scope**

- `tools/asdlc/coda.py` — il passo.
- `backlog/PBI-7-un-cambio.md` — la spunta.
- `decisions/` — le decisioni.

## Verifica
- [x] **Il primo criterio.** Fatto.
- [x] **Il secondo criterio.** Fatto.
"""


class MondoDelMerge:
    """Il tick di un progetto con `PBI-7` in coda, il suo ramo su `origin`, il rapporto del giro
    nel worktree del runner e un `gh` finto che rende la PR aperta (e, dopo il `merge`, mergiata)."""

    def __init__(self, tmp_path, ramo="pbi/pbi-7", esito=None, ci="SUCCESS",
                 mergeable="MERGEABLE", testo=PBI_7, files="ok", in_coda=True):
        self.origin = tmp_path / "merge-origin.git"
        self.repo = tmp_path / "merge-tick"
        self.worktree = tmp_path / "merge-albero"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(tmp_path, "clone", "-q", str(self.origin), str(self.repo))
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "backlog").mkdir()
        (self.repo / "backlog" / "CODA.md").write_text(
            "# Coda\n\n- PBI-7\n" if in_coda else "# Coda\n\n- PBI-8\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "base")
        git(self.repo, "push", "-q", "origin", "main")
        git(self.repo, "checkout", "-q", "-b", ramo)
        (self.repo / "backlog" / "PBI-7-un-cambio.md").write_text(testo)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "PBI-7: un cambio")
        git(self.repo, "push", "-q", "origin", ramo)
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "fetch", "-q", "origin")
        (self.worktree / "runs").mkdir(parents=True)
        voce = {"pbi": "PBI-7", "stato": "fatto", "critic_saltato": False, "solver": []}
        voce.update(esito or {})
        (self.worktree / "runs" / "20261028-100000.json").write_text(
            json.dumps({"run": "20261028-100000", "esiti": [voce]}))
        self.pr = {"number": 1, "title": "PBI-7: un cambio al runner", "headRefName": ramo,
                   "mergeable": mergeable,
                   "statusCheckRollup": [{"conclusion": ci, "status": "COMPLETED"}]}
        if files is not None:
            self.pr["files"] = [{"path": p} for p in (
                ["tools/asdlc/coda.py", "backlog/PBI-7-un-cambio.md"] if files == "ok" else files)]
        self.chiamate: list[list[str]] = []
        self.altre_pr: list = []
        self.uscita_merge = 0
        self.uscita_commento = 0

    def esegui(self, cmd, cwd):
        self.chiamate.append(list(cmd))
        if cmd[:3] == ["gh", "pr", "list"]:
            return 0, json.dumps([self.pr, *self.altre_pr])
        if cmd[:3] == ["gh", "pr", "merge"]:
            return self.uscita_merge, "" if self.uscita_merge == 0 else "merge rifiutato"
        if cmd[:3] == ["gh", "pr", "comment"]:
            return self.uscita_commento, "" if self.uscita_commento == 0 else "commento rifiutato"
        return ESEGUI_VERO(cmd, cwd)

    def comandi(self, *inizio):
        return [c for c in self.chiamate if c[:len(inizio)] == list(inizio)]


@pytest.fixture
def mondo_del_merge(tmp_path, monkeypatch):
    def crea(**kwargs):
        m = MondoDelMerge(tmp_path, **kwargs)
        monkeypatch.setattr(coda, "esegui", m.esegui)
        return m
    return crea


def test_una_pr_che_passa_tutte_le_condizioni_si_mergia_e_il_tick_lo_dice(mondo_del_merge):
    m = mondo_del_merge()

    righe = coda.passo_del_merge(m.repo, m.worktree)

    assert righe == ["merge: PBI-7 #1"]
    [merge] = m.comandi("gh", "pr", "merge")
    assert merge[:5] == ["gh", "pr", "merge", "1", "--merge"]
    assert m.comandi("gh", "pr", "comment"), "il commento sulla PR"
    assert m.chiamate.index(merge) < m.chiamate.index(m.comandi("gh", "pr", "comment")[0])


SCENARI_CHE_ATTENDONO = {
    "ramo-non-del-runner": ({"ramo": "feature/x"}, "ramo"),
    "pbi-non-in-coda": ({"in_coda": False}, "coda"),
    "rapporto-assente": ({"esito": {"pbi": "PBI-6"}}, "rapporto"),
    "stato-non-fatto": ({"esito": {"stato": "fermato"}}, "stato"),
    "critic-saltato": ({"esito": {"critic_saltato": True}}, "Critic"),
    "esito-intento": ({"esito": {"solver": [{"esito": "intento"}]}}, "intento"),
    "ci-rossa": ({"ci": "FAILURE"}, "CI"),
    "conflitto": ({"mergeable": "CONFLICTING"}, "mergeable"),
    "criterio-non-spuntato": ({"testo": PBI_7.replace("- [x] **Il secondo", "- [ ] **Il secondo")},
                              "criterio non spuntato"),
    "criterio-a-vista-spuntato": ({"testo": PBI_7.replace("Il secondo criterio.**",
                                                          "Il secondo criterio (a vista).**")},
                                  "a vista"),
    "file-fuori-scope": ({"files": ["tools/asdlc/altro.py", "backlog/PBI-7-un-cambio.md"]},
                         "fuori dallo Scope"),
    "file-in-decisions": ({"files": ["decisions/ADR-0099-x.md", "backlog/PBI-7-un-cambio.md"]},
                          "riservato"),
    "files-assente": ({"files": None}, "elenco dei file"),
}


@pytest.mark.parametrize("scenario", SCENARI_CHE_ATTENDONO.values(),
                         ids=SCENARI_CHE_ATTENDONO.keys())
def test_ogni_condizione_che_manca_lascia_la_pr_a_una_persona_col_motivo(mondo_del_merge, scenario):
    cambio, parola = scenario
    m = mondo_del_merge(**cambio)

    righe = coda.passo_del_merge(m.repo, m.worktree)

    assert m.comandi("gh", "pr", "merge") == []
    [riga] = righe
    assert riga.startswith("merge: #1 attende una persona — ")
    assert parola in riga


def test_un_merge_che_non_riesce_non_e_scritto_come_fatto(mondo_del_merge):
    m = mondo_del_merge()
    m.uscita_merge = 1

    righe = coda.passo_del_merge(m.repo, m.worktree)

    assert m.comandi("gh", "pr", "comment") == []
    assert not any(r.startswith("merge: PBI-7 #1") for r in righe)
    [riga] = righe
    assert riga.startswith("merge: #1 non riuscito")
    assert "merge rifiutato" in riga


def test_un_commento_che_non_riesce_lascia_la_riga_del_merge_e_lo_dice(mondo_del_merge):
    m = mondo_del_merge()
    m.uscita_commento = 1

    righe = coda.passo_del_merge(m.repo, m.worktree)

    assert righe[0] == "merge: PBI-7 #1"
    assert any("commento" in r and "#1" in r for r in righe[1:])


@pytest.mark.parametrize("malformata", ["senza-numero", "rapporto-solver-null", "solver-non-dict"])
def test_una_pr_malformata_non_cancella_le_righe_delle_altre(mondo_del_merge, malformata):
    m = mondo_del_merge()
    if malformata == "senza-numero":
        m.altre_pr = [{"headRefName": "pbi/pbi-9"}]
    else:
        # Una seconda PR, di PBI-9, il cui rapporto ha un `solver` che non si legge.
        m.altre_pr = [{**m.pr, "number": 2, "title": "PBI-9: altro", "headRefName": "pbi/pbi-9",
                       "files": [{"path": "tools/asdlc/coda.py"},
                                 {"path": "backlog/PBI-9-altro.md"}]}]
        (m.repo / "backlog" / "CODA.md").write_text("# Coda\n\n- PBI-7\n- PBI-9\n")
        git(m.repo, "commit", "-qam", "PBI-9 in coda")
        solver = None if malformata == "rapporto-solver-null" else ["intento"]
        (m.worktree / "runs" / "20261028-110000.json").write_text(json.dumps({
            "run": "20261028-110000",
            "esiti": [{"pbi": "PBI-9", "stato": "fatto", "critic_saltato": False,
                       "solver": solver}]}))
        git(m.repo, "checkout", "-q", "-b", "pbi/pbi-9")
        (m.repo / "backlog" / "PBI-9-altro.md").write_text(PBI_7.replace("PBI-7", "PBI-9"))
        git(m.repo, "add", ".")
        git(m.repo, "commit", "-qm", "PBI-9")
        git(m.repo, "push", "-q", "origin", "pbi/pbi-9")
        git(m.repo, "checkout", "-q", "main")
        git(m.repo, "fetch", "-q", "origin")

    righe = coda.passo_del_merge(m.repo, m.worktree)

    assert "merge: PBI-7 #1" in righe
    assert len(righe) == 2, righe


def test_il_pbi_nel_log_e_nel_commento_e_quello_del_ramo_che_si_e_verificato(mondo_del_merge):
    m = mondo_del_merge()
    m.pr["title"] = "PBI-8: un altro titolo"

    righe = coda.passo_del_merge(m.repo, m.worktree)

    assert righe == ["merge: PBI-7 #1"]
    [commento] = m.comandi("gh", "pr", "comment")
    assert "PBI-7" in commento[-1]
    assert "PBI-8" not in commento[-1]


def test_il_commento_sulla_pr_elenca_le_sei_condizioni_e_lo_sha_mergiato(mondo_del_merge):
    m = mondo_del_merge()
    sha = git(m.repo, "rev-parse", "origin/pbi/pbi-7")

    coda.passo_del_merge(m.repo, m.worktree)

    [commento] = m.comandi("gh", "pr", "comment")
    corpo = commento[commento.index("--body") + 1]
    assert len([r for r in corpo.splitlines() if r.startswith("- ") and r.endswith(": ok")]) == 6
    assert sha in corpo


class MondoCheMergia(Mondo):
    """Il mondo del rilascio con la PR di `PBI-600` ancora aperta: `gh pr merge` la rende
    mergiata, e solo da lì il rilascio la vede."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path, rilascia="patch")
        self.mergiato = False
        self.worktree = tmp_path / "albero-del-giro"
        (self.worktree / "runs").mkdir(parents=True)
        (self.worktree / "runs" / "20261028-100000.json").write_text(json.dumps({
            "run": "20261028-100000",
            "esiti": [{"pbi": "PBI-600", "stato": "fatto", "critic_saltato": False,
                       "solver": []}]}))
        (self.repo / "backlog" / "CODA.md").write_text("# Coda\n\n- PBI-600\n")
        git(self.repo, "checkout", "-q", "-b", "pbi/pbi-600")
        (self.repo / "backlog" / "PBI-600-un-cambio.md").write_text(
            "# PBI-600: un cambio al runner\n\nrilascia: patch\n\n## Direttiva\n\nFai.\n\n"
            "**Scope**\n\n- `tools/asdlc/coda.py` — il passo.\n"
            "- `backlog/PBI-600-un-cambio.md` — la spunta.\n\n## Verifica\n- [x] **Uno.** Fatto.\n")
        git(self.repo, "commit", "-qam", "PBI-600: il giro")
        git(self.repo, "push", "-q", "origin", "pbi/pbi-600")
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "fetch", "-q", "origin")

    def esegui(self, cmd, cwd):
        if cmd[:3] == ["gh", "pr", "list"] and "open" in cmd:
            self.chiamate.append((list(cmd), Path(cwd)))
            aperte = [] if self.mergiato else [{
                "number": 1, "title": "PBI-600: un cambio al runner",
                "headRefName": "pbi/pbi-600", "mergeable": "MERGEABLE",
                "statusCheckRollup": [{"conclusion": "SUCCESS"}],
                "files": [{"path": "tools/asdlc/coda.py"},
                          {"path": "backlog/PBI-600-un-cambio.md"}]}]
            return 0, json.dumps(aperte)
        if cmd[:3] == ["gh", "pr", "list"] and not self.mergiato:
            self.chiamate.append((list(cmd), Path(cwd)))
            return 0, "[]"
        if cmd[:3] == ["gh", "pr", "merge"]:
            self.chiamate.append((list(cmd), Path(cwd)))
            self.mergiato = True
            return 0, ""
        if cmd[:3] == ["gh", "pr", "comment"]:
            self.chiamate.append((list(cmd), Path(cwd)))
            return 0, ""
        return super().esegui(cmd, cwd)


def test_il_tick_mergia_prima_di_rilasciare_nello_stesso_passaggio(tmp_path, monkeypatch, capsys):
    m = MondoCheMergia(tmp_path)
    monkeypatch.setattr(coda, "esegui", m.esegui)
    casa = tmp_path / "casa-del-tick"
    casa.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    monkeypatch.setattr(coda, "allinea", lambda repo: None)
    monkeypatch.setattr(coda, "reinstalla", lambda repo, albero: None)
    monkeypatch.setattr(coda, "decidi", lambda repo, albero: coda.Finita())
    monkeypatch.setattr(coda, "pin", lambda repo: [])

    assert coda.smista(["--repo", str(m.repo), "--worktree", str(m.worktree)]) == 0

    righe = capsys.readouterr().out.splitlines()
    assert "merge: PBI-600 #1" in righe
    [rilascio] = [r for r in righe if r.startswith("rilascio: PBI-600 → ")]
    assert righe.index("merge: PBI-600 #1") < righe.index(rilascio)
