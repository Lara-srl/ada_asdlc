# Registro dei precedenti

Le decisioni di Francesco che fanno precedente, quelle che il Solver legge **prima di
chiedere** (`specs/solver-e-rilascio/spec.md`, R12). Solo in aggiunta: una riga non si
cancella né si riscrive. Una decisione superata si barra (`~~riga~~`) e si cita la nuova, come
le regole abrogate (`decisions/ADR-0011-dati-reali-nel-repository.md`).

Una riga per decisione, in questo formato:

`- AAAA-MM-GG · <causa o ruolo> · <sentenza in una frase> · <riferimento: PR, ADR o PBI>`

Le cinque righe del 16/10 sono le decisioni di `ADR-0030`: stanno qui come esempio del
formato, non come precedenti di merito. Quella del 15/10 è un precedente vero.

- 2026-10-15 · runner-* · un limite del runner si corregge con un PBI in `asdlc`, non a mano · PBI-505
- 2026-10-16 · solver · il ciclo Solver↔Builder ha un tetto di 3 giri per lo stesso blocco · ADR-0030
- 2026-10-16 · tick · il battito del tick tace oltre 30 minuti prima che parta l'avviso · ADR-0030
- 2026-10-16 · solver · il registro dei precedenti sta in `backlog/PRECEDENTI.md` · ADR-0030
- 2026-10-16 · solver · la PR a monte si apre da un fork di `asdlc`, senza permessi di scrittura sul repository · ADR-0030
- 2026-10-16 · runner-* · l'elenco delle cause `runner-*` sta in `backlog/README.md` di `asdlc` · ADR-0030
- 2026-10-25 · critic · un rilievo di sola storia dei commit non fa `non pronto`: va sotto «Note per chi mergia», e il rimedio non è mai un rebase, prima o dopo la pubblicazione del ramo · PBI-525
- 2026-10-25 · critic · un rilievo di correttezza su un dato utente riporta l'intera classe verificata, non un caso per passaggio · PBI-525
- 2026-10-25 · tick · l'avviso di un giro fermo è una issue di GitHub nel repository del progetto, una sola per PBI e motivo · PBI-525
- 2026-10-25 · rosso-mai-visto · un test nato verde su un comportamento che vive in un file `.sql` passa non verificato se il commit porta `Verde-per-costruzione: <motivo>` e il ramo tocca un `.sql`; fuori dall'SQL ferma come prima · PBI-526, ADR-0022 (revisione del 25/10)
- 2026-10-25 · criteri · un criterio che solo una persona può giudicare si marca `(a vista)`: niente sonda né test, il Critic non blocca, lo spunta chi mergia · ADR-0032
- 2026-10-25 · rilascio · una PR che accoda o scrive un PBI non si intitola `PBI-XXX:` e non nasce da `pbi/`, finché PBI-528 non è in main · PBI-528
- 2026-10-25 · merge · il merge di una PR di giro è del tick alle condizioni di `ADR-0033`; `(a vista)`, costituzione, deroghe e PR non del runner restano di Francesco · ADR-0033
