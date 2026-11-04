"""`asdlc-panoramica`: i PBI di ogni progetto in markdown, in sola lettura (PBI-538).

Per ogni progetto i PBI divisi in in corso, in coda, fatti e fuori coda, col titolo
e i criteri spuntati. Non è una seconda verità: i dati vengono dalle funzioni del
tick (`coda.leggi_voci()`, `coda.pbi_mergiati()`, `coda.pbi_con_ramo()`,
`coda.pr_sul_ramo()`), e gli argomenti, l'elenco dei progetti e la riga di stato
da `asdlc-stato`. Non prende il lucchetto del tick, non fa `fetch` e non scrive
né il log né il registro.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from asdlc import coda, stato

NESSUNO = "- nessuno"

# Le caselle di un criterio, spuntata o no.
RE_CRITERIO = re.compile(r"^\s*-\s+\[([ xX])\]")
# L'intestazione che chiude la sezione `## Verifica`: la `#` o la `##` seguente.
RE_FINE_SEZIONE = re.compile(r"^#{1,2}\s")


def file_dei_pbi(checkout: Path) -> dict[str, Path]:
    """I file di `backlog/` col nome del modello `[backlog].file`, per PBI: il
    primo in ordine di nome, come in `coda.avviso_domande()`."""
    modello = coda.asdlc_config.regex_del_modello(coda.CFG.backlog.file)
    trovati: dict[str, Path] = {}
    for file in sorted((checkout / coda.BACKLOG).iterdir()):
        if file.is_file() and (nome := modello.fullmatch(file.name)) is not None:
            trovati.setdefault(coda.CFG.backlog.id_di(nome.group("n")), file)
    return trovati


def in_ordine_di_numero(pbi: set[str]) -> list[str]:
    return sorted(pbi, key=lambda p: int(coda.CFG.backlog.numero(p) or 0))


def titolo_di(testo: str, pbi: str) -> str:
    """La prima riga `# <PBI>: <titolo>`, senza il prefisso; senza, la prima `# `."""
    for riga in testo.splitlines():
        if riga.startswith("# "):
            titolo = riga[2:].strip()
            prefisso = f"{pbi}:"
            return titolo[len(prefisso):].strip() if titolo.startswith(prefisso) else titolo
    return ""


def criteri_di(testo: str) -> tuple[int, int]:
    """`(spuntati, tutti)` delle caselle della sola sezione `## Verifica`."""
    spuntati = tutti = 0
    dentro = False
    for riga in testo.splitlines():
        if RE_FINE_SEZIONE.match(riga):
            dentro = riga.lstrip("#").strip() == "Verifica"
            continue
        if dentro and (casella := RE_CRITERIO.match(riga)) is not None:
            tutti += 1
            spuntati += casella.group(1) != " "
    return spuntati, tutti


def riga_del_pbi(pbi: str, file: Path | None, pr: str | None = None) -> str:
    """`**PBI-XXX** — <titolo> · criteri <x>/<y>`, la PR se c'è, e `· ❓` se il
    PBI ha una sezione di domande (decisioni 3 e 5)."""
    if file is None:
        pezzi = [f"**{pbi}** — (file mancante)", "criteri 0/0"]
        testo = ""
    else:
        testo = file.read_text(encoding="utf-8")
        spuntati, tutti = criteri_di(testo)
        pezzi = [f"**{pbi}** — {titolo_di(testo, pbi)}", f"criteri {spuntati}/{tutti}"]
    if pr is not None:
        pezzi.append(f"PR {pr}")
    if coda.RE_DOMANDE.search(testo):
        pezzi.append("❓")
    return " · ".join(pezzi)


def pr_di(checkout: Path, pbi: str) -> str:
    pr = coda.pr_sul_ramo(checkout, pbi)
    return "?" if pr is None else ", ".join(pr) or "-"


def guasto_in_riga(guasto: coda.Guasto) -> str:
    """Il messaggio del `Guasto` per intero in una riga: comincia già con ciò che
    non ha risposto (`gh non risponde`, `git non parla con`)."""
    return f"- ? {' '.join(str(guasto).split())}"


def sezioni(checkout: Path) -> list[str]:
    """Le quattro sezioni di un progetto (decisione 4). `gh` o `origin` che non
    rispondono lasciano la loro sezione con un `- ?` (`gh` muto sulle PR mergiate
    anche Fuori coda), e le voci si trattano come non fatte e senza ramo
    (decisione 6)."""
    coda.configura(coda.asdlc_config.carica(checkout))
    voci = coda.leggi_voci((checkout / coda.CODA).read_text(encoding="utf-8"))
    file = file_dei_pbi(checkout)
    guasto_fatti = guasto_rami = None
    try:
        mergiati = coda.pbi_mergiati(checkout)
    except coda.Guasto as guasto:
        mergiati, guasto_fatti = set(), guasto
    try:
        rami = coda.pbi_con_ramo(checkout)
    except coda.Guasto as guasto:
        rami, guasto_rami = set(), guasto

    in_corso: list[str] = []
    in_coda: list[str] = []
    numero = 0
    for voce in voci:
        if isinstance(voce, coda.VoceBarriera):
            in_coda.append(f"- ‖ {voce.testo}")
        elif voce.pbi in mergiati:
            continue
        elif voce.pbi in rami:
            pr = pr_di(checkout, voce.pbi)
            in_corso.append(f"- {riga_del_pbi(voce.pbi, file.get(voce.pbi), pr)}")
        else:
            numero += 1
            in_coda.append(f"{numero}. {riga_del_pbi(voce.pbi, file.get(voce.pbi))}")
    if guasto_rami is not None:
        in_corso = [guasto_in_riga(guasto_rami)]

    if guasto_fatti is not None:
        fatti = [guasto_in_riga(guasto_fatti)]
    else:
        fatti = [f"- {riga_del_pbi(p, file[p])}"
                 for p in in_ordine_di_numero(mergiati & set(file))]

    # Senza `gh` il «non fatto» non si sa: i file elencati mostrerebbero lavoro
    # fatto come lavoro da fare, e Fuori coda ha la riga del guasto (decisione 6).
    if guasto_fatti is not None:
        fuori = [guasto_in_riga(guasto_fatti)]
    else:
        in_coda_o_fatti = {v.pbi for v in voci if isinstance(v, coda.VocePbi)} | mergiati
        fuori = [f"- {riga_del_pbi(p, file[p])}"
                 for p in in_ordine_di_numero(set(file) - in_coda_o_fatti)]

    righe: list[str] = []
    for titolo, contenuto in (("In corso", in_corso), ("In coda", in_coda),
                              ("Fatti", fatti), ("Fuori coda", fuori)):
        righe += [f"## {titolo}", *(contenuto or [NESSUNO])]
    return righe


def markdown_di(checkout: Path) -> str:
    """La sezione `# <nome>` di un progetto. Un progetto che non si legge ha la
    sola riga di `stato.riga()`, «non raggiungibile», e non ferma gli altri
    (decisione 6, `ADR-0008`)."""
    dato = stato.stato_o_guasto(checkout)
    intestazione = [f"# {dato['progetto']}", "", stato.riga(dato)]
    if dato["decisione"].startswith(stato.NON_RAGGIUNGIBILE):
        return "\n".join(intestazione)
    try:
        return "\n".join([*intestazione, "", *sezioni(checkout)])
    except Exception as guasto:  # noqa: BLE001 — qualunque guasto è di quel progetto
        motivo = coda.in_una_riga(str(guasto) or type(guasto).__name__)
        return "\n".join([f"# {dato['progetto']}", "",
                          f"{dato['progetto']} · {stato.NON_RAGGIUNGIBILE} — {motivo}"])


def main(argv: list[str] | None = None) -> int:
    """Gli argomenti e le uscite di `asdlc-stato` (decisione 1)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("nome", nargs="?",
                    help="il progetto da mostrare, cioè la cartella del suo checkout; "
                         "senza, tutti quelli di ~/.config/asdlc/progetti.toml")
    ap.add_argument("--repo", type=Path,
                    help="il checkout di un progetto, senza passare dall'elenco")
    a = ap.parse_args(argv)
    if a.repo is not None:
        checkout = [a.repo]
    else:
        try:
            checkout = stato.progetti()
        except stato.ElencoIlleggibile as guasto:
            print(f"asdlc-panoramica: {guasto}", file=sys.stderr)
            return 2
        if a.nome is not None:
            checkout = [c for c in checkout if stato.nome_di(c) == a.nome]
            if not checkout:
                print(f"asdlc-panoramica: nessun progetto «{a.nome}» in "
                      f"{stato.file_dei_progetti()}", file=sys.stderr)
                return 2
    print("\n\n".join(markdown_di(c) for c in checkout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
