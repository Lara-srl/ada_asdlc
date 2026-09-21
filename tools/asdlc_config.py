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

import tomllib
from dataclasses import dataclass
from pathlib import Path

NOME_FILE = "asdlc.toml"


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


@dataclass(frozen=True)
class Backlog:
    cartella: str
    coda: str
    id: str    # modello dell'id, `PBI-{n}`
    file: str  # modello del nome file, `PBI-{n}-{slug}.md`


@dataclass(frozen=True)
class Registro:
    cartella: str
    tempi: str


@dataclass(frozen=True)
class Ambiente:
    venv: str
    prestiti: tuple[str, ...]


@dataclass(frozen=True)
class Worktree:
    percorso: Path


@dataclass(frozen=True)
class Soglie:
    tentativi: int
    igiene: int
    revisioni: int


@dataclass(frozen=True)
class GateDelRosso:
    attivo: bool


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


def carica(repo: Path) -> Config:
    """La configurazione letta da `repo / asdlc.toml`."""
    return interpreta(leggi_toml(repo / NOME_FILE), NOME_FILE)


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
    return Config(
        git=Git(base=git.testo("base"), prefisso_ramo=git.testo("prefisso_ramo")),
        backlog=Backlog(cartella=backlog.testo("cartella"), coda=backlog.testo("coda"),
                        id=backlog.testo("id"), file=backlog.testo("file")),
        registro=Registro(cartella=registro.testo("cartella"), tempi=registro.testo("tempi")),
        ambiente=Ambiente(venv=ambiente.testo("venv"), prestiti=ambiente.testi("prestiti")),
        worktree=Worktree(percorso=Path(worktree.testo("percorso")).expanduser()),
        soglie=Soglie(tentativi=soglie.intero("tentativi"), igiene=soglie.intero("igiene"),
                      revisioni=soglie.intero("revisioni")),
        gate_del_rosso=GateDelRosso(attivo=gate_del_rosso.booleano("attivo")),
        gate=tuple(_gate(g) for g in sezione.elenco_di_sezioni("gate")),
    )


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

    def dentro(self, chiave: str) -> _Sezione:
        return _Sezione(self._valore(chiave, dict, "una sezione"), self.file, chiave)

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

    def intero(self, chiave: str) -> int:
        return self._valore(chiave, int, "un numero intero")

    def booleano(self, chiave: str) -> bool:
        return self._valore(chiave, bool, "`true` o `false`")
