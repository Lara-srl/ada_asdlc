# AGENTS.md — [nome del progetto]

> **Progetto:** [una riga: cosa fa, per chi, e dove gira].

Il metodo sta qui sotto, nella sua parte; il lavoro da fare sta in `backlog/`, le decisioni
con le loro alternative in `decisions/`. Il file è in due parti: `## Metodo` vale identica
in ogni progetto che usa il runner, e si tiene uguale a quella del repository del pacchetto
`asdlc`, da cui questo file è stato copiato; `## Dominio` è di questo progetto, e la scrive
chi lo apre. Le parentesi quadre dicono cosa ci va.

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

### Toolchain

[Il comando di ogni gate di `asdlc.toml`, con il venv che deve avere i suoi eseguibili sul
`PATH`: è il gate CI, e la CI gira gli stessi comandi.]

### Confini di giudizio

[I MAI, i CHIEDI e i SEMPRE di questo progetto, oltre a quelli del metodo: cosa l'agente qui
non fa mai, su cosa si ferma a chiedere, cosa fa sempre. Con l'ADR che li ha decisi.]

### Sorgenti

[Dove sta il codice, dove i test, dove le spec e i prompt: una riga per cartella, con cosa
ci va e cosa no.]

### Scope dei commit

[Gli scope di `tipo(scope): descrizione`, uno per area del progetto, in una riga.]
