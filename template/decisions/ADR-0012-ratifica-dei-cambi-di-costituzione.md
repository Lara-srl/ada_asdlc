# ADR-0012: chi beneficia di una decisione non la firma

**Stato:** Accettata · **Data:** 2026-08-21 · **Ratificata da Francesco** il 2026-08-21,
col merge della PR di PBI-201

## Contesto

ADR-0011 abroga un'istruzione esplicita del proprietario (*«puoi inserirli però non
hardcoded»*, 08/08/2026) ed è stato scritto dall'agente **dentro il branch che ne trae il
beneficio diretto**: senza quell'abrogazione il golden non entra nel repository e il
criterio centrale di PBI-201 resta senza gate. Nel merito l'ADR regge, e Francesco l'ha
ratificato. Ma la revisione avversariale ha dovuto **dedurre** che una decisione di quella
forma non fosse autocertificabile: non è scritto da nessuna parte.

Il tentativo di scriverlo ha prodotto il fatto che apre questo ADR. La riga aggiunta a
`AGENTS.md` — *«chi beneficia di una decisione non la firma»* — è stata introdotta dallo
stesso branch, senza ADR e quindi senza un'intestazione dove una firma potesse stare: una
regola contro l'autocertificazione, autocertificata. Il giro successivo l'ha rilevata
esattamente così, ed è la dimostrazione più netta che il vincolo serve: nemmeno chi lo
stava scrivendo se n'è accorto.

## Decisione

Una modifica ad `AGENTS.md`, o un ADR che abroga un'istruzione del proprietario, **richiede
la ratifica di Francesco, scritta nell'intestazione dell'ADR con nome e data.**

`AGENTS.md` **rimanda** a questo ADR invece di contenere la regola: la costituzione elenca
i confini, le decisioni con le loro alternative stanno in `decisions/`.

**La ratifica è il merge.** Non serve un rito separato: l'Acceptance Gate — la PR che il
runner apre e non mergia mai — è già l'unico atto che nessun agente può compiere. Scriverla
nell'intestazione la rende **ispezionabile**: chi legge l'ADR fra sei mesi vede che qualcuno
ha firmato, senza dover ricostruire dalla storia di git chi ha premuto il pulsante.

## Conseguenze

**Positive**
- Il Critic **verifica una regola** invece di dedurne una: c'è la firma nell'intestazione?
  Sì o no. Prima doveva ricostruirla dai principi, e per quattro giri non l'ha fatto.
- Il regresso si ferma. Una regola sull'autocertificazione, scritta da un agente, sarebbe
  contestabile all'infinito da ogni revisione successiva; la firma umana è l'unico punto
  in cui la catena poggia su qualcosa che non è un'altra macchina.

**Negative**
- Un cambio di costituzione non può più essere chiuso dentro un giro di runner: aspetta una
  persona. È il costo, ed è voluto — le cose che vincolano tutto il repository non hanno
  fretta.
- La regola vale **anche quando il merito è evidente**, che è il caso in cui costa di più e
  in cui si è più tentati di saltarla. ADR-0011 era argomentato bene: mancava la firma, non
  l'argomento.

## Alternative considerate

**Lasciarlo al giudizio**, com'era prima. Scartata dai fatti: sei revisioni, e il confine è
stato ricostruito da capo ogni volta — sbagliandolo nei primi quattro giri. È la stessa
dinamica che ADR-0011 ha chiuso per i dati reali, e il rimedio è lo stesso: si scrive il
confine, non lo si affida al buon senso di chi legge.

**Vietare all'agente di toccare `AGENTS.md`.** Semplice da controllare, e sbagliata: le
occasioni in cui la costituzione va corretta emergono **lavorando**, non a tavolino — questa
serata ne ha prodotte due in poche ore. Vietare la modifica non fa nascere le regole giuste,
fa solo restare quelle vecchie senza che nessuno le scriva.

**Un secondo agente che ratifica.** Scartata perché sposta il problema di un passo: chi
ratifica il ratificatore? La catena deve poggiare su una persona, e nel merge ce l'ha già.

## Ambito

Questo ADR vincola `AGENTS.md` e gli ADR che abrogano istruzioni del proprietario. **Non**
si applica alle spec né ai PBI: quelli si aggiornano lavorando, ed è il loro mestiere.
