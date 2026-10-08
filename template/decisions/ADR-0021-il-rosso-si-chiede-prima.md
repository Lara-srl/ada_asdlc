# ADR-0021: il rosso si chiede prima, non si accerta dopo

**Stato:** **Accettata** · **Data:** 2026-09-01 · **Ratifica:** Francesco, con il merge
(`ADR-0012`) — questo  ADR **irrigidisce** un SEMPRE di `AGENTS.md`, non lo abroga, ma ne
cambia il modo di applicazione e tocca il file della costituzione.

## Contesto

`PBI-103` ha dato al Quality Gate la seconda domanda: *quei test sono mai stati rossi?*
Il gate cammina i commit del branch, estrae ognuno che introduce test nuovi in un worktree
usa e getta, ci gira dentro **solo quei test** e attende il rosso. Funziona, ed è la sola
cosa che lega: il divieto scritto nel prompt non aveva fermato né `aa40167` (PBI-328) né
`f35abd1` (PBI-330).

Ma **guarda dopo**, e il conto di quel «dopo» è stato misurato su PBI-333:

| giro | esito | costo |
|---|---|---|
| 31/08, 17:36 | `fermato` — *rosso non isolabile* su `bb7e562`, `bbebb07` | 5 commit, 17 min |
| 01/09, 00:15 | `fermato` — *nato verde* su `638b587` | 9 commit, 24 min |

In tutti e due i casi il verdetto era giusto e il rimedio inesistente: *«il ciclo mancato è
ex ante e nessuna fix lo annulla»*. Due giri, 41 minuti di macchina, zero righe entrate in
`main`, e un PBI che alla terza sarebbe ripartito da capo.

**La causa non sta dove il gate ferma.** Nel giro del 01/09 il gate ha fermato `638b587`, il
commit che *aggiungeva* due test. Il fatto era successo tre commit prima, in `49d4f59`: 494
righe di `FoglioPage.tsx` con dentro

```tsx
onClick={() => navigate(`/pratiche/${riga.pratica_id}`)}
```

che nessuno dei undici test del commit precedente aveva chiesto. Il Builder aveva scritto la
pagina **intera** — il PBI la descrive intera — e mezz'ora dopo, rileggendo la checklist, ha
scritto il test del criterio ancora scoperto. Quel test nasce verde perché il codice c'era
già. Il gate multa la ricevuta, non il fatto.

Il prompt lo permetteva: *«scrivi PRIMA il test che fallisce, poi il codice che lo fa
passare»* non è *«solo il codice che lo fa passare»*, e *«3-5 commit»* su un PBI con otto
criteri è un invito ad accorpare per aritmetica. La regola giusta esisteva perfino nel
repository — `.claude/skills/tdd-feature/SKILL.md`, passo 3, *«implementa il minimo»* — in un
file che il Builder non apre mai.

## Decisione

**Il permesso di scrivere codice di produzione si guadagna sul rosso osservato, prima della
scrittura.** Il giro del runner nasce in fase `TEST_ONLY` e la fase governa cosa si può
scrivere:

```
TEST_ONLY   produzione in sola lettura   → non si implementa ciò che nessun rosso ha chiesto
   │        `--chiedi-impl` gira i test nati nell'albero: apre solo se falliscono
   ▼
IMPL        test in sola lettura         → il verde non si ottiene ammorbidendo l'asserzione
   │        il commit riporta il giro in TEST_ONLY (post-commit)
   ▼
TEST_ONLY   e si ricomincia dal criterio dopo
```

Tre livelli, con mestieri diversi e nessuno ridondante:

1. **`PreToolUse` di Claude Code** (`.claude/hooks/fase-tdd.sh`) — blocca `Edit` e `Write`
   fuori fase con `exit 2` e **spiega**: l'agente legge la ragione e cambia mossa nello
   stesso turno. È il livello veloce, quello che rende il blocco un'istruzione invece di una
   fermata;
2. **`pre-commit` di git** — guarda lo **stage**, non lo strumento. `Edit`, `Write`, un
   heredoc da Bash, `sed -i`, una patch applicata a mano: finiscono tutti lì, e lì valgono
   uguale. È il livello invalicabile;
3. **il gate del rosso di `PBI-103`** — resta dov'è, a fine giro. Adesso è la rete: copre il
   lavoro fatto a mano, i branch recuperati, e qualunque strada che i primi due non vedano.

`--chiedi-impl` osserva il rosso **sull'albero non committato**. Effetto di lato che vale la
pena dire: il commit di soli test che ne segue è per costruzione quello che il gate di
PBI-103 vorrebbe — nessun file di produzione dentro, e il fallimento visto sull'albero esatto.

Il `PROMPT_BUILDER` cambia di conseguenza: il ciclo in quattro passi, il divieto di
anticipare, lo scheletro vuoto per i moduli nuovi, e il budget dei commit legato ai criteri
invece che a un numero.

## Conseguenze

**Il costo di un errore passa da un giro a un turno.** Il Builder che prova a scrivere la
pagina prima del test riceve subito la ragione, invece di scoprirlo 24 minuti dopo quando
non c'è più niente da correggere.

**I giri diventano più lunghi in commit e più corti in fermate.** Una coppia per criterio
significa sedici commit su un PBI da otto criteri, contro i nove di stanotte. È il verso
giusto: i commit sono punti di ripristino, le fermate no.

**Il lucchetto è inerte fuori da un giro.** `.claude/settings.json` sta nel repository e vale
per ogni sessione aperta qui dentro, quindi la guardia tace quando il file della fase non
c'è — e il file lo scrive solo il runner. *Emendato il 02/09:* stava nella radice del
worktree, gitignorato, e un `rm` o un `git clean -fdx` via Bash lo portava via a metà giro
lasciando il lucchetto inerte in silenzio. Sta ora nel git dir **di quel worktree**
(`git rev-parse --git-path asdlc-fase`), dove l'albero di lavoro non arriva.

**Un `pre-commit` di qualcun altro non si calpesta.** Se ce n'è già uno, il secondo livello
non si installa e restano il primo e il terzo. È una perdita dichiarata, non silenziosa.

**Il primo livello vive solo se il Builder gira nella modalità giusta.** Misurato il
01/09: con `--dangerously-skip-permissions` — e con `--permission-mode auto` — l'hook
`PreToolUse` **non viene chiamato affatto**, in silenzio, contro quello che la
documentazione dichiara per `bypassPermissions`. Il Builder gira in `acceptEdits` con
`Bash` permesso per nome, che è l'unica combinazione in cui può lavorare e il lucchetto
esiste. È una dipendenza dal comportamento di una versione di Claude Code, quindi va
riprovata quando la CLI cambia: il test che la fissa guarda i flag, non l'effetto.

**Resta scoperto il test che non morde.** Un test può essere rosso per la ragione sbagliata e
poi verde per la ragione sbagliata — asserzione debole, dato costruito perché l'errore non si
manifesti. Il lucchetto non lo vede; lo vedrebbe il mutation testing, che è la direzione
naturale del prossimo passo e non di questo.
**Chiuso il 01/09 da `ADR-0022`:** il test nato verde passa se morde.

## Alternative considerate

**Il tag `(GUARD)` / `(REGRESSION)` che esenta il commit dal gate.** Proposta esterna, e la
più tentante: l'agente dichiara «questo test protegge codice che esiste già» e il gate si
limita a chiedere che sia verde. Scartata perché **inverte PBI-103**: oggi il gate esamina
ogni commit che introduce test nuovi e non legge affatto l'etichetta `(RED)`; con il tag
sarebbe l'agente esaminato a decidere quali suoi commit vengono esaminati. Lo stesso Builder
che ha accorpato le due guardie avrebbe scritto `(GUARD)`. E il dato che ha fatto nascere
PBI-103 è esattamente questo: due autodichiarazioni su due, in tre giorni.

**Il mutation testing al posto del rosso storico.** Chiede *«questo test morde?»* invece di
*«è mai stato rosso?»*, ed è la domanda che ci interessa davvero — una guardia nata verde che
uccide il mutante è un buon test. Non scartata: **rimandata**. Costa O(mutanti × suite) anche
circoscritta alle righe toccate dal commit, e non risolve la causa a monte, che è il codice
scritto senza che nessuno l'avesse chiesto. Prima il lucchetto, che costa secondi.

**Il gate del rosso come job di `ci.yml`.** Chiude un buco vero — oggi la verifica esiste solo
se il runner arriva in fondo, quindi non tocca le PR aperte a mano come `#151` — ma è la stessa
autopsia spostata **dopo** il push, e non riduce di una le fermate del runner. Rimandata, e
resta da fare: `--gate-rosso origin/main..HEAD` esce già 0/1/2 apposta.

**Tre sessioni separate** (uno scrive i test, un altro implementa). È la forma forte della
separazione, e il playbook la suggerisce. Scartata per il costo: triplica le invocazioni per
criterio e va riconciliata con `-c`, che oggi tiene una sessione sola per tutto il giro. Gli
hook danno lo stesso vincolo **dentro** una sessione, che è il motivo per cui il permesso di
scrittura è più forte di un prompt: `PreToolUse` scatta anche sotto
`--dangerously-skip-permissions`, dove *«hooks provide the only safety gate»*.
