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

`tools/` non è un pacchetto installato e non deve diventarlo per un test: si
carica il modulo dal suo percorso, come fa `test_importa_storico.py`.
"""

import fcntl
import importlib.util
import datetime
import json
import sys
from pathlib import Path

import pytest

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


def test_una_finestra_di_pr_mergiate_piena_non_produce_lancia(tmp_path, monkeypatch):
    """Un elenco lungo quanto il limite può essere tagliato, e un elenco tagliato mente.

    `gh pr list --limit N` non dice mai «non lo so»: una PR caduta fuori dalla
    finestra semplicemente non c'è, e il tick la legge come «non mergiato». Per
    una voce di coda il cui ramo su `origin` sia stato potato dopo il merge quel
    silenzio diventa `Lancia`, cioè il rilancio di un PBI già in `main` — il
    doppione che `test_la_testa_con_un_ramo_su_origin_e_senza_merge_si_attende`
    impedisce, entrato dall'altra porta. È anche il rovescio esatto del guasto
    che `pbi_mergiati()` evita leggendo il titolo invece del nome del ramo.

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
        if "asdlc_runner.py" in " ".join(cmd):
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
        ["python3", "tools/asdlc_runner.py", "PBI-337"],
    ]
    assert {cwd for _, cwd in visti} == {albero}
    for aperto in tenuti:
        aperto.close()


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

    assert not any("asdlc_runner.py" in " ".join(cmd) for cmd in visti)


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

    uscita = coda.main(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 0
    assert ["python3", "tools/asdlc_runner.py", "PBI-337"] in visti
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

    uscita = coda.main(
        ["--repo", str(repo), "--worktree", str(albero), "--dry-run"]
    )

    assert uscita == 0
    assert "PBI-337" in capsys.readouterr().out
    eseguiti = [" ".join(cmd) for cmd in visti]
    assert not [c for c in eseguiti if "asdlc_runner.py" in c], eseguiti
    assert not [c for c in eseguiti if "switch" in c or "fetch" in c or "checkout" in c], eseguiti


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

    coda.main(argomenti)
    coda.main(argomenti)

    righe = (repo / "runs" / "coda.log").read_text(encoding="utf-8").splitlines()
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

    coda.main(["--repo", str(repo), "--worktree", str(albero), "--dry-run"])

    stampato = capsys.readouterr().out
    assert "PBI-340" in stampato
    assert "Da decidere, se le dodici colonne non ci stanno" in stampato
    assert "Da decidere" in (repo / "runs" / "coda.log").read_text(encoding="utf-8")


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

    uscita = coda.main(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 1
    log = (repo / "runs" / "coda.log").read_text(encoding="utf-8")
    assert "fetch" in log


def test_un_runner_che_esce_male_lo_scrive_nel_log(tmp_path, monkeypatch):
    """Il gesto subito dopo il pre-flight, che ha la stessa ragione di stare nel log.

    Il codice d'uscita del runner copre ciò che succede **prima** del distacco, e
    solo quello: `--e2e`, che il runner rifiuta con `2`; un argomento che argparse
    non riconosce; `python3` che su quella macchina non c'è, e allora `esegui()`
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
        if "asdlc_runner.py" in " ".join(cmd):
            return 127, "comando non eseguibile: python3 — [Errno 2] No such file"
        return 0, ""

    monkeypatch.setattr(coda, "esegui", python_che_non_ce)

    uscita = coda.main(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 1
    log = (repo / "runs" / "coda.log").read_text(encoding="utf-8")
    assert "non lanciato" in log, log
    assert "uscita 127" in log, log
    assert "python3" in log, log


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

    uscita = coda.main(["--repo", str(repo), "--worktree", str(albero)])

    assert uscita == 1
    log = (repo / "runs" / "coda.log").read_text(encoding="utf-8")
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

    uscita = coda.main(["--repo", str(repo), "--worktree", str(repo)])

    assert uscita == 2
    assert "--worktree" in capsys.readouterr().out
