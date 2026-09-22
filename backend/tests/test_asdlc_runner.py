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
import io
import json
import os
import subprocess
import sys
import time
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

    def test_un_commento_falso_non_fa_non_pronto_da_solo(self):
        """Giro 4 di PBI-335 (03/09/2026): il Critic ha chiesto due commenti corretti.

        Il Builder in `TEST_ONLY` non può toccarli, e non c'è un rosso che
        apra quel file: un `NON PRONTO` per una frase manda il Builder a girare
        su un rimedio che non può eseguire. È un terzo esito, né rilievo né
        domanda: una nota per chi mergia, che non pesa sul verdetto.
        """
        prompt = runner.PROMPT_CRITIC.format(pbi_path="backlog/x.md").lower()
        assert "note per chi mergia" in prompt, (
            "un commento falso in un file di produzione si segnala sotto un titolo "
            "suo, fuori dai rilievi numerati, e da solo non fa NON PRONTO"
        )

    def test_l_esenzione_del_commento_falso_non_guarda_dove_sta_il_file(self):
        """PBI-342, giro 5 (07/09/2026): l'esenzione dice il luogo, non la ragione.

        Il Critic ha trovato un commento falso in `AnalisiPage.test.tsx` e ha
        escluso l'esenzione con l'argomento giusto per la regola scritta — «è un
        file di test» — chiudendo il giro su `non convergente` per una frase,
        dopo quattro giri che avevano chiuso rilievi di comportamento. Ma la
        ragione dell'esenzione non è dove sta il file: è che un commento non ha
        comportamento, nessun rosso lo produce e spendere un giro intero —
        Builder, gate e Critic — per una frase è un giro buttato ovunque stia.
        """
        critic = runner.PROMPT_CRITIC.format(pbi_path="backlog/x.md")
        rimedio = runner.PROMPT_RIMEDIO.format(rapporto="x", pbi_path="backlog/x.md")
        for nome, prompt in (("PROMPT_CRITIC", critic), ("PROMPT_RIMEDIO", rimedio)):
            assert "commento falso in un file di produzione" not in prompt, (
                f"{nome} restringe l'esenzione alla produzione: un commento falso in un "
                "file di test costa lo stesso giro, e la regola lo lascia bloccare"
            )
            assert "in un file di test" in prompt, (
                f"{nome} deve nominare il caso del file di test, o chi legge la regola "
                "la applica alla lettera e il caso torna"
            )

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

    def test_dice_come_si_fa_il_test_first_quando_il_codice_c_e_gia(self):
        """Sulla strada del rimedio «test-first» alla lettera è ineseguibile.

        Il codice che il rilievo riguarda è già committato: qualunque test il
        Builder scriva adesso nasce verde, e il gate del rosso lo ferma. È
        successo su **PBI-332**, due commit su due — `851c967` (la guardia
        scritta dopo l'import che difende) e `f429096` (test e produzione
        insieme) — dopo che il Critic aveva chiesto proprio quei test. Ripetere
        «test-first» senza dire **come** è un ordine che non si può eseguire, e
        un ordine ineseguibile lo si smette di leggere.

        Il **come** è cambiato. Il prompt ordinava di riportare il test davanti
        al codice con un `git rebase` e di verificarlo rosso lì; il giro 6 di
        PBI-333 si è chiuso `sospeso` proprio su quella domanda, e il 02/09/2026
        Francesco ha deciso che **il riordino non vale come rosso osservato**
        (`PBI-105`, misurato su un albero staccato identico byte per byte). La
        contraddizione era interna alla macchina: `ADR-0021` chiede il rosso
        prima, e questo prompt ordinava il gesto che lo fabbrica dopo. La strada
        buona esiste ed è `ADR-0022`: il test resta in coda, si **dichiara** nato
        verde, e a dire se guarda qualcosa sono i mutanti del gate.
        """
        prompt = runner.PROMPT_RIMEDIO.format(rapporto="x", pbi_path="backlog/x.md")

        assert "rebase" not in prompt, (
            "il riordino della storia non vale come rosso osservato (PBI-105, "
            "02/09): ordinarlo qui rifabbrica a ogni revisione la contraddizione "
            "con ADR-0021. Su questa strada l'unica cosa che il Builder spostava "
            "era il test — se un giorno servisse un rebase dei soli messaggi, "
            "questa asserzione si restringe apposta, non si cancella"
        )
        assert "nato verde" in prompt, (
            "tolto il riordino, senza la dichiarazione il Builder non ha strada: "
            "un test che nasce verde va detto tale, non spacciato per un RED"
        )
        assert "morde" in prompt, (
            "a dire se quel test vale è la quarta lettura di ADR-0022 — i "
            "mutanti delle righe del branch — non la posizione del suo commit"
        )
        assert "rosso" in prompt, (
            "il rosso resta dovuto quando il rilievo è che il codice è sbagliato: "
            "lì il test fallisce davvero, e sono due commit"
        )

    def test_ripete_le_regole_che_il_rimedio_puo_violare(self):
        """Il rimedio è codice come il resto: stesse regole, non un'eccezione.

        Un commit di rimedio che accorpa tre correzioni, o che chiude un rilievo
        cancellando un test, passa i gate e disfa quello che il Critic difendeva.
        """
        prompt = runner.PROMPT_RIMEDIO.format(rapporto="x", pbi_path="backlog/x.md")
        assert "test" in prompt.lower(), "il rimedio non si chiude spegnendo un test"
        assert "commit" in prompt.lower(), "un commit per rimedio, come nel resto del PBI"

    def test_dice_cosa_fare_di_un_commento_falso_in_produzione(self):
        """Il terzo caso, trovato dal giro 4 di PBI-335 (03/09/2026).

        Il rilievo era due commenti sbagliati in `PratichePage.tsx` e in
        `e2e/contract.ts`. Non è né «manca la guardia» né «il codice è
        sbagliato»: un commento non ha comportamento, non c'è un rosso da
        osservare e in `TEST_ONLY` quel file è chiuso. Il Builder ha rifiutato
        le due scappatoie — un rosso recitato, un hook spento — e ha scritto la
        domanda. Il prompt deve nominare il caso e dire la strada, perché al giro
        dopo la stessa domanda tornerebbe uguale.
        """
        prompt = runner.PROMPT_RIMEDIO.format(rapporto="x", pbi_path="backlog/x.md")
        assert "commento falso" in prompt, (
            "un rilievo di solo commento in un file di produzione non ha un rosso: "
            "senza una strada scritta il Builder si ferma o imbroglia"
        )
        assert "chi mergia" in prompt, (
            "se nel giro non si apre IMPL su quel file, la correzione la fa chi mergia: "
            "il Builder lascia il rilievo aperto e nomina file e riga"
        )


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
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        with runner.lucchetto():
            with pytest.raises(runner.AlberoOccupato):
                with runner.lucchetto():
                    pass

    def test_rilasciato_torna_libero(self, tmp_path, monkeypatch):
        """Il lucchetto è del **processo**, non del file: se il runner muore di
        schianto non resta un lucchetto morto da togliere a mano."""
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        with runner.lucchetto():
            pass
        with runner.lucchetto():
            pass

    def test_il_lucchetto_sta_dove_stanno_i_log(self, tmp_path, monkeypatch):
        """Chi sposta `LOG_DIR` sposta anche il lucchetto — e non è cosmesi.

        Il lucchetto è uno dei file che il runner scrive sotto `runs/`, e chi
        redirige quella cartella crede di aver spostato tutto: è ciò che fanno i
        test di `main()`, che girano su `tmp_path`. Con un percorso calcolato
        all'import il lucchetto resta indietro, nel `runs/` **vero** — e allora
        quei test non provano più il runner: provano se sul PC c'è un runner
        vivo. Girando *dentro* un giro del runner — cioè ogni volta che il gate
        pytest è il suo — falliscono tutti insieme con «Non parto: un altro
        runner sta già lavorando», che è il contrario di ciò che affermano.

        Due nomi per la stessa cartella divergono; qui erano già divergenti.
        """
        monkeypatch.setattr(runner, "LOG_DIR", tmp_path)
        with runner.lucchetto():
            assert (tmp_path / runner.NOME_LUCCHETTO).exists()


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

    def test_crea_branch_conta_anche_i_rami_locali(self, monkeypatch):
        """Difetto 29, misurato su PBI-335 la sera del 02/09/2026.

        Il giro `20260902-220921` è morto in **zero secondi**, prima del Builder:
        `git switch -c pbi/pbi-335 origin/main` → *«esiste già un ramo denominato
        pbi/pbi-335»*. Su `origin` quel ramo non c'era — era stato mergiato e
        cancellato giorni prima — ma in `ada-run` era rimasto il locale, con
        dentro il solo commit che aveva scritto il documento del PBI.

        `nome_libero()` chiede i nomi occupati a chi non può saperli tutti: il
        remoto risponde per sé, e `switch -c` fallisce sul locale. La premessa
        che reggeva la scelta — *«il worktree del runner è appena stato creato»* —
        vale per un albero usa e getta, non per `ada-run`, che è di lunga vita e
        colleziona i rami di ogni sessione che ci ha lavorato dentro.
        """
        def _git(*args: str) -> str:
            if args[0] == "ls-remote":
                return ""  # su origin è stato mergiato e cancellato
            if args[0] == "branch":
                return "pbi/pbi-335\n"  # ma nel worktree è rimasto
            return ""

        monkeypatch.setattr(runner, "git", _git)
        assert runner.crea_branch("PBI-335") == "pbi/pbi-335-giro2", (
            "un nome che `switch -c` non può prendere è un nome occupato, "
            "qualunque sia il ref che lo occupa"
        )

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

    def test_il_builder_sa_che_una_restrizione_si_guadagna(self):
        """Il gate ha fermato PBI-333 su `not.toContain('/analisi/foglio')`.

        A quel commit quella voce non esiste per nessun ruolo: l'asserzione è vera
        per costruzione, e nessuna riscrittura del commit la fa mordere finché ciò
        che nega non esiste. L'ordine in cui invece morde esiste — la cosa senza la
        restrizione, poi il test dell'assenza, poi la restrizione — ma è l'unico, e
        un Builder che non lo conosce riscrive lo stesso test nello stesso posto al
        giro dopo.
        """
        prompt = runner.PROMPT_BUILDER.lower()
        assert "assenza" in prompt and "restrizione" in prompt

    def test_il_builder_corregge_i_commenti_nel_fix_che_li_rende_falsi(self):
        """Il giro 4 di PBI-335 (03/09/2026) si è fermato su due commenti.

        `PratichePage.tsx:1892` ed `e2e/contract.ts:109` mandavano ancora il N°
        preventivo in accettazione, dopo che `4868355` l'aveva portato in
        testata. Il Critic li ha chiesti corretti; il Builder, in `TEST_ONLY`,
        non poteva: un commento non ha comportamento, nessun test lo nomina,
        nessun rosso riapre quel file. Le uniche uscite erano un rosso recitato
        o un hook spento, e ha fatto bene a non prenderle.

        Il momento in cui quel commento si corregge esiste ed è uno solo: il
        `fix` che lo rende falso, quando la produzione è ancora aperta. Il
        prompt deve dirlo lì, al passo in cui il commit di produzione nasce.
        """
        prompt = runner.PROMPT_BUILDER.lower()
        assert "commenti" in prompt and "rende falsi" in prompt, (
            "il commento che un fix rende falso si corregge nello stesso commit del "
            "fix: dopo, in TEST_ONLY, non c'è più un rosso che riapra quel file "
            "(PBI-335 giro 4, 03/09/2026)"
        )


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

    def test_un_titolo_con_un_escape_unicode_si_legge_come_lo_esegue_vitest(
            self, monkeypatch):
        """Il nome estratto dal sorgente deve essere la stringa **valutata**.

        Il gate lo usa per due cose che vivono a runtime: il filtro `-t`, che vitest
        matcha sul titolo vero, e la chiave con cui si rilegge il json, dove il
        titolo è già valutato. Passare `all’officina` a `-t` non matcha niente:
        zero test girati, `nessuno`, e il gate ferma un commit sano.
        """
        git_del_commit(
            monkeypatch,
            "M\tfrontend/src/pages/AnalisiPage.test.tsx",
            {"frontend/src/pages/AnalisiPage.test.tsx":
             "@@ -1,0 +2,1 @@\n"
             "+  it('non compare all\\u2019officina: sono i conti dell\\u2019azienda', () => {\n"},
        )

        assert [t.nome for t in runner.test_nuovi_del_commit("abc1234")] == [
            "non compare all’officina: sono i conti dell’azienda"
        ]

    def test_un_apostrofo_con_la_barra_non_taglia_il_titolo_a_meta(self, monkeypatch):
        """`it('l\\'officina non lo vede')`: l'apice scappato non chiude la stringa.

        Qui il titolo si perde due volte — la regola si ferma all'apice e ne legge
        metà, e quella metà porta ancora la barra — e tutte e due le volte `-t` non
        matcha.
        """
        git_del_commit(
            monkeypatch,
            "M\tfrontend/src/pages/AnalisiPage.test.tsx",
            {"frontend/src/pages/AnalisiPage.test.tsx":
             "@@ -1,0 +2,1 @@\n"
             "+  it('l\\'officina non lo vede', () => {\n"},
        )

        assert [t.nome for t in runner.test_nuovi_del_commit("abc1234")] == [
            "l'officina non lo vede"
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
        """Il caso di `f35abd1`: il codice era già in un commit precedente.

        E il test **non guarda niente** — `callable(somma)` è vero anche con un
        `return` cancellato. Da PBI-105 un nato verde che morde passa: il caso che
        ferma è questo, il verde che non prova niente."""
        repo_di_prova.commit("feat: la somma", {
            "backend/app/somma.py": "def somma(a, b):\n    return a + b\n",
        })
        sha = repo_di_prova.commit("test: la somma fa due", {
            "backend/tests/test_somma.py": sorgente_che_lascia_un_segno(
                tmp_path / "girato", "from app.somma import somma\n    assert callable(somma)"),
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

    def test_anche_sul_commit_misto_lid_e_quello_che_pytest_trova(
        self, repo_di_prova, monkeypatch
    ):
        """Il ramo del commit misto è il più visibile del gate — è il caso di
        PBI-328, l'esempio che il PBI porta per primo — e l'id lo ricostruiva a mano:
        senza la classe, e col prefisso `backend/` che da `backend/` non si esegue.
        Chi copia dal `fermato` si prende un «not found» e conclude che il gate ha
        sbagliato: il difetto che `e64555f` chiude, lasciato aperto proprio lì.

        L'AST si legge dal blob (`git show sha:percorso`): niente worktree, quindi
        «ferma **senza** girare i test» resta intatto.
        """
        monkeypatch.setattr(
            runner, "worktree_usa_e_getta",
            lambda sha: pytest.fail("il diff bastava: nessun commit va estratto"),
        )
        repo_di_prova.commit("feat: la somma, con il suo test", {
            "backend/app/somma.py": "def somma(a, b):\n    return a + b\n",
            "backend/tests/test_somma.py":
                "from app.somma import somma\n\n\n"
                "class TestLaSomma:\n"
                "    def test_fa_due(self):\n        assert somma(1, 1) == 2\n",
        })

        mancati = runner.gate_del_rosso()

        assert mancati[0]["test"] == "tests/test_somma.py::TestLaSomma::test_fa_due", (
            "l'id va scritto come si esegue, dalla cartella da cui si esegue"
        )
        assert "produzione" in mancati[0]["esito"]

    def test_sul_commit_misto_un_test_del_frontend_porta_il_filtro_di_vitest(
        self, repo_di_prova, monkeypatch
    ):
        """`file -t nome`, che è come vitest lo riesegue: `::` lì non vuol dire
        niente e manderebbe chi legge a cercare un node id che non esiste."""
        monkeypatch.setattr(
            runner, "worktree_usa_e_getta",
            lambda sha: pytest.fail("il diff bastava: nessun commit va estratto"),
        )
        repo_di_prova.commit("feat: il riquadro del margine, col suo test", {
            "frontend/src/Margine.tsx": "export const Margine = () => null\n",
            "frontend/src/Margine.test.tsx":
                "it('mostra il margine', () => {\n  expect(1).toBe(1)\n})\n",
        })

        mancati = runner.gate_del_rosso()

        assert mancati[0]["test"] == "src/Margine.test.tsx -t mostra il margine"

    def test_un_test_punto_spec_non_esce_dal_gate_per_il_suo_nome(
        self, repo_di_prova, monkeypatch
    ):
        """`.spec.tsx` è un test per vitest quanto `.test.tsx` — è la sua `include`
        di default — e il gate lo deve trattare come tale.

        Il verso è quello: il file resta un test e i suoi casi sono test nuovi, così
        il commit che lo porta insieme alla pagina ferma come misto. L'altro verso —
        toglierlo dai file di test — lo renderebbe produzione, e un commit di soli
        `.spec` verrebbe fermato per una regola che non c'entra.

        Serve perché le due liste divergevano: `e_file_di_test` conosceva `.spec.*`,
        `linguaggio_del_test` no. Il file non era né produzione né portatore di test
        nuovi, e il commit misto passava **in silenzio** — il caso che il Protocollo
        di rifinitura vieta: in caso di dubbio il gate ferma e lo dice, non indovina.
        """
        monkeypatch.setattr(
            runner, "worktree_usa_e_getta",
            lambda sha: pytest.fail("il diff bastava: nessun commit va estratto"),
        )
        sha = repo_di_prova.commit("feat: il riquadro del margine, col suo spec", {
            "frontend/src/Margine.tsx": "export const Margine = () => null\n",
            "frontend/src/Margine.spec.tsx":
                "it('mostra il margine', () => {\n  expect(1).toBe(1)\n})\n",
        })

        mancati = runner.gate_del_rosso()

        assert [m["commit"] for m in mancati] == [sha[:7]], (
            "un test uscito dal gate per la sola forma del suo nome"
        )
        assert "produzione" in mancati[0]["esito"]
        assert mancati[0]["test"] == "src/Margine.spec.tsx -t mostra il margine"

    def test_un_nome_che_nel_file_non_ce_non_finge_di_essere_un_node_id(
        self, repo_di_prova, monkeypatch
    ):
        """Un test generato, o dentro un `if`: il gate non indovina, e non scrive un
        `::` che promette a chi legge un comando che non esiste."""
        monkeypatch.setattr(
            runner, "worktree_usa_e_getta",
            lambda sha: pytest.fail("il diff bastava: nessun commit va estratto"),
        )
        repo_di_prova.commit("feat: la somma, con i suoi test generati", {
            "backend/app/somma.py": "def somma(a, b):\n    return a + b\n",
            "backend/tests/test_somma.py":
                "for _caso in (1, 2):\n"
                "    def test_generato():\n        assert True\n",
        })

        mancati = runner.gate_del_rosso()

        assert "::" not in mancati[0]["test"], (
            "un id che dà «not found» fa sembrare sbagliato il gate invece del commit"
        )
        assert "test_generato" in mancati[0]["test"]

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

    def test_un_rosso_accanto_a_un_nato_verde_non_lo_copre(self, repo_di_prova, tmp_path):
        """La classificazione è **per test**, non per comando.

        Un `test(...) (RED)` porta quasi sempre più di un test, e girano tutti in un
        `pytest` solo: se basta un rosso per dire «il RED c'è stato», il test nato
        verde accanto sparisce dall'elenco. È il caso di `f35abd1`, che di funzioni
        di test ne introduce dodici — e leggere l'esito dal totale ne farebbe un
        tutto-o-niente su dodici invece che una misura per test.
        """
        repo_di_prova.commit("feat: la somma", {
            "backend/app/somma.py": "def somma(a, b):\n    return a + b\n",
        })
        sha = repo_di_prova.commit("test: la somma e la differenza (RED)", {
            "backend/tests/test_conti.py":
                "from app.somma import somma\n\n\n"
                "def test_la_somma_fa_due():\n    assert callable(somma)\n\n\n"
                "def test_la_differenza_fa_zero():\n"
                "    from app.differenza import differenza\n"
                "    assert differenza(1, 1) == 0\n",
        })

        mancati = runner.gate_del_rosso()

        assert [m["commit"] for m in mancati] == [sha[:7]], (
            "il rosso di un test vicino ha coperto quello nato verde"
        )
        assert "test_la_somma_fa_due" in mancati[0]["test"]
        assert "test_la_differenza_fa_zero" not in mancati[0]["test"], (
            "un test che a quel commit è davvero rosso non va nell'elenco"
        )

    def test_uno_skipif_accanto_a_un_rosso_non_sparisce(self, repo_di_prova):
        """Lo `skipped` in mezzo a un `failed`: il PBI-103 esiste per **raccogliere**
        i casi in cui il rosso non si può vedere, e sommarli al totale li perde."""
        sha = repo_di_prova.commit("test: il golden e la somma (RED)", {
            "backend/tests/test_conti.py":
                "import pytest\n\n\n"
                "@pytest.mark.skipif(True, reason='il foglio non c\\'è su questa macchina')\n"
                "def test_il_golden_coincide():\n    assert False\n\n\n"
                "def test_la_somma_fa_due():\n"
                "    from app.somma import somma\n    assert somma(1, 1) == 2\n",
        })

        mancati = runner.gate_del_rosso()

        assert [m["commit"] for m in mancati] == [sha[:7]]
        assert "non osservabile" in mancati[0]["esito"]
        assert "test_il_golden_coincide" in mancati[0]["test"]

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
                tmp_path / "girato", "from app.somma import somma\n    assert callable(somma)"),
        })
        prima = repo_di_prova._git("worktree", "list")

        assert runner.gate_del_rosso() != []
        assert repo_di_prova._git("worktree", "list") == prima
        assert repo_di_prova._git("status", "--porcelain") == ""

    def test_lelenco_dice_il_comando_con_cui_ritrovare_il_test(self, repo_di_prova, tmp_path):
        """L'elenco porta il **node id**, non un `file::nome` ricostruito.

        Un test dentro una classe si chiama `file::Classe::test`, e chi copia dal
        rapporto un id senza la classe si prende un «not found» da pytest e crede
        che il gate abbia sbagliato. È successo il 31/08 rileggendo `4d7b48f`.
        """
        repo_di_prova.commit("feat: la somma", {
            "backend/app/somma.py": "def somma(a, b):\n    return a + b\n",
        })
        repo_di_prova.commit("test: la somma fa due", {
            "backend/tests/test_somma.py":
                "from app.somma import somma\n\n\n"
                "class TestLaSomma:\n"
                "    def test_fa_due(self):\n        assert callable(somma)\n",
        })

        mancati = runner.gate_del_rosso()

        assert mancati[0]["test"] == "tests/test_somma.py::TestLaSomma::test_fa_due", (
            "l'id va scritto come si esegue, dalla cartella da cui si esegue"
        )

    def test_lelenco_non_taglia_un_nome_a_meta(self):
        """Un commit con quaranta test nuovi non deve finire con un `::test` mozzo:
        un nome tagliato non si ritrova, e sembra un difetto del gate."""
        voce = runner.voce_mancata(
            "abc1234", "test: tanti", [f"tests/test_x.py::test_{n}" for n in range(40)],
            "nato verde", "",
        )

        assert "tests/test_x.py::test_0, tests/test_x.py::test_1" in voce["test"]
        assert voce["test"].endswith("e altri 36")

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


class TestLEsitoSiLeggePerTest:
    """Il verdetto è di **ogni test**, non del comando che li ha girati insieme.

    I test nuovi di un commit girano in un `pytest` solo — costa un avvio di
    interprete invece di dodici — ma il conteggio finale (`1 failed, 11 passed`) è
    una somma, e una somma non dice **quale**. Leggere l'esito dal totale farebbe di
    ogni `test(...) (RED)` un tutto-o-niente: basterebbe un test che morde per
    coprire gli undici nati verdi accanto.
    """

    def test_pytest_lo_dice_riga_per_riga(self):
        uscita = (
            "tests/test_conti.py::test_la_somma_fa_due PASSED                  [ 33%]\n"
            "tests/test_conti.py::TestIlGolden::test_coincide SKIPPED (il foglio) [ 66%]\n"
            "tests/test_conti.py::test_la_differenza_fa_zero FAILED            [100%]\n"
            "\n1 failed, 1 passed, 1 skipped in 0.12s\n"
        )

        assert runner.esiti_di_pytest(uscita) == {
            "tests/test_conti.py::test_la_somma_fa_due": "verde",
            "tests/test_conti.py::TestIlGolden::test_coincide": "saltato",
            "tests/test_conti.py::test_la_differenza_fa_zero": "rosso",
        }

    def test_un_test_parametrizzato_torna_sotto_il_nome_della_funzione(self):
        """`pytest -v` stampa una riga per caso — `test_x[1]`, `test_x[2]` — mentre
        l'id che il gate ha chiesto è quello della funzione. Un caso rosso basta:
        quel test un momento in cui mordeva ce l'ha avuto."""
        uscita = ("tests/t.py::test_lo_scarto[1] PASSED   [ 50%]\n"
                  "tests/t.py::test_lo_scarto[2] FAILED   [100%]\n")

        assert runner.esiti_di_pytest(uscita) == {"tests/t.py::test_lo_scarto": "rosso"}

    def test_vitest_lo_dice_nel_suo_json(self, tmp_path):
        """`--reporter=json`: l'unica forma in cui vitest dà l'esito per test senza
        farlo dedurre da un simbolo in mezzo all'output."""
        rapporto = tmp_path / "vitest.json"
        rapporto.write_text(json.dumps({"testResults": [{
            "name": "src/Margine.test.tsx",
            "assertionResults": [
                {"title": "mostra il margine", "status": "passed"},
                {"title": "senza dati non mostra niente", "status": "failed"},
                {"title": "il caso lento", "status": "skipped"},
            ],
        }]}), encoding="utf-8")

        assert runner.esiti_di_vitest(rapporto) == {
            "mostra il margine": "verde",
            "senza dati non mostra niente": "rosso",
            "il caso lento": "saltato",
        }

    def test_un_rapporto_che_non_ce_non_e_un_verdetto(self, tmp_path):
        """Vuoto e non «tutto verde»: chi non ha letto niente non ha visto niente, e
        l'esito del comando intero resta l'unica cosa che si sa."""
        assert runner.esiti_di_vitest(tmp_path / "mai-scritto.json") == {}


class TestUnGateGuastoNonEUnCicloMancato:
    """`127` non è «nato verde».

    Il gate butta via il codice di uscita di proposito — pytest torna 0 anche con
    tutto saltato — ma un comando che **non parte** non ha detto niente sui test: non
    stampa conteggi, e leggerlo come «il rosso non si è mai visto» accusa il Builder
    di un guasto della macchina. Il caso concreto è il venv fuori dal `PATH`, ed è
    già costato una diagnosi sbagliata (difetto 11).
    """

    def _comando(self, linguaggio="python"):
        return runner.ComandoDiProva(
            Path("/tmp"), ["pytest", "--tb=no", "-v", "tests/t.py::test_x"],
            linguaggio, {"tests/t.py::test_x": "tests/t.py::test_x"},
        )

    def test_un_comando_che_non_parte_alza_invece_di_accusare(self, monkeypatch):
        monkeypatch.setattr(
            runner, "esegui",
            lambda *a, **k: (127, "comando non eseguibile: pytest — [Errno 2]"),
        )

        with pytest.raises(runner.GuastoDelGate) as guasto:
            runner.esiti_del_comando(self._comando())

        assert "pytest" in str(guasto.value)

    def test_una_riga_di_comando_sbagliata_e_del_gate_non_del_builder(self, monkeypatch):
        """`4` è l'uso sbagliato di pytest: se l'id l'ha scritto il gate, l'errore è
        del gate."""
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (4, "ERROR: not found"))

        with pytest.raises(runner.GuastoDelGate):
            runner.esiti_del_comando(self._comando())

    def test_nessun_test_raccolto_resta_una_lettura_sui_test(self, monkeypatch):
        """`5` lo dice pytest **sui test**: lì il gate non indovina e lo scrive, che
        è un'altra cosa dal non aver potuto guardare."""
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (5, "no tests ran in 0.01s"))

        esiti, _ = runner.esiti_del_comando(self._comando())

        assert esiti == {"tests/t.py::test_x": "nessuno"}

    def test_un_errore_di_raccolta_resta_un_rosso(self, monkeypatch):
        """L'import che a quel commit non esiste ancora è il rosso più comune del
        test-first: `2` è un codice di pytest, e il conteggio c'è."""
        monkeypatch.setattr(
            runner, "esegui",
            lambda *a, **k: (2, "ERROR tests/t.py\n1 error in 0.02s"),
        )

        esiti, _ = runner.esiti_del_comando(self._comando())

        assert esiti == {"tests/t.py::test_x": "rosso"}

    def _comando_vitest(self, rapporto):
        relativo = "src/pages/FoglioPage.test.tsx"
        nome = "mostra le commesse del foglio"
        return runner.ComandoDiProva(
            Path("/tmp"), ["npm", "test", "--", relativo, "-t", nome], "vitest",
            {nome: f"{relativo} -t {nome}"}, rapporto,
        )

    def test_un_file_che_non_si_carica_e_un_rosso_anche_in_vitest(
            self, monkeypatch, tmp_path):
        """Il gemello frontend dell'import che non esiste ancora.

        `FoglioPage.test.tsx` senza `FoglioPage.tsx` è il RED classico del
        test-first nel frontend, ed è il caso che in Python `leggi_esito` conta come
        rosso leggendo `1 error`. Col `--reporter=json` quel conteggio a schermo non
        c'è mai: il file non si carica, quindi non esiste nessun risultato per-test,
        e l'unica cosa scritta è il file `failed` con zero `assertionResults`.
        """
        rapporto = tmp_path / "vitest-0.json"
        rapporto.write_text(json.dumps({"testResults": [
            {"name": "src/pages/FoglioPage.test.tsx", "status": "failed",
             "assertionResults": []},
        ]}), encoding="utf-8")
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (1, "\n RUN  v3.2.4\n"))

        esiti, _ = runner.esiti_del_comando(self._comando_vitest(rapporto))

        assert esiti == {"mostra le commesse del foglio": "rosso"}

    def test_un_file_verde_senza_test_non_diventa_un_rosso_ne_un_verde(
            self, monkeypatch, tmp_path):
        """Il file `passed` con zero test è il filtro `-t` che non ha matchato niente.

        Leggerlo come verde darebbe per girato un test che non è mai partito — il
        gate del rosso passerebbe in silenzio proprio dove non ha guardato. Resta
        `nessuno`, che è quello che il gate segnala come «rosso non isolabile».
        """
        rapporto = tmp_path / "vitest-0.json"
        rapporto.write_text(json.dumps({"testResults": [
            {"name": "src/pages/FoglioPage.test.tsx", "status": "passed",
             "assertionResults": []},
        ]}), encoding="utf-8")
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "\n RUN  v3.2.4\n"))

        esiti, _ = runner.esiti_del_comando(self._comando_vitest(rapporto))

        assert esiti == {"mostra le commesse del foglio": "nessuno"}


class TestIlGateDelRossoStaNelGiro:
    """Dove sta il gate, e cosa succede quando ferma.

    Sta nel **Quality Gate**, dopo che i quattro sono verdi e prima del Critic: è la
    seconda domanda dello stesso gate — *i test passano?* e *sono mai stati rossi?* —
    e la sa una macchina come l'altra. Ferma vuol dire `fermato` **subito**: il ciclo
    mancato è *ex ante* e nessuna fix lo annulla, quindi rimandare il Builder a
    correggere sarebbe spendere una revisione su una cosa che non si corregge.
    """

    def _mondo(self, monkeypatch, mancati, critic=None):
        monkeypatch.setattr(
            runner, "git",
            lambda *a: ("2" if a[:2] == ("rev-list", "--count")
                        else elenco_backlog() if a[:2] == ("ls-tree", "--name-only")
                        else ""),
        )
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "pubblica", lambda branch: True)
        monkeypatch.setattr(
            runner, "revisione_critica", critic or (lambda p: runner.Verdetto("pass", "", "ok"))
        )
        monkeypatch.setattr(runner, "gate_del_rosso", mancati)

    def test_un_commit_senza_rosso_ferma_il_pbi_subito(self, monkeypatch):
        visto = {"critic": 0}

        def _critic(_p):
            visto["critic"] += 1
            return runner.Verdetto("pass", "", "ok")

        self._mondo(monkeypatch, lambda **k: [
            {"commit": "f35abd1", "titolo": "test: rimisura dal database",
             "test": "backend/tests/test_importa_storico.py::test_la_riga_12",
             "esito": "nato verde: a quel commit il test passa, il codice c'era già",
             "coda": ""},
        ], critic=_critic)

        esito = runner.esegui_pbi("PBI-103", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "fermato"
        assert "f35abd1" in esito.nota
        assert visto["critic"] == 0, (
            "il Critic è stato chiamato su un lavoro già fermo: sono minuti di modello "
            "spesi per farsi porre una domanda che il gate aveva già posto"
        )

    def test_lelenco_finisce_nel_rapporto_e_a_schermo(self, monkeypatch, capsys):
        """Commit, test, esito: il giro si chiude con l'elenco, e la lettura la fa
        una persona che non ha più il worktree sotto mano."""
        self._mondo(monkeypatch, lambda **k: [
            {"commit": "f35abd1", "titolo": "test: rimisura dal database",
             "test": "backend/tests/test_importa_storico.py::test_la_riga_12",
             "esito": "nato verde: a quel commit il test passa, il codice c'era già",
             "coda": "1 passed"},
        ])

        esito = runner.esegui_pbi("PBI-103", attivi=set(), dry=False, con_pr=False)

        assert [m["commit"] for m in esito.commit_senza_rosso] == ["f35abd1"]
        a_schermo = capsys.readouterr().out
        assert "gate del rosso" in a_schermo, "il log lo stampa come gli altri quattro"
        assert "f35abd1" in a_schermo and "nato verde" in a_schermo

    def test_il_suo_tempo_e_tempo_di_gate(self, monkeypatch):
        """Sta in `gate_s` perché è tempo di **macchina**, come pytest e vitest: la
        colonna del registro separa il modello dalla macchina, non i gate fra loro."""
        def _lento(**k):
            time.sleep(0.05)
            return []

        self._mondo(monkeypatch, _lento)

        esito = runner.esegui_pbi("PBI-103", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "fatto"
        assert esito.tempi["gate"] >= 0.05
        assert runner.riga_di_registro("r", {"pbi": "PBI-103", "stato": "fatto",
                                             "tempi": dict(esito.tempi)})["gate_s"] >= 0.05

    def test_al_secondo_giro_non_rigira_i_commit_gia_visti(self, monkeypatch):
        """Il gate sta dentro un ciclo che può ripetersi cinque volte: rigirare ogni
        volta la storia intera moltiplicherebbe il tempo macchina per le revisioni."""
        chiamate: list[set[str]] = []
        giri = {"critic": 0}

        def _gate(visti=None, **k):
            chiamate.append(set(visti))
            visti.add("abc1234")
            return []

        def _critic(_p):
            giri["critic"] += 1
            return runner.Verdetto("non pronto" if giri["critic"] == 1 else "pass", "", "")

        self._mondo(monkeypatch, _gate, critic=_critic)

        assert runner.esegui_pbi("PBI-103", attivi=set(), dry=False, con_pr=False).stato == "fatto"
        assert chiamate == [set(), {"abc1234"}], (
            "il secondo giro ha riguardato i commit del primo"
        )

    def test_un_gate_guasto_chiude_rosso_con_la_ragione_vera(self, monkeypatch):
        """Un `pytest` fuori dal `PATH` non è un ciclo mancato.

        Senza distinguerli, il runner accusa il Builder di aver saltato il TDD su
        **tutti** i commit del branch insieme quando il guasto è un venv: è la
        diagnosi sbagliata sul rilievo più grave che sappia emettere, e chi legge il
        rapporto non ha modo di accorgersene. È la lezione del difetto 11, già
        scritta in `esegui`.
        """
        def _guasto(**k):
            raise runner.GuastoDelGate("comando non eseguibile: pytest")

        self._mondo(monkeypatch, _guasto)

        esito = runner.esegui_pbi("PBI-103", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "rosso", "un gate rotto è un gate rosso, non un TDD saltato"
        assert "pytest" in esito.nota
        assert "il rosso non si è mai visto" not in esito.nota
        assert esito.commit_senza_rosso == [], (
            "nessun commit è stato accusato: il gate non ha guardato niente"
        )

    def test_un_gate_verde_lascia_passare_al_critic(self, monkeypatch):
        interrogato: list[int] = []
        self._mondo(monkeypatch, lambda **k: interrogato.append(1) or [])

        assert runner.esegui_pbi("PBI-103", attivi=set(), dry=False, con_pr=False).stato == "fatto"
        assert interrogato, (
            "il gate non è stato nemmeno interrogato: un `fatto` che nessuno ha misurato"
        )


class TestIlGateDelRossoSiLanciaDaSolo:
    """`--gate-rosso <ref>`: il gate senza il giro intorno.

    Serve a due cose che il gate dentro il giro non dà: provarlo su un branch già
    chiuso — è così che si guarda `pbi/pbi-330` — e rileggere un `fermato` senza
    rifare mezz'ora di Builder.
    """

    def test_senza_argomento_guarda_head(self):
        assert runner.costruisci_parser().parse_args(["--gate-rosso"]).gate_rosso == "HEAD"
        assert runner.costruisci_parser().parse_args(
            ["--gate-rosso", "pbi/pbi-330"]).gate_rosso == "pbi/pbi-330"

    def test_non_esegue_nessun_pbi_e_torna_1_se_ferma(self, monkeypatch, capsys):
        monkeypatch.setattr(runner, "gate_del_rosso", lambda ref, **k: [
            {"commit": "f35abd1", "titolo": "test: rimisura dal database",
             "test": "backend/tests/test_importa_storico.py::test_la_riga_12",
             "esito": "nato verde: a quel commit il test passa, il codice c'era già",
             "coda": ""},
        ])
        monkeypatch.setattr(
            runner, "esegui_pbi", lambda *a, **k: pytest.fail("non esegue nessun PBI")
        )
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "--gate-rosso", "pbi/pbi-330"])

        assert runner.main() == 1
        assert "f35abd1" in capsys.readouterr().out

    def test_accetta_anche_un_intervallo(self, monkeypatch):
        """`BASE..REF`, perché un branch **già mergiato** non ha più commit fuori da
        `origin/main` — e la prova sul caso vero è esattamente lì. `pbi/pbi-330` è
        entrato in main il 31/08, mentre PBI-103 lo stava usando come prova."""
        visto: dict[str, str] = {}
        monkeypatch.setattr(
            runner, "gate_del_rosso",
            lambda base="origin/main", ref="HEAD", **k: visto.update(base=base, ref=ref) or [],
        )
        monkeypatch.setattr(
            sys, "argv", ["asdlc_runner", "--gate-rosso", "d2c084c..pbi/pbi-330"]
        )

        assert runner.main() == 0
        assert visto == {"base": "d2c084c", "ref": "pbi/pbi-330"}

    def test_un_guasto_non_si_confonde_con_un_ciclo_mancato(self, monkeypatch, capsys):
        """`2` e non `1`: chi lancia il gate a mano deve poter distinguere «il rosso
        non c'è stato» da «il gate non ha potuto guardare»."""
        def _guasto(**k):
            raise runner.GuastoDelGate("comando non eseguibile: pytest")

        monkeypatch.setattr(runner, "gate_del_rosso", _guasto)
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "--gate-rosso", "pbi/pbi-330"])

        assert runner.main() == 2
        assert "pytest" in capsys.readouterr().out

    def test_torna_0_quando_il_rosso_ce_stato(self, monkeypatch):
        monkeypatch.setattr(runner, "gate_del_rosso", lambda ref, **k: [])
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "--gate-rosso"])

        assert runner.main() == 0


class TestLaFaseDecideCosaSiPuoScrivere:
    """Il lucchetto ex ante: `PBI-104`.

    Il gate del rosso è un'autopsia — accerta a giro finito che un test è nato
    verde, quando non c'è più niente da correggere e l'ora è spesa. La stessa
    regola messa **prima** della scrittura non accerta: impedisce. Il Builder in
    `TEST_ONLY` non può toccare la produzione, quindi non può implementare ciò
    che nessun rosso gli ha chiesto; in `IMPL` non può toccare i test, quindi il
    verde non si ottiene ammorbidendo l'asserzione. Sono i due imbrogli
    simmetrici, e servono due lucchetti opposti.

    Fuori da un giro il file della fase non c'è e la guardia tace: le sessioni
    di una persona non se ne devono accorgere.
    """

    PAGINA = "frontend/src/pages/FoglioPage.tsx"
    PROVA = "frontend/src/pages/FoglioPage.test.tsx"

    def test_senza_fase_non_dice_niente(self):
        assert runner.guardia_di_fase(None, self.PAGINA) is None
        assert runner.guardia_di_fase(None, self.PROVA) is None

    def test_in_test_only_la_produzione_e_chiusa(self):
        ragione = runner.guardia_di_fase("TEST_ONLY", self.PAGINA)
        assert ragione is not None
        assert self.PAGINA in ragione

    def test_in_test_only_il_test_si_scrive(self):
        assert runner.guardia_di_fase("TEST_ONLY", self.PROVA) is None
        assert runner.guardia_di_fase("TEST_ONLY", "backend/tests/test_margine.py") is None

    def test_in_impl_il_test_e_in_sola_lettura(self):
        """L'imbroglio simmetrico: il verde ottenuto ammorbidendo l'asserzione."""
        ragione = runner.guardia_di_fase("IMPL", self.PROVA)
        assert ragione is not None
        assert self.PROVA in ragione

    def test_in_impl_la_produzione_si_scrive(self):
        assert runner.guardia_di_fase("IMPL", self.PAGINA) is None

    def test_la_spec_si_scrive_in_tutte_e_due_le_fasi(self):
        """`AGENTS.md`, SEMPRE: la spec si aggiorna nello stesso commit del codice.

        Un `.md` non è né test né produzione — è la stessa esclusione con cui il
        gate del rosso non ferma un commit di soli test con la sua spec.
        """
        for fase in ("TEST_ONLY", "IMPL"):
            assert runner.guardia_di_fase(fase, "specs/analisi-kpi/spec.md") is None

    def test_il_file_della_fase_non_lo_scrive_lagente(self):
        """Il permesso non si prende: lo dà `--chiedi-impl` sul rosso osservato."""
        for fase in ("TEST_ONLY", "IMPL"):
            ragione = runner.guardia_di_fase(fase, runner.FILE_DELLA_FASE)
            assert ragione is not None
            assert "non la decidi tu" in ragione

    def test_una_fase_che_non_si_conosce_chiude(self):
        """Si sbaglia dalla parte del blocco: un file di fase corrotto o scritto a
        metà non deve valere come «nessuna fase», o il lucchetto si apre da sé."""
        assert runner.guardia_di_fase("VERDE", self.PAGINA) is not None
        assert runner.guardia_di_fase("VERDE", self.PROVA) is not None


class TestLaFaseSiLeggeDalWorktree:
    """La fase è stato del giro, non del repository, e sta nel **git dir del
    worktree** — `git rev-parse --git-path asdlc-fase` — non nell'albero di
    lavoro. La guardia la trova da qualunque sottocartella, perché l'agente può
    aver cambiato cartella e `cwd` arriva da Claude Code così com'è: la risalita
    la fa git, non noi."""

    def test_la_fase_si_legge_dalla_radice(self, repo_di_prova):
        runner.percorso_della_fase(repo_di_prova.radice).write_text("TEST_ONLY\n")
        assert runner.fase_corrente(repo_di_prova.radice) == "TEST_ONLY"

    def test_la_fase_si_trova_da_una_sottocartella(self, repo_di_prova):
        runner.percorso_della_fase(repo_di_prova.radice).write_text("IMPL\n")
        sotto = repo_di_prova.radice / "frontend" / "src" / "pages"
        sotto.mkdir(parents=True)
        assert runner.fase_corrente(sotto) == "IMPL"

    def test_senza_file_non_ce_fase(self, repo_di_prova):
        assert runner.fase_corrente(repo_di_prova.radice) is None


class TestLaFaseStaFuoriDalWorktree:
    """Il lucchetto si spegneva da solo. `.asdlc-fase` stava nella radice
    dell'albero, protetto da `Edit`/`Write` ma non da un `rm` o da un
    `git clean -fdx` via Bash: nei due giri del 01/09 è sparito a metà, e da lì
    hook e `pre-commit` sono stati inerti **in silenzio** — la guardia tace quando
    il file non c'è, ed è giusto, ma «non c'è» non distingueva «nessun giro» da
    «il giro l'ha perso». Il file sta ora dove l'albero di lavoro non arriva: nel
    git dir **di quel worktree**, così la fase di `~/ada-run` non si accende
    nell'albero accanto.
    """

    def test_il_file_sta_nel_git_dir_e_non_nellalbero(self, repo_di_prova):
        percorso = runner.percorso_della_fase(repo_di_prova.radice)

        assert ".git" in percorso.parts
        assert not (repo_di_prova.radice / ".asdlc-fase").exists()

    def test_ogni_worktree_ha_la_sua_fase(self, repo_di_prova, tmp_path):
        altro = tmp_path / "altro"
        repo_di_prova._git("worktree", "add", "-q", str(altro), "HEAD")
        runner.percorso_della_fase(repo_di_prova.radice).write_text("IMPL\n")

        assert runner.fase_corrente(altro) is None, "la fase di un albero si è accesa nell'altro"
        assert runner.percorso_della_fase(altro) != runner.percorso_della_fase(repo_di_prova.radice)

    def test_git_clean_non_lo_porta_via(self, repo_di_prova):
        runner.apri_la_fase()
        repo_di_prova._git("clean", "-fdxq")

        assert runner.fase_corrente(repo_di_prova.radice) == runner.FASE_TEST_ONLY

    def test_senza_repository_non_ce_un_percorso_ne_una_fase(self, monkeypatch, tmp_path):
        """Sotto i test `git` è sostituito e torna la stringa vuota: `Path("")` è
        la cartella corrente, e lì non si scrive niente — e non si legge una fase."""
        monkeypatch.setattr(runner, "git", lambda *a: "")
        assert runner.percorso_della_fase(tmp_path) is None
        assert runner.fase_corrente(tmp_path) is None


class TestLHookChiedeAlRunnerSeSiPuoScrivere:
    """`--guardia-fase`: il ponte fra `PreToolUse` e la guardia.

    Claude Code passa allo script un JSON su stdin (`tool_name`, `tool_input`,
    `cwd`) e legge l'uscita: **solo `exit 2` blocca davvero**, e in
    `bypassPermissions` — cioè `--dangerously-skip-permissions`, come il runner
    lancia il Builder — il JSON con `permissionDecision: "deny"` non basta. Per
    questo la ragione va su stderr e l'uscita è 2.

    Il mestiere di classificare i percorsi resta in Python e non finisce in uno
    script di shell: `e_file_di_produzione` è la stessa funzione con cui il gate
    del rosso ferma un commit misto, e due copie della stessa regola divergono.
    """

    def _stdin(self, monkeypatch, **campi):
        dato = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {}}
        dato.update(campi)
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(dato)))
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "--guardia-fase"])

    def test_il_flag_esiste(self):
        assert runner.costruisci_parser().parse_args(["--guardia-fase"]).guardia_fase

    def test_blocca_con_2_e_scrive_la_ragione_su_stderr(self, monkeypatch, repo_di_prova, capsys):
        tmp_path = repo_di_prova.radice
        runner.percorso_della_fase(tmp_path).write_text("TEST_ONLY\n")
        self._stdin(monkeypatch, cwd=str(tmp_path),
                    tool_input={"file_path": str(tmp_path / "frontend/src/App.tsx")})

        assert runner.main() == 2
        assert "TEST_ONLY" in capsys.readouterr().err

    def test_lascia_passare_il_test_e_non_dice_niente(self, monkeypatch, repo_di_prova, capsys):
        tmp_path = repo_di_prova.radice
        runner.percorso_della_fase(tmp_path).write_text("TEST_ONLY\n")
        self._stdin(monkeypatch, cwd=str(tmp_path),
                    tool_input={"file_path": str(tmp_path / "frontend/src/App.test.tsx")})

        assert runner.main() == 0
        assert capsys.readouterr().err == ""

    def test_uno_strumento_senza_percorso_non_lo_riguarda(self, monkeypatch, repo_di_prova):
        """Il matcher è `Edit|Write`, ma la guardia non si fida del matcher."""
        tmp_path = repo_di_prova.radice
        runner.percorso_della_fase(tmp_path).write_text("TEST_ONLY\n")
        self._stdin(monkeypatch, cwd=str(tmp_path), tool_name="Bash",
                    tool_input={"command": "npm test"})

        assert runner.main() == 0

    def test_un_json_rotto_non_blocca_la_sessione(self, monkeypatch, capsys):
        """Si sbaglia dalla parte del passaggio, ed è l'unico posto dove si fa.

        Un hook che esce 2 su un guasto proprio blocca **ogni** scrittura di ogni
        sessione del repository, e la cura sarebbe modificare un file — cioè
        proprio ciò che ha appena vietato. Il confine duro non è qui: è il
        `pre-commit`, che nessuna tool call aggira.
        """
        monkeypatch.setattr(sys, "stdin", io.StringIO("{non è json"))
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "--guardia-fase"])

        assert runner.main() == 0
        assert "guardia" in capsys.readouterr().err


class TestLHookERegistratoEFerma:
    """Lo script e la sua registrazione, provati sul file vero.

    Il resto della suite gira senza toccare il mondo; qui no, e apposta: un hook
    che non è eseguibile, o registrato con un matcher sbagliato, non dà nessun
    errore — semplicemente non scatta, e il lucchetto sembra esserci senza
    esserci. È lo stesso motivo per cui i gate si dichiarano prima di partire.
    """

    SCRIPT = REPO / ".claude" / "hooks" / "fase-tdd.sh"
    IMPOSTAZIONI = REPO / ".claude" / "settings.json"

    def test_lo_script_ce_ed_e_eseguibile(self):
        assert self.SCRIPT.is_file()
        assert os.access(self.SCRIPT, os.X_OK), "un hook non eseguibile non scatta e non lo dice"

    def test_e_registrato_su_pretooluse_per_edit_e_write(self):
        registrate = json.loads(self.IMPOSTAZIONI.read_text())["hooks"]["PreToolUse"]
        voci = [v for v in registrate if v.get("matcher") == "Edit|Write"]
        assert voci, "senza matcher Edit|Write l'hook non vede le scritture"
        comandi = [h["command"] for v in voci for h in v["hooks"]]
        assert any("fase-tdd.sh" in c for c in comandi)

    def test_ferma_la_produzione_in_test_only(self, repo_di_prova):
        tmp_path = repo_di_prova.radice
        runner.percorso_della_fase(tmp_path).write_text("TEST_ONLY\n")
        dato = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(tmp_path),
                "tool_input": {"file_path": str(tmp_path / "frontend/src/App.tsx")}}

        esito = subprocess.run([str(self.SCRIPT)], input=json.dumps(dato),
                               capture_output=True, text=True, cwd=tmp_path)

        assert esito.returncode == 2, esito.stderr
        assert "TEST_ONLY" in esito.stderr

    def test_fuori_da_un_giro_non_dice_niente(self, tmp_path):
        dato = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(tmp_path),
                "tool_input": {"file_path": str(tmp_path / "frontend/src/App.tsx")}}

        esito = subprocess.run([str(self.SCRIPT)], input=json.dumps(dato),
                               capture_output=True, text=True, cwd=tmp_path)

        assert esito.returncode == 0
        assert esito.stderr == ""


class TestIlPermessoDiImplementareSiChiede:
    """`--chiedi-impl`: l'unico modo di passare da `TEST_ONLY` a `IMPL`.

    È il cardine del lucchetto. L'agente può **chiedere** il permesso di scrivere
    codice di produzione, non prenderselo: il runner gira i test che sono nati
    nell'albero e apre la fase solo se li vede fallire. Un test che passa al
    primo colpo non è un permesso negato per pignoleria — è la prova che quel
    comportamento c'è già, e che non è questo il commit in cui nasce.

    Il rosso si osserva **prima** del commit, quindi il commit di soli test che
    ne segue è per costruzione quello che il gate di PBI-103 vorrebbe: nessun
    file di produzione dentro, e il fallimento visto sull'albero esatto.
    """

    TEST_NUOVO = "backend/tests/test_foglio.py"
    SORGENTE = "def test_il_clic_apre_la_pratica():\n    assert False\n"

    def _in_test_only(self, repo, monkeypatch, esito="rosso"):
        runner.percorso_della_fase(repo.radice).write_text(f"{runner.FASE_TEST_ONLY}\n")
        (repo.radice / self.TEST_NUOVO).write_text(self.SORGENTE, encoding="utf-8")
        monkeypatch.setattr(runner, "esiti_del_comando",
                            lambda c: ({k: esito for k in c.etichette}, "coda"))
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "--chiedi-impl"])

    def _fase(self, repo):
        return runner.percorso_della_fase(repo.radice).read_text().strip()

    def test_il_flag_chiedi_impl_esiste(self):
        assert runner.costruisci_parser().parse_args(["--chiedi-impl"]).chiedi_impl

    def test_apre_la_fase_quando_il_test_nuovo_e_rosso(self, repo_di_prova, monkeypatch):
        self._in_test_only(repo_di_prova, monkeypatch)

        assert runner.main() == 0
        assert self._fase(repo_di_prova) == runner.FASE_IMPL

    def test_non_apre_su_un_test_nato_verde(self, repo_di_prova, monkeypatch, capsys):
        self._in_test_only(repo_di_prova, monkeypatch, esito="verde")

        assert runner.main() == 1
        assert self._fase(repo_di_prova) == runner.FASE_TEST_ONLY
        assert runner.ESITI_MANCATI["verde"] in capsys.readouterr().out

    def test_non_apre_se_il_rosso_non_e_isolabile(self, repo_di_prova, monkeypatch, capsys):
        """Il caso del 31/08: il test non gira perché importa ciò che non c'è.

        Si chiude come il verde, ma la ragione è un'altra e va detta: la cura non
        è cambiare il test, è far esistere il modulo vuoto prima.
        """
        self._in_test_only(repo_di_prova, monkeypatch, esito="nessuno")

        assert runner.main() == 1
        assert runner.ESITI_MANCATI["nessuno"] in capsys.readouterr().out

    def test_senza_test_nuovi_non_apre(self, repo_di_prova, monkeypatch, capsys):
        runner.percorso_della_fase(repo_di_prova.radice).write_text(f"{runner.FASE_TEST_ONLY}\n")
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "--chiedi-impl"])

        assert runner.main() == 1
        assert self._fase(repo_di_prova) == runner.FASE_TEST_ONLY
        assert "nessun test nuovo" in capsys.readouterr().out

    def test_fuori_da_test_only_non_si_chiede(self, repo_di_prova, monkeypatch, capsys):
        """Da `IMPL` la richiesta non ha senso, e riaprirla sarebbe il modo di
        restarci per sempre: un giro che non torna mai a `TEST_ONLY` è un giro
        senza lucchetto."""
        runner.percorso_della_fase(repo_di_prova.radice).write_text(f"{runner.FASE_IMPL}\n")
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "--chiedi-impl"])

        assert runner.main() == 1
        assert runner.FASE_TEST_ONLY in capsys.readouterr().out


class TestITestNuoviSiLeggonoDallAlbero:
    """Il gate di PBI-103 legge i test nuovi da un **commit**; il lucchetto deve
    leggerli da ciò che non è ancora committato, perché il permesso si chiede
    prima del commit. Un file di test appena creato non è tracciato, e
    `git diff HEAD` non lo nomina: va cercato apposta, o il caso più comune —
    il primo test di un modulo nuovo — non verrebbe visto affatto."""

    def test_vede_un_file_di_test_non_tracciato(self, repo_di_prova):
        (repo_di_prova.radice / "backend/tests/test_nuovo.py").write_text(
            "def test_la_riga_si_apre():\n    assert False\n", encoding="utf-8")

        nuovi = runner.test_nuovi_dellalbero()

        assert [(t.file, t.nome) for t in nuovi] == [
            ("backend/tests/test_nuovo.py", "test_la_riga_si_apre")]

    def test_vede_un_test_aggiunto_a_un_file_che_ce_gia(self, repo_di_prova):
        repo_di_prova.commit("test: il primo", {
            "backend/tests/test_c_era.py": "def test_il_primo():\n    assert True\n"})
        (repo_di_prova.radice / "backend/tests/test_c_era.py").write_text(
            "def test_il_primo():\n    assert True\n\n\ndef test_il_secondo():\n    assert False\n",
            encoding="utf-8")

        assert [t.nome for t in runner.test_nuovi_dellalbero()] == ["test_il_secondo"]

    def test_la_produzione_non_e_un_test(self, repo_di_prova):
        (repo_di_prova.radice / "backend/app/foglio.py").write_text("def calcola():\n    pass\n")

        assert runner.test_nuovi_dellalbero() == []


class TestIlCommitNonNasceFuoriFase:
    """Il confine che nessuna tool call aggira.

    L'hook `PreToolUse` guarda `Edit` e `Write`, e un agente a cui la scrittura
    viene negata ha una via laterale ovvia: `cat > pagina.tsx <<'EOF'` da Bash.
    Filtrare i comandi di shell a colpi di regex è una guerra che si perde, così
    il confine duro sta dove nessuno strumento arriva — il `pre-commit` di git,
    che vede ciò che è **in stage** e non come ci è finito.

    I due livelli hanno mestieri diversi e servono tutti e due: l'hook è veloce e
    spiega mentre l'agente scrive, il `pre-commit` è invalicabile e arriva tardi.
    """

    def _stage(self, repo, percorso, contenuto="x = 1\n"):
        f = repo.radice / percorso
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(contenuto, encoding="utf-8")
        repo._git("add", percorso)

    def test_ferma_il_commit_con_produzione_in_test_only(self, repo_di_prova, monkeypatch, capsys):
        runner.percorso_della_fase(repo_di_prova.radice).write_text(f"{runner.FASE_TEST_ONLY}\n")
        self._stage(repo_di_prova, "backend/app/foglio.py")
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "--guardia-commit"])

        assert runner.main() == 1
        assert "backend/app/foglio.py" in capsys.readouterr().out

    def test_lascia_passare_il_commit_di_soli_test(self, repo_di_prova, monkeypatch):
        runner.percorso_della_fase(repo_di_prova.radice).write_text(f"{runner.FASE_TEST_ONLY}\n")
        self._stage(repo_di_prova, "backend/tests/test_foglio.py", "def test_x():\n    pass\n")
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "--guardia-commit"])

        assert runner.main() == 0

    def test_fuori_da_un_giro_non_guarda_niente(self, repo_di_prova, monkeypatch):
        self._stage(repo_di_prova, "backend/app/foglio.py")
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "--guardia-commit"])

        assert runner.main() == 0

    def test_il_pre_commit_si_installa_e_non_calpesta_quello_che_ce(self, repo_di_prova):
        """Installarlo è del runner, non di chi lancia: un lucchetto che dipende da
        un gesto ricordato a mano è un lucchetto che a un certo punto non c'è."""
        runner.installa_la_guardia_del_commit()
        hook = repo_di_prova.radice / ".git" / "hooks" / "pre-commit"

        assert hook.is_file() and os.access(hook, os.X_OK)
        assert "--guardia-commit" in hook.read_text()

        hook.write_text("#!/bin/sh\n# di qualcun altro\n", encoding="utf-8")
        runner.installa_la_guardia_del_commit()
        assert "di qualcun altro" in hook.read_text()


class TestOgniCommitRiportaAllaFaseDelTest:
    """Il ciclo si chiude da sé, o il lucchetto vale una volta sola.

    Il Builder fa molti criteri in una sessione, e fra un commit e l'altro il
    runner non c'è: se `IMPL` restasse aperta dopo il primo permesso, il secondo
    comportamento tornerebbe a nascere senza rosso e avremmo speso tutto questo
    per un criterio solo. Chi vede ogni commit è git, quindi è git a riportare
    la fase indietro — `post-commit`, subito dopo che il commit è nato.
    """

    def test_il_post_commit_riporta_in_test_only(self, repo_di_prova):
        runner.percorso_della_fase(repo_di_prova.radice).write_text(f"{runner.FASE_IMPL}\n")
        runner.installa_il_ritorno_in_test_only()
        hook = repo_di_prova.radice / ".git" / "hooks" / "post-commit"

        assert hook.is_file() and os.access(hook, os.X_OK)
        repo_di_prova.commit("feat: il minimo che fa passare il test",
                             {"backend/app/foglio.py": "def calcola():\n    return 1\n"})

        assert runner.percorso_della_fase(repo_di_prova.radice).read_text().strip() == \
            runner.FASE_TEST_ONLY

    def test_fuori_da_un_giro_il_post_commit_non_crea_niente(self, repo_di_prova):
        runner.installa_il_ritorno_in_test_only()
        repo_di_prova.commit("chore: un commit di una persona", {"README.md": "ciao\n"})

        assert not runner.percorso_della_fase(repo_di_prova.radice).exists()


class TestIlGiroSiApreInTestOnly:
    """Il lucchetto si accende con il giro e si spegne con lui: un worktree
    lasciato in fase è un worktree in cui la sessione dopo non può scrivere, e la
    diagnosi costerebbe più del giro."""

    def test_apri_la_fase_installa_gli_hook_e_scrive_test_only(self, repo_di_prova):
        runner.apri_la_fase()

        assert runner.percorso_della_fase(repo_di_prova.radice).read_text().strip() == \
            runner.FASE_TEST_ONLY
        assert (repo_di_prova.radice / ".git" / "hooks" / "pre-commit").is_file()
        assert (repo_di_prova.radice / ".git" / "hooks" / "post-commit").is_file()

    def test_chiudi_la_fase_toglie_il_file(self, repo_di_prova):
        runner.apri_la_fase()
        runner.chiudi_la_fase()

        assert not runner.percorso_della_fase(repo_di_prova.radice).exists()

    def test_chiudere_due_volte_non_e_un_errore(self, repo_di_prova):
        runner.chiudi_la_fase()
        runner.chiudi_la_fase()

    def test_il_giro_apre_la_fase_e_la_chiude(self, tmp_path, monkeypatch):
        """Il PBI non si esegue mai senza lucchetto: aprirlo è del runner."""
        visto: dict[str, object] = {}
        monkeypatch.setattr(runner, "trova_pbi", lambda pbi: tmp_path / "backlog" / f"{pbi}.md")
        monkeypatch.setattr(runner, "REPO", tmp_path)
        monkeypatch.setattr(runner, "git", lambda *a: "")
        monkeypatch.setattr(runner, "crea_branch", lambda pbi: f"pbi/{pbi.lower()}")
        monkeypatch.setattr(runner, "apri_la_fase", lambda: visto.__setitem__("aperta", True))
        monkeypatch.setattr(runner, "chiudi_la_fase", lambda: visto.__setitem__("chiusa", True))
        monkeypatch.setattr(runner, "esegui",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("basta")))

        with pytest.raises(RuntimeError):
            runner.esegui_pbi("PBI-333", set(), dry=False, con_pr=False)

        assert visto.get("aperta"), "il giro deve aprire la fase prima del Builder"


class TestIlBuilderSaComeSiApreLaProduzione:
    """Il lucchetto senza le istruzioni è una porta chiusa senza cartello.

    Un agente che trova l'edit negato e non sa che esiste `--chiedi-impl` fa la
    cosa che farebbe chiunque: ci riprova da un'altra strada — un heredoc da
    Bash, `sed -i` — e finisce contro il `pre-commit` dopo aver speso il turno.
    Il blocco deve costare secondi, non un giro, e la differenza è tutta scritta
    qui dentro.
    """

    def _prompt(self):
        return runner.PROMPT_BUILDER.format(pbi_path="backlog/PBI-333-il-foglio.md")

    def test_dice_il_nome_del_comando_che_apre_la_fase(self):
        assert "--chiedi-impl" in self._prompt()

    def test_dice_che_si_scrive_solo_il_minimo(self):
        """La causa a monte di PBI-333: 494 righe di pagina con dentro un
        comportamento che nessun rosso aveva chiesto. «Il codice che lo fa
        passare» non è «solo il codice che lo fa passare»."""
        prompt = self._prompt()
        assert "solo il codice" in prompt or "il minimo" in prompt

    def test_dice_come_far_nascere_un_modulo_senza_rompere_il_rosso(self):
        """L'altra fermata, quella del 31/08: il primo test di un modulo che non
        esiste non fallisce, esplode in raccolta. Lo scheletro vuoto prima."""
        assert "scheletro" in self._prompt()

    def test_dice_che_una_guardia_nata_verde_passa_solo_se_morde(self):
        """Il Critic ordina guardie su comportamenti che ci sono già, e il Builder
        le scrive: nascono verdi per forza. Il prompt deve dire che è lecito, e
        a che condizione — il gate le rigira contro i mutanti delle righe del
        branch, e passa solo quella che se ne accorge (PBI-105)."""
        prompt = self._prompt()
        assert "guardia" in prompt
        assert "morde" in prompt
        assert "mutant" in prompt

    def test_non_promette_piu_un_numero_di_commit_scollegato_dai_criteri(self):
        """«3-5 commit» su un PBI da otto criteri è un invito ad accorpare, ed è
        aritmetica: due o tre coppie non coprono otto comportamenti."""
        assert "3-5" not in self._prompt(), "il testo va a capo: il numero si cerca da solo"


class TestUnNomeDiTestAmbiguoNonSiIndovina:
    """Trovato addosso a se stesso: il gate del rosso girato su questa PR.

    `id_pytest` tornava il **primo** metodo con quel nome trovato nel file. Due
    classi che definiscono un test omonimo — cosa normale, `test_il_flag_esiste`
    esiste già due volte in questa suite da prima di oggi — e il gate esegue il
    test sbagliato: quello vecchio, che a quel commit passa. Verdetto *nato
    verde* su un test che era rosso davvero.

    Non è il caso «il gate è troppo severo»: è un gate che dice una cosa falsa
    con la stessa faccia con cui dice le vere, ed è peggio. In caso di dubbio
    ferma e lo dice — la regola c'è già per i test generati e per quelli dentro
    un `if`, e questo è lo stesso dubbio.
    """

    # `def ` sta fuori dalla stringa apposta: `nomi_dei_test` legge i nomi dal
    # **testo del diff**, quindi un `def test_…` dentro un letterale conterebbe
    # come test nato in questo commit. Il gate del rosso di questa stessa PR ci è
    # cascato: ha eseguito un omonimo vero, l'ha trovato verde, e ha fermato il
    # branch per un test che qui non esiste. Il difetto è suo e resta scritto in
    # PBI-104; questa riga evita di darglielo in pasto.
    DEF = "def "
    SORGENTE = f"""
class TestVecchia:
    {DEF}test_omonimo(self):
        pass


class TestNuova:
    {DEF}test_omonimo(self):
        pass
"""

    def test_due_classi_con_lo_stesso_nome_non_danno_un_id(self):
        assert runner.id_pytest(self.SORGENTE, "test_omonimo", "tests/test_x.py") is None

    def test_anche_una_funzione_fuori_classe_conta_come_omonima(self):
        sorgente = self.SORGENTE + f"\n\n{self.DEF}test_omonimo():\n    pass\n"
        assert runner.id_pytest(sorgente, "test_omonimo", "tests/test_x.py") is None


class TestSenzaUnRepositorySottoNonSiApreNiente:
    """Il lucchetto non scrive dove non c'è un giro.

    Trovato dalla suite stessa: `apri_la_fase` è entrato in `esegui_pbi`, e le
    decine di test che eseguono un PBI con `git` sostituito hanno cominciato a
    lasciare `pre-commit` e `post-commit` **nella radice del repository vero** —
    `git rev-parse --git-path hooks` tornava la stringa vuota del doppio, e
    `Path("")` è la cartella corrente. Con `.asdlc-fase` sarebbe stato peggio:
    un albero lasciato in fase è un albero in cui la sessione dopo non scrive.

    Un dubbio su dove si sta scrivendo si risolve non scrivendo.
    """

    def test_un_percorso_che_non_finisce_in_hooks_non_e_una_cartella_di_hook(self, monkeypatch):
        monkeypatch.setattr(runner, "git", lambda *a: "")
        assert runner.cartella_degli_hook() is None

    def test_apri_la_fase_non_scrive_niente_senza_hook(self, monkeypatch, tmp_path):
        monkeypatch.setattr(runner, "REPO", tmp_path)
        monkeypatch.setattr(runner, "git", lambda *a: "")

        runner.apri_la_fase()

        assert list(tmp_path.iterdir()) == []


class TestIlPermessoSiChiedeAncheDopoIlCommitRed:
    """Il buco trovato al primo giro vero, il 01/09 alle 15:09.

    `--chiedi-impl` guardava solo i test **non committati**, e il ciclo non si
    chiudeva: il commit RED — che la convenzione del progetto vuole, e che il
    gate del rosso pretende di soli test — rendeva la richiesta cieca. L'unica
    via rimasta era non committare il RED, aprire `IMPL` e scoprire che lì il
    `pre-commit` vieta di mettere in stage un file di test: il commit del test
    non poteva più nascere, e la storia sarebbe uscita `feat` prima e `test`
    dopo. Nata verde, cioè la cosa che tutto questo esiste per impedire.

    Il Builder se n'è accorto da solo e ha chiesto con `STOP:` — 12 minuti,
    zero commit, nessun danno.

    Si guarda **l'ultimo commit e basta**, non tutto `origin/main..HEAD`: dopo
    tre criteri i test dei primi due sono verdi, e la richiesta verrebbe
    rifiutata per «nato verde» su lavoro già dimostrato.
    """

    TEST = "backend/tests/test_foglio.py"
    ROSSO = "def test_il_clic_apre_la_pratica():\n    assert False\n"

    def _chiedi(self, repo, monkeypatch, esito="rosso"):
        runner.percorso_della_fase(repo.radice).write_text(f"{runner.FASE_TEST_ONLY}\n")
        monkeypatch.setattr(runner, "esiti_del_comando",
                            lambda c: ({k: esito for k in c.etichette}, "coda"))
        monkeypatch.setattr(sys, "argv", ["asdlc_runner", "--chiedi-impl"])

    def _fase(self, repo):
        return runner.percorso_della_fase(repo.radice).read_text().strip()

    def test_apre_sul_commit_di_soli_test_appena_fatto(self, repo_di_prova, monkeypatch):
        repo_di_prova.commit("test(analisi): il clic apre la pratica (RED)", {self.TEST: self.ROSSO})
        self._chiedi(repo_di_prova, monkeypatch)

        assert runner.main() == 0
        assert self._fase(repo_di_prova) == runner.FASE_IMPL

    def test_non_apre_se_lultimo_commit_porta_anche_produzione(self, repo_di_prova, monkeypatch, capsys):
        """Un commit misto non è un RED: il rosso non può essere esistito in mezzo."""
        repo_di_prova.commit("feat: la pagina e il suo test", {
            self.TEST: self.ROSSO, "backend/app/foglio.py": "def calcola():\n    pass\n"})
        self._chiedi(repo_di_prova, monkeypatch)

        assert runner.main() == 1
        assert "nessun test nuovo" in capsys.readouterr().out

    def test_non_guarda_un_commit_che_e_gia_su_origin_main(self, repo_di_prova, monkeypatch, capsys):
        """Il branch nasce da `origin/main`: se lì l'ultimo commit fosse di soli
        test, la fase si aprirebbe senza che questo giro abbia scritto niente."""
        repo_di_prova.commit("test(analisi): un test di qualcun altro", {self.TEST: self.ROSSO})
        repo_di_prova._git("update-ref", "refs/remotes/origin/main", "HEAD")
        self._chiedi(repo_di_prova, monkeypatch)

        assert runner.main() == 1
        assert "nessun test nuovo" in capsys.readouterr().out


class TestIlPromptDiceDiCommittareIlRossoPrima:
    """L'ordine dei passi è la metà del lucchetto.

    Il prompt descriveva quattro passi — scrivi il test, chiedi, scrivi il
    codice, committa — e in quell'ordine il commit RED non esiste: il test entra
    in storia insieme al `feat`, cioè in un commit misto che il gate ferma. Il
    Builder del 01/09 ha seguito il prompt alla lettera ed è finito contro il
    muro dopo dodici minuti.
    """

    def test_il_commit_del_rosso_viene_prima_della_richiesta(self):
        prompt = runner.PROMPT_BUILDER.format(pbi_path="backlog/PBI-333-il-foglio.md")
        posto_del_commit = prompt.index("(RED)`")
        posto_della_richiesta = prompt.index("--chiedi-impl")
        assert posto_del_commit < posto_della_richiesta, (
            "il prompt deve dire di committare il RED prima di chiedere il permesso"
        )


class TestIlBuilderGiraDoveGliHookScattano:
    """Misurato il 01/09: `--dangerously-skip-permissions` **non chiama gli hook**.

    La documentazione di Claude Code dice il contrario — in `bypassPermissions`
    *«hooks remain active and can block via exit 2»* — e su questa versione è
    falso: l'hook non viene invocato affatto, in silenzio, che è il modo peggiore
    di non funzionare. Provato su un repo apposta, quattro modalità:

    | modalità                          | Bash | hook | scrittura fuori fase |
    |-----------------------------------|------|------|----------------------|
    | `--dangerously-skip-permissions`  | sì   | no   | **passa**            |
    | `--permission-mode auto`          | sì   | no   | **passa**            |
    | `--permission-mode dontAsk`       | no   | sì   | bloccata             |
    | `acceptEdits`                     | no   | sì   | bloccata             |
    | `acceptEdits` + `--allowedTools Bash` | sì | sì | bloccata             |

    L'ultima riga è l'unica in cui il Builder può lavorare **e** il lucchetto
    esiste: le modifiche ai file sono accettate senza chiedere, ma passano
    dall'hook; `Bash` è permesso per nome, e senza quel permesso gira in una
    sandbox che non scrive fuori dalla working directory.
    """

    def test_non_gira_nella_modalita_che_spegne_gli_hook(self):
        assert "--dangerously-skip-permissions" not in runner.BUILDER, (
            "in bypassPermissions l'hook di fase non viene chiamato: il lucchetto non c'è"
        )

    def test_gira_dove_gli_hook_scattano_e_bash_funziona(self):
        assert "acceptEdits" in runner.BUILDER
        assert "Bash" in runner.BUILDER

    def test_allowedtools_non_e_in_coda(self):
        """`--allowedTools` è variadico: in coda si mangia il prompt, che il
        runner concatena subito dopo, e `-p` parte senza input. È la stessa
        trappola annotata per il Critic."""
        assert "--allowedTools" in runner.BUILDER
        assert runner.BUILDER.index("--allowedTools") < len(runner.BUILDER) - 2


class TestIMutantiSiFannoDalleRigheCambiate:
    """La quarta lettura del gate: `PBI-105`.

    Un test nato verde non prova niente **se non morde**. La domanda giusta non è
    «è mai stato rosso?» ma «se guasto il codice che copre, se ne accorge?» — e la
    seconda si misura, mentre la prima è una prova di processo che due giri su
    quattro ha ucciso lavoro buono.

    I mutanti si fanno sulle **righe che il branch ha cambiato**, non su tutto il
    file: è il codice che quel giro ha scritto, ed è l'unico di cui i suoi test
    devono rispondere. La cancellazione della riga è l'operatore più forte e vale
    in tutti e due i linguaggi; gli scambi servono dove togliere la riga non
    cambia niente di osservabile.
    """

    def test_cancella_la_riga_cambiata(self):
        sorgente = "def calcola():\n    x = 1\n    return x\n"
        mutanti = runner.mutanti_del_sorgente(sorgente, {2})

        assert ("    x = 1", "") in [(m.prima, m.dopo) for m in mutanti]

    def test_scambia_gli_operatori_di_confronto(self):
        sorgente = "  const senza = soglia.valore === null\n"
        dopo = [m.dopo for m in runner.mutanti_del_sorgente(sorgente, {1})]

        assert "  const senza = soglia.valore !== null" in dopo

    def test_scambia_la_congiunzione(self):
        dopo = [m.dopo for m in runner.mutanti_del_sorgente("  if (a && b) return\n", {1})]

        assert "  if (a || b) return" in dopo

    def test_non_muta_le_righe_che_il_branch_non_ha_toccato(self):
        sorgente = "  const a = 1 === 2\n  const b = 3 === 4\n"
        mutanti = runner.mutanti_del_sorgente(sorgente, {1})

        assert all(m.riga == 1 for m in mutanti)

    def test_una_riga_di_sola_parentesi_non_e_un_mutante(self):
        """Cancellarla rompe la sintassi e basta: il file non compila, nessun test
        gira, e un guasto di forma non è una prova che il test morda."""
        assert runner.mutanti_del_sorgente("}\n", {1}) == []


class TestGliScambiValgonoInTuttiEDueILinguaggi:
    """Il gate giudica pytest e vitest con la stessa regola, e i mutanti devono
    saper guastare tutti e due i lati: `==`/`and`/`True` in Python valgono quanto
    `===`/`&&`/`true` in TypeScript. Il confronto d'ordine — `<` che diventa `<=` —
    è il guasto di confine, quello che un test scritto sul caso «giusto» non vede.
    """

    def _dopo(self, riga: str) -> list[str]:
        return [m.dopo for m in runner.mutanti_del_sorgente(riga + "\n", {1})]

    def test_scambia_uguale_e_diverso_di_python(self):
        """E `===` ha già il suo scambio: leggerlo anche come `==` darebbe `!===`,
        che non compila e non prova niente."""
        assert "    if a != b:" in self._dopo("    if a == b:")
        assert "    if a == b:" in self._dopo("    if a != b:")
        assert self._dopo("  const c = a === b") == ["", "  const c = a !== b"]

    def test_scambia_and_e_or(self):
        assert "    if a or b:" in self._dopo("    if a and b:")
        assert "    if a and b:" in self._dopo("    if a or b:")

    def test_scambia_vero_e_falso(self):
        assert "    aperto = False" in self._dopo("    aperto = True")
        assert "  const aperto = false" in self._dopo("  const aperto = true")

    def test_scambia_il_confronto_di_confine(self):
        assert "    if a <= b:" in self._dopo("    if a < b:")
        assert "    if a < b:" in self._dopo("    if a <= b:")
        assert "  if (a >= b) return" in self._dopo("  if (a > b) return")
        assert "  if (a > b) return" in self._dopo("  if (a >= b) return")

    def test_la_freccia_non_e_un_confronto(self):
        """`=>` e `->` contengono un `>` che non decide niente."""
        assert self._dopo("  const f = (x) => x") == [""]
        assert self._dopo("def f() -> int:") == []

    def test_una_riga_di_commento_non_si_cancella(self):
        assert self._dopo("    # la somma") == []
        assert self._dopo("  // la somma") == []

    def test_una_riga_che_apre_un_blocco_non_si_cancella(self):
        """Senza il `def` la riga dopo è un'indentazione senza padrone, e senza la
        `{` il file non chiude: sono guasti di forma, e vanno solo a tempo perso."""
        assert self._dopo("def somma(a, b):") == []
        assert self._dopo("export function somma(a: number, b: number) {") == []
        assert self._dopo("  const voci = NAV_ITEMS.filter(") == []


class TestLeRigheCambiateSiLeggonoDalDiff:
    """Quali righe si mutano: quelle di produzione che il branch ha cambiato **fino a
    quel commit**, nella numerazione del file a quel commit — è lì che il test
    nato verde viene rigirato, e un numero di riga preso altrove guasterebbe la
    riga sbagliata."""

    def test_le_righe_nuove_di_un_file_nuovo_e_quelle_toccate_di_uno_vecchio(
        self, repo_di_prova
    ):
        vecchio = repo_di_prova.commit("feat: la differenza", {
            "backend/app/differenza.py":
                "def differenza(a, b):\n    return a - b\n\n\ndef zero():\n    return 0\n",
        })
        repo_di_prova._git("update-ref", "refs/remotes/origin/main", vecchio)
        sha = repo_di_prova.commit("feat: la somma, e lo zero che diventa uno", {
            "backend/app/somma.py": "def somma(a, b):\n    return a + b\n",
            "backend/app/differenza.py":
                "def differenza(a, b):\n    return a - b\n\n\ndef zero():\n    return 1\n",
        })

        righe = runner.righe_cambiate("origin/main", sha)

        assert righe == {"backend/app/somma.py": {1, 2},
                         "backend/app/differenza.py": {6}}

    def test_i_test_i_documenti_e_le_sole_cancellazioni_non_contano(self, repo_di_prova):
        """Si muta la produzione: un test non è ciò che il test guarda, un `.md`
        non gira, e una riga tolta non c'è più da guastare."""
        vecchio = repo_di_prova.commit("feat: la somma, con una riga di troppo", {
            "backend/app/somma.py": "def somma(a, b):\n    c = 0\n    return a + b\n",
        })
        repo_di_prova._git("update-ref", "refs/remotes/origin/main", vecchio)
        sha = repo_di_prova.commit("refactor: togli la riga di troppo", {
            "backend/app/somma.py": "def somma(a, b):\n    return a + b\n",
            "backend/tests/test_somma.py": "def test_x():\n    assert True\n",
            "docs/somma.md": "# la somma\n",
        })

        assert runner.righe_cambiate("origin/main", sha) == {}


class TestIlTestNatoVerdePassaSeMorde:
    """PBI-105, la quarta lettura: *se guasto il codice che copre, se ne accorge?*

    «Nato verde» è una prova di processo con un falso positivo sistematico: la
    guardia che il Critic ordina su un comportamento che c'è già nasce verde per
    forza, e su PBI-333 ha chiuso due giri su quattro. Prima di fermare, il gate
    muta le righe di produzione che il branch ha cambiato e rigira **quel test**:
    un mutante ucciso è la prova che il test guarda quelle righe.
    """

    def test_una_guardia_che_uccide_un_mutante_passa_e_il_gate_dice_quale(
        self, repo_di_prova, tmp_path
    ):
        """Il caso di `9f952c0`: il test nasce verde, e cancellata la riga che
        somma si accorge che il totale non c'è più.

        Tre righe e non due: con `return a + b` da solo l'unico mutante è il `def`
        vuoto, che non compila e non si prova — e una guardia che non ha mutanti
        da uccidere non è il caso di questo test."""
        repo_di_prova.commit("feat: la somma", {
            "backend/app/somma.py":
                "def somma(a, b):\n    totale = a + b\n    return totale\n",
        })
        sha = repo_di_prova.commit("test: la somma fa due", {
            "backend/tests/test_somma.py": sorgente_che_lascia_un_segno(
                tmp_path / "girato", "from app.somma import somma\n    assert somma(1, 1) == 2"),
        })
        morsi: list[dict[str, str]] = []

        assert runner.gate_del_rosso(morsi=morsi) == []
        assert [m["commit"] for m in morsi] == [sha[:7]]
        assert morsi[0]["test"] == "tests/test_somma.py::test_la_somma_fa_due"
        assert "backend/app/somma.py:2" in morsi[0]["mutante"]
        assert "totale = a + b" in morsi[0]["mutante"]
        assert "riga cancellata" in morsi[0]["mutante"]

    def test_una_guardia_che_non_uccide_nessun_mutante_ferma_e_dice_quanti_ne_ha_provati(
        self, repo_di_prova
    ):
        """«Nato verde e non morde» è una lettura più forte di «il codice c'era
        già»: dice che il test non guarda le righe che il branch ha scritto. Il
        conto dei mutanti provati è ciò che permette a chi legge di crederci."""
        repo_di_prova.commit("feat: la somma", {
            "backend/app/somma.py":
                "def somma(a, b):\n    totale = a + b\n    return totale\n",
        })
        sha = repo_di_prova.commit("test: la somma esiste", {
            "backend/tests/test_somma.py":
                "from app.somma import somma\n\n\n"
                "def test_la_somma_esiste():\n    assert callable(somma)\n",
        })
        morsi: list[dict[str, str]] = []

        mancati = runner.gate_del_rosso(morsi=morsi)

        assert morsi == []
        assert [m["commit"] for m in mancati] == [sha[:7]]
        assert "nato verde e non morde" in mancati[0]["esito"]
        assert "2 mutanti provati" in mancati[0]["esito"]

    def test_senza_righe_da_mutare_la_lettura_lo_dice(self, repo_di_prova):
        """Un `def` con il solo `return` ha un mutante solo, e non compila: zero
        provati non è «nessuno lo fa fallire», è «non c'era niente da provare»."""
        repo_di_prova.commit("feat: la somma", {
            "backend/app/somma.py": "def somma(a, b):\n    return a + b\n",
        })
        repo_di_prova.commit("test: la somma esiste", {
            "backend/tests/test_somma.py":
                "from app.somma import somma\n\n\n"
                "def test_la_somma_esiste():\n    assert callable(somma)\n",
        })

        mancati = runner.gate_del_rosso()

        assert "nato verde" in mancati[0]["esito"]
        assert "nessun mutante da provare" in mancati[0]["esito"]

    def test_si_mutano_solo_i_file_del_linguaggio_del_test(self, repo_di_prova):
        """Un test Python non morde un `.ts`: mutare l'altra metà del monolite è
        tempo speso a rigirare un test che non può vedere niente — e un conto
        gonfiato di mutanti che «non lo fanno fallire»."""
        repo_di_prova.commit("feat: la somma, di qua e di là", {
            "backend/app/somma.py":
                "def somma(a, b):\n    totale = a + b\n    return totale\n",
            "frontend/src/lib/somma.ts":
                "export function somma(a: number, b: number) {\n"
                "  const totale = a + b\n  return totale\n}\n",
        })
        repo_di_prova.commit("test: la somma esiste", {
            "backend/tests/test_somma.py":
                "from app.somma import somma\n\n\n"
                "def test_la_somma_esiste():\n    assert callable(somma)\n",
        })

        mancati = runner.gate_del_rosso()

        assert "2 mutanti provati" in mancati[0]["esito"], (
            "le righe del .ts sono entrate nel conto di un test Python"
        )

    def test_il_file_mutato_torna_com_era_dopo_la_prova(self, repo_di_prova):
        """L'ultimo mutante non deve restare nel worktree: il secondo test nato
        verde dello stesso commit leggerebbe un file già guasto, e i suoi mutanti
        nascerebbero da lì — o troverebbe rosso per una ragione che non è la sua."""
        sorgente = "def somma(a, b):\n    totale = a + b\n    return totale\n"
        repo_di_prova.commit("feat: la somma", {"backend/app/somma.py": sorgente})
        sha = repo_di_prova.commit("test: la somma esiste", {
            "backend/tests/test_somma.py":
                "from app.somma import somma\n\n\n"
                "def test_la_somma_esiste():\n    assert callable(somma)\n",
        })
        nuovi = runner.test_nuovi_del_commit(sha)

        with runner.worktree_usa_e_getta(sha) as albero:
            comandi, _ = runner.comandi_dei_test(albero, nuovi)
            runner.quarta_lettura(albero, "origin/main", sha, comandi[0],
                                  "tests/test_somma.py::test_la_somma_esiste")

            assert (albero / "backend/app/somma.py").read_text() == sorgente


class TestITestCheMordonoFinisconoNelRapporto:
    """Un test nato verde che passa per la quarta lettura non sparisce: il
    rapporto del giro dice **perché** è passato — commit, test, mutante — accanto
    ai commit senza rosso. Chi rilegge il giro deve poter andare a quella riga e
    vedere il guasto che il test ha sentito; e chi non ci crede deve poterlo
    contestare col Protocollo di rifinitura di PBI-105.
    """

    MORSO = {"commit": "9f952c0",
             "titolo": "test(analisi): presidia l'altra metà della regola del rail",
             "test": "src/components/AppLayout.test.tsx -t su una pratica tiene accesa "
                     "la sezione che la contiene",
             "mutante": "frontend/src/lib/nav.ts:67  `a || b` → `a && b`"}

    def _mondo(self, monkeypatch):
        monkeypatch.setattr(
            runner, "git",
            lambda *a: ("2" if a[:2] == ("rev-list", "--count")
                        else elenco_backlog() if a[:2] == ("ls-tree", "--name-only")
                        else ""),
        )
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "pubblica", lambda branch: True)
        monkeypatch.setattr(runner, "revisione_critica",
                            lambda p: runner.Verdetto("pass", "", "ok"))

        def _gate(visti=None, morsi=None, **k):
            morsi.append(dict(self.MORSO))
            return []

        monkeypatch.setattr(runner, "gate_del_rosso", _gate)

    def test_il_morso_finisce_nellesito_e_a_schermo(self, monkeypatch, capsys):
        self._mondo(monkeypatch)

        esito = runner.esegui_pbi("PBI-105", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "fatto"
        assert esito.test_che_mordono == [self.MORSO]
        a_schermo = capsys.readouterr().out
        assert "9f952c0" in a_schermo and "morde" in a_schermo
        assert "nav.ts:67" in a_schermo

    def test_anche_il_gate_lanciato_da_solo_li_stampa(self, monkeypatch, capsys):
        """`--gate-rosso` è il modo di rileggere un `fermato` e di provare un branch
        chiuso: se non dice chi è passato per la quarta lettura, la prova sul caso
        vero — `9f952c0` — non si può leggere da nessuna parte."""
        def _gate(base, ref, morsi=None, **k):
            morsi.append(dict(self.MORSO))
            return []

        monkeypatch.setattr(runner, "gate_del_rosso", _gate)

        assert runner.stampa_il_gate_del_rosso("origin/main..pbi/pbi-333-giro4") == 0
        a_schermo = capsys.readouterr().out
        assert "9f952c0" in a_schermo and "morde" in a_schermo
        assert "nav.ts:67" in a_schermo


class TestIlMorsoEUnFallimentoPerAsserzione:
    """Guardia nata verde su `falliti_per_asserzione` — e giudicata, come ogni
    guardia, dalla quarta lettura di questo stesso branch.

    Il lato pytest lo esercitano già le fixture `callable(somma)`; qui il lato
    vitest, che legge dal json: il file che non si carica non ha esiti per test
    e non è un morso, l'asserzione fallita lo è.
    """

    def _comando(self, rapporto):
        return runner.ComandoDiProva(Path("/nessuna"), ["npm", "test"], "vitest",
                                     {"morde": "x.test.ts -t morde"}, rapporto)

    def test_il_file_che_vitest_non_carica_non_e_un_morso(self, tmp_path):
        rapporto = tmp_path / "vitest.json"
        rapporto.write_text(json.dumps({"testResults": [
            {"status": "failed", "assertionResults": []}]}))

        assert runner.falliti_per_asserzione(self._comando(rapporto), "") == set()

    def test_lasserzione_fallita_e_un_morso(self, tmp_path):
        rapporto = tmp_path / "vitest.json"
        rapporto.write_text(json.dumps({"testResults": [{"status": "failed", "assertionResults": [
            {"title": "morde", "status": "failed"},
            {"title": "non morde", "status": "passed"}]}]}))

        assert runner.falliti_per_asserzione(self._comando(rapporto), "") == {"morde"}

    def test_in_pytest_conta_il_failed_e_non_lerror(self):
        comando = runner.ComandoDiProva(Path("/nessuna"), ["pytest"], "python",
                                        {"tests/test_x.py::test_a": "tests/test_x.py::test_a"})
        uscita = ("tests/test_x.py::test_a FAILED\n"
                  "tests/test_x.py::test_b ERROR\n"
                  "tests/test_x.py::test_c PASSED\n")

        assert runner.falliti_per_asserzione(comando, uscita) == {"tests/test_x.py::test_a"}


class TestSiCancellaSoloDentroUnCorpo:
    """Dalla prima prova sul caso vero (`pbi/pbi-333-giro4`, 01/09): il mutante che
    la guardia ha ucciso era la cancellazione di `import { … } from '../lib/nav'`
    in `AppLayout.tsx`. Non è un guasto di **comportamento**, è un guasto di
    **esistenza**: senza quell'import ogni test che rende il componente fallisce,
    compreso uno che non guarda niente. Lo stesso vale per un `export const` o
    per una costante di modulo in Python. La riga a livello di modulo — senza
    indentazione — dichiara; la riga dentro un corpo decide, ed è quella che si
    cancella. Gli scambi restano dove sono, anche a livello di modulo.
    """

    def _dopo(self, riga: str) -> list[str]:
        return [m.dopo for m in runner.mutanti_del_sorgente(riga + "\n", {1})]

    def test_una_importazione_non_si_cancella(self):
        assert self._dopo("import { navItemsForRole } from '../lib/nav'") == []
        assert self._dopo("from app.somma import somma") == []

    def test_una_dichiarazione_di_modulo_non_si_cancella_ma_si_scambia(self):
        assert self._dopo("export const APERTO = true") == ["export const APERTO = false"]
        assert self._dopo("SOGLIA_ALTA = 1 < 2") == ["SOGLIA_ALTA = 1 <= 2"]

    def test_dentro_un_corpo_si_cancella(self):
        assert "" in self._dopo("    totale = a + b")
        assert "" in self._dopo("  const totale = a + b")


# --- Le costanti nascono da asdlc.toml (PBI-358) ------------------------------
#
# Le stesse due forme dell'id di un PBI erano scritte a mano in cinque punti fra
# runner e tick, e undici letture eseguite dicevano `origin/main` una per una:
# PBI-353 ne ha corrette tre insieme, e la coda è rimasta ferma sette ore perché
# la quarta diceva un'altra cosa. Da qui i valori li porta `asdlc.toml`, letto da
# `tools/asdlc_config.py`, e le costanti di modulo restano nomi di modulo: i 36
# `monkeypatch.setattr` di questo file devono mordere ancora.


def toml_di_prova(base="origin/main", prefisso_ramo="pbi/pbi-",
                  cartella="backlog", coda="backlog/CODA.md",
                  id="PBI-{n}", file="PBI-{n}-{slug}.md",
                  registro="runs", tempi="tempi.csv",
                  venv="backend/.venv", prestiti=("data", "frontend/node_modules"),
                  tentativi=3, igiene=3, revisioni=4, gate_del_rosso=True,
                  gate=(("pytest", ("pytest", "-q"), "backend", ()),)) -> str:
    """Un `asdlc.toml` coi valori di oggi, e ogni test nomina solo ciò che cambia.
    Un gate è `(nome, comando, cwd, solo_se_tocca)`."""
    def elenco(voci):
        return "[" + ", ".join(f'"{v}"' for v in voci) + "]"

    testo = (
        f'[git]\nbase = "{base}"\nprefisso_ramo = "{prefisso_ramo}"\n\n'
        f'[backlog]\ncartella = "{cartella}"\ncoda = "{coda}"\nid = "{id}"\nfile = "{file}"\n\n'
        f'[registro]\ncartella = "{registro}"\ntempi = "{tempi}"\n\n'
        f'[ambiente]\nvenv = "{venv}"\nprestiti = {elenco(prestiti)}\n\n'
        f'[worktree]\npercorso = "~/ada-run"\n\n'
        f'[soglie]\ntentativi = {tentativi}\nigiene = {igiene}\nrevisioni = {revisioni}\n\n'
        f'[gate_del_rosso]\nattivo = {"true" if gate_del_rosso else "false"}\n'
    )
    for nome, comando, cwd, solo_se_tocca in gate:
        testo += f'\n[[gate]]\nnome = "{nome}"\ncomando = {elenco(comando)}\ncwd = "{cwd}"\n'
        if solo_se_tocca:
            testo += f"solo_se_tocca = {elenco(solo_se_tocca)}\n"
    return testo


def toml_versionato(config):
    """Il solo `asdlc.toml` del repository, **senza** `asdlc.local.toml`.

    All'import il modulo applica anche il file locale, che sulla macchina di chi
    lo scrive cambia `[ambiente]` e `[worktree]` di proposito: un test che
    guardasse lì il «valore di ieri» sarebbe rosso su codice giusto, e verde
    solo dove il file non c'è — in CI, e nel worktree del runner."""
    return config.interpreta(config.leggi_toml(REPO / config.NOME_FILE), config.NOME_FILE)


@pytest.fixture
def configura(tmp_path):
    """Parte dal solo `asdlc.toml` versionato, scrive un TOML di prova, lo applica
    al runner e alla fine rimette la configurazione di macchina. Il `monkeypatch`
    di un singolo nome non basterebbe: qui si prova che dal file arrivino
    **tutti** i nomi insieme."""
    di_prima = runner.CFG
    runner.configura(toml_versionato(runner.asdlc_config))

    def _applica(testo: str):
        (tmp_path / "asdlc.toml").write_text(testo, encoding="utf-8")
        runner.configura(runner.asdlc_config.carica(tmp_path))
        return runner.CFG

    yield _applica
    runner.configura(di_prima)


class TestIGateVengonoDaAsdlcToml:
    def test_i_quattro_gate_di_oggi_nome_per_nome_e_cwd_per_cwd(self):
        """Nessun numero cambia in questo giro (decisione 5): il TOML del
        repository dichiara i gate di prima, alla lettera."""
        assert [(g.nome, list(g.comando), g.cwd) for g in runner.GATE] == [
            ("pytest", ["pytest", "-q"], "backend"),
            ("tsc", ["npm", "run", "build"], "frontend"),
            ("eslint", ["npm", "run", "lint"], "frontend"),
            ("vitest", ["npm", "test"], "frontend"),
        ]
        assert [g.nome for g in runner.GATE] == [g.nome for g in runner.CFG.gate], (
            "i gate del runner sono quelli letti da asdlc.toml, non una lista sua"
        )

    def test_con_un_toml_a_due_gate_gira_gate_ne_gira_due(self, configura, monkeypatch):
        configura(toml_di_prova(gate=(
            ("pytest", ("pytest", "-q"), "backend", ()),
            ("mypy", ("mypy", "."), "src", ()),
        )))
        girati: list[tuple[str, Path]] = []
        monkeypatch.setattr(
            runner, "esegui",
            lambda cmd, cwd, timeout=0: girati.append((cmd[0], cwd)) or (0, ""),
        )

        assert runner.gira_gate(set()) == []
        assert girati == [("pytest", runner.REPO / "backend"), ("mypy", runner.REPO / "src")]


class TestLeSoglieEIPercorsiVengonoDaAsdlcToml:
    """Nessun numero cambia in questo giro (decisione 5): prima di applicare il
    TOML di prova, ogni test guarda che il valore di oggi sia quello di ieri."""

    def test_le_soglie_seguono_il_toml(self, configura):
        """Il TOML porta il numero; la ragione — PBI-201, sei revisioni, i due
        difetti peggiori usciti al quarto e al quinto giro — resta nel sorgente."""
        assert (runner.MAX_TENTATIVI, runner.MAX_IGIENE, runner.MAX_REVISIONI) == (3, 3, 4)

        configura(toml_di_prova(tentativi=2, igiene=5, revisioni=7))

        assert (runner.MAX_TENTATIVI, runner.MAX_IGIENE, runner.MAX_REVISIONI) == (2, 5, 7)

    def test_i_prestiti_e_il_registro_seguono_il_toml(self, configura):
        assert runner.PRESTITI == ("data", "frontend/node_modules")
        assert runner.CSV_TEMPI == runner.REPO / "runs" / "tempi.csv"

        configura(toml_di_prova(prestiti=("dati",), registro="giri", tempi="ore.csv"))

        assert runner.PRESTITI == ("dati",)
        assert runner.LOG_DIR == runner.REPO / "giri"
        assert runner.CSV_TEMPI == runner.REPO / "giri" / "ore.csv"

    def test_il_venv_segue_il_toml(self, configura, tmp_path, monkeypatch):
        configura(toml_di_prova(venv="altro/.venv"))
        bin_venv = tmp_path / "altro" / ".venv" / "bin"
        bin_venv.mkdir(parents=True)
        monkeypatch.setattr(runner, "REPO", tmp_path)
        monkeypatch.setenv("PATH", "/usr/bin")

        assert runner.venv_sul_path() == str(bin_venv)

    def test_la_cartella_del_backlog_segue_il_toml(self, configura, git_finto):
        """`trova_pbi` chiede a `origin/main` l'elenco di **quella** cartella."""
        configura(toml_di_prova(cartella="storie"))

        runner.trova_pbi("PBI-102")

        assert ("ls-tree", "--name-only", "origin/main", "storie/") in git_finto


class TestIlRamoDiBaseVieneDaAsdlcToml:
    """Undici letture eseguite di `origin/main`, più le righe dei prompt che lo
    dicono all'agente: con `[git] base = "origin/master"` lo seguono tutte, e
    nessuna resta indietro — un gate che misura su un ramo e un prompt che ne
    nomina un altro è una bugia che costa un giro (decisione 6)."""

    @pytest.fixture
    def su_master(self, configura):
        configura(toml_di_prova(base="origin/master"))

    def test_crea_branch_ramifica_dal_ramo_del_toml(self, su_master, git_finto):
        assert runner.crea_branch("PBI-102") == "pbi/pbi-102"
        assert ("fetch", "origin", "master") in git_finto
        assert ("switch", "-c", "pbi/pbi-102", "origin/master") in git_finto

    def test_trova_pbi_cerca_il_file_sul_ramo_del_toml(self, su_master, git_finto):
        runner.trova_pbi("PBI-102")

        assert ("fetch", "origin", "master") in git_finto
        assert ("ls-tree", "--name-only", "origin/master", "backlog/") in git_finto

    def test_un_giro_intero_non_nomina_mai_origin_main(self, su_master, git_finto, monkeypatch):
        """Il conteggio dei commit, l'elenco dei file e il gate del rosso: sono
        le letture dentro `esegui_pbi`, e si guardano da fuori tutte insieme."""
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: [])
        monkeypatch.setattr(
            runner, "revisione_critica", lambda p: runner.Verdetto("pass", "", "PASS"))

        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False)

        assert esito.stato == "fatto"
        assert ("rev-list", "--count", "origin/master..HEAD") in git_finto
        assert ("rev-list", "--reverse", "origin/master..HEAD") in git_finto
        assert ("diff", "--name-only", "origin/master...HEAD") in git_finto
        assert not [c for c in git_finto if any("origin/main" in arg for arg in c)], (
            "una lettura è rimasta sul ramo scritto a mano"
        )

    def test_un_pbi_che_non_c_e_lo_dice_col_ramo_del_toml(self, su_master, git_finto):
        esito = runner.esegui_pbi("PBI-999", attivi=set(), dry=True, con_pr=False)

        assert esito.stato == "saltato"
        assert "origin/master" in esito.nota

    def test_il_gate_del_rosso_parte_dal_ramo_del_toml(self, su_master, monkeypatch):
        visto: dict[str, str] = {}
        monkeypatch.setattr(
            runner, "commit_da_esaminare",
            lambda base, ref, visti: visto.update(base=base, ref=ref) or [])

        assert runner.gate_del_rosso() == []
        assert visto == {"base": "origin/master", "ref": "HEAD"}

    def test_gate_rosso_a_mano_parte_dal_ramo_del_toml(self, su_master, monkeypatch):
        visto: dict[str, str] = {}
        monkeypatch.setattr(
            runner, "gate_del_rosso",
            lambda base, ref, **k: visto.update(base=base, ref=ref) or [])

        assert runner.stampa_il_gate_del_rosso("pbi/pbi-330") == 0
        assert visto == {"base": "origin/master", "ref": "pbi/pbi-330"}

    def test_chiedi_impl_conta_i_commit_dal_ramo_del_toml(self, su_master, git_finto, monkeypatch):
        monkeypatch.setattr(runner, "test_nuovi_dellalbero", lambda: [])

        runner.test_nuovi_da_aprire()

        assert ("rev-list", "--count", "origin/master..HEAD") in git_finto

    def test_la_pr_si_apre_verso_il_ramo_del_toml(self, su_master, monkeypatch):
        comandi: list[list[str]] = []
        monkeypatch.setattr(runner, "pubblica", lambda branch: True)
        monkeypatch.setattr(
            runner, "esegui",
            lambda cmd, cwd, timeout=0: comandi.append(cmd) or (0, "https://x/pull/1\n"))

        runner.apri_pr("PBI-212", runner.REPO / "backlog" / "PBI-212-x.md",
                       "pbi/pbi-212", runner.Esito("PBI-212", "fatto"))

        assert ["--base", "master"] == comandi[0][comandi[0].index("--base"):][:2]

    def test_i_prompt_del_critic_e_del_rimedio_nominano_il_ramo_del_toml(self, su_master):
        critic = runner.PROMPT_CRITIC.format(pbi_path="backlog/x.md")
        rimedio = runner.PROMPT_RIMEDIO.format(rapporto="x", pbi_path="backlog/x.md")
        aiuto = runner.costruisci_parser().format_help()

        for nome, testo in (("PROMPT_CRITIC", critic), ("PROMPT_RIMEDIO", rimedio),
                            ("--help", aiuto)):
            assert "origin/master" in testo, f"{nome} non nomina il ramo del TOML"
            assert "origin/main" not in testo, f"{nome} nomina ancora il ramo scritto a mano"


class TestLIdEIlNomeFileDelPbiStannoInUnPostoSolo:
    """`[backlog].id` e `.file` sono modelli — `PBI-{n}`, `PBI-{n}-{slug}.md` —
    e `[git].prefisso_ramo` il prefisso del ramo: chi forka scrive il suo
    modello, e le forme che il runner deriva cambiano tutte insieme. Prima di
    applicare il modello di prova ogni test guarda che con quello di oggi le
    forme siano quelle di ieri."""

    def test_trova_pbi_riconosce_il_file_dal_modello(self, configura, monkeypatch, tmp_path):
        configura(toml_di_prova(id="US-{n}", file="US-{n}-{slug}.md"))

        def _git(*args):
            if args[:2] == ("ls-tree", "--name-only"):
                return "backlog/US-7-somma.md\nbacklog/US-70-altro.md\nbacklog/PBI-7-vecchio.md\n"
            return ""

        monkeypatch.setattr(runner, "git", _git)

        assert runner.trova_pbi("US-7") == runner.REPO / "backlog" / "US-7-somma.md"
        assert runner.trova_pbi("PBI-7") is None, "non è un id di questo progetto"

        # E il ripiego sull'albero estratto, quando `origin` non risponde.
        (tmp_path / "backlog").mkdir()
        (tmp_path / "backlog" / "US-7-somma.md").write_text("# US-7\n", encoding="utf-8")
        monkeypatch.setattr(runner, "REPO", tmp_path)

        def _git_muto(*args):
            raise RuntimeError("origin non risponde")

        monkeypatch.setattr(runner, "git", _git_muto)

        assert runner.trova_pbi("US-7") == tmp_path / "backlog" / "US-7-somma.md"

    def test_il_ramo_del_pbi_segue_il_prefisso(self, configura, git_finto):
        assert runner.nome_libero("PBI-322", set()) == "pbi/pbi-322"
        assert runner.nome_libero("PBI-322", {"pbi/pbi-322"}) == "pbi/pbi-322-giro2"

        configura(toml_di_prova(id="US-{n}", file="US-{n}-{slug}.md", prefisso_ramo="us/us-"))

        assert runner.nome_libero("US-7", set()) == "us/us-7"
        assert runner.nome_libero("US-7", {"us/us-7"}) == "us/us-7-giro2"
        assert runner.crea_branch("US-7") == "us/us-7"
        assert ("ls-remote", "--heads", "origin", "us/us-7*") in git_finto
        assert ("branch", "--list", "us/us-7*", "--format=%(refname:short)") in git_finto
        assert ("switch", "-c", "us/us-7", "origin/main") in git_finto


class TestIlGateDelRossoSiSpegneDaAsdlcTomlELoDichiara:
    """La valvola del livello 4 rinviato (decisione 7): un progetto il cui runner
    di test il gate non sa leggere tiene gli altri due gate — degradato, ma
    ancora ASDLC. Un gate che si indebolisce in silenzio è la prima cosa che
    `AUTOMAZIONE.md` vieta, quindi spento **lo si scrive**."""

    def _giro(self, monkeypatch, con_critic=True):
        chiamati: list[str] = []
        monkeypatch.setattr(runner, "esegui", lambda *a, **k: (0, "FATTO: fatto\n"))
        monkeypatch.setattr(runner, "gira_gate", lambda attivi: chiamati.append("gate") or [])
        monkeypatch.setattr(runner, "gate_del_rosso",
                            lambda **k: chiamati.append("rosso") or [])
        monkeypatch.setattr(
            runner, "revisione_critica",
            lambda p: chiamati.append("critic") or runner.Verdetto("pass", "", "PASS"))
        esito = runner.esegui_pbi("PBI-102", attivi=set(), dry=False, con_pr=False,
                                  con_critic=con_critic)
        return esito, chiamati

    def test_spento_non_gira_gli_altri_due_si_e_la_nota_lo_dice(
        self, configura, git_finto, monkeypatch, capsys
    ):
        esito, chiamati = self._giro(monkeypatch)
        assert chiamati == ["gate", "rosso", "critic"], "acceso, oggi, gira"
        assert "spento" not in esito.nota

        configura(toml_di_prova(gate_del_rosso=False))
        esito, chiamati = self._giro(monkeypatch)

        assert esito.stato == "fatto"
        assert chiamati == ["gate", "critic"]
        assert "gate del rosso spento da asdlc.toml" in esito.nota
        uscita = capsys.readouterr().out
        assert "gate del rosso" in uscita and "spento" in uscita, "e lo dice anche a schermo"

    def test_la_dichiarazione_convive_con_quella_del_critic_saltato(
        self, configura, git_finto, monkeypatch
    ):
        """Due gate su tre tolti, due frasi nella nota: chi legge `tempi.csv`
        deve sapere che quel giro ne ha avuto **uno**."""
        configura(toml_di_prova(gate_del_rosso=False))

        esito, chiamati = self._giro(monkeypatch, con_critic=False)

        assert chiamati == ["gate"]
        assert "gate del rosso spento da asdlc.toml" in esito.nota
        assert "critic saltato" in esito.nota


class TestUnGateConSoloSeToccaSiAccendeSeIlDiffToccaQueiPercorsi:
    """`[[gate]].solo_se_tocca` risuscita `Gate.solo_se` (decisione 8), che era
    codice morto: `attivi` era sempre vuoto. La semantica che serve è «accendi
    questo gate se il diff `base...HEAD` tocca uno di questi percorsi»; un gate
    senza il campo è sempre acceso, che è il comportamento di oggi per tutti e
    quattro. Il primo consumatore vero è il gate `asdlc` della Fase 2."""

    def _gate_girati(self, configura, monkeypatch, toccati: list[str]) -> list[str]:
        configura(toml_di_prova(gate=(
            ("pytest", ("pytest", "-q"), "backend", ()),
            ("asdlc", ("pytest", "-q", "tools/tests"), ".", ("tools/", "asdlc.toml")),
        )))
        girati: list[str] = []
        monkeypatch.setattr(
            runner, "esegui", lambda cmd, cwd, timeout=0: girati.append(cmd[-1]) or (0, ""))

        def _git(*args):
            assert args == ("diff", "--name-only", "origin/main...HEAD"), args
            return "\n".join(toccati)

        monkeypatch.setattr(runner, "git", _git)
        runner.gira_gate(set())
        return girati

    def test_acceso_se_tocca_spento_altrimenti_e_senza_il_campo_sempre_acceso(
        self, configura, monkeypatch
    ):
        assert self._gate_girati(configura, monkeypatch, ["backend/app/x.py"]) == ["-q"], (
            "il diff non tocca tools/ né asdlc.toml: il gate asdlc resta spento"
        )
        assert self._gate_girati(
            configura, monkeypatch, ["backend/app/x.py", "tools/asdlc_runner.py"]
        ) == ["-q", "tools/tests"], "tocca tools/: si accende, dopo il gate sempre acceso"
        assert self._gate_girati(configura, monkeypatch, ["asdlc.toml"]) == ["-q", "tools/tests"]
        assert self._gate_girati(configura, monkeypatch, []) == ["-q"], (
            "un gate senza il campo gira anche su un diff vuoto"
        )

    def test_i_gate_di_oggi_non_hanno_il_campo_e_sono_sempre_accesi(self):
        assert [list(g.solo_se_tocca) for g in runner.GATE] == [[], [], [], []]
