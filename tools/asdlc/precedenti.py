"""Il registro dei precedenti: la regola «solo in aggiunta» (`backlog/PBI-506`).

`backlog/PRECEDENTI.md` si scrive solo aggiungendo righe: una riga non si cancella né si
riscrive, una decisione superata si barra (`~~riga~~`).
"""


def _barrata(riga):
    return riga.removeprefix("- ").startswith("~~")


def _barrando(riga):
    """La riga com'è dopo che l'hanno barrata: `- ~~corpo~~`, il rinvio segue."""
    return f"- ~~{riga.removeprefix('- ')}~~"


def righe_perse(vecchio, nuovo):
    """Le righe non barrate di `vecchio` che in `nuovo` non ci sono più, nell'ordine di `vecchio`.

    Una riga che in `nuovo` compare barrata non è persa: barrarla è la modifica lecita.
    """
    righe = nuovo.splitlines()
    presenti = set(righe)
    return [r for r in vecchio.splitlines()
            if r.strip() and not _barrata(r) and r not in presenti
            and not any(n.startswith(_barrando(r)) for n in righe)]
