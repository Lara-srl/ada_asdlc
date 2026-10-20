"""Il limite d'uso non ferma la coda (`backlog/PBI-519`).

Un `senza esito` dovuto al limite d'uso dell'account, con l'ora del reset
leggibile nello stderr della CLI, porta nel rapporto `riprendi_dopo`; il tick
aspetta quell'ora e rilancia il PBI con `--riprendi`, che riparte dalla punta del
ramo pubblicato. Gli agenti e l'orologio sono finti: nessun test lancia `claude`
né aspetta davvero.

Il runner e il tick si caricano per nome, `asdlc.runner` e `asdlc.coda`:
`conftest.py` mette `tools/` sul `sys.path` (PBI-383).
"""

import importlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"

runner = importlib.import_module("asdlc.runner")
# Come in `test_asdlc_runner.py`: la radice e la configurazione sono quelle del
# progetto di prova, e l'import non legge `asdlc.toml` (PBI-382, PBI-394).
runner.REPO = PROGETTO
runner.configura(runner.asdlc_config.carica(PROGETTO))

FATTO = {"esito": "fatto", "riepilogo": "fatto"}
LIMITE = "You've hit your session limit · resets 7:50pm\n"


def elenco_backlog() -> str:
    """Cosa risponde `git ls-tree` sulla base: il runner cerca lì il file del PBI."""
    return "\n".join(f"backlog/{f.name}" for f in sorted((PROGETTO / "backlog").glob("*.md")))


def git_del_senza_esito(*args: str) -> str:
    """Il `git` minimo di un giro che chiude `senza esito`: albero pulito, due commit."""
    if args[:2] == ("rev-list", "--count"):
        return "2"
    if args[:2] == ("ls-tree", "--name-only"):
        return elenco_backlog()
    return ""


def ruolo_ed_esito(cmd: list[str]) -> tuple[str | None, Path | None]:
    """Il ruolo e il file d'esito di un'invocazione, dalla config `--mcp-config`."""
    if "--mcp-config" not in cmd:
        return None, None
    config = json.loads(Path(cmd[cmd.index("--mcp-config") + 1]).read_text(encoding="utf-8"))
    ambiente = config["mcpServers"]["asdlc"]["env"]
    return ambiente["ASDLC_RUOLO"], Path(ambiente["ASDLC_ESITO"])


def agente_che_scrive_i_flussi(esiti: dict, stdout: dict | None = None,
                               stderr: dict | None = None, codice: int = 1):
    """Un `esegui` che fa l'agente come la CLI: scrive stdout e stderr del ruolo nei
    due file di `flussi`, e rende il codice e i due testi concatenati, come
    `runner.esegui`. Per il ruolo scrive nel file d'esito ciò che il server
    scriverebbe dopo una chiamata valida; un ruolo assente non chiama niente."""
    stdout, stderr = stdout or {}, stderr or {}
    comandi: list[list[str]] = []

    def _esegui(cmd, cwd, timeout=7200, flussi=None, **k):
        comandi.append(cmd)
        ruolo, file_esito = ruolo_ed_esito(cmd)
        if file_esito is not None and esiti.get(ruolo) is not None:
            file_esito.write_text(json.dumps(esiti[ruolo]), encoding="utf-8")
        fuori, dentro = stdout.get(ruolo, ""), stderr.get(ruolo, "")
        if flussi is not None:
            flussi[0].write_text(fuori, encoding="utf-8")
            flussi[1].write_text(dentro, encoding="utf-8")
        return codice, fuori + dentro

    _esegui.comandi = comandi
    return _esegui


def giro_col_limite(monkeypatch, tmp_path, agente) -> dict:
    """Un giro di `PBI-102` con `agente`, e la voce del suo esito nel rapporto."""
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
    monkeypatch.setattr(runner, "git", git_del_senza_esito)
    monkeypatch.setattr(runner, "gira_gate", lambda attivi, base=None: [])
    monkeypatch.setattr(runner, "esegui", agente)
    esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)
    assert esito.stato == "senza esito", esito.nota
    return json.loads(runner.chiudi_rapporto("giro", [esito]).read_text(
        encoding="utf-8"))["esiti"][0]


class TestLOraDiRipresa:
    """Criterio 2, decisione 3: la prima occorrenza dell'ora del reset successiva
    all'istante in cui l'uscita è stata scritta, più cinque minuti di margine."""

    def test_letta_prima_del_reset_e_oggi(self):
        scritta = datetime(2026, 10, 16, 17, 45)

        assert runner.ora_di_ripresa("7:50pm", scritta) == datetime(2026, 10, 16, 19, 55)

    def test_letta_dopo_il_reset_e_domani(self):
        scritta = datetime(2026, 10, 16, 21, 0)

        assert runner.ora_di_ripresa("7:50pm", scritta) == datetime(2026, 10, 17, 19, 55)


class TestIlSenzaEsitoDelLimitePortaRiprendiDopo:
    """Criterio 1, decisione 1: un `builder-senza-esito` o un `critic-senza-esito`
    con la frase del limite e l'ora del reset nello stderr della CLI, e codice
    d'uscita ≠ 0, porta nel rapporto `riprendi_dopo`."""

    @pytest.mark.parametrize(
        "esiti, ruolo",
        [
            pytest.param({}, "builder", id="builder"),
            pytest.param({"builder": FATTO}, "critic", id="critic"),
        ],
    )
    def test_il_rapporto_porta_riprendi_dopo(self, monkeypatch, tmp_path, esiti, ruolo):
        voce = giro_col_limite(monkeypatch, tmp_path,
                               agente_che_scrive_i_flussi(esiti, stderr={ruolo: LIMITE}))

        assert voce.get("riprendi_dopo"), (
            f"il rapporto non dice quando riprendere dopo il limite d'uso: {voce.get('nota')}"
        )
        assert datetime.fromisoformat(voce["riprendi_dopo"]) > datetime.now(), (
            "l'ora di ripresa è la prossima occorrenza del reset, nel futuro"
        )

    def test_la_frase_solo_nello_stdout_non_porta_riprendi_dopo(self, monkeypatch, tmp_path):
        """Lo stdout è testo del modello (`ADR-0027`): un agente che cita la frase
        senza chiamare lo strumento non fa ripartire il giro."""
        voce = giro_col_limite(monkeypatch, tmp_path,
                               agente_che_scrive_i_flussi({}, stdout={"builder": LIMITE}))

        assert not voce.get("riprendi_dopo"), (
            "la frase del limite si cerca solo nello stderr della CLI"
        )

    def test_la_frase_nello_stderr_con_uscita_zero_non_porta_riprendi_dopo(
        self, monkeypatch, tmp_path
    ):
        """La CLI che esce 0 non si è fermata sul limite: la frase vale solo con un
        codice d'uscita diverso da zero."""
        voce = giro_col_limite(monkeypatch, tmp_path,
                               agente_che_scrive_i_flussi({}, stderr={"builder": LIMITE},
                                                          codice=0))

        assert not voce.get("riprendi_dopo"), (
            "con uscita 0 la frase del limite non fa riprendere il giro"
        )


class TestSenzaOraLeggibileNonSiRiprende:
    """Criterio 3, decisione 2: con la frase del limite ma senza un'ora del reset
    leggibile non c'è `riprendi_dopo`, e la nota lo dichiara. Un'ora inventata è
    peggio di una mancante (`PBI-363`, decisione 4)."""

    @pytest.mark.parametrize(
        "testo",
        [
            pytest.param("You've hit your session limit\n", id="senza-ora"),
            pytest.param("You've hit your session limit · resets soon\n", id="ora-illeggibile"),
        ],
    )
    def test_niente_riprendi_dopo_e_la_nota_lo_dice(self, monkeypatch, tmp_path, testo):
        voce = giro_col_limite(monkeypatch, tmp_path,
                               agente_che_scrive_i_flussi({}, stderr={"builder": testo}))

        assert not voce.get("riprendi_dopo"), "un'ora del reset che non si legge non si inventa"
        assert "limite d'uso dell'account, ora del reset non leggibile" in voce["nota"], (
            f"la nota «{voce['nota']}» non dice che l'ora del reset non si legge"
        )


class TestSulLimiteIlSolverNonParte:
    """Criterio 9, decisione 4: con `riprendi_dopo` nel rapporto il giro chiude
    `senza esito` come prima, ma il Solver non parte. Non c'è niente da
    decidere: il tick aspetta il reset e riprende."""

    def test_il_solver_non_parte(self, monkeypatch, tmp_path):
        agente = agente_che_scrive_i_flussi({}, stderr={"builder": LIMITE})
        voce = giro_col_limite(monkeypatch, tmp_path, agente)

        assert voce["solver"] == [], "sul limite d'uso con l'ora leggibile il Solver non parte"
        assert voce["giri_solver"] == 0, "un Solver che non parte non conta un giro"
        assert [ruolo_ed_esito(c)[0] for c in agente.comandi] == ["builder"]


def sh(cwd: Path, *args: str) -> str:
    """`git` vero in `cwd`. I commit di preparazione saltano gli hook (`--no-verify`
    dove si committa): il pre-commit di `apri_la_fase` lancerebbe il runner vero."""
    p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false",
                        *args], cwd=cwd, capture_output=True, text=True, check=True)
    return p.stdout.strip()


def committa(albero: Path, nome: str, messaggio: str) -> None:
    (albero / nome).write_text(f"{nome}\n", encoding="utf-8")
    sh(albero, "add", "-A")
    sh(albero, "commit", "-q", "--no-verify", "-m", messaggio)


def rapporto_fermo_sul_limite(registro: Path, pbi: str, ramo: str, **campi) -> None:
    """Il rapporto di un giro chiuso `senza esito` sul limite d'uso, in `registro`."""
    run = campi.pop("run", "20261016-174510")
    (registro / f"{run}.json").write_text(json.dumps({
        "run": run, "stato": "finito",
        "esiti": [{"pbi": pbi, "stato": "senza esito", "motivo": "builder-senza-esito",
                   "ramo": ramo, "riprendi_dopo": "2026-10-16T19:55"} | campi],
    }), encoding="utf-8")


class TestRiprendiParteDallaPuntaDelRamo:
    """Criterio 6, decisione 6: `--riprendi` porta il worktree alla punta di
    `origin/<ramo>` dell'ultimo rapporto e continua su quel ramo, senza `-giro2`."""

    def test_il_rapporto_porta_il_ramo_del_giro(self, monkeypatch, tmp_path):
        voce = giro_col_limite(monkeypatch, tmp_path,
                               agente_che_scrive_i_flussi({}, stderr={"builder": LIMITE}))

        assert voce.get("ramo") == "pbi/pbi-102", (
            "senza il ramo nel rapporto --riprendi non sa da quale ramo ripartire"
        )

    def test_riparte_dai_due_commit_e_avanza_di_fast_forward(self, monkeypatch, tmp_path):
        remoto, noi, altri = tmp_path / "remoto.git", tmp_path / "noi", tmp_path / "altri"
        sh(tmp_path, "init", "-q", "--bare", str(remoto))
        sh(tmp_path, "clone", "-q", str(remoto), str(altri))
        (altri / "backlog").mkdir()
        committa(altri, "backlog/PBI-102-una-prova.md", "docs: il PBI")
        sh(altri, "push", "-q", "origin", "main")
        sh(altri, "switch", "-q", "-c", "pbi/pbi-102")
        committa(altri, "uno.txt", "test: il primo criterio (RED)")
        committa(altri, "due.txt", "feat: il primo criterio")
        sh(altri, "push", "-q", "origin", "pbi/pbi-102")
        punta = sh(altri, "rev-parse", "HEAD")
        sh(tmp_path, "clone", "-q", str(remoto), str(noi))
        # Un ramo locale rimasto indietro con lo stesso nome: si riallinea, non si crea.
        sh(noi, "branch", "pbi/pbi-102", "origin/main")
        sh(noi, "switch", "-q", "--detach", "origin/main")  # come dopo il pre-flight del tick

        registro = tmp_path / "runs"
        registro.mkdir()
        rapporto_fermo_sul_limite(registro, "PBI-102", "pbi/pbi-102")
        monkeypatch.setattr(runner, "REPO", noi)
        monkeypatch.setattr(runner, "LOG_DIR", registro)
        monkeypatch.setattr(runner, "apri_la_fase", lambda base="": None)
        monkeypatch.setattr(runner, "gira_gate", lambda attivi, base=None: [])
        vero_esegui = runner.esegui
        agente = agente_che_scrive_i_flussi({})

        def _esegui(cmd, cwd, timeout=7200, **k):
            if cmd[:1] == ["git"]:
                return vero_esegui(cmd, cwd, timeout, **k)
            if ruolo_ed_esito(cmd)[0] == "builder":
                committa(noi, "tre.txt", "test: il secondo criterio (RED)")
            return agente(cmd, cwd, timeout, **k)

        monkeypatch.setattr(runner, "esegui", _esegui)

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False,
                                  run="giro", riprendi=True)

        assert esito.ramo == "pbi/pbi-102", f"il giro di ripresa è finito su {esito.ramo}"
        assert "giro2" not in sh(noi, "branch", "--list", "pbi/*"), "la ripresa non crea -giro2"
        assert "giro2" not in sh(remoto, "branch", "--list", "pbi/*")
        assert sh(remoto, "rev-parse", "pbi/pbi-102^") == punta, (
            "il commit nuovo sta sopra ai due del ramo pubblicato, di fast-forward"
        )
        assert esito.commit == 3, "il giro conta anche i due commit di prima"
        assert esito.riprese_limite == 1, "la prima ripresa per limite d'uso conta 1"

    def test_la_riga_di_comando_passa_riprendi_al_giro(self, monkeypatch, tmp_path):
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        monkeypatch.setattr(runner, "agenti_estranei", lambda *a, **k: [])
        monkeypatch.setattr(runner, "gate_mancanti", lambda attivi: [])
        chiamate: list[dict] = []

        def esegui_pbi_finto(pbi, *a, **k):
            chiamate.append(k)
            return runner.Esito(pbi, "senza esito")

        monkeypatch.setattr(runner, "esegui_pbi", esegui_pbi_finto)
        monkeypatch.setattr(sys, "argv",
                            ["asdlc-runner", "PBI-102", "--riprendi", "--in-primo-piano"])

        runner.smista()

        assert [k.get("riprendi") for k in chiamate] == [True], (
            "asdlc-runner PBI-N --riprendi deve far ripartire il giro dalla punta del ramo"
        )
