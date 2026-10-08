# ADR-0011: il repository è privato, i dati reali sono ammessi

**Stato:** Accettata · **Data:** 2026-08-21 · **Ratificata da Francesco** il 2026-08-21

> La ratifica è parte della decisione, non una formalità. Questo ADR **abroga un'istruzione
> esplicita del proprietario** (vedi *Contesto*) e il branch che lo introduce ne trae un
> beneficio diretto: senza, il golden non può entrare nel repository e il criterio centrale
> di PBI-201 resta senza gate. Una decisione di questa forma non può essere
> autocertificata da chi ne beneficia — rilevata dalla quinta revisione avversariale, che
> ha chiesto la firma prima del merge.

## Contesto

`AGENTS.md` portava dalla conversione ASDLC una clausola **MAI** — *«dati reali di
Carrozzeria Fiume nel repository: nomi, targhe, importi e costi orari vivono in `data/`»* —
che non è mai passata da `decisions/`.

**La ragione c'era, ed era buona.** L'08/08/2026, consegnando i costi orari, Francesco l'ha
detta per esteso: sono retribuzioni associate a nomi di persone reali, e *«puoi inserirli
però non hardcoded»* — perché un seed o una migrazione li metterebbe nella storia di git
per sempre. Il fatto nuovo **non è** che nessuno la conoscesse: è che non fosse mai stata
**scritta nel repository**, e quindi non fosse ispezionabile da chi lavora qui. Una regola
la cui motivazione vive fuori dai file è una regola che ogni revisione deve ricostruire da
capo — ed è ciò che è successo, quattro volte in una sera.

**Il fatto che rende la revoca possibile è un altro, e va detto con precisione:** quelle
cifre sono **già nel repository**, e da prima di questo branch. `docs/archivio/04 §4`
scrive `20,79·0,2 + 21,29·1 + 9·2,5` ed è versionato dal commit di fork. Portare il caso
nel test non aggiunge un'esposizione: la rende **utile**, perché quella già presente non
verifica niente. Questo ADR quindi non apre una porta — constata che è aperta e decide di
smettere di comportarsi come se fosse chiusa, che è l'unica delle due posizioni che si può
difendere.

Il costo di quella regola si è visto misurandolo. In una sola sessione la revisione
avversariale l'ha sollevata **tre volte su tre giri**, ogni volta su un file diverso e ogni
volta con un confine tracciato altrove: gli addendi in un docstring, la targa in uno
scenario Gherkin, il costo orario nominativo in un test preesistente. Ogni volta la
discussione è ripartita da zero, perché la regola diceva *cosa* è vietato senza dire
*perché* — e senza il perché nessuno può decidere i casi che la formula non prevede.

Il tentativo intermedio — il confine **numeri sì, identità no** — è durato meno di
mezz'ora: la revisione successiva ha trovato che il branch che introduceva quella regola
la violava nel proprio Scope. Un confine che chi l'ha appena scritto non riesce ad
applicare non è un confine: è una fonte di rilievi.

Il dato di fatto che rende la scelta possibile: **il repository è privato e ha un solo
proprietario.** I dati sono di Carrozzeria Fiume, cioè di un cliente che li ha affidati a
Lara, e restano dentro un perimetro che oggi coincide con una persona sola.

## Decisione

**I dati reali possono stare nel repository.** Targhe, nomi, importi e costi orari
nominativi possono comparire in spec, test, docstring e commenti, dove servono a rendere
un'affermazione verificabile o a ritrovare un caso nel foglio.

`data/` **resta gitignored**, ma per un'altra ragione — che va detta perché altrimenti si
scambia per un residuo di questa: sono file sorgente pesanti e binari (l'Excel della
marginalità, i template Word, le anagrafiche), che la CI non deve scaricare e che si
aggiornano fuori da git. È una scelta di igiene del repository, non di riservatezza. Da
qui in avanti, un test che si **skippa** perché `data/` manca è un test che ha rinunciato a
un'evidenza che poteva versionare: si preferiscono i valori scritti nel test.

## Conseguenze

**Positive**
- La domanda non torna più. Il Critic legge questo ADR e passa oltre, invece di doversi
  fare un'opinione file per file — che è il modo in cui ha bruciato tre giri.
- Le evidenze possono essere **versionate**: le sei cifre che l'Excel documenta possono
  stare nel test come letterali, invece di dipendere da un file gitignored che si rigenera
  dal motore stesso, e che quindi non è evidenza.
- Le spec restano leggibili: uno scenario Gherkin con la targa e i nomi veri è ciò che
  Barbara può controllare, e il controllo di Barbara è l'unica validazione che conta.

**Negative**
- **La storia di git non si ripulisce.** Un commit che porta dentro una targa la porta per
  sempre: revocare questo ADR domani non toglie ciò che è già entrato oggi. È la
  conseguenza asimmetrica di questa decisione, e la ragione per cui la condizione di
  revisione qui sotto non è una formalità.
- I dati escono dal repository ovunque il repository vada: cloni su ogni macchina, log
  delle Action, artifact delle build.
- Sono dati **di terzi** — clienti della carrozzeria — non di chi li versiona.

## Alternative considerate

**Vietare tutto** (la regola ereditata). Scartata perché rende le spec non verificabili: un
golden test senza importi non ha nulla contro cui coincidere, e uno scenario senza numeri
descrive una forma invece di un comportamento. In pratica ogni file finiva per decidere da
sé dove stava il confine, che è il contrario di una regola.

**Il confine numeri-vs-identità** — importi sì, targhe e nomi no. Difendibile sulla carta,
e infatti l'abbiamo adottata: è durata un giro di revisione. Cade su un caso banale e
frequentissimo, il costo orario nominativo, dove il numero *è* l'identità: `angelo → 20,79`
non è più anonimo di «Angelo». Una regola che ha bisogno di un arbitro a ogni riga non
riduce il lavoro di giudizio, lo sposta.

**Anonimizzare alla fonte** — uno script che riscrive i dati veri con pseudonimi stabili
prima che entrino. È la soluzione tecnicamente corretta e resta quella giusta il giorno in
cui il perimetro si allarga. Scartata **ora** perché costa uno strumento da scrivere e da
mantenere per proteggere un perimetro che oggi è una persona sola, e perché aggiunge un
passaggio fra il foglio e il test: il golden diventerebbe verificabile contro i dati
pseudonimi, non contro la cella che Barbara apre.

## Trigger per rivedere

Questa decisione poggia su un fatto, non su un principio, e il fatto può cambiare:

- un **collaboratore in più** sul repository, o il repo che smette di essere privato —
  e allora l'istruzione dell'08/08 torna valida esattamente com'era scritta;
- una **CI pubblica**, o artifact accessibili fuori dall'organizzazione;
- la carrozzeria che chiede conto di dove stanno i suoi dati.

Al primo di questi, si riapre — sapendo che *«da domani non entrano più»* non basta,
perché ciò che è entrato resta nella storia: la revisione dovrà mettere in conto una
riscrittura della storia o un repository nuovo. È la ragione per cui questa clausola è
scritta qui e non lasciata al buon senso.
