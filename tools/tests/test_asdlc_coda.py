"""Il tick della coda dei PBI (`backlog/PBI-350`).

Tre gruppi, dal centro verso fuori:

- **La decisione** — `prossimo()` è una funzione pura, voci dentro e un esito
  fuori, ed è dove stanno i cinque casi del PBI: occupato, attende, barriera,
  lancia, finita.
- **La lettura del mondo** — `leggi_voci()` su `CODA.md`, e `decidi()`, che
  compone la coda con ciò che `gh` e `git` raccontano. Qui `esegui()` è
  sostituito: nessuno di questi test parla davvero con GitHub.
- **Gli effetti** — `lancia()` e `main()`, guardati dai comandi che *devono*
  partire e da quelli che non devono. Nessun test avvia un giro: un test che
  lancia il runner non è un test, è una notte.

Il modulo si carica per nome, `asdlc.coda`: `conftest.py` mette `tools/` sul
`sys.path` (PBI-383).
"""

import contextlib
import fcntl
import importlib.util
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

coda = importlib.import_module("asdlc.coda")
# L'import non legge `asdlc.toml` (PBI-382): lo fa `main()` dalla cwd. Qui la
# configurazione è quella del repository di questo file, e i test chiamano
# `smista()`, cioè `main()` senza quel passo.
coda.REPO = REPO
coda.configura(coda.asdlc_config.carica(REPO))

# Il runner che il tick lancia: il comando installato nel venv di
# `[ambiente].pacchetto`, risolto dalla radice comune (PBI-384).
RUNNER_INSTALLATO = (coda.asdlc_config.radice_comune(REPO) / ".venv-asdlc" / "bin"
                     / "asdlc-runner")

# La verifica dell'ambiente prima del lancio (PBI-384) guarda il mondo: il venv del
# runner, il `PATH`, le versioni. Nei test si sostituisce, come `esegui`: su
# questa macchina e in CI il runner installato non c'è, e ogni lancio si
# fermerebbe lì. Il test della verifica la rimette con `ambiente_vero`.
MANCANZE_VERE = getattr(coda, "mancanze_dell_ambiente", None)


@pytest.fixture(autouse=True)
def ambiente_presente(monkeypatch):
    monkeypatch.setattr(coda, "mancanze_dell_ambiente", lambda worktree: [], raising=False)


@pytest.fixture
def ambiente_vero(monkeypatch):
    monkeypatch.setattr(coda, "mancanze_dell_ambiente", MANCANZE_VERE, raising=False)


# Il tick allinea il suo checkout a `origin/main` e reinstalla il pacchetto prima
# di decidere (PBI-392): sono comandi `git` e `pip` veri sul `--repo`. Nei test si
# sostituiscono come la verifica dell'ambiente, e i test del checkout rimettono
# le funzioni vere con `checkout_vero`.
VERE_DEL_CHECKOUT = {nome: getattr(coda, nome, None) for nome in ("allinea",)}


@pytest.fixture(autouse=True)
def checkout_allineato(monkeypatch):
    for nome in VERE_DEL_CHECKOUT:
        monkeypatch.setattr(coda, nome, lambda *a, **k: None, raising=False)


@pytest.fixture
def checkout_vero(monkeypatch):
    for nome, vera in VERE_DEL_CHECKOUT.items():
        monkeypatch.setattr(coda, nome, vera, raising=False)


@pytest.fixture(autouse=True)
def home_finta(tmp_path, monkeypatch):
    """`HOME` in una cartella temporanea, per ogni test (PBI-385). Il tick legge la
    pausa in `~/asdlc-tick.pausa`: con la `HOME` vera, la pausa di chi lancia i
    test li farebbe fallire, e un test che la creasse spegnerebbe il suo cron."""
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    return casa


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


def test_una_coda_senza_nemmeno_una_voce_e_finita():
    """Il lotto chiuso: `CODA.md` non ha più righe, e il tick non lancia niente.

    Dall'08/09 è lo stato vero del file — Fase 3 e Fase 4 sono ferme su una
    decisione commerciale, non su un vincolo tecnico — e va misurato qui, perché
    è la sola lettura in cui un `Finita` mancante diventerebbe un `None` passato
    a `chiudi()` di notte. Nasce verde e morde: cancellata l'ultima riga di
    `prossimo()` il test cade (`ADR-0022`).
    """
    decisione = coda.prossimo([], mergiati=set(), rami=set(), occupato=False)

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

    Che le voci ci **siano** invece non è una proprietà: una coda vuota è un
    lotto chiuso, non un guasto, e il tick che ci arriva dice `Finita` — è
    misurato in `test_una_coda_senza_nemmeno_una_voce_e_finita`. Pretenderlo qui
    trasformava la fine di un lotto in una CI rossa (PR #209).
    """
    voci = coda.leggi_voci((REPO / "backlog" / "CODA.md").read_text(encoding="utf-8"))

    nomi = [v.pbi for v in voci if isinstance(v, coda.VocePbi)]
    assert len(nomi) == len(set(nomi)), f"un PBI compare due volte in coda: {nomi}"
    for nome in nomi:
        assert list(REPO.glob(f"backlog/{nome}-*.md")), f"{nome} non ha un file in backlog/"


def pr_mergiata(titolo="", ramo="", files=None):
    """Una PR mergiata, nella forma in cui `gh pr list --json` la rende.

    `files=None` è la PR che quel campo non ce l'ha affatto — il caso in cui `gh`
    non lo rende — ed è diverso da `files=[]`, la PR che non tocca nessun file.
    Una stringa al posto del record è la sola PR di cui interessa il titolo.
    """
    record = {"title": titolo, "headRefName": ramo}
    if files is not None:
        record["files"] = [{"path": percorso} for percorso in files]
    return record


def mondo(pr_mergiate=(), rami_su_origin=()):
    """Un `esegui()` finto: `gh` e `git` rispondono nella forma in cui rispondono davvero.

    Un comando non previsto fa fallire il test invece di rendere una risposta
    vuota: qui si sta misurando *cosa* il tick chiede al mondo, e una risposta
    di comodo nasconderebbe una domanda in più. Per la stessa ragione di `gh`
    escono **solo i campi chiesti** in `--json`: un campo che il tick legge senza
    chiederlo non arriverebbe mai, e qui si vede.
    """

    def esegui(cmd, cwd):
        if cmd[0] == "gh":
            chiesti = cmd[cmd.index("--json") + 1].split(",")
            return 0, json.dumps([
                {campo: valore
                 for campo, valore in (pr if isinstance(pr, dict) else {"title": pr}).items()
                 if campo in chiesti}
                for pr in pr_mergiate
            ])
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
    costruisce — che qui è l'unico dei due segnali disponibile: di questa PR non
    si sa altro. Il ramo su `origin` si riconosce lo stesso col suffisso di un
    secondo giro.
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


def test_una_pr_che_tocca_solo_backlog_non_spegne_il_pbi_che_nomina(tmp_path, monkeypatch):
    """Il caso della PR #215, ed è il difetto che apre PBI-353.

    Il 09/09 la PR che *scriveva* PBI-352 — il file in `backlog/` e la sua riga
    in `CODA.md` — si intitolava `PBI-352: …`, e al proprio merge ha spento la
    voce che stava scrivendo. La coda è rimasta ferma sette ore dicendo `finita`,
    che è la parola con cui il tick dice che va tutto bene.

    Una PR che tocca **solo** `backlog/` è un documento su un PBI, non il PBI: il
    lavoro non c'è in `main` e la voce resta da lanciare.
    """
    repo = scrivi_coda(tmp_path, "- PBI-352\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    monkeypatch.setattr(
        coda,
        "esegui",
        mondo(pr_mergiate=[
            pr_mergiata(
                titolo="PBI-352: il cruscotto si stringe a cinque — e la riga in coda",
                ramo="docs/il-cruscotto-si-stringe-a-cinque",
                files=["backlog/PBI-352-il-cruscotto-si-stringe.md", "backlog/CODA.md"],
            )
        ]),
    )

    assert coda.decidi(repo, albero) == coda.Lancia("PBI-352")


def test_il_ramo_del_runner_spegne_il_pbi_anche_col_titolo_senza_prefisso(
    tmp_path, monkeypatch
):
    """L'altro modo di nominare un PBI: il ramo `pbi/pbi-XXX` da cui la PR viene.

    Sono i diciannove giri intitolati con la convenzione vecchia — `feat(scope):
    PBI-XXX — …` — tutti in `main` e tutti che il solo titolo dà per da fare. Il
    `headRefName` regge alla potatura del ramo: verificato il 09/09 su #207 e
    #206, rami cancellati da `origin` e nome ancora reso da `gh`. Il timore che
    aveva fatto scartare il ramo — «lo squash il ramo lo perde» — vale per git,
    non per il record della PR.
    """
    repo = scrivi_coda(tmp_path, "- PBI-327\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    monkeypatch.setattr(
        coda,
        "esegui",
        mondo(pr_mergiate=[
            pr_mergiata(
                titolo="feat(officina): PBI-327 — il tipo di lavoro eseguito",
                ramo="pbi/pbi-327",
                files=["backend/app/routers/officina.py"],
            )
        ]),
    )

    assert coda.decidi(repo, albero) == coda.Finita()


def test_il_ramo_col_suffisso_di_giro_nomina_lo_stesso_pbi(tmp_path, monkeypatch):
    """`pbi/pbi-338-giro3` è PBI-338, e `pbi/pbi-337-giro8` è PBI-337.

    Il suffisso lo mette `nome_libero()` quando un primo giro c'era già, ed è la
    forma in cui finisce in `main` ogni PBI ripreso dopo una fermata — cioè
    proprio quelli su cui sbagliare costa un rilancio. `pbi_con_ramo()` il
    suffisso lo tollera già dal ref: qui si tollera dal record della PR.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n- PBI-338\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    monkeypatch.setattr(
        coda,
        "esegui",
        mondo(pr_mergiate=[
            pr_mergiata(
                titolo="feat(officina): PBI-337 — il tipo di lavoro eseguito",
                ramo="pbi/pbi-337-giro8",
                files=["backend/app/routers/officina.py"],
            ),
            pr_mergiata(
                titolo="feat(officina): PBI-338 — la riga di ricambio",
                ramo="pbi/pbi-338-giro3",
                files=["frontend/src/pages/FoglioPage.tsx"],
            ),
        ]),
    )

    assert coda.decidi(repo, albero) == coda.Finita()


def test_il_titolo_spegne_il_pbi_anche_da_un_ramo_che_non_e_pbi(tmp_path, monkeypatch):
    """Il caso #158: PBI-104 implementato a mano dal ramo `ci/il-rosso-si-chiede-prima`.

    È la ragione per cui il titolo resta uno dei due segnali invece di lasciare
    il posto al solo ramo. In questo repository si è implementato a mano da rami
    non `pbi/` più di una volta — #158, #138 (PBI-102), #65 (PBI-209) — e una
    regola sul nome del ramo non lo sa: le darebbe per da fare, cioè
    rilancerebbe un PBI già in `main`, che costa un giro, un ramo e un conflitto.
    """
    repo = scrivi_coda(tmp_path, "- PBI-104\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    monkeypatch.setattr(
        coda,
        "esegui",
        mondo(pr_mergiate=[
            pr_mergiata(
                titolo="PBI-104: il rosso si chiede prima",
                ramo="ci/il-rosso-si-chiede-prima",
                files=["tools/asdlc_runner.py", "decisions/ADR-0021.md"],
            )
        ]),
    )

    assert coda.decidi(repo, albero) == coda.Finita()


def test_un_elenco_di_file_muto_o_al_limite_conta_come_pbi_speso(tmp_path, monkeypatch):
    """Le tre risposte da cui non si capisce cosa la PR abbia toccato, e il verso della prudenza.

    `gh pr list --json files` rende **al più 100 file per PR**: una PR grossa i
    cui primi cento stessero tutti in `backlog/` si leggerebbe «documentale».
    Insieme al campo che manca e alla PR senza file sono i tre silenzi, e per
    tutti e tre il PBI si considera **speso**.

    Il segno è quello: un falso negativo rilancia un PBI già in `main` e costa un
    giro, un ramo e un conflitto; un falso positivo costa i dieci minuti fino al
    tick dopo. È lo stesso fail-closed di PBI-350 col segno tenuto dalla parte
    giusta.
    """
    cento = [f"backlog/PBI-{n}-un-file-documentale.md" for n in range(100)]
    for caso, files in [("assente", None), ("vuoto", []), ("al-limite", cento)]:
        repo = scrivi_coda(tmp_path / caso, "- PBI-352\n")
        albero = tmp_path / caso / "albero"
        albero.mkdir()
        monkeypatch.setattr(
            coda,
            "esegui",
            mondo(pr_mergiate=[
                pr_mergiata(titolo="PBI-352: il cruscotto si stringe a cinque", files=files)
            ]),
        )

        assert coda.decidi(repo, albero) == coda.Finita(), caso


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


def test_un_processo_che_nomina_il_runner_non_occupa_lalbero(tmp_path, monkeypatch):
    """Il lucchetto libero dice che non c'è nessun giro, chiunque lavori lì.

    Il 07/09 e due volte il 25/09 un poller o un Monitor di Claude, con la
    cartella corrente nel worktree e `asdlc_runner` nel comando, hanno fatto
    dire `occupato` al tick senza essere un runner (difetto 47 di PBI-102). Qui
    il processo è vero: un `python3` che dorme dentro l'albero e ha
    `tools/asdlc_runner.py` fra gli argomenti, col lucchetto che nessuno tiene.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    (albero / "runs").mkdir(parents=True)
    (albero / "runs" / ".runner.lock").touch()
    monkeypatch.setattr(coda, "esegui", mondo())

    impostore = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", "tools/asdlc_runner.py"],
        cwd=albero,
    )
    try:
        assert coda.giro_in_corso(albero) is False
        assert coda.decidi(repo, albero) != coda.Occupato()
    finally:
        impostore.kill()
        impostore.wait()


def test_un_lucchetto_che_non_si_apre_occupa_lalbero(tmp_path, monkeypatch):
    """Nel dubbio non si lancia (`PBI-350`, punto 8; `PBI-379`, guardia).

    Al posto del file c'è una cartella: `open()` alza, e il tick non può sapere
    se qualcuno ci lavora.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    (albero / "runs" / ".runner.lock").mkdir(parents=True)
    monkeypatch.setattr(coda, "esegui", nessun_comando)

    assert coda.giro_in_corso(albero) is True
    assert coda.decidi(repo, albero) == coda.Occupato()


def test_un_lucchetto_presente_ma_libero_non_occupa_lalbero(tmp_path, monkeypatch):
    """Il file sopravvive a ogni giro: conta se è tenuto (`PBI-379`, guardia).

    Un processo vero prende il `flock` ed esce, come fa un giro finito: il
    kernel rilascia il lucchetto e il file resta. Senza nessun processo
    intorno, il tick lancia la testa della coda.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    (albero / "runs").mkdir(parents=True)
    lucchetto = albero / "runs" / ".runner.lock"
    monkeypatch.setattr(coda, "esegui", mondo())

    subprocess.run(
        [
            sys.executable,
            "-c",
            "import fcntl, sys\n"
            "fd = open(sys.argv[1], 'a+')\n"
            "fcntl.flock(fd, fcntl.LOCK_EX)\n",
            str(lucchetto),
        ],
        check=True,
    )

    assert lucchetto.is_file()
    assert coda.giro_in_corso(albero) is False
    assert coda.decidi(repo, albero) == coda.Lancia("PBI-337")


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


def test_una_finestra_di_pr_mergiate_piena_non_produce_lancia(tmp_path, monkeypatch):
    """Un elenco lungo quanto il limite può essere tagliato, e un elenco tagliato mente.

    `gh pr list --limit N` non dice mai «non lo so»: una PR caduta fuori dalla
    finestra semplicemente non c'è, e il tick la legge come «non mergiato». Per
    una voce di coda il cui ramo su `origin` sia stato potato dopo il merge quel
    silenzio diventa `Lancia`, cioè il rilancio di un PBI già in `main` — il
    doppione che `test_la_testa_con_un_ramo_su_origin_e_senza_merge_si_attende`
    impedisce, entrato dall'altra porta. È la finestra delle PR, e ha il suo
    gemello nella finestra dei file di una PR, dove il silenzio si risolve
    dalla parte opposta (`test_un_elenco_di_file_muto_o_al_limite_conta_come_pbi_speso`):
    lì non sapere significa «speso», qui significa fermarsi.

    Non si allarga soltanto la finestra, perché una finestra grande resta una
    finestra: quando è piena il tick non deduce niente, alza e va in `Barriera`.
    Costa un tick, e la riga nel log dice cosa alzare.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    # Il limite intero, e nessuna di queste PR è quella della testa della coda:
    # senza il controllo, PBI-337 risulterebbe non mergiato e si lancerebbe.
    piene = [f"PBI-{n}: una PR mergiata mesi fa" for n in range(1000, 1000 + coda.LIMITE_PR)]
    monkeypatch.setattr(coda, "esegui", mondo(pr_mergiate=piene))

    decisione = coda.decidi(repo, albero)

    assert isinstance(decisione, coda.Barriera), decisione
    assert str(coda.LIMITE_PR) in decisione.testo, decisione.testo


def test_la_finestra_piena_nomina_il_tick_in_tools_asdlc_coda(tmp_path, monkeypatch):
    """PBI-383: la riga del log dice in che file alzare `LIMITE_PR`, e il file
    è `tools/asdlc/coda.py`."""
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    piene = [f"PBI-{n}: una PR mergiata mesi fa" for n in range(1000, 1000 + coda.LIMITE_PR)]
    monkeypatch.setattr(coda, "esegui", mondo(pr_mergiate=piene))

    decisione = coda.decidi(repo, albero)

    assert "tools/asdlc/coda.py" in decisione.testo, decisione.testo


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


def test_un_pbi_con_una_domanda_aperta_si_lancia_lo_stesso(tmp_path, monkeypatch):
    """Il ❓ avvisa, non blocca: mettere un PBI in coda è dichiararlo pronto.

    Un grep cieco direbbe che PBI-340 non si può lanciare, e avrebbe torto: la
    sua sezione ❓ è un protocollo di rifinitura già deciso. La distinzione non è
    meccanizzabile, e il cancello vero è un altro — la coda la scrive Francesco.
    Il tick stampa l'intestazione come avviso e lancia lo stesso (`ADR-0008`).
    """
    repo = scrivi_coda(tmp_path, "- PBI-340\n")
    (repo / "backlog" / "PBI-340-le-due-date-del-foglio.md").write_text(
        "# PBI-340: le due date del foglio\n\n"
        "## ❓ Da decidere, se le dodici colonne non ci stanno\n\n"
        "La rifinitura sta qui.\n",
        encoding="utf-8",
    )
    albero = tmp_path / "albero"
    albero.mkdir()
    monkeypatch.setattr(coda, "esegui", mondo())

    assert coda.decidi(repo, albero) == coda.Lancia("PBI-340")
    assert coda.avviso_domande(repo, "PBI-340") == (
        "## ❓ Da decidere, se le dodici colonne non ci stanno"
    )


def test_un_pbi_senza_domande_non_produce_nessun_avviso(tmp_path):
    """L'altro verso: senza ❓ non si inventa un avviso che nessuno ha scritto."""
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    (repo / "backlog" / "PBI-337-il-tipo-di-lavoro-eseguito.md").write_text(
        "# PBI-337: il tipo di lavoro eseguito\n\n## Verifica\n\n- [ ] tutto chiaro\n",
        encoding="utf-8",
    )

    assert coda.avviso_domande(repo, "PBI-337") == ""


def registratore():
    """Un `esegui()` che dice di sì a tutto e tiene la lista di ciò che ha visto."""
    visti = []

    def esegui(cmd, cwd):
        visti.append((cmd, cwd))
        return 0, ""

    return visti, esegui


def runner_che_prende_lalbero(albero, esegui):
    """Un `esegui()` che, sul comando del runner, si comporta come il runner vero.

    Il runner si stacca in un figlio, e il figlio prende il `flock` su
    `runs/.runner.lock` e lo tiene per tutto il giro. È l'unico segno visibile
    da fuori che distingue un runner al lavoro da uno che si è rifiutato subito
    dopo il fork, quando il padre è già uscito `0`.

    Rende anche la lista dei file aperti, perché il lucchetto va rilasciato: è
    un `flock` dell'open file description, e vive finché il test non lo chiude.
    """
    tenuti = []

    def si_stacca(cmd, cwd):
        esito = esegui(cmd, cwd)
        if cmd[0].endswith("/bin/asdlc-runner"):
            (albero / "runs").mkdir(exist_ok=True)
            aperto = (albero / "runs" / ".runner.lock").open("w")
            fcntl.flock(aperto, fcntl.LOCK_EX | fcntl.LOCK_NB)
            tenuti.append(aperto)
        return esito

    return si_stacca, tenuti


def test_il_lancio_fa_il_preflight_e_poi_chiama_il_runner(tmp_path, monkeypatch):
    """Il pre-flight è quello del lancio a mano, perché è lo stesso lancio.

    Il registro dei tempi si rimette a posto — il controllo d'igiene del runner
    non lo esclude, e un albero sporco ferma il giro — poi si prende `origin` e
    ci si stacca sopra, e solo allora parte il runner. Tre righe che vivevano in
    una memoria di sessione, e qui diventano codice versionato.
    """
    albero = tmp_path / "albero"
    albero.mkdir()
    visti, esegui = registratore()
    si_stacca, tenuti = runner_che_prende_lalbero(albero, esegui)
    monkeypatch.setattr(coda, "esegui", si_stacca)
    monkeypatch.setattr(coda, "ATTESA_DEL_DISTACCO", 0)

    coda.lancia("PBI-337", albero)

    assert [cmd for cmd, _ in visti] == [
        ["git", "checkout", "--", "runs/tempi.csv"],
        ["git", "fetch", "origin"],
        ["git", "switch", "--detach", "origin/main"],
        [str(RUNNER_INSTALLATO), "PBI-337"],
    ]
    assert {cwd for _, cwd in visti} == {albero}
    for aperto in tenuti:
        aperto.close()


def test_il_tick_lancia_asdlc_runner_dal_venv_del_pacchetto_anche_col_path_minimo(
    configura, tmp_path, monkeypatch
):
    """PBI-384, criterio 5: il tick lancia `<pacchetto>/bin/asdlc-runner` per
    percorso assoluto. Il cron ha il `PATH` minimo, `/usr/bin:/bin`: un nome nudo
    non si troverebbe, e `python3 tools/asdlc/runner.py` lancerebbe la copia di
    lavoro dell'albero invece del runner installato (`ADR-0026`, decisione 3).

    Il runner è uno script vero nel `bin/` del venv dichiarato, e parte con il
    `PATH` del cron; il pre-flight di `git` è finto, e il giro vivo dopo il
    distacco si dà per visto."""
    configura(toml_di_prova())
    installato = tmp_path.resolve() / ".venv-asdlc" / "bin" / "asdlc-runner"
    installato.parent.mkdir(parents=True)
    installato.write_text('#!/bin/sh\necho "$@" > "$(dirname "$0")/lanciato"\n',
                          encoding="utf-8")
    installato.chmod(0o755)
    albero = tmp_path / "albero"
    albero.mkdir()
    vero = coda.esegui
    monkeypatch.setattr(coda, "esegui",
                        lambda cmd, cwd: (0, "") if cmd[0] == "git" else vero(cmd, cwd))
    monkeypatch.setattr(coda, "ATTESA_DEL_DISTACCO", 0)
    monkeypatch.setattr(coda, "giro_in_corso", lambda worktree: True)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    try:
        coda.lancia("PBI-384", albero)
        fermata = ""
    except coda.Guasto as guasto:
        fermata = str(guasto)

    assert fermata == ""
    assert (installato.parent / "lanciato").read_text(encoding="utf-8") == "PBI-384\n"


def test_un_preflight_che_fallisce_non_chiama_il_runner(tmp_path, monkeypatch):
    """Se `git fetch` non prende origin, lo switch andrebbe su un main di ieri.

    Il giro partirebbe lo stesso, e produrrebbe un ramo costruito su una base
    vecchia: un guasto del pre-flight ferma il lancio e dice quale comando è
    andato storto.
    """
    albero = tmp_path / "albero"
    albero.mkdir()
    visti = []

    def fetch_rotto(cmd, cwd):
        visti.append(cmd)
        if cmd[:2] == ["git", "fetch"]:
            return 1, "could not resolve host github.com"
        return 0, ""

    monkeypatch.setattr(coda, "esegui", fetch_rotto)

    with pytest.raises(coda.Guasto, match="fetch"):
        coda.lancia("PBI-337", albero)

    assert not any("asdlc-runner" in " ".join(cmd) for cmd in visti)


def mondo_registrato(pr_mergiate=(), rami_su_origin=()):
    """Come `mondo()`, ma tiene la lista dei comandi e dice di sì a tutti gli altri."""
    visti = []

    def esegui(cmd, cwd):
        visti.append(cmd)
        if cmd[0] == "gh":
            return 0, json.dumps([{"title": t} for t in pr_mergiate])
        if "ls-remote" in cmd:
            return 0, "".join(
                f"{'0' * 40}\trefs/heads/{r}\n" for r in rami_su_origin
            )
        return 0, ""

    return visti, esegui


def test_il_tick_lancia_il_pbi_che_la_coda_indica(tmp_path, monkeypatch, capsys):
    """Il giro intero, dalla riga di cron al runner: decide una cosa e la fa."""
    repo = scrivi_coda(tmp_path, "- PBI-337\n- PBI-338\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    visti, esegui = mondo_registrato()
    si_stacca, tenuti = runner_che_prende_lalbero(albero, esegui)
    monkeypatch.setattr(coda, "esegui", si_stacca)
    monkeypatch.setattr(coda, "ATTESA_DEL_DISTACCO", 0)

    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 0
    assert [str(RUNNER_INSTALLATO), "PBI-337"] in visti
    assert "PBI-337" in capsys.readouterr().out
    for aperto in tenuti:
        aperto.close()


def test_il_dry_run_stampa_la_decisione_e_non_esegue_niente(tmp_path, monkeypatch, capsys):
    """La prova sul comando che **non** parte.

    Le domande al mondo restano — senza `gh` e senza `git ls-remote` non ci
    sarebbe nessuna decisione da stampare — ma nessuno dei comandi che cambiano
    lo stato viene eseguito: né il pre-flight, che sposta il worktree su un
    altro ramo, né il runner.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    visti, esegui = mondo_registrato()
    monkeypatch.setattr(coda, "esegui", esegui)

    uscita = coda.smista(
        ["--repo", str(repo), "--worktree", str(albero), "--dry-run"]
    )

    assert uscita == 0
    assert "PBI-337" in capsys.readouterr().out
    eseguiti = [" ".join(cmd) for cmd in visti]
    assert not [c for c in eseguiti if "asdlc-runner" in c], eseguiti
    assert not [c for c in eseguiti if "switch" in c or "fetch" in c or "checkout" in c], eseguiti


PR_338 = "https://github.com/Lara-srl/ada-controller/pull/338"
PR_338_BIS = "https://github.com/Lara-srl/ada-controller/pull/339"


def mondo_con_pr_aperte(aperte):
    """Un `esegui()` finto per un PBI in attesa: nessuna PR mergiata, il ramo
    `pbi/pbi-338-giro2` su `origin`, e le PR aperte `aperte` — `None` è un `gh`
    che non risponde. Come in `mondo()`, di `gh` escono solo i campi chiesti."""

    def esegui(cmd, cwd):
        if cmd[:3] == ["gh", "pr", "list"] and "merged" in cmd:
            return 0, "[]"
        if cmd[:3] == ["gh", "pr", "list"] and "open" in cmd:
            if aperte is None:
                return 1, "HTTP 502: Bad Gateway"
            chiesti = cmd[cmd.index("--json") + 1].split(",")
            return 0, json.dumps([
                {campo: valore for campo, valore in pr.items() if campo in chiesti}
                for pr in aperte
            ])
        if cmd[0] == "git" and "ls-remote" in cmd:
            return 0, f"{'0' * 40}\trefs/heads/pbi/pbi-338-giro2\n"
        raise AssertionError(f"comando non previsto: {cmd}")

    return esegui


@pytest.mark.parametrize("aperte, coda_della_riga", [
    ([{"url": PR_338, "headRefName": "pbi/pbi-338-giro2"},
      {"url": "https://github.com/Lara-srl/ada-controller/pull/3380",
       "headRefName": "pbi/pbi-3380"}],
     f"— PR {PR_338}"),
    ([{"url": PR_338, "headRefName": "pbi/pbi-338"},
      {"url": PR_338_BIS, "headRefName": "pbi/pbi-338-giro2"}],
     f"— PR {PR_338}, {PR_338_BIS}"),
    ([{"url": "https://github.com/Lara-srl/ada-controller/pull/3380",
       "headRefName": "pbi/pbi-3380"}],
     "— nessuna PR sul ramo: crearla o rilanciare"),
    (None, "— GitHub non ha risposto: PR da verificare"),
], ids=["una-pr", "piu-pr", "nessuna-pr", "gh-muto"])
def test_la_riga_di_attesa_dice_cosa_ce_sul_ramo(
    tmp_path, monkeypatch, capsys, aperte, coda_della_riga
):
    """PBI-381, decisioni 3 e 4. «Tocca a un umano» non diceva perché la coda
    fosse ferma: chi leggeva cercava una domanda di un giro fermato, e intanto
    una PR nata senza URL era aperta e nessuno la nominava. La riga fa la
    ricerca sul ramo del PBI — col suffisso di un secondo giro, e non sul ramo
    di un PBI che ne ha il numero come prefisso — e dice cosa c'è."""
    repo = scrivi_coda(tmp_path, "- PBI-338\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    monkeypatch.setattr(coda, "esegui", mondo_con_pr_aperte(aperte))

    assert coda.smista(["--repo", str(repo), "--worktree", str(albero), "--dry-run"]) == 0

    assert capsys.readouterr().out.strip() == (
        f"attende: PBI-338 ha un ramo su origin e non è in main {coda_della_riga}")


def test_guardia_un_lancio_non_cerca_le_pr_aperte(tmp_path, monkeypatch):
    """Guardia dichiarata di PBI-381: la ricerca delle PR aperte è dell'attesa e
    di nessun'altra decisione. Un PBI senza ramo su `origin` si lancia con le
    stesse due domande al mondo di prima."""
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    visti, esegui = mondo_registrato()
    monkeypatch.setattr(coda, "esegui", esegui)

    assert coda.decidi(repo, albero) == coda.Lancia("PBI-337")
    assert len(visti) == 2, visti
    assert not [c for c in visti if c[:3] == ["gh", "pr", "list"] and "open" in c], visti


def test_ogni_tick_lascia_una_riga_nel_log(tmp_path, monkeypatch):
    """Il tick gira senza nessuno davanti: ciò che ha deciso deve restare scritto.

    Una riga per giro, in coda alle altre — due tick, due righe — con l'ora
    davanti, perché in un log di cron una decisione senza quando non si colloca.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    _, esegui = mondo_registrato()
    monkeypatch.setattr(coda, "esegui", esegui)
    argomenti = ["--repo", str(repo), "--worktree", str(albero), "--dry-run"]

    coda.smista(argomenti)
    coda.smista(argomenti)

    righe = (repo / coda.LOG).read_text(encoding="utf-8").splitlines()
    assert len(righe) == 2
    oggi = datetime.date.today().isoformat()
    assert all(riga.startswith(oggi) and "PBI-337" in riga for riga in righe), righe


def test_lavviso_delle_domande_esce_accanto_al_lancio(tmp_path, monkeypatch, capsys):
    """Segnalare invece di bloccare: l'intestazione ❓ esce, e il PBI parte.

    L'avviso deve finire dove qualcuno lo troverà — a schermo e nel log — perché
    è tutto ciò che resta di una verifica che il tick non può fare al posto di
    chi ha scritto la coda.
    """
    repo = scrivi_coda(tmp_path, "- PBI-340\n")
    (repo / "backlog" / "PBI-340-le-due-date-del-foglio.md").write_text(
        "# PBI-340: le due date del foglio\n\n"
        "## ❓ Da decidere, se le dodici colonne non ci stanno\n",
        encoding="utf-8",
    )
    albero = tmp_path / "albero"
    albero.mkdir()
    _, esegui = mondo_registrato()
    monkeypatch.setattr(coda, "esegui", esegui)

    coda.smista(["--repo", str(repo), "--worktree", str(albero), "--dry-run"])

    stampato = capsys.readouterr().out
    assert "PBI-340" in stampato
    assert "Da decidere, se le dodici colonne non ci stanno" in stampato
    assert "Da decidere" in (repo / coda.LOG).read_text(encoding="utf-8")


def test_un_lancio_che_non_parte_lo_scrive_nel_log(tmp_path, monkeypatch):
    """Il pre-flight che si rompe deve lasciare una diagnosi, non un traceback.

    Da cron l'eccezione non la legge nessuno: quello che resta è il log, e lì
    «non ho lanciato» senza il perché costa il tempo di rifare il giro a mano.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()

    def fetch_rotto(cmd, cwd):
        if cmd[0] == "gh":
            return 0, "[]"
        if "ls-remote" in cmd:
            return 0, ""
        if cmd[:2] == ["git", "fetch"]:
            return 1, "could not resolve host github.com"
        return 0, ""

    monkeypatch.setattr(coda, "esegui", fetch_rotto)

    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 1
    log = (repo / coda.LOG).read_text(encoding="utf-8")
    assert "fetch" in log


def test_un_runner_che_esce_male_lo_scrive_nel_log(tmp_path, monkeypatch):
    """Il gesto subito dopo il pre-flight, che ha la stessa ragione di stare nel log.

    Il codice d'uscita del runner copre ciò che succede **prima** del distacco, e
    solo quello: `--e2e`, che il runner rifiuta con `2`; un argomento che argparse
    non riconosce; un `asdlc-runner` che nel venv non c'è, e allora `esegui()`
    rende `127` per la convenzione della shell. Sono i casi di questo test.

    Senza leggere quel codice nel log resterebbe «lancia: PBI-337» — il contrario
    di quel che è successo — il tick uscirebbe `0`, e al tick dopo, non trovando
    nessun ramo su origin, si riproverebbe: un ciclo ogni N minuti che non lascia
    mai una diagnosi. Per i rifiuti che vengono **dopo** il distacco il codice non
    dice più niente, ed è l'altro test.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()

    def python_che_non_ce(cmd, cwd):
        if cmd[0] == "gh":
            return 0, "[]"
        if "ls-remote" in cmd:
            return 0, ""
        if cmd[0].endswith("/bin/asdlc-runner"):
            return 127, "comando non eseguibile: asdlc-runner — [Errno 2] No such file"
        return 0, ""

    monkeypatch.setattr(coda, "esegui", python_che_non_ce)

    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 1
    log = (repo / coda.LOG).read_text(encoding="utf-8")
    assert "non lanciato" in log, log
    assert "uscita 127" in log, log
    assert "asdlc-runner" in log, log


def test_un_runner_fermatosi_dopo_il_distacco_non_conta_come_lanciato(
    tmp_path, monkeypatch
):
    """Il codice d'uscita non copre i rifiuti che vengono dopo il fork: l'albero sì.

    `stacca()` esce dal padre con `os._exit(0)` **prima** del lucchetto, prima di
    `agenti_estranei()` e prima del controllo d'igiene (`asdlc_runner.py:2624`,
    `:2630`, `:2638`), e l'ordine è deliberato — il `flock` vive nell'open file
    description, e un padre che lo prendesse e poi forkasse se lo porterebbe via.
    Quindi una gara sul lucchetto dell'albero, un file sporco o un PBI senza file
    in `backlog/` fanno uscire male il **figlio**: quel codice finisce in
    `runs/<run>.log` e non arriva a nessuno, mentre il tick legge lo `0` del padre.

    Sotto `cron` è il caso più probabile di tutti, ed è quello che riaprirebbe il
    ciclo che il test qui sopra dichiara chiuso: «lancia: PBI-337», uscita `0`, e
    al tick dopo — nessun ramo su origin, nessun merge — si riprova.

    Quello che si guarda quindi non è il codice del padre, è l'albero: passato il
    tempo del distacco, o lì dentro c'è un giro vivo, o il giro non è partito.
    Qui il finto runner rende `0` e non prende niente, come il figlio che si è
    già arreso.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    _, esegui = mondo_registrato()
    monkeypatch.setattr(coda, "esegui", esegui)
    monkeypatch.setattr(coda, "ATTESA_DEL_DISTACCO", 0)

    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 1
    log = (repo / coda.LOG).read_text(encoding="utf-8")
    assert "non lanciato" in log, log
    assert "PBI-337" in log, log


def test_il_tick_non_gira_dentro_lalbero_che_comanda(tmp_path, monkeypatch, capsys):
    """Checkout e worktree coincidono: il tick si ferma prima di guardare qualsiasi cosa.

    L'albero del runner cambia ramo a ogni giro. Un tick che leggesse il proprio
    codice da lì si riscriverebbe a metà, e il pre-flight sposterebbe l'albero
    sotto i piedi al processo che lo sta eseguendo.
    """
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    monkeypatch.setattr(coda, "esegui", nessun_comando)

    uscita = coda.smista(["--repo", str(repo), "--worktree", str(repo)])

    assert uscita == 2
    assert "--worktree" in capsys.readouterr().out


# --- Le costanti del tick nascono da asdlc.toml (PBI-358) ----------------------
#
# Le regex delle voci, dei titoli e dei rami delle PR dicevano la forma dell'id
# del PBI a mano, come `trova_pbi` nel runner: quattro copie della stessa cosa,
# e PBI-353 ne ha corrette tre insieme mentre la quarta teneva ferma la coda per
# sette ore. Da qui il tick e il runner leggono lo **stesso** file.


def toml_di_prova(base="origin/main", prefisso_ramo="pbi/pbi-",
                  cartella="backlog", coda_md="backlog/CODA.md",
                  id="PBI-{n}", file="PBI-{n}-{slug}.md",
                  registro="runs", tempi="tempi.csv", worktree="../ada-run") -> str:
    """Un `asdlc.toml` coi valori di oggi: ogni test nomina solo ciò che cambia."""
    return (
        f'[git]\nbase = "{base}"\nprefisso_ramo = "{prefisso_ramo}"\n\n'
        f'[backlog]\ncartella = "{cartella}"\ncoda = "{coda_md}"\nid = "{id}"\nfile = "{file}"\n\n'
        f'[registro]\ncartella = "{registro}"\ntempi = "{tempi}"\n\n'
        '[ambiente]\nvenv = "backend/.venv"\nprestiti = ["data"]\npacchetto = ".venv-asdlc"\n\n'
        f'[worktree]\npercorso = "{worktree}"\n\n'
        '[soglie]\ntentativi = 3\nigiene = 3\nrevisioni = 4\n\n'
        '[gate_del_rosso]\nattivo = true\n\n'
        '[[gate]]\nnome = "pytest"\ncomando = ["pytest", "-q"]\ncwd = "backend"\n'
    )


@pytest.fixture
def configura(tmp_path):
    """Parte dal solo `asdlc.toml` versionato — senza `asdlc.local.toml`, che
    sulla macchina di chi lo scrive cambia `[worktree]` di proposito — applica un
    TOML di prova al tick e alla fine rimette la configurazione di macchina."""
    config = coda.asdlc_config
    di_prima = coda.CFG
    # La `configura()` vera e non quella che `log_dir_temporanea` avvolge per
    # spostare il `LOG` (PBI-382): qui si prova ciò che deriva da `asdlc.toml`.
    configura = getattr(coda.configura, "__wrapped__", coda.configura)
    configura(config.interpreta(config.leggi_toml(REPO / config.NOME_FILE), config.NOME_FILE))

    def _applica(testo: str):
        (tmp_path / "asdlc.toml").write_text(testo, encoding="utf-8")
        configura(config.carica(tmp_path))

    yield _applica
    coda.configura(di_prima)


STORIE = dict(id="US-{n}", file="US-{n}-{slug}.md", prefisso_ramo="us/us-",
              cartella="storie", coda_md="storie/CODA.md")


def test_le_voci_della_coda_seguono_il_modello_dell_id(configura):
    assert coda.leggi_voci("- PBI-7\n- US-7\n") == [coda.VocePbi("PBI-7")]

    configura(toml_di_prova(**STORIE))

    assert coda.leggi_voci("- PBI-7\n- US-7\n") == [coda.VocePbi("US-7")], (
        "con l'altro modello `- PBI-7` è prosa, come lo era `- US-7`"
    )


def test_il_pbi_nominato_da_una_pr_segue_il_modello_e_il_prefisso(configura):
    assert coda.pbi_nominato(pr_mergiata(titolo="PBI-7: x")) == "PBI-7"
    assert coda.pbi_nominato(pr_mergiata(titolo="feat: x", ramo="pbi/pbi-7-giro2")) == "PBI-7"

    configura(toml_di_prova(**STORIE))

    assert coda.pbi_nominato(pr_mergiata(titolo="US-7: x")) == "US-7"
    assert coda.pbi_nominato(pr_mergiata(titolo="feat: x", ramo="us/us-7-giro2")) == "US-7"
    assert coda.pbi_nominato(pr_mergiata(titolo="PBI-7: x", ramo="pbi/pbi-7")) is None


def test_i_rami_su_origin_si_chiedono_e_si_leggono_col_prefisso(configura, tmp_path, monkeypatch):
    configura(toml_di_prova(**STORIE))
    chiesti = []

    def esegui(cmd, cwd):
        chiesti.append(cmd)
        return 0, ("0" * 40 + "\trefs/heads/us/us-7\n" + "0" * 40 + "\trefs/heads/pbi/pbi-8\n")

    monkeypatch.setattr(coda, "esegui", esegui)

    assert coda.pbi_con_ramo(tmp_path) == {"US-7"}
    assert chiesti[0][-1] == "refs/heads/us/*", "si chiede a origin la sola cartella del prefisso"


def test_tocca_codice_guarda_la_cartella_del_backlog_del_toml(configura):
    assert coda.tocca_codice(pr_mergiata(files=["backlog/PBI-7-x.md"])) is False

    configura(toml_di_prova(**STORIE))

    assert coda.tocca_codice(pr_mergiata(files=["storie/US-7-x.md", "storie/CODA.md"])) is False
    assert coda.tocca_codice(pr_mergiata(files=["backlog/PBI-7-x.md"])) is True


def test_la_coda_e_l_avviso_delle_domande_si_leggono_dalla_cartella_del_toml(
    configura, tmp_path, monkeypatch
):
    configura(toml_di_prova(**STORIE))
    repo = tmp_path / "repo"
    (repo / "storie").mkdir(parents=True)
    (repo / "storie" / "CODA.md").write_text("- US-7\n", encoding="utf-8")
    (repo / "storie" / "US-7-la-somma.md").write_text(
        "# US-7\n\n## ❓ Aperta\n", encoding="utf-8")
    albero = tmp_path / "albero"
    albero.mkdir()
    monkeypatch.setattr(coda, "esegui", mondo())

    assert coda.decidi(repo, albero) == coda.Lancia("US-7")
    assert coda.avviso_domande(repo, "US-7") == "## ❓ Aperta"


def test_il_worktree_il_log_e_il_lucchetto_vengono_dal_toml(configura, tmp_path):
    # Letto senza `carica()`, il percorso resta com'è scritto: a risolverlo dalla
    # radice comune è `carica()`, che sa dove sta il repository (PBI-384).
    assert coda.WORKTREE_DEL_RUNNER == Path("../ada-run")
    assert coda.LOG == Path("runs") / "coda.log"
    assert coda.LUCCHETTO == Path("runs") / ".runner.lock"

    configura(toml_di_prova(registro="giri", worktree="../altro-run"))

    assert coda.WORKTREE_DEL_RUNNER == tmp_path.resolve().parent / "altro-run"
    assert coda.LOG == Path("giri") / "coda.log"
    assert coda.LUCCHETTO == Path("giri") / ".runner.lock"


def test_il_preflight_si_stacca_sul_ramo_del_toml(configura, tmp_path, monkeypatch):
    """Lo stesso ramo da cui il runner ramifica: un pre-flight che si staccasse
    su un altro `origin/main` farebbe nascere il branch su una base vecchia."""
    configura(toml_di_prova(base="origin/master", tempi="ore.csv"))
    albero = tmp_path / "albero"
    albero.mkdir()
    visti, esegui = registratore()
    si_stacca, tenuti = runner_che_prende_lalbero(albero, esegui)
    monkeypatch.setattr(coda, "esegui", si_stacca)
    monkeypatch.setattr(coda, "ATTESA_DEL_DISTACCO", 0)

    coda.lancia("PBI-337", albero)

    assert [cmd for cmd, _ in visti][:3] == [
        ["git", "checkout", "--", "runs/ore.csv"],
        ["git", "fetch", "origin"],
        ["git", "switch", "--detach", "origin/master"],
    ]
    for aperto in tenuti:
        aperto.close()


# --- La radice del tick è la cartella di lavoro (PBI-382) --------------------


def tick_dal_checkout(tmp_path, monkeypatch):
    """`main()` lanciato con la cwd nel checkout vero, come fa il cron da
    `ada_controller`, con un mondo finto al posto di `gh` e `git ls-remote`.

    `main()` rilegge `asdlc.toml` e rimette i nomi di modulo: si registrano
    prima, perché `monkeypatch` li restituisca ai test dopo. Il worktree è una
    cartella vuota: quello di `asdlc.toml` è quest'albero stesso, quando la
    suite gira nel worktree del runner, e il tick si rifiuterebbe. Torna le
    cartelle da cui il tick ha interrogato il mondo, e il `--worktree`."""
    for nome in ("REPO", "CFG", "WORKTREE_DEL_RUNNER", "LOG", "LUCCHETTO", "BACKLOG",
                 "CODA", "BASE", "REMOTO", "PREFISSO_RAMO", "RE_PBI", "RE_TITOLO_PR",
                 "RE_RAMO_PR", "RE_RAMO_PBI"):
        monkeypatch.setattr(coda, nome, getattr(coda, nome))
    cartelle = []
    _, rispondi = mondo_registrato()

    def esegui(cmd, cwd):
        cartelle.append(Path(cwd))
        return rispondi(cmd, cwd)

    monkeypatch.setattr(coda, "esegui", esegui)
    albero = tmp_path / "albero"
    albero.mkdir()
    monkeypatch.chdir(REPO)
    return cartelle, albero


def test_guardia_il_dry_run_lanciato_dal_checkout_decide_come_col_repo_esplicito(
    tmp_path, monkeypatch, capsys
):
    """Il checkout è la radice trovata dalla cwd, non più la cartella del codice:
    in aDa coincidono, e la decisione stampata è la stessa che dà `--repo`
    esplicito sullo stesso checkout. Le domande al mondo partono da lì."""
    cartelle, albero = tick_dal_checkout(tmp_path, monkeypatch)

    dalla_cwd = coda.main(["--worktree", str(albero), "--dry-run"])
    decisa_dalla_cwd = capsys.readouterr().out
    col_repo = coda.main(["--repo", str(REPO), "--worktree", str(albero), "--dry-run"])
    decisa_col_repo = capsys.readouterr().out

    assert dalla_cwd == col_repo == 0
    assert decisa_dalla_cwd == decisa_col_repo
    assert decisa_dalla_cwd.strip()
    assert set(cartelle) == {REPO}


def test_guardia_il_dry_run_dal_checkout_scrive_il_log_nel_temporaneo(tmp_path, monkeypatch, capsys):
    """Decisione 6 di PBI-382: il tick chiamato sul checkout vero lascia il
    `runs/coda.log` vero com'era, e la sua riga sta nella cartella temporanea
    di `log_dir_temporanea` — la classe del difetto 38 è un test che sporca il
    registro vero."""
    _, albero = tick_dal_checkout(tmp_path, monkeypatch)
    vero = REPO / "runs" / "coda.log"
    prima = vero.read_bytes() if vero.is_file() else None

    coda.main(["--worktree", str(albero), "--dry-run"])
    decisa = capsys.readouterr().out.strip()

    assert (vero.read_bytes() if vero.is_file() else None) == prima
    assert not coda.LOG.is_relative_to(REPO), coda.LOG
    righe = coda.LOG.read_text(encoding="utf-8").splitlines()
    assert [r.split("  ", 1)[1] for r in righe] == [decisa]


# --- Il tick verifica l'ambiente prima di lanciare (PBI-384) -----------------


def test_il_tick_con_l_ambiente_mancante_scrive_la_riga_e_non_lancia(
    configura, ambiente_vero, tmp_path, monkeypatch
):
    """Decisione 7: senza `<pacchetto>/bin/asdlc-runner`, o con un eseguibile
    dichiarato che manca, il tick scrive una riga `ambiente mancante: …` e non
    lancia — né il runner né il pre-flight, che sposta il worktree su un altro
    ramo. Il `PATH` del cron è minimo, e il runner si fermerebbe lo stesso dopo il
    distacco, dove la ragione finisce in un log che il tick non legge."""
    configura(toml_di_prova().replace(
        'pacchetto = ".venv-asdlc"', 'pacchetto = ".venv-asdlc"\neseguibili = ["git", "pytest"]'))
    monkeypatch.setattr(shutil, "which",
                        lambda c, *a, **k: None if c == "pytest" else f"/usr/bin/{c}")
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    visti, esegui = mondo_registrato()
    monkeypatch.setattr(coda, "esegui", esegui)
    monkeypatch.setattr(coda, "ATTESA_DEL_DISTACCO", 0)

    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 1
    righe = (repo / coda.LOG).read_text(encoding="utf-8").splitlines()
    mancante = [r for r in righe if "  ambiente mancante: " in r]
    assert len(mancante) == 1, righe
    runner_del_pacchetto = tmp_path.resolve() / ".venv-asdlc" / "bin" / "asdlc-runner"
    assert str(runner_del_pacchetto) in mancante[0]
    assert "`pytest`" in mancante[0], "tutte le mancanze, nella stessa riga"
    assert not any("asdlc-runner" in " ".join(cmd) for cmd in visti), "il runner non parte"
    assert not any(c in cmd for cmd in visti for c in ("fetch", "switch", "checkout")), (
        "e nemmeno il pre-flight")


# --- La pausa del tick (PBI-385) ---------------------------------------------


def smista_senza_decidere(monkeypatch):
    """`decidi()` e `lancia()` che registrano di essere stati chiamati: con la
    pausa il tick non deve arrivare a nessuno dei due."""
    chiamati: list[str] = []
    monkeypatch.setattr(coda, "decidi", lambda repo, worktree: (
        chiamati.append("decidi") or coda.Lancia("PBI-337")))
    monkeypatch.setattr(coda, "lancia", lambda pbi, worktree: chiamati.append("lancia"))
    return chiamati


@pytest.mark.parametrize("prova", [[], ["--dry-run"]], ids=["tick", "dry-run"])
def test_il_tick_in_pausa_esce_con_zero_senza_decidere_e_lo_scrive_nel_log(
    home_finta, tmp_path, monkeypatch, prova
):
    """Decisione 5. Il tick non si spegne più nel crontab — cron lancia dalla
    tabella caricata, e fra la modifica e il `RELOAD` il 30/09 ha lanciato 384
    (difetto 69 di PBI-102). Con `~/asdlc-tick.pausa` il tick esce subito con 0,
    non chiede niente al mondo e non lancia, e nel log scrive la riga del file:
    chi legge `coda.log` vede perché non è successo niente. `--dry-run` la
    rispetta come un tick vero."""
    riga = "2026-09-30 21:30 asdlc-chiudi-giro PBI-385"
    (home_finta / "asdlc-tick.pausa").write_text(riga + "\n", encoding="utf-8")
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    chiamati = smista_senza_decidere(monkeypatch)

    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero), *prova])

    assert uscita == 0
    assert chiamati == []
    righe = (repo / coda.LOG).read_text(encoding="utf-8").splitlines()
    assert len(righe) == 1 and righe[0].endswith(f"  in pausa: {riga}"), righe


def test_un_file_di_pausa_che_non_si_legge_e_pausa_lo_stesso(
    home_finta, tmp_path, monkeypatch
):
    """Decisione 5: un file che c'è ma non si legge è pausa lo stesso. Chi l'ha
    creato voleva il tick fermo, e un errore di lettura non è una ragione per
    lanciare. Qui al posto del file c'è una cartella, che `read_text` rifiuta."""
    (home_finta / "asdlc-tick.pausa").mkdir()
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    chiamati = smista_senza_decidere(monkeypatch)

    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 0
    assert chiamati == []
    righe = (repo / coda.LOG).read_text(encoding="utf-8").splitlines()
    assert len(righe) == 1 and "  in pausa: " in righe[0], righe
    assert "non si legge" in righe[0], righe


def test_la_pausa_nata_dopo_la_decisione_ferma_il_lancio(home_finta, tmp_path, monkeypatch):
    """Decisione 5: il tick legge la pausa una seconda volta, subito prima di
    `lancia()`. Un tick partito un attimo prima che `asdlc-chiudi-giro` creasse
    il file ha già deciso di lanciare, e senza la seconda lettura lancerebbe sul
    ramo che il comando sta cancellando — il 23/09 con PBI-365."""
    riga = "2026-09-30 21:30 asdlc-chiudi-giro PBI-385"
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    lanciati: list[str] = []

    def decide_e_intanto_nasce_la_pausa(repo, worktree):
        (home_finta / "asdlc-tick.pausa").write_text(riga + "\n", encoding="utf-8")
        return coda.Lancia("PBI-337")

    monkeypatch.setattr(coda, "decidi", decide_e_intanto_nasce_la_pausa)
    monkeypatch.setattr(coda, "lancia", lambda pbi, worktree: lanciati.append(pbi))

    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 0
    assert lanciati == []
    righe = (repo / coda.LOG).read_text(encoding="utf-8").splitlines()
    assert righe[-1].endswith(f"  in pausa: {riga}"), righe


# --- Il lucchetto del tick (PBI-392) -----------------------------------------


@contextlib.contextmanager
def tenuto_da_un_figlio(file: Path):
    """Un processo figlio che prende il `flock` su `file` e lo tiene finché il
    blocco `with` non finisce. Un processo e non un descrittore di questo: il
    lucchetto vero lo tiene un altro tick, o `asdlc-chiudi-giro`."""
    file.parent.mkdir(parents=True, exist_ok=True)
    figlio = subprocess.Popen(
        [sys.executable, "-c",
         "import fcntl, sys\n"
         "f = open(sys.argv[1], 'w')\n"
         "fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
         "print('preso', flush=True)\n"
         "sys.stdin.read()\n",
         str(file)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert figlio.stdout.readline().strip() == "preso"
        yield
    finally:
        figlio.stdin.close()
        figlio.wait(timeout=10)


OCCUPATO_DAL_TICK = "occupato: il lucchetto del tick è tenuto — un altro tick o asdlc-chiudi-giro"


@pytest.mark.parametrize("prova", [[], ["--dry-run"]], ids=["tick", "dry-run"])
def test_con_il_lucchetto_del_tick_tenuto_il_tick_esce_senza_decidere(
    tmp_path, monkeypatch, prova
):
    """PBI-392, decisione 2. Fino al `flock` del runner il tick non teneva nessun
    lucchetto, e `asdlc-chiudi-giro` faceva i suoi sei passi mentre un tick
    finiva il lancio (difetto 70 di PBI-102). Con `runs/.tick.lock` tenuto da un
    altro processo il tick esce con 0, non decide e non lancia, e lo scrive in
    `coda.log`. Il `--dry-run` fa lo stesso."""
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    chiamati = smista_senza_decidere(monkeypatch)

    with tenuto_da_un_figlio(repo / "runs" / ".tick.lock"):
        uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero), *prova])

    assert uscita == 0
    assert chiamati == []
    righe = (repo / coda.LOG).read_text(encoding="utf-8").splitlines()
    assert len(righe) == 1 and righe[0].endswith(f"  {OCCUPATO_DAL_TICK}"), righe


def prova_il_lucchetto_del_tick(repo: Path) -> bool:
    """Un secondo `flock` non bloccante su `runs/.tick.lock`, da un descrittore
    nuovo: `True` se il lucchetto era libero. Il `flock` è dell'open file
    description, quindi due aperture dello stesso processo si escludono."""
    file = repo / "runs" / ".tick.lock"
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("a") as altro:
        try:
            fcntl.flock(altro, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(altro, fcntl.LOCK_UN)
        return True


def test_guardia_il_tick_tiene_il_suo_lucchetto_mentre_lancia(tmp_path, monkeypatch):
    """PBI-392, decisione 3. Il lucchetto si tiene fino alla fine di `smista()`,
    quindi anche durante `lancia()`: il pre-flight, l'avvio del runner e
    l'attesa del distacco. È la finestra in cui `asdlc-chiudi-giro` creava la
    pausa e cancellava un ramo mentre il tick lanciava (difetto 70 di PBI-102).
    Con `lancia()` finto, un secondo `flock` sullo stesso file fallisce."""
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    libero_durante_il_lancio: list[bool] = []
    monkeypatch.setattr(coda, "decidi", lambda repo, worktree: coda.Lancia("PBI-337"))
    monkeypatch.setattr(coda, "lancia", lambda pbi, worktree: libero_durante_il_lancio.append(
        prova_il_lucchetto_del_tick(repo)))

    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 0
    assert libero_durante_il_lancio == [False]
    assert prova_il_lucchetto_del_tick(repo), "finito il tick, il lucchetto è libero"


def test_guardia_il_runner_lanciato_non_eredita_il_lucchetto_del_tick(tmp_path, monkeypatch):
    """PBI-392, decisione 3. Un giro in corso tiene il lucchetto del runner, non
    quello del tick: se il runner staccato ereditasse il descrittore, il tick
    dopo e `asdlc-chiudi-giro` troverebbero il lucchetto tenuto per tutta l'ora
    del giro. Al posto del runner un processo che dorme, avviato da `lancia()`
    mentre il tick tiene il lucchetto: finito il tick il lucchetto è libero, e
    il processo è ancora vivo."""
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    lanciati: list[subprocess.Popen] = []
    libero_al_lancio: list[bool] = []

    def lancia_uno_che_dorme(pbi, worktree):
        libero_al_lancio.append(prova_il_lucchetto_del_tick(repo))
        lanciati.append(subprocess.Popen(["sleep", "30"], cwd=worktree,
                                         start_new_session=True))

    monkeypatch.setattr(coda, "decidi", lambda repo, worktree: coda.Lancia("PBI-337"))
    monkeypatch.setattr(coda, "lancia", lancia_uno_che_dorme)

    try:
        uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])

        assert uscita == 0
        assert libero_al_lancio == [False], "il runner parte col lucchetto del tick tenuto"
        assert lanciati[0].poll() is None, "il runner è ancora vivo"
        assert prova_il_lucchetto_del_tick(repo), "e il lucchetto del tick è libero"
    finally:
        for figlio in lanciati:
            figlio.kill()
            figlio.wait()


def test_guardia_un_tick_lock_senza_nessuno_che_lo_tiene_non_ferma_il_tick(
    tmp_path, monkeypatch
):
    """PBI-392, decisione 1: il lucchetto è un `flock`, del processo e non del
    file. Il file resta su disco dopo ogni tick, e letto come presenza il primo
    tick della storia fermerebbe la coda per sempre (`PBI-373`, difetto 9). Con
    `runs/.tick.lock` lasciato da un tick finito il tick decide e lancia."""
    repo = scrivi_coda(tmp_path, "- PBI-337\n")
    albero = tmp_path / "albero"
    albero.mkdir()
    (repo / "runs").mkdir(exist_ok=True)
    (repo / "runs" / ".tick.lock").write_text("", encoding="utf-8")
    chiamati = smista_senza_decidere(monkeypatch)

    uscita = coda.smista(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 0
    assert chiamati == ["decidi", "lancia"]


# --- Il checkout del tick (PBI-392, difetto 75) ------------------------------


def git_in(cartella: Path, *args: str) -> str:
    """`git` vero in `cartella`, con un autore e il ramo `main` di default."""
    fatto = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                            "-c", "init.defaultBranch=main", *args],
                           cwd=cartella, capture_output=True, text=True, check=True)
    return fatto.stdout.strip()


def un_checkout_indietro(tmp_path, monkeypatch, *, tocca="README.md"):
    """Un `origin` nudo, il checkout del tick clonato su `main`, e un merge
    arrivato su `origin` dopo il clone, che cambia il file `tocca`. Il pacchetto
    è una cartella temporanea con la firma dell'albero di `tools/` del checkout,
    com'era all'ultima installazione. Torna `(origin, checkout, pacchetto)`."""
    origin, semina, checkout = tmp_path / "origin.git", tmp_path / "semina", tmp_path / "checkout"
    git_in(tmp_path, "init", "-q", "--bare", str(origin))
    git_in(tmp_path, "clone", "-q", str(origin), str(semina))
    (semina / "tools").mkdir()
    (semina / "tools" / "modulo.py").write_text("x = 1\n", encoding="utf-8")
    (semina / "README.md").write_text("prima\n", encoding="utf-8")
    git_in(semina, "add", "-A")
    git_in(semina, "commit", "-q", "-m", "base")
    git_in(semina, "push", "-q", "origin", "main")
    git_in(tmp_path, "clone", "-q", str(origin), str(checkout))
    (semina / tocca).write_text("dopo\n", encoding="utf-8")
    git_in(semina, "commit", "-q", "-am", "il merge")
    git_in(semina, "push", "-q", "origin", "main")
    pacchetto = tmp_path / "pacchetto"
    (pacchetto / "bin").mkdir(parents=True)
    (pacchetto / ".installato-da").write_text(
        git_in(checkout, "rev-parse", "HEAD:tools") + "\n", encoding="utf-8")
    monkeypatch.setattr(coda, "PACCHETTO", pacchetto)
    return origin, checkout, pacchetto


def test_il_tick_porta_il_checkout_indietro_a_origin_main_e_decide(
    checkout_vero, tmp_path, monkeypatch
):
    """PBI-392, decisione 7. Il tick decide da `origin/main`, ma il runner che
    lancia è quello installato dal suo checkout, che avanzava solo col `ff-only`
    a mano: il 01/10 quel passo è saltato e il giro 2 di PBI-386 è partito col
    runner di prima (difetto 75 di PBI-102). Con il checkout indietro di un
    merge che non tocca `tools/`, il tick lo porta a `origin/main` col `ff-only`
    e decide nello stesso passaggio."""
    origin, checkout, _ = un_checkout_indietro(tmp_path, monkeypatch)
    albero = tmp_path / "albero"
    albero.mkdir()
    chiamati = smista_senza_decidere(monkeypatch)
    monkeypatch.setattr(coda, "decidi", lambda repo, worktree: (
        chiamati.append("decidi") or coda.Finita()))

    uscita = coda.smista(["--repo", str(checkout), "--worktree", str(albero)])

    assert uscita == 0
    assert git_in(checkout, "rev-parse", "HEAD") == git_in(origin, "rev-parse", "main")
    assert chiamati == ["decidi"]


def diverge(checkout: Path) -> None:
    """Un commit locale sul checkout, che `origin` non ha: rami divergenti."""
    (checkout / "LOCALE.md").write_text("di una persona\n", encoding="utf-8")
    git_in(checkout, "add", "LOCALE.md")
    git_in(checkout, "commit", "-q", "-m", "locale")


def su_un_altro_ramo(checkout: Path) -> None:
    git_in(checkout, "switch", "-q", "-c", "prova-a-mano")


def fetch_che_fallisce(checkout: Path) -> None:
    git_in(checkout, "remote", "set-url", "origin", str(checkout.parent / "non-ce.git"))


@pytest.mark.parametrize("guasta", [diverge, su_un_altro_ramo, fetch_che_fallisce],
                         ids=["divergente", "altro-ramo", "fetch-fallito"])
def test_il_checkout_che_non_si_allinea_ferma_il_tick_senza_toccarlo(
    checkout_vero, tmp_path, monkeypatch, guasta
):
    """PBI-392, decisione 7. Il checkout deve stare su `main`, il `fetch` deve
    riuscire e `git` deve accettare il `ff-only`. Se no il tick scrive `non
    allineato: <la ragione>` in `coda.log`, esce con 0, non decide e non lancia —
    col runner di prima sarebbe il difetto 75. È un avviso e non una
    correzione: il checkout resta com'era, sullo stesso commit e sullo stesso
    ramo (`ADR-0008`)."""
    _, checkout, _ = un_checkout_indietro(tmp_path, monkeypatch)
    guasta(checkout)
    prima = (git_in(checkout, "rev-parse", "HEAD"),
             git_in(checkout, "branch", "--show-current"))
    albero = tmp_path / "albero"
    albero.mkdir()
    chiamati = smista_senza_decidere(monkeypatch)

    uscita = coda.smista(["--repo", str(checkout), "--worktree", str(albero)])

    assert uscita == 0
    assert chiamati == []
    righe = (checkout / coda.LOG).read_text(encoding="utf-8").splitlines()
    assert len(righe) == 1 and righe[0].split("  ", 1)[1].startswith("non allineato: "), righe
    assert (git_in(checkout, "rev-parse", "HEAD"),
            git_in(checkout, "branch", "--show-current")) == prima
