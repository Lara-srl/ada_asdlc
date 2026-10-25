# PBI-526: i criteri a vista, e chi li spunta
rilascia: minor

**Stato:** proposto il 25/10 in una sessione con Francesco, dopo `PBI-525`; **non letto** e **non in
coda**: si accoda dopo la `v0.8.0`, se Francesco ratifica `ADR-0032` col merge di questa PR.

## Direttiva

Un criterio della `## Verifica` oggi è di due specie: dichiara un **rosso** che un test prova, o è
una **guardia**, nata verde (`backlog/README.md`). Non c'è posto per la terza: il criterio che solo
una persona può giudicare — un'offerta che un commerciale firmerebbe, una dispensa che si legge, una
risposta dell'agente che ha senso. Chi scrive il PBI o lo traduce in misure (in `ada_dispense`,
`PBI-011`: pagine, capitoli per pagina, `line-height`) o lo lascia ambiguo, e il Builder lo scopre a
giro iniziato con un `fermati`.

**Cosa dicono i dati** (19–25/10, `ada_nlt`, `ada_dispense`, `ada_unical`, runner `v0.7.0`): 14 PBI
in `main`, 10 al primo giro. **Nessun giro è rimbalzato su un criterio a vista.** I fermi sono di due
cause: meccaniche (`PBI-524`, `PBI-525`) e criteri ambigui (`ada_nlt` `PBI-4` criterio 7,
`ada_dispense` `PBI-007`, `ada_unical` `PBI-003`), che la pre-verifica di `ADR-0031` già prende: su
`PBI-4` l'ha presa prima del giro. Questo PBI quindi **non corregge un fermo visto**: dà una forma
alla terza specie prima che arrivino le PBI che si guardano (`ada_nlt` `PBI-6`, `ada_dispense`
`PBI-011`, `ada_unical` `PBI-009`), e porta l'occhio umano nel punto dove già sta, il merge.

Cosa cambia: la marca «a vista» nel criterio; il Lettore con un'ottava domanda; il Critic che non
blocca su un criterio a vista; la PR che li elenca; la spunta che resta a chi mergia (`ADR-0032`).

**Scope**

- `tools/asdlc/runner.py`:
  - `RE_A_VISTA` e `criteri_a_vista(testo)`, accanto a `RE_GUARDIA` e `criteri_del_pbi()`;
  - `criteri_senza_sonda()`: un criterio a vista non ha sonda e non ha l'avviso;
  - i rilievi di forma (`PBI-520`, decisione 2): una `Verifica` di soli criteri a vista;
  - il rapporto della pre-verifica: il campo `a_vista`;
  - `apri_pr()`: la sezione «Da verificare a vista» nel corpo.
- `tools/asdlc/esito.py` — `V` in `DOMANDE_DEL_LETTORE`. È il server dell'esito che il runner lancia
  durante il giro: il giro ci sopravvive perché gira il pacchetto **installato** (`ADR-0026`), e il
  server nuovo entra al tag successivo.
- `tools/asdlc/prompt/lettore.md` — l'ottava domanda. `critic.md` — un criterio a vista non spuntato
  non è `non pronto`. `builder.md` — un criterio a vista non ha coppia RED→GREEN e resta `[ ]`.
- `template/backlog/TEMPLATE.md`, `template/backlog/README.md`, `backlog/README.md` — le tre specie
  e la domanda **V**, nello stesso commit del codice.
- `README.md` — la marca e la sezione della PR.
- `tools/tests/test_asdlc_preverifica.py`, `test_asdlc_lettore.py`, `test_asdlc_esito.py`,
  `test_asdlc_runner.py` — i test dei criteri.
- `backlog/PBI-526-i-criteri-a-vista.md` — questo file, per la spunta.

**Fuori scope**

- Un lucchetto che impedisca al Builder di spuntare un criterio a vista: lo nota il Critic.
- Il criterio a vista nel giro del Solver e nei precedenti.
- Una misura del rendering al posto dell'occhio: è un PBI del progetto, non del runner.
- Il tetto `[soglie].revisioni` e tutto `PBI-525`.

## ✅ Deciso

1. **La marca è il testo «a vista», a confine di parola, nel criterio.** Righe rientrate comprese,
   maiuscole e minuscole uguali, come «guardia» (`RE_GUARDIA`): `RE_A_VISTA = r"\ba vista\b"`. Il
   confine serve: «`SELECT` sulla vista riesce» (`ada_unical`, `PBI-008`, criterio 5) non è a vista.
   Un criterio che dice sia «guardia» sia «a vista» è a vista. Si è scartata una marca in forma di
   tag (`[a vista]`) per restare nella forma di «guardia», che il runner già legge.
2. **Un criterio a vista non dichiara un rosso.** Non ha sonda, non ha coppia RED→GREEN, non ha test;
   `ADR-0021` e `ADR-0031` non gli si applicano perché non c'è niente da far nascere rosso. Il codice
   che serve per produrre ciò che si guarda sta nei criteri a test dello stesso PBI.
3. **L'ottava domanda del Lettore è V.** Per ogni criterio senza marca: lo prova un test? Un criterio
   che nessun test può provare e non è marcato è un rilievo `V` sul suo numero, con l'evidenza nel
   PBI. Il server accetta `V` in `rilievo`. Un criterio a vista non ha sonda e `criteri_senza_sonda()`
   non ne dà l'avviso (come la guardia, `PBI-521` decisione 5).
4. **Una `Verifica` di soli criteri a vista e guardie è un rilievo di forma**: «la Verifica ha solo
   criteri a vista: è un lavoro da fare in sessione, non dal runner». Il percorso è quello dei rilievi
   di `PBI-520`: il giro chiude `fermato`, motivo `preverifica`, prima del ramo.
5. **Il rapporto della pre-verifica ha `a_vista`**, la lista dei numeri dei criteri a vista, anche
   vuota, accanto a `rilievi`, `avvisi` e `sonde`.
6. **Il Builder lo lascia `[ ]`.** Nessun test, nessun commit per quel criterio, nessun `fermati` per
   il solo fatto che non si può provare: la marca dice che è atteso. Se il PBI non dice cosa produrre
   perché qualcuno lo guardi, quella è un'ambiguità normale, e si chiama `fermati`.
7. **Il Critic non lo usa per `non pronto`.** Un criterio a vista non spuntato va sotto «Note per
   chi mergia» come «da verificare a vista: criterio N — <testo in grassetto>». Un criterio a vista
   che il Builder ha spuntato è una nota, non un rilievo: la spunta la toglie chi mergia.
8. **La PR li elenca.** Dopo la riga «Manca l'unica cosa che uno script non può dare», la sezione
   «Da verificare a vista» con un punto per criterio (numero e testo in grassetto). Senza criteri a
   vista la sezione non c'è.
9. **La spunta è di chi mergia**, in un commit sul ramo prima del merge o su `main` dopo: è il suo
   verdetto, e il runner non la mette mai. Un criterio a vista `[ ]` su `main` conta come non
   spuntato per chi dipende da quel PBI: è già così (`PBI-520`, l'avviso della dipendenza), e resta
   un avviso.
10. **Scope dei commit:** `runner` per `runner.py`, `esito` per il server, `prompt` per i tre prompt,
    `template` per `template/`.

## Dipendenze

- Bloccato da: `PBI-525` — tocca `runner.py` e `critic.md` negli stessi punti, e va nel rilascio dopo
  la `v0.8.0`.
- Blocca: nessuno.

## Contesto

- `decisions/ADR-0032-un-criterio-a-vista-lo-spunta-chi-mergia.md` — la regola e le alternative.
- `decisions/ADR-0031-la-lettura-prima-della-coda.md` — le sette domande, le sonde, il percorso del
  rilievo (decisioni 1, 2 e 4).
- `tools/asdlc/runner.py`: `RE_CRITERIO`, `RE_GUARDIA`, `criteri_del_pbi()`, `criteri_senza_sonda()`,
  `Rilievo`, i rilievi di forma di `PBI-520`, `apri_pr()` (il `corpo`).
- `tools/asdlc/esito.py`: `DOMANDE_DEL_LETTORE`, il ramo di `rilievo` in `chiama()`.
- `tools/tests/test_asdlc_runner.py::test_il_corpo_della_pr` — come si prova il corpo con `esegui`
  finto; `tools/tests/test_asdlc_lettore.py` — il Lettore finto e il test delle domande rifiutate.

## Verifica

Tutto pytest, senza `claude`. Su `main` la marca, la domanda `V`, il campo e la sezione non esistono:
i criteri nascono rossi per asserzione o per `AttributeError` dentro il test.

- [ ] **`criteri_a_vista()` legge la marca a confine di parola, e il criterio non ha l'avviso della
      sonda.** Un PBI con quattro criteri: il secondo ha «a vista» su una riga rientrata, il quarto
      dice «`SELECT` sulla vista riesce». `criteri_a_vista(testo) == [2]`, e
      `criteri_senza_sonda(testo, [])` dà gli avvisi per 1, 3 e 4 e non per 2.
- [ ] **Il server accetta la domanda `V`.** Come il test delle domande di `PBI-521`: `rilievo` con
      `domanda="V"` è valido e finisce in `letto`; una domanda fuori da `R F T A E D N V` resta
      rifiutata.
- [ ] **Una `Verifica` di soli criteri a vista è un rilievo di forma.** Un PBI con un criterio a vista
      e una guardia dà un rilievo `forma` il cui testo contiene «solo criteri a vista»; lo stesso PBI
      con in più un criterio a test non lo dà.
- [ ] **Il rapporto porta `a_vista`.** Il rapporto di `--preverifica` sul PBI del criterio 1 ha
      `a_vista == [2]`; su un PBI senza marca ha `a_vista == []`.
- [ ] **La PR elenca i criteri a vista.** Come `test_il_corpo_della_pr`: con un PBI che ha un
      criterio a vista il `--body` contiene «Da verificare a vista» e il testo in grassetto del
      criterio; con `PBI-102` non contiene «Da verificare a vista».
- [ ] **I tre prompt dicono la regola.** `lettore.md` ha una riga che comincia con «- **V**» e nomina
      «a vista»; `critic.md` nomina «a vista» e «Note per chi mergia» nella stessa frase o paragrafo;
      `builder.md` nomina «a vista» e `[ ]`. Oggi nessuno dei tre contiene «a vista».

**Non regressione:**
- I PBI senza marca danno gli stessi rilievi, avvisi e sonde di prima: i test di `PBI-520` e `PBI-521`
  restano verdi senza cambiare.
- `python3 -m pytest -q tools/tests` resta verde.

## Protocollo di rifinitura

Si può scegliere senza chiedere:
- i nomi interni e il testo esatto del rilievo di forma e della sezione della PR, purché portino le
  parole che i criteri cercano;
- dove sta la riga **V** nei tre file di `backlog/README.md` e del template.

Si scrive come domanda (e si chiama `fermati`):
- se la sezione della PR supera il limite del corpo che `apri_pr()` già gestisce;
- se un PBI di `main` di questo repository risulta avere un criterio marcato a vista per caso.

## Dopo il merge (non è un criterio)

Nei tre progetti si rileggono le PBI in coda e si marcano i criteri a vista, se ce ne sono: oggi non
ce n'è nessuno, ed è la misura da ripetere fra un mese. Il conto va in una nota di `ADR-0032`: quanti
criteri a vista sono nati, quante volte chi mergia ha tolto una spunta, quanti rilievi `V`.
