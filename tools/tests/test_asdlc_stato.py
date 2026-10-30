"""`asdlc-stato`: lo stato dei PBI di ogni progetto, in sola lettura (PBI-534).

Ogni test costruisce un progetto vero in `tmp_path` — un checkout con la sua coda e
un `origin` locale, bare — e sostituisce soltanto `gh`: nessuna rete. `git` è
quello vero, perché il ramo del PBI si legge da `origin` come fa il tick.
"""
import importlib
import json
import subprocess
from pathlib import Path

import pytest

coda = importlib.import_module("asdlc.coda")
stato = importlib.import_module("asdlc.stato")

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"
# Il tick configurato sul progetto di prova, come in `test_asdlc_coda.py`: è lo
# stato in cui ogni test lo trova e lo lascia.
coda.configura(coda.asdlc_config.carica(PROGETTO))

# Il pin dei test: un `installa` URL, perché la firma di una cartella chiede un
# `git rev-parse` dell'albero che qui non c'è (PBI-534, *Contesto*).
PIN = "git+https://github.com/Lara-srl/asdlc@v1.1.0#subdirectory=tools"

# I nomi di modulo che `coda.configura()` riscrive. `asdlc-stato` la chiama per
# ogni progetto, e i test di `test_asdlc_coda.py` contano sul progetto di prova:
# si rimettono com'erano alla fine di ogni test.
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


def progetto(tmp_path, righe_coda, nome="alfa", rami=("pbi/pbi-1",), installa=PIN):
    """Un checkout `tmp_path/<nome>` su `main`, con la coda `righe_coda`, il file
    di PBI-1, e un `origin` bare che ha `main` e i `rami`."""
    origine = tmp_path / f"{nome}.git"
    checkout = tmp_path / nome
    git("init", "-q", "--bare", "-b", "main", str(origine), cwd=tmp_path)
    git("init", "-q", "-b", "main", str(checkout), cwd=tmp_path)
    toml = (PROGETTO / "asdlc.toml").read_text(encoding="utf-8")
    (checkout / "asdlc.toml").write_text(
        toml.replace('installa = "./tools"', f'installa = "{installa}"'), encoding="utf-8")
    # La cartella di `[prompt].aggiunte`, che `carica()` vuole presente; vuota, e
    # quindi fuori dal commit.
    (checkout / "asdlc-aggiunte").mkdir()
    backlog = checkout / "backlog"
    backlog.mkdir()
    (backlog / "CODA.md").write_text(
        "# Coda\n\n" + "".join(f"{riga}\n" for riga in righe_coda), encoding="utf-8")
    (backlog / "PBI-1-prova.md").write_text("# PBI-1: prova\n", encoding="utf-8")
    git("add", ".", cwd=checkout)
    git("commit", "-q", "-m", "la coda", cwd=checkout)
    git("remote", "add", "origin", str(origine), cwd=checkout)
    git("push", "-q", "origin", "main", cwd=checkout)
    for ramo in rami:
        git("push", "-q", "origin", f"main:refs/heads/{ramo}", cwd=checkout)
    git("fetch", "-q", "origin", cwd=checkout)
    return checkout


def decisione_del_tick(checkout):
    coda.configura(coda.asdlc_config.carica(checkout))
    return coda.racconta(coda.decidi(checkout, coda.WORKTREE_DEL_RUNNER))


# --- Criterio 1: la decisione del tick -----------------------------------------


def test_il_comando_mostra_nome_voce_e_decisione_del_tick(tmp_path, capsys):
    checkout = progetto(tmp_path, ["- PBI-1"])

    assert stato.main(["--repo", str(checkout)]) == 0
    riga = capsys.readouterr().out

    attesa = decisione_del_tick(checkout)
    assert attesa.startswith("attende: PBI-1")
    assert "alfa" in riga
    assert "PBI-1" in riga
    assert attesa in riga


def test_con_la_coda_ferma_su_una_barriera_la_riga_porta_la_barriera(tmp_path, capsys):
    checkout = progetto(tmp_path, ["- ‖ il merge della v1.0.0", "- PBI-1"])

    assert stato.main(["--repo", str(checkout)]) == 0
    riga = capsys.readouterr().out

    assert "barriera: il merge della v1.0.0" in riga
    assert riga.startswith("alfa")


# --- Criterio 2: `--json` -------------------------------------------------------

CHIAVI = {"progetto", "decisione", "voce", "esito", "pr", "pausa", "allineato",
          "installato", "pin"}


def json_di(argv, capsys):
    assert stato.main(argv) == 0
    return json.loads(capsys.readouterr().out)


def test_il_json_ha_un_oggetto_con_le_chiavi_fisse(tmp_path, capsys):
    checkout = progetto(tmp_path, ["- PBI-1"])

    [oggetto] = json_di(["--repo", str(checkout), "--json"], capsys)

    assert set(oggetto) == CHIAVI
    assert oggetto["progetto"] == "alfa"
    assert oggetto["voce"] == "PBI-1"
    assert oggetto["decisione"] == decisione_del_tick(checkout)
    assert oggetto["esito"] is None
    assert oggetto["pr"] == []


def rapporto(tmp_path, esito, run="20261030-120000"):
    """Un rapporto del runner nel worktree del progetto di prova, `../progetto-run`."""
    registro = tmp_path / "progetto-run" / "runs"
    registro.mkdir(parents=True, exist_ok=True)
    (registro / f"{run}.json").write_text(
        json.dumps({"run": run, "esiti": [{"pbi": "PBI-1", **esito}]}), encoding="utf-8")


PR_APERTA = json.dumps([{"url": "https://github.com/Lara-srl/alfa/pull/7",
                         "headRefName": "pbi/pbi-1"}])


def test_l_ultimo_esito_e_la_pr_aperta_stanno_nella_riga_e_nel_json(
    tmp_path, capsys, gh_finto
):
    checkout = progetto(tmp_path, ["- PBI-1"])
    rapporto(tmp_path, {"stato": "fermato", "motivo": "non-convergente"})
    gh_finto["open"] = (0, PR_APERTA)

    assert stato.main(["--repo", str(checkout)]) == 0
    riga = capsys.readouterr().out
    [oggetto] = json_di(["--repo", str(checkout), "--json"], capsys)

    assert " · fermato non-convergente · " in riga
    assert " · PR https://github.com/Lara-srl/alfa/pull/7" in riga
    assert oggetto["esito"] == {"stato": "fermato", "motivo": "non-convergente"}
    assert oggetto["pr"] == ["https://github.com/Lara-srl/alfa/pull/7"]


def test_senza_esito_e_senza_pr_la_riga_porta_dei_trattini(tmp_path, capsys):
    checkout = progetto(tmp_path, ["- PBI-1"])

    assert stato.main(["--repo", str(checkout)]) == 0
    riga = capsys.readouterr().out

    assert " · PBI-1 · - · PR - " in riga.rstrip("\n") + " "


def test_un_gh_muto_sulle_pr_aperte_e_un_punto_di_domanda(tmp_path, capsys, gh_finto):
    checkout = progetto(tmp_path, ["- PBI-1"])
    gh_finto["open"] = (1, "gh: non autenticato")

    assert stato.main(["--repo", str(checkout)]) == 0
    riga = capsys.readouterr().out
    [oggetto] = json_di(["--repo", str(checkout), "--json"], capsys)

    assert " · PR ? " in riga.rstrip("\n") + " "
    assert oggetto["pr"] is None
