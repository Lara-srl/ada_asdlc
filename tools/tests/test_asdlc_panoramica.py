"""`asdlc-panoramica`: i PBI di ogni progetto in markdown, in sola lettura (PBI-538).

Come in `test_asdlc_stato.py`, ogni test costruisce un progetto vero in `tmp_path` —
un checkout con la sua coda, i file dei PBI e un `origin` locale, bare — e sostituisce
soltanto `gh`, con un monkeypatch di `coda.esegui`: nessuna rete. Per questo i test
chiamano `panoramica.main()` nello stesso processo, e non in un sottoprocesso.
"""
import importlib
import json
import subprocess
from pathlib import Path

import pytest

coda = importlib.import_module("asdlc.coda")
panoramica = importlib.import_module("asdlc.panoramica")

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"
coda.configura(coda.asdlc_config.carica(PROGETTO))

PIN = "git+https://github.com/Lara-srl/asdlc@v1.1.0#subdirectory=tools"

# I nomi di modulo che `coda.configura()` riscrive: si rimettono com'erano alla
# fine di ogni test, come in `test_asdlc_stato.py`.
NOMI_DELLA_CONFIGURAZIONE = (
    "CFG", "WORKTREE_DEL_RUNNER", "LOG", "LUCCHETTO", "LUCCHETTO_DEL_TICK", "BACKLOG",
    "CODA", "BASE", "REMOTO", "PREFISSO_RAMO", "PACCHETTO", "INSTALLA", "RE_PBI",
    "RE_TITOLO_PR", "RE_RAMO_PR", "RE_RAMO_PBI",
)


@pytest.fixture(autouse=True)
def configurazione_rimessa(monkeypatch):
    for nome in NOMI_DELLA_CONFIGURAZIONE:
        monkeypatch.setattr(coda, nome, getattr(coda, nome))


@pytest.fixture(autouse=True)
def home_finta(tmp_path, monkeypatch):
    """`HOME` in `tmp_path`: la pausa e l'elenco dei progetti di chi lancia i test
    non entrano nei test."""
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    return casa


@pytest.fixture(autouse=True)
def gh_finto(monkeypatch):
    """`gh` risponde «nessuna PR», mergiata o aperta che sia; il resto passa a
    `esegui()` vera. Il test cambia la risposta per stato della PR: `(codice,
    uscita)` sotto `"merged"` o `"open"`."""
    vera = coda.esegui
    risposte = {"merged": (0, "[]"), "open": (0, "[]")}

    def esegui(cmd, cwd):
        if cmd[0] == "gh":
            return risposte[cmd[cmd.index("--state") + 1]]
        return vera(cmd, cwd)

    monkeypatch.setattr(coda, "esegui", esegui)
    return risposte


def git(*argomenti, cwd):
    subprocess.run(["git", "-c", "user.name=prova", "-c", "user.email=prova@esempio.it",
                    *argomenti], cwd=cwd, check=True, capture_output=True)


def progetto(tmp_path, righe_coda, file_pbi, nome="alfa", rami=()):
    """Un checkout `tmp_path/<nome>` su `main`, con la coda `righe_coda`, i file di
    `backlog/` di `file_pbi` (nome → testo), e un `origin` bare che ha `main` e i
    `rami`."""
    origine = tmp_path / f"{nome}.git"
    checkout = tmp_path / nome
    git("init", "-q", "--bare", "-b", "main", str(origine), cwd=tmp_path)
    git("init", "-q", "-b", "main", str(checkout), cwd=tmp_path)
    toml = (PROGETTO / "asdlc.toml").read_text(encoding="utf-8")
    (checkout / "asdlc.toml").write_text(
        toml.replace('installa = "./tools"', f'installa = "{PIN}"'), encoding="utf-8")
    (checkout / "asdlc-aggiunte").mkdir()
    backlog = checkout / "backlog"
    backlog.mkdir()
    (backlog / "CODA.md").write_text(
        "# Coda\n\n" + "".join(f"{riga}\n" for riga in righe_coda), encoding="utf-8")
    for file, testo in file_pbi.items():
        (backlog / file).write_text(testo, encoding="utf-8")
    git("add", ".", cwd=checkout)
    git("commit", "-q", "-m", "la coda", cwd=checkout)
    git("remote", "add", "origin", str(origine), cwd=checkout)
    git("push", "-q", "origin", "main", cwd=checkout)
    for ramo in rami:
        git("push", "-q", "origin", f"main:refs/heads/{ramo}", cwd=checkout)
    git("fetch", "-q", "origin", cwd=checkout)
    return checkout


def sezione(testo, titolo):
    """Le righe non vuote sotto `## <titolo>`, fino all'intestazione seguente."""
    righe = testo.splitlines()
    inizio = righe.index(f"## {titolo}") + 1
    dentro = []
    for riga in righe[inizio:]:
        if riga.startswith("#"):
            break
        if riga.strip():
            dentro.append(riga)
    return dentro


# Il progetto del criterio 1: una voce per sezione, una barriera, e i criteri di
# `PBI-2` contati nella sola `## Verifica`.
CODA_DI_PROVA = ["- PBI-1", "- PBI-2", "- ‖ prova", "- PBI-3", "- PBI-5"]
FILE_DI_PROVA = {
    "PBI-1-uno.md": "# PBI-1: il primo\n\n## Verifica\n\n- [x] fatto\n",
    "PBI-2-due.md": (
        "# PBI-2: il secondo\n\n"
        "## Direttiva\n\n- [ ] una casella fuori dalla verifica\n\n"
        "## Verifica\n\n- [x] uno\n- [ ] due\n- [x] tre\n\n"
        "## Protocollo\n\nniente\n"
    ),
    "PBI-3-tre.md": "# PBI-3: il terzo\n",
    "PBI-4-quattro.md": "# PBI-4: il quarto\n\n## ❓ Domande\n\n- quale?\n",
    "PBI-5-cinque.md": "# PBI-5: il quinto\n",
}
PR_MERGIATA = json.dumps([{"title": "PBI-1: il primo", "headRefName": "pbi/pbi-1",
                           "files": [{"path": "tools/asdlc/x.py"}]}])
URL_PR_5 = "https://github.com/Lara-srl/alfa/pull/9"
PR_APERTA = json.dumps([{"url": URL_PR_5, "headRefName": "pbi/pbi-5"}])


# --- Criterio 1: un progetto, con le quattro sezioni, i criteri e la `❓` -----------


def test_un_progetto_ha_le_quattro_sezioni_coi_criteri_e_la_domanda(
    tmp_path, capsys, gh_finto
):
    checkout = progetto(tmp_path, CODA_DI_PROVA, FILE_DI_PROVA, rami=("pbi/pbi-5",))
    gh_finto["merged"] = (0, PR_MERGIATA)
    gh_finto["open"] = (0, PR_APERTA)

    assert panoramica.main(["--repo", str(checkout)]) == 0
    testo = capsys.readouterr().out

    assert testo.splitlines()[0] == "# alfa"
    fatti = sezione(testo, "Fatti")
    assert fatti == ["- **PBI-1** — il primo · criteri 1/1"]
    in_corso = sezione(testo, "In corso")
    assert in_corso == [f"- **PBI-5** — il quinto · criteri 0/0 · PR {URL_PR_5}"]
    in_coda = sezione(testo, "In coda")
    assert in_coda == [
        "1. **PBI-2** — il secondo · criteri 2/3",
        "- ‖ prova",
        "2. **PBI-3** — il terzo · criteri 0/0",
    ]
    fuori = sezione(testo, "Fuori coda")
    assert fuori == ["- **PBI-4** — il quarto · criteri 0/0 · ❓"]


# --- Criterio 2: tutti i progetti, e uno illeggibile non ferma gli altri ------------


def elenco(casa, *checkout):
    """`~/.config/asdlc/progetti.toml` con i `checkout`, in quest'ordine."""
    cartella = casa / ".config" / "asdlc"
    cartella.mkdir(parents=True, exist_ok=True)
    voci = ", ".join(f'"{percorso}"' for percorso in checkout)
    (cartella / "progetti.toml").write_text(f"checkout = [{voci}]\n", encoding="utf-8")


def test_guardia_tutti_i_progetti_e_uno_illeggibile_non_ferma_gli_altri(
    tmp_path, home_finta, capsys
):
    alfa = progetto(tmp_path, ["- PBI-1"], {"PBI-1-uno.md": "# PBI-1: il primo\n"},
                    nome="alfa")
    beta = progetto(tmp_path, ["- PBI-2"], {"PBI-2-due.md": "# PBI-2: il secondo\n"},
                    nome="beta")
    elenco(home_finta, alfa, tmp_path / "sparito", beta)

    assert panoramica.main([]) == 0
    testo = capsys.readouterr().out

    progetti = [riga for riga in testo.splitlines() if riga.startswith("# ")]
    assert progetti == ["# alfa", "# sparito", "# beta"]
    blocchi = testo.split("\n\n# ")
    assert len(blocchi) == 3
    assert "sparito · non raggiungibile — " in blocchi[1]
    assert "## In coda" not in blocchi[1]
    assert "1. **PBI-1** — il primo · criteri 0/0" in blocchi[0]
    assert "1. **PBI-2** — il secondo · criteri 0/0" in blocchi[2]


# --- Criterio 3: `gh` e `origin` che non rispondono non fermano la panoramica ---------


def test_guardia_gh_muto_sulle_pr_mergiate_lascia_fatti_col_punto_di_domanda(
    tmp_path, capsys, gh_finto
):
    checkout = progetto(tmp_path, CODA_DI_PROVA, FILE_DI_PROVA, rami=("pbi/pbi-5",))
    gh_finto["merged"] = (1, "gh: non autenticato")
    gh_finto["open"] = (0, PR_APERTA)

    assert panoramica.main(["--repo", str(checkout)]) == 0
    testo = capsys.readouterr().out

    [fatti] = sezione(testo, "Fatti")
    assert fatti.startswith("- ? gh non risponde")
    in_coda = sezione(testo, "In coda")
    assert in_coda[0] == "1. **PBI-1** — il primo · criteri 1/1"
    assert sezione(testo, "In corso") == [
        f"- **PBI-5** — il quinto · criteri 0/0 · PR {URL_PR_5}"]


def test_guardia_origin_muto_lascia_in_corso_col_punto_di_domanda(
    tmp_path, capsys, gh_finto, monkeypatch
):
    checkout = progetto(tmp_path, CODA_DI_PROVA, FILE_DI_PROVA, rami=("pbi/pbi-5",))
    gh_finto["merged"] = (0, PR_MERGIATA)
    gh_finto["open"] = (0, PR_APERTA)
    finta = coda.esegui

    def esegui(cmd, cwd):
        if "ls-remote" in cmd:
            return 1, "fatal: impossibile raggiungere origin"
        return finta(cmd, cwd)

    monkeypatch.setattr(coda, "esegui", esegui)

    assert panoramica.main(["--repo", str(checkout)]) == 0
    testo = capsys.readouterr().out

    [in_corso] = sezione(testo, "In corso")
    assert in_corso.startswith("- ? git non parla con")
    assert sezione(testo, "In coda") == [
        "1. **PBI-2** — il secondo · criteri 2/3",
        "- ‖ prova",
        "2. **PBI-3** — il terzo · criteri 0/0",
        "3. **PBI-5** — il quinto · criteri 0/0",
    ]
    assert sezione(testo, "Fatti") == ["- **PBI-1** — il primo · criteri 1/1"]


# --- Non regressione: la sola lettura -----------------------------------------------


def fotografia(checkout, worktree):
    """Ciò che un comando di sola lettura non deve cambiare: lo stato di git del
    checkout, il registro del checkout e quello del worktree del runner, e il log
    del tick."""
    stato_git = subprocess.run(["git", "status", "--porcelain", "--ignored"], cwd=checkout,
                               capture_output=True, text=True, check=True).stdout
    registri = {
        str(file): file.read_bytes()
        for cartella in (checkout / "runs", worktree / "runs") if cartella.exists()
        for file in sorted(cartella.rglob("*")) if file.is_file()
    }
    log = coda.LOG.read_bytes() if coda.LOG.exists() else None
    return stato_git, registri, log


def test_guardia_asdlc_panoramica_non_scrive_nel_checkout_ne_nel_registro(
    tmp_path, capsys, gh_finto
):
    checkout = progetto(tmp_path, CODA_DI_PROVA, FILE_DI_PROVA, rami=("pbi/pbi-5",))
    gh_finto["merged"] = (0, PR_MERGIATA)
    gh_finto["open"] = (0, PR_APERTA)
    registro = tmp_path / "progetto-run" / "runs"
    registro.mkdir(parents=True)
    (registro / "20261030-120000.json").write_text(
        json.dumps({"run": "20261030-120000",
                    "esiti": [{"pbi": "PBI-5", "stato": "fermato", "motivo": "x"}]}),
        encoding="utf-8")
    prima = fotografia(checkout, tmp_path / "progetto-run")

    assert panoramica.main(["--repo", str(checkout)]) == 0
    assert "## Fatti" in capsys.readouterr().out

    assert fotografia(checkout, tmp_path / "progetto-run") == prima


# --- Guardie delle decisioni scritte nel GREEN del criterio 1 -----------------------


def test_guardia_una_sezione_vuota_ha_la_riga_nessuno(tmp_path, capsys):
    checkout = progetto(tmp_path, ["- PBI-1"], {"PBI-1-uno.md": "# PBI-1: il primo\n"})

    assert panoramica.main(["--repo", str(checkout)]) == 0
    testo = capsys.readouterr().out

    assert sezione(testo, "In corso") == ["- nessuno"]
    assert sezione(testo, "In coda") == ["1. **PBI-1** — il primo · criteri 0/0"]
    assert sezione(testo, "Fatti") == ["- nessuno"]
    assert sezione(testo, "Fuori coda") == ["- nessuno"]


def test_guardia_una_voce_di_coda_senza_file_e_file_mancante(tmp_path, capsys):
    checkout = progetto(tmp_path, ["- PBI-1", "- PBI-7"],
                        {"PBI-1-uno.md": "# PBI-1: il primo\n"})

    assert panoramica.main(["--repo", str(checkout)]) == 0
    testo = capsys.readouterr().out

    assert sezione(testo, "In coda") == [
        "1. **PBI-1** — il primo · criteri 0/0",
        "2. **PBI-7** — (file mancante) · criteri 0/0",
    ]
