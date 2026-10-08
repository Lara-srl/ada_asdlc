# backlog/ — il delta

Un PBI è **il cambiamento**, non il dominio: transitorio, chiuso col merge. Lo stato del
sistema sta in `specs/`, e il PBI ci **punta** invece di copiarlo: una copia diventa obsoleta
il giorno dopo.

**Il modello è [`TEMPLATE.md`](TEMPLATE.md)**: si copia in `PBI-XXX-titolo-in-kebab.md` e si
riempie. Le sezioni sono Direttiva (con lo **Scope**) · ✅ Deciso · Il giro N, e cosa si
riprende · Dipendenze · Contesto (puntatori) · Verifica (spuntabile) · Protocollo di
rifinitura.

**Lo Scope contiene sempre il file del PBI stesso**, perché i suoi criteri si spuntano nel
giro che li chiude. Il Builder resta dentro lo Scope, e un PBI che non si nomina arriva in
`main` con la *Verifica* tutta a `[ ]`.
**Un PBI che tocca un file che il runner lancia durante il giro** (il server dell'esito, un
hook) lo dichiara nella *Direttiva*, e dice come il giro ci sopravvive.
**La risposta a un giro fermato nomina sempre il tag e i commit da riprendere**: il tag
`giro-fermato/…` del giro chiuso, e gli sha da riprendere in ordine con `git cherry-pick`, con
quelli da lasciare e perché. Il runner non riprende niente: crea un ramo nuovo dalla base, e
il Builder legge la ripresa nel PBI, nella sezione *Il giro N, e cosa si riprende*.
**Una decisione non chiede mai di cambiare un test nel GREEN.** In `IMPL` i test sono in sola
lettura (la guardia di fase di `ADR-0021`), quindi un test cambia nel commit RED, dichiarato
nel messaggio, o in `TEST_ONLY`.
Regole d'oro: **atomico** (o atterra tutto o niente), **auto-verificabile** (i suoi test
passano senza aspettare un altro PBI), **isolato** (non tocca i file di un PBI concorrente).

**Un criterio è un comportamento, non un esempio.** Criteri che la stessa modifica minima
rende verdi sono **un criterio solo con più esempi** — un test parametrico, con un id
esplicito per caso — perché il gate chiede un rosso per criterio, e un verde che ne chiude
tre lascia gli altri due nati verdi. E un criterio che dichiara un rosso lo si verifica
**caso per caso sulla base** prima di accodarlo: ogni input deve fallire da solo, per
asserzione, contro `main`. Un caso verde su `main` non è un criterio, è una **guardia**, e
va nella non regressione dichiarata come tale (`ADR-0022`).

## Eseguirli con un agente

Il runner (`asdlc-runner`) fa girare i PBI uno per volta con `claude -p`, contesto pulito
per PBI e **gate eseguiti dallo script**; il tick (`asdlc-coda`) li lancia nell'ordine di
[CODA.md](CODA.md). Girano sempre **installati dal tag** di `[ambiente].installa` in
`asdlc.toml`, mai dalla copia di lavoro (`ADR-0026`). Come si lancia la catena, e quanta
autonomia dare a un PBI, sta in [AUTOMAZIONE.md](AUTOMAZIONE.md).
