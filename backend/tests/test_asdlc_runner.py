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

import csv
import importlib.util
import json
import subprocess
import sys
from contextlib import contextmanager
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


@pytest.fixture(autouse=True)
def lucchetto_di_prova(tmp_path, monkeypatch):
    """Il lucchetto del runner, spostato in una cartella usa e getta.

    `LUCCHETTO` è `runs/.runner.lock`, un percorso solo per albero, e i test che
    passano da `main()` lo prendono davvero. Lanciare la suite **mentre** un giro è
    vivo trovava quel file già preso e faceva rosso nove test di `main()` per colpa
    di un processo vicino invece che del codice — ed è esattamente la condizione in
    cui la suite gira sempre, perché il Builder lo lancia il runner, che il
    lucchetto ce l'ha in mano. `LOG_DIR` quei test lo spostavano già; questo no,
    perché `LUCCHETTO` è calcolato all'import e non segue la patch.
    """
    monkeypatch.setattr(runner, "LUCCHETTO", tmp_path / ".runner.lock")


def elenco_backlog() -> str:
    """Cosa risponde `git ls-tree origin/main backlog/`: il runner cerca lì il file
    del PBI (difetto 7), quindi ogni finto `git` deve saperlo dire."""
    return "\n".join(f"backlog/{f.name}" for f in sorted((REPO / "backlog").glob("*.md")))

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
        if args[:2] == ("ls-tree", "--name-only"):
            return elenco_backlog()
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


class TestIlPbiSiCercaSuOriginMain:
    """Difetto 7 di PBI-102, ricaduto due volte.

    Il worktree del runner resta fermo al commit su cui qualcuno l'ha messo
    l'ultima volta; il branch invece nasce da `origin/main` (`crea_branch`).
    Un PBI mergiato dopo quell'ultimo `switch` c'è **dove il lavoro si farà** e
    non c'è **dove lo si cercava**: il giro chiudeva «saltato (PBI inesistente)»
    con il file sotto il naso, e chi lanciava perdeva il giro senza capire.
    """

    def test_un_pbi_che_ce_solo_su_origin_main_si_esegue(self, monkeypatch):
        chiamate: list[tuple[str, ...]] = []

        def _git(*args: str) -> str:
            chiamate.append(args)
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:2] == ("rev-list", "--count"):
                return "3"
            if args[:2] == ("ls-tree", "--name-only"):
                # origin/main ce l'ha; l'albero estratto no — non esiste su disco.
                return "backlog/PBI-999-mergiato-stanotte.md\nbacklog/README.md"
            return ""

        monkeypatch.setattr(runner, "git", _git)
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(
            runner, "revisione_critica", lambda p: runner.Verdetto("pass", "", "rapporto")
        )

        esito = runner.esegui_pbi("PBI-999", attivi=set(), dry=False, con_pr=False)

        assert esito.stato != "saltato", esito.nota
        assert any(c[:2] == ("ls-tree", "--name-only") for c in chiamate), (
            "il nome del file va chiesto a origin/main, non all'albero estratto"
        )
        assert any(c[:1] == ("fetch",) for c in chiamate), (
            "un origin/main vecchio non sa del PBI mergiato stanotte"
        )

    def test_un_pbi_che_non_esiste_da_nessuna_parte_resta_saltato(self, monkeypatch, git_finto):
        esito = runner.esegui_pbi("PBI-000", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "saltato"
        assert "inesistente" in esito.nota

    def test_senza_rete_si_ripiega_sullalbero_estratto(self, monkeypatch, capsys):
        """Il fetch che non parte non è una ragione per non fare il PBI che si ha
        già in casa: si ripiega, e lo si dice."""

        def _git(*args: str) -> str:
            if args[:1] == ("fetch",) or args[:2] == ("ls-tree", "--name-only"):
                raise RuntimeError("Could not resolve host: github.com")
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:2] == ("rev-list", "--count"):
                return "3"
            return ""

        monkeypatch.setattr(runner, "git", _git)

        trovato = runner.trova_pbi("PBI-102")

        assert trovato is not None and trovato.name.startswith("PBI-102-")
        assert "origin/main" in capsys.readouterr().out


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


class TestLIgieneGuardaTuttoLAlbero:
    """L'eccezione su `runs/` non c'è più, perché non c'è più la sua causa.

    Il controllo d'igiene ha escluso `runs/` da quando `runs/tempi.csv` è
    versionato: il runner lo scriveva a fine invocazione, e il giro dopo lo
    trovava modificato fermandosi su «albero di lavoro sporco» prima ancora di
    cominciare. L'eccezione era la toppa; `ADR-0020` ha tolto il chiodo — il
    registro esce dai branch — e la regola torna intera, che è ciò che il criterio
    del difetto 12 chiedeva: *«finché serve, è il sintomo che questo punto non è
    chiuso»*.
    """

    def test_nessun_controllo_digiene_ha_piu_eccezioni(self, monkeypatch):
        viste: list[tuple[str, ...]] = []

        def _git(*args: str) -> str:
            viste.append(args)
            if args[:2] == ("rev-list", "--count"):
                return "2"
            if args[:2] == ("ls-tree", "--name-only"):
                return elenco_backlog()
            return ""

        monkeypatch.setattr(runner, "git", _git)
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(
            runner, "revisione_critica", lambda p: runner.Verdetto("pass", "", "ok")
        )

        runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        controlli = [a for a in viste if a[:2] == ("status", "--porcelain")]
        assert controlli, "il controllo d'igiene non è stato fatto"
        assert all("exclude" not in " ".join(a) for a in controlli), (
            "un pezzo di albero escluso è un pezzo in cui il lavoro dell'agente può "
            "sparire senza che nessuno se ne accorga"
        )

    def test_un_file_vero_non_committato_ferma_ancora_tutto(self, monkeypatch):
        """Il rovescio, che è la ragione per cui il controllo esiste: ciò che non
        è committato non esiste, e l'agente non deve partire sopra al lavoro di
        qualcun altro."""
        monkeypatch.setattr(
            runner, "git",
            lambda *a: (" M backend/app/marginalita.py" if a[0] == "status"
                        else elenco_backlog() if a[:2] == ("ls-tree", "--name-only")
                        else ""),
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
            if args[:2] == ("ls-tree", "--name-only"):
                return elenco_backlog()
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

    def test_dentro_il_giro_lalbero_si_guarda_intero(self, monkeypatch):
        """Il gemello del controllo d'ingresso, dentro il giro.

        Qui l'eccezione su `runs/` serviva alla catena: il secondo PBI trovava la
        riga di registro del primo e il Builder si sentiva chiedere di committare
        la contabilità del runner dentro il suo branch. Da `ADR-0020` quella riga
        non c'è più, e l'albero si guarda intero — se qualcosa resta fuori, resta
        fuori davvero.
        """
        viste: list[tuple[str, ...]] = []

        def _git(*args: str) -> str:
            viste.append(args)
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:2] == ("rev-list", "--count"):
                return "2"
            if args[:2] == ("ls-tree", "--name-only"):
                return elenco_backlog()
            return ""

        monkeypatch.setattr(runner, "git", _git)
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(
            runner, "revisione_critica", lambda p: runner.Verdetto("pass", "", "ok")
        )

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "fatto"
        assert all(
            "exclude" not in " ".join(a)
            for a in viste if a[:2] == ("status", "--porcelain")
        ), "nessun controllo d'igiene ha più eccezioni, dentro il giro come all'ingresso"

    def test_ogni_revisione_ritrova_i_suoi_tentativi(self, monkeypatch):
        """La pazienza sui gate è **per revisione**, non per PBI.

        `e.tentativi` non si azzera mai: è la fatica totale, ed è il numero che
        finisce in `runs/tempi.csv`. Farne anche il criterio d'uscita
        significherebbe che alla terza revisione il Builder non ha più un giro —
        chiuderebbe `rosso` senza aver eseguito niente, che è esattamente la
        diagnosi falsa da cui parte questa classe, spostata di un livello.
        """
        giri = {"critic": 0}

        def _critic(_p):
            giri["critic"] += 1
            # Quattro NON PRONTO: `e.tentativi` supera MAX_TENTATIVI ben prima
            # che il Critic si dichiari soddisfatto.
            if giri["critic"] <= 4:
                return runner.Verdetto("non pronto", "", "manca una deroga")
            return runner.Verdetto("pass", "", "")

        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(runner, "revisione_critica", _critic)
        monkeypatch.setattr(
            runner, "git",
            lambda *a: ("2" if a[:2] == ("rev-list", "--count")
                        else elenco_backlog() if a[:2] == ("ls-tree", "--name-only")
                        else ""),
        )

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "fatto", (
            f"chiuso {esito.stato} dopo {esito.tentativi} tentativi: il tetto dei gate "
            "ha smesso di valere per revisione e ha cominciato a valere per PBI"
        )
        assert esito.tentativi > runner.MAX_TENTATIVI, (
            "il registro deve continuare a contare la fatica totale"
        )


class TestUnFermatoDiceQuantiCommitHaFatto:
    """Difetto 10 di PBI-102.

    Il conteggio dei commit stava **dopo** il giro dei gate: ogni uscita
    anticipata — lo `STOP` del Builder, l'albero che resta sporco — scriveva
    `commit = 0` nel registro. Su PBI-209 quel `fermato` aveva **otto commit e
    2.174 righe** dentro, e il registro diceva zero: chi legge il giorno dopo
    decide se buttare il branch guardando quella colonna.
    """

    def _mondo(self, monkeypatch, uscita_builder: str, commit: str = "8"):
        def _git(*args: str) -> str:
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:2] == ("rev-list", "--count"):
                return commit
            if args[:2] == ("ls-tree", "--name-only"):
                return elenco_backlog()
            return ""

        monkeypatch.setattr(runner, "git", _git)
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, uscita_builder))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(
            runner, "revisione_critica", lambda p: runner.Verdetto("pass", "", "ok")
        )

    def test_uno_stop_del_builder_conta_i_suoi_commit(self, monkeypatch):
        self._mondo(monkeypatch, "STOP: la migrazione tocca una tabella con dati sopra\n")

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "fermato"
        assert esito.commit == 8, (
            "un fermato a mani vuote e un fermato con otto commit dentro si "
            "leggono uguali, e il secondo finisce buttato"
        )

    def test_un_sospeso_del_critic_conta_i_suoi_commit(self, monkeypatch):
        self._mondo(monkeypatch, "FATTO: fatto\n", commit="4")
        monkeypatch.setattr(
            runner, "revisione_critica",
            lambda p: runner.Verdetto("sospeso", "il CHIEDI sulla migrazione", "rapporto"),
        )

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "sospeso"
        assert esito.commit == 4


class TestDiUnGateRossoRestaLaRagione:
    """Difetto 14 di PBI-102.

    `gate_rossi` teneva i **nomi** dei gate caduti e buttava il loro output: il
    rapporto diceva *«pytest»* e chi lo leggeva doveva rifare girare la suite per
    sapere quale test, o avere il Builder ancora sotto mano. La coda dell'output
    ce l'abbiamo già in mano — `gira_gate` la restituisce per darla al Builder —
    e buttarla è l'unico passaggio che costa qualcosa.
    """

    def _mondo_rosso(self, monkeypatch):
        def _git(*args: str) -> str:
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:2] == ("rev-list", "--count"):
                return "2"
            if args[:2] == ("ls-tree", "--name-only"):
                return elenco_backlog()
            return ""

        monkeypatch.setattr(runner, "git", _git)
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(
            runner, "gira_gate",
            lambda attivi: [("pytest", "E   assert 496.51 == 609.00\ntest_riga_12 FAILED")],
        )

    def test_la_coda_delloutput_finisce_nel_rapporto(self, monkeypatch, tmp_path):
        self._mondo_rosso(monkeypatch)
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)
        assert esito.stato == "rosso"

        rapporto = json.loads(runner.chiudi_rapporto("giro", [esito]).read_text(encoding="utf-8"))
        scritto = json.dumps(rapporto, ensure_ascii=False)
        assert "pytest" in scritto, "il nome del gate c'era già"
        assert "test_riga_12 FAILED" in scritto, (
            "senza la coda dell'output il rapporto dice che è rosso e non dice perché"
        )

    def test_la_coda_delloutput_finisce_anche_nel_log(self, monkeypatch, capsys):
        self._mondo_rosso(monkeypatch)

        runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert "test_riga_12 FAILED" in capsys.readouterr().out, (
            "il log del giro è ciò che si apre per primo: la ragione va anche lì"
        )


class TestUnComandoCheNonCeFaRossoNonUnTraceback:
    """Difetto 11 di PBI-102.

    `subprocess.run` alza `FileNotFoundError` quando il comando non esiste, e
    l'eccezione saliva fino a `main()`: il processo moriva col traceback, senza
    riga nel registro e senza rapporto. Un `pytest` che manca sulla macchina è
    un gate rosso con una diagnosi ovvia — non la fine della sequenza.

    Il controllo di `gate_mancanti` copre il caso normale, ma copre solo i gate
    e solo **prima** del primo PBI: qui si tiene il fondo del secchio.
    """

    def test_il_comando_inesistente_torna_127_invece_di_alzare(self, monkeypatch):
        def _run(*a, **k):
            raise FileNotFoundError(2, "No such file or directory", "pytest")

        monkeypatch.setattr(runner.subprocess, "run", _run)

        code, out = runner.esegui(["pytest", "-q"], runner.REPO)

        assert code == 127, "127 è «comando non trovato», la convenzione della shell"
        assert "pytest" in out

    def test_un_gate_senza_comando_e_un_gate_rosso(self, monkeypatch):
        monkeypatch.setattr(
            runner, "esegui",
            lambda cmd, cwd, timeout=0: (127, f"comando non eseguibile: {cmd[0]}"),
        )

        rossi = runner.gira_gate(attivi=set())

        assert rossi, "un gate che non gira non è un gate verde"
        assert all("non eseguibile" in coda for _, coda in rossi)


class TestDueRunnerNonGiranoNelloStessoAlbero:
    """Il worktree è uno solo, e finora non aveva un lucchetto.

    La notte del 24→25/08 il builder del runner e un agente avviato a mano sono
    finiti sullo stesso `ada-run` sullo stesso branch, e il secondo ha committato
    due modifiche non committate del primo. È andata bene per caso: due processi
    che scrivono lo stesso albero si sovrascrivono i file a vicenda e i commit
    escono mescolati. Difetto n°9 di PBI-102.
    """

    def test_il_secondo_lucchetto_non_si_prende(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "LUCCHETTO", tmp_path / ".runner.lock")
        with runner.lucchetto():
            with pytest.raises(runner.AlberoOccupato):
                with runner.lucchetto():
                    pass

    def test_rilasciato_torna_libero(self, tmp_path, monkeypatch):
        """Il lucchetto è del **processo**, non del file: se il runner muore di
        schianto non resta un lucchetto morto da togliere a mano."""
        monkeypatch.setattr(runner, "LUCCHETTO", tmp_path / ".runner.lock")
        with runner.lucchetto():
            pass
        with runner.lucchetto():
            pass


class TestUnAgenteNelWorktreeFermaIlLancio:
    """Il lucchetto tiene fuori un secondo runner, non un agente avviato a mano —
    ed è **quello** che è successo. Prima di partire si guarda chi altro sta
    lavorando in questo albero."""

    def _finto(self, proc, pid, cwd, cmdline):
        d = proc / str(pid)
        d.mkdir(parents=True)
        (d / "cwd").symlink_to(cwd)
        (d / "cmdline").write_bytes(cmdline)

    def test_trova_il_claude_che_gira_nello_stesso_albero(self, tmp_path):
        proc, albero = tmp_path / "proc", tmp_path / "albero"
        albero.mkdir()
        self._finto(proc, 797078, albero, b"claude\x00-p\x00")
        assert runner.agenti_estranei(albero, proc=proc) == [(797078, "claude -p")]

    def test_trova_anche_un_sottoalbero(self, tmp_path):
        proc, albero = tmp_path / "proc", tmp_path / "albero"
        (albero / "frontend").mkdir(parents=True)
        self._finto(proc, 42, albero / "frontend", b"claude\x00")
        assert [p for p, _ in runner.agenti_estranei(albero, proc=proc)] == [42]

    def test_ignora_chi_lavora_altrove(self, tmp_path):
        proc, albero = tmp_path / "proc", tmp_path / "albero"
        albero.mkdir()
        (tmp_path / "altrove").mkdir()
        self._finto(proc, 42, tmp_path / "altrove", b"claude\x00")
        assert runner.agenti_estranei(albero, proc=proc) == []

    def test_ignora_se_stesso(self, tmp_path):
        """Il runner è un processo dell'albero come gli altri: senza questa
        esclusione non partirebbe mai."""
        import os

        proc, albero = tmp_path / "proc", tmp_path / "albero"
        albero.mkdir()
        self._finto(proc, os.getpid(), albero, b"python3\x00tools/asdlc_runner.py\x00")
        assert runner.agenti_estranei(albero, proc=proc) == []

    def test_ignora_chi_non_e_un_agente(self, tmp_path):
        """Un `tail -f` sul log non è un agente che scrive: fermare il lancio per
        lui sarebbe un falso positivo, e un controllo che grida sempre si spegne."""
        proc, albero = tmp_path / "proc", tmp_path / "albero"
        albero.mkdir()
        self._finto(proc, 42, albero, b"tail\x00-f\x00runs/tempi.csv\x00")
        assert runner.agenti_estranei(albero, proc=proc) == []


class TestIlLancioSiFermaPrimaDiScrivere:
    """I due controlli servono se stanno **prima** del primo PBI: dopo, l'albero
    è già stato scritto da due mani."""

    @pytest.fixture(autouse=True)
    def albero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "LUCCHETTO", tmp_path / ".runner.lock")
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        monkeypatch.setattr(
            runner, "esegui_pbi",
            lambda *a, **k: pytest.fail("nessun PBI deve partire con l'albero occupato"),
        )

    def test_un_agente_estraneo_ferma_tutto(self, monkeypatch, capsys):
        monkeypatch.setattr(runner, "agenti_estranei", lambda *a, **k: [(797078, "claude -p")])
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "PBI-212", "--in-primo-piano"])
        assert runner.main() == 2
        assert "797078" in capsys.readouterr().out

    def test_un_altro_runner_ferma_tutto(self, monkeypatch, capsys):
        monkeypatch.setattr(runner, "agenti_estranei", lambda *a, **k: [])
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "PBI-212", "--in-primo-piano"])
        with runner.lucchetto():
            assert runner.main() == 2
        assert "lucchetto" in capsys.readouterr().out.lower()


class TestSiPuoSaltareIlCritic:
    """Il Review Gate si può togliere, ma non di nascosto.

    Deciso da Francesco il 25/08/2026: su una modifica locale e puntuale, che lui
    guarda dal frontend prima di mergiare, il Critic costa più di quanto rende —
    dal registro dei tempi è il **39%** del giro (PBI-210: builder 52:53 · gate
    5:18 · critic 36:26). Il Quality Gate resta: è deterministico, costa 5 minuti
    su 90, e non è un giudizio.

    La condizione è che il registro non menta. `critic_s = 0` da solo non basta —
    è la lezione di `gate_s = 0` su PBI-208, dove uno zero è stato letto come «un
    gate rosso» invece che «i gate non sono mai girati».
    """

    @pytest.fixture
    def builder_verde(self, monkeypatch):
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(
            runner, "revisione_critica",
            lambda *a, **k: pytest.fail("il Critic non deve girare con --senza-critic"),
        )

    def test_il_flag_esiste_e_di_default_e_spento(self):
        ap = runner.costruisci_parser()
        assert ap.parse_args(["PBI-212"]).senza_critic is False
        assert ap.parse_args(["PBI-212", "--senza-critic"]).senza_critic is True

    def test_col_flag_il_critic_non_viene_chiamato(self, git_finto, builder_verde):
        esito = runner.esegui_pbi(
            "PBI-102", attivi=set(), dry=False, con_pr=False, con_critic=False
        )
        assert esito.stato == "fatto"

    def test_la_riga_del_registro_dice_che_e_saltato(self, git_finto, builder_verde):
        """Un giro senza Critic non deve somigliare a un giro con il Critic."""
        esito = runner.esegui_pbi(
            "PBI-102", attivi=set(), dry=False, con_pr=False, con_critic=False
        )
        assert "critic" in esito.nota.lower()
        assert esito.tempi["critic"] == 0

    def test_senza_il_flag_il_critic_gira_come_sempre(self, monkeypatch, git_finto):
        """Il default non si sposta: chi non chiede niente ha i tre gate."""
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        giri = {"critic": 0}

        def critic(_p):
            giri["critic"] += 1
            return runner.Verdetto("pass", "", "rapporto")

        monkeypatch.setattr(runner, "revisione_critica", critic)
        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)
        assert giri["critic"] == 1
        assert "critic" not in esito.nota.lower()

    def test_la_pr_non_dichiara_un_pass_che_non_ce_stato(self, monkeypatch, git_finto):
        """La riga peggiore da lasciare com'è.

        Il corpo della PR scrive *«revisione avversariale PASS»* fisso. Su un giro
        `--senza-critic` sarebbe una frase falsa nel documento su cui si decide il
        merge — e la lezione del 25/08 su PBI-212 è esattamente questa: chi
        rilegge deve sapere quali gate non ci sono stati **prima** di guardare il
        diff, non dopo.
        """
        catturato: dict[str, list[str]] = {}

        def finto_esegui(cmd, cwd, timeout=7200):
            catturato["cmd"] = cmd
            return 0, "https://github.com/Lara-srl/ada_controller/pull/1"

        monkeypatch.setattr(runner, "esegui", finto_esegui)
        pbi_path = REPO / "backlog" / "PBI-102-soglia-di-revisione-del-runner.md"
        esito = runner.Esito("PBI-102", "fatto", critic_saltato=True)

        runner.apri_pr("PBI-102", pbi_path, "pbi/pbi-102", esito)

        cmd = catturato["cmd"]
        corpo = cmd[cmd.index("--body") + 1]
        assert "PASS" not in corpo, "non si dichiara un verdetto che nessuno ha emesso"
        assert "--senza-critic" in corpo


class TestIlRunnerSiStaccaDaSolo:
    """Difetto 15 di PBI-102: chiudere il terminale non deve uccidere il giro.

    Misurato il 26/08 su PBI-322: la catena era `python3 → bash → claude` con il
    `SID` della shell chiamante, e otto commit buoni sono stati salvati a mano
    prima di chiudere. Finché il distacco lo fa chi lancia — `setsid nohup … <
    /dev/null &` — lo stesso runner si comporta in due modi a seconda di come lo
    si chiama, che è la forma dei difetti 11 e 12. Se ne occupa lui; chi vuole
    guardarlo lavorare lo dice, con `--in-primo-piano`.
    """

    def test_il_flag_esiste_e_di_default_e_spento(self):
        ap = runner.costruisci_parser()
        assert ap.parse_args(["PBI-212"]).in_primo_piano is False
        assert ap.parse_args(["PBI-212", "--in-primo-piano"]).in_primo_piano is True

    def test_di_default_si_stacca(self):
        assert runner.va_staccato(in_primo_piano=False, pid=4242, sid=4200) is True

    def test_col_flag_resta_dove_e(self):
        """Il debug e la CI vogliono l'output sotto gli occhi, e un exit code."""
        assert runner.va_staccato(in_primo_piano=True, pid=4242, sid=4200) is False

    def test_chi_e_gia_leader_di_sessione_non_si_stacca_due_volte(self):
        """Lanciato da `setsid` o da un rilancio, il processo è già dove deve stare."""
        assert runner.va_staccato(in_primo_piano=False, pid=4242, sid=4242) is False

    def test_si_stacca_prima_di_prendere_il_lucchetto(self, tmp_path, monkeypatch):
        """L'ordine non è estetico: il `flock` è dell'open file description, e il
        padre che muore dopo averlo preso se lo porterebbe via."""
        ordine: list[str] = []

        @contextmanager
        def finto_lucchetto():
            ordine.append("lucchetto")
            yield

        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        monkeypatch.setattr(runner, "lucchetto", finto_lucchetto)
        monkeypatch.setattr(runner, "agenti_estranei", lambda *a, **k: [])
        monkeypatch.setattr(runner, "stacca", lambda run: ordine.append("stacca"))
        monkeypatch.setattr(runner, "va_staccato", lambda *a, **k: True)
        monkeypatch.setattr(
            runner, "esegui_pbi", lambda *a, **k: runner.Esito("PBI-212", "saltato")
        )
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "PBI-212"])

        runner.main()

        assert ordine[:2] == ["stacca", "lucchetto"]

    def test_col_flag_non_si_stacca_affatto(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        monkeypatch.setattr(runner, "agenti_estranei", lambda *a, **k: [])
        monkeypatch.setattr(runner, "gate_mancanti", lambda attivi: [])
        monkeypatch.setattr(
            runner, "stacca", lambda run: pytest.fail("--in-primo-piano non deve forkare")
        )
        monkeypatch.setattr(
            runner, "esegui_pbi", lambda *a, **k: runner.Esito("PBI-212", "saltato")
        )
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "PBI-212", "--in-primo-piano"])

        assert runner.main() == 0

    def test_il_log_del_giro_sta_accanto_al_suo_rapporto(self, tmp_path, monkeypatch):
        """Log e rapporto JSON portano lo stesso nome: sono lo stesso giro visto da
        due parti, e cercarne uno partendo dall'altro non deve costare niente."""
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        assert runner.log_del_giro("20260828-224500") == tmp_path / "20260828-224500.log"


class TestIlBranchLoPubblicaIlRunner:
    """Difetti 8, 16 e 18 di PBI-102: chi pubblica il branch, quando, e con che nome.

    Le tre storie sono la stessa storia. **PBI-322**, il 26/08: un giro fallito
    lascia `pbi/pbi-322` su `origin`, il rilancio ci ripassa sopra e muore prima
    di cominciare. **PBI-324**, il 27/08: il Builder pusha e apre la PR dentro il
    giro 1, il Critic chiede altri quattro giri, il branch si riscrive, e il push
    finale si prende un `non-fast-forward` che uccide il processo — in `main` è
    entrato un terzo del lavoro con la sua checklist spuntata. **PBI-203 e
    PBI-320**: un giro che chiude `fermato` o `rosso` lascia i commit solo in
    locale, dove nessuno li guarda.
    """

    def test_senza_collisione_il_nome_resta_quello_semplice(self):
        assert runner.nome_libero("PBI-322", presi=set()) == "pbi/pbi-322"

    def test_un_nome_gia_su_origin_fa_nascere_il_giro_due(self):
        assert runner.nome_libero("PBI-322", presi={"pbi/pbi-322"}) == "pbi/pbi-322-giro2"

    def test_e_si_continua_a_contare(self):
        presi = {"pbi/pbi-322", "pbi/pbi-322-giro2"}
        assert runner.nome_libero("PBI-322", presi=presi) == "pbi/pbi-322-giro3"

    def test_crea_branch_chiede_a_origin_prima_di_scegliere(self, monkeypatch):
        """Il nome non si decide guardando il locale: il locale è appena stato clonato."""
        chiamate: list[tuple[str, ...]] = []

        def _git(*args: str) -> str:
            chiamate.append(args)
            if args[0] == "ls-remote":
                return "aef71f4\trefs/heads/pbi/pbi-322\n"
            return ""

        monkeypatch.setattr(runner, "git", _git)
        assert runner.crea_branch("PBI-322") == "pbi/pbi-322-giro2"
        assert ("switch", "-c", "pbi/pbi-322-giro2", "origin/main") in chiamate

    def test_il_push_del_proprio_branch_e_force_with_lease(self, git_finto):
        """Fra un giro e l'altro il branch si riscrive — ed è lecito. Un push
        semplice si prende il non-fast-forward che ha ucciso PBI-324."""
        assert runner.pubblica("pbi/pbi-322") is True
        assert ("push", "--force-with-lease", "-u", "origin", "pbi/pbi-322") in git_finto

    def test_un_push_fallito_non_uccide_il_giro(self, monkeypatch, capsys):
        """L'ultima riga del difetto 16: `git()` alza, nessuno la cattura, e un'ora
        di lavoro se ne va con il traceback."""
        def _git(*args: str) -> str:
            raise RuntimeError("git push → ! [rejected] (stale info)")

        monkeypatch.setattr(runner, "git", _git)
        assert runner.pubblica("pbi/pbi-322") is False
        assert "non pubblicato" in capsys.readouterr().out

    def test_un_giro_sospeso_pubblica_lo_stesso_il_suo_branch(self, monkeypatch, git_finto):
        """Il lavoro c'è: sta su un ramo che nessuno vedrà mai, se resta locale."""
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(
            runner, "revisione_critica",
            lambda p: runner.Verdetto("sospeso", "chi decide?", "rapporto"),
        )

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "sospeso"
        assert any(c[0] == "push" for c in git_finto), "un giro fermo va comunque su origin"

    def test_un_giro_fatto_non_pubblica_due_volte(self, monkeypatch, git_finto):
        """Sulla strada buona a pubblicare è `apri_pr`, e una volta sola."""
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(
            runner, "revisione_critica", lambda p: runner.Verdetto("pass", "", "rapporto")
        )

        runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert [c for c in git_finto if c[0] == "push"] == []

    def test_il_builder_ha_il_divieto_scritto_nel_prompt(self):
        """La prima causa del difetto 18: a pushare era il Builder, dentro il giro.

        Un branch pubblicato a metà è una promessa fatta su lavoro che il Critic
        non ha ancora accettato — e su PBI-324 quella promessa è stata riscossa
        con un merge."""
        prompt = runner.PROMPT_BUILDER.lower()
        assert "git push" in prompt and "pr create" in prompt


class TestUnGiroLasciaTracciaAppenaComincia:
    """Difetto 20 di PBI-102: un giro che muore a metà non deve sparire.

    `scrivi_tempi` gira in fondo a `main()`. Fino a lì, del giro in corso non
    esiste niente: né una riga nel CSV né un rapporto. PBI-329, il 28/08, ha
    prodotto diciassette commit fra le 17:49 e le 18:33 con la Verifica spuntata
    cinque su cinque, e nel registro non c'è — trovato solo cercando i rami
    locali. Il rapporto per-run si apre subito, e siccome è gitignored non
    peggiora il difetto 19 come farebbe una riga aperta nel CSV condiviso.
    """

    def test_il_rapporto_esiste_prima_del_primo_pbi(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        rapporto = runner.apri_rapporto("20260828-224137", ["PBI-329", "PBI-330"])

        assert rapporto.exists()
        dentro = json.loads(rapporto.read_text())
        assert dentro["stato"] == "in-corso"
        assert dentro["pbi"] == ["PBI-329", "PBI-330"]
        assert dentro["iniziato"]
        assert "finito" not in dentro, "un giro in corso non ha una fine"

    def test_main_lo_apre_prima_di_eseguire(self, tmp_path, monkeypatch):
        """L'ordine è il difetto: aprirlo dopo il primo PBI lascia scoperto
        proprio il caso che è successo."""
        visto: dict[str, bool] = {}

        def esegui_pbi_finto(pbi, *a, **k):
            visto["rapporto"] = any(tmp_path.glob("*.json"))
            return runner.Esito(pbi, "saltato")

        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        monkeypatch.setattr(runner, "agenti_estranei", lambda *a, **k: [])
        monkeypatch.setattr(runner, "gate_mancanti", lambda attivi: [])
        monkeypatch.setattr(runner, "esegui_pbi", esegui_pbi_finto)
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "PBI-212", "--in-primo-piano"])

        runner.main()

        assert visto["rapporto"], "il rapporto del giro va aperto prima del primo PBI"

    def test_alla_fine_il_rapporto_e_quello_di_sempre(self, tmp_path, monkeypatch):
        """L'apertura non deve cambiare cosa si legge a giro finito."""
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        monkeypatch.setattr(runner, "agenti_estranei", lambda *a, **k: [])
        monkeypatch.setattr(runner, "gate_mancanti", lambda attivi: [])
        monkeypatch.setattr(
            runner, "esegui_pbi", lambda pbi, *a, **k: runner.Esito(pbi, "fatto", commit=3)
        )
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "PBI-212", "--in-primo-piano"])

        runner.main()

        rapporto = json.loads(next(tmp_path.glob("*.json")).read_text())
        assert [e["pbi"] for e in rapporto["esiti"]] == ["PBI-212"]
        assert rapporto["stato"] == "finito"


class TestUnPbiFinitoELoResta:
    """Difetto 17 di PBI-102, che ha due metà.

    **La prima**: un'eccezione dentro un PBI usciva da `main()` col traceback e
    portava via la sequenza intera — e con lei i rilievi del Critic dei PBI già
    chiusi, che stavano ancora in memoria. Un guasto su un PBI è un esito di
    *quel* PBI; se la catena prosegua lo decide la regola che esiste già,
    `STATI_CHE_INTERROMPONO`, non il fatto che sia caduta un'eccezione.

    **La seconda**: il rapporto si scriveva solo in fondo a `main()`. Un
    `kill` a metà della seconda ora cancellava la prima: il giro era esistito e
    non lo diceva nessuno.
    """

    def _mondo(self, monkeypatch, tmp_path, esegui_pbi_finto, argv):
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        monkeypatch.setattr(runner, "agenti_estranei", lambda *a, **k: [])
        monkeypatch.setattr(runner, "gate_mancanti", lambda attivi: [])
        monkeypatch.setattr(runner, "esegui_pbi", esegui_pbi_finto)
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", *argv, "--in-primo-piano"])

    def test_uneccezione_chiude_quel_pbi_e_non_la_sequenza(self, tmp_path, monkeypatch):
        def esegui_pbi_finto(pbi, *a, **k):
            if pbi == "PBI-212":
                raise RuntimeError("git switch → already used by worktree")
            return runner.Esito(pbi, "fatto", commit=3)

        self._mondo(monkeypatch, tmp_path, esegui_pbi_finto,
                    ["PBI-212", "PBI-214", "--continua-sui-rossi"])

        runner.main()

        rapporto = json.loads(next(tmp_path.glob("*.json")).read_text())
        esiti = {e["pbi"]: e for e in rapporto["esiti"]}
        assert set(esiti) == {"PBI-212", "PBI-214"}, (
            "il traceback si portava via anche i PBI che erano andati bene"
        )
        assert esiti["PBI-212"]["stato"] == "rosso"
        assert "already used by worktree" in esiti["PBI-212"]["nota"], (
            "la diagnosi del guasto è la cosa che serve, e stava solo nel traceback"
        )

    def test_uneccezione_ferma_comunque_la_catena_se_nessuno_ha_detto_il_contrario(
        self, tmp_path, monkeypatch
    ):
        partiti: list[str] = []

        def esegui_pbi_finto(pbi, *a, **k):
            partiti.append(pbi)
            raise RuntimeError("il mondo è rotto")

        self._mondo(monkeypatch, tmp_path, esegui_pbi_finto, ["PBI-212", "PBI-214"])

        runner.main()

        assert partiti == ["PBI-212"], (
            "`rosso` interrompe: costruire sul PBI dopo una base rotta costa di più"
        )

    def test_il_rapporto_di_un_pbi_ce_appena_quel_pbi_e_finito(self, tmp_path, monkeypatch):
        visto: dict[str, list] = {}

        def esegui_pbi_finto(pbi, *a, **k):
            if pbi == "PBI-214":
                rapporto = json.loads(next(tmp_path.glob("*.json")).read_text())
                visto["esiti"] = [e["pbi"] for e in rapporto.get("esiti", [])]
            return runner.Esito(pbi, "fatto", commit=3)

        self._mondo(monkeypatch, tmp_path, esegui_pbi_finto, ["PBI-212", "PBI-214"])

        runner.main()

        assert visto["esiti"] == ["PBI-212"], (
            "l'esito del primo PBI deve essere già su disco mentre parte il secondo: "
            "un kill a metà della seconda ora non cancella la prima"
        )


class TestIlRegistroEsceDaiBranch:
    """Difetti 12 e 19 di PBI-102, chiusi insieme da `ADR-0020`.

    `runs/tempi.csv` è versionato e append-only, e il runner lo scriveva in fondo
    a `main()` — cioè **dentro il worktree del PBI**, sul branch. Ogni branch nato
    prima che la riga di un altro giro entrasse in `main` scriveva la stessa
    ultima riga, e la PR si presentava `CONFLICTING` su un file che il PBI non ha
    mai toccato: due volte il 27/08 (PBI-326, poi PBI-306). Committarlo più
    spesso — il difetto 12 — alzava la frequenza del conflitto invece di toglierlo.

    Francesco, 29/08: *«il CSV esce dai branch e si scrive su main dopo il
    merge»*. Il giro scrive solo il suo rapporto, che è gitignored e per-run;
    `--registra` piega i rapporti nel CSV, su `main`, quando il lavoro è già
    entrato.
    """

    def _rapporto(self, cartella: Path, run: str, esiti: list[dict]) -> None:
        (cartella / f"{run}.json").write_text(
            json.dumps({"run": run, "stato": "finito", "esiti": esiti}, ensure_ascii=False),
            encoding="utf-8",
        )

    def _esito(self, pbi: str, iniziato: str, stato: str = "fatto") -> dict:
        return {"pbi": pbi, "stato": stato, "iniziato": iniziato, "finito": iniziato,
                "durata_s": 600.0, "tentativi": 1, "revisioni": 0, "commit": 4,
                "pr": "", "nota": "", "tempi": {"builder": 500.0, "gate": 60.0, "critic": 40.0}}

    def test_il_giro_non_scrive_il_registro_nel_branch(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        monkeypatch.setattr(runner, "agenti_estranei", lambda *a, **k: [])
        monkeypatch.setattr(runner, "gate_mancanti", lambda attivi: [])
        monkeypatch.setattr(
            runner, "esegui_pbi", lambda pbi, *a, **k: runner.Esito(pbi, "fatto", commit=3)
        )
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "PBI-212", "--in-primo-piano"])

        runner.main()

        assert not (tmp_path / "tempi.csv").exists(), (
            "il registro scritto sul branch è il conflitto del difetto 19"
        )
        assert next(tmp_path.glob("*.json")), "il giro deve restare scritto da qualche parte"

    def test_registra_piega_i_rapporti_nel_csv_in_ordine_di_tempo(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        self._rapporto(tmp_path, "20260829-020000", [self._esito("PBI-330", "2026-08-29T02:00:00")])
        self._rapporto(tmp_path, "20260828-230000", [self._esito("PBI-329", "2026-08-28T23:00:00")])

        assert runner.registra(tmp_path) == 0

        righe = list(csv.DictReader((tmp_path / "tempi.csv").open(encoding="utf-8")))
        assert [r["pbi"] for r in righe] == ["PBI-329", "PBI-330"], (
            "una riga persa o fuori ordine è un giro che non è mai esistito"
        )
        assert righe[0]["builder_s"] == "500.0" and righe[0]["commit"] == "4"

    def test_un_rapporto_vecchio_e_una_lista_nuda_di_esiti(self, tmp_path, monkeypatch):
        """I rapporti scritti prima di `apri_rapporto()` sono una **lista** di esiti,
        senza `run` e senza `stato`: `runs/20260828-224137.json` è così, ed è
        l'unico rimasto sulla macchina quando `--registra` è stato eseguito la
        prima volta. Leggerli è tutto il punto del comando — sono i giri già
        fatti — e un `AttributeError` su un file vecchio è un registro che non si
        può più ricostruire. Il `run` lo dà il nome del file, che è il timestamp
        con cui il giro è nato.
        """
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        (tmp_path / "20260828-224137.json").write_text(
            json.dumps([self._esito("PBI-328", "2026-08-28T22:41:37")]), encoding="utf-8"
        )

        assert runner.registra(tmp_path) == 0

        righe = list(csv.DictReader((tmp_path / "tempi.csv").open(encoding="utf-8")))
        assert [(r["run"], r["pbi"]) for r in righe] == [("20260828-224137", "PBI-328")]

    def test_un_rapporto_di_forma_ignota_si_salta_dicendolo(self, tmp_path, monkeypatch, capsys):
        """Un file storto non porta via gli altri: è la stessa regola del lettore
        del consuntivo — *«un lettore che esplode su una riga vecchia spegne la
        pagina intera per una pratica su seicento»*."""
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        (tmp_path / "storto.json").write_text('"un giro"', encoding="utf-8")
        (tmp_path / "20260829-020000.json").write_text(
            json.dumps({"run": "20260829-020000",
                        "esiti": [self._esito("PBI-330", "2026-08-29T02:00:00")]}),
            encoding="utf-8",
        )

        assert runner.registra(tmp_path) == 0

        righe = list(csv.DictReader((tmp_path / "tempi.csv").open(encoding="utf-8")))
        assert [r["pbi"] for r in righe] == ["PBI-330"]
        assert "storto.json" in capsys.readouterr().out, "un file saltato in silenzio è una riga persa"

    def test_registrare_due_volte_non_duplica(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        self._rapporto(tmp_path, "20260829-020000", [self._esito("PBI-330", "2026-08-29T02:00:00")])

        runner.registra(tmp_path)
        runner.registra(tmp_path)

        righe = list(csv.DictReader((tmp_path / "tempi.csv").open(encoding="utf-8")))
        assert len(righe) == 1, "la chiave è (run, pbi): rilanciarlo deve essere innocuo"

    def test_un_saltato_non_prende_riga(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        self._rapporto(tmp_path, "20260829-030000",
                       [self._esito("PBI-000", "2026-08-29T03:00:00", stato="saltato")])

        runner.registra(tmp_path)

        assert not (tmp_path / "tempi.csv").exists(), (
            "una riga a zero sporcherebbe la media: niente tempo, niente riga"
        )


class TestIlGateE2ENonEDelRunner:
    """Difetto 13 di PBI-102.

    `--e2e` faceva girare `npm run e2e` **senza `E2E_BASE_URL`**: Playwright
    puntava a `localhost:8081`, che è lo stack del checkout principale, cioè
    `main`. Il gate cadeva su «element(s) not found» per roba che sul branch
    c'era — un rosso che parla di un altro checkout. Costato 33 minuti su PBI-320
    il 26/08, tre tentativi bruciati e **il Critic mai chiamato**, perché il
    Review Gate viene dopo i gate deterministici.

    Non si aggiusta passando un `E2E_BASE_URL`: lo stack andrebbe **ricostruito
    a ogni giro del Builder**, e il runner non lo fa. Chi lo fa è la CI sulla PR,
    che lo stack lo costruisce dal branch (`ADR-0009`, `ci.yml`). Quindi il gate
    e2e non è del runner, e il flag non resta a mezz'aria.
    """

    def test_nessun_gate_del_runner_e_l_e2e(self):
        assert [g.nome for g in runner.GATE if g.nome == "e2e"] == [], (
            "un gate che prova un altro checkout non è un gate: è un rosso finto"
        )

    def test_chiedere_l_e2e_ferma_il_lancio_e_dice_dove_gira(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        monkeypatch.setattr(runner, "agenti_estranei", lambda *a, **k: [])
        monkeypatch.setattr(runner, "gate_mancanti", lambda attivi: [])
        monkeypatch.setattr(
            runner, "esegui_pbi",
            lambda *a, **k: pytest.fail("con --e2e non deve partire niente"),
        )
        monkeypatch.setattr(
            sys, "argv", ["asdlc_runner", "PBI-212", "--e2e", "--in-primo-piano"]
        )

        assert runner.main() == 2
        uscita = capsys.readouterr().out
        assert "CI" in uscita or "ci.yml" in uscita, (
            "chi ha battuto --e2e vuole gli E2E: va detto dove girano davvero"
        )


class TestIlVenvSeLoTrovaDaSolo:
    """L'ultimo pezzo di `ada-notte.sh` che il runner non faceva: il `PATH`.

    `backend/requirements.txt` è il file del runtime e `pytest` non c'è, quindi i
    gate girano col venv del worktree — che finora andava messo sul `PATH` a mano
    prima di ogni lancio. Dimenticarlo non costa più il giro (difetto 21 lo dice
    in tre secondi), ma resta una cosa da ricordarsi, e il criterio che chiude
    PBI-102 è **non doversi ricordare niente**.
    """

    def test_il_venv_del_worktree_entra_nel_path(self, tmp_path, monkeypatch):
        (tmp_path / "backend" / ".venv" / "bin").mkdir(parents=True)
        monkeypatch.setattr(runner, "REPO", tmp_path)
        monkeypatch.setenv("PATH", "/usr/bin")

        aggiunto = runner.venv_sul_path()

        import os
        assert aggiunto == str(tmp_path / "backend" / ".venv" / "bin")
        assert os.environ["PATH"].startswith(aggiunto), (
            "il venv del worktree deve venire prima del python di sistema"
        )

    def test_senza_venv_il_path_resta_quello_che_era(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "REPO", tmp_path)
        monkeypatch.setenv("PATH", "/usr/bin")

        assert runner.venv_sul_path() is None

        import os
        assert os.environ["PATH"] == "/usr/bin"

    def test_non_lo_aggiunge_due_volte(self, tmp_path, monkeypatch):
        bin_venv = tmp_path / "backend" / ".venv" / "bin"
        bin_venv.mkdir(parents=True)
        monkeypatch.setattr(runner, "REPO", tmp_path)
        monkeypatch.setenv("PATH", f"{bin_venv}:/usr/bin")

        assert runner.venv_sul_path() is None

        import os
        assert os.environ["PATH"] == f"{bin_venv}:/usr/bin"


class TestLUrlDellaPrSiRiconoscePerForma:
    """L'altra metà del difetto 12 di PBI-102.

    `gh pr create` scrive l'URL sull'ultima riga **quando va tutto liscio**. Un
    avviso di aggiornamento, una nota sul remoto, una riga di `gh` che parla di
    sé: bastano a far finire nella colonna `pr` del registro una frase che non è
    un indirizzo. La colonna serve a una cosa sola — aprire la PR — e un warning
    lì dentro la rende inutile senza dirlo.
    """

    def _crea_pr(self, monkeypatch, uscita: str) -> str:
        monkeypatch.setattr(runner, "pubblica", lambda branch: True)
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, uscita))
        return runner.apri_pr(
            "PBI-212", runner.REPO / "backlog" / "PBI-212-margine-costo-e-ricavo.md",
            "pbi/pbi-212", runner.Esito("PBI-212", "fatto"),
        )

    def test_lurl_si_trova_anche_sotto_un_warning(self, monkeypatch):
        uscita = ("https://github.com/Lara-srl/ada_controller/pull/212\n"
                  "A new release of gh is available: 2.55.0 → 2.62.0\n")
        assert self._crea_pr(monkeypatch, uscita) == (
            "https://github.com/Lara-srl/ada_controller/pull/212"
        )

    def test_senza_url_la_colonna_resta_vuota(self, monkeypatch):
        """Meglio vuota che con dentro una frase: una colonna che mente costa più
        di una che tace."""
        assert self._crea_pr(monkeypatch, "A new release of gh is available\n") == ""


class TestIGateSiDichiaranoPrimaDiPartire:
    """Difetto 21 di PBI-102: un gate che non può girare si dice in tre secondi.

    `backend/requirements.txt` è il file del runtime: `pytest` non c'è, e il venv
    di `~/ada-run` ce l'ha solo perché qualcuno gliel'ha installato a mano. Il
    28/08, allestendo `~/ada-run-310` per far girare due PBI in parallelo, il
    primo gate sarebbe morto su `pytest: command not found` **dopo** mezz'ora di
    Builder. Il controllo sta dove stanno già il lucchetto e il censimento degli
    agenti: prima del primo PBI.
    """

    def test_dice_quali_comandi_mancano(self, monkeypatch):
        monkeypatch.setattr(runner.shutil, "which", lambda c: None if c == "pytest" else "/usr/bin/npm")
        assert runner.gate_mancanti(attivi=set()) == ["pytest"]

    def test_con_tutto_a_posto_non_dice_niente(self, monkeypatch):
        monkeypatch.setattr(runner.shutil, "which", lambda c: f"/usr/bin/{c}")
        assert runner.gate_mancanti(attivi=set()) == []

    def test_guarda_solo_i_gate_accesi(self, monkeypatch):
        """`--e2e` spento non deve pretendere lo stack Playwright."""
        monkeypatch.setattr(runner.shutil, "which", lambda c: f"/usr/bin/{c}")
        assert "e2e" not in runner.gate_mancanti(attivi=set())

    def test_il_lancio_si_ferma_e_li_nomina_tutti(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        monkeypatch.setattr(runner, "agenti_estranei", lambda *a, **k: [])
        monkeypatch.setattr(runner, "gate_mancanti", lambda attivi: ["pytest"])
        monkeypatch.setattr(
            runner, "esegui_pbi",
            lambda *a, **k: pytest.fail("nessun PBI parte senza i suoi gate"),
        )
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "PBI-212", "--in-primo-piano"])

        assert runner.main() == 2
        assert "pytest" in capsys.readouterr().out

    def test_un_dry_run_non_pretende_i_gate(self, tmp_path, monkeypatch):
        """`--dry-run` stampa il prompt e non esegue niente: pretendere i gate lì
        vorrebbe dire non poter leggere un prompt su una macchina qualsiasi."""
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        monkeypatch.setattr(runner, "CSV_TEMPI", tmp_path / "tempi.csv")
        monkeypatch.setattr(runner, "agenti_estranei", lambda *a, **k: [])
        monkeypatch.setattr(runner, "gate_mancanti", lambda attivi: ["pytest"])
        monkeypatch.setattr(
            runner, "esegui_pbi", lambda pbi, *a, **k: runner.Esito(pbi, "saltato")
        )
        monkeypatch.setattr(
            sys, "argv", ["asdlc_runner", "PBI-212", "--dry-run", "--in-primo-piano"]
        )

        assert runner.main() == 0

    def test_le_dipendenze_di_test_sono_dichiarate(self):
        """La conoscenza che stava nella testa di chi allestì il primo venv."""
        dev = REPO / "backend" / "requirements-dev.txt"
        assert dev.exists(), "un albero nuovo deve poter installare i gate leggendo un file"
        assert "pytest" in dev.read_text()


# --- Il gate del rosso (PBI-103) --------------------------------------------
#
# Il Quality Gate risponde a una domanda sola — *i test passano?* — e ne manca una
# seconda che è meccanica: **quei test sono mai stati rossi?** Un test nato verde
# non prova niente, e due volte su due in tre giorni (PBI-328, PBI-330) il divieto
# scritto in AGENTS.md non ha fermato niente, perché una frase in un prompt non è
# un vincolo. Qui sotto i pezzi di quel gate, dal più piccolo in su.


class TestChiEUnTestEChiEProduzione:
    """Il primo taglio lo fa il **diff**, senza eseguire niente.

    Un commit che porta test nuovi e file di produzione insieme non può aver avuto
    un rosso in mezzo: il codice che li fa passare è arrivato nello stesso gesto. È
    il caso di `aa40167` (PBI-328), 1337 righe di pagina e 445 di test insieme.
    """

    @pytest.mark.parametrize("percorso", [
        "backend/tests/test_importa_storico.py",
        "backend/tests/conftest.py",
        "frontend/src/pages/PratichePage.test.tsx",
        "e2e/tests/fase2-marginalita.spec.ts",
    ])
    def test_questi_sono_test(self, percorso):
        assert runner.e_file_di_test(percorso)

    @pytest.mark.parametrize("percorso", [
        "frontend/src/pages/PratichePage.tsx",
        "backend/app/services/marginalita.py",
        "tools/importa_storico.py",
        "e2e/contract.ts",
    ])
    def test_questi_sono_produzione(self, percorso):
        assert runner.e_file_di_produzione(percorso)
        assert not runner.e_file_di_test(percorso)

    @pytest.mark.parametrize("percorso", [
        "specs/marginalita/spec.md",
        "backlog/PBI-330-lo-storico-entra-dal-foglio.md",
        "decisions/ADR-0015-la-deroga-allo-scope-si-dichiara.md",
    ])
    def test_un_documento_non_e_ne_luno_ne_laltro(self, percorso):
        """La spec viaggia **con** il codice che cambia (AGENTS.md, SEMPRE): se
        contasse come produzione, ogni commit di soli test con la sua spec
        aggiornata verrebbe fermato per una regola che non c'entra. È il caso di
        `f35abd1`, che tocca il file di test e `specs/marginalita/spec.md`."""
        assert not runner.e_file_di_produzione(percorso)
        assert not runner.e_file_di_test(percorso)


def git_del_commit(monkeypatch, name_status: str, diff: dict[str, str]):
    """Un `git` che risponde per un commit solo: i suoi file e il suo diff."""
    def _git(*args: str) -> str:
        if args[:3] == ("show", "--format=", "--name-status"):
            return name_status
        if args[0] == "show" and "--unified=0" in args:
            return diff.get(args[-1], "")
        return ""

    monkeypatch.setattr(runner, "git", _git)


class TestITestNuoviSiLeggonoDalDiff:
    """Quali test **nascono** in questo commit: né quelli che c'erano, né quelli
    che il commit sposta da un file all'altro."""

    def test_una_funzione_aggiunta_e_un_test_nuovo(self, monkeypatch):
        git_del_commit(
            monkeypatch,
            "M\tbackend/tests/test_somma.py",
            {"backend/tests/test_somma.py":
             "@@ -1,0 +2,2 @@\n+def test_somma_due_numeri():\n+    assert somma(1, 1) == 2\n"},
        )

        nuovi = runner.test_nuovi_del_commit("abc1234")

        assert [(t.file, t.nome, t.linguaggio) for t in nuovi] == [
            ("backend/tests/test_somma.py", "test_somma_due_numeri", "python")
        ]

    def test_un_test_spostato_non_e_un_test_nuovo(self, monkeypatch):
        """Lo stesso nome cancellato e riaggiunto è un trasloco, non una nascita.

        È il caso che il Protocollo di rifinitura chiama *«un file di test
        riscritto per intero»*: senza questo, un riordino farebbe girare tutta la
        suite di quel commit e la fermerebbe come nata verde.
        """
        git_del_commit(
            monkeypatch,
            "M\tbackend/tests/test_somma.py",
            {"backend/tests/test_somma.py":
             "@@ -3,3 +3,4 @@\n-def test_vecchio():\n-    assert True\n"
             "+def test_vecchio():\n+    assert True\n+def test_davvero_nuovo():\n+    assert False\n"},
        )

        assert [t.nome for t in runner.test_nuovi_del_commit("abc1234")] == ["test_davvero_nuovo"]

    def test_riconosce_i_test_del_frontend(self, monkeypatch):
        git_del_commit(
            monkeypatch,
            "A\tfrontend/src/pages/PratichePage.test.tsx",
            {"frontend/src/pages/PratichePage.test.tsx":
             "@@ -0,0 +1,3 @@\n+  it('mostra il margine in fondo alla colonna', () => {\n"
             "+    expect(1).toBe(1)\n+  })\n"},
        )

        nuovi = runner.test_nuovi_del_commit("abc1234")

        assert [(t.nome, t.linguaggio) for t in nuovi] == [
            ("mostra il margine in fondo alla colonna", "vitest")
        ]

    def test_gli_e2e_non_sono_del_runner(self, monkeypatch):
        """`npm run e2e` da un worktree punta allo stack di un altro codice
        (ADR-0009): quel gate è della CI, e un rosso che il runner non può
        osservare non lo può nemmeno pretendere."""
        git_del_commit(
            monkeypatch,
            "M\te2e/tests/fase2-marginalita.spec.ts",
            {"e2e/tests/fase2-marginalita.spec.ts":
             "@@ -1,0 +2,1 @@\n+  test('la pratica si chiude', async ({ page }) => {\n"},
        )

        assert runner.test_nuovi_del_commit("abc1234") == []

    def test_le_righe_di_intestazione_del_diff_non_sono_codice(self, monkeypatch):
        """`+++ b/…` comincia per `+` e non è una riga aggiunta."""
        git_del_commit(
            monkeypatch,
            "M\tbackend/tests/test_somma.py",
            {"backend/tests/test_somma.py":
             "--- a/backend/tests/test_somma.py\n+++ b/backend/tests/test_somma.py\n"
             "@@ -1,0 +2,1 @@\n+def test_uno():\n"},
        )

        assert [t.nome for t in runner.test_nuovi_del_commit("abc1234")] == ["test_uno"]


class RepoDiProva:
    """Un repository vero e minuscolo, con la forma di questo: `backend/app` e
    `backend/tests`.

    Qui git non si può fingere. Il gate del rosso estrae un commit in un
    `git worktree` usa e getta e **ci esegue i test dentro**: è tutto ciò che fa, e
    un doppio lo lascerebbe fuori dalla prova. Il prezzo è qualche decimo di secondo
    per commit; la prova è che il rosso viene osservato, non dedotto dal messaggio.
    """

    def __init__(self, radice: Path):
        self.radice = radice
        self._git("init", "-q")
        self._git("config", "user.email", "prova@example.invalid")
        self._git("config", "user.name", "prova")
        self._git("config", "commit.gpgsign", "false")
        base = self.commit("chore: l'impalcatura", {
            "backend/app/__init__.py": "",
            "backend/tests/__init__.py": "",
        })
        self._git("update-ref", "refs/remotes/origin/main", base)

    def _git(self, *args: str) -> str:
        fatto = subprocess.run(["git", *args], cwd=self.radice,
                               capture_output=True, text=True, check=True)
        return fatto.stdout.strip()

    def commit(self, messaggio: str, file: dict[str, str]) -> str:
        for percorso, contenuto in file.items():
            f = self.radice / percorso
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(contenuto, encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", messaggio)
        return self._git("rev-parse", "HEAD")


@pytest.fixture
def repo_di_prova(tmp_path, monkeypatch):
    radice = tmp_path / "repo"
    radice.mkdir()
    repo = RepoDiProva(radice)
    monkeypatch.setattr(runner, "REPO", radice)
    return repo


def sorgente_che_lascia_un_segno(marcatore: Path, corpo: str) -> str:
    """Un test che lascia scritto di essere stato eseguito, poi decide se passare.

    Il marcatore è la sola prova che il test è **girato** invece di essere saltato,
    dedotto dal messaggio del commit, o mai raccolto: il worktree in cui gira viene
    distrutto, quindi il segno va lasciato fuori.
    """
    return (
        "from pathlib import Path\n\n\n"
        "def test_la_somma_fa_due():\n"
        f"    Path({str(marcatore)!r}).write_text('eseguito')\n"
        f"    {corpo}\n"
    )


class TestIlGateDelRossoCamminaICommit:
    """PBI-103: *quei test sono mai stati rossi?*

    Tre esiti e non due (dalla tabella del PBI): a quel commit il test **fallisce**
    — il RED c'è stato, e il gate passa; **passa** — è nato verde, e il gate ferma;
    **si salta** — il rosso non era osservabile lì, e il gate ferma con una ragione
    distinta, perché le due letture non vanno confuse.
    """

    def test_un_test_nato_verde_ferma_e_dice_quale(self, repo_di_prova, tmp_path):
        """Il caso di `f35abd1`: il codice era già in un commit precedente."""
        repo_di_prova.commit("feat: la somma", {
            "backend/app/somma.py": "def somma(a, b):\n    return a + b\n",
        })
        sha = repo_di_prova.commit("test: la somma fa due", {
            "backend/tests/test_somma.py": sorgente_che_lascia_un_segno(
                tmp_path / "girato", "from app.somma import somma\n    assert somma(1, 1) == 2"),
        })

        mancati = runner.gate_del_rosso()

        assert [m["commit"] for m in mancati] == [sha[:7]]
        assert "nato verde" in mancati[0]["esito"]
        assert "test_la_somma_fa_due" in mancati[0]["test"]
        assert (tmp_path / "girato").exists(), "il verdetto va osservato, non dedotto"

    def test_la_coppia_giusta_passa_e_il_test_e_girato_davvero(self, repo_di_prova, tmp_path):
        """`test(...) (RED)` e poi `fix(...)`: il ciclo fatto come si deve."""
        repo_di_prova.commit("test: la somma fa due (RED)", {
            "backend/tests/test_somma.py": sorgente_che_lascia_un_segno(
                tmp_path / "girato", "from app.somma import somma\n    assert somma(1, 1) == 2"),
        })
        repo_di_prova.commit("fix: aggiungi la somma", {
            "backend/app/somma.py": "def somma(a, b):\n    return a + b\n",
        })

        assert runner.gate_del_rosso() == []
        assert (tmp_path / "girato").exists(), (
            "il rosso è stato dedotto dal messaggio del commit invece che osservato"
        )

    def test_un_commit_misto_ferma_senza_girare_niente(self, repo_di_prova, tmp_path):
        """Il caso di `aa40167` (PBI-328): pagina e test nello stesso commit.

        Il rosso non può essere esistito in mezzo a un commit solo, e si riconosce
        dal solo diff: eseguire i test lì non aggiungerebbe niente.
        """
        sha = repo_di_prova.commit("feat: la somma, con il suo test", {
            "backend/app/somma.py": "def somma(a, b):\n    return a + b\n",
            "backend/tests/test_somma.py": sorgente_che_lascia_un_segno(
                tmp_path / "girato", "from app.somma import somma\n    assert somma(1, 1) == 2"),
        })

        mancati = runner.gate_del_rosso()

        assert [m["commit"] for m in mancati] == [sha[:7]]
        assert "produzione" in mancati[0]["esito"]
        assert not (tmp_path / "girato").exists(), "il diff bastava: i test non vanno eseguiti"

    def test_uno_skipif_ferma_con_la_ragione_sua(self, repo_di_prova):
        """«Rosso non osservabile» non è «nato verde», e confonderli nasconde la
        domanda che il PBI-103 vuole vedere posta: *se il rosso non si può vedere,
        cosa vale al suo posto?*"""
        sha = repo_di_prova.commit("test: il golden, se il foglio c'è", {
            "backend/tests/test_golden.py":
                "import pytest\n\n\n"
                "@pytest.mark.skipif(True, reason='il foglio non c\\'è su questa macchina')\n"
                "def test_il_golden_coincide():\n    assert False\n",
        })

        mancati = runner.gate_del_rosso()

        assert [m["commit"] for m in mancati] == [sha[:7]]
        assert "non osservabile" in mancati[0]["esito"]
        assert "nato verde" not in mancati[0]["esito"]

    def test_un_refactor_senza_test_nuovi_non_ferma(self, repo_di_prova):
        """La regola morde sul test nuovo, non su ogni riga scritta."""
        repo_di_prova.commit("feat: la somma", {
            "backend/app/somma.py": "def somma(a, b):\n    return a + b\n",
        })
        repo_di_prova.commit("refactor: dai un nome ai due addendi", {
            "backend/app/somma.py": "def somma(primo, secondo):\n    return primo + secondo\n",
        })

        assert runner.gate_del_rosso() == []

    def test_non_lascia_worktree_appesi_ne_sporca_lalbero(self, repo_di_prova, tmp_path):
        """Il gate gira **sotto** l'agente che lavora: se toccasse l'albero del giro
        romperebbe il lavoro che sta giudicando."""
        repo_di_prova.commit("feat: la somma", {
            "backend/app/somma.py": "def somma(a, b):\n    return a + b\n",
        })
        repo_di_prova.commit("test: la somma fa due", {
            "backend/tests/test_somma.py": sorgente_che_lascia_un_segno(
                tmp_path / "girato", "from app.somma import somma\n    assert somma(1, 1) == 2"),
        })
        prima = repo_di_prova._git("worktree", "list")

        assert runner.gate_del_rosso() != []
        assert repo_di_prova._git("worktree", "list") == prima
        assert repo_di_prova._git("status", "--porcelain") == ""

    def test_guarda_solo_i_commit_nuovi_dallultimo_giro(self, repo_di_prova, tmp_path):
        """Al secondo giro del Builder i commit già visti non si rigirano: il gate
        sta dentro un ciclo che può ripetersi quattro volte, e rieseguire ogni volta
        la storia intera moltiplicherebbe il tempo macchina per le revisioni."""
        repo_di_prova.commit("test: la somma fa due (RED)", {
            "backend/tests/test_somma.py": sorgente_che_lascia_un_segno(
                tmp_path / "girato", "from app.somma import somma\n    assert somma(1, 1) == 2"),
        })
        visti: set[str] = set()

        assert runner.gate_del_rosso(visti=visti) == []
        assert len(visti) == 1
        (tmp_path / "girato").unlink()

        assert runner.gate_del_rosso(visti=visti) == []
        assert not (tmp_path / "girato").exists(), "un commit già visto è stato rigirato"
