"""Il progetto è la cartella di lavoro, non la cartella del codice (PBI-382).

Installato, il runner sta in site-packages (`ADR-0026`, decisione 3), e
`Path(__file__).parent.parent` non è più il repository. Qui il codice si copia
in una cartella temporanea **senza** `asdlc.toml` e si lancia da un'altra: se
leggesse il progetto da dove sta il suo sorgente, lo si vedrebbe.

I moduli si lanciano in un processo figlio, e non con `importlib` come negli
altri test: la cwd e l'import sono proprio ciò che si prova, e cambiarli nel
processo di pytest li cambierebbe a tutta la suite.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Il progetto di prova (PBI-394, decisione 1): il suo `asdlc.toml` e le sue
# aggiunte, al posto di quelli del progetto che ospita questi test.
PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"


def copia_il_pacchetto(tools: Path) -> None:
    """Il pacchetto `asdlc` in `tools/asdlc/`, com'è nel repository (PBI-383)."""
    shutil.copytree(REPO / "tools" / "asdlc", tools / "asdlc",
                    ignore=shutil.ignore_patterns("__pycache__"))


def copia_il_codice(tmp_path: Path) -> Path:
    """Il pacchetto in `<tmp>/codice/tools`, lontano da ogni `asdlc.toml`."""
    tools = tmp_path / "codice" / "tools"
    tools.mkdir(parents=True)
    copia_il_pacchetto(tools)
    return tools


def test_importare_runner_e_tick_non_legge_asdlc_toml(tmp_path):
    """Un modulo importato con la cwd in una cartella qualsiasi non fallisce: la
    configurazione si legge quando si lancia, non quando si importa."""
    tools = copia_il_codice(tmp_path)
    vuota = tmp_path / "vuota"
    vuota.mkdir()

    fatto = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(tools)!r}); import asdlc.runner, asdlc.coda"],
        cwd=vuota, capture_output=True, text=True, timeout=60,
    )

    assert fatto.returncode == 0, fatto.stderr


def tutti_i_file(cartella: Path) -> set[Path]:
    return {p.relative_to(cartella) for p in cartella.rglob("*")}


def lancia(tools: Path, modulo: str, argomenti: list[str], cwd: Path):
    """`-B`: il `__pycache__` accanto al codice copiato non è una scrittura del
    runner, e renderebbe cieco il confronto dei file."""
    return subprocess.run([sys.executable, "-B", str(tools / modulo), *argomenti],
                          cwd=cwd, capture_output=True, text=True, timeout=60)


def test_runner_e_tick_senza_asdlc_toml_dalla_cwd_in_su_escono_col_motivo(tmp_path):
    """Il messaggio nomina la cwd, e prima non c'è nient'altro: né il lucchetto sotto
    `runs/`, né un worktree, né il rapporto del giro."""
    tools = copia_il_codice(tmp_path)
    vuota = tmp_path / "vuota"
    vuota.mkdir()
    prima = tutti_i_file(tmp_path)

    for modulo, argomenti in (("asdlc/runner.py", ["PBI-1", "--in-primo-piano"]),
                              ("asdlc/coda.py", ["--dry-run"])):
        fatto = lancia(tools, modulo, argomenti, vuota)

        assert fatto.returncode != 0, modulo
        assert (f"nessun `asdlc.toml` da `{vuota}` in su: il runner si lancia dalla "
                "cartella di un progetto ASDLC") in fatto.stderr, (modulo, fatto.stderr)
        assert tutti_i_file(tmp_path) - prima == set(), modulo


def un_progetto(tmp_path: Path) -> Path:
    """Un progetto ASDLC con valori che non sono quelli di aDa, e la cartella
    del runner che è la radice stessa: il tick lo rifiuta nominando `--repo`."""
    progetto = tmp_path / "progetto"
    (progetto / "src" / "moduli").mkdir(parents=True)
    (progetto / "asdlc.toml").write_text(f"""\
[git]
base = "origin/master"
prefisso_ramo = "us/us-"

[backlog]
cartella = "storie"
coda = "storie/CODA.md"
id = "US-{{n}}"
file = "US-{{n}}-{{slug}}.md"

[registro]
cartella = "giri"
tempi = "ore.csv"

[ambiente]
venv = ".venv"
prestiti = []
pacchetto = ".venv-asdlc"
installa = "./tools"

[worktree]
percorso = "."

[soglie]
tentativi = 2
igiene = 5
revisioni = 7

[gate_del_rosso]
attivo = true

[[gate]]
nome = "pytest"
comando = ["pytest", "-q"]
""", encoding="utf-8")
    return progetto


def test_il_runner_lanciato_da_una_sottocartella_lavora_sul_progetto_della_cwd(tmp_path):
    """Il codice sta in `codice/`, che un `asdlc.toml` non ce l'ha: i tempi che
    il riepilogo cerca sono quelli di `progetto/giri/ore.csv`.

    Il codice d'uscita non si guarda: senza `ore.csv` il riepilogo esce 1 da
    prima di PBI-382, che non lo cambia (decisione 5). La prova è il percorso
    nel messaggio."""
    tools = copia_il_codice(tmp_path)
    progetto = un_progetto(tmp_path)

    fatto = lancia(tools, "asdlc/runner.py", ["--riepilogo"], progetto / "src" / "moduli")

    assert "Nessun tempo registrato: giri/ore.csv non esiste ancora." in fatto.stdout, (
        fatto.stderr)


def test_il_tick_lanciato_da_una_sottocartella_lavora_sul_progetto_della_cwd(tmp_path):
    """Il checkout del tick è la radice trovata dalla cwd: qui coincide con il
    worktree del TOML, e il tick si rifiuta nominandola."""
    tools = copia_il_codice(tmp_path)
    progetto = un_progetto(tmp_path)

    fatto = lancia(tools, "asdlc/coda.py", ["--dry-run"], progetto / "src" / "moduli")

    assert fatto.returncode == 2, fatto.stderr
    assert f"--repo e --worktree sono lo stesso albero ({progetto})" in fatto.stdout


# --- Guardie: con il codice dentro il progetto decidono come prima (PBI-382) --


def un_progetto_come_ada(tmp_path: Path) -> Path:
    """La forma di aDa oggi: il codice in `<progetto>/tools/asdlc`, l'hook in
    `.claude/hooks/`, l'`asdlc.toml` versionato alla radice, e un giro in
    `TEST_ONLY`. Prima di PBI-382 il progetto lo diceva `__file__`, ora la cwd:
    qui coincidono, e le guardie devono decidere uguale."""
    progetto = tmp_path / "progetto"
    tools = progetto / "tools"
    tools.mkdir(parents=True)
    copia_il_pacchetto(tools)
    shutil.copy(PROGETTO / "asdlc.toml", progetto / "asdlc.toml")
    # La cartella delle aggiunte ai prompt che `asdlc.toml` dichiara (PBI-386):
    # senza, il caricamento si ferma.
    shutil.copytree(PROGETTO / "asdlc-aggiunte", progetto / "asdlc-aggiunte")
    hooks = progetto / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    shutil.copy(REPO / ".claude" / "hooks" / "fase-tdd.sh", hooks / "fase-tdd.sh")
    subprocess.run(["git", "init", "-q"], cwd=progetto, check=True)
    fase = subprocess.run(["git", "rev-parse", "--git-path", "asdlc-fase"], cwd=progetto,
                          capture_output=True, text=True, check=True).stdout.strip()
    (progetto / fase).write_text("TEST_ONLY\n", encoding="utf-8")
    return progetto


def test_guardia_la_guardia_di_fase_dall_hook_lanciato_altrove_decide_come_prima(tmp_path):
    """L'hook `PreToolUse` lanciato da una cwd fuori dal progetto: in
    `TEST_ONLY` ferma la produzione con `2` e lascia passare il test con `0`."""
    progetto = un_progetto_come_ada(tmp_path)
    altrove = tmp_path / "altrove"
    altrove.mkdir()
    hook = progetto / ".claude" / "hooks" / "fase-tdd.sh"

    def chiedi(file_path: str):
        dato = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(progetto),
                "tool_input": {"file_path": str(progetto / file_path)}}
        return subprocess.run([str(hook)], input=json.dumps(dato), cwd=altrove,
                              capture_output=True, text=True, timeout=60,
                              # Fuori da un giro: con `ASDLC_GIRO`, che la sessione
                              # del Builder ha, lo script esce subito (PBI-384).
                              env={**{k: v for k, v in os.environ.items()
                                      if k != "ASDLC_GIRO"},
                                   "PYTHONDONTWRITEBYTECODE": "1"})

    produzione = chiedi("backend/app/foglio.py")
    test = chiedi("backend/tests/test_foglio.py")

    assert produzione.returncode == 2, produzione.stderr
    assert "TEST_ONLY" in produzione.stderr
    assert test.returncode == 0, test.stderr
    assert test.stderr == ""


def test_guardia_la_guardia_del_commit_dalla_radice_decide_come_prima(tmp_path):
    """Il `pre-commit` parte dalla radice dell'albero: in `TEST_ONLY` rifiuta lo
    stage con la produzione, nominandola, e accetta quello di soli test."""
    progetto = un_progetto_come_ada(tmp_path)

    def in_stage(percorso: str):
        (progetto / percorso).parent.mkdir(parents=True, exist_ok=True)
        (progetto / percorso).write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", percorso], cwd=progetto, check=True)
        return lancia(progetto / "tools", "asdlc/runner.py", ["--guardia-commit"], progetto)

    solo_test = in_stage("backend/tests/test_foglio.py")
    con_produzione = in_stage("backend/app/foglio.py")

    assert solo_test.returncode == 0, solo_test.stdout + solo_test.stderr
    assert con_produzione.returncode == 1, con_produzione.stderr
    assert "backend/app/foglio.py" in con_produzione.stdout
