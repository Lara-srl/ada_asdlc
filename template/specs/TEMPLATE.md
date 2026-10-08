# Feature: [Nome del dominio]

> Stato: [bozza | attiva | in evoluzione]
> PBI aperti: [PBI-XXX, …] · ADR collegati: [ADR-XXXX, …]

## Blueprint

### Contesto
Uno o due paragrafi: perché esiste questo dominio, quale gesto reale sostituisce, cosa
succede se non c'è. Niente product brief.

### Architettura
- **API:** `VERBO /rotta` — cosa fa, cosa accetta, cosa torna. Percorsi veri, non descrizioni.
- **Modello:** entità e colonne che contano, con il file in cui vivono.
- **Dipende da:** [altre spec, servizi, tool] · **Ne dipendono:** [chi consuma questo]

### Vincoli
Regole enunciate **al positivo**, come fatti sul sistema: «i tool di scrittura passano dal
service», non «non scrivere in tabella». Dove un vincolo esiste per un fallimento già visto,
il fallimento si codifica in uno scenario del Contratto, non in un avvertimento.

## Contratto

### Definition of Done
- [ ] Criterio osservabile e verificabile da solo.

### Guardie di regressione
- Invarianti che restano veri **dopo** questo PBI e dopo i prossimi.

### Scenari

```gherkin
Scenario: [Nome descrittivo]
  Dato [stato di partenza]
  Quando [l'azione]
  Allora [esito osservabile]
```

Marca ogni scenario con il livello che lo verifica: `[unit]` `[api]` `[e2e]`.
Gli scenari di un livello hanno un test di quel livello.

### Domande aperte
| # | domanda | chi risponde | blocca? |
|---|---|---|---|
