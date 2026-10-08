# AGENTS.md — asdlc

> **Progetto:** il runner ASDLC — il runner dei PBI, il tick della coda, il server dell'esito,
> i prompt dei ruoli e la guardia di fase — come pacchetto Python installato da un tag git.
> Nasce da aDa Controller, estratto con la sua storia (`ADR-0026`).

Il metodo sta qui sotto, nella sua parte; il lavoro da fare sta in `backlog/`, le decisioni
con le loro alternative in `decisions/`. Il file è in due parti (`ADR-0028` di aDa): `## Metodo`
vale identica in ogni progetto che usa il runner, `## Dominio` è di questo repository.

## Metodo

Il gate CI è la verità.

### Confini di giudizio

**MAI**
- Un hard-block nel flusso operativo: si segnala con un avviso e si lascia passare
  (`decisions/ADR-0008-osserva-e-segnala.md`).
- Una regola abrogata cancellata: resta scritta, barrata, con l'ADR che la abroga e la
  condizione che la farebbe rivedere (`decisions/ADR-0011-dati-reali-nel-repository.md`).
- Un esito ricavato dal testo libero di un modello. Ciò che il codice decide da un agente
  passa per una chiamata a strumento o per un output strutturato validato, senza ripiegare
  sul testo (`decisions/ADR-0027-gli-esiti-passano-per-chiamate-a-strumento.md`).

**CHIEDI**
- Quando la spec è ambigua: si scrive la domanda nel PBI, non si sceglie in silenzio.
- Prima di modificare **questo file**, o di scrivere un ADR che abroga un'istruzione del
  proprietario: serve la ratifica di Francesco, scritta nell'intestazione dell'ADR — e la
  ratifica **è il merge** (`decisions/ADR-0012-ratifica-dei-cambi-di-costituzione.md`).
  Chi beneficia di una decisione non la firma.

**SEMPRE**
- Test-first: RED → GREEN → REFACTOR. Il test che fallisce si scrive prima, e si scrive
  **solo il codice che lo fa passare**: ciò che si anticipa non lo si potrà più dimostrare.
  Nel giro del runner il permesso di scrivere produzione lo dà il rosso osservato, non la
  parola di chi lo scrive (`decisions/ADR-0021-il-rosso-si-chiede-prima.md`).
- La spec si aggiorna nello **stesso commit** del codice che ne cambia il comportamento.
- **Micro-commit**: si committa ogni pezzo che sta in piedi da solo (un test, una funzione
  che compila, un modulo che passa il lint) — una coppia RED→GREEN **per criterio** del PBI,
  quindi sedici commit su un PBI da otto criteri. Un commit unico finale non è un punto di
  ripristino. Lo squash, se serve, è al merge.
- Allargare lo **Scope** di un PBI è lecito; farlo in silenzio no. La deroga si dichiara
  nel commit che la introduce, con cosa, perché e cosa non cambia
  (`decisions/ADR-0015-la-deroga-allo-scope-si-dichiara.md`).
- Commit in italiano, Conventional Commits: `tipo(scope): descrizione imperativa`
  (`feat` `fix` `test` `refactor` `chore` `docs` `ci` `build`; gli scope sono del progetto,
  in `## Dominio`).

### Mappa del contesto

```yaml
contesto-agente:
  AGENTS.md:      questo file (CLAUDE.md ne è un symlink)
  specs/:         una cartella per dominio, sempre spec.md — lo stato (come funziona)
  backlog/:       PBI-XXX.md — il delta (cosa cambia)
  decisions/:     ADR-XXXX-*.md — le scelte e le alternative scartate
```

### Personas

Quando serve una lettura avversariale (spec ambigua, PR grossa) si usa
`.claude/skills/asdlc/patterns/adversarial-code-review.md` della skill ASDLC, non un
ruolo cablato qui.

## Dominio

- **Il prodotto è il runner.** Il codice sta in `tools/asdlc/`, i test in `tools/tests/`,
  i prompt dei ruoli in `tools/asdlc/prompt/`; la plancia in `tools/plancia/` non è scritta.
- **Il runner che lavora è quello installato, mai la copia di lavoro.** Il tick e i giri di
  questo repository girano col pacchetto installato dal pin di `asdlc.toml`
  (`[ambiente].installa`); una correzione al runner diventa attiva al tag successivo, e il
  tag è la release (`ADR-0026`, decisioni 1 e 3).
- **Toolchain:** `python3 -m pytest -q tools/tests` con un venv che ha `pytest` sul `PATH`;
  è l'unico gate di `asdlc.toml` e l'unico job della CI.
- **Scope dei commit:** `runner` `coda` `config` `esito` `prompt` `hook` `plancia` `ci` `kb`
  `template` (`decisions/ADR-0028-lo-scope-template.md`).
- **La KB** (`.claude/skills/asdlc/`) è una copia di villetakanen/asdlc-io (MIT) allo sha
  di `UPSTREAM`; il comando che la rigenera resta in aDa per la `v0.1.0` (D8).
