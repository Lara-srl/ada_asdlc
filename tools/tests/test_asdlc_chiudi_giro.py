"""`asdlc-chiudi-giro`: un giro fermato si chiude con un comando (`backlog/PBI-385`).

Tre gruppi:

- **La testa nel rapporto** — `Esito.testa`, lo sha del ramo pubblicato su
  `origin`, che il runner scrive e il comando legge.
- **I rifiuti** — ciò che fa dire di no al comando prima di toccare qualsiasi cosa.
- **I sei passi** — pausa, tag, push del tag, ramo cancellato, `ff-only`, pausa
  tolta: nell'ordine, anche quando uno fallisce.

`HOME` è una cartella temporanea in ogni test (`home_finta`): la pausa vera,
`~/asdlc-tick.pausa`, ferma il tick della macchina, e un test che la creasse o la
togliesse spegnerebbe o riaccenderebbe il cron di chi li lancia.
"""

import importlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

runner = importlib.import_module("asdlc.runner")
# L'import non legge `asdlc.toml` (PBI-382): lo si legge qui, come fa
# `test_asdlc_runner.py`, sulla radice di questo repository.
runner.REPO = REPO
runner.configura(runner.asdlc_config.carica(REPO))


@pytest.fixture(autouse=True)
def home_finta(tmp_path, monkeypatch):
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    return casa


def sh(cwd: Path, *args: str) -> str:
    fatto = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                            "-c", "init.defaultBranch=main", *args],
                           cwd=cwd, capture_output=True, text=True, check=True)
    return fatto.stdout.strip()


# --- La testa nel rapporto ---------------------------------------------------


def test_il_rapporto_di_un_giro_che_pubblica_porta_la_testa_che_sta_su_origin(
    tmp_path, monkeypatch
):
    """Decisione 1: `Esito.testa` è lo sha del ramo pubblicato su `origin`. È ciò
    su cui `asdlc-chiudi-giro` mette il tag, e senza il comando dovrebbe
    indovinarlo — il 25/09 il tag di `PBI-363` è finito sulla testa sbagliata.

    Con git vero: un remoto nudo, un clone, un commit del giro pubblicato."""
    remoto, noi = tmp_path / "remoto.git", tmp_path / "noi"
    sh(tmp_path, "init", "-q", "--bare", str(remoto))
    sh(tmp_path, "clone", "-q", str(remoto), str(noi))
    sh(noi, "commit", "-q", "--allow-empty", "-m", "base")
    sh(noi, "switch", "-q", "-c", "pbi/pbi-385")
    sh(noi, "commit", "-q", "--allow-empty", "-m", "del giro")
    monkeypatch.setattr(runner, "REPO", noi)
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path / "runs")
    esito = runner.Esito("PBI-385", "fermato")

    assert runner.pubblica("pbi/pbi-385", esito) is True
    rapporto = runner.scrivi_rapporto("20260930-211011-341864", [esito], "finito")

    su_origin = sh(noi, "ls-remote", "origin", "refs/heads/pbi/pbi-385").split()[0]
    scritto = json.loads(rapporto.read_text(encoding="utf-8"))["esiti"][0]
    assert scritto.get("testa") == su_origin


def test_guardia_un_rapporto_senza_testa_si_registra_ancora(tmp_path, monkeypatch):
    """Guardia dichiarata di PBI-385: i rapporti dei giri di prima non hanno
    `testa`, e `--registra` li deve piegare in `runs/tempi.csv` come prima. Il
    campo nuovo è del comando che chiude il giro, non del registro."""
    cartella = tmp_path / "runs"
    cartella.mkdir()
    (cartella / "20260927-100000-000001.json").write_text(json.dumps({
        "run": "20260927-100000-000001", "stato": "finito",
        "esiti": [{"pbi": "PBI-377", "stato": "fermato", "commit": 4,
                   "nota": "fermati: la domanda", "iniziato": "2026-09-27T10:00:00",
                   "finito": "2026-09-27T10:40:00", "durata_s": 2400.0,
                   "tempi": {"builder": 2000.0, "gate": 400.0}}],
    }), encoding="utf-8")
    monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")

    assert runner.registra(cartella) == 0

    righe = list(runner.csv.DictReader((tmp_path / "tempi.csv").open(encoding="utf-8")))
    assert [(r["run"], r["pbi"], r["stato"], r["commit"]) for r in righe] == [
        ("20260927-100000-000001", "PBI-377", "fermato", "4")]


# --- Il comando --------------------------------------------------------------


def test_il_modulo_di_asdlc_chiudi_giro_sta_nel_pacchetto():
    """Il punto d'ingresso `asdlc-chiudi-giro` di `tools/pyproject.toml` punta a
    `asdlc.chiudi_giro:main`: il modulo deve esserci, nel pacchetto `asdlc`."""
    assert importlib.util.find_spec("asdlc.chiudi_giro") is not None


# --- I sei passi -------------------------------------------------------------

coda = importlib.import_module("asdlc.coda")
coda.REPO = REPO
coda.configura(coda.asdlc_config.carica(REPO))

TESTA = "7e57a00000000000000000000000000000000377"
ALTRA = "a17a000000000000000000000000000000000377"
RUN = "20260927-101500-000001"
TAG = "giro-fermato/pbi-377-giro1-20260927"


def chiudi_giro():
    return importlib.import_module("asdlc.chiudi_giro")


def un_giro_fermato(tmp_path, *, testa=TESTA, run=RUN, pbi="PBI-377"):
    """Il checkout del tick e l'albero del runner, con dentro il rapporto di un
    giro fermato che porta la sua testa."""
    repo, albero = tmp_path / "repo", tmp_path / "albero"
    repo.mkdir()
    (albero / "runs").mkdir(parents=True)
    esito = {"pbi": pbi, "stato": "fermato", "iniziato": "2026-09-27T10:15:00"}
    if testa is not None:
        esito["testa"] = testa
    (albero / "runs" / f"{run}.json").write_text(
        json.dumps({"run": run, "stato": "finito", "esiti": [esito]}), encoding="utf-8")
    return repo, albero


def un_origin(home, rami=(("pbi/pbi-377", TESTA),), tag_presenti=(), fallisce=None):
    """Un `esegui()` finto: `ls-remote` risponde coi rami e i tag dati, il resto
    riesce. Ogni comando si registra con la riga della pausa com'era in quel
    momento, `None` se il file non c'era. `fallisce` è l'inizio di un comando
    che esce 1."""
    visti: list[tuple[list[str], Path, str | None]] = []

    def esegui(cmd, cwd):
        pausa = home / "asdlc-tick.pausa"
        visti.append((cmd, cwd, pausa.read_text(encoding="utf-8") if pausa.exists() else None))
        if fallisce is not None and cmd[:len(fallisce)] == fallisce:
            return 1, "! [remote rejected] (permission denied)"
        if "ls-remote" in cmd and "--tags" in cmd:
            return 0, "".join(f"{TESTA}\trefs/tags/{t}\n" for t in tag_presenti)
        if "ls-remote" in cmd:
            return 0, "".join(f"{sha}\trefs/heads/{r}\n" for r, sha in rami)
        return 0, ""

    return visti, esegui


def i_passi(visti):
    """I comandi che cambiano qualcosa: tutto tranne le domande a `ls-remote`."""
    return [(cmd, cwd, pausa) for cmd, cwd, pausa in visti if "ls-remote" not in cmd]


def test_un_giro_fermato_si_chiude_coi_sei_passi_in_ordine(home_finta, tmp_path, monkeypatch):
    """Il criterio che dà il nome al PBI. Pausa, tag sulla testa del rapporto,
    push del tag, ramo tolto da `origin`, `ff-only` del checkout del tick, pausa
    tolta: sette comandi a mano, e l'ordine conta."""
    repo, albero = un_giro_fermato(tmp_path)
    visti, esegui = un_origin(home_finta)
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui, raising=False)

    uscita = chiudi_giro().smista(["PBI-377", "--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 0
    passi = i_passi(visti)
    assert [cmd for cmd, _, _ in passi] == [
        ["git", "tag", TAG, TESTA],
        ["git", "push", "origin", f"refs/tags/{TAG}"],
        ["git", "push", "origin", "--delete", "pbi/pbi-377"],
        ["git", "fetch", "origin"],
        ["git", "merge", "--ff-only", "origin/main"],
    ]
    assert {cwd for _, cwd, _ in passi} == {repo}
    assert all(pausa is not None for _, _, pausa in passi), "ogni passo avviene in pausa"
    assert not (home_finta / "asdlc-tick.pausa").exists(), "alla fine la pausa è tolta"


def test_la_pausa_ce_prima_che_il_ramo_si_cancelli(home_finta, tmp_path, monkeypatch):
    """Il 23/09 il ramo di PBI-365 è stato cancellato prima di spegnere il tick,
    e il tick ha rilanciato il PBI col testo vecchio. Quando parte la
    cancellazione del ramo la pausa c'è già, con la ragione del comando."""
    repo, albero = un_giro_fermato(tmp_path)
    visti, esegui = un_origin(home_finta)
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui, raising=False)

    chiudi_giro().smista(["PBI-377", "--repo", str(repo), "--worktree", str(albero)])

    cancellazione = [pausa for cmd, _, pausa in visti if "--delete" in cmd]
    assert len(cancellazione) == 1
    assert cancellazione[0] is not None, "la pausa deve esserci prima della cancellazione"
    assert cancellazione[0].strip().endswith("asdlc-chiudi-giro PBI-377"), cancellazione


def test_il_nome_del_tag_porta_il_giro_dal_ramo_e_la_data_dal_rapporto(
    home_finta, tmp_path, monkeypatch
):
    """Decisione 4. `pbi/pbi-376-giro2` è il secondo giro (`nome_libero()`), e il
    rapporto è del 29/09 anche se lo si chiude un altro giorno: il tag dice quale
    giro è stato fermato e quando, non quando qualcuno lo ha chiuso."""
    repo, albero = un_giro_fermato(tmp_path, run="20260929-231500-000002", pbi="PBI-376")
    visti, esegui = un_origin(home_finta, rami=(("pbi/pbi-376-giro2", TESTA),))
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)

    assert chiudi_giro().smista(
        ["PBI-376", "--repo", str(repo), "--worktree", str(albero)]) == 0

    tag = [cmd for cmd, _, _ in visti if cmd[:2] == ["git", "tag"]]
    assert tag == [["git", "tag", "giro-fermato/pbi-376-giro2-20260929", TESTA]]
    cancellato = [cmd for cmd, _, _ in visti if "--delete" in cmd]
    assert cancellato == [["git", "push", "origin", "--delete", "pbi/pbi-376-giro2"]]


# --- I rifiuti -----------------------------------------------------------------


def test_senza_testa_nel_rapporto_il_comando_rifiuta(home_finta, tmp_path, monkeypatch, capsys):
    """Decisione 3. Un rapporto senza `testa` è di un giro di prima di PBI-385, o
    di un giro che non ha pubblicato: su cosa mettere il tag non lo dice, e il
    comando non lo indovina. Rifiuta prima di toccare qualsiasi cosa, e nomina
    il rapporto che ha letto."""
    repo, albero = un_giro_fermato(tmp_path, testa=None)
    visti, esegui = un_origin(home_finta)
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)

    uscita = chiudi_giro().smista(["PBI-377", "--repo", str(repo), "--worktree", str(albero)])

    assert uscita != 0
    assert i_passi(visti) == []
    assert not (home_finta / "asdlc-tick.pausa").exists()
    detto = capsys.readouterr().out
    assert "testa" in detto and RUN in detto, detto
