"""Il lettore di `asdlc.toml`: i gate, i percorsi, le soglie e il ramo del runner.

Solo libreria standard, di proposito: `tomllib` è stdlib da Python 3.11, e un
runner che si legge la configurazione senza un `pip install` è un runner che si
copia in un altro progetto così com'è (`ADR-0017`, precondizione 2).

Il file è **obbligatorio** e non ha default silenziosi: un runner che partisse
senza, coi valori di aDa cablati da qualche parte, passerebbe su un progetto
nuovo per la ragione sbagliata — che è il solo modo di non accorgersi che un
percorso è ancora scritto nel sorgente (PBI-358, decisione 3). Ogni mancanza si
ferma con un messaggio che nomina il file e la chiave: lo legge chi ha appena
perso l'uso di `git commit`, perché l'hook esegue il runner a ogni commit.
"""
from __future__ import annotations

import re
import subprocess
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

NOME_FILE = "asdlc.toml"
# I percorsi di macchina, gitignored. Facoltativo: nel worktree del runner non c'è.
NOME_FILE_LOCALE = "asdlc.local.toml"
# Le sole sezioni che il file locale può sovrascrivere: i gate, le soglie e il
# ramo sono del progetto, e una macchina che li cambiasse da un file gitignored
# girerebbe un altro metodo con lo stesso nome, senza che una PR lo mostri.
SEZIONI_LOCALI = ("ambiente", "worktree")
# Le chiavi di quelle sezioni che restano del progetto lo stesso: il pin da cui
# si installa il pacchetto è versionato, e una macchina con un pin suo
# registrerebbe giri di una versione che nessun altro ha (PBI-395, decisione 3).
CHIAVI_DEL_PROGETTO = (("ambiente", "installa"),)


class ErroreDiConfigurazione(ValueError):
    """`asdlc.toml` manca, non si legge, o non dice ciò che serve."""


@dataclass(frozen=True)
class Gate:
    nome: str
    comando: tuple[str, ...]
    cwd: str = "."
    # I percorsi che lo accendono: il gate gira solo se il diff del branch ne
    # tocca uno. Vuoto = sempre acceso.
    solo_se_tocca: tuple[str, ...] = ()


@dataclass(frozen=True)
class Git:
    base: str           # `origin/main`: il ramo da cui si nasce e su cui si misura
    prefisso_ramo: str  # `pbi/pbi-`: il ramo del PBI è il prefisso più il numero

    @property
    def remoto(self) -> str:
        """`origin`, da `origin/main`: a chi si chiede il fetch."""
        return self.base.partition("/")[0]

    @property
    def ramo(self) -> str:
        """`main`, da `origin/main`: il ramo verso cui si apre la PR."""
        return self.base.partition("/")[2]

    def ramo_del_pbi(self, numero: str) -> str:
        """`pbi/pbi-358` dal numero: il prefisso e basta, il suffisso del giro
        lo aggiunge chi trova il nome occupato."""
        return f"{self.prefisso_ramo}{numero}"


# I segnaposto dei modelli, e ciò che ciascuno accetta: `{n}` un numero, `{slug}`
# il resto del nome senza salire di cartella. Da qui il lettore deriva le regex
# e i glob, così chi forka scrive il modello e non una regex.
SEGNAPOSTO = {"{n}": r"(?P<n>\d+)", "{slug}": r"(?P<slug>[^/]+)"}


def regex_del_modello(modello: str) -> re.Pattern[str]:
    """`PBI-{n}` → `PBI-(?P<n>\\d+)`, col resto scappato alla lettera."""
    pezzi = re.split("(" + "|".join(re.escape(s) for s in SEGNAPOSTO) + ")", modello)
    return re.compile("".join(SEGNAPOSTO.get(p, re.escape(p)) for p in pezzi))


@dataclass(frozen=True)
class Backlog:
    cartella: str
    coda: str
    id: str    # modello dell'id, `PBI-{n}`
    file: str  # modello del nome file, `PBI-{n}-{slug}.md`

    def numero(self, pbi: str) -> str | None:
        """`358` da `PBI-358`, o `None` se non è un id di questo progetto."""
        trovato = regex_del_modello(self.id).fullmatch(pbi)
        return trovato.group("n") if trovato else None

    def id_di(self, numero: str) -> str:
        return self.id.replace("{n}", numero)

    def glob_del_file(self, numero: str) -> str:
        """`PBI-358-*.md` dal numero: il nome file con lo slug libero, per `glob`
        e `fnmatch`."""
        return self.file.replace("{n}", numero).replace("{slug}", "*")


@dataclass(frozen=True)
class Registro:
    cartella: str
    tempi: str


@dataclass(frozen=True)
class Ambiente:
    venv: str
    prestiti: tuple[str, ...]
    # Il venv in cui è installato il runner, assoluto dopo `carica()`: relativo
    # alla radice comune, non a quella del progetto (PBI-384). `None` se il
    # progetto non lo dichiara.
    pacchetto: Path | None = None
    # Ciò che i gate e il runner lanciano per nome: il runner e il tick lo cercano
    # prima di partire. Vuoto, non si verifica niente.
    eseguibili: tuple[str, ...] = ()
    # La versione principale minima di un eseguibile, `{ node = 20 }`.
    minimi: dict[str, int] = field(default_factory=dict)
    # Da dove si reinstalla il pacchetto, come lo legge `pip install`: una
    # cartella della radice del progetto o un URL git pinnato a un tag
    # (PBI-395). Obbligatoria con `pacchetto`; `None` senza.
    installa: str | None = None


@dataclass(frozen=True)
class Worktree:
    percorso: Path


@dataclass(frozen=True)
class Soglie:
    tentativi: int
    igiene: int
    revisioni: int
    # I tetti di una chiamata a un agente, in minuti (PBI-369, decisione 6).
    minuti_builder: int = 90
    minuti_critic: int = 25


@dataclass(frozen=True)
class GateDelRosso:
    attivo: bool


@dataclass(frozen=True)
class Junit:
    # Il comando che lancia i test JUnit isolati: una lista di argomenti con
    # l'elemento `{test}`, che il runner sostituisce con `Classe#m1+m2,Altra#m3`
    # (PBI-505, decisione 4). `None` se il progetto non ha la sezione: il runner
    # non conosce Maven e non indovina un comando.
    comando: tuple[str, ...] | None = None


# I ruoli che hanno un prompt: ognuno è `asdlc/prompt/<ruolo>.md` nel pacchetto, e
# può avere un file di aggiunte `<ruolo>.md` nella cartella di `[prompt].aggiunte`.
RUOLI_DEI_PROMPT = ("builder", "igiene", "riprova", "critic", "rimedio")
# Il solo file della cartella delle aggiunte che non è un ruolo: dice a chi la
# apre cosa ci va, e non arriva a nessun prompt.
LEGGIMI_DELLE_AGGIUNTE = "README.md"


@dataclass(frozen=True)
class Prompt:
    # La cartella delle aggiunte del progetto, assoluta dopo `carica()`: relativa
    # alla radice del progetto nel TOML. `None` se il progetto non ne dichiara.
    aggiunte: Path | None = None


@dataclass(frozen=True)
class Solver:
    # Il tetto dei giri Solver↔Builder per lo stesso PBI (`PBI-507`, decisione 5).
    giri_massimi: int = 3
    # Le cause `runner-*` che `segnala_limite_runner` accetta: il progetto le tiene
    # allineate a `backlog/README.md` di `asdlc` (decisione 8). Vuota, ogni causa
    # è rifiutata.
    cause: tuple[str, ...] = ()
    # Il modello del Solver, come lo vuole `claude --model` (decisione 12).
    modello: str = "opus"


@dataclass(frozen=True)
class Lettore:
    # Il modello del Lettore, come lo vuole `claude --model` (`PBI-521`): il default è
    # quello del Solver.
    modello: str = "opus"
    # Il tetto della sua chiamata, in minuti, come `[soglie].minuti_*` (PBI-369).
    minuti: int = 30


@dataclass(frozen=True)
class Preverifica:
    # La pre-verifica nel giro, prima del ramo (`PBI-522`, `ADR-0031` decisione 4). Spenta
    # se la sezione manca: i giri dei test, con PBI finti di poche righe, si fermerebbero
    # tutti. Si accende nell'`asdlc.toml` di ogni progetto, come `[junit]`.
    attiva: bool = False
    # Con la pre-verifica accesa, legge anche il Lettore (`PBI-521`).
    lettore: bool = True


@dataclass(frozen=True)
class Rilascio:
    # Il remote git che punta al fork di `asdlc` da cui il Solver apre la PR a monte
    # (`PBI-509`, R5), e il prefisso del tag di rilascio (`ADR-0026`: `vX.Y.Z`).
    remote_fork: str = "fork"
    prefisso_tag: str = "v"
    # Il percorso della copia di `asdlc` sul disco da cui si apre la PR a monte
    # (`PBI-512`, decisione 3). Non si deduce da altro: senza, la PR non si apre.
    clone: str | None = None


@dataclass(frozen=True)
class Tick:
    # Il distacco dal battito precedente oltre il quale il tick avvisa, in minuti
    # (`PBI-510`, decisione 1).
    soglia_battito_minuti: int = 30


@dataclass(frozen=True)
class Notifiche:
    # Le notifiche del tick su Slack (`PBI-533`, decisione 8): spente se la sezione
    # manca. Il webhook è un segreto e non sta qui, ma in `~/.config/asdlc/slack-webhook`.
    attive: bool = False
    # Gli eventi da mandare, fra quelli della decisione 3: il default è tutti.
    eventi: tuple[str, ...] = ("fermo", "non-lanciato", "pronto", "rilascio", "barriera",
                               "finita", "guasto", "non-allineato", "reinstallazione",
                               "pausa")


@dataclass(frozen=True)
class Config:
    git: Git
    backlog: Backlog
    registro: Registro
    ambiente: Ambiente
    worktree: Worktree
    soglie: Soglie
    gate_del_rosso: GateDelRosso
    gate: tuple[Gate, ...]
    prompt: Prompt = Prompt()
    junit: Junit = Junit()
    solver: Solver = Solver()
    lettore: Lettore = Lettore()
    preverifica: Preverifica = Preverifica()
    rilascio: Rilascio = Rilascio()
    tick: Tick = Tick()
    notifiche: Notifiche = Notifiche()


def radice(cwd: Path) -> Path:
    """La radice del progetto: il primo antenato di `cwd`, compresa, che contiene
    `asdlc.toml`. Se non c'è, è un errore che nomina la cwd.

    Il progetto lo dice la cartella di lavoro e non il sorgente del runner:
    installato, il sorgente sta in site-packages (`ADR-0026`, PBI-382). Non
    `git rev-parse --show-toplevel`: in un repository senza `asdlc.toml` il
    runner non ha niente da fare.
    """
    for cartella in (cwd, *cwd.parents):
        if (cartella / NOME_FILE).is_file():
            return cartella
    raise ErroreDiConfigurazione(
        f"nessun `{NOME_FILE}` da `{cwd}` in su: il runner si lancia dalla "
        "cartella di un progetto ASDLC"
    )


def carica(repo: Path) -> Config:
    """La configurazione letta da `repo / asdlc.toml`, con sopra le sovrascritture
    di `asdlc.local.toml` se c'è, e con `[ambiente].pacchetto` e
    `[worktree].percorso` risolti dalla radice comune (`radice_comune()`)."""
    dati = leggi_toml(repo / NOME_FILE)
    rifiuta_i_percorsi_di_macchina(dati)
    locale = repo / NOME_FILE_LOCALE
    if locale.exists():
        dati = sovrascrivi(dati, leggi_toml(locale), NOME_FILE_LOCALE)
    cfg = interpreta(dati, NOME_FILE)
    comune = radice_comune(repo)
    pacchetto = cfg.ambiente.pacchetto
    aggiunte = cfg.prompt.aggiunte
    if aggiunte is not None:
        aggiunte = (repo / aggiunte).resolve()
        controlla_le_aggiunte(aggiunte)
    return replace(
        cfg,
        prompt=Prompt(aggiunte=aggiunte),
        ambiente=replace(cfg.ambiente,
                         pacchetto=None if pacchetto is None else risolvi(comune, pacchetto)),
        worktree=Worktree(percorso=risolvi(comune, cfg.worktree.percorso)),
    )


# Le chiavi di percorso che si risolvono dalla radice comune: in `asdlc.toml`
# solo relative, perché il file è versionato e vale su ogni PC (PBI-384).
PERCORSI_DELLA_RADICE_COMUNE = (("worktree", "percorso"), ("ambiente", "pacchetto"))


def rifiuta_i_percorsi_di_macchina(dati: dict) -> None:
    """Un percorso assoluto o con `~` in `asdlc.toml` si ferma, nominando chiave
    e valore. Si guarda il file versionato **prima** del locale: in
    `asdlc.local.toml` lo stesso percorso vale, ed è il suo posto."""
    for sezione, chiave in PERCORSI_DELLA_RADICE_COMUNE:
        tabella = dati.get(sezione)
        valore = tabella.get(chiave) if isinstance(tabella, dict) else None
        if isinstance(valore, str) and (valore.startswith("~") or Path(valore).is_absolute()):
            raise ErroreDiConfigurazione(
                f"{NOME_FILE}: `[{sezione}].{chiave}` è un percorso di macchina, "
                f"{valore!r} — qui i percorsi sono relativi alla radice comune del "
                f"repository, e uno assoluto va in {NOME_FILE_LOCALE}, che è gitignored")


def controlla_le_aggiunte(cartella: Path) -> None:
    """La cartella di `[prompt].aggiunte` c'è, e porta solo file `<ruolo>.md`.

    Una cartella dichiarata e assente, o un file con un nome che non è un ruolo,
    si fermano nominandoli: un refuso non diventa un'aggiunta persa in silenzio
    (PBI-386, decisione 3). Il `README.md` è ammesso: è la documentazione della
    cartella."""
    if not cartella.is_dir():
        raise ErroreDiConfigurazione(
            f"{NOME_FILE}: `[prompt].aggiunte` è {cartella}, che non è una cartella")
    ruoli = {f"{ruolo}.md" for ruolo in RUOLI_DEI_PROMPT}
    for file in sorted(cartella.iterdir()):
        if file.name not in ruoli and file.name != LEGGIMI_DELLE_AGGIUNTE:
            raise ErroreDiConfigurazione(
                f"{NOME_FILE}: `{file.name}` in {cartella} non è un ruolo — le aggiunte "
                f"sono file `<ruolo>.md`, con ruolo fra {', '.join(RUOLI_DEI_PROMPT)}")


def radice_comune(repo: Path) -> Path:
    """Il checkout principale del repository di `repo`: la cartella madre di
    `git rev-parse --git-common-dir`, la stessa da ogni worktree (PBI-384).

    Fuori da un repository git, o senza `git`, è `repo` stesso: un progetto che
    non ha worktree ha una radice sola.
    """
    try:
        detto = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--path-format=absolute",
             "--git-common-dir"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return repo.resolve()
    if detto.returncode != 0 or not detto.stdout.strip():
        return repo.resolve()
    return Path(detto.stdout.strip()).parent


def risolvi(comune: Path, percorso: Path) -> Path:
    """`percorso` in assoluto: com'è se lo è già, altrimenti dalla radice comune,
    con i `..` sciolti."""
    return percorso if percorso.is_absolute() else (comune / percorso).resolve()


def sovrascrivi(dati: dict, locali: dict, file: str) -> dict:
    """`dati` con sopra le sezioni di `locali`, chiave per chiave: una sezione
    locale che dice solo il venv non cancella i prestiti. Una sezione fuori da
    `SEZIONI_LOCALI`, o una chiave di `CHIAVI_DEL_PROGETTO`, si ferma e dice
    dove va."""
    uniti = dict(dati)
    for sezione, valori in locali.items():
        if sezione not in SEZIONI_LOCALI:
            ammesse = " e ".join(f"[{s}]" for s in SEZIONI_LOCALI)
            raise ErroreDiConfigurazione(
                f"{file}: `[{sezione}]` non si sovrascrive da qui — il file locale "
                f"porta solo {ammesse}; il resto è del progetto e sta in {NOME_FILE}")
        for propria, chiave in CHIAVI_DEL_PROGETTO:
            if propria == sezione and chiave in valori:
                raise ErroreDiConfigurazione(
                    f"{file}: `[{sezione}].{chiave}` non si sovrascrive da qui — è del "
                    f"progetto, e va in {NOME_FILE}")
        uniti[sezione] = {**dati.get(sezione, {}), **valori}
    return uniti


def leggi_toml(file: Path) -> dict:
    """Il file come dizionario. Assente o malformato, si ferma nominandolo."""
    try:
        with file.open("rb") as aperto:
            return tomllib.load(aperto)
    except FileNotFoundError:
        raise ErroreDiConfigurazione(
            f"{file.name} non c'è in {file.parent}: il runner legge da lì i suoi gate, "
            f"i suoi percorsi e il suo ramo, e senza non parte"
        ) from None
    except tomllib.TOMLDecodeError as guasto:
        raise ErroreDiConfigurazione(f"{file.name} non si legge: {guasto}") from None


def interpreta(dati: dict, file: str) -> Config:
    """Il dizionario nei suoi tipi. Ogni chiave è obbligatoria, tranne dove il
    default è scritto accanto al campo."""
    sezione = _Sezione(dati, file)
    git = sezione.dentro("git")
    backlog = sezione.dentro("backlog")
    registro = sezione.dentro("registro")
    ambiente = sezione.dentro("ambiente")
    worktree = sezione.dentro("worktree")
    soglie = sezione.dentro("soglie")
    gate_del_rosso = sezione.dentro("gate_del_rosso")
    # Facoltativa: un progetto che non estende i prompt non la scrive. E ha una
    # chiave sola: i prompt del pacchetto si estendono, non si sostituiscono
    # (`ADR-0026`, decisione 2), e un refuso non si ignora in silenzio.
    prompt = sezione.dentro("prompt", default={})
    prompt.solo("aggiunte", perche="i prompt del pacchetto si estendono con le "
                "aggiunte, e non si sostituiscono")
    # Facoltativa, con una chiave sola: la sezione dice come lanciare i test JUnit,
    # e una chiave che non conosciamo o un comando senza `{test}` non si ignorano
    # (PBI-505, decisione 4).
    junit = Junit()
    if "junit" in sezione.dati:
        dichiarato = sezione.dentro("junit")
        dichiarato.solo("comando", perche="la sezione dice solo il comando che lancia "
                        "i test JUnit isolati")
        comando = dichiarato.testi("comando")
        if not any("{test}" in argomento for argomento in comando):
            raise ErroreDiConfigurazione(
                f"{file}: `[junit].comando` deve contenere un argomento con `{{test}}`, "
                "dove il runner mette i test da lanciare")
        junit = Junit(comando=comando)
    # Facoltativa: i default valgono per un progetto che non la scrive (`PBI-507`).
    solver = Solver()
    if "solver" in sezione.dati:
        dichiarato = sezione.dentro("solver")
        dichiarato.solo("giri_massimi", "cause", "modello",
                        perche="la sezione dice il tetto dei giri, le cause `runner-*` "
                        "e il modello del Solver")
        solver = Solver(giri_massimi=dichiarato.positivo("giri_massimi", default=3),
                        cause=dichiarato.testi("cause", default=()),
                        modello=dichiarato.testo("modello", default="opus"))
    # Facoltativa: i default valgono per un progetto che non la scrive (`PBI-521`).
    lettore = Lettore()
    if "lettore" in sezione.dati:
        dichiarato = sezione.dentro("lettore")
        dichiarato.solo("modello", "minuti",
                        perche="la sezione dice il modello e il tetto in minuti del Lettore")
        lettore = Lettore(modello=dichiarato.testo("modello", default="opus"),
                          minuti=dichiarato.positivo("minuti", default=30))
    # Facoltativa: senza, la pre-verifica nel giro è spenta (`PBI-522`, decisione 1).
    preverifica = Preverifica()
    if "preverifica" in sezione.dati:
        dichiarato = sezione.dentro("preverifica")
        dichiarato.solo("attiva", "lettore",
                        perche="la sezione dice se il giro fa la pre-verifica e se legge "
                        "anche il Lettore")
        preverifica = Preverifica(attiva=dichiarato.booleano("attiva", default=False),
                                  lettore=dichiarato.booleano("lettore", default=True))
    # Facoltativa: i default valgono per un progetto che non la scrive (`PBI-509`).
    rilascio = Rilascio()
    if "rilascio" in sezione.dati:
        dichiarato = sezione.dentro("rilascio")
        dichiarato.solo("remote_fork", "prefisso_tag", "clone",
                        perche="la sezione dice il remote del fork di `asdlc`, il "
                        "prefisso del tag e il clone di `asdlc` da cui aprire la PR a monte")
        rilascio = Rilascio(remote_fork=dichiarato.testo("remote_fork", default="fork"),
                            prefisso_tag=dichiarato.testo("prefisso_tag", default="v"),
                            clone=dichiarato.testo("clone", default=None))
    # Facoltativa: il default vale per un progetto che non la scrive (`PBI-510`).
    tick = Tick()
    if "tick" in sezione.dati:
        dichiarato = sezione.dentro("tick")
        dichiarato.solo("soglia_battito_minuti",
                        perche="la sezione dice la soglia del battito del tick")
        tick = Tick(soglia_battito_minuti=dichiarato.positivo("soglia_battito_minuti",
                                                              default=30))
    # Facoltativa: senza, il tick non manda niente e non lo dice (`PBI-533`, decisione 8).
    notifiche = Notifiche()
    if "notifiche" in sezione.dati:
        dichiarato = sezione.dentro("notifiche")
        notifiche = Notifiche(attive=dichiarato.booleano("attive", default=False),
                              eventi=dichiarato.testi("eventi", default=Notifiche.eventi))
    # Un pacchetto senza sapere da dove reinstallarlo si ferma: un `"./tools"`
    # implicito è la causa `default-implicito` (PBI-395, decisione 2).
    if "pacchetto" in ambiente.dati and "installa" not in ambiente.dati:
        raise ErroreDiConfigurazione(
            f"{file}: manca `[ambiente].installa` — con `[ambiente].pacchetto` il tick "
            "deve sapere da dove reinstallare il pacchetto")
    installa = ambiente.testo("installa", default=None)
    if installa is not None:
        controlla_installa(installa, file)
    return Config(
        git=Git(base=git.testo("base"), prefisso_ramo=git.testo("prefisso_ramo")),
        backlog=Backlog(cartella=backlog.testo("cartella"), coda=backlog.testo("coda"),
                        id=backlog.testo("id"), file=backlog.testo("file")),
        registro=Registro(cartella=registro.testo("cartella"), tempi=registro.testo("tempi")),
        ambiente=Ambiente(venv=ambiente.testo("venv"), prestiti=ambiente.testi("prestiti"),
                          pacchetto=_percorso(ambiente.testo("pacchetto", default=None)),
                          eseguibili=ambiente.testi("eseguibili", default=()),
                          minimi=ambiente.interi_per_nome("minimi", default={}),
                          installa=installa),
        worktree=Worktree(percorso=Path(worktree.testo("percorso")).expanduser()),
        soglie=Soglie(tentativi=soglie.intero("tentativi"), igiene=soglie.intero("igiene"),
                      revisioni=soglie.intero("revisioni"),
                      minuti_builder=soglie.positivo("minuti_builder", default=90),
                      minuti_critic=soglie.positivo("minuti_critic", default=25)),
        gate_del_rosso=GateDelRosso(attivo=gate_del_rosso.booleano("attivo")),
        gate=tuple(_gate(g) for g in sezione.elenco_di_sezioni("gate")),
        prompt=Prompt(aggiunte=_percorso(prompt.testo("aggiunte", default=None))),
        junit=junit,
        solver=solver,
        lettore=lettore,
        preverifica=preverifica,
        rilascio=rilascio,
        tick=tick,
        notifiche=notifiche,
    )


# L'URL git di `[ambiente].installa`, pinnato a un tag e mai a un ramo
# (`ADR-0026`): `git+<schema>://…@v<maggiore>.<minore>.<patch>[#subdirectory=…]`.
RE_PIN_URL = re.compile(r"git\+[a-z]+://[^@#\s]*(@[^@#\s]*)?@v\d+\.\d+\.\d+"
                        r"(#subdirectory=[^#\s]+)?")


def controlla_installa(installa: str, file: str) -> None:
    """`[ambiente].installa` è in una delle due forme che `pip install` capisce:
    una cartella relativa alla radice del progetto, o un URL git pinnato a un tag
    (PBI-395, decisione 1). Fuori da queste si ferma, nominando chiave e valore."""
    if e_un_url(installa):
        if not RE_PIN_URL.fullmatch(installa):
            raise ErroreDiConfigurazione(
                f"{file}: `[ambiente].installa` è {installa!r}, un URL git non pinnato a "
                "un tag — la forma è `git+…@v<maggiore>.<minore>.<patch>"
                "[#subdirectory=…]`, mai un ramo (`ADR-0026`)")
    elif installa.startswith("~") or Path(installa).is_absolute():
        raise ErroreDiConfigurazione(
            f"{file}: `[ambiente].installa` è un percorso di macchina, {installa!r} — "
            "una cartella si scrive relativa alla radice del progetto, `./tools`")


def e_un_url(installa: str) -> bool:
    """`[ambiente].installa` è un URL git e non una cartella del progetto: la
    firma allora è il solo pin, senza albero (PBI-395, decisione 4)."""
    return installa.startswith("git+")


def _percorso(testo: str | None) -> Path | None:
    return None if testo is None else Path(testo).expanduser()


def _gate(sezione: _Sezione) -> Gate:
    return Gate(
        nome=sezione.testo("nome"),
        comando=sezione.testi("comando"),
        cwd=sezione.testo("cwd", default="."),
        solo_se_tocca=sezione.testi("solo_se_tocca", default=()),
    )


_MANCA = object()


class _Sezione:
    """Una tabella del TOML, che sa dire il proprio nome quando le manca qualcosa."""

    def __init__(self, dati: dict, file: str, nome: str = ""):
        self.dati, self.file, self.nome = dati, file, nome

    def _chiave(self, chiave: str) -> str:
        return f"[{self.nome}].{chiave}" if self.nome else f"[{chiave}]"

    def _valore(self, chiave: str, tipo: type, descrizione: str, default=_MANCA):
        valore = self.dati.get(chiave, _MANCA)
        if valore is _MANCA:
            if default is not _MANCA:
                return default
            raise ErroreDiConfigurazione(f"{self.file}: manca `{self._chiave(chiave)}`")
        # `bool` è un `int` per Python, e `attivo = 1` non è un modo di dire sì.
        if not isinstance(valore, tipo) or (tipo is int and isinstance(valore, bool)):
            raise ErroreDiConfigurazione(
                f"{self.file}: `{self._chiave(chiave)}` deve essere {descrizione}, "
                f"non {valore!r}")
        return valore

    def dentro(self, chiave: str, default=_MANCA) -> _Sezione:
        return _Sezione(self._valore(chiave, dict, "una sezione", default), self.file, chiave)

    def solo(self, *ammesse: str, perche: str) -> None:
        """Una chiave fuori da `ammesse` si ferma, nominandola."""
        for chiave in self.dati:
            if chiave not in ammesse:
                raise ErroreDiConfigurazione(
                    f"{self.file}: `{self._chiave(chiave)}` non è una chiave ammessa — {perche}")

    def elenco_di_sezioni(self, chiave: str) -> list[_Sezione]:
        elenco = self._valore(chiave, list, "un elenco di sezioni `[[…]]`")
        if not all(isinstance(voce, dict) for voce in elenco):
            raise ErroreDiConfigurazione(
                f"{self.file}: `{self._chiave(chiave)}` deve essere un elenco di sezioni `[[…]]`")
        return [_Sezione(voce, self.file, chiave) for voce in elenco]

    def testo(self, chiave: str, default=_MANCA) -> str:
        return self._valore(chiave, str, "una stringa", default)

    def testi(self, chiave: str, default=_MANCA) -> tuple[str, ...]:
        elenco = self._valore(chiave, list, "un elenco di stringhe", default)
        if not all(isinstance(voce, str) for voce in elenco):
            raise ErroreDiConfigurazione(
                f"{self.file}: `{self._chiave(chiave)}` deve essere un elenco di stringhe")
        return tuple(elenco)

    def interi_per_nome(self, chiave: str, default=_MANCA) -> dict[str, int]:
        tabella = self._valore(chiave, dict, "una tabella di numeri interi", default)
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in tabella.values()):
            raise ErroreDiConfigurazione(
                f"{self.file}: `{self._chiave(chiave)}` deve essere una tabella di numeri interi")
        return dict(tabella)

    def intero(self, chiave: str, default=_MANCA) -> int:
        return self._valore(chiave, int, "un numero intero", default)

    def positivo(self, chiave: str, default=_MANCA) -> int:
        """Un intero sopra lo zero: un tetto di zero minuti scadrebbe a ogni chiamata."""
        valore = self.intero(chiave, default)
        if valore <= 0:
            raise ErroreDiConfigurazione(
                f"{self.file}: `{self._chiave(chiave)}` deve essere positivo, non {valore!r}")
        return valore

    def booleano(self, chiave: str, default=_MANCA) -> bool:
        return self._valore(chiave, bool, "`true` o `false`", default)
