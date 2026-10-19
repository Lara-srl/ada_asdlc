"""Il ruolo Solver nel server dell'esito (`backlog/PBI-507`, `ADR-0030`, R1-R3).

Il Solver è il terzo ruolo accanto a Builder e Critic: smista un giro fermato con uno
di tre strumenti, che il server dell'esito valida (`ADR-0027`).
"""

import importlib
import json
import tomllib
from pathlib import Path

import pytest
from test_asdlc_runner import agente_finto, fermati, git_del_senza_esito, ruolo_ed_esito

esito = importlib.import_module("asdlc.esito")
config = importlib.import_module("asdlc.config")

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"

runner = importlib.import_module("asdlc.runner")
runner.REPO = PROGETTO
runner.configura(runner.asdlc_config.carica(PROGETTO))

STRUMENTI_DEL_SOLVER = {"risolvi", "segnala_limite_runner", "chiedi_a_francesco"}


def nomi(ruolo):
    return {s["name"] for s in esito.strumenti(ruolo)}


def test_il_solver_ha_i_suoi_tre_strumenti_e_gli_altri_ruoli_no():
    """R1: gli strumenti del Solver sono suoi e di nessun altro ruolo."""
    assert STRUMENTI_DEL_SOLVER <= nomi("solver")
    assert not STRUMENTI_DEL_SOLVER & nomi("builder")
    assert not STRUMENTI_DEL_SOLVER & nomi("critic")


def test_risolvi_rifiuta_un_evidenza_che_non_esiste_e_accetta_un_file_dell_albero(tmp_path, monkeypatch):
    """R2: `evidenza` nomina un file dell'albero, con un eventuale `:riga`."""
    monkeypatch.chdir(tmp_path)  # l'albero del giro è la cartella da cui parte il server
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "spec.md").write_text("x\n", encoding="utf-8")
    cartella = tmp_path / "esito"
    cartella.mkdir()

    rifiutata = esito.chiama("risolvi", {"risposta": "perché sì", "evidenza": "specs/non-c-e.md"},
                             "solver", str(cartella / "a.json"))
    assert rifiutata["isError"]
    assert not (cartella / "a.json").exists()

    accettata = esito.chiama("risolvi", {"risposta": "perché sì", "evidenza": "specs/spec.md:3"},
                             "solver", str(cartella / "b.json"))
    assert not accettata["isError"], accettata
    assert (cartella / "b.json").exists()


def albero_con_un_commit(tmp_path, monkeypatch):
    """Un repository git con un commit, e la cartella d'esito: l'albero del giro."""
    import subprocess
    monkeypatch.chdir(tmp_path)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["init", "-q"], check=True)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(git + ["add", "a.txt"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "uno"], check=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True,
                         text=True).stdout.strip()
    cartella = tmp_path / "esito"
    cartella.mkdir()
    return sha, cartella


def test_segnala_limite_runner_con_una_causa_in_elenco_registra_il_limite(tmp_path, monkeypatch):
    """R3: causa dell'elenco `runner-*`, comando e output pieni, commit esistente."""
    sha, cartella = albero_con_un_commit(tmp_path, monkeypatch)
    monkeypatch.setenv("ASDLC_CAUSE", "runner-non-legge-junit,runner-altro")
    monkeypatch.setenv("ASDLC_CLONE", str(tmp_path))

    risposta = esito.chiama(
        "segnala_limite_runner",
        {"causa": "runner-non-legge-junit", "comando": "pytest -q", "output": "0 test",
         "commit": sha, "pbi": "# PBI-9: x\n"}, "solver", str(cartella / "a.json"))

    assert not risposta["isError"], risposta
    registrato = json.loads((cartella / "a.json").read_text(encoding="utf-8"))
    assert registrato["esito"] == "limite-del-runner"
    assert registrato["causa"] == "runner-non-legge-junit"


def test_segnala_limite_runner_rifiuta_causa_fuori_elenco_comando_o_output_vuoti_commit_sconosciuto(
        tmp_path, monkeypatch):
    """R3: quattro rifiuti, e nessun esito scritto."""
    sha, cartella = albero_con_un_commit(tmp_path, monkeypatch)
    monkeypatch.setenv("ASDLC_CAUSE", "runner-non-legge-junit")
    monkeypatch.setenv("ASDLC_CLONE", str(tmp_path))
    valido = {"causa": "runner-non-legge-junit", "comando": "pytest -q", "output": "0 test",
              "commit": sha, "pbi": "# PBI-9: x\n"}
    guasti = [
        {"causa": "runner-inventata"},
        {"comando": "  "},
        {"output": ""},
        {"commit": "0123456789abcdef0123456789abcdef01234567"},
    ]
    for numero, guasto in enumerate(guasti):
        file = cartella / f"{numero}.json"
        risposta = esito.chiama("segnala_limite_runner", {**valido, **guasto}, "solver", str(file))
        assert risposta["isError"], guasto
        assert not file.exists(), guasto


def test_la_prima_chiamata_valida_del_solver_e_definitiva(tmp_path, monkeypatch):
    """`ADR-0027`: una seconda chiamata dopo un esito valido non cambia l'esito."""
    sha, cartella = albero_con_un_commit(tmp_path, monkeypatch)
    monkeypatch.setenv("ASDLC_CAUSE", "runner-non-legge-junit")
    monkeypatch.setenv("ASDLC_CLONE", str(tmp_path))
    file = cartella / "a.json"

    prima = esito.chiama("risolvi", {"risposta": "perché sì", "evidenza": "a.txt"},
                         "solver", str(file))
    assert not prima["isError"], prima
    dopo = file.read_text(encoding="utf-8")

    for nome, argomenti in (
        ("risolvi", {"risposta": "altro", "evidenza": "a.txt"}),
        ("segnala_limite_runner", {"causa": "runner-non-legge-junit", "comando": "x",
                                   "output": "y", "commit": sha, "pbi": "# PBI-9: x\n"}),
    ):
        seconda = esito.chiama(nome, argomenti, "solver", str(file))
        assert seconda["isError"], nome
        assert file.read_text(encoding="utf-8") == dopo, nome


def configurazione(sezione_solver: str = ""):
    """La configurazione del progetto di prova con sopra la sezione `[solver]` data."""
    testo = (PROGETTO / "asdlc.toml").read_text(encoding="utf-8") + "\n" + sezione_solver
    return config.interpreta(tomllib.loads(testo), "asdlc.toml")


def test_la_sezione_solver_ha_i_default_3_nessuna_causa_e_opus():
    """Decisioni 8 e 12: `giri_massimi` 3, `cause` vuota, `modello` opus."""
    solver = configurazione().solver

    assert (solver.giri_massimi, solver.cause, solver.modello) == (3, (), "opus")


def test_la_sezione_solver_si_legge_dal_toml():
    solver = configurazione('[solver]\ngiri_massimi = 5\ncause = ["runner-a", "runner-b"]\n'
                            'modello = "sonnet"\n').solver

    assert (solver.giri_massimi, solver.cause, solver.modello) == (
        5, ("runner-a", "runner-b"), "sonnet")


def ruolo_del(comando):
    return ruolo_ed_esito(comando)[0]


@pytest.fixture
def giro_fermato(monkeypatch, tmp_path):
    """Un `esegui_pbi` il cui Builder si ferma con una domanda: `LOG_DIR` e `git` finti,
    l'agente lo sceglie il test."""
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
    monkeypatch.setattr(runner, "git", git_del_senza_esito)

    def lancia(esiti, testo=""):
        agente = agente_finto({"builder": fermati("che faccio?"), **esiti}, testo)
        monkeypatch.setattr(runner, "esegui", agente)
        return runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False), agente

    return lancia


def test_un_solver_senza_chiamate_chiude_senza_esito_con_l_uscita_grezza(giro_fermato):
    """R1: dopo il `fermati` del Builder il Solver parte; se non chiama niente,
    l'esito del suo giro è `senza esito` e porta l'uscita com'è."""
    esito, agente = giro_fermato({}, {"solver": "non so che dire"})

    assert any("--model" in c and c[c.index("--model") + 1] == "opus"
               and "mcp__asdlc__risolvi" in " ".join(c) for c in agente.comandi), (
        "il Solver è un terzo invocato con i suoi tre strumenti")
    assert [(s["esito"], s["uscita"]) for s in esito.solver] == [
        ("senza esito", "non so che dire")]


def test_il_server_del_solver_riceve_le_cause_del_progetto_in_asdlc_cause(monkeypatch, tmp_path):
    """Decisione 8: le cause `runner-*` viaggiano da `[solver].cause` alla variabile
    `ASDLC_CAUSE`, separate da virgola; nessuna lettura di rete."""
    import dataclasses
    monkeypatch.setattr(runner, "PACCHETTO", tmp_path)
    monkeypatch.setattr(runner, "CFG", dataclasses.replace(
        runner.CFG, solver=config.Solver(cause=("runner-a", "runner-b"))))

    percorso = runner.config_del_server("solver", tmp_path / "esito.json")

    ambiente = json.loads(percorso.read_text(encoding="utf-8"))["mcpServers"]["asdlc"]["env"]
    assert ambiente["ASDLC_RUOLO"] == "solver"
    assert ambiente["ASDLC_CAUSE"] == "runner-a,runner-b"


def test_chiedi_a_francesco_registra_l_esito_intento_con_la_domanda(tmp_path):
    """Decisione 1: `chiedi_a_francesco(domanda)` è l'esito `intento`."""
    risposta = esito.chiama("chiedi_a_francesco", {"domanda": "quale dei due?"}, "solver",
                            str(tmp_path / "a.json"))

    assert not risposta["isError"], risposta
    assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8")) == {
        "esito": "intento", "domanda": "quale dei due?"}


@pytest.mark.parametrize("nome", ["chiedi_a_francesco", "segnala_limite_runner", "risolvi"])
@pytest.mark.parametrize("argomenti", [None, [], "testo", {"domanda": "  "}, {"domanda": 3}])
def test_gli_strumenti_del_solver_rifiutano_argomenti_che_non_reggono(tmp_path, nome, argomenti):
    """Un rifiuto torna al Solver come errore dello strumento (decisione 2): mai
    un'eccezione, e mai un esito scritto."""
    risposta = esito.chiama(nome, argomenti, "solver", str(tmp_path / "a.json"))

    assert risposta["isError"]
    assert not (tmp_path / "a.json").exists()


def rapporto_precedente(cartella, giri, pbi="PBI-102"):
    """Il rapporto di un giro di prima, con `giri` giri Solver già contati."""
    (cartella / "20261015-100000.json").write_text(json.dumps(
        {"run": "20261015-100000", "stato": "finito",
         "esiti": [{"pbi": pbi, "giri_solver": giri}]}), encoding="utf-8")


def test_il_contatore_dei_giri_solver_si_rilegge_dal_rapporto_e_cresce_di_uno(giro_fermato,
                                                                              tmp_path):
    """Decisione 10: un intero per PBI nel rapporto, riletto dal giro dopo."""
    rapporto_precedente(tmp_path, 2)

    esito, agente = giro_fermato({}, {"solver": "boh"})

    assert esito.giri_solver == 3
    assert len(esito.solver) == 1


def test_il_primo_giro_del_solver_conta_uno(giro_fermato):
    esito, _ = giro_fermato({}, {"solver": "boh"})

    assert esito.giri_solver == 1


def test_il_quarto_giro_del_solver_non_parte_e_la_nota_lo_avvisa(giro_fermato, tmp_path):
    """R12 (`ADR-0008`): avviso e non blocco. Con `giri_massimi = 3` e tre giri già
    nel rapporto, il Solver non si lancia e il contatore resta com'è."""
    rapporto_precedente(tmp_path, 3)

    esito, agente = giro_fermato({}, {"solver": "boh"})

    assert not any(ruolo_del(c) == "solver" for c in agente.comandi)
    assert esito.solver == []
    assert esito.giri_solver == 3
    assert "tetto dei giri del Solver" in esito.nota


def test_chiedi_a_francesco_ferma_il_giro_con_un_avviso_che_porta_la_domanda(giro_fermato):
    """R12: la domanda del Solver a Francesco chiude il giro con un avviso nella nota,
    non con un blocco (`ADR-0008`); l'esito `intento` resta registrato."""
    intento = {"esito": "intento", "domanda": "quale dei due lo scope?"}

    esito, _ = giro_fermato({"solver": intento})

    assert esito.solver == [intento]
    assert "avviso: il Solver chiede a Francesco: quale dei due lo scope?" in esito.nota


def test_il_prompt_del_solver_legge_il_toml_e_i_precedenti_prima_di_segnalare_e_di_chiedere():
    """R4 e R12: l'ordine degli esiti è `risolvi`, `segnala_limite_runner`,
    `chiedi_a_francesco` (voci numerate); `asdlc.toml` si legge prima del limite del
    runner e `backlog/PRECEDENTI.md` prima di chiedere a Francesco."""
    import re
    testo = runner.prompt_del_pacchetto("solver")

    voci = [(m.group(1), m.start()) for m in re.finditer(
        r"^\d\. `(risolvi|segnala_limite_runner|chiedi_a_francesco)`", testo, re.MULTILINE)]
    assert [nome for nome, _ in voci] == ["risolvi", "segnala_limite_runner",
                                          "chiedi_a_francesco"]
    posizione = dict(voci)
    assert 0 <= testo.find("asdlc.toml") < posizione["segnala_limite_runner"]
    assert 0 <= testo.find("backlog/PRECEDENTI.md") < posizione["chiedi_a_francesco"]


@pytest.mark.parametrize("nome,argomenti", [("fatto", {"riepilogo": "x"}),
                                            ("fermati", {"domanda": "che faccio?"}),
                                            ("sconosciuto", {})])
def test_il_solver_non_scrive_esiti_fuori_dai_suoi_tre(tmp_path, nome, argomenti):
    """R1 / `ADR-0027`: le regole le applica il server, non la CLI. `fatto` e `fermati` sono
    del Builder e del Critic; il Solver che li chiama riceve un errore che nomina i suoi tre."""
    risposta = esito.chiama(nome, argomenti, "solver", str(tmp_path / "a.json"))

    assert risposta["isError"]
    assert all(s in risposta["content"][0]["text"] for s in STRUMENTI_DEL_SOLVER)
    assert not (tmp_path / "a.json").exists()


def test_un_guasto_del_solver_non_salta_la_chiusura_del_giro(giro_fermato, monkeypatch):
    """Il Solver è invocato e registrato, non seguito (decisione 11): se `esegui` solleva per il
    suo ruolo, il giro fermato si chiude lo stesso, con lo stato del blocco e un avviso."""
    interno = agente_finto({"builder": fermati("che faccio?")})

    def guasto(cmd, cwd, timeout=7200, **k):
        if ruolo_del(cmd) == "solver":
            raise RuntimeError("disco pieno")
        return interno(cmd, cwd, timeout, **k)

    monkeypatch.setattr(runner, "git", git_del_senza_esito)
    monkeypatch.setattr(runner, "esegui", guasto)

    esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

    assert esito.stato == "fermato"
    assert "avviso: il Solver è fallito: RuntimeError: disco pieno" in esito.nota
    assert esito.solver == []
    assert esito.file_traceback


@pytest.mark.parametrize("evidenza", ["{fuori}", "../fuori.md", "specs/../../fuori.md:2"])
def test_risolvi_rifiuta_un_evidenza_fuori_dall_albero(tmp_path, monkeypatch, evidenza):
    """R2 e decisione 3: l'evidenza è un percorso relativo alla radice del progetto. Un
    assoluto o un `../` che esce dall'albero esiste, ma non è una fonte del repository."""
    albero = tmp_path / "albero"
    (albero / "specs").mkdir(parents=True)
    (tmp_path / "fuori.md").write_text("x\n", encoding="utf-8")
    monkeypatch.chdir(albero)

    risposta = esito.chiama(
        "risolvi", {"risposta": "perché sì", "evidenza": evidenza.format(fuori=tmp_path / "fuori.md")},
        "solver", str(tmp_path / "a.json"))

    assert risposta["isError"]
    assert not (tmp_path / "a.json").exists()


def test_l_invocazione_del_solver_entra_nelle_invocazioni_del_rapporto(giro_fermato):
    """Una voce per invocazione di un agente, nell'ordine: anche il Solver, e anche quando
    chiude `senza esito`, perché lì le sue chiamate e il suo stderr si ritrovano dal rapporto."""
    esito, _ = giro_fermato({}, {"solver": "boh"})

    assert [i["ruolo"] for i in esito.invocazioni] == ["builder", "solver"]
    assert esito.invocazioni[-1]["codice"] == 0
