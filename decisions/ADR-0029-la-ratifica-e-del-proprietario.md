# ADR-0029: la ratifica dei cambi di costituzione è del proprietario del progetto

**Stato:** **Accettata** · **Data:** 2026-10-11 · **Ratifica:** Francesco, con il merge
(`ADR-0012`). **Cambia la costituzione**: nella parte `## Metodo` di `AGENTS.md` sostituisce un
nome con un ruolo, nella stessa PR, sia qui sia in `template/AGENTS.md`.

## Contesto

`AGENTS.md` chiede, prima di modificare il file o di abrogare un'istruzione del proprietario,
«la ratifica di Francesco». La regola è di `ADR-0012` e in aDa, dove è nata, il proprietario
è Francesco. Ma `## Metodo` «vale identica in ogni progetto che usa il runner» (`ADR-0028` di
aDa) e `template/AGENTS.md` è la copia che un progetto nuovo riceve alla nascita. In un
progetto che non è di Francesco la riga nomina una persona che non ha né la proprietà né il
merge, e il Critic che cerca la firma nell'intestazione non sa chi cercare.

## Decisione

Nella parte `## Metodo` di `AGENTS.md`, in questo repository e in `template/AGENTS.md`
(identiche), «la ratifica di Francesco» diventa **«la ratifica del proprietario del
progetto»**. Il proprietario è chi mergia le PR del progetto; l'ADR lo nomina
nell'intestazione, con nome e data, come già chiede `ADR-0012`. La sostanza di `ADR-0012`
non cambia: chi beneficia di una decisione non la firma, e la ratifica è il merge.

Gli ADR copiati in `template/decisions/` **restano come sono**: citano Francesco perché sono
la storia di aDa. In questo repository il proprietario è Francesco.

Le quattro domande (`decisions/README.md`):

1. **cosa si controlla**: la riga della ratifica in `AGENTS.md`, e che `## Metodo` sia
   identica fra la radice e `template/`;
2. **quando**: alla rilettura del Critic, come per ogni cambio di costituzione;
3. **cosa conta come prova**: nell'intestazione dell'ADR c'è il nome del proprietario del
   progetto e la data;
4. **cosa succede se manca**: lo segnala il Critic e il giro va avanti (`ADR-0008`).

## Conseguenze

- **Positive:** il template si copia senza correggere la riga; un progetto nuovo non eredita
  il nome di un altro.
- **Negative:** `AGENTS.md` di aDa ha ancora il nome, finché non lo allinea una sua PR: nel
  frattempo `## Metodo` non è identica fra aDa e qui.
- **Neutre:** `ADR-0012` non cambia e non è abrogato.

## Alternative considerate

- **Lasciare il nome e correggerlo a mano in ogni progetto.** Scartata: è una modifica di
  costituzione in ogni copia, e la prima che la dimentica ha una regola che nomina un estraneo.
- **Riscrivere anche gli ADR del template.** Scartata: perde la fedeltà con gli ADR originali
  di aDa, che citano persone vere in fatti veri.
