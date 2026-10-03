"""I test del runner ASDLC stanno in `tools/tests/`, fuori dall'applicazione
(`backlog/PBI-360`).

Due cose che il trasloco deve rendere vere, e che nessun altro test guarda:

- **Il gate `asdlc` gira la suite.** Il gate `pytest` lancia
  `cd backend && pytest -q`: appena i test escono da lì, smette di eseguirli. Se
  `asdlc.toml` non li riprende con un gate suo, il giro si certifica verde su una
  suite che non gira più. Lo si prova sul progetto di prova (PBI-394), che ha
  quel gate solo.
- **Nessuna connessione a un database.** `backend/tests/conftest.py` monta uno
  SQLite in memoria per ogni test, `autouse`; i test del runner non toccano un
  database e fuori da lì non devono pagarlo. La sonda li gira in un processo suo,
  con `sqlite3.dbapi2.connect` contato: è la porta da cui passa quella fixture —
  SQLAlchemy apre SQLite da `dbapi2`, non da `sqlite3.connect`.

Il runner si carica dal suo percorso in `tools/asdlc/` con un nome suo, e non
per nome come negli altri file di questa cartella: vedi sotto.
"""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUI = Path(__file__).resolve()
# Il progetto di prova dei test del runner (PBI-394, decisione 1).
PROGETTO = QUI.parent / "dati" / "progetto"

# Un nome suo in `sys.modules`: `test_asdlc_runner.py` registra il runner come
# `asdlc.runner` e lo riconfigura nei suoi test, e questo modulo non glielo tocca.
_spec = importlib.util.spec_from_file_location(
    "asdlc_runner_del_gate", REPO / "tools" / "asdlc" / "runner.py"
)
runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner
_spec.loader.exec_module(runner)
# L'import non legge `asdlc.toml` (PBI-382): la configurazione è quella del
# progetto di prova, e non del progetto che ospita questi test (PBI-394).
runner.REPO = PROGETTO
runner.configura(runner.asdlc_config.carica(PROGETTO))


# L'elenco del passo 2.2 di `RUNBOOK-FASE-5.md`: ciò che trasloca nel repository
# `asdlc`. Lo legge `git filter-repo --paths-from-file`, e lo legge la sonda qui
# sotto per costruire la forma di quel repository (PBI-394, decisione 3).
ESTRAZIONE = QUI.parent / "dati" / "estrazione.txt"


def voci_dell_estrazione() -> list[str]:
    """Le righe di `estrazione.txt`, senza commenti né righe vuote."""
    righe = ESTRAZIONE.read_text(encoding="utf-8").splitlines()
    return [r.strip() for r in righe if r.strip() and not r.lstrip().startswith("#")]


def file_dell_estrazione(radice: Path) -> list[Path]:
    """I file sotto `radice` che le voci dell'estrazione prendono, oggi.

    Una voce che finisce in `/` è una cartella, una `glob:` è un modello come
    lo legge `git filter-repo`, le altre sono un file. Un percorso che oggi non
    esiste è storia — il nome di prima di un `git mv` — e non prende niente.
    """
    presi: set[Path] = set()
    for voce in voci_dell_estrazione():
        if voce.startswith("glob:"):
            presi.update(p for p in radice.glob(voce.removeprefix("glob:")) if p.is_file())
        elif (radice / voce).is_dir():
            presi.update(p for p in (radice / voce).rglob("*")
                         if p.is_file() and "__pycache__" not in p.parts)
        elif (radice / voce).is_file():
            presi.add(radice / voce)
    return sorted(presi)


def test_l_estrazione_porta_il_pacchetto_e_i_nomi_di_prima_e_lascia_aggiorna_kb():
    voci = voci_dell_estrazione()
    presi = [p.relative_to(REPO).as_posix() for p in file_dell_estrazione(REPO)]

    assert "tools/asdlc/" in voci
    assert "tools/asdlc_runner.py" in voci, "il nome di prima del `git mv` di PBI-383"
    assert "backend/tests/test_asdlc_runner.py" in voci, "il nome di prima di PBI-360"
    assert "tools/asdlc/runner.py" in presi
    assert "tools/tests/test_asdlc_runner.py" in presi
    assert "tools/tests/test_aggiorna_kb.py" not in voci
    assert "tools/tests/test_aggiorna_kb.py" not in presi, "aggiorna_kb.py resta in aDa (D8)"


def test_gira_gate_esegue_la_suite_asdlc_del_progetto_di_prova(monkeypatch):
    chiamati: list[tuple[list[str], Path]] = []
    monkeypatch.setattr(
        runner, "esegui",
        lambda cmd, cwd, timeout=0: chiamati.append((list(cmd), Path(cwd))) or (0, ""),
    )

    assert runner.gira_gate(set()) == []

    assert chiamati == [(["python3", "-m", "pytest", "-q", "tools/tests"], PROGETTO / ".")]


# Il processo figlio conta le connessioni SQLite intorno a un `pytest`
# di questa cartella, e le stampa **dopo** che pytest ha finito: la riga è sua,
# non si confonde con l'output dei test.
SONDA = """
import sqlite3, sqlite3.dbapi2, sys
import pytest

aperte = []
_connect = sqlite3.dbapi2.connect

def _contata(*a, **k):
    aperte.append(a[:1])
    return _connect(*a, **k)

sqlite3.connect = sqlite3.dbapi2.connect = _contata
esito = pytest.main(sys.argv[1:])
print(f"CONNESSIONI APERTE: {len(aperte)}")
sys.exit(esito)
"""


# Ciò che il commit di nascita del passo 2.3 aggiunge alla radice del repository
# `asdlc`, oltre ai percorsi dell'estrazione: l'hook di fase e le sue impostazioni,
# e il progetto di prova come progetto della radice (PBI-394, decisione 4).
DELL_OSPITE = (".claude/hooks/fase-tdd.sh", ".claude/settings.json")
DEL_PROGETTO_DI_PROVA = ("asdlc.toml", "asdlc-aggiunte", "backlog/CODA.md")


def forma_del_repository_asdlc(cartella: Path) -> Path:
    """Una cartella con i soli file che traslocano, e nessun altro file di aDa.

    Fuori da un repository git, in una cartella temporanea: i test che ci girano
    non possono trovare né il checkout di aDa né i suoi file per la strada.
    """
    for file in file_dell_estrazione(REPO):
        copia = cartella / file.relative_to(REPO)
        copia.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, copia)
    for relativo in DELL_OSPITE:
        (cartella / relativo).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / relativo, cartella / relativo)
    for relativo in DEL_PROGETTO_DI_PROVA:
        if (PROGETTO / relativo).is_dir():
            shutil.copytree(PROGETTO / relativo, cartella / relativo)
        else:
            (cartella / relativo).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROGETTO / relativo, cartella / relativo)
    return cartella


def test_i_test_di_tools_tests_non_aprono_connessioni_a_un_database(tmp_path):
    """La suite gira **nella forma del repository `asdlc`**, non dalla radice di
    aDa: è il controllo del passo 0.2 del runbook, e si rifà identico al 2.5.

    Un sottoprocesso solo, che conta anche le connessioni: la suite gira già due
    volte a ogni gate, e una terza costerebbe un altro mezzo minuto a ogni gate
    di ogni giro (PBI-394, decisione 4)."""
    forma = forma_del_repository_asdlc(tmp_path / "asdlc")
    fatto = subprocess.run(
        [sys.executable, "-c", SONDA, "-q", "-p", "no:cacheprovider",
         "tools/tests", "-k", "not non_aprono_connessioni"],
        cwd=forma, capture_output=True, text=True, timeout=600,
    )
    uscita = fatto.stdout + fatto.stderr

    assert "CONNESSIONI APERTE: 0" in uscita, uscita[-3000:]
    assert fatto.returncode == 0, uscita[-3000:]
    assert " passed" in uscita, uscita[-3000:]
