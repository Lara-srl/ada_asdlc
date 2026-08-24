"""Il runner ASDLC: le due diagnosi che gli mancavano, e da dove nasce il branch.

`backlog/PBI-102`. Tre difetti misurati sulla run notturna del 20→21/08, e due
di questi costano ore vere:

- **Un rilievo del Critic indirizzato a una persona deve sospendere**, non
  consumare revisioni. Il ramo giusto esiste già — *«fermato: domanda
  dell'agente»* — ma lo può attivare solo il builder. Quando è il Critic a
  trovare qualcosa che nessuna fix può chiudere, il builder non ha vie d'uscita:
  rende il rilievo più visibile, il runner conta un giro e riparte. Su PBI-203
  sono stati **cinque giri, 1h26m, 22 commit** per finire dove si era al primo.
- **`git switch -c` parte da dove si trova.** Due PBI nella stessa invocazione e
  il secondo nasce dal branch del primo: le PR si impilano, e il diff del secondo
  contiene il lavoro del primo.

I test girano **senza rete e senza git**: `git` ed `esegui` sono i due varchi
verso il mondo, e si sostituiscono. Un test del runner che chiamasse git davvero
sarebbe un test che riscrive il repository in cui gira.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "asdlc_runner", REPO / "tools" / "asdlc_runner.py"
)
runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner
_spec.loader.exec_module(runner)


# --- Niente infrastruttura sotto uno strumento da riga di comando ------------


@pytest.fixture(autouse=True)
def db():
    return None


@pytest.fixture(autouse=True)
def clear_login_limiter():
    return None


@pytest.fixture(autouse=True)
def clear_event_bus():
    return None


@pytest.fixture
def git_finto(monkeypatch):
    """Registra i comandi git invece di eseguirli, e risponde il minimo indispensabile."""
    chiamate: list[tuple[str, ...]] = []

    def _git(*args: str) -> str:
        chiamate.append(args)
        if args[:2] == ("status", "--porcelain"):
            return ""  # albero pulito
        if args[:2] == ("rev-list", "--count"):
            return "3"
        return ""

    monkeypatch.setattr(runner, "git", _git)
    return chiamate


class TestIlCriticPuoSospendere:
    """Un rilievo che aspetta una persona non è «non pronto»: è un'altra diagnosi."""

    def test_riconosce_il_verdetto_sospeso_e_ne_prende_la_domanda(self, monkeypatch):
        uscita = (
            "**1. [processo] Il CHIEDI sulla migrazione è stato saltato**\n"
            "- Violato: AGENTS.md, CHIEDI prima di una migrazione su tabelle con dati\n"
            "STOP: si può eseguire 0011 su `pratiche`, che ha 46 righe?\n"
            "VERDETTO: SOSPESO\n"
        )
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, uscita))

        verdetto = runner.revisione_critica(REPO / "backlog" / "PBI-102-soglia-di-revisione-del-runner.md")

        assert verdetto.esito == "sospeso"
        assert verdetto.domanda == "si può eseguire 0011 su `pratiche`, che ha 46 righe?"

    def test_un_sospeso_senza_domanda_e_un_guasto_non_un_giudizio(self, monkeypatch):
        """Sospendere senza dire cosa si aspetta lascia la persona davanti a un muro.

        Stessa regola del verdetto mancante: un guasto dello strumento deve
        somigliare a un guasto, non a un giudizio.
        """
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "VERDETTO: SOSPESO\n"))

        with pytest.raises(RuntimeError, match="domanda"):
            runner.revisione_critica(REPO / "backlog" / "PBI-102-soglia-di-revisione-del-runner.md")

    def test_pass_e_non_pronto_restano_quelli_di_prima(self, monkeypatch):
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "VERDETTO: PASS\n"))
        assert runner.revisione_critica(Path("backlog/x.md")).esito == "pass"

        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "VERDETTO: NON PRONTO\n"))
        assert runner.revisione_critica(Path("backlog/x.md")).esito == "non pronto"


class TestIlSospesoChiudeAlPrimoGiro:
    def test_non_consuma_le_revisioni(self, monkeypatch, git_finto, tmp_path):
        """È il difetto che è costato quattro giri su PBI-203.

        Il conto non è teorico: `MAX_REVISIONI + 1` giri, ognuno con builder e
        gate, per arrivare a una diagnosi che era disponibile al primo.
        """
        giri = {"critic": 0}

        def critic_sospende(_pbi_path):
            giri["critic"] += 1
            return runner.Verdetto("sospeso", "chi decide se la migrazione si esegue?", "rapporto")

        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(runner, "revisione_critica", critic_sospende)

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "sospeso"
        assert esito.revisioni == 0, "un sospeso non consuma revisioni: la risposta è di una persona"
        assert giri["critic"] == 1, "il Critic non si richiama: la diagnosi non cambia riprovando"
        assert "chi decide" in esito.nota

    def test_la_nota_dice_che_e_il_critic_a_chiedere(self, monkeypatch, git_finto):
        """Le due sospensioni non sono la stessa cosa e la nota le distingue.

        Il builder si ferma su un'ambiguità del PBI; il Critic su una violazione
        che nessuna fix può chiudere. Chi rilegge `runs/tempi.csv` deve sapere da
        quale lato è arrivata la domanda, perché il rimedio è diverso: la prima si
        chiude riscrivendo il PBI, la seconda rispondendo.
        """
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(
            runner, "revisione_critica",
            lambda p: runner.Verdetto("sospeso", "la migrazione si esegue?", "rapporto"),
        )

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)
        assert "critic" in esito.nota.lower()


class TestIlBranchNasceDaOriginMain:
    def test_ramifica_da_origin_main_senza_passare_dal_main_locale(self, monkeypatch, git_finto):
        """Due PBI nella stessa invocazione devono produrre branch **fratelli**.

        Senza questo, il secondo nasce dal branch del primo: le PR si impilano e
        il diff del secondo contiene il lavoro del primo. È la ragione per cui
        `ada-notte.sh` esiste come ciclo esterno.

        E ci si arriva **senza fare `switch main`**: il runner gira nel worktree
        `ada-run`, e un branch può essere estratto in un solo worktree alla volta.
        Con `main` estratto nel repository principale — che è dove sta di solito —
        `git switch main` là dentro fallisce con «already used by worktree», e
        `git()` alza: il PBI muore prima di cominciare. Ramificare direttamente da
        `origin/main` non tocca nessun branch locale e non può collidere.
        """
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(
            runner, "revisione_critica", lambda p: runner.Verdetto("pass", "", "rapporto")
        )

        runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        comandi = [" ".join(c) for c in git_finto]
        crea = next(i for i, c in enumerate(comandi) if c.startswith("switch -c pbi/pbi-102"))

        assert comandi[crea] == "switch -c pbi/pbi-102 origin/main", (
            "il punto di partenza va scritto nel comando, non lasciato a «dove mi trovo»"
        )
        assert any(c.startswith("fetch") for c in comandi[:crea]), (
            "un origin/main vecchio è lo stesso difetto con un nome diverso"
        )
        assert not any(c.startswith("switch main") or c.startswith("checkout main")
                       for c in comandi), (
            "estrarre `main` fallisce nel worktree: è già estratto nel repository principale"
        )

    def test_i_commit_si_contano_da_origin_main(self, monkeypatch, git_finto):
        """Il `main` locale del worktree può essere indietro di giorni: da quando
        non lo si estrae più, nessuno lo aggiorna. Contare `main..HEAD` gonfierebbe
        i commit del PBI con quelli che main ha ricevuto nel frattempo."""
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(
            runner, "revisione_critica", lambda p: runner.Verdetto("pass", "", "ok")
        )

        runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        conteggi = [c for c in git_finto if c[:2] == ("rev-list", "--count")]
        assert conteggi, "il conteggio dei commit non è stato fatto"
        assert all("origin/main..HEAD" in c for c in conteggi)


class TestIlRiepilogoNonSommaStatiDiversi:
    def test_mostra_gli_stati_di_ogni_pbi(self, monkeypatch, tmp_path, capsys):
        """Sommare un `fatto` e un `non convergente` in una riga sola misura la
        fatica e nasconde la causa: 1h26m spesi bene e 1h26m buttati si leggono
        uguali."""
        csv_finto = tmp_path / "tempi.csv"
        csv_finto.write_text(
            "run,pbi,stato,iniziato,finito,durata_s,durata_hms,builder_s,gate_s,critic_s,"
            "tentativi,revisioni,commit,pr,nota\n"
            "1,PBI-203,non convergente,x,y,5000,1:23:20,4000,500,500,5,5,22,,niente\n"
            "2,PBI-203,fatto,x,y,1000,0:16:40,800,100,100,1,0,4,,\n"
            "3,PBI-205,sospeso,x,y,600,0:10:00,500,50,50,1,0,2,,la migrazione\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(runner, "CSV_TEMPI", csv_finto)

        runner.riepilogo(tariffa=None)
        uscita = capsys.readouterr().out

        assert "non convergente" in uscita
        assert "sospeso" in uscita
        assert "fatto" in uscita


class TestLIgieneNonContaIlRegistroDelRunner:
    def test_il_csv_dei_tempi_non_conta_come_albero_sporco(self, monkeypatch):
        """Il runner scrive `runs/tempi.csv` a fine invocazione. Da quando quel
        file è **versionato**, il giro dopo lo trova modificato e si ferma su
        «albero di lavoro sporco» — al primo PBI, prima ancora di cominciare.

        Il controllo esiste per non perdere lavoro non committato dell'agente.
        Il registro del runner non è lavoro dell'agente: è la sua contabilità.
        """
        visti: list[tuple[str, ...]] = []

        def _git(*args: str) -> str:
            visti.append(args)
            if args[0] == "status":
                # Il mondo reale del giro dopo: solo il registro è cambiato.
                return " M runs/tempi.csv" if "runs" not in " ".join(args) else ""
            if args[:2] == ("rev-list", "--count"):
                return "1"
            return ""

        monkeypatch.setattr(runner, "git", _git)
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(
            runner, "revisione_critica", lambda p: runner.Verdetto("pass", "", "ok")
        )

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert esito.stato != "fermato", (
            "il registro del runner non è lavoro non committato: escluderlo dal "
            "controllo, o il secondo giro non parte mai"
        )

    def test_un_file_vero_non_committato_ferma_ancora_tutto(self, monkeypatch):
        """Il rovescio, che è la ragione per cui il controllo esiste: ciò che non
        è committato non esiste, e l'agente non deve partire sopra al lavoro di
        qualcun altro."""
        monkeypatch.setattr(
            runner, "git",
            lambda *a: " M backend/app/marginalita.py" if a[0] == "status" else "",
        )
        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)
        assert esito.stato == "fermato"
        assert "sporco" in esito.nota


class TestUnSospesoFermaLaCatena:
    def test_sospeso_e_fra_gli_stati_che_interrompono(self):
        """`sospeso` è «fermo su una domanda» quanto `fermato`, e la ragione per
        cui la catena si interrompe è la stessa: i PBI successivi poggiano su
        questo, e la domanda aperta è esattamente ciò che non si supera
        proseguendo.

        Senza questa riga il runner tira dritto dopo un sospeso — che è il
        difetto che il sospeso esisteva per togliere, spostato di un livello.
        """
        assert "sospeso" in runner.STATI_CHE_INTERROMPONO
        assert {"rosso", "respinto", "non convergente", "fermato"} <= set(
            runner.STATI_CHE_INTERROMPONO
        )


class TestLaSessioneRuotaFraLeRevisioni:
    """Il contesto pulito vale per revisione, non una volta per PBI.

    `decisions/ADR-0015`, *Dove entra*. `-c` è giusto **dentro** un giro — dove
    serve a non rileggere tutto il repository per un gate rosso — e sbagliato
    **fra** i giri: dopo un NON PRONTO il Builder porta con sé la finestra in cui
    ha già discusso, e su PBI-309 quella finestra gli aveva insegnato che lo Scope
    è negoziabile. Con `MAX_REVISIONI = 4` sono fino a quindici turni nella stessa
    sessione, ed è il punto in cui PBI-201 ha misurato che escono i difetti peggiori.
    """

    def scenario(self, monkeypatch, comandi):
        """Un gate rosso nella prima revisione, poi un NON PRONTO, poi verde.

        Serve a produrre i tre giri che distinguono i due casi: il ritentativo
        dentro la revisione e il primo giro della revisione dopo.
        """
        gate = {"chiamate": 0}
        critic = {"chiamate": 0}

        def esegui_finto(cmd, cwd):
            comandi.append(cmd)
            return 0, "FATTO: fatto\n"

        def gira_gate_finto(attivi):
            gate["chiamate"] += 1
            return [("pytest", "1 failed")] if gate["chiamate"] == 1 else []

        def critic_finto(_pbi_path):
            critic["chiamate"] += 1
            if critic["chiamate"] == 1:
                return runner.Verdetto("non pronto", "", "manca una deroga")
            return runner.Verdetto("pass", "", "")

        monkeypatch.setattr(runner, "esegui", esegui_finto)
        monkeypatch.setattr(runner, "gira_gate", gira_gate_finto)
        monkeypatch.setattr(runner, "revisione_critica", critic_finto)

    def test_il_ritentativo_su_un_gate_rosso_continua_la_sessione(self, monkeypatch, git_finto):
        comandi: list[list[str]] = []
        self.scenario(monkeypatch, comandi)
        runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert "-c" not in comandi[0], "il primo giro in assoluto apre la sessione"
        assert "-c" in comandi[1], "un gate rosso non vale una rilettura di tutto il repository"

    def test_la_revisione_dopo_un_non_pronto_riparte_pulita(self, monkeypatch, git_finto):
        comandi: list[list[str]] = []
        self.scenario(monkeypatch, comandi)
        runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert len(comandi) == 3, "un rosso, il suo rimedio, e il giro dopo il NON PRONTO"
        assert "-c" not in comandi[2], (
            "dopo un NON PRONTO la sessione riparte: il Builder non deve portarsi dietro "
            "la finestra in cui ha già argomentato"
        )


class TestIlPromptDiRimedioSiReggeDaSolo:
    """Una sessione nuova riceve solo ciò che il prompt le porta.

    Finché il rimedio continuava la sessione del Builder, `PROMPT_RIMEDIO` poteva
    contenere il solo rapporto del Critic: il resto era già nella finestra. Con la
    rotazione non lo è più, e un Builder che riceve «chiudi queste violazioni»
    senza sapere su quale PBI sta lavorando né quali sono i confini di giudizio
    farebbe danni con le migliori intenzioni. È l'avvertenza ⚠️ di ADR-0015.
    """

    def test_porta_con_se_la_costituzione_e_il_PBI(self):
        prompt = runner.PROMPT_RIMEDIO.format(
            rapporto="1. [scope]: due file fuori perimetro",
            pbi_path="backlog/PBI-102-soglia-di-revisione-del-runner.md",
        )
        assert "AGENTS.md" in prompt, "i confini di giudizio non sono più nella finestra"
        assert "backlog/PBI-102-soglia-di-revisione-del-runner.md" in prompt, (
            "senza il PBI il Builder non sa cosa stava costruendo"
        )
        assert "1. [scope]" in prompt, "il rapporto del Critic resta il cuore del prompt"

    def test_ripete_le_regole_che_il_rimedio_puo_violare(self):
        """Il rimedio è codice come il resto: stesse regole, non un'eccezione.

        Un commit di rimedio che accorpa tre correzioni, o che chiude un rilievo
        cancellando un test, passa i gate e disfa quello che il Critic difendeva.
        """
        prompt = runner.PROMPT_RIMEDIO.format(rapporto="x", pbi_path="backlog/x.md")
        assert "test" in prompt.lower(), "il rimedio non si chiude spegnendo un test"
        assert "commit" in prompt.lower(), "un commit per rimedio, come nel resto del PBI"


class TestUnGiroSpesoACommittareNonEUnGateRosso:
    """PBI-208, notte del 24/08: `rosso` in dieci minuti **senza un gate eseguito**.

    Il Builder aveva committato il test e un refactor lasciando fuori il file
    nuovo — `AnalisiPage.tsx`, la pagina intera, 840 righe — perché `git commit
    -am` i file non tracciati non li prende. L'albero è rimasto sporco a ogni
    giro, e i tre tentativi si sono consumati tutti sul controllo d'igiene: il
    rapporto diceva *«gate ancora rossi dopo i tentativi previsti»* con
    `gate_rossi` vuoto, cioè una diagnosi falsa che manda a cercare il guasto
    dove non è.

    `MAX_TENTATIVI` conta i **gate rossi** — «hai sbagliato una riga, riprova» —
    e un giro speso a chiedere un commit non è quella cosa lì: contarlo insieme
    toglie al lavoro vero i tentativi che gli servivano.
    """

    def _mondo(self, monkeypatch, stati: list[str], gate: list[list]):
        """Un runner senza mondo: git risponde da una lista, i gate da un'altra."""
        rimasti_stati, rimasti_gate = list(stati), list(gate)
        eseguiti: list[str] = []

        def _git(*args: str) -> str:
            if args[:2] == ("status", "--porcelain"):
                return rimasti_stati.pop(0) if rimasti_stati else ""
            if args[:2] == ("rev-list", "--count"):
                return "2"
            return ""

        def _gate(attivi):
            eseguiti.append("gate")
            return rimasti_gate.pop(0) if rimasti_gate else []

        monkeypatch.setattr(runner, "git", _git)
        monkeypatch.setattr(runner, "gira_gate", _gate)
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(
            runner, "revisione_critica", lambda p: runner.Verdetto("pass", "", "ok")
        )
        return eseguiti

    def test_i_giri_di_igiene_non_mangiano_i_tentativi_di_gate(self, monkeypatch):
        """Due giri persi a far committare, poi il lavoro vero: i tre tentativi
        di gate devono esserci ancora tutti."""
        # Il primo `status` è quello d'ingresso, prima che il PBI cominci.
        eseguiti = self._mondo(
            monkeypatch,
            stati=["", "?? nuovo.tsx", "?? nuovo.tsx", "", "", ""],
            gate=[[("pytest", "rosso")], [("pytest", "rosso")], []],
        )

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "fatto", (
            f"chiuso {esito.stato}: i giri d'igiene hanno consumato i tentativi "
            "che servivano ai gate"
        )
        assert len(eseguiti) == 3, "i gate devono avere avuto i loro tre tentativi"

    def test_un_albero_che_resta_sporco_chiude_dicendo_la_verita(self, monkeypatch):
        """Il rovescio: un Builder che non committa mai deve fermarsi — e la nota
        deve dire *questo*, non «gate rossi» che sarebbe falso.

        Il tetto separato esiste perché il giro d'igiene non è gratis: senza,
        basta un file che l'agente non riesce a committare e il runner gira
        finché non finisce la notte.
        """
        self._mondo(
            monkeypatch,
            stati=[""] + ["?? nuovo.tsx"] * 20,
            gate=[],
        )

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert esito.stato != "fatto"
        assert "committ" in esito.nota or "sporco" in esito.nota, (
            f"nota fuorviante: «{esito.nota}» — l'albero è rimasto sporco, i gate "
            "non hanno mai girato"
        )
        assert "gate" not in esito.nota.lower(), (
            "dire «gate rossi» dove i gate non sono mai partiti manda a cercare "
            "il guasto dove non è: è successo su PBI-208"
        )

    def test_il_registro_del_runner_non_e_lavoro_da_far_committare(self, monkeypatch):
        """`runs/tempi.csv` è escluso all'ingresso ma non dentro il giro: nella
        catena, il secondo PBI trova la riga del primo e il Builder si sente
        chiedere di committare la contabilità del runner dentro il suo branch."""
        viste: list[tuple[str, ...]] = []

        def _git(*args: str) -> str:
            viste.append(args)
            if args[:2] == ("status", "--porcelain"):
                return "" if "runs" in " ".join(args) else " M runs/tempi.csv"
            if args[:2] == ("rev-list", "--count"):
                return "2"
            return ""

        monkeypatch.setattr(runner, "git", _git)
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(
            runner, "revisione_critica", lambda p: runner.Verdetto("pass", "", "ok")
        )

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "fatto", (
            "il registro del runner ha fatto sembrare sporco l'albero dentro il giro"
        )
        assert all(
            "runs" in " ".join(a) for a in viste if a[:2] == ("status", "--porcelain")
        ), "ogni controllo d'igiene esclude `runs/`, dentro il giro come all'ingresso"

    def test_il_prompt_dice_di_prendere_anche_i_file_nuovi(self):
        """La causa prima: `git commit -am` non prende i file non tracciati.

        Il prompt che chiede il commit deve dirlo, perché è esattamente lì che
        il Builder di PBI-208 si è perso — e la pagina che aveva scritto è
        rimasta a un `git add` dal non esistere.
        """
        prompt = runner.PROMPT_IGIENE.format(sporco="?? frontend/src/pages/AnalisiPage.tsx")
        assert "add" in prompt, "senza `git add` i file nuovi non entrano nel commit"
        assert "AnalisiPage" in prompt, "il Builder deve vedere *cosa* è rimasto fuori"
