
## Ripresa dopo il limite d'uso

Questo PBI non comincia adesso. Il giro precedente si è interrotto per il **limite d'uso
dell'account**, non per un errore tuo né del PBI, e il tick lo ha ripreso dopo il reset. Il
lavoro fatto fin lì è nel ramo su cui stai, già committato.

Prima di scrivere qualcosa, guarda dove era arrivato:

- `git log --oneline` dalla base del ramo: i commit RED e GREEN già fatti, criterio per criterio;
- le spunte della Verifica nel PBI: i criteri già chiusi.

Continua dal primo criterio non spuntato e non ancora committato, **senza rifare** ciò che è
già committato: un test già scritto non si riscrive, un GREEN già fatto non si ripete. Se il
lavoro è tutto lì, chiama `fatto` col riepilogo. Le regole di sopra valgono come sempre: il giro
riparte in `TEST_ONLY`, e il permesso di scrivere produzione te lo dà il rosso.
