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

## Gli ADR di metodo

I dodici ADR qui sotto sono le regole del runner, **copiati senza rinumerare** dal
repository del pacchetto `asdlc` e identici a quelli di là, byte per byte: nominano il
progetto in cui ogni regola è nata, perché è la loro storia, e un test di quel repository li
tiene uguali. I numeri che mancano sono decisioni di dominio di quel progetto, e non entrano.
**Il prossimo ADR, il primo di questo progetto, è lo 0028.**

| # | Decisione | Stato |
|---|---|---|
| [0008](ADR-0008-osserva-e-segnala.md) | Il prodotto osserva e segnala, non blocca | Accettata |
| [0009](ADR-0009-e2e-playwright-nel-gate.md) | Gli E2E Playwright girano dentro `ci.yml` | Accettata |
| [0011](ADR-0011-dati-reali-nel-repository.md) | Il repository è privato: i dati reali sono ammessi | Accettata |
| [0012](ADR-0012-ratifica-dei-cambi-di-costituzione.md) | Chi beneficia di una decisione non la firma: i cambi di costituzione li ratifica il proprietario | Accettata |
| [0015](ADR-0015-la-deroga-allo-scope-si-dichiara.md) | Allargare lo Scope di un PBI è lecito; farlo in silenzio no: la deroga si dichiara nel commit che la introduce | Accettata |
| [0017](ADR-0017-il-runner-e-un-prodotto-a-se.md) | Il runner ASDLC è un prodotto a sé: si estrae, non si riscrive (la forma dell'estrazione la decide 0026) | Accettata |
| [0020](ADR-0020-il-registro-dei-tempi-esce-dai-branch.md) | Il registro dei tempi esce dai branch: si scrive su `main` dopo il merge, con `--registra` | Accettata |
| [0021](ADR-0021-il-rosso-si-chiede-prima.md) | Il rosso si chiede prima, non si accerta dopo: il giro nasce in `TEST_ONLY` e la fase governa cosa si può scrivere | Accettata |
| [0022](ADR-0022-il-verde-che-morde-passa.md) | Un test nato verde passa il gate se morde: si mutano le righe che il branch ha cambiato e si rigira quel test | Accettata |
| [0024](ADR-0024-anti-pattern-nel-prompt-del-builder.md) | Gli anti-pattern stanno nel prompt del Builder | Accettata |
| [0026](ADR-0026-il-runner-e-un-pacchetto-installato-da-tag.md) | Il runner è un pacchetto installato da un tag git, non una fotocopia: prompt estesi e mai sostituiti, si lavora sempre con la versione installata, ogni giro registra la sua versione | Accettata |
| [0027](ADR-0027-gli-esiti-passano-per-chiamate-a-strumento.md) | Tra codice e modello gli esiti passano per chiamate a strumento, mai dal testo libero (aggiunge un MAI ad `AGENTS.md`) | Accettata |

`ADR-0017` cita `PBI-102` con un link a `../backlog/`, che qui non porta a niente: `PBI-102`
è il registro dei difetti del runner, nel repository del pacchetto. Il link resta rotto
perché la copia è identica.
