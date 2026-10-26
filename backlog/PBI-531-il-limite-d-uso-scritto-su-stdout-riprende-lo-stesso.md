# PBI-531: il limite d'uso scritto su stdout riprende lo stesso

**Stato:** proposto il 26/10; **non letto**, **non in coda**. La domanda ❓1 ha una proposta
(*Deciso*, punto 1) che il merge della PR che accoda ratifica.

## Direttiva

Il 25/10 alle 23:25 il tick ha lanciato `PBI-524`; il Builder ha lavorato 6 minuti, fatto 2 commit e
la CLI è uscita con codice 1 e `You've hit your session limit · resets 12:10am (Europe/Rome)`. Il
giro è chiuso `senza esito` (`builder-senza-esito`) con `riprendi_dopo: ""` e `riprese_limite: 0`.
Da allora il tick ha scritto `attende: PBI-524 ha un ramo su origin e non è in main — nessuna PR sul
ramo` ogni 10 minuti fino alle 08:05 del 26/10, otto ore dopo il reset, finché una persona non ha
chiuso il giro a mano. È il caso che `PBI-519` doveva coprire.

La causa: `riprendi_dopo_il_limite()` (`tools/asdlc/runner.py`) cerca la frase **solo nel file di
stderr** dell'invocazione (`PBI-519`, decisione 1, per `ADR-0027`). Qui lo stderr è vuoto (0 byte) e
la frase sta nello **stdout** (62 byte, solo quella riga): `nota_senza_esito()` la legge da lì e
scrive «reset alle 12:10am» nella nota, ma `riprendi_dopo` resta vuoto e il tick non sa riprendere.
`PBI-519` aveva visto la frase su stderr («7:50pm», «2:10am»); la CLI di oggi la scrive su stdout.

Settimo fermo meccanico della settimana. Il guasto nasconde un secondo difetto, già in `PBI-525`
(punto 4, criterio 5): il giro fermato ha lasciato nel worktree del runner una modifica non committata
(`tools/tests/test_asdlc_runner.py`, +25 righe) che ferma ogni lancio con `albero-sporco-all-ingresso`.
`PBI-525` è accodato **dopo** `PBI-524`, che non parte per quel difetto: finché una persona non pulisce
l'albero, la coda è in stallo.

**Scope**

- `tools/asdlc/runner.py` — `riprendi_dopo_il_limite()`: oltre allo stderr, lo stdout conta **solo**
  se è la frase del limite e nient'altro (vedi *Deciso*, punto 1). `limite_d_uso()` non cambia.
- `tools/tests/` — i test dei criteri, accanto a quelli di `PBI-519`; il finto agente dei test scrive
  la frase su stdout.
- `backlog/PBI-531-il-limite-d-uso-scritto-su-stdout-riprende-lo-stesso.md` — questo file, per la spunta.
- **Fuori scope:** il worktree sporco dopo un giro fermato (è `PBI-525`, criterio 5); la
  classificazione di `builder-senza-esito`; il tetto di 3 riprese di `PBI-519`.

## ❓ Domanda aperta

**❓1 — Come si distingue la frase della CLI da un modello che la cita su stdout?** `ADR-0027`: un
esito non si ricava dal testo libero di un modello, e lo stdout lo è. Alternative: (a) lo stdout conta
solo se, tolti gli spazi, è **una sola riga** che coincide per intero con `FRASE_DEL_LIMITE` + l'ora, con
codice d'uscita ≠ 0 e **nessuna chiamata a strumento** nel file `.chiamate.jsonl`; (b) leggere l'evento
d'errore strutturato nella traccia della sessione (`.sessione.jsonl`), se la CLI ne scrive uno per il
limite; (c) lasciare lo stderr come unica fonte e chiedere alla CLI di scrivere lì (non dipende da noi).

## ✅ Deciso (proposta, ratificata dal merge)

1. **(a), e (b) se la traccia ha l'evento.** Una riga intera e nient'altro, codice ≠ 0, zero chiamate a
   strumento: un modello che racconta il limite scrive altro intorno, o ha chiamato `fatto`/`fermati`.
   Se la traccia porta un errore strutturato per il limite, il Builder lo preferisce e (a) resta il
   ripiego; l'ordine lo sceglie lui e lo scrive nel commit.

## Dipendenze
- Bloccato da: nessuno.
- Blocca: niente per forza, ma ogni limite d'uso su stdout ferma la coda finché una persona non interviene.

## Contesto
- `tools/asdlc/runner.py`: `FRASE_DEL_LIMITE`, `ORA_DEL_RESET`, `limite_d_uso()`,
  `riprendi_dopo_il_limite()`, `ora_di_ripresa()`, `nota_senza_esito()`.
- `tools/asdlc/coda.py`: `riprendi_dopo()`, `ultimo_esito()`, `RIPRESE_MASSIME`.
- `runs/20261025-232512.json` e `…-232645-724204_builder_esito.json.{stdout,stderr}` nell'albero del
  runner; `runs/coda.log` dal 25/10 23:35 al 26/10 08:05.
- `backlog/PBI-519-il-limite-d-uso-non-ferma-la-coda.md`, decisione 1.

## Verifica
- [ ] **Una riga di limite su stdout, stderr vuoto e codice 1 danno `riprendi_dopo`.** Un finto agente
      esce con 1, stdout `You've hit your session limit · resets 12:10am (Europe/Rome)`, stderr vuoto:
      `riprendi_dopo_il_limite()` rende l'ISO della prima 12:10 successiva più `MARGINE_DEL_RESET`.
      Rosso su `main`: oggi rende `""`.
- [ ] **La stessa frase con codice 0, o dentro altro testo, o con una chiamata a strumento, non
      riprende.** È la **guardia** di `ADR-0027`: tre casi, ciascuno rende `""`.
      `Guardia-su: riprendi_dopo_il_limite`.
- [ ] **Lo stderr con la frase riprende come prima.** Il caso di `PBI-519`, invariato.
      `Guardia-su: riprendi_dopo_il_limite`.

**Non regressione:** `python3 -m pytest -q tools/tests` resta verde; i test di `PBI-519` non cambiano.

## Protocollo di rifinitura
Si può scegliere senza chiedere: dove sta la lettura dello stdout, e se (b) esiste nella traccia.
Si chiama `fermati`: se la CLI scrive il limite in un posto che non è né stdout né stderr né la traccia.
