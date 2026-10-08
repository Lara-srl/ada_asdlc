PBI: `backlog/PBI-XXX-titolo-in-kebab.md`

Cosa cambia, in due righe. I gate deterministici li ha già passati la CI: qui manca l'unica
cosa che uno script non può dare, **l'accettazione umana**.

Prima del merge, guarda:

- [ ] i criteri della *Verifica* del PBI sono spuntati, e ognuno ha il suo test;
- [ ] il diff fuori dallo Scope del PBI è dichiarato nel commit che lo introduce (`ADR-0015`);
- [ ] la spec è aggiornata nello stesso commit del comportamento che cambia.
