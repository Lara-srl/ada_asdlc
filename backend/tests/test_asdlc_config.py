"""Il lettore di `asdlc.toml` (`backlog/PBI-358`).

Le costanti del runner — i gate, i percorsi, le soglie, il ramo di base — stavano
scritte nel sorgente, e le stesse due forme dell'id di un PBI in cinque punti
diversi: PBI-353 ne ha corrette tre insieme, e la coda è rimasta ferma sette ore
perché la quarta diceva un'altra cosa. Qui si legge un file solo.

`tools/` non è un pacchetto e non deve diventarlo per un test: si carica il modulo
dal suo percorso, come `test_asdlc_runner.py` e `test_asdlc_coda.py`.
"""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SORGENTE = REPO / "tools" / "asdlc_config.py"

_spec = importlib.util.spec_from_file_location("asdlc_config", SORGENTE)
asdlc_config = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = asdlc_config
_spec.loader.exec_module(asdlc_config)


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
percorso = "~/prova-run"

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
    assert cfg.worktree.percorso == Path.home() / "prova-run", "la tilde si espande"
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
    scrivi_toml(tmp_path, '[ambiente]\nvenv = "/opt/venv"\n\n[worktree]\npercorso = "/tmp/altro-run"\n',
                nome="asdlc.local.toml")
    con = asdlc_config.carica(tmp_path)

    assert senza.ambiente.venv == ".venv"
    assert senza.worktree.percorso == Path.home() / "prova-run"
    assert con.ambiente.venv == "/opt/venv"
    assert con.ambiente.prestiti == ("dati",), "ciò che il locale non dice resta"
    assert con.worktree.percorso == Path("/tmp/altro-run")
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
