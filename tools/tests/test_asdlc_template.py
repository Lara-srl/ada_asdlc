"""I modelli di `template/` (`backlog/PBI-500`), la configurazione d'esempio
(`backlog/PBI-501`) e il metodo (`backlog/PBI-502`).

`template/` è la cartella che un progetto nuovo copia alla nascita. Questi test
leggono quella del repository che li ospita, non il progetto di prova: per questo
portano il marcatore `progetto_ospite`. Delle intestazioni conta l'ordine, e si
confrontano come lista; il testo sotto è libero, salvo dove un criterio lo dice.

I file che il pacchetto o `git` leggono si provano in una cartella **nata** dalla
copia di `template/` (`nasci()`), non qui: qui `.gitignore` e `asdlc.toml` sono
quelli di questo repository.
"""

import csv
import importlib
import itertools
import re
import shutil
import subprocess
from pathlib import Path

import pytest

asdlc_config = importlib.import_module("asdlc.config")
runner = importlib.import_module("asdlc.runner")

RE_INTESTAZIONE = re.compile(r"^#+ .*$", re.MULTILINE)


def radice() -> Path:
    return asdlc_config.radice(Path(__file__).resolve().parent)


def template() -> Path:
    return radice() / "template"


def intestazioni(testo: str) -> list[str]:
    return RE_INTESTAZIONE.findall(testo)


def parte_metodo(testo: str) -> list[str]:
    """Le righe di `AGENTS.md` dalla riga `## Metodo` esclusa alla riga
    `## Dominio` esclusa (PBI-502, decisione 2)."""
    righe = testo.splitlines()
    return righe[righe.index("## Metodo") + 1:righe.index("## Dominio")]


@pytest.mark.progetto_ospite
def test_la_costituzione_del_template_ha_il_metodo_di_qui_e_un_dominio_da_scrivere():
    percorso = template() / "AGENTS.md"
    assert percorso.is_file(), percorso

    testo = percorso.read_text(encoding="utf-8")
    qui = (radice() / "AGENTS.md").read_text(encoding="utf-8")
    dominio = testo.split("\n## Dominio\n", 1)[1]
    link = template() / "CLAUDE.md"

    assert parte_metodo(testo) == parte_metodo(qui)
    assert intestazioni(dominio) == [
        "### Toolchain",
        "### Confini di giudizio",
        "### Sorgenti",
        "### Scope dei commit",
    ]
    assert link.is_symlink(), link
    assert link.readlink() == Path("AGENTS.md")


@pytest.mark.progetto_ospite
@pytest.mark.parametrize("cartella", ["backlog", "decisions", "specs"])
def test_ogni_cartella_del_metodo_spiega_le_sue_regole_e_rimanda_al_suo_modello(cartella):
    percorso = template() / cartella / "README.md"
    assert percorso.is_file(), percorso

    testo = percorso.read_text(encoding="utf-8")

    assert "](TEMPLATE.md)" in testo
    assert (percorso.parent / "TEMPLATE.md").is_file()


# I dodici ADR di metodo (PBI-502, decisione 4). Una costante e non un glob su
# `decisions/`: è una decisione, e non si ricava dai file — `ADR-0028` di questo
# repository è di dominio e non si copia.
ADR_DI_METODO = ("0008", "0009", "0011", "0012", "0015", "0017",
                 "0020", "0021", "0022", "0024", "0026", "0027")


@pytest.mark.progetto_ospite
def test_gli_adr_di_metodo_sono_nel_template_identici_e_numerati_come_qui():
    readme = template() / "decisions" / "README.md"
    assert readme.is_file(), readme

    testo = readme.read_text(encoding="utf-8")
    originali = []
    for numero in ADR_DI_METODO:
        originale, = (radice() / "decisions").glob(f"ADR-{numero}-*.md")
        originali.append(originale)
    copie = [template() / "decisions" / o.name for o in originali]

    assert [c.name for c in copie if not c.is_file()] == []
    assert [c.name for c, o in zip(copie, originali)
            if c.read_bytes() != o.read_bytes()] == []
    assert [o.name for o in originali if f"]({o.name})" not in testo] == []
    assert re.search(r"prossimo ADR[^\n]*\b0028\b", testo), testo


@pytest.mark.progetto_ospite
def test_il_modello_dei_pbi_ha_le_sezioni_del_formato_nell_ordine():
    percorso = template() / "backlog" / "TEMPLATE.md"
    assert percorso.is_file(), percorso

    testo = percorso.read_text(encoding="utf-8")
    titolo, *sezioni = intestazioni(testo)

    assert titolo.startswith("# PBI-XXX: ")
    assert sezioni == [
        "## Direttiva",
        "## ✅ Deciso",
        "## Il giro N, e cosa si riprende",
        "## Dipendenze",
        "## Contesto",
        "## Verifica",
        "## Protocollo di rifinitura",
    ]
    direttiva = testo.split("## Direttiva", 1)[1].split("\n## ", 1)[0]
    assert "**Scope**" in direttiva.splitlines()
    assert "backlog/PBI-XXX-" in direttiva.split("**Scope**", 1)[1]
    verifica = testo.split("## Verifica", 1)[1].split("\n## ", 1)[0].splitlines()
    assert any(riga.startswith("- [ ]") for riga in verifica)
    assert any(riga.startswith("**Non regressione:**") for riga in verifica)


@pytest.mark.progetto_ospite
def test_il_modello_degli_adr_porta_la_firma_vuota_e_le_quattro_domande():
    percorso = template() / "decisions" / "TEMPLATE.md"
    assert percorso.is_file(), percorso

    testo = percorso.read_text(encoding="utf-8")
    titolo, *sezioni = intestazioni(testo)

    assert titolo.startswith("# ADR-NNNN: ")
    assert "**Ratificata da** … **il** …" in testo.split("\n## ", 1)[0]
    assert sezioni == [
        "## Contesto",
        "## Decisione",
        "## Conseguenze",
        "## Alternative considerate",
    ]
    decisione = testo.split("## Decisione", 1)[1].split("\n## ", 1)[0]
    voci = re.findall(r"^\d+\. (.*)$", decisione, re.MULTILINE)
    domande = ["cosa si controlla", "quando", "cosa conta come prova", "cosa succede se manca"]
    assert len(voci) == len(domande), voci
    assert [v.startswith(f"**{d}**") for v, d in zip(voci, domande)] == [True] * 4, voci


@pytest.mark.progetto_ospite
def test_il_modello_delle_spec_ha_le_sezioni_di_quello_di_partenza_senza_le_fasi():
    percorso = template() / "specs" / "TEMPLATE.md"
    assert percorso.is_file(), percorso

    testo = percorso.read_text(encoding="utf-8")
    titolo, *sezioni = intestazioni(testo)

    assert titolo.startswith("# Feature: ")
    assert sezioni == [
        "## Blueprint",
        "### Contesto",
        "### Architettura",
        "### Vincoli",
        "## Contratto",
        "### Definition of Done",
        "### Guardie di regressione",
        "### Scenari",
        "### Domande aperte",
    ]
    assert "Fase:" not in testo
    assert "e2e/contract.ts" not in testo


@pytest.mark.progetto_ospite
def test_il_modello_della_pr_chiede_le_tre_cose_dell_accettazione_umana():
    percorso = template() / ".github" / "PULL_REQUEST_TEMPLATE.md"
    assert percorso.is_file(), percorso

    righe = percorso.read_text(encoding="utf-8").splitlines()
    caselle = [riga for riga in righe if riga.startswith("- [ ]")]

    assert any(riga.startswith("PBI:") for riga in righe)
    assert len(caselle) == 3, caselle
    assert any(all(chiave in riga for chiave, riga in zip(ordine, caselle))
               for ordine in itertools.permutations(("Verifica", "Scope", "spec"))), caselle


VIETATI = ("/home/", "/Users/", "~/", "aDa", "Barbara", "Oltre3D", "Carrozzeria")


@pytest.mark.progetto_ospite
def test_guardia_template_non_porta_percorsi_di_macchina_ne_nomi_di_ada():
    """Non regressione di PBI-500, ereditata dai PBI di `template/` che vengono
    dopo. Ne restano fuori, per nome, le copie degli ADR di metodo
    (`template/decisions/ADR-*.md`, PBI-502): nominano aDa perché è lì che le
    regole sono nate. Una cartella vuota non guarda niente, quindi un file ci
    deve essere."""
    radice = template()
    file = [p for p in sorted(radice.rglob("*"))
            if p.is_file() and not p.relative_to(radice).match("decisions/ADR-*.md")]

    assert file, f"{radice} non ha file"
    trovati = [(str(p.relative_to(radice)), v) for p in file
               for v in VIETATI if v in p.read_text(encoding="utf-8")]
    assert trovati == []


def nasci(tmp_path: Path) -> Path:
    """Un progetto nato da `template/`: la copia in `tmp_path`, `git init` e un
    commit iniziale (PBI-501, decisione 1). Una funzione e non una fixture: il
    test asserisce prima che il file del suo criterio c'è, e un'asserzione in
    una fixture sarebbe un errore di setup, non un fallimento. `--no-verify`
    per il difetto 92: un `core.hooksPath` globale non entra nella nascita."""
    nata = tmp_path / "progetto"
    shutil.copytree(template(), nata, symlinks=True)
    for comando in (["init", "-q"], ["add", "-A"],
                    ["-c", "user.name=nascita", "-c", "user.email=nascita@esempio.invalid",
                     "commit", "-q", "--no-verify", "-m", "nascita"]):
        subprocess.run(["git", "-C", str(nata), *comando], check=True,
                       capture_output=True, text=True)
    return nata


@pytest.mark.progetto_ospite
def test_un_progetto_nato_dal_template_carica_la_sua_configurazione(tmp_path):
    assert (template() / "asdlc.toml").is_file()
    nata = nasci(tmp_path)

    cfg = asdlc_config.carica(nata)

    assert cfg.gate
    assert [g.cwd for g in cfg.gate if not (nata / g.cwd).is_dir()] == []
    assert cfg.ambiente.pacchetto == asdlc_config.radice_comune(nata) / ".venv-asdlc"
    qui = asdlc_config.carica(asdlc_config.radice(Path(__file__).resolve().parent))
    assert cfg.ambiente.installa == qui.ambiente.installa


@pytest.mark.progetto_ospite
def test_il_registro_dei_tempi_del_template_ha_le_colonne_del_runner_e_nessuna_riga():
    percorso = template() / "runs" / "tempi.csv"
    assert percorso.is_file(), percorso

    righe = list(csv.reader(percorso.read_text(encoding="utf-8").splitlines()))

    assert righe == [runner.COLONNE_CSV]


@pytest.mark.progetto_ospite
@pytest.mark.parametrize("percorso, ignorato", [
    pytest.param(percorso, ignorato, id=percorso) for percorso, ignorato in (
        ("asdlc.local.toml", True),
        ("runs/giro.log", True),
        ("runs/giro.json", True),
        (".venv-asdlc/bin/asdlc-coda", True),
        ("runs/tempi.csv", False),
    )])
def test_un_progetto_nato_dal_template_ignora_gli_effimeri_e_versiona_il_registro(
        tmp_path, percorso, ignorato):
    assert (template() / ".gitignore").is_file()
    nata = nasci(tmp_path)

    detto = subprocess.run(["git", "-C", str(nata), "check-ignore", "-q", "--no-index",
                            percorso], capture_output=True, text=True)

    assert detto.returncode in (0, 1), detto.stderr
    assert (detto.returncode == 0) is ignorato


@pytest.mark.progetto_ospite
def test_la_ci_del_template_gira_i_comandi_dei_gate_del_template():
    """Letta come testo, senza una libreria YAML: la CI installa solo `pytest`
    (PBI-501, decisione 6)."""
    percorso = template() / ".github" / "workflows" / "ci.yml"
    assert percorso.is_file(), percorso

    testo = percorso.read_text(encoding="utf-8")
    eseguiti = [riga.split("run:", 1)[1].strip() for riga in testo.splitlines()
                if riga.strip().removeprefix("- ").startswith("run:")]
    gate = asdlc_config.leggi_toml(template() / "asdlc.toml")["gate"]

    assert gate
    assert [g["comando"] for g in gate
            if not any(" ".join(g["comando"]) in riga for riga in eseguiti)] == []
    assert "pull_request" in testo
    assert "push" in testo
