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
