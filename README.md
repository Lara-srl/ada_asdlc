# asdlc

Il runner ASDLC come pacchetto Python: fa girare i PBI di un progetto uno per volta con
`claude -p`, un contesto pulito per PBI, i **gate eseguiti dallo script** e il permesso di
scrivere produzione dato dal rosso osservato. Comandi installati:

| Comando | Cosa fa |
|---|---|
| `asdlc-runner` | un giro su un PBI, e la guardia di fase (`--guardia-fase`) per l'hook `PreToolUse` |
| `asdlc-coda` | il tick: legge `backlog/CODA.md` e lancia il PBI successivo quando il precedente è in `main` |
| `asdlc-chiudi-giro` | chiude un giro fermato: tag `giro-fermato/…`, ramo tolto |
| `asdlc-esito` | il server MCP dell'esito, da cui gli agenti dichiarano com'è andata (`ADR-0027`) |

## Da dove viene

Estratto da [aDa Controller](https://github.com/Lara-srl/ada_controller) al commit
**`683e2dd79d4a53fd39904b8e3e4bba66b5e47236`** (il commit `E` del runbook della Fase 5),
con `git filter-repo` e la storia dei nomi di prima dei traslochi: i messaggi dei commit
sono la documentazione dei difetti, e `backlog/PBI-102-…` è il loro registro.

## Come lo installa un progetto

Il progetto dichiara in `asdlc.toml` il venv e il pin, mai un ramo (`ADR-0026`):

```toml
[ambiente]
pacchetto = ".venv-asdlc"
installa = "git+ssh://git@github.com/Lara-srl/ada_asdlc@v0.1.0#subdirectory=tools"
```

Il tick reinstalla da solo quando il pin cambia: salire di tag è una PR che cambia quella
riga. La riga di cron, dal checkout principale del progetto, è in
[`backlog/AUTOMAZIONE.md`](backlog/AUTOMAZIONE.md).

## Sviluppo

```
python3 -m venv .venv && . .venv/bin/activate && pip install pytest
python3 -m pytest -q tools/tests
```

Il runner che lavora su questo repository è quello installato dall'ultimo tag, non la copia
di lavoro (`AGENTS.md`, `## Dominio`).
