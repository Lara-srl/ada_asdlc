# specs/ — lo stato

Una spec dice **come funziona** un dominio, oggi: è lo stato del sistema, non il
cambiamento. Il cambiamento sta in `backlog/`, e punta qui invece di copiare.

**Una cartella per dominio, sempre `spec.md`**: `specs/<dominio>/spec.md`. Il modello è
[`TEMPLATE.md`](TEMPLATE.md): un *Blueprint* (contesto, architettura, vincoli) e un
*Contratto* (definition of done, guardie di regressione, scenari, domande aperte). Il Critic
legge il contratto, e giudica il diff contro quello.

**La spec si aggiorna nello stesso commit del codice che ne cambia il comportamento**: una
spec che dice una cosa e un codice che ne fa un'altra sono due fonti, e la seconda vince in
silenzio. I vincoli si scrivono **al positivo**, come fatti sul sistema; un fallimento già
visto diventa uno scenario del contratto, non un avvertimento.

**Un modello è vivo**: se una sezione resta vuota tre volte di fila nelle spec vere, si
toglie dal modello.
