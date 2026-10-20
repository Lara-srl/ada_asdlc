"""La pre-verifica dei PBI in codice (`backlog/PBI-520`).

`asdlc-runner PBI-N --preverifica` legge il file del PBI alla base e scrive un
rapporto: i rilievi di forma, che fanno uscire 1, e gli avvisi, che non cambiano
il codice d'uscita. Su `main` le funzioni e il flag non esistono: i test le
prendono con `getattr(runner, "…", None)` e un `assert`, così il rosso è per
asserzione e non un errore di import.

Il runner si carica per nome, `asdlc.runner`: `conftest.py` mette `tools/` sul
`sys.path` (PBI-383).
"""

import importlib
import subprocess
from pathlib import Path

import pytest

PROGETTO = Path(__file__).resolve().parent / "dati" / "progetto"

runner = importlib.import_module("asdlc.runner")
# Come in `test_asdlc_runner.py`: la radice e la configurazione sono quelle del
# progetto di prova, e l'import non legge `asdlc.toml` (PBI-382, PBI-394).
runner.REPO = PROGETTO
runner.configura(runner.asdlc_config.carica(PROGETTO))


def pbi(scope: str | None = "- `backlog/PBI-520-la-preverifica-in-codice.md` — questo file.",
        verifica: str | None = "- [ ] **Un criterio.** Con la sua riga rientrata\n"
                               "      sotto (pytest).") -> str:
    """Il testo di un PBI col formato del backlog: lo Scope e la Verifica si tolgono
    passando `None`."""
    parti = ["# PBI-520: una prova\n", "## Direttiva\n", "Una direttiva.\n"]
    if scope is not None:
        parti.append(f"**Scope**\n\n{scope}\n")
    parti += ["## Dipendenze\n", "- Bloccato da: nessuno.\n"]
    if verifica is not None:
        parti.append(f"## Verifica\n\n{verifica}\n")
    parti += ["## Protocollo di rifinitura\n", "- [ ] una casella fuori dalla Verifica\n"]
    return "\n".join(parti)


@pytest.mark.parametrize(
    "testo, attesi",
    [
        pytest.param(pbi(verifica=None), 1, id="senza-verifica"),
        pytest.param(pbi(verifica="Solo prosa, nessuna casella."), 1, id="verifica-senza-criteri"),
        pytest.param(pbi(scope=None), 1, id="senza-scope"),
        pytest.param(pbi(scope="- `tools/asdlc/runner.py`"), 1, id="scope-senza-il-pbi"),
        pytest.param(pbi(scope="- `backlog/PBI-520-…md` — abbreviato"), 0, id="pbi-abbreviato"),
        pytest.param(pbi(scope="- `backlog/PBI-52-un-altro.md`"), 1, id="pbi-52-non-e-pbi-520"),
    ],
)
def test_i_quattro_rilievi_di_forma(testo, attesi):
    forma_del_pbi = getattr(runner, "forma_del_pbi", None)
    assert forma_del_pbi is not None, "runner.forma_del_pbi non esiste"

    rilievi = forma_del_pbi(testo, "PBI-520")

    assert len(rilievi) == attesi, rilievi
    assert all(r.domanda == "forma" and r.criterio is None for r in rilievi), rilievi


def sh(cwd: Path, *args: str) -> str:
    """`git` vero in `cwd`. I commit di preparazione saltano gli hook (`--no-verify`
    dove si committa): il pre-commit della fase lancerebbe il runner vero."""
    p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false",
                        *args], cwd=cwd, capture_output=True, text=True, check=True)
    return p.stdout.strip()


DIPENDENZA_APERTA = """# PBI-600: una dipendenza aperta

## Verifica

- [x] **Un criterio chiuso.**
- [ ] **Un criterio ancora aperto.**
"""

DIPENDENZA_CHIUSA = """# PBI-601: una dipendenza chiusa

## Verifica

- [x] **L'unico criterio, chiuso.**

## Protocollo di rifinitura

- [ ] una casella fuori dalla Verifica, che non conta
"""

FILE_DELLA_BASE = {
    "backlog/PBI-600-una-dipendenza-aperta.md": DIPENDENZA_APERTA,
    "backlog/PBI-601-una-dipendenza-chiusa.md": DIPENDENZA_CHIUSA,
    "backlog/PBI-610-una-prova.md": "# PBI-610: una prova\n",
    "tools/asdlc/runner.py": "",
    "tools/tests/test_asdlc_prova.py": "",
}


def clone_con_la_base(tmp_path: Path) -> tuple[Path, str]:
    """Un remoto bare e un suo clone, con `FILE_DELLA_BASE` in `origin/main`: il
    clone e lo sha della base."""
    remoto, clone = tmp_path / "remoto.git", tmp_path / "clone"
    sh(tmp_path, "init", "-q", "--bare", str(remoto))
    sh(tmp_path, "clone", "-q", str(remoto), str(clone))
    for nome, testo in FILE_DELLA_BASE.items():
        (clone / nome).parent.mkdir(parents=True, exist_ok=True)
        (clone / nome).write_text(testo, encoding="utf-8")
    sh(clone, "add", "-A")
    sh(clone, "commit", "-q", "--no-verify", "-m", "docs: la base")
    sh(clone, "push", "-q", "origin", "main")
    return clone, sh(clone, "rev-parse", "origin/main")


def pbi_610(scope: str = "", bloccato_da: str = "nessuno.") -> str:
    """Il testo di PBI-610, con lo Scope che nomina il suo file e `runner.py`."""
    return (
        "# PBI-610: una prova\n\n**Scope**\n\n"
        "- `backlog/PBI-610-una-prova.md` — questo file.\n"
        f"{scope or '- `tools/asdlc/runner.py`'}\n\n"
        f"## Dipendenze\n\n- Bloccato da: {bloccato_da}\n\n"
        "## Verifica\n\n- [ ] **Un criterio.** (pytest)\n"
    )


@pytest.mark.parametrize(
    "testo, attesi",
    [
        pytest.param(pbi_610("- `tools/asdlc/runner.py`\n- `tools/asdlc/manca.py`"), 1,
                     id="percorso-che-non-c-e"),
        pytest.param(pbi_610("- `tools/asdlc/runner.py`\n- `tools/asdlc/manca.py` — **nuovo**"), 0,
                     id="percorso-detto-nuovo"),
        pytest.param(pbi_610(bloccato_da="`PBI-600`."), 1, id="dipendenza-aperta"),
        pytest.param(pbi_610(bloccato_da="`PBI-601`."), 0, id="casella-fuori-dalla-verifica"),
        pytest.param(pbi_610("- `tools/tests/test_asdlc_prova.py`"), 1, id="scope-di-soli-test"),
    ],
)
def test_gli_avvisi_della_base_non_sono_rilievi(testo, attesi, tmp_path, monkeypatch):
    avvisi_della_base = getattr(runner, "avvisi_della_base", None)
    assert avvisi_della_base is not None, "runner.avvisi_della_base non esiste"
    clone, base = clone_con_la_base(tmp_path)
    monkeypatch.setattr(runner, "REPO", clone)

    avvisi = avvisi_della_base(testo, "PBI-610", base)

    assert len(avvisi) == attesi, avvisi
    assert all(isinstance(a, str) for a in avvisi), avvisi
