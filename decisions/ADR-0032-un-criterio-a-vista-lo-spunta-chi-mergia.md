# ADR-0032: un criterio a vista lo spunta chi mergia

**Stato:** **Proposta** · **Data:** 2026-10-25 · **Ratifica:** Francesco, con il merge
(`ADR-0012`, `ADR-0029`). Non cambia la costituzione: il test-first di `AGENTS.md` vale per il
codice, e un criterio a vista non produce codice suo. Non restringe nessuna frase di altri ADR:
aggiunge una terza specie di criterio alle due di `backlog/README.md`, il criterio che dichiara un
rosso e la guardia, e dice a chi tocca spuntarla.

## Contesto

Il gate del runner è un test (`AGENTS.md`, «Il gate CI è la verità»). Da `ADR-0021` ogni criterio
chiede il suo rosso prima, da `ADR-0031` il Lettore lo prova sulla base con una sonda. Funziona per
ciò che un test può dire. Non dice niente di ciò che può dire solo una persona: un'offerta che un
commerciale firmerebbe, una dispensa che si legge, una risposta di un agente che ha senso per chi
la riceve.

Oggi quella specie di criterio non ha posto, e chi scrive il PBI fa una di tre cose:

- la **traduce in misure**: `ada_dispense` `PBI-011` trasforma «la dispensa di riferimento è
  giusta» in pagine, capitoli per pagina, figure e `line-height`. È la scelta buona quando si può;
- la **lascia ambigua**, e il Builder la scopre a giro iniziato con un `fermati`;
- la **tiene per sé** e la applica dopo, in chat: è il modo del configuratore, otto mesi in cui il
  criterio era sempre l'occhio di Francesco, non scritto, e un commit su quattro è un `fix` del
  commit precedente.

I numeri della settimana (19–25/10, tre progetti sul runner `v0.7.0`): 14 PBI in `main`, 10 al
primo giro. **Nessun fermo è nato da un criterio a vista.** I fermi sono meccanici (`PBI-524`,
`PBI-525`) o di criteri ambigui, che la pre-verifica prende già (`ada_nlt` `PBI-4`, criterio 7,
fermato prima del giro). La regola quindi non ripara un danno visto: arriva prima delle PBI che
si guardano, che nelle tre code sono a una o due posizioni (`ada_nlt` `PBI-6`, `ada_dispense`
`PBI-011`, `ada_unical` `PBI-009`).

Il punto fermo da cui si parte: **i merge restano sempre di Francesco** (`ADR-0030`, decisione 3).
L'occhio umano c'è già, una volta per PBI, alla fine. La regola lo usa invece di aggiungerne uno.

## Decisione

1. **Un criterio della `Verifica` è di tre specie.** Dichiara un rosso che un test prova; oppure
   è una guardia, nata verde; oppure è **a vista**, e lo giudica una persona. La terza si dichiara
   nel testo del criterio con la marca «a vista», a confine di parola, come «guardia». Un criterio
   a vista non dichiara un rosso: niente sonda, niente coppia RED→GREEN, niente test. Il codice
   che produce la cosa da guardare sta nei criteri a test dello stesso PBI.
2. **Prima del giro, il Lettore chiede se ogni criterio è provabile.** È l'ottava domanda, **V**:
   un criterio che nessun test può provare e che non porta la marca è un rilievo, e il giro si
   ferma prima del ramo. È il momento in cui Francesco viene interpellato: decide se riscriverlo
   come criterio a test o marcarlo. Una `Verifica` fatta solo di criteri a vista e guardie è un
   rilievo di forma: quel lavoro è da sessione, non da runner.
3. **Nel giro nessun modello lo giudica.** Il Builder lo lascia `[ ]`; il Critic non lo usa per
   `non pronto` e lo scrive sotto «Note per chi mergia». Il giudizio di un criterio a vista non si
   delega né al Builder né al Critic né a un modello che guarda uno screenshot: sarebbe un esito
   ricavato dal giudizio libero di un modello (`ADR-0027`), su ciò che il proprietario ha detto di
   voler vedere lui.
4. **La PR li elenca e chi mergia li spunta.** La PR porta la sezione «Da verificare a vista»; la
   spunta `[x]` di quel criterio la mette una persona, in un commit che il runner non fa, ed è il
   verdetto. Un criterio a vista non spuntato in `main` conta come non spuntato per i PBI che ne
   dipendono, e resta un avviso.

**Le quattro domande** (`decisions/README.md`):

1. **Cosa si controlla:** il testo di ogni criterio della `## Verifica` del PBI, alla versione
   che il giro lancerà, e la presenza della marca.
2. **Quando:** nella pre-verifica, prima del ramo (il codice per la forma e l'avviso della sonda,
   il Lettore per la domanda V); a fine giro, nel rapporto del Critic; all'apertura della PR.
3. **Cosa conta come prova:** nel rapporto della pre-verifica il campo `a_vista` elenca i
   criteri, e nessuno di essi ha una sonda né l'avviso «senza sonda»; il corpo della PR ha la
   sezione; la spunta `[x]` sul criterio sta in un commit di una persona. Il runner non la mette.
4. **Cosa succede se manca:** un criterio non provabile senza marca è un rilievo `V`, e il giro
   chiude `fermato` con motivo `preverifica` prima del ramo; il tick scrive `attende` e rilancia
   quando il PBI cambia (`ADR-0031`, decisione 4). Una `Verifica` di soli criteri a vista fa lo
   stesso percorso con un rilievo di forma. A fine giro un criterio a vista non spuntato non ferma
   niente: è una nota per chi mergia (`ADR-0008`).

## Conseguenze

- Un PBI può portare ciò che solo un occhio giudica, scritto come tale, invece di piegarlo in una
  misura che non lo è o di lasciarlo ambiguo.
- Il lavoro di chi mergia cresce esattamente dei criteri elencati nella PR, e non di altro.
- Un PBI di soli criteri a vista è dichiarato non da runner: si fa in sessione, e il metodo lo
  dice invece di lasciarlo scoprire al Builder.
- Il costo nel giro è zero; il costo nella pre-verifica è una domanda in più al Lettore.
- Il limite: niente impedisce al Builder di spuntare un criterio a vista. Lo nota il Critic, lo
  toglie chi mergia; un lucchetto verrà se il caso si vede.
- La misura, fra un mese: quanti criteri a vista sono nati nei tre progetti, quante spunte tolte,
  quanti rilievi V. Oggi il conto è zero, ed è scritto qui perché si possa confrontare.

## Alternative considerate

- **Fermare il giro a metà, col `fermati` del Builder.** È ciò che succede oggi con un criterio
  ambiguo, ed è tardi due volte: la cosa da guardare non esiste ancora, e il giro è già speso.
  Scartata.
- **Far giudicare il Critic, o un modello con uno screenshot.** Sposta su un modello ciò che il
  proprietario ha detto di voler vedere, e l'esito nasce dal testo libero di un modello
  (`ADR-0027`). Scartata.
- **`chiedi_a_francesco` all'inizio del giro.** Una domanda senza l'oggetto da guardare, e sul
  canale del Solver, che è per i blocchi e non per le accettazioni. Scartata.
- **Tradurre sempre il criterio in misure.** È la prima scelta e la regola non la tocca:
  `ada_dispense` lo fa ed è giusto. La marca è per ciò che resta dopo aver misurato quel che si
  può. Non è un'alternativa, è il passo prima.
- **Solo una riga nel TEMPLATE.** Come la prima alternativa di `ADR-0031`: una regola che nessuno
  controlla non regge. Resta nel template, ma con il Lettore che la chiede.
