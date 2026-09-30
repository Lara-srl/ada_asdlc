#!/usr/bin/env python3
"""`asdlc-chiudi-giro PBI-XXX`: un giro fermato si chiude con un comando (PBI-385).

Un giro fermato lascia un ramo su `origin`, e finché c'è il tick tiene la coda in
`attende`. Chiuderlo a mano erano sette comandi, e l'ordine contava: cancellare
il ramo prima di spegnere il tick toglieva la barriera, e il tick rilanciava il
PBI col testo vecchio (`PBI-365`, 23/09). I passi qui sono sei:

1. pausa: `~/asdlc-tick.pausa` creato, e il tick non lancia più;
2. tag `giro-fermato/<pbi>-giro<N>-<data>` sulla testa del rapporto del giro;
3. push del tag;
4. cancellazione del ramo su `origin`;
5. `ff-only` del checkout del tick;
6. pausa tolta.

Rilanciare il PBI non è di questo comando: lo fa il tick, al primo passaggio
dopo la riaccensione.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Lanciato per percorso, come il tick: `tools/` sul `sys.path`.
SORGENTE = Path(__file__).resolve().parent.parent
if str(SORGENTE) not in sys.path:
    sys.path.insert(0, str(SORGENTE))
from asdlc import coda  # noqa: E402
from asdlc import config as asdlc_config  # noqa: E402

# Il varco verso il mondo è quello del tick: un comando, una cartella, e un
# codice d'uscita invece di un'eccezione. È il nome che i test sostituiscono.
esegui = coda.esegui


def ultimo_rapporto(worktree: Path, pbi: str, run: str | None = None
                    ) -> tuple[str, dict] | None:
    """`(run, esito)` dell'ultimo `runs/<run>.json` dell'albero che nomina il PBI,
    o di `runs/<run>.json` se `run` è dato (PBI-385, decisione 2)."""
    cartella = worktree / coda.CFG.registro.cartella
    candidati = [cartella / f"{run}.json"] if run else sorted(cartella.glob("*.json"),
                                                              reverse=True)
    for file in candidati:
        try:
            dati = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(dati, dict):
            continue
        esiti = [e for e in dati.get("esiti", []) if isinstance(e, dict) and e.get("pbi") == pbi]
        if esiti:
            return dati.get("run", file.stem), esiti[-1]
    return None


class OriginMuto(RuntimeError):
    """`ls-remote` non ha risposto: cosa c'è su `origin` non si sa, e non si chiude."""


def chiedi_a_origin(comando: list[str], repo: Path) -> str:
    """L'uscita di una domanda a `origin`, o `OriginMuto` con ciò che git ha detto.
    Un errore letto come risposta vuota diventerebbe «nessun ramo», e un messaggio
    d'errore letto come risposta piena «il tag c'è già»."""
    codice, uscita = esegui(comando, repo)
    if codice != 0:
        raise OriginMuto(f"`{' '.join(comando)}` è uscito {codice}: {uscita.strip()[:200]}")
    return uscita


def rami_del_pbi(repo: Path, pbi: str) -> list[tuple[str, str]]:
    """`(ramo, sha)` dei rami di quel PBI su `origin`, letti come li legge il tick."""
    cartella = coda.PREFISSO_RAMO.rpartition("/")[0]
    uscita = chiedi_a_origin(
        ["git", "ls-remote", "--heads", coda.REMOTO, f"refs/heads/{cartella}/*"], repo)
    rami = []
    for riga in uscita.splitlines():
        sha, _, ref = riga.partition("\t")
        trovato = coda.RE_RAMO_PBI.match(ref.strip())
        if trovato is not None and coda.CFG.backlog.id_di(trovato.group(1)) == pbi:
            rami.append((ref.strip().removeprefix("refs/heads/"), sha.strip()))
    return rami


# Il suffisso che `nome_libero()` del runner dà al secondo giro in poi:
# `pbi/pbi-377` è il giro 1, `pbi/pbi-377-giro2` il 2.
RE_GIRO = re.compile(r"-giro(\d+)$")


def nome_del_tag(pbi: str, ramo: str, run: str) -> str:
    """`giro-fermato/<pbi>-giro<N>-<data>` (PBI-385, decisione 4): il PBI in
    minuscolo, il giro dal nome del ramo, la data del rapporto — le prime otto
    cifre del run, `AAAAMMGG` — e non quella di oggi."""
    trovato = RE_GIRO.search(ramo)
    giro = trovato.group(1) if trovato is not None else "1"
    return f"giro-fermato/{pbi.lower()}-giro{giro}-{run[:8]}"


def rifiuta(ragione: str) -> int:
    """Il comando non parte, e dice quale condizione e con quali valori. Esce
    con 2, come il runner che non parte: non è un passo fallito, perché nessun
    passo è cominciato."""
    print(f"Non chiudo: {ragione}")
    return 2


def smista(argv: list[str] | None = None) -> int:
    """`main()` a configurazione già letta: i test la chiamano da qui."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pbi", help="il PBI del giro fermato, per esempio PBI-377")
    ap.add_argument("--repo", type=Path, default=getattr(coda, "REPO", Path.cwd()),
                    help="il checkout del tick, da cui si parla con origin")
    ap.add_argument("--worktree", type=Path, default=coda.WORKTREE_DEL_RUNNER,
                    help="l'albero del runner, dove sta il rapporto del giro")
    ap.add_argument("--run", metavar="ID",
                    help="il rapporto runs/<ID>.json al posto dell'ultimo che nomina il PBI")
    ap.add_argument("--dry-run", action="store_true",
                    help="stampa i sei passi con i valori veri e non esegue niente")
    a = ap.parse_args(argv)

    # Prima di tutto, anche delle domande a `origin`: con un runner al lavoro
    # il giro non è fermo, e il suo ramo non si tocca. Lo stesso controllo del
    # tick, il `flock` sul lucchetto (PBI-373).
    if coda.giro_in_corso(a.worktree):
        return rifiuta(f"il lucchetto {a.worktree / coda.LUCCHETTO} è tenuto: in "
                       f"{a.worktree} c'è un runner al lavoro, e il giro non è fermo.")
    trovato = ultimo_rapporto(a.worktree, a.pbi, a.run)
    if trovato is None:
        dove = a.worktree / coda.CFG.registro.cartella
        return rifiuta(f"in {dove} non c'è un rapporto " +
                       (f"{a.run}.json " if a.run else "") + f"con un esito di {a.pbi}.")
    run, esito = trovato
    testa = esito.get("testa", "")
    if not testa:
        return rifiuta(f"il rapporto {run} di {a.pbi} non ha `testa`, e il tag non saprebbe "
                       "su quale commit andare. È un giro di prima di PBI-385 o un giro che "
                       "non ha pubblicato: si chiude a mano, con il file di pausa.")
    # Un solo ramo, e sulla testa: con due il tag andrebbe su un giro e si
    # cancellerebbe l'altro, e un ramo andato avanti dopo il rapporto non è più
    # il giro che il rapporto descrive (il tag di PBI-363, il 25/09).
    try:
        rami = rami_del_pbi(a.repo, a.pbi)
    except OriginMuto as muto:
        return rifiuta(f"{coda.REMOTO} non ha risposto — {muto}")
    if len(rami) != 1:
        trovati = ", ".join(f"{r} ({sha})" for r, sha in rami) or "nessun ramo"
        return rifiuta(f"su {coda.REMOTO} ci dev'essere un solo ramo di {a.pbi}, e ho "
                       f"trovato: {trovati}.")
    ramo, sha = rami[0]
    if sha != testa:
        return rifiuta(f"su {coda.REMOTO} {ramo} è {sha}, ma il rapporto {run} dice che la "
                       f"testa del giro è {testa}: il ramo è cambiato dopo il giro.")
    tag = nome_del_tag(a.pbi, ramo, run)
    try:
        sul_remoto = chiedi_a_origin(
            ["git", "ls-remote", "--tags", coda.REMOTO, f"refs/tags/{tag}"], a.repo)
    except OriginMuto as muto:
        return rifiuta(f"{coda.REMOTO} non ha risposto — {muto}")
    if sul_remoto.strip():
        return rifiuta(f"su {coda.REMOTO} c'è già il tag {tag}: il giro è già stato chiuso, "
                       "o un altro giro ne ha preso il nome. Spostarlo è un `push -f`, e "
                       "non lo faccio io.")

    # I passi da 2 a 5, col loro numero: il quinto, il `ff-only` del checkout
    # del tick, sono due comandi.
    passi = [
        (2, ["git", "tag", tag, testa]),
        (3, ["git", "push", coda.REMOTO, f"refs/tags/{tag}"]),
        (4, ["git", "push", coda.REMOTO, "--delete", ramo]),
        (5, ["git", "fetch", coda.REMOTO]),
        (5, ["git", "merge", "--ff-only", coda.BASE]),
    ]
    pausa = coda.file_di_pausa()
    if a.dry_run:
        print(f"1. pausa: {pausa}")
        for n, comando in passi:
            print(f"{n}. {' '.join(comando)}   (in {a.repo})")
        print(f"6. pausa tolta: {pausa}")
        return 0
    # Una pausa che c'era già è di qualcun altro, per un'altra ragione: non si
    # riscrive e non si toglie, perché riaccendere il tick non è di questo comando.
    di_prima = coda.pausa()
    if di_prima is None:
        pausa.write_text(f"{datetime.now():%Y-%m-%d %H:%M} asdlc-chiudi-giro {a.pbi}\n",
                         encoding="utf-8")
    # La pausa si toglie comunque, anche se un passo fallisce o alza: lasciata
    # indietro terrebbe il tick spento senza che nessuno lo sappia.
    try:
        for i, (n, comando) in enumerate(passi):
            print(f"{n}. {' '.join(comando)}")
            codice, uscita = esegui(comando, a.repo)
            if codice != 0:
                # Ci si ferma al primo passo fallito: senza il tag su `origin`,
                # cancellare il ramo perderebbe il giro.
                print(f"Passo fallito: `{' '.join(comando)}` (uscita {codice}): "
                      f"{uscita.strip()[:200]}")
                print(f"Restano da fare a mano, in {a.repo}:")
                for _, resto in passi[i:]:
                    print(f"  {' '.join(resto)}")
                return 1
    finally:
        if di_prima is None:
            pausa.unlink(missing_ok=True)
        else:
            print(f"Il tick resta in pausa, com'era prima: {di_prima} ({pausa}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Legge `asdlc.toml` dalla cwd, come il tick, e chiude il giro."""
    try:
        radice = asdlc_config.radice(Path.cwd())
        coda.configura(asdlc_config.carica(radice))
    except asdlc_config.ErroreDiConfigurazione as guasto:
        sys.exit(f"asdlc-chiudi-giro: {guasto}")
    coda.REPO = radice
    return smista(argv)


if __name__ == "__main__":
    raise SystemExit(main())
