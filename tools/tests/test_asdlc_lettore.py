"""Il Lettore e la sonda del rosso (`backlog/PBI-521`, `ADR-0031`).

Il Lettore è il quarto ruolo: legge il PBI contro la base, risponde alle sette
domande con `rilievo`, propone con `sonda` i test RED dei criteri e chiude con
`letto`. Le sonde le esegue il runner, in un albero usa e getta alla base: una
sonda verde è un rilievo R deciso dal codice, non dal modello.

Nessun test lancia `claude`: il Lettore è finto, e scrive nel suo `cwd` e nei file
della decisione 2 ciò che il server scriverebbe. Su `main` il ruolo, gli strumenti
e il flag non esistono, quindi i criteri nascono rossi per asserzione.
"""

import dataclasses
import importlib
import json
import re
import tomllib
from pathlib import Path

import pytest
from test_asdlc_preverifica import clone_con_la_base, lancia, sh
from test_asdlc_runner import ruolo_ed_esito

esito = importlib.import_module("asdlc.esito")
runner = importlib.import_module("asdlc.runner")
config = importlib.import_module("asdlc.config")

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"


def nomi(ruolo):
    return {s["name"] for s in esito.strumenti(ruolo)}


def righe_della_lettura(file: Path) -> list[dict]:
    lettura = Path(f"{file}.lettura.jsonl")
    if not lettura.exists():
        return []
    return [json.loads(r) for r in lettura.read_text(encoding="utf-8").splitlines() if r.strip()]


# --- Criterio 1: il server accetta e accumula gli strumenti del Lettore -------

RILIEVO_R = {"domanda": "R", "criterio": 2, "testo": "il criterio 2 è già vero su main",
             "evidenza": "modulo.py:1"}
RILIEVO_N = {"domanda": "N", "criterio": 0, "testo": "il PBI cita una funzione che non c'è",
             "evidenza": "modulo.py"}
SONDA = {"criterio": 1, "file": "test_sonda.py", "nome": "test_la_somma"}


def albero_del_lettore(tmp_path, monkeypatch) -> Path:
    """L'albero da cui parte il server, con un modulo e un test, e il file d'esito
    in una cartella accanto."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "modulo.py").write_text("def somma(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "test_sonda.py").write_text("def test_la_somma():\n    pass\n", encoding="utf-8")
    cartella = tmp_path / "esito"
    cartella.mkdir()
    return cartella / "lettore.json"


def test_il_server_accetta_e_accumula_gli_strumenti_del_lettore(tmp_path, monkeypatch):
    file = albero_del_lettore(tmp_path, monkeypatch)

    assert {"rilievo", "sonda", "letto"} <= nomi("lettore")
    for nome, argomenti in (("rilievo", RILIEVO_R), ("rilievo", RILIEVO_N), ("sonda", SONDA)):
        risposta = esito.chiama(nome, argomenti, "lettore", str(file))
        assert not risposta["isError"], (nome, risposta)
    assert not file.exists(), "rilievo e sonda si accumulano, non chiudono la lettura"
    assert righe_della_lettura(file) == [{"strumento": "rilievo", **RILIEVO_R},
                                         {"strumento": "rilievo", **RILIEVO_N},
                                         {"strumento": "sonda", **SONDA}]

    letto = esito.chiama("letto", {"riepilogo": "due rilievi e una sonda"}, "lettore", str(file))

    assert not letto["isError"], letto
    assert json.loads(file.read_text(encoding="utf-8")) == {
        "esito": "letto", "riepilogo": "due rilievi e una sonda",
        "rilievi": [RILIEVO_R, RILIEVO_N], "sonde": [SONDA]}


def test_il_server_rifiuta_le_chiamate_del_lettore_che_non_reggono_e_quelle_dopo_letto(
        tmp_path, monkeypatch):
    """Decisione 1: la domanda è una fra `R F T A E D N`, l'evidenza e il file della
    sonda sono file dell'albero (la regola di `_risolvi()`), il criterio della sonda è
    almeno 1; dopo `letto` la lettura è chiusa. Un rifiuto non scrive niente."""
    file = albero_del_lettore(tmp_path, monkeypatch)
    rifiutate = [
        ("rilievo", {**RILIEVO_R, "domanda": "X"}),
        ("rilievo", {**RILIEVO_R, "evidenza": "non-c-e.py:3"}),
        ("rilievo", {**RILIEVO_R, "evidenza": str(tmp_path / "modulo.py")}),
        ("rilievo", {**RILIEVO_R, "criterio": -1}),
        ("rilievo", {**RILIEVO_R, "testo": "  "}),
        ("sonda", {**SONDA, "criterio": 0}),
        ("sonda", {**SONDA, "file": "test_che_non_c_e.py"}),
        ("sonda", {**SONDA, "nome": ""}),
    ]
    for nome, argomenti in rifiutate:
        assert esito.chiama(nome, argomenti, "lettore", str(file))["isError"], argomenti
    assert righe_della_lettura(file) == []

    assert not esito.chiama("rilievo", RILIEVO_R, "lettore", str(file))["isError"]
    assert not esito.chiama("letto", {"riepilogo": "un rilievo"}, "lettore", str(file))["isError"]
    chiuso = file.read_text(encoding="utf-8")

    for nome, argomenti in (("rilievo", RILIEVO_N), ("sonda", SONDA),
                            ("letto", {"riepilogo": "un altro"})):
        assert esito.chiama(nome, argomenti, "lettore", str(file))["isError"], nome
    assert file.read_text(encoding="utf-8") == chiuso
    assert righe_della_lettura(file) == [{"strumento": "rilievo", **RILIEVO_R}]


# --- Criterio 2: una sonda verde sulla base è un rilievo R --------------------

MODULO = "def somma(a, b):\n    return a + b\n"

SONDE = """import modulo


def test_la_somma_c_e_gia():
    assert modulo.somma(2, 3) == 5


def test_la_differenza():
    assert modulo.differenza(5, 3) == 2
"""


def pbi_con_criteri(*criteri: str) -> str:
    """PBI-610 con lo Scope che nomina il suo file e i `criteri` nella Verifica."""
    return ("# PBI-610: una prova\n\n**Scope**\n\n"
            "- `backlog/PBI-610-una-prova.md` — questo file.\n- `modulo.py`\n\n"
            "## Dipendenze\n\n- Bloccato da: nessuno.\n\n## Verifica\n\n"
            + "".join(f"{c}\n" for c in criteri))


DUE_CRITERI = pbi_con_criteri("- [ ] **La somma.** (pytest)", "- [ ] **La differenza.** (pytest)")


def lettore_finto(monkeypatch, file: dict[str, str], chiamate: list[dict], letto: bool = True):
    """Un `esegui` che fa il Lettore: scrive `file` nel suo `cwd`, le `chiamate` valide in
    `<esito>.lettura.jsonl` e, con `letto`, l'esito che il server scriverebbe. Ogni altro
    comando (git, pytest) va all'`esegui` vero. I lanci del Lettore restano in `.lanci`,
    come `(comando, cwd, timeout)`."""
    vero = runner.esegui
    lanci: list[tuple[list[str], Path, float]] = []

    def _esegui(cmd, cwd, timeout=7200, **k):
        ruolo, file_esito = ruolo_ed_esito(cmd)
        if ruolo != "lettore":
            return vero(cmd, cwd, timeout, **k)
        lanci.append((cmd, Path(cwd), timeout))
        for nome, testo in file.items():
            (Path(cwd) / nome).write_text(testo, encoding="utf-8")
        Path(f"{file_esito}.lettura.jsonl").write_text(
            "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chiamate), encoding="utf-8")
        if letto:
            voci = [{k: v for k, v in c.items() if k != "strumento"} for c in chiamate]
            file_esito.write_text(json.dumps({
                "esito": "letto", "riepilogo": "letto",
                "rilievi": [v for v, c in zip(voci, chiamate) if c["strumento"] == "rilievo"],
                "sonde": [v for v, c in zip(voci, chiamate) if c["strumento"] == "sonda"],
            }, ensure_ascii=False), encoding="utf-8")
        return 0, "letto"

    _esegui.lanci = lanci
    monkeypatch.setattr(runner, "esegui", _esegui)
    return _esegui


def preverifica_col_lettore(tmp_path, monkeypatch, testo_del_pbi: str, file: dict[str, str],
                            chiamate: list[dict], letto: bool = True):
    """`asdlc-runner PBI-610 --preverifica --lettore` su un clone con `modulo.py` alla base:
    il codice d'uscita, il rapporto, il clone, il Lettore finto, e i rami e lo stato del
    clone com'erano prima del lancio."""
    clone, _ = clone_con_la_base(tmp_path, {"modulo.py": MODULO,
                                            "backlog/PBI-610-una-prova.md": testo_del_pbi})
    prima = sh(clone, "branch"), sh(clone, "status", "--porcelain")
    monkeypatch.setattr(runner, "REPO", clone)
    for nome in ("stacca", "lucchetto", "esegui_pbi"):
        monkeypatch.setattr(runner, nome, lambda *a, _n=nome, **k: pytest.fail(f"{_n} non si chiama"))
    agente = lettore_finto(monkeypatch, file, chiamate, letto)

    codice = lancia(["PBI-610", "--preverifica", "--lettore"], monkeypatch)

    rapporti = sorted(runner.LOG_DIR.glob("*-PBI-610-preverifica.json"))
    assert len(rapporti) == 1, list(runner.LOG_DIR.iterdir())
    return codice, json.loads(rapporti[0].read_text(encoding="utf-8")), clone, agente, prima


def test_una_sonda_verde_sulla_base_e_un_rilievo_r_e_il_lettore_lavora_fuori_dal_checkout(
        tmp_path, monkeypatch):
    montati = runner.USA_E_GETTA["montati"]
    sonde = [{"strumento": "sonda", "criterio": 1, "file": "test_sonde.py",
              "nome": "test_la_somma_c_e_gia"},
             {"strumento": "sonda", "criterio": 2, "file": "test_sonde.py",
              "nome": "test_la_differenza"}]

    codice, rapporto, clone, agente, (rami, stato) = preverifica_col_lettore(
        tmp_path, monkeypatch, DUE_CRITERI, {"test_sonde.py": SONDE}, sonde)

    assert codice == 1
    assert rapporto["lettore"] == "letto"
    assert [(s["criterio"], s["esito"]) for s in rapporto["sonde"]] == [(1, "verde"), (2, "rosso")]
    assert [(r["domanda"], r["criterio"]) for r in rapporto["rilievi"]] == [("R", 1)]
    assert "nato verde" in rapporto["rilievi"][0]["testo"]
    assert len(agente.lanci) == 1 and agente.lanci[0][1] != clone
    assert sh(clone, "branch") == rami and sh(clone, "status", "--porcelain") == stato
    assert not (clone / "test_sonde.py").exists()
    assert runner.USA_E_GETTA["montati"] == montati + 1
    assert runner.USA_E_GETTA["montati"] == runner.USA_E_GETTA["smontati"]


# --- Criterio 3: senza `letto` la lettura è `senza esito` ---------------------


def test_senza_letto_la_lettura_e_senza_esito_coi_rilievi_e_senza_sonde(tmp_path, monkeypatch):
    """Decisione 2: i rilievi del `.jsonl` entrano lo stesso nel rapporto, marcati
    `"lettore": "senza esito"`, ma le sonde non si eseguono — anche quella che il
    Lettore ha nominato prima di fermarsi."""
    rilievo = {"domanda": "D", "criterio": 0, "testo": "manca una decisione",
               "evidenza": "modulo.py"}
    chiamate = [{"strumento": "rilievo", **rilievo},
                {"strumento": "sonda", "criterio": 1, "file": "test_sonde.py",
                 "nome": "test_la_somma_c_e_gia"}]

    codice, rapporto, _, _, _ = preverifica_col_lettore(
        tmp_path, monkeypatch, DUE_CRITERI, {"test_sonde.py": SONDE}, chiamate, letto=False)

    assert codice == 1
    assert rapporto["lettore"] == "senza esito"
    assert rapporto["rilievi"] == [{**rilievo, "lettore": "senza esito"}]
    assert rapporto["sonde"] == []


def test_senza_letto_e_senza_rilievi_il_comando_esce_1(tmp_path, monkeypatch):
    """Decisione 7: il comando esce 1 con un rilievo, oppure con `senza esito`. Una
    lettura che non ha chiamato niente non dice che il PBI è pronto."""
    codice, rapporto, _, _, _ = preverifica_col_lettore(
        tmp_path, monkeypatch, DUE_CRITERI, {}, [], letto=False)

    assert (rapporto["lettore"], rapporto["rilievi"]) == ("senza esito", [])
    assert codice == 1


# --- Criterio 4: un criterio senza sonda è un avviso --------------------------

TRE_CRITERI = pbi_con_criteri(
    "- [ ] **La differenza.** (pytest)",
    "- [ ] **La somma resta com'è.** Il comportamento c'è già:\n"
    "      è una Guardia, e non ha un test nuovo.",
    "- [ ] **Il prodotto.** (pytest)")

UNA_SONDA = [{"strumento": "sonda", "criterio": 1, "file": "test_sonde.py",
              "nome": "test_la_differenza"}]


def test_un_criterio_senza_sonda_e_un_avviso_e_non_un_rilievo(tmp_path, monkeypatch):
    codice, rapporto, _, _, _ = preverifica_col_lettore(
        tmp_path, monkeypatch, TRE_CRITERI, {"test_sonde.py": SONDE}, UNA_SONDA)

    assert "criterio 3 senza sonda" in rapporto["avvisi"]
    assert rapporto["rilievi"] == []
    assert codice == 0


def test_un_criterio_dichiarato_guardia_non_ha_l_avviso_senza_sonda(tmp_path, monkeypatch):
    """Decisione 5: è guardia un criterio il cui testo intero, righe rientrate comprese,
    contiene «guardia» o «nato verde», senza distinguere maiuscole e minuscole. Il
    secondo criterio lo dice su una riga rientrata, con la maiuscola."""
    _, rapporto, _, _, _ = preverifica_col_lettore(
        tmp_path, monkeypatch, TRE_CRITERI, {"test_sonde.py": SONDE}, UNA_SONDA)

    assert [a for a in rapporto["avvisi"] if "senza sonda" in a] == ["criterio 3 senza sonda"]


# --- Criterio 5: il Lettore ha il suo tetto e la sua traccia ------------------


def sezione_lettore(testo: str = ""):
    """La sezione `[lettore]` della configurazione del progetto di prova con sopra `testo`."""
    toml = (PROGETTO / "asdlc.toml").read_text(encoding="utf-8") + "\n" + testo
    return config.interpreta(tomllib.loads(toml), "asdlc.toml").lettore


def test_la_sezione_lettore_ha_i_default_opus_e_30_minuti():
    lettore = sezione_lettore()

    assert (lettore.modello, lettore.minuti) == ("opus", 30)


def test_il_lettore_usa_il_suo_tetto_e_cerca_la_traccia_nelle_sessioni_del_suo_albero(
        tmp_path, monkeypatch):
    """`invoca_agente("lettore", …, cwd=albero)`: il tetto è `[lettore].minuti`, non quello
    del Critic, il modello è `[lettore].modello`, e la sessione si cerca nella cartella
    di Claude Code di `albero`, dove `claude` lanciato da lì la scrive."""
    di_prima = runner.CFG
    runner.configura(dataclasses.replace(
        di_prima, lettore=sezione_lettore('[lettore]\nmodello = "sonnet"\nminuti = 7\n')))
    monkeypatch.setattr(runner, "MINUTI_CRITIC", 3)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
    albero = tmp_path / "albero"
    albero.mkdir()
    sessioni = (tmp_path / "home" / ".claude" / "projects"
                / re.sub(r"[^A-Za-z0-9]", "-", str(albero)))
    sessioni.mkdir(parents=True)
    lanci = []

    def _esegui(cmd, cwd, timeout=7200, **k):
        lanci.append((cmd, Path(cwd), timeout))
        (sessioni / f"{cmd[cmd.index('--session-id') + 1]}.jsonl").write_text(
            json.dumps({"type": "user", "message": {"role": "user", "content": "x"}}) + "\n",
            encoding="utf-8")
        return 0, ""

    monkeypatch.setattr(runner, "esegui", _esegui)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("x", encoding="utf-8")
    try:
        invocazione = runner.invoca_agente("lettore", runner.comando_del_lettore(), prompt,
                                           tmp_path / "esito.json", cwd=albero)
    finally:
        runner.configura(di_prima)

    [(cmd, cwd, timeout)] = lanci
    assert cwd == albero
    assert timeout == 7 * 60
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert invocazione.registro["traccia"] is not None, invocazione.registro.get("traccia_nota")


# --- Decisione 4: le sonde che non si eseguono --------------------------------


def test_una_sonda_che_non_e_un_test_o_non_si_trova_nel_file_e_un_rilievo_r(tmp_path, monkeypatch):
    """Decisione 4: un file che `linguaggio_del_test()` non riconosce, e un nome che nel
    file non c'è (l'orfano di `comandi_dei_test`, che torna al criterio dal file della
    sonda), danno tutti e due un rilievo `R` con `ESITI_MANCATI["nessuno"]`."""
    sonde = [{"strumento": "sonda", "criterio": 1, "file": "note.txt", "nome": "test_nota"},
             {"strumento": "sonda", "criterio": 2, "file": "test_sonde.py",
              "nome": "test_che_non_c_e"}]

    codice, rapporto, _, _, _ = preverifica_col_lettore(
        tmp_path, monkeypatch, DUE_CRITERI, {"note.txt": "una nota\n", "test_sonde.py": SONDE},
        sonde)

    assert [(s["criterio"], s["esito"]) for s in rapporto["sonde"]] == [(1, "nessuno"),
                                                                       (2, "nessuno")]
    assert [(r["domanda"], r["criterio"], r["testo"]) for r in rapporto["rilievi"]] == [
        ("R", 1, runner.ESITI_MANCATI["nessuno"]), ("R", 2, runner.ESITI_MANCATI["nessuno"])]
    assert codice == 1
