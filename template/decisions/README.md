# decisions/ — le decisioni, con le alternative scartate

Un ADR si scrive quando la scelta **vincola il lavoro futuro** e aveva alternative
ragionevoli. Non si scrive per ciò che è già in una spec, per ciò che è reversibile con un
rename, o per ciò che non aveva alternative.

**Il modello è [`TEMPLATE.md`](TEMPLATE.md)**: nome `ADR-NNNN-titolo-in-kebab.md`, col
prossimo numero libero; sezioni Contesto · Decisione · Conseguenze (positive/negative/neutre)
· Alternative considerate; e nell'intestazione la riga della ratifica,
`**Ratificata da** … **il** …`. Una decisione che ne sostituisce un'altra non la cancella: la
marca *Superata da ADR-XXXX*. Chi beneficia di una decisione non la firma, e la ratifica è
il merge (`ADR-0012`).

**Una regola di gate o di giro risponde a quattro domande**, obbligatorie, nella sezione
Decisione. Vale per un ADR nuovo e per la revisione di uno esistente:

1. **cosa si controlla**: il test, il commit, il ramo, il file, lo stato;
2. **quando**: in quale momento del giro, e su quale albero o commit;
3. **cosa conta come prova**: cosa fa passare, detto in modo che lo decida il codice
   (un'asserzione, un codice d'uscita, un campo di un rapporto);
4. **cosa succede se manca**: se si ferma o si segnala, con quale esito, e chi lo legge.

Una domanda senza risposta la sceglie chi implementa, cioè l'agente, in silenzio.
