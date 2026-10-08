#!/usr/bin/env bash
# Il lucchetto ex ante, in forma di hook `PreToolUse` (PBI-104).
#
# Non decide niente da sé: passa il JSON di Claude Code al runner, che è dove
# vive la regola. `e_file_di_produzione` è la stessa funzione con cui il gate
# del rosso ferma un commit misto, e due copie della stessa regola — una in
# Python e una in shell — divergono al primo caso di bordo.
#
# `exec` perché il codice d'uscita del runner deve arrivare intatto a Claude
# Code: **solo `2` blocca**. Se `python3` non c'è, `exec` fallisce con 127, che
# non blocca — ed è il verso giusto in cui rompersi per un hook che sta davanti
# a ogni scrittura di ogni sessione.
#
# Il `cd` prima dell'`exec` perché il runner trova il progetto dalla cartella di
# lavoro, cioè dal primo `asdlc.toml` dalla cwd in su (PBI-382), e la cwd da cui
# Claude Code lancia un hook non è garantita. Il `pre-commit` di git non ne ha
# bisogno: parte già dalla radice dell'albero.
#
# Il runner si cerca prima installato, `<radice comune>/<pacchetto>/bin/asdlc-runner`
# (PBI-395): col pin di un tag `tools/asdlc/` nell'albero non c'è. `pacchetto` si
# legge da `asdlc.local.toml` e poi da `asdlc.toml`, con `tomllib` e una riga di
# Python, senza importare il pacchetto. Poi il sorgente dell'albero, in due forme,
# la nuova prima (PBI-388): `PBI-383` lo sposta in `tools/asdlc/runner.py`, e
# `python3` su un file che non c'è esce con 2.
set -uo pipefail
# Dentro un giro tace (PBI-384): il runner mette `ASDLC_GIRO=1` nella sessione
# del Builder e le passa con `--settings` la sua guardia di fase, che lancia il
# runner installato. Questo script, senza runner installato, lancia il sorgente
# dell'albero, cioè la copia di lavoro che il Builder sta cambiando, e resta per
# le sessioni delle persone.
[ "${ASDLC_GIRO:-}" = "1" ] && exit 0
radice="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$radice" || exit 1
comune="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"
comune="$(dirname "${comune:-$radice/.git}")"
installato="$(python3 -c 'import sys,tomllib,pathlib as p;d=[tomllib.loads(p.Path(f).read_text()).get("ambiente",{}) for f in ("asdlc.local.toml","asdlc.toml") if p.Path(f).is_file()];v=next((a["pacchetto"] for a in d if "pacchetto" in a),None);v and print(p.Path(sys.argv[1])/p.Path(v).expanduser()/"bin"/"asdlc-runner")' "$comune" 2>/dev/null)"
[ -n "$installato" ] && [ -x "$installato" ] && exec "$installato" --guardia-fase
for sorgente in tools/asdlc/runner.py tools/asdlc_runner.py; do
    [ -f "$radice/$sorgente" ] && exec python3 "$radice/$sorgente" --guardia-fase
done
# Nessuna delle due: lo si dice e non si blocca, perché una guardia che non trova
# il suo codice non deve fermare ogni scrittura (ADR-0008). Per Claude Code solo
# il 2 blocca.
echo "guardia del lucchetto: runner non trovato${installato:+ in $installato,} in tools/asdlc/runner.py né in tools/asdlc_runner.py" >&2
exit 1
