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

import fcntl
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


def test_con_il_lucchetto_tenuto_il_comando_rifiuta_senza_git_e_senza_pausa(
    home_finta, tmp_path, monkeypatch, capsys
):
    """Decisione 3. Un runner al lavoro nell'albero è un giro vivo, non un giro
    fermato: cancellargli il ramo sotto i piedi è peggio del problema. Il
    controllo è quello del tick, `giro_in_corso()` — il `flock` sul lucchetto,
    non la presenza del file (PBI-373) — e viene prima di tutto: nessun
    comando git, nemmeno una domanda, e nessuna pausa."""
    repo, albero = un_giro_fermato(tmp_path)
    visti, esegui = un_origin(home_finta)
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)

    with (albero / coda.LUCCHETTO).open("w") as tenuto:
        fcntl.flock(tenuto, fcntl.LOCK_EX | fcntl.LOCK_NB)
        uscita = chiudi_giro().smista(
            ["PBI-377", "--repo", str(repo), "--worktree", str(albero)])

    assert uscita != 0
    assert visti == [], "con un giro vivo non si chiama git"
    assert not (home_finta / "asdlc-tick.pausa").exists()
    detto = capsys.readouterr().out
    assert "lucchetto" in detto and str(albero) in detto, detto


@pytest.mark.parametrize("rami, nominati", [
    ((("pbi/pbi-377", ALTRA),), (TESTA, ALTRA)),
    ((), ("nessun ramo",)),
    ((("pbi/pbi-377", TESTA), ("pbi/pbi-377-giro2", ALTRA)),
     ("pbi/pbi-377", "pbi/pbi-377-giro2")),
], ids=["ramo-diverso-dalla-testa", "nessun-ramo", "due-rami"])
def test_senza_un_solo_ramo_sulla_testa_del_rapporto_il_comando_rifiuta(
    home_finta, tmp_path, monkeypatch, capsys, rami, nominati
):
    """Decisione 3. Su `origin` ci dev'essere esattamente un ramo del PBI, e deve
    puntare alla testa del rapporto. Un ramo andato avanti dopo il giro — una
    correzione a mano, un secondo giro — non è ciò che il rapporto descrive, e
    il tag finirebbe su un commit mentre si cancella un altro: il 25/09 il tag
    di PBI-363 è finito su 739fc08 e c'è voluto un `push -f`. Il rifiuto nomina
    i due sha, o i rami che ha trovato."""
    repo, albero = un_giro_fermato(tmp_path)
    visti, esegui = un_origin(home_finta, rami=rami)
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)

    uscita = chiudi_giro().smista(["PBI-377", "--repo", str(repo), "--worktree", str(albero)])

    assert uscita != 0
    assert i_passi(visti) == []
    assert not (home_finta / "asdlc-tick.pausa").exists()
    detto = capsys.readouterr().out
    assert all(n in detto for n in nominati), detto


def test_un_tag_con_lo_stesso_nome_gia_su_origin_fa_rifiutare(
    home_finta, tmp_path, monkeypatch, capsys
):
    """Decisione 4: un tag con quel nome già su `origin` è un rifiuto. Vuol dire
    che quel giro è già stato chiuso una volta, o che un altro giro dello stesso
    giorno ne ha preso il nome: spostarlo è il `push -f` di PBI-363."""
    repo, albero = un_giro_fermato(tmp_path)
    visti, esegui = un_origin(home_finta, tag_presenti=(TAG,))
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)

    uscita = chiudi_giro().smista(["PBI-377", "--repo", str(repo), "--worktree", str(albero)])

    assert uscita != 0
    assert i_passi(visti) == []
    assert not (home_finta / "asdlc-tick.pausa").exists()
    assert TAG in capsys.readouterr().out


def test_un_passo_che_fallisce_toglie_la_pausa_e_dice_cosa_resta(
    home_finta, tmp_path, monkeypatch, capsys
):
    """Decisione 6. Il push del tag è rifiutato: il comando si ferma lì — senza
    il tag su `origin`, cancellare il ramo perderebbe il giro — toglie la pausa
    lo stesso, esce diverso da 0, nomina il passo fallito e scrive i comandi che
    restano da fare a mano. Una pausa lasciata indietro da un guasto terrebbe il
    tick spento senza che nessuno lo sappia."""
    repo, albero = un_giro_fermato(tmp_path)
    push_del_tag = ["git", "push", "origin", f"refs/tags/{TAG}"]
    visti, esegui = un_origin(home_finta, fallisce=push_del_tag)
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)

    uscita = chiudi_giro().smista(["PBI-377", "--repo", str(repo), "--worktree", str(albero)])

    assert uscita not in (0, None)
    assert not (home_finta / "asdlc-tick.pausa").exists(), "la pausa si toglie anche qui"
    assert not [cmd for cmd, _, _ in visti if "--delete" in cmd], "il ramo non si cancella"
    detto = capsys.readouterr().out
    assert " ".join(push_del_tag) in detto, detto
    assert "git push origin --delete pbi/pbi-377" in detto, detto


def test_una_pausa_che_cera_gia_resta_con_la_sua_riga_e_il_comando_lo_dice(
    home_finta, tmp_path, monkeypatch, capsys
):
    """Decisione 6, l'eccezione. Il tick era già in pausa per un'altra ragione:
    il comando non riscrive il file e non lo toglie — riaccendere il tick non è
    una sua decisione — e alla fine dice che il tick resta in pausa e da quando."""
    riga = "2026-09-30 17:51 ripassata dell'import, Francesco\n"
    (home_finta / "asdlc-tick.pausa").write_text(riga, encoding="utf-8")
    repo, albero = un_giro_fermato(tmp_path)
    visti, esegui = un_origin(home_finta)
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)

    uscita = chiudi_giro().smista(["PBI-377", "--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 0
    assert (home_finta / "asdlc-tick.pausa").read_text(encoding="utf-8") == riga
    assert all(pausa == riga for _, _, pausa in i_passi(visti)), "il file non si riscrive"
    detto = capsys.readouterr().out
    assert "resta in pausa" in detto and riga.strip() in detto, detto


def test_il_dry_run_stampa_i_sei_passi_coi_valori_veri_e_non_esegue_niente(
    home_finta, tmp_path, monkeypatch, capsys
):
    """Decisione 7. Le domande a `origin` restano — senza non ci sarebbero i
    valori veri, il ramo e il tag — ma nessun comando che cambia qualcosa parte,
    e la pausa non nasce."""
    repo, albero = un_giro_fermato(tmp_path)
    visti, esegui = un_origin(home_finta)
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)

    uscita = chiudi_giro().smista(
        ["PBI-377", "--repo", str(repo), "--worktree", str(albero), "--dry-run"])

    assert uscita == 0
    assert i_passi(visti) == []
    assert not (home_finta / "asdlc-tick.pausa").exists()
    detto = capsys.readouterr().out
    for atteso in (str(home_finta / "asdlc-tick.pausa"),
                   f"git tag {TAG} {TESTA}",
                   f"git push origin refs/tags/{TAG}",
                   "git push origin --delete pbi/pbi-377",
                   "git merge --ff-only origin/main"):
        assert atteso in detto, (atteso, detto)


def test_il_rapporto_e_l_ultimo_che_nomina_il_pbi_o_quello_scelto_con_run(
    home_finta, tmp_path, monkeypatch
):
    """Decisione 2. Il rapporto è l'ultimo `runs/<run>.json` dell'albero che
    nomina il PBI: uno più recente di un altro PBI non conta. Con `--run <id>` si
    sceglie quello, e il tag porta la sua testa e la sua data."""
    repo, albero = un_giro_fermato(tmp_path, run="20260926-090000-000001", testa=ALTRA)
    runs = albero / "runs"
    (runs / f"{RUN}.json").write_text(json.dumps({"run": RUN, "esiti": [
        {"pbi": "PBI-377", "stato": "fermato", "testa": TESTA}]}), encoding="utf-8")
    (runs / "20260928-080000-000001.json").write_text(json.dumps({
        "run": "20260928-080000-000001", "esiti": [
            {"pbi": "PBI-378", "stato": "fermato", "testa": "f" * 40}]}), encoding="utf-8")
    argomenti = ["PBI-377", "--repo", str(repo), "--worktree", str(albero)]

    visti, esegui = un_origin(home_finta)
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)
    assert chiudi_giro().smista(argomenti) == 0
    assert ["git", "tag", TAG, TESTA] in [cmd for cmd, _, _ in visti]

    visti, esegui = un_origin(home_finta, rami=(("pbi/pbi-377", ALTRA),))
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)
    assert chiudi_giro().smista([*argomenti, "--run", "20260926-090000-000001"]) == 0
    assert (["git", "tag", "giro-fermato/pbi-377-giro1-20260926", ALTRA]
            in [cmd for cmd, _, _ in visti])


@pytest.mark.parametrize("scelto", [[], ["--run", "20260101-000000-000001"]],
                         ids=["nessun-rapporto-del-pbi", "run-che-non-esiste"])
def test_senza_un_rapporto_del_pbi_il_comando_rifiuta(
    home_finta, tmp_path, monkeypatch, capsys, scelto
):
    """La Direttiva: il comando rifiuta di partire quando non è sicuro di cosa
    sta chiudendo. Nell'albero c'è solo il rapporto di un altro PBI, o `--run`
    nomina un rapporto che non c'è: niente testa, niente tag, e il rifiuto dice
    dove ha cercato."""
    repo, albero = un_giro_fermato(tmp_path, pbi="PBI-378")
    visti, esegui = un_origin(home_finta)
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)

    uscita = chiudi_giro().smista(
        ["PBI-377", "--repo", str(repo), "--worktree", str(albero), *scelto])

    assert uscita != 0
    assert i_passi(visti) == []
    assert not (home_finta / "asdlc-tick.pausa").exists()
    assert str(albero / "runs") in capsys.readouterr().out


@pytest.mark.parametrize("muta", ["--heads", "--tags"])
def test_un_origin_che_non_risponde_fa_rifiutare_e_il_rifiuto_lo_dice(
    home_finta, tmp_path, monkeypatch, capsys, muta
):
    """Decisione 3: il rifiuto dice quale condizione e con quali valori. Un
    `ls-remote` che fallisce non è «nessun ramo» né «il tag c'è già»: è un
    `origin` che non ha risposto, e il rifiuto riporta ciò che git ha detto."""
    repo, albero = un_giro_fermato(tmp_path)
    visti, esegui_sano = un_origin(home_finta)

    def esegui(cmd, cwd):
        if "ls-remote" in cmd and muta in cmd:
            visti.append((cmd, cwd, None))
            return 128, "fatal: unable to access 'https://github.com/': Could not resolve host"
        return esegui_sano(cmd, cwd)

    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)

    uscita = chiudi_giro().smista(["PBI-377", "--repo", str(repo), "--worktree", str(albero)])

    assert uscita != 0
    assert i_passi(visti) == []
    assert not (home_finta / "asdlc-tick.pausa").exists()
    detto = capsys.readouterr().out
    assert "Could not resolve host" in detto, detto


# --- Il lucchetto del tick (PBI-392) -----------------------------------------


def test_con_il_lucchetto_del_tick_tenuto_il_comando_rifiuta_senza_git_e_senza_pausa(
    home_finta, tmp_path, monkeypatch, capsys
):
    """PBI-392, decisione 4. Un tick che sta lanciando non tiene ancora il
    lucchetto del runner, e il comando lo trovava libero: creava la pausa e
    cancellava il ramo mentre il tick finiva il lancio (difetto 70 di PBI-102).
    Con `runs/.tick.lock` del checkout tenuto il comando rifiuta prima di ogni
    altra cosa — nessun `git`, nemmeno una domanda, e nessuna pausa — dice che
    un tick è in corso e di riprovare fra un minuto, ed esce diverso da 0."""
    repo, albero = un_giro_fermato(tmp_path)
    visti, esegui = un_origin(home_finta)
    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)
    (repo / "runs").mkdir()

    with (repo / "runs" / ".tick.lock").open("w") as tenuto:
        fcntl.flock(tenuto, fcntl.LOCK_EX | fcntl.LOCK_NB)
        uscita = chiudi_giro().smista(
            ["PBI-377", "--repo", str(repo), "--worktree", str(albero)])

    assert uscita not in (0, None)
    assert visti == [], "con un tick in corso non si chiama git"
    assert not (home_finta / "asdlc-tick.pausa").exists()
    detto = capsys.readouterr().out
    assert "tick" in detto and "riprova" in detto and "minuto" in detto, detto



def test_guardia_un_tick_lanciato_durante_un_passo_esce_occupato(
    home_finta, tmp_path, monkeypatch
):
    """PBI-392, decisione 4: il comando tiene il lucchetto del tick per tutti i
    sei passi. A ogni comando che cambia qualcosa il `git` finto fa partire un
    tick sullo stesso checkout, e ogni tick esce con la riga `occupato:` del
    lucchetto — non `in pausa:`, che vorrebbe dire che il tick è arrivato fin
    lì perché il lucchetto era libero."""
    repo, albero = un_giro_fermato(tmp_path)
    visti, rispondi = un_origin(home_finta)
    tick_albero = tmp_path / "albero-del-tick"
    tick_albero.mkdir()
    righe_dei_tick: list[str] = []

    def esegui(cmd, cwd):
        esito = rispondi(cmd, cwd)
        if "ls-remote" not in cmd:
            assert coda.smista(["--repo", str(repo), "--worktree", str(tick_albero)]) == 0
            righe_dei_tick.append(
                (repo / coda.LOG).read_text(encoding="utf-8").splitlines()[-1])
        return esito

    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)

    uscita = chiudi_giro().smista(["PBI-377", "--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 0
    assert len(righe_dei_tick) == len(i_passi(visti)) == 5
    assert all(r.split("  ", 1)[1].startswith("occupato: il lucchetto del tick")
               for r in righe_dei_tick), righe_dei_tick


def lucchetto_del_tick_libero(repo: Path) -> bool:
    """Un `flock` non bloccante su `runs/.tick.lock` da un descrittore nuovo:
    `True` se nessuno lo tiene."""
    with (repo / "runs" / ".tick.lock").open("a") as altro:
        try:
            fcntl.flock(altro, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(altro, fcntl.LOCK_UN)
        return True


def test_guardia_un_passo_che_fallisce_rilascia_il_lucchetto_del_tick(
    home_finta, tmp_path, monkeypatch
):
    """PBI-392, decisione 4: il lucchetto si tiene fino alla fine anche quando
    un passo fallisce, e alla fine si rilascia. Un lucchetto rimasto preso
    terrebbe fermo il tick senza una riga che dica perché. Il push del tag è
    rifiutato: mentre fallisce il lucchetto è tenuto, e uscito il comando è
    libero."""
    repo, albero = un_giro_fermato(tmp_path)
    push_del_tag = ["git", "push", "origin", f"refs/tags/{TAG}"]
    _, rispondi = un_origin(home_finta, fallisce=push_del_tag)
    libero_al_passo_fallito: list[bool] = []

    def esegui(cmd, cwd):
        if cmd == push_del_tag:
            libero_al_passo_fallito.append(lucchetto_del_tick_libero(repo))
        return rispondi(cmd, cwd)

    monkeypatch.setattr(chiudi_giro(), "esegui", esegui)

    uscita = chiudi_giro().smista(["PBI-377", "--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 1, "il passo è fallito"
    assert libero_al_passo_fallito == [False]
    assert lucchetto_del_tick_libero(repo), "uscito il comando, il lucchetto è libero"
