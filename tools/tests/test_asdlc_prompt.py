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
import re
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


# --- PBI-524: lo scheletro che il prompt chiede è quello che il lucchetto accetta ---


# Il blocco di esempio dello scheletro nel prompt del Builder: l'unico blocco
# `python` recintato del prompt.
RE_ESEMPIO_DI_SCHELETRO = re.compile(r"```python\n(.*?)```", re.DOTALL)


class TestLoScheletroDelPromptEQuelloDelLucchetto:
    """PBI-524, criterio 1: il prompt e il lucchetto non possono divergere in
    silenzio. L'esempio di scheletro che il prompt dà al Builder passa da
    `e_scheletro_vuoto()`, la stessa funzione del `pre-commit` (decisione 3), e il
    prompt non descrive più uno scheletro con firme (decisione 1)."""

    def test_l_esempio_di_scheletro_del_prompt_e_uno_scheletro_vuoto_per_il_lucchetto(
            self, configura):
        configura()

        blocchi = RE_ESEMPIO_DI_SCHELETRO.findall(generati()["builder"])

        assert len(blocchi) == 1, "il prompt del Builder ha un blocco di esempio dello scheletro"
        assert runner.e_scheletro_vuoto("nlt/esempio.py", blocchi[0])

    @pytest.mark.parametrize("frase", ["la funzione che torna `None`", "contenitore vuoto"])
    def test_il_prompt_non_promette_piu_uno_scheletro_con_firme(self, configura, frase):
        configura()

        # Gli a capo del prompt non contano: la frase può essere spezzata su due righe.
        assert frase not in " ".join(generati()["builder"].split())


# --- PBI-525: i rilievi di storia e la classe dei casi nel prompt del Critic ---


def paragrafi(testo: str) -> list[str]:
    """I paragrafi del prompt, separati dalle righe bianche, con gli a capo come
    spazi: una regola può andare a capo a metà frase."""
    return [" ".join(blocco.split()) for blocco in re.split(r"\n\s*\n", testo) if blocco.strip()]


class TestIlCriticNonChiedeUnRebase:
    """PBI-525, criterio 1: sul giro 1 di `PBI-5` di `ada_nlt` il Critic ha dato
    `non pronto` per due rilievi di sola storia dei commit col rimedio «un rebase»,
    che il Builder non può eseguire, e ha consumato due revisioni su quattro. E fra
    un passaggio e l'altro ha riportato un'istanza per volta della stessa classe di
    difetto (un dato utente non valido che torna 500). Il prompt manda i rilievi di
    storia fra le note per chi mergia (decisioni 1 e 4), non nomina il rebase, e
    chiede la classe intera (decisione 5)."""

    def test_un_rilievo_di_sola_storia_va_nelle_note_per_chi_mergia(self, configura):
        configura()

        regole = [p for p in paragrafi(generati()["critic"])
                  if "storia" in p and "Note per chi mergia" in p]

        assert regole, "nessuna regola del Critic manda i rilievi di storia fra le note per chi mergia"

    def test_il_prompt_non_nomina_il_rebase(self, configura):
        configura()

        assert "rebase" not in generati()["critic"]

    def test_un_rilievo_di_correttezza_elenca_la_classe_intera(self, configura):
        configura()

        regole = [p for p in paragrafi(generati()["critic"]) if "classe" in p and "dato" in p]

        assert regole, "il Critic non chiede di elencare la classe intera dei dati utente non validi"
