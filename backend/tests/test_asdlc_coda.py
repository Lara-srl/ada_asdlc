"""Il tick della coda dei PBI (`backlog/PBI-350`).

Qui si guarda la **decisione**, non l'effetto: `prossimo()` è una funzione pura —
voci dentro, un esito fuori — e nessuno di questi test avvia un giro. Un test che
lancia il runner non è un test, è una notte.

`tools/` non è un pacchetto installato e non deve diventarlo per un test: si
carica il modulo dal suo percorso, come fa `test_importa_storico.py`.
"""

import fcntl
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("asdlc_coda", REPO / "tools" / "asdlc_coda.py")
coda = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = coda
_spec.loader.exec_module(coda)


def test_un_giro_in_corso_rende_occupato_senza_guardare_la_coda():
    """La testa sarebbe da lanciare, e non si lancia lo stesso.

    Un albero, un agente: il 24→25/08 due agenti sullo stesso worktree sono
    costati un PBI intero, e qui il secondo lo avvierebbe `cron`, che non guarda
    lo schermo.
    """
    decisione = coda.prossimo(
        [coda.VocePbi("PBI-337")], mergiati=set(), rami=set(), occupato=True
    )

    assert decisione == coda.Occupato()


def test_la_testa_della_coda_senza_ramo_su_origin_si_lancia():
    """Nessun giro in corso, il PBI in testa non è mai partito: si lancia."""
    decisione = coda.prossimo(
        [coda.VocePbi("PBI-337")], mergiati=set(), rami=set(), occupato=False
    )

    assert decisione == coda.Lancia("PBI-337")


def test_la_testa_gia_mergiata_si_consuma_e_tocca_alla_voce_dopo():
    """È il gesto per cui il tick esiste: il merge del 337 fa partire il 338.

    Il ramo che il 337 si è lasciato dietro non lo trattiene: un ramo su `origin`
    parla solo **in assenza** di merge (PBI-350, punto 1).
    """
    decisione = coda.prossimo(
        [coda.VocePbi("PBI-337"), coda.VocePbi("PBI-338")],
        mergiati={"PBI-337"},
        rami={"PBI-337"},
        occupato=False,
    )

    assert decisione == coda.Lancia("PBI-338")


def test_la_testa_con_un_ramo_su_origin_e_senza_merge_si_attende():
    """Il giro c'è già stato e non è finito in `main`: tocca a un umano.

    `chiudi()` pubblica su ogni stato che interrompe, quindi un ramo su `origin`
    senza merge è un giro fermo — mai un giro da rifare. È il test che impedisce
    il doppione: rilanciarlo di notte darebbe due rami sullo stesso PBI e il
    lavoro fermo resterebbe fermo.
    """
    decisione = coda.prossimo(
        [coda.VocePbi("PBI-337"), coda.VocePbi("PBI-338")],
        mergiati=set(),
        rami={"PBI-337"},
        occupato=False,
    )

    assert decisione == coda.Attende("PBI-337")


def test_una_barriera_ferma_la_coda_e_le_voci_dopo_non_si_guardano():
    """Il PBI dietro la barriera sarebbe lanciabile, e non si lancia.

    Una riga `‖` non è un PBI: è un gesto umano che deve venire prima. Senza
    questo esito la prima voce non-PBI della coda diventerebbe un PBI
    inesistente lanciato di notte.
    """
    decisione = coda.prossimo(
        [coda.VoceBarriera("la ripassata dell'import"), coda.VocePbi("PBI-337")],
        mergiati=set(),
        rami=set(),
        occupato=False,
    )

    assert decisione == coda.Barriera("la ripassata dell'import")


def test_una_coda_tutta_mergiata_e_finita():
    """Non c'è più niente da lanciare, e non è un guasto: è un lotto chiuso."""
    decisione = coda.prossimo(
        [coda.VocePbi("PBI-337"), coda.VocePbi("PBI-338")],
        mergiati={"PBI-337", "PBI-338"},
        rami=set(),
        occupato=False,
    )

    assert decisione == coda.Finita()


CODA_FINTA = """# La coda dei PBI

L'ordine in cui i PBI vanno lanciati.

**Come si legge una riga**

- `- PBI-337` — un PBI da lanciare.
- `- ‖ testo` — una **barriera**: un gesto umano.

## La coda

- PBI-337

⚠️ Una riga di prosa fra una voce e l'altra, che spiega perché quest'ordine.

- ‖ la ripassata dell'import
- PBI-338

## Fuori dalla coda

- **PBI-349** — ⏸ sospeso: non rientra finché la decisione non c'è.
"""


def test_le_voci_escono_nellordine_del_file_e_la_prosa_resta_fuori():
    """Il documento è anche l'ingresso del programma, e intorno alle voci c'è prosa.

    Le righe insidiose sono quelle che *nominano* la forma di una voce senza
    esserlo — la legenda in cima e la sezione «Fuori dalla coda», dove PBI-349 è
    scritto in grassetto perché è sospeso.
    """
    voci = coda.leggi_voci(CODA_FINTA)

    assert voci == [
        coda.VocePbi("PBI-337"),
        coda.VoceBarriera("la ripassata dell'import"),
        coda.VocePbi("PBI-338"),
    ]


def test_la_coda_vera_si_legge():
    """Il collaudo su `backlog/CODA.md`, che è il file che il tick eseguirà.

    Le asserzioni sono sulle proprietà e non sul contenuto: la coda la riscrive
    Francesco quando vuole, e un test che si rompe a ogni riordino verrebbe
    spento. Che ogni voce abbia il suo PBI in `backlog/` invece resta vero
    sempre, ed è ciò che morde se una riga di prosa diventasse una voce.
    """
    voci = coda.leggi_voci((REPO / "backlog" / "CODA.md").read_text(encoding="utf-8"))

    assert voci, "CODA.md non ha nessuna voce: il tick non avrebbe niente da eseguire"
    nomi = [v.pbi for v in voci if isinstance(v, coda.VocePbi)]
    assert len(nomi) == len(set(nomi)), f"un PBI compare due volte in coda: {nomi}"
    for nome in nomi:
        assert list(REPO.glob(f"backlog/{nome}-*.md")), f"{nome} non ha un file in backlog/"


def mondo(pr_mergiate=(), rami_su_origin=()):
    """Un `esegui()` finto: `gh` e `git` rispondono nella forma in cui rispondono davvero.

    Un comando non previsto fa fallire il test invece di rendere una risposta
    vuota: qui si sta misurando *cosa* il tick chiede al mondo, e una risposta
    di comodo nasconderebbe una domanda in più.
    """

    def esegui(cmd, cwd):
        if cmd[0] == "gh":
            return 0, json.dumps([{"title": t} for t in pr_mergiate])
        if cmd[0] == "git":
            return 0, "".join(
                f"{'0' * 40}\trefs/heads/{r}\n" for r in rami_su_origin
            )
        raise AssertionError(f"comando non previsto: {cmd}")

    return esegui


def scrivi_coda(tmp_path, righe):
    """Un finto checkout con dentro la sua `backlog/CODA.md`."""
    repo = tmp_path / "repo"
    (repo / "backlog").mkdir(parents=True)
    (repo / "backlog" / "CODA.md").write_text(righe, encoding="utf-8")
    return repo


def test_la_decisione_si_compone_dalle_pr_mergiate_e_dai_rami_su_origin(
    tmp_path, monkeypatch
):
    """Lo stato non sta su disco: lo raccontano `gh` e `git`.

    Il merge si riconosce dal **titolo** della PR — la forma che `apri_pr()`
    costruisce — perché regge sia al merge di commit sia allo squash, che il nome
    del ramo lo perde. Il ramo si riconosce lo stesso col suffisso di un secondo
    giro.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n- PBI-338\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    monkeypatch.setattr(
        coda,
        "esegui",
        mondo(
            pr_mergiate=["PBI-337: il tipo di lavoro eseguito"],
            rami_su_origin=["pbi/pbi-338-giro2"],
        ),
    )

    assert coda.decidi(repo, albero) == coda.Attende("PBI-338")


def nessun_comando(cmd, cwd):
    raise AssertionError(f"il tick non doveva chiedere niente al mondo: {cmd}")


def test_il_lucchetto_tenuto_nel_worktree_ferma_il_tick(tmp_path, monkeypatch):
    """Il lucchetto del runner è la prova che qualcuno sta già lavorando lì.

    `esegui()` qui fa fallire il test se viene chiamato: davanti a un giro in
    corso il tick non deve nemmeno interrogare `gh`, perché qualunque risposta
    porterebbe a un secondo agente sullo stesso albero.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    (albero / "runs").mkdir(parents=True)
    lucchetto = albero / "runs" / ".runner.lock"
    lucchetto.touch()
    monkeypatch.setattr(coda, "esegui", nessun_comando)

    with lucchetto.open("r+") as tenuto:
        fcntl.flock(tenuto, fcntl.LOCK_EX | fcntl.LOCK_NB)

        assert coda.decidi(repo, albero) == coda.Occupato()


def test_un_runner_vivo_nellalbero_ferma_il_tick_anche_senza_lucchetto(
    tmp_path, monkeypatch
):
    """La rete sotto al lucchetto: chi lavora lì si vede da `/proc`.

    Il lucchetto lo prende il runner; una sessione avviata a mano no, e nemmeno
    un giro più vecchio del lucchetto. L'unico segnale comune ai due è **dove**
    lavorano, ed è la stessa lettura di `agenti_estranei()`.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    finto_proc = tmp_path / "proc"
    (finto_proc / "4242").mkdir(parents=True)
    (finto_proc / "4242" / "cwd").symlink_to(albero)
    (finto_proc / "4242" / "cmdline").write_bytes(
        b"python3\x00tools/asdlc_runner.py\x00PBI-337\x00"
    )
    monkeypatch.setattr(coda, "PROC", finto_proc)
    monkeypatch.setattr(coda, "esegui", nessun_comando)

    assert coda.decidi(repo, albero) == coda.Occupato()


def test_un_gh_che_non_risponde_non_produce_lancia(tmp_path, monkeypatch):
    """Nel dubbio non si lancia, e si scrive perché.

    Un tick che sbaglia per eccesso di prudenza costa dieci minuti fino al tick
    dopo; uno che lancia sul dubbio costa un giro e un ramo da ripulire.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()

    def gh_rotto(cmd, cwd):
        if cmd[0] == "gh":
            return 1, "could not connect to github.com"
        return 0, ""

    monkeypatch.setattr(coda, "esegui", gh_rotto)

    decisione = coda.decidi(repo, albero)

    assert isinstance(decisione, coda.Barriera)
    assert "gh" in decisione.testo


def test_una_coda_illeggibile_non_produce_lancia(tmp_path, monkeypatch):
    """Senza la coda non ci sono ordini, e senza ordini non si lancia niente."""
    repo = tmp_path / "repo"
    (repo / "backlog").mkdir(parents=True)  # e nessun CODA.md dentro
    albero = tmp_path / "albero"
    albero.mkdir()
    monkeypatch.setattr(coda, "esegui", mondo())

    decisione = coda.decidi(repo, albero)

    assert isinstance(decisione, coda.Barriera)
    assert "CODA.md" in decisione.testo
