# ADR-0020: il registro dei tempi esce dai branch

**Stato:** **Accettata** · **Data:** 2026-08-29 · **Decisa da:** Francesco, 29/08/2026 —
*«il CSV esce dai branch e si scrive su `main` dopo il merge»*.

## Contesto

`runs/tempi.csv` è il registro dei giri del runner: una riga per PBI eseguito, con i tempi
scomposti. È **versionato** apposta — è la base su cui si fattura l'ingegnere-agente — ed è
**append-only**.

Finché a scriverlo è stato il giro, la riga nasceva **dentro il worktree del PBI**, cioè sul
branch. Ogni branch nato prima che la riga di un altro giro entrasse in `main` scriveva la
**stessa ultima riga** del file, e la PR si presentava `CONFLICTING` su un file che il PBI
non aveva mai toccato. Successo due volte il 27/08 — PBI-326, poi PBI-306 — e la cura era
sempre la stessa: risolvere il conflitto tenendo **tutte** le righe, in ordine di `iniziato`.
Una riga persa in un conflitto è un giro che non è mai esistito.

Il difetto 12 di `PBI-102` proponeva di committare il registro a **fine invocazione** invece
che a fine giro. Non è una cura: alza la frequenza con cui due giri toccano la coda dello
stesso file versionato, cioè peggiora esattamente ciò che il difetto 19 descrive. I due
difetti sono lo stesso difetto guardato da due lati, e si chiudono insieme.

## Decisione

**Il registro non si scrive più dal branch.** Un giro lascia solo il suo rapporto
`runs/<run>.json` — gitignored, per-run, un file che nessun altro giro tocca — e lo aggiorna
dopo ogni PBI concluso (difetto 17).

**Le righe entrano in `main` dopo il merge**, con un comando che si lancia lì:

```bash
python3 tools/asdlc_runner.py --registra ~/ada-run/runs
```

`registra()` legge i rapporti, salta i `saltato` (niente tempo, niente riga), scarta ciò che
il CSV ha già — la chiave è `(run, pbi)`, quindi rilanciarlo è innocuo — e appende il resto
**in ordine di `iniziato`**, che è l'ordine in cui i giri sono accaduti e non quello in cui
qualcuno si è ricordato di registrarli.

**Il commit lo fa una persona**, con la sua PR `chore(ci): registra i giri`. È la forma che
il repository usava già a mano (PR #129, #136): qui cambia solo che le righe non se le
scrive più a mano nessuno.

## Conseguenze

**Positive**
- Un file versionato in meno da toccare su ogni branch: il conflitto del difetto 19 non ha
  più dove nascere, e la PR di un PBI torna a contenere **solo** il PBI.
- Il registro si può ricostruire: i rapporti restano sulla macchina, e `--registra` è
  idempotente. Un giro dimenticato si recupera il giorno dopo.
- La riga di un PBI **respinto o fermato** entra lo stesso, perché entra dal rapporto e non
  dalla PR: il tempo speso male è tempo speso, e toglierlo renderebbe il totale più bello e
  meno vero.

**Negative**
- **Il registro non si aggiorna da solo.** Fra il merge e il `--registra` il CSV è indietro,
  e un `--riepilogo` in quella finestra mostra meno ore di quelle fatte. È il prezzo del
  fatto che nessuno scrive su `main` senza passare da una PR.
- I rapporti sono **gitignored e locali**: la macchina che ha fatto girare i PBI è l'unica
  che può registrarli. Se quella macchina si perde prima del `--registra`, i giri si
  perdono con lei.

**Neutre**
- `runs/tempi.csv` resta versionato, con le stesse colonne: `--riepilogo` non cambia di un
  byte, e le righe scritte a mano fino al 29/08 restano valide.

## Alternative considerate

- **Committare il registro a fine invocazione** (difetto 12, come scritto). Scartata: è la
  causa travestita da cura — più commit sullo stesso file condiviso, più conflitti.
- **Togliere `runs/tempi.csv` dal versionamento** e tenerlo solo locale. Scartata: è il
  registro su cui si fattura, e un registro che vive su un disco solo non è un registro.
- **Un workflow su `push` a `main` che scrive la riga**. Scartata per ora: i rapporti stanno
  sulla macchina di chi lancia, non su GitHub, e farceli arrivare vorrebbe dire pubblicare
  anche i rilievi del Critic. Resta la strada se un giorno il runner girerà in cloud.
- **Una riga per PBI dentro la PR del PBI stesso**, come faceva il Builder. È la situazione
  di partenza: è il difetto.
