# PBI-509: il rilascio a tick, dal merge a monte al pin nel progetto

## Direttiva

Quarto PBI di `ADR-0030`, decisioni 2 e 3. I cinque passi che oggi si fanno a mano dopo il
merge di un PBI a monte (`PBI-505`: checkout su `main`, `--registra`, tag, PR del pin, rilancio)
diventano un tick. Il PBI ha due metà, che si provano separate ma si rilasciano insieme (la PR a monte del Solver, R5 e R6, è passata a `PBI-512`, 16/10):

- **Lato `asdlc`:** il tick vede una PR di PBI `MERGED`; se il PBI dichiara `rilascia:
  patch|minor` e la CI di `main` è verde, allinea `main`, registra il giro e mette il tag, in
  un worktree usa-e-getta (R8, R9).
- **Lato progetto:** il tick vede i PBI fermi con `attende:`; a PR a monte `MERGED` (verificato
  con `gh pr view`) e tag esistente apre la PR che cambia solo `[ambiente].installa`; a PR del
  pin `MERGED` toglie la pausa (R10, R11).

I merge restano sempre di Francesco.

**Scope**

- `tools/asdlc/coda.py` — il passo di rilascio, la lettura di `rilascia:` e di `attende:`, il
  passo del pin e la pausa.
- `tools/asdlc/runner.py` — il worktree usa-e-getta.
- `tools/asdlc/config.py` — la sezione `[rilascio]` (nome del remote del fork, del tag
  prefisso).
- `tools/tests/test_asdlc_rilascio.py` — nuovo: i test dei criteri.
- `README.md`, `backlog/AUTOMAZIONE.md`, `backlog/CODA.md` — la sezione e la riga di coda.
- `backlog/PBI-509-il-rilascio-a-tick.md` — questo file, per la spunta.

**Fuori scope**

- La PR a monte del Solver, R5 e R6 (`PBI-512`).
- Il merge: mai automatico. Un `gh pr merge` nel codice è una violazione di R10-R11.
- Il battito e il timer dei tick persi (`PBI-510`).
- Il pin dei progetti che non dichiarano `attende:`.

## ✅ Via libera di Francesco (16/10)

Francesco ha accodato il PBI con il formato di `rilascia:` e `attende:` qui sotto così come
proposto: valgono come decisioni. Il PBI è largo (due metà e una PR): se il Critic lo giudica
tale, la divisione in due è lecita e si dichiara (`ADR-0015`).

## ✅ Deciso

1. **`rilascia: patch|minor`** è una riga dell'intestazione del PBI, subito sotto il titolo,
   accanto a `Direttiva`. Senza, nessun tag (R8). Un PBI di documentazione non lo dichiara.
2. **`attende: <repo>#<PBI>`** è una riga analoga nel PBI fermo del progetto, per esempio
   `attende: Lara-srl/ada_asdlc#PBI-505`. La pausa del progetto è `~/asdlc-tick.pausa`
   (già esistente, `PBI-385`).
3. **Il tag è `vX.Y.Z`**, con il numero successivo secondo `patch` o `minor`; non esiste già;
   la CI di `main` è verde (`gh run list`).
4. **Il worktree usa-e-getta** è creato fuori dal checkout del tick, che resta pulito (R9);
   `--registra` e il tag girano là dentro; il worktree si toglie a fine passo.
5. **La PR del pin cambia una sola riga**, `[ambiente].installa` di `asdlc.toml`. La parte
   specifica del progetto (per esempio `[junit]`) è del suo PBI a valle.
6. **Credenziali:** il fork usa il `gh` del proprietario. Nessun permesso di scrittura su
   `asdlc` (R5).
7. **Lo scope dei commit è `coda` e `runner`.**

## Dipendenze

- Bloccato da: `PBI-506` (il vocabolario), `PBI-507` (lo strumento che apre la PR a monte).
- Sblocca: la chiusura automatica del ciclo di `ADR-0030`.

## Contesto

- `specs/solver-e-rilascio/spec.md`, R5-R11 e il disegno del ciclo.
- `PBI-505`, «Dipendenze»: i cinque passi manuali da automatizzare.
- `ADR-0026`: il tag è la release.

## Verifica

Su `main` non c'è rilascio: ogni criterio è un **rosso atteso**. `gh` e `git remote` sono
sostituiti da finti; nessun test usa la rete.

- [x] **Un PBI con `rilascia: patch` mergiato e CI verde produce il tag.** Da `v0.3.0` a
      `v0.3.1`; con `minor`, `v0.4.0` (R8).
- [x] **Senza `rilascia:` non c'è tag.** Lo stesso scenario, nessun tag (R8).
- [x] **CI rossa o tag già esistente: nessun tag.** Due casi (R8).
- [x] **Il rilascio gira in un worktree separato e il checkout del tick resta pulito.** Il test
      verifica lo stato del checkout prima e dopo, e che il worktree sia tolto (R9).
- [x] **Un PBI fermo con `attende:` e PR a monte `MERGED` con tag apre la PR del pin.** La PR
      cambia solo `[ambiente].installa` (R10).
- [x] **La PR a monte non `MERGED` non apre niente.** Il progetto resta in attesa (R10).
- [x] **La pausa si toglie solo a PR del pin `MERGED`,** verificata con `gh pr view`; con la
      PR aperta o chiusa senza merge la pausa resta (R11, due casi).
- [x] **Nessun `gh pr merge` nel pacchetto.** Un test sull'AST che nessuna chiamata lo contenga
      (R10-R11).

**Non regressione:** il tick di un progetto senza `attende:` e senza `rilascia:` fa quello di
prima; `python3 -m pytest -q tools/tests` resta verde.

## Il giro 3, e cosa si riprende

Il giro 2 (16/10) si è fermato con otto criteri su dieci e una domanda su R5 e R6. Francesco ha
deciso: la PR a monte del Solver esce e diventa `PBI-512`; qui restano rilascio, pin e pausa,
più la guardia sulle eccezioni. Il giro 3 ha ripreso i 24 commit, ma ha perso il criterio
della guardia nel conflitto sul file di questo PBI e si è fermato a chiederlo (22:27).

**Si riprende il tag `giro-fermato/pbi-509-giro3-20261016`:** è il codice completo, gate verde
(1004 test), con tutti gli sha del giro 2 già dentro. Si crea il ramo da quel tag e non si
cherry-picka niente. Sul file di questo PBI vale la versione di `main`, che ha già le otto
spunte `[x]` e il criterio nuovo, scritto sopra: `git checkout origin/main --
backlog/PBI-509-il-rilascio-a-tick.md` e un commit. Niente da lasciare.

**Resta da fare un solo criterio, quello sulle eccezioni** («Un errore in `rilascia()` o in
`pin()` non ferma il tick»), in `tools/asdlc/coda.py`, nelle due funzioni `rilascia()` e
`pin()`. Esito atteso: un avviso (`ADR-0008`) e il tick che prosegue con gli altri passi e
gli altri progetti; nessuna eccezione esce da `tick()`. Casi: JSON illeggibile (`pin`),
worktree che non si crea (`rilascia`). RED prima, poi GREEN; alla fine si spunta la riga e
si aggiorna la spec nello stesso commit.
