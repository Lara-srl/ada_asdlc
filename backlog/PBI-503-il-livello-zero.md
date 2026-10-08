# PBI-503: il livello zero — `template/ZERO.md`, il metodo senza il runner

## Direttiva

Ultimo dei quattro PBI di `template/` (D5 di `SCAFFOLDING.md` di aDa; la riga «il livello
zero» di §I PBI che si spostano, Francesco 05/10/2026). Un progetto grosso può adottare ASDLC
**senza il pacchetto**: la struttura e il metodo, e niente runner. È il **livello zero**, il
gradino prima di `mvp` nella scala zero → `mvp` → `staged` → `prod` (§Dopo `v0.1.0` di
`SCAFFOLDING.md`): si sale soltanto, e il passaggio da zero a `mvp`, cioè l'installazione del
pacchetto, si fa con un ADR.

Nasce `template/ZERO.md`, il file d'ingresso di chi parte da zero. Dice **cosa si copia**,
**cosa non si copia**, e **cosa si aggiunge per salire a `mvp`**. Ogni file di `template/` è
in una delle due liste, e in una sola.

**Scope**
- `template/ZERO.md` — nuovo.
- `tools/tests/test_asdlc_template.py` — i test dei criteri.
- `backlog/PBI-503-il-livello-zero.md` — questo file, per la spunta.
- **Fuori scope:** gli altri file di `template/`, che non cambiano; una seconda copia di
  `AGENTS.md` per il livello zero (le righe da togliere le dice `ZERO.md`, non un file a
  parte); i profili `mvp` → `staged` → `prod` in `asdlc.toml`, che sono un PBI loro.

**Nessun file di produzione.** Il giro resta in `TEST_ONLY` dall'inizio alla fine e non
chiama mai `--chiedi-impl` (difetto 89 di `PBI-102`). Durante il giro il runner non lancia
nessun file dello Scope.

## ✅ Deciso, per non fermare il giro

1. **`ZERO.md` ha tre sezioni**: `## Si copia`, `## Non si copia`, `## Per salire a mvp`,
   nell'ordine. Nelle prime due ogni voce è una riga `- ` che comincia con un percorso fra
   backtick, relativo a `template/`, seguito da un trattino e dalla ragione in una riga. Un
   percorso che finisce con `/` vale per tutta la cartella. I test leggono le voci con una
   regex su `^- \`([^\`]+)\``.
2. **La divisione, file per file:**
   - **si copiano** `AGENTS.md` e `CLAUDE.md`, `backlog/README.md`, `backlog/TEMPLATE.md`,
     `backlog/CODA.md` (scritta e lanciata a mano), `decisions/README.md`,
     `decisions/TEMPLATE.md`, `specs/README.md`, `specs/TEMPLATE.md`,
     `.github/PULL_REQUEST_TEMPLATE.md`, `.github/workflows/ci.yml` (il gate CI è la verità
     anche a zero), e gli ADR di metodo che non parlano del runner: `0008`, `0009`, `0011`,
     `0012`, `0015`;
   - **non si copiano** `asdlc.toml`, `asdlc-aggiunte/`, `.claude/` (l'hook di fase),
     `runs/` (il registro dei tempi lo scrive il runner), `.gitignore` (le sue regole sono
     tutte del runner), `backlog/AUTOMAZIONE.md` (il tick e la riga di cron), e gli ADR del
     runner: `0017`, `0020`, `0021`, `0022`, `0024`, `0026`, `0027`.
   Gli ADR si nominano per percorso intero, `decisions/ADR-0008-osserva-e-segnala.md`, non
   per numero.
3. **`AGENTS.md` a zero perde le regole che esistono solo per il runner**: la frase di
   `SEMPRE` sul rosso chiesto prima («Nel giro del runner il permesso di scrivere produzione
   lo dà il rosso osservato…», `ADR-0021`) e la riga `MAI` sugli esiti dal testo libero
   (`ADR-0027`). `ZERO.md` le riporta **testualmente**, con gli stessi a capo, in un blocco citato ciascuna, sotto
   `## Si copia`, alla voce di `AGENTS.md`: chi copia le cancella a mano. Una citazione che
   non è più in `template/AGENTS.md` è un'istruzione che non si può eseguire, e il test la
   ferma.
4. **`## Per salire a mvp`** dice che il passaggio è un ADR ratificato col merge
   (`ADR-0012`), poi elenca in ordine: installare il pacchetto dal pin, copiare ciò che a zero
   non si era copiato, rimettere in `AGENTS.md` le righe tolte, accendere la riga di cron di
   `backlog/AUTOMAZIONE.md`. Nomina ogni voce di `## Non si copia`, per percorso.
5. **I criteri si scrivono in ordine, uno per commit RED→GREEN**: prima le due liste, poi le
   citazioni, poi `## Per salire a mvp`. Il file cresce un pezzo per criterio, e ogni test
   nasce rosso sul `ZERO.md` del commit prima.
6. **Ogni test asserisce prima che `template/ZERO.md` ci sia**, così su `main` il rosso è un
   fallimento per asserzione. Nessuna asserzione nelle fixture.
7. **Lo scope dei commit è `template`** (`ADR-0028`).

## Dipendenze
- Bloccato da: `PBI-502` (gli ADR copiati, `AGENTS.md`, la coda e `AUTOMAZIONE.md` che
  `ZERO.md` nomina), e quindi da `PBI-500` e `PBI-501`.
- Dopo questo, `template/` è completa per la `v0.2.0` (passo 4.3 del runbook di aDa).

## Contesto
- `backlog/SCAFFOLDING.md` di aDa, §I PBI che si spostano, la riga «il livello zero»: cosa si
  copia e cosa no, detto da Francesco; e §Dopo `v0.1.0`, il gradino zero. Il contenuto che
  serve è nella *Direttiva* e nelle decisioni qui sopra.
- `template/` com'è dopo `PBI-502`: i file da classificare.
- `template/AGENTS.md` — le due righe della decisione 3.
- `decisions/ADR-0012-…` — la ratifica col merge, per il passaggio a `mvp`.

## Verifica
- [x] **Ogni file di `template/` è in una lista sola di `ZERO.md`, ed è la divisione
      decisa.** Ogni file sotto `template/`, tranne `ZERO.md`, è nominato da una voce di
      `## Si copia` o di `## Non si copia` (per percorso, o per una cartella che lo contiene),
      e da una sola; ogni voce nomina un percorso che c'è; e le voci delle due liste sono
      quelle della decisione 2, né una di più né una di meno. Un criterio solo: la stessa
      scrittura delle due liste lo rende verde tutto.
- [x] **Le righe che a zero si tolgono da `AGENTS.md` ci sono davvero.** `ZERO.md` ha due
      blocchi citati, e il testo di ognuno, tolto il `> `, è una sottostringa di
      `template/AGENTS.md`.
- [ ] **Per salire a `mvp` si aggiunge ciò che a zero mancava, con un ADR.** La sezione
      `## Per salire a mvp` nomina ogni percorso di `## Non si copia` e la parola `ADR`.

**Non regressione:**
- La guardia di `PBI-500` resta verde con `ZERO.md`.
- I test di `PBI-500`, `PBI-501` e `PBI-502` restano verdi senza cambiare.
- `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura
Un file nuovo in `template/` entra in una delle due liste di `ZERO.md` nella stessa PR che lo
crea: il primo criterio lo fa diventare rosso finché non c'è.
