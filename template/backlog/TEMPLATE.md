# PBI-XXX: [titolo, cosa cambia]

<!--
Il file si chiama `PBI-XXX-titolo-in-kebab.md`. Un PBI è il delta, non lo stato: punta alle
spec invece di copiarle. Regole d'oro: atomico, auto-verificabile, isolato.
-->

## Direttiva

Cosa cambia e perché, in pochi paragrafi: il problema visto, dove, e cosa succede oggi.

**Scope**
- `percorso/del/file` — cosa ci cambia.
- `backlog/PBI-XXX-titolo-in-kebab.md` — questo file, per la spunta dei criteri.
- **Fuori scope:** ciò che resta com'è, e quale PBI lo prende.

Se il PBI tocca un file che il runner lancia durante il giro (il server dell'esito, un hook),
lo dice qui, e dice come il giro ci sopravvive.

## ✅ Deciso

1. **La scelta, in grassetto.** Perché, e quale alternativa si è scartata.

## Il giro N, e cosa si riprende

Si scrive solo dopo un giro fermato, e si riscrive a ogni giro. Nomina sempre il tag
`giro-fermato/…` del giro chiuso e gli sha da riprendere in ordine con `git cherry-pick`, con
quelli da lasciare e perché: il runner non riprende niente (fra un giro e l'altro; dentro il giro, dopo `risolto`, il Builder riprende: `PBI-517`) (dopo il limite d'uso il tick riprende il PBI: `PBI-519`), e crea un ramo nuovo dalla base.

## Dipendenze
- Bloccato da: [PBI-XXX, o nessuno].
- Blocca: [PBI-XXX, o nessuno].

## Contesto
- `specs/[dominio]/spec.md` — lo stato che questo PBI cambia.
- `decisions/ADR-XXXX-…` — le decisioni che vincolano il lavoro.

**Prima di accodare, rileggi:**
- **R** — ogni criterio può nascere rosso su `main`?
- **F** — il GREEN è scrivibile nella fase?
- **T** — un test esistente contraddice una decisione?
- **A** — qualcosa sporca l'albero o scrive fuori?
- **E** — un RED che non termina, flag doppi, nomi in conflitto?
- **D** — una decisione è lasciata al Builder, o manca una dipendenza?
- **N** — i nomi e i fatti citati sono veri nel codice?

## Verifica
- [ ] **Un comportamento osservabile, in grassetto.** Come lo si verifica, e perché fallisce
      sulla base prima del lavoro. Criteri che la stessa modifica minima rende verdi sono un
      criterio solo, con più esempi.

**Non regressione:**
- Le guardie: ciò che è già vero e deve restarlo, dichiarato come tale.
- La suite dei test resta verde: nessun test che c'è cambia.

## Protocollo di rifinitura
Cosa fare se un criterio si rivela ambiguo durante il giro: quale scelta è lecita senza
chiedere, e quale si scrive come domanda in questo file.
