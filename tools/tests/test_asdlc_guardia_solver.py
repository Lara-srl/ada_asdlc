"""La guardia di processo del Solver (`backlog/PBI-508`, `ADR-0030` decisione 4, R4-R7 e R13).

Che il Solver abbia rispettato le regole lo dice il codice, leggendo il rapporto, git e `gh`:
mai un modello (`ADR-0027`). La guardia segnala e non blocca (`ADR-0008`).
"""

import importlib

from test_asdlc_solver import giro_fermato  # noqa: F401 — è una fixture

runner = importlib.import_module("asdlc.runner")

INTESTAZIONE = "## Guardia di processo"


def righe_della_guardia(e):
    return e.guardia.splitlines()


def test_la_riga_r4_e_non_eseguita_con_il_rinvio_a_pbi_511():
    """R4: la traccia delle letture è di `PBI-511`; fin lì la riga è sempre `non eseguita`."""
    e = runner.Esito("PBI-102", "fermato", solver=[{"esito": "senza esito", "uscita": ""}])

    runner.guardia_del_solver(e)

    assert righe_della_guardia(e)[0] == INTESTAZIONE
    assert "R4: non eseguita (PBI-511)" in righe_della_guardia(e)


def test_un_giro_fermato_con_il_solver_porta_la_sezione_e_chiude_come_prima(giro_fermato):  # noqa: F811
    """Il giro non si ferma per la guardia: lo stato è quello del blocco."""
    esito, _ = giro_fermato({}, {"solver": "boh"})

    assert esito.stato == "fermato"
    assert "R4: non eseguita (PBI-511)" in esito.guardia.splitlines()


def test_un_giro_senza_solver_non_ha_la_sezione():
    e = runner.Esito("PBI-102", "fatto")

    runner.guardia_del_solver(e)

    assert e.guardia == ""


def git_in(repo, *args):
    import subprocess
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          cwd=repo, check=True, capture_output=True, text=True).stdout


def repo_a_monte(tmp_path, tocca=(), nuovo=("backlog/PBI-900-x.md",)):
    """Un repository `asdlc` finto: `main` con `AGENTS.md` e un ADR, e il ramo `pbi/x` che
    modifica i file di `tocca` e ne aggiunge di `nuovo`."""
    git_in(tmp_path, "init", "-q", "-b", "main")
    for file in ("AGENTS.md", "decisions/ADR-0001-uno.md"):
        (tmp_path / file).parent.mkdir(exist_ok=True)
        (tmp_path / file).write_text("uno\n", encoding="utf-8")
    git_in(tmp_path, "add", "-A")
    git_in(tmp_path, "commit", "-q", "-m", "base")
    git_in(tmp_path, "checkout", "-q", "-b", "pbi/x")
    for file in tocca:
        (tmp_path / file).write_text("due\n", encoding="utf-8")
    for file in nuovo:
        (tmp_path / file).parent.mkdir(exist_ok=True)
        (tmp_path / file).write_text("nuovo\n", encoding="utf-8")
    git_in(tmp_path, "add", "-A")
    git_in(tmp_path, "commit", "-q", "-m", "ramo")
    return runner.AMonte(repo=tmp_path, ramo="pbi/x", base="main",
                         pbi="backlog/PBI-900-x.md", causa="runner-x")


def guardia_di(a_monte):
    e = runner.Esito("PBI-102", "fermato", solver=[{"esito": "limite-del-runner"}])
    runner.guardia_del_solver(e, a_monte)
    return righe_della_guardia(e)


def riga(righe, regola):
    return next(r for r in righe if r.startswith(f"{regola}:"))


def test_r5_e_violata_se_la_pr_parte_da_main(tmp_path):
    a_monte = repo_a_monte(tmp_path)
    git_in(tmp_path, "checkout", "-q", "main")
    git_in(tmp_path, "merge", "-q", "pbi/x")

    assert riga(guardia_di(runner.AMonte(**{**a_monte.__dict__, "ramo": "main", "base": "main"})),
                "R5").startswith("R5: violata")


def test_r5_e_violata_se_la_pr_tocca_agents_md_o_un_adr_esistente(tmp_path):
    a_monte = repo_a_monte(tmp_path, tocca=("AGENTS.md", "decisions/ADR-0001-uno.md"))

    r5 = riga(guardia_di(a_monte), "R5")

    assert r5.startswith("R5: violata")
    assert "AGENTS.md" in r5 and "decisions/ADR-0001-uno.md" in r5


def test_r5_e_ok_per_un_ramo_che_aggiunge_solo_file_nuovi(tmp_path):
    a_monte = repo_a_monte(tmp_path, nuovo=("backlog/PBI-900-x.md", "decisions/ADR-0099-n.md"))

    assert riga(guardia_di(a_monte), "R5") == "R5: ok"


def con_gh(monkeypatch, codice=0, uscita="[]"):
    """`gh` finto: risponde `uscita` con `codice`; ogni altro comando va al varco vero."""
    vero = runner.esegui

    def _esegui(cmd, cwd, *a, **k):
        if cmd[0] == "gh":
            return codice, uscita
        return vero(cmd, cwd, *a, **k)

    monkeypatch.setattr(runner, "esegui", _esegui)


def test_r6_e_violata_se_un_altro_pbi_ha_la_stessa_causa_e_cita_il_pbi(tmp_path, monkeypatch):
    """Un file in `backlog/` con `**Causa:** runner-x` e una seconda segnalazione di `runner-x`."""
    a_monte = repo_a_monte(tmp_path)
    (tmp_path / "backlog" / "PBI-700-prima.md").write_text(
        "# PBI-700\n\n**Causa:** runner-x\n", encoding="utf-8")
    con_gh(monkeypatch)

    r6 = riga(guardia_di(a_monte), "R6")

    assert r6.startswith("R6: violata")
    assert "PBI-700-prima.md" in r6


def test_r6_e_violata_se_una_pr_aperta_porta_la_stessa_causa_e_cita_la_pr(tmp_path, monkeypatch):
    a_monte = repo_a_monte(tmp_path)
    con_gh(monkeypatch, uscita='[{"number": 12, "title": "PBI-701: runner-x", "body": "",'
                               ' "headRefName": "pbi/altro"}]')

    r6 = riga(guardia_di(a_monte), "R6")

    assert r6.startswith("R6: violata")
    assert "#12" in r6


def test_r6_e_ok_se_nessun_altro_pbi_ne_pr_ha_la_causa(tmp_path, monkeypatch):
    """Il PBI della PR stessa non è un duplicato di sé, né lo è la sua PR."""
    a_monte = repo_a_monte(tmp_path)
    (tmp_path / "backlog" / "PBI-900-x.md").write_text("**Causa:** runner-x\n", encoding="utf-8")
    con_gh(monkeypatch, uscita='[{"number": 13, "title": "runner-x", "body": "",'
                               ' "headRefName": "pbi/x"}]')

    assert riga(guardia_di(a_monte), "R6") == "R6: ok"


def scrivi_il_pbi_a_monte(tmp_path, scope):
    """Riscrive sul ramo il PBI della PR con lo Scope dato (un elenco di righe)."""
    testo = "# PBI-900: x\n\n## Direttiva\n\n**Scope**\n\n" + "\n".join(scope) + (
        "\n\n**Fuori scope**\n\n- `asdlc.toml` del progetto: è del PBI a valle.\n")
    (tmp_path / "backlog" / "PBI-900-x.md").write_text(testo, encoding="utf-8")
    git_in(tmp_path, "add", "-A")
    git_in(tmp_path, "commit", "-q", "-m", "scope")


def test_r7_e_violata_se_lo_scope_elenca_un_file_del_progetto(tmp_path, monkeypatch):
    a_monte = repo_a_monte(tmp_path)
    scrivi_il_pbi_a_monte(tmp_path, ["- `tools/asdlc/runner.py` — il fix.",
                                     "- `asdlc.toml` del progetto — la sezione `[junit]`."])
    con_gh(monkeypatch)

    r7 = riga(guardia_di(a_monte), "R7")

    assert r7.startswith("R7: violata")
    assert "asdlc.toml" in r7


def test_r7_e_ok_se_lo_scope_elenca_solo_il_runner(tmp_path, monkeypatch):
    """La riga di «Fuori scope» che nomina il file del progetto non è nello Scope."""
    a_monte = repo_a_monte(tmp_path)
    scrivi_il_pbi_a_monte(tmp_path, ["- `tools/asdlc/runner.py` — il fix.",
                                     "- `tools/tests/test_x.py` — il test."])
    con_gh(monkeypatch)

    assert riga(guardia_di(a_monte), "R7") == "R7: ok"
