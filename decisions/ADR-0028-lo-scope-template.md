# ADR-0028: i commit su `template/` hanno lo scope `template`

**Stato:** **Accettata** · **Data:** 2026-10-08 · **Ratifica:** Francesco, con il merge
(`ADR-0012`). **Cambia la costituzione**: aggiunge una parola alla lista degli scope dei
commit in `AGENTS.md`, nella stessa PR.

## Contesto

Il primo lavoro di questo repository è `template/` (D5 di `SCAFFOLDING.md` di aDa): la
cartella che un progetto nuovo copia alla nascita, con i modelli dei documenti, la
configurazione d'esempio e il metodo. La fanno quattro PBI, da `PBI-500` a `PBI-503`, col
runner `v0.1.0` installato.

`AGENTS.md` chiede `tipo(scope): descrizione`, con gli scope del progetto in `## Dominio`:
`runner` `coda` `config` `esito` `prompt` `hook` `plancia` `ci` `kb`. Nessuno copre
`template/`. Un Builder che non trova lo scope o ne sceglie uno che non c'entra in silenzio,
o si ferma a chiederlo: tutte e due le cose sono un giro speso su una parola.

Il nome che l'ADR di numero 0028 aveva in aDa (`ADR-0028`, `AGENTS.md` in metodo e dominio)
non entra qui: gli ADR di aDa che non sono di metodo non sono stati copiati, e la numerazione
di questo repository riparte da 0028 (`decisions/README.md`). Quando qui si cita «`ADR-0028`
di aDa», si intende quello.

## Decisione

**Lo scope `template` si aggiunge alla lista di `AGENTS.md`**, e vale per ogni commit che
tocca `template/`. Un commit che tocca `template/` e un'altra parte del pacchetto prende lo
scope dell'altra parte: `template` dice «solo i file da copiare».

Le quattro domande (`decisions/README.md`):

1. **cosa si controlla**: il messaggio di un commit che tocca solo `template/` e i test che
   lo guardano;
2. **quando**: al commit, nel giro del Builder, e alla rilettura del Critic;
3. **cosa conta come prova**: lo scope fra parentesi è `template`;
4. **cosa succede se manca**: nessun gate lo controlla. Lo segnala il Critic, come ogni
   commit fuori dalla convenzione, e il giro va avanti (`ADR-0008`).

## Conseguenze

- **Positive:** i quattro PBI di `template/` non hanno una domanda aperta sullo scope.
- **Negative:** dieci scope invece di nove.
- **Neutre:** la regola dei Conventional Commits non cambia.

## Alternative considerate

- **Uno scope che c'è già, per esempio `ci`.** Scartata: il registro dei commit direbbe `ci`
  per dei modelli di documenti, e chi cerca nella storia le modifiche a `template/` dovrebbe
  sapere che stanno sotto un nome sbagliato.
- **Lasciare la scelta al Builder.** Scartata: è la domanda che AGENTS.md chiede di scrivere
  nel PBI, e non di decidere in silenzio.
