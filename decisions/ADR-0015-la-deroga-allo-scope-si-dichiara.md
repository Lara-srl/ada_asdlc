# ADR-0015: una deroga allo Scope si dichiara dove accade

**Stato:** **Accettata** · **Data:** 2026-08-23 · **Ratifica di Francesco:** Francesco,
23/08/2026 — la regola vincola l'agente ed è l'agente ad averla scritta, quindi la firma chi
non ne beneficia (ADR-0012).

## Contesto

La notte del 22→23/08 due PBI hanno esaurito le revisioni senza chiudersi, e la causa è la
stessa: lo **Scope** dichiarato dal PBI non è un confine che il Builder possa rispettare.

> Le righe di quella notte non sono in `runs/tempi.csv` versionato — l'ultima è
> `20260823-023855`, PBI-401. L'evidenza qui sotto è nei due PBI e nel `git log`, che per
> questa domanda dice di più: mostra **quando** le cose sono state scritte.

**PBI-309 — si è allargato lo Scope da solo.** Scope dichiarato: `lib/officina.inChiusura`
e `PratichePage:RiquadroChiusura`. Gli serviva `PratichePage:RiquadroMargine` — lo **stesso
file**. Al terzo giro ha committato l'aggiunta al proprio Scope e ha proseguito.

**PBI-301 — ha toccato due file non dichiarati** (`routers/marginalita.py`,
`services/accettazione.py`) senza aggiungerli. Nel merito erano due estrazioni giuste —
logica condivisa che riscritta avrebbe creato due sorgenti di verità — e infatti la
sezione che le dichiara **esiste**: è in `backlog/PBI-301-vista-anagrafica.md`, sotto
*«Allargato in corso d'opera»*, ed è arrivata come **ultimo commit del branch**:

```
6b5bb9b docs(accettazione): dichiara nello Scope di PBI-301 le due estrazioni
```

I due PBI hanno fatto **la stessa cosa**. Uno l'ha dichiarata al terzo giro, l'altro dopo
tre NON PRONTO e ventisei commit. Il paragrafo che chiude il ciclo è stato scritto in tutti
e due i casi: la differenza è *quando*, e se il Critic avesse una regola per riconoscerlo.

**PBI-207 non è il controllo che sembra.** Si è fermato con uno `STOP` corretto, ma a
fermarlo non è stato lo Scope: è stata la costituzione, che protegge il motore **per nome**.
Lo stesso vale per la run `20260821-014702` di PBI-202, che si è fermata dopo 16 minuti con
una domanda che era esattamente una domanda di Scope — *«estendo lo Scope a
`backend/app/marginalita.py` … oppure `AK/AL/AM` restano fuori dal modello?»*. Il confine
che regge, nei due casi in cui ha retto, è quello scritto in `AGENTS.md`, non quello scritto
nel PBI.

### Perché il PBI riscrivibile non è il difetto

La tentazione è dire che il difetto sia questo: la regola vincola l'agente rispetto a un
documento che l'agente può modificare. Ma quel confine è **già stato deciso**, due giorni
prima, in ADR-0012, *Ambito*:

> Non si applica alle spec né ai PBI: quelli si aggiornano lavorando, ed è il loro mestiere.

E l'alternativa *«vietare all'agente di toccare `AGENTS.md`»* è stata scartata lì con la
ragione che vale identica qui: *«le occasioni in cui la costituzione va corretta emergono
lavorando, non a tavolino»*. Il raggio di un cambiamento si scopre lavorando ancora più
della costituzione. **PBI-309 non ha trovato una scappatoia: ha fatto ciò che è lecito.**

### Cosa manca davvero

Manca allo Scope ciò che ADR-0012 ha dato alla costituzione, e che quell'ADR mette nelle
proprie Conseguenze positive:

> Il Critic **verifica una regola** invece di dedurne una: c'è la firma nell'intestazione?
> Sì o no. Prima doveva ricostruirla dai principi, e per quattro giri non l'ha fatto.

È, parola per parola, il fallimento del 301: il Critic ha dovuto **dedurre dai principi** se
due estrazioni non dichiarate fossero una violazione, e ha ciclato tre volte. E del 309: ha
dovuto giudicare se un emendamento fosse legittimo, senza niente da controllare.

Oggi le due regole del runner non guardano nemmeno la stessa cosa. Al Builder: *«Resta
dentro lo scope dichiarato dal PBI. Se ti serve toccare altro, fermati e dillo»* — e
«altro», in un repository, si legge come *un altro file*, mentre quel file al 309 era già
stato dato. Al Critic: *«Scope: file toccati fuori da quelli dichiarati?»* — che è una
domanda sui file, posta su un documento che nel frattempo può essere cambiato.

E le uscite dal problema, per il Builder, oggi sono due: `STOP:` — che chiude il PBI, e con
esso il lavoro di quella sessione — oppure procedere.

> **Quanto costa davvero uno `STOP`.** Non la notte: `STATI_CHE_INTERROMPONO` ferma la
> catena **dentro una singola invocazione** del runner, ma `ada-notte.sh` ne fa una per PBI
> e prosegue. Il registro lo dice quattro volte: PBI-202 chiude `fermato` alle `02:03:30`
> del 21/08 e PBI-203 parte alle `02:03:30`, stesso secondo; identico per PBI-205, e per il
> PBI-207 del 23/08 seguito da PBI-401. Il prezzo di uno `STOP` è **quel PBI più un giro
> umano** — sedici minuti buttati per il 202, e una domanda che aspetta la mattina. Resta
> un'asimmetria forte contro un paragrafo di deroga, ma è quella vera e va scritta così:
> un argomento che si regge su un costo esagerato si sgretola il giorno che qualcuno lo
> verifica. Manca la terza, che è quella che entrambi i
PBI hanno finito per inventarsi da soli, tardi e senza forma.

Il costo di non averla è il costo più alto che il runner sostiene: **ogni revisione rilegge
tutto il diff con un contesto nuovo.** PBI-301 ha pagato tre letture complete per ottenere
un paragrafo che è stato scritto comunque.

## Decisione

**Allargare lo Scope resta lecito. Farlo in silenzio no: la deroga si dichiara nel commit
che la introduce.**

1. **La deroga è contestuale.** Va scritta nel commit che porta il primo file fuori
   perimetro — non nella risposta al Critic, non alla fine. Un fatto datato dopo non è più
   una dichiarazione: è una giustificazione.
2. **Ha una forma fissa**, in una sezione `## Deroghe allo Scope` del PBI. Tre righe per
   deroga: **cosa** (i file), **perché** (cosa si romperebbe facendo altrimenti), **cosa non
   cambia** (quale comportamento esistente resta identico). Il modello è già scritto: la
   sezione *«Allargato in corso d'opera»* di PBI-301 è esattamente questo, con la
   motivazione giusta. Cambia il nome, perché il Critic deve poterla cercare.
3. **Il Critic cambia domanda.** Da *«file toccati fuori da quelli dichiarati?»* — un
   giudizio — a: *«ogni file fuori dal perimetro dichiarato all'inizio ha la sua deroga?
   Sì o no.»* Una deroga **mal motivata** resta un rilievo normale, con il suo rimedio; una
   deroga **assente** è la sola violazione di Scope che esista ancora.
4. **Il perimetro si legge al dispatch**, prima di `crea_branch`. Non perché il PBI sia
   immutabile — ADR-0012 dice il contrario e resta valido — ma perché altrimenti la deroga
   sparisce nello stesso gesto che la crea: confrontare il diff col file corrente vuol dire
   confrontarlo con un documento che l'allargamento ha appena riscritto. Congelare non
   vieta niente: rende osservabile.
5. **Il perimetro verificato a macchina è il file.** `git diff --name-only
   origin/main...HEAD` contro l'elenco letto al dispatch. `file:componente`
   (`PratichePage:RiquadroChiusura`) resta nel PBI come intenzione, e chi la giudica è
   l'Acceptance Gate. Non si perde niente di ciò che oggi protegge davvero: l'isolamento fra
   PBI che condividono un file lo fa la **sequenza delle onde**, non il componente — è
   scritto nelle Dipendenze di PBI-311, *«condividono `PratichePage.tsx`: non vanno lanciati
   nella stessa onda»*.
6. **Il runner osserva e segnala.** Calcola il delta a ogni giro e lo scrive **nella PR**:
   *dichiarati · toccati · in deroga · fuori perimetro senza deroga*. Non blocca, non conta
   giri, non decide. Le deroghe si registrano perché diventino una serie.
7. **Nessuna soglia, per ora.** Chiudere un PBI `non convergente` oltre *n* deroghe sarebbe
   un hard-block con un numero scelto prima di avere il dato. ADR-0008 dice come si trattano
   le anomalie, ADR-0002 e ADR-0014 dicono in che ordine si sceglie un numero: prima la
   misura, poi la regola. La soglia è una decisione futura, e la sua condizione di apertura
   è scritta in fondo.

## Conseguenze

**Positive**
- Il Critic verifica invece di dedurre, sulla domanda che nel 301 gli è costata tre giri.
  È lo stesso guadagno che ADR-0012 ha portato sulla firma degli ADR.
- Il Builder ha una terza uscita, e costa un paragrafo invece di un PBI. Oggi l'unica uscita
  onesta butta il lavoro fatto e rimanda a una risposta umana — PBI-202 si è fermato dopo
  sedici minuti su una domanda che era di Scope — mentre le due disoneste costano zero. Un
  prezzo così **seleziona** il comportamento del 309: non perché l'agente sia furbo, ma
  perché è la sola strada che il runner lascia aperta a costo ragionevole.
- L'informazione arriva al gate che risponde a quella domanda. *«È cresciuto fino a toccare
  questi due file, ecco perché»* non è un contratto della spec: è *«è la cosa giusta?»*, e
  quella è l'Acceptance Gate — dove il corpo della PR già invita a guardare *«il diff fuori
  scope»*, senza però dire dove sia.
- Le deroghe diventano misurabili. È la premessa di due cose che oggi non si possono
  scegliere: la soglia della clausola 7, e il segnale di convergenza che PBI-102 ha già
  proposto e rinviato (`BLOCCANTI: n`).

**Negative**
- Una deroga ben scritta resta una deroga. Il rischio è che dichiarare diventi il modo
  economico di fare qualunque cosa, e il contrappeso non è nel runner: è nella PR e in chi
  la legge. Il registro delle deroghe serve anche a questo — se crescono, la risposta non è
  una soglia automatica ma dei PBI scritti meglio.
- Il perimetro a livello di file non avrebbe visto il 309: `PratichePage:RiquadroMargine`
  sta in un file già dichiarato. Va detto per intero — con questa regola il 309 **non
  produce nemmeno una deroga** e converge, ed è l'esito che si voleva; ma è anche la prova
  che a quel livello di dettaglio la macchina non guarda.
- I PBI guadagnano una sezione, e il perimetro un formato che il runner sappia leggere. I
  PBI già scritti non si migrano: la regola vale da qui in avanti, e un PBI senza perimetro
  leggibile semplicemente non produce il confronto.

**Neutre**
- Il Critic non può revocare una deroga, come non può revocare una firma: può dire che è
  motivata male. Chi decide se il PBI è cresciuto troppo è chi mergia.
- La regola non cambia niente per i PBI che restano dentro il proprio perimetro, che sono
  la maggioranza: non aggiunge un rito, aggiunge una via d'uscita a chi ne ha bisogno.

## Alternative considerate

**Irrigidire: allargarsi è uno `STOP`, e il PBI diventa immutabile sul branch.** Scartata
per due ragioni indipendenti. Contraddice ADR-0012 nel punto in cui quell'ADR ha argomentato
meglio — le regole giuste emergono lavorando, e vietare la modifica non le fa nascere, fa
restare quelle vecchie. E sposta il costo invece di toglierlo: chiudere l'uscita economica
senza abbassare il prezzo di quella onesta lascia in piedi solo l'uscita che costa la notte.
Dei tre casi ne risolverebbe uno, e per giunta non il 301 — che taceva, e una regola in
prosa non cura il silenzio.

**Scrivere Scope più precisi.** Scartata dai fatti. PBI-309 aveva **già scritto** nel
proprio Contesto la conseguenza che l'ha fatto esplodere: *«`importo_fatturato` è il ricavo
del motore: scriverlo prima vuol dire che il margine si può guardare prima»*. Era scritta, e
non era Scope. Se conoscere la causa non basta a metterla nel posto giusto, non è un
problema di disciplina di scrittura — è che lo Scope si compila prima di sapere il raggio, e
uno Scope più preciso è solo più superficie da falsificare, cioè più `STOP`.

**Un Critic più severo sullo Scope.** Scartata: nel 301 ha trovato tutto, tre volte. Il
rilevamento non è mai stato il problema. Sul 309 poi non farebbe niente — l'emendamento era
lecito, e una lettura più severa sposterebbe soltanto la lite su *«era lecito emendare?»*,
che è la specie di disputa più cara che il runner possa ospitare: nessuno la arbitra, e
consuma tutte le revisioni rimaste.

**Contare le deroghe e chiudere `non convergente` oltre soglia.** Rinviata, non scartata:
è la clausola 7. Il numero non c'è ancora, e sceglierlo adesso significherebbe tarare un
hard-block sull'impressione di due notti — lo stesso errore che `MAX_REVISIONI = 2` ha già
commesso e che PBI-102 ha corretto con una misura.

**Togliere lo Scope dal PBI.** Scartata: il perimetro dichiarato serve comunque — a
sequenziare le onde (PBI-311 e PBI-212 condividono `PratichePage.tsx`) e a dare alla PR un
riferimento contro cui misurare la crescita. Senza perimetro non esiste nemmeno la nozione
di deroga, e si perde la serie che serve alla clausola 7.

## Ambito

Vincola `backlog/` e i due prompt del runner. **Restringe l'*Ambito* di ADR-0012
limitatamente ai PBI**: l'aggiornamento di un PBI resta libero — è il suo mestiere — ma
l'allargamento del suo Scope, che è la sola parte del PBI su cui l'agente è giudicato,
smette di essere autocertificabile in silenzio. Non tocca le spec, che restano fuori da
tutti e due gli ADR.

La ratifica serve, per la ragione di ADR-0012 e non per formalità: **chi beneficia di questa
regola è l'agente che la sta scrivendo.** Con il merge entra anche la riga in `AGENTS.md`,
sotto **SEMPRE**, che rimanda qui invece di contenere la regola:

> - Allargare lo **Scope** di un PBI è lecito; farlo in silenzio no. La deroga si dichiara
>   nel commit che la introduce, con cosa, perché e cosa non cambia
>   (`decisions/ADR-0015-la-deroga-allo-scope-si-dichiara.md`).

## Dove entra

L'implementazione non è di questo ADR, e **non è la prima cosa da fare.**

**Prima viene la rotazione di contesto del Builder.** In `esegui_pbi`, `cmd = BUILDER + ([]
if e.tentativi == 1 else ["-c"])`: `e.tentativi` non si azzera mai, quindi la sessione è
nuova solo al primo giro in assoluto e con `MAX_REVISIONI = 4` un PBI può arrivare a quindici
turni nella stessa finestra. Un Builder che discute di Scope da quattro giri ha, dentro il
proprio contesto, quattro giri di autoconvincimento sul fatto che lo Scope sia negoziabile —
e una regola sulle deroghe, applicata lì, regolerebbe il sintomo. Il `-c` è giusto **dentro**
un giro, dove serve a non rileggere tutto per un gate rosso; è sbagliato **fra** i giri, dove
il contesto pulito è il principio dichiarato del runner.

⚠️ La modifica è una riga, ma non è sola: `PROMPT_RIMEDIO` oggi contiene solo il rapporto del
Critic, e in una sessione nuova un Builder lo riceverebbe **senza** `AGENTS.md`, senza il PBI
e senza le spec. Va reso autoportante come `PROMPT_BUILDER` — altrimenti la rotazione
peggiora ciò che deve migliorare.

Poi, e in un PBI suo: la sezione `## Deroghe allo Scope`, il perimetro leggibile a macchina,
la lettura al dispatch, la domanda 2 del Critic riscritta come verifica, e il delta nel corpo
della PR.

**La condizione che farebbe rivedere questo ADR.** Se dopo qualche notte le deroghe
risultano quasi tutte dello stesso tipo — file già noti, sempre gli stessi, sempre ben
motivati — allora il difetto non era la dichiarazione mancante ma il perimetro scritto
troppo stretto, e la risposta è nei PBI, non nel runner. Se invece crescono in varietà, la
serie raccolta è il dato su cui scegliere la soglia della clausola 7.
