"""Il lettore di `asdlc.toml` (`backlog/PBI-358`).

Le costanti del runner — i gate, i percorsi, le soglie, il ramo di base — stavano
scritte nel sorgente, e le stesse due forme dell'id di un PBI in cinque punti
diversi: PBI-353 ne ha corrette tre insieme, e la coda è rimasta ferma sette ore
perché la quarta diceva un'altra cosa. Qui si legge un file solo.

Il modulo si carica per nome, `asdlc.config`, come `test_asdlc_runner.py` e
`test_asdlc_coda.py`: `conftest.py` mette `tools/` sul `sys.path` (PBI-383).
"""

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SORGENTE = REPO / "tools" / "asdlc" / "config.py"

asdlc_config = importlib.import_module("asdlc.config")


@pytest.fixture(autouse=True)
def db():
    return None


@pytest.fixture(autouse=True)
def clear_login_limiter():
    return None


@pytest.fixture(autouse=True)
def clear_event_bus():
    return None


# Un `asdlc.toml` di prova, completo e piccolo: due gate e valori che non sono
# quelli del repository, così un test che leggesse per sbaglio il file vero se
# ne accorgerebbe.
TOML_DI_PROVA = """\
[git]
base = "origin/master"
prefisso_ramo = "us/us-"

[backlog]
cartella = "storie"
coda = "storie/CODA.md"
id = "US-{n}"
file = "US-{n}-{slug}.md"

[registro]
cartella = "giri"
tempi = "ore.csv"

[ambiente]
venv = ".venv"
prestiti = ["dati"]

[worktree]
percorso = "../prova-run"

[soglie]
tentativi = 2
igiene = 5
revisioni = 7

[gate_del_rosso]
attivo = true

[[gate]]
nome = "pytest"
comando = ["pytest", "-q"]

[[gate]]
nome = "mypy"
comando = ["mypy", "."]
cwd = "src"
solo_se_tocca = ["src/", "pyproject.toml"]
"""


def scrivi_toml(cartella: Path, testo: str = TOML_DI_PROVA, nome: str = "asdlc.toml") -> Path:
    (cartella / nome).write_text(testo, encoding="utf-8")
    return cartella


def test_carica_un_toml_e_torna_i_campi_tipizzati(tmp_path):
    """Non un dizionario: attributi con un nome, così `cfg.soglie.revisioni` si
    legge e si sbaglia a tempo di lettura del file, non a metà giro."""
    cfg = asdlc_config.carica(scrivi_toml(tmp_path))

    assert cfg.git.base == "origin/master"
    assert cfg.git.prefisso_ramo == "us/us-"
    assert (cfg.backlog.cartella, cfg.backlog.coda) == ("storie", "storie/CODA.md")
    assert (cfg.backlog.id, cfg.backlog.file) == ("US-{n}", "US-{n}-{slug}.md")
    assert (cfg.registro.cartella, cfg.registro.tempi) == ("giri", "ore.csv")
    assert cfg.ambiente.venv == ".venv"
    assert cfg.ambiente.prestiti == ("dati",)
    assert cfg.worktree.percorso == tmp_path.resolve().parent / "prova-run", (
        "relativo alla radice comune, che fuori da git è la radice del progetto")
    assert (cfg.soglie.tentativi, cfg.soglie.igiene, cfg.soglie.revisioni) == (2, 5, 7)
    assert cfg.gate_del_rosso.attivo is True
    assert [(g.nome, list(g.comando), g.cwd, list(g.solo_se_tocca)) for g in cfg.gate] == [
        ("pytest", ["pytest", "-q"], ".", []),
        ("mypy", ["mypy", "."], "src", ["src/", "pyproject.toml"]),
    ], "cwd vale `.` e solo_se_tocca è vuoto quando non sono scritti"


def test_l_asdlc_toml_del_repository_si_carica():
    """Il file vero, non uno di prova: è quello che il runner leggerà al prossimo
    giro, e un errore lì ferma `git commit` a chi lo sta usando (decisione 4)."""
    cfg = asdlc_config.carica(REPO)

    assert cfg.git.base == "origin/main"
    assert cfg.soglie.revisioni == 4
    assert cfg.gate_del_rosso.attivo is True


def test_i_tetti_per_chiamata_hanno_i_default_90_e_25(tmp_path):
    """PBI-369, decisione 6: un tetto per ruolo in `[soglie]`. Il TOML di prova
    non li scrive, e valgono i minuti confermati da Francesco il 24/09."""
    cfg = asdlc_config.carica(scrivi_toml(tmp_path))

    assert (cfg.soglie.minuti_builder, cfg.soglie.minuti_critic) == (90, 25)


def test_i_tetti_per_chiamata_si_leggono_da_soglie(tmp_path):
    con_i_tetti = TOML_DI_PROVA.replace(
        "revisioni = 7\n", "revisioni = 7\nminuti_builder = 45\nminuti_critic = 12\n"
    )

    cfg = asdlc_config.carica(scrivi_toml(tmp_path, con_i_tetti))

    assert (cfg.soglie.minuti_builder, cfg.soglie.minuti_critic) == (45, 12)


@pytest.mark.parametrize("chiave", ["minuti_builder", "minuti_critic"])
@pytest.mark.parametrize("valore", [0, -5])
def test_un_tetto_non_positivo_si_ferma_nominando_la_chiave(tmp_path, chiave, valore):
    """Un tetto di zero minuti scadrebbe a ogni chiamata: ogni giro chiuderebbe
    `senza esito` dopo un lancio, e la ragione sarebbe un numero nel TOML."""
    sbagliato = TOML_DI_PROVA.replace("revisioni = 7\n", f"revisioni = 7\n{chiave} = {valore}\n")

    with pytest.raises(asdlc_config.ErroreDiConfigurazione) as fermata:
        asdlc_config.carica(scrivi_toml(tmp_path, sbagliato))

    assert f"[soglie].{chiave}" in str(fermata.value)


def test_l_asdlc_toml_del_repository_dichiara_i_tetti():
    """I due valori stanno scritti nel TOML, con la loro ragione accanto: un
    default del lettore non si vede da chi apre il file."""
    testo = (REPO / "asdlc.toml").read_text(encoding="utf-8")

    assert "minuti_builder = 90" in testo
    assert "minuti_critic = 25" in testo


def test_un_file_assente_si_ferma_nominando_il_file(tmp_path):
    """Nessun default silenzioso: un runner che partisse senza `asdlc.toml`
    passerebbe per la ragione sbagliata (decisione 3)."""
    with pytest.raises(asdlc_config.ErroreDiConfigurazione) as fermata:
        asdlc_config.carica(tmp_path)

    assert "asdlc.toml" in str(fermata.value)
    assert str(tmp_path) in str(fermata.value), "dove lo ha cercato"


def test_una_chiave_mancante_si_ferma_nominando_file_e_chiave(tmp_path):
    """Non un `KeyError`: quel messaggio lo legge chi ha appena perso l'uso di
    `git commit`, perché l'hook esegue il runner a ogni commit."""
    senza_base = TOML_DI_PROVA.replace('base = "origin/master"\n', "")

    with pytest.raises(asdlc_config.ErroreDiConfigurazione) as fermata:
        asdlc_config.carica(scrivi_toml(tmp_path, senza_base))

    assert "asdlc.toml" in str(fermata.value)
    assert "[git].base" in str(fermata.value)


def test_una_sezione_mancante_si_ferma_nominando_la_sezione(tmp_path):
    senza_soglie = TOML_DI_PROVA.replace(
        "[soglie]\ntentativi = 2\nigiene = 5\nrevisioni = 7\n", ""
    )

    with pytest.raises(asdlc_config.ErroreDiConfigurazione) as fermata:
        asdlc_config.carica(scrivi_toml(tmp_path, senza_soglie))

    assert "[soglie]" in str(fermata.value)


def test_un_valore_del_tipo_sbagliato_si_ferma_nominando_la_chiave(tmp_path):
    """`revisioni = "7"` è una stringa: un `range("7" + 1)` a metà giro sarebbe
    un traceback, e a quel punto il Builder ha già lavorato un'ora."""
    stringa = TOML_DI_PROVA.replace("revisioni = 7", 'revisioni = "7"')

    with pytest.raises(asdlc_config.ErroreDiConfigurazione) as fermata:
        asdlc_config.carica(scrivi_toml(tmp_path, stringa))

    assert "[soglie].revisioni" in str(fermata.value)


def test_un_toml_malformato_si_ferma_nominando_il_file(tmp_path):
    with pytest.raises(asdlc_config.ErroreDiConfigurazione) as fermata:
        asdlc_config.carica(scrivi_toml(tmp_path, "[git\nbase = \n"))

    assert "asdlc.toml" in str(fermata.value)


def test_asdlc_local_toml_sovrascrive_ambiente_e_worktree_chiave_per_chiave(tmp_path):
    """I percorsi di macchina stanno nel file gitignored, non in quello versionato.

    Assente non è un errore: gitignored vuol dire che nel worktree del runner non
    c'è, e se fosse obbligatorio il primo giro dopo il merge non partirebbe
    (decisione 3). Presente, sovrascrive chiave per chiave: un `[ambiente]`
    locale che dice solo il venv non cancella i prestiti, o ogni macchina
    dovrebbe ricopiarsi la sezione intera per cambiare una riga."""
    scrivi_toml(tmp_path)
    senza = asdlc_config.carica(tmp_path)
    scrivi_toml(tmp_path, '[ambiente]\nvenv = "/opt/venv"\npacchetto = "/opt/venv-asdlc"\n\n'
                '[worktree]\npercorso = "/tmp/altro-run"\n', nome="asdlc.local.toml")
    con = asdlc_config.carica(tmp_path)

    assert senza.ambiente.venv == ".venv"
    assert senza.worktree.percorso == tmp_path.resolve().parent / "prova-run"
    assert con.ambiente.venv == "/opt/venv"
    assert con.ambiente.prestiti == ("dati",), "ciò che il locale non dice resta"
    assert con.worktree.percorso == Path("/tmp/altro-run")
    assert con.ambiente.pacchetto == Path("/opt/venv-asdlc"), (
        "nel file locale un percorso assoluto vale (PBI-384, decisione 2)")
    assert con.git.base == "origin/master", "le altre sezioni non le tocca"


@pytest.mark.parametrize("sezione", [
    '[[gate]]\nnome = "pytest"\ncomando = ["pytest"]\n',
    '[soglie]\nrevisioni = 9\n',
    '[git]\nbase = "origin/mio"\n',
])
def test_una_sezione_diversa_nel_locale_e_un_errore_che_lo_dice(tmp_path, sezione):
    """I gate, le soglie e il ramo sono del progetto: una macchina che li
    cambiasse da un file gitignored girerebbe un altro metodo con lo stesso
    nome, e nessuna PR lo mostrerebbe."""
    scrivi_toml(tmp_path)
    scrivi_toml(tmp_path, sezione, nome="asdlc.local.toml")

    with pytest.raises(asdlc_config.ErroreDiConfigurazione) as fermata:
        asdlc_config.carica(tmp_path)

    assert "asdlc.local.toml" in str(fermata.value)
    assert sezione.split("]")[0].strip("[") in str(fermata.value), "nomina la sezione"
    assert "[ambiente]" in str(fermata.value) and "[worktree]" in str(fermata.value), (
        "e dice quali sono le due che può sovrascrivere"
    )


def test_il_lettore_usa_solo_la_libreria_standard():
    """È ciò che rende il runner copiabile senza un `pip install`: la
    precondizione 2 di `ADR-0017`, che la Fase 2 di `SCAFFOLDING.md` dimostrerà
    in CI con il solo `pytest` installato. `tomllib` è stdlib da Python 3.11."""
    modulo = ast.parse(SORGENTE.read_text(encoding="utf-8"))
    importati = {
        (alias.name if isinstance(nodo, ast.Import) else nodo.module).split(".")[0]
        for nodo in ast.walk(modulo)
        if isinstance(nodo, (ast.Import, ast.ImportFrom))
        for alias in nodo.names
    }
    fuori = importati - sys.stdlib_module_names
    assert not fuori, f"import fuori dalla libreria standard: {sorted(fuori)}"


# --- La radice del progetto è la cartella di lavoro (PBI-382) ---------------


def test_la_radice_si_trova_salendo_da_una_sottocartella(tmp_path):
    """Il runner installato non sta nel progetto: il progetto lo dice la cwd, e
    il primo antenato che contiene `asdlc.toml` è la radice."""
    scrivi_toml(tmp_path)
    sotto = tmp_path / "frontend" / "src"
    sotto.mkdir(parents=True)

    assert asdlc_config.radice(sotto) == tmp_path


def test_la_radice_lanciata_dalla_radice_e_la_cartella_stessa(tmp_path):
    scrivi_toml(tmp_path)

    assert asdlc_config.radice(tmp_path) == tmp_path


def test_la_radice_e_il_primo_antenato_col_file_non_l_ultimo(tmp_path):
    """Un progetto dentro un altro: vince quello più vicino alla cwd."""
    scrivi_toml(tmp_path)
    interno = tmp_path / "vendor" / "altro"
    interno.mkdir(parents=True)
    scrivi_toml(interno)

    assert asdlc_config.radice(interno / ".") == interno


def test_senza_asdlc_toml_dalla_cwd_in_su_la_radice_e_un_errore_che_lo_dice(tmp_path):
    """Un runner lanciato fuori da un progetto non ha niente da fare, e lo deve
    dire con la cartella da cui è partito — prima del lucchetto e di ogni
    scrittura, che sono di chi chiama."""
    vuota = tmp_path / "vuota"
    vuota.mkdir()

    with pytest.raises(asdlc_config.ErroreDiConfigurazione) as fermata:
        asdlc_config.radice(vuota)

    assert str(fermata.value) == (
        f"nessun `asdlc.toml` da `{vuota}` in su: il runner si lancia dalla "
        "cartella di un progetto ASDLC"
    )


# --- I percorsi di macchina si risolvono dalla radice comune (PBI-384) -------


def git_in(cartella: Path, *argomenti: str) -> None:
    subprocess.run(["git", "-c", "user.name=prova", "-c", "user.email=prova@example.invalid",
                    *argomenti], cwd=cartella, check=True, capture_output=True)


def test_pacchetto_e_worktree_si_risolvono_dalla_radice_comune_anche_da_un_worktree(tmp_path):
    """`[ambiente].pacchetto` e `[worktree].percorso` sono relativi alla radice
    comune del repository, la cartella madre di `git rev-parse --git-common-dir`:
    il checkout principale, che è lo stesso da ogni suo worktree. Dal checkout del
    tick e da `ada-run` il venv del runner è uno solo (decisioni 1 e 2)."""
    principale = tmp_path / "principale"
    principale.mkdir()
    scrivi_toml(principale, TOML_DI_PROVA.replace(
        'venv = ".venv"\n', 'venv = ".venv"\npacchetto = ".venv-asdlc"\n'
    ))
    git_in(principale, "init", "-q")
    git_in(principale, "add", "-A")
    git_in(principale, "commit", "-q", "-m", "progetto")
    git_in(principale, "worktree", "add", "-q", str(tmp_path / "secondo"))

    dal_principale = asdlc_config.carica(principale)
    dal_worktree = asdlc_config.carica(tmp_path / "secondo")

    venv = principale.resolve() / ".venv-asdlc"
    assert getattr(dal_principale.ambiente, "pacchetto", None) == venv
    assert getattr(dal_worktree.ambiente, "pacchetto", None) == venv
    albero = tmp_path.resolve() / "prova-run"
    assert dal_principale.worktree.percorso == albero
    assert dal_worktree.worktree.percorso == albero


@pytest.mark.parametrize("sezione,chiave,valore", [
    ("worktree", "percorso", "~/prova-run"),
    ("worktree", "percorso", "/tmp/prova-run"),
    ("ambiente", "pacchetto", "~/.venv-asdlc"),
    ("ambiente", "pacchetto", "/opt/venv-asdlc"),
])
def test_un_percorso_di_macchina_in_asdlc_toml_e_un_errore_che_nomina_la_chiave(
    tmp_path, sezione, chiave, valore
):
    """`asdlc.toml` è versionato e deve valere su ogni PC: un percorso assoluto o
    con `~` funziona solo su quello di chi l'ha scritto. Il suo posto è
    `asdlc.local.toml` (PBI-384, decisione 2)."""
    if chiave == "pacchetto":
        testo = TOML_DI_PROVA.replace('venv = ".venv"\n', f'venv = ".venv"\npacchetto = "{valore}"\n')
    else:
        testo = TOML_DI_PROVA.replace('percorso = "../prova-run"', f'percorso = "{valore}"')

    with pytest.raises(asdlc_config.ErroreDiConfigurazione) as fermata:
        asdlc_config.carica(scrivi_toml(tmp_path, testo))

    assert f"[{sezione}].{chiave}" in str(fermata.value)
    assert valore in str(fermata.value)
    assert "asdlc.local.toml" in str(fermata.value), "dice dove va un percorso di macchina"
