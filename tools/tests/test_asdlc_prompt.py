"""I prompt dei cinque ruoli come dati del pacchetto (`backlog/PBI-386`).

Il Builder, l'igiene, la riprova, il Critic e il rimedio stavano come costanti
nel sorgente del runner. Diventano file di `asdlc/prompt/`, e un progetto li
**estende** con un file di aggiunte per ruolo, accodato; non li sostituisce
(`ADR-0026`, decisione 2).

Il golden in `dati/prompt/` è il testo generato dal codice di prima dello
spostamento, con la config fissa di questo file: lo spostamento non cambia un
byte.
"""

import importlib
from pathlib import Path

import pytest

# Il progetto di prova (PBI-394, decisione 1): la configurazione del runner sotto
# test, al posto del progetto che ospita questi test.
PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"
GOLDEN = Path(__file__).resolve().parent / "dati" / "prompt"

runner = importlib.import_module("asdlc.runner")
asdlc_config = runner.asdlc_config
# Come in `test_asdlc_runner.py`: `configura()` ricava i percorsi da `REPO`, che
# fuori da `main()` nessuno ha ancora trovato, e la fixture `configura` rimette
# alla fine la configurazione di prima, che deve esserci.
runner.REPO = PROGETTO
runner.configura(asdlc_config.carica(PROGETTO))


@pytest.fixture(autouse=True)
def db():
    return None


@pytest.fixture(autouse=True)
def clear_login_limiter():
    return None


@pytest.fixture(autouse=True)
def clear_event_bus():
    return None


RUOLI = ("builder", "igiene", "riprova", "critic", "rimedio")

# La config fissa: un progetto che non è aDa, e il venv del runner in un
# percorso che non dipende dalla macchina, perché il prompt del Builder lo
# scrive per intero.
TOML_FISSO = """\
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
prestiti = []
# Il pacchetto lo dice il file locale; da dove si reinstalla, solo questo (PBI-395).
installa = "./tools"

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
"""
# Il percorso assoluto sta nel file locale, che è il suo posto.
LOCALE_FISSO = '[ambiente]\npacchetto = "/opt/asdlc/venv"\n'

PBI = "storie/US-7-prova.md"


def generati() -> dict[str, str]:
    """I cinque prompt come li scrive il runner, con i segnaposto riempiti come
    li riempie un giro."""
    return {
        "builder": runner.PROMPT_BUILDER.format(pbi_path=PBI),
        "igiene": runner.PROMPT_IGIENE.format(sporco="?? nuovo.py"),
        "riprova": runner.PROMPT_RIPROVA.format(esiti="## pytest\n1 failed"),
        "critic": runner.MODELLO_CRITIC.format(base="ba5e386", pbi_path=PBI),
        "rimedio": runner.MODELLO_RIMEDIO.format(base="ba5e386", pbi_path=PBI,
                                                 rapporto="1. [scope]: x"),
    }


def golden(ruolo: str) -> str:
    return (GOLDEN / f"{ruolo}.txt").read_text(encoding="utf-8")


@pytest.fixture
def configura(tmp_path):
    """Scrive un progetto con la config fissa, più `sezione` in coda al TOML e i
    file di `aggiunte` nella loro cartella, e lo applica al runner. Alla fine
    rimette la configurazione di prima."""
    di_prima = runner.CFG

    def _applica(sezione: str = "", aggiunte: dict[str, str] | None = None) -> Path:
        progetto = tmp_path / "progetto"
        progetto.mkdir(exist_ok=True)
        (progetto / "asdlc.toml").write_text(TOML_FISSO + sezione, encoding="utf-8")
        (progetto / "asdlc.local.toml").write_text(LOCALE_FISSO, encoding="utf-8")
        for nome, testo in (aggiunte or {}).items():
            file = progetto / nome
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(testo, encoding="utf-8")
        runner.configura(asdlc_config.carica(progetto))
        return progetto

    yield _applica
    runner.configura(di_prima)


@pytest.mark.parametrize("ruolo", RUOLI)
def test_senza_aggiunte_il_prompt_generato_e_identico_al_golden(configura, ruolo):
    configura()

    assert generati()[ruolo] == golden(ruolo)


# --- Le aggiunte del progetto ------------------------------------------------


# Con le graffe dentro: un'aggiunta è testo, non un modello, e un `{x}` scritto
# da chi estende il prompt arriva all'agente così com'è.
AGGIUNTA = 'Qui i test si lanciano con `make prova`, e la risposta è `{"esito": "ok"}` o `{x}`.\n'


@pytest.mark.parametrize("ruolo", RUOLI)
def test_un_file_di_aggiunte_finisce_in_fondo_al_prompt_del_suo_ruolo_e_in_nessun_altro(
    configura, ruolo,
):
    configura('\n[prompt]\naggiunte = "asdlc-aggiunte"\n',
              {f"asdlc-aggiunte/{ruolo}.md": AGGIUNTA})

    prompt = generati()

    assert prompt[ruolo] == golden(ruolo) + "\n## Aggiunte del progetto\n\n" + AGGIUNTA
    for altro in RUOLI:
        if altro != ruolo:
            assert prompt[altro] == golden(altro), f"l'aggiunta di {ruolo} è finita in {altro}"
