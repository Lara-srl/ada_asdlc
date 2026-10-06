# ADR-0009: Gli E2E Playwright girano dentro `ci.yml`, sullo stack Docker

**Stato:** Accettata · **Data:** 2026-08-17

## Contesto

La Fase 1 ha trovato tre difetti che né pytest né vitest potevano trovare, e sono tutti
della stessa specie:

- il frontend **non chiamava** `POST /pratiche` né `POST /pratiche/{id}/transizione`: gli
  endpoint esistevano, erano testati, ed erano nella collection Postman. Dall'app non si
  poteva aprire una commessa;
- cancellare un utente con una storia rispondeva **500** — la suite non poteva prenderlo,
  perché gira su **SQLite senza foreign key attive**;
- dietro `tailscale serve`, nginx vedeva sempre il gateway Docker come indirizzo del client,
  e il limitatore anti-brute-force diventava un secchio unico condiviso: un operaio che
  sbaglia il PIN avrebbe bloccato Barbara.

Il denominatore comune: **il difetto sta fra i pezzi**, dove nessun test unitario guarda.

## Decisione

Un job `e2e` in **`ci.yml`**: `docker compose up -d --build` (Postgres vero, migrazioni
vere, nginx vero), seed deterministico, **Playwright** headless su Chromium contro
`http://localhost:8081`. Gira su ogni PR e su ogni push in `main`.

Poiché `release.yml` richiama `ci.yml` con `uses:`, **un tag non scavalca nemmeno gli E2E**.

## Conseguenze

**Positive**
- Il giro che il collaudo manuale percorre a mano — apri, conferma, compila, prezza, chiudi —
  diventa un test che gira da solo a ogni PR.
- Postgres vero significa foreign key attive: la classe di difetti del 409/500 è coperta.
- Gli scenari Gherkin delle spec smettono di essere prosa: quelli marcati `[e2e]` hanno un
  test con lo stesso nome.

**Negative**
- La PR costa qualche minuto in più e un runner più carico.
- I test E2E sono i più fragili della piramide: si ancorano a **`data-testid`** dichiarati in
  `e2e/contract.ts`, non a testo o struttura del DOM.
- Il gateway LLM in CI non ha chiavi: gli scenari di chat verificano **l'orchestrazione**
  (tool chiamato, evento pubblicato, pratica creata) con un provider finto, non le risposte
  del modello.

## Alternative considerate

**E2E solo sul tag.** Più veloce sulle PR, ma il difetto arriva quando il codice è già in
`main` — cioè quando costa di più toglierlo.

**E2E non bloccanti.** Un gate che non blocca è documentazione: dopo il terzo rosso ignorato
nessuno lo guarda più.
