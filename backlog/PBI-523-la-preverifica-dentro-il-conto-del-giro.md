# PBI-523: la pre-verifica dentro il conto del giro

**Stato:** proposto il 21/10, **non letto e non accodato**. Il codice che tocca nasce con `PBI-522`
e su `main` non c'è ancora: la lettura avversariale si fa dopo il merge del 522.

## Direttiva

`PBI-522` mette la pre-verifica dentro il giro, dopo il controllo dell'albero pulito e prima
dell'inventario d'inizio (decisione 2). Nel suo giro 1 il Builder ha trovato due casi di guasto del
Lettore in cui quest'ordine fa perdere qualcosa al giro. Francesco (21/10) li ha lasciati al 522 come
limite dichiarato, e le due correzioni proposte dal Builder sono questo PBI:

- **(1) Un albero del Lettore non smontato non si conta.** `worktree_usa_e_getta` conta in
  `USA_E_GETTA` gli alberi montati e smontati, e `chiudi()` dichiara nella nota «albero usa e getta
  montato e non smontato» quando i due numeri divergono (`PBI-363`, decisione 6). Ma il giro
  fotografa `contati = Counter(USA_E_GETTA)` **dopo** la pre-verifica: un albero del Lettore che
  `git worktree remove` non smonta non entra nella differenza, e la nota non lo dice. È la strada
  che il commento di `USA_E_GETTA` vuole chiusa: «se una strada salta lo smontaggio, i due numeri
  divergono anche senza un avviso».
- **(2) Un Lettore che sporca l'albero del giro non ferma il giro.** Il Lettore ha `Write` ed
  `Edit`, col `cwd` nel suo albero (`PBI-521`, decisione 3), e `ADR-0031` (decisione 5) vuole che la
  pre-verifica non tocchi l'albero del progetto. Se lo toccasse, con un percorso assoluto, il
  controllo `albero-sporco-all-ingresso` è già passato: il Builder parte su un albero sporco, e il
  giro finisce nei giri d'igiene invece di chiudere subito col motivo giusto.

Questo PBI sposta la fotografia del conto prima della pre-verifica e ripete il controllo dell'albero
pulito dopo. L'ordine della decisione 2 del 522 non cambia: la pre-verifica resta prima di
`inventario()` e del ramo.

**Scope**

- `tools/asdlc/runner.py`, `esegui_pbi()`:
  - `contati = Counter(USA_E_GETTA)` prima del blocco della pre-verifica, e non dopo;
  - dopo il blocco della pre-verifica, quando la pre-verifica ha girato in questo giro, un secondo
    `git status --porcelain`, che con l'albero sporco chiude `albero-sporco-all-ingresso`.
- `tools/tests/test_asdlc_preverifica_nel_giro.py` — i test dei criteri, con l'impianto del 522
  (`giro_sul_clone`, `accendi`).
- `README.md`, sezione `### La pre-verifica nel giro` — il paragrafo «Un limite dichiarato» scritto
  dal giro 2 del 522 si riscrive per dire cosa fa il giro adesso, nello stesso commit del codice.
- `backlog/PBI-523-la-preverifica-dentro-il-conto-del-giro.md` — questo file, per la spunta.

**Fuori scope**

- L'inventario d'inizio resta dopo la pre-verifica (decisione 2 del 522): un albero del Lettore non
  smontato continua a comparire fra i «residui dei giri prima» nel log. Questo PBI lo fa contare,
  non lo sposta.
- Le due uscite della pre-verifica, `preverifica` e `lettore-senza-esito`, chiudono prima di
  `chiudi()` e non fanno inventario. Un albero non smontato lì resta solo nella stampa «worktree
  non smontato» di `worktree_usa_e_getta`.
- Togliere `Write` ed `Edit` al Lettore, o cambiarne il `cwd`: sono di `PBI-521`.
- `--riprendi`, che non lancia la pre-verifica (522, criterio 6), e non ha niente da ricontrollare.

## ✅ Deciso

1. **Solo la fotografia si sposta.** `contati` si prende prima della pre-verifica; `e.inventario
   ["inizio"]`, `e`, `t0` e il resto restano dove sono.
2. **Il secondo controllo usa il motivo che c'è.** Con l'albero sporco dopo la pre-verifica il giro
   chiude `albero-sporco-all-ingresso`, la stessa uscita del primo controllo, senza ramo, commit, PR
   né Solver. Nessuna riga nuova in `USCITE`, quindi `USCITE_DEL_GIRO` non cambia.
3. **Solo quando la pre-verifica ha girato.** Con la sezione spenta, con `--riprendi` e con una
   versione del PBI già letta pronta il secondo controllo non serve: il primo ha appena guardato lo
   stesso albero.

## Dipendenze

- Bloccato da: `PBI-522` (il blocco della pre-verifica in `esegui_pbi()`, i test e il `README`).

## Contesto

- `backlog/PBI-522-la-preverifica-nel-giro-e-nel-tick.md`: la decisione 2 e la sezione «Il giro 2,
  e cosa si riprende», con la domanda del Builder e la risposta.
- `tools/asdlc/runner.py`: `esegui_pbi()` (il controllo `albero-sporco-all-ingresso`, il blocco della
  pre-verifica, `inventario()`, `contati`, `chiudi()`), `USA_E_GETTA`, `worktree_usa_e_getta`.
- `tools/tests/test_asdlc_preverifica_nel_giro.py`: `giro_sul_clone` sostituisce `esegui` e lascia
  passare i `git` veri; un test può intercettare lì `git worktree remove`, o far scrivere al
  Lettore finto un file nel clone prima di rendere `letto`.

## Verifica

I test accendono `[preverifica]` col Lettore (`accendi(monkeypatch, lettore=True)`) e usano il Lettore
finto del 522, che chiama `letto` senza rilievi.

- [ ] **Un albero del Lettore non smontato entra nel conto del giro.** `git worktree remove` fallisce
      per l'albero del Lettore, il Builder finto chiama `fermati`. La nota del giro contiene «1
      albero usa e getta montato e non smontato» e `e.inventario["usa_e_getta"]` è `{"montati": 1,
      "smontati": 0}` (pytest, `git` vero per tutto il resto). Rosso atteso: dopo il 522 il conto è
      `{"montati": 0, "smontati": 0}`.
- [ ] **Un Lettore che sporca l'albero del giro ferma il giro prima del ramo.** Il Lettore finto
      scrive un file non tracciato nel clone, fuori dal suo albero, e chiama `letto` senza rilievi.
      Il giro dà `motivo == "albero-sporco-all-ingresso"` e `stato == "fermato"`, il Builder finto
      non è invocato, `git branch` è uguale a prima ed `e.solver` è vuoto (pytest, `git` vero).
      Rosso atteso: dopo il 522 il Builder parte.

**Non regressione:**

- `python3 -m pytest -q tools/tests` resta verde.
- Con `[preverifica]` assente il giro è quello di oggi: i test esistenti di `esegui_pbi()` passano
  senza modifiche.

## Protocollo di rifinitura

Si può scegliere senza chiedere:

- il dettaglio dell'uscita `albero-sporco-all-ingresso` del secondo controllo, purché dica che
  l'albero si è sporcato durante la pre-verifica;
- come il test fa fallire lo smontaggio, purché fallisca solo per l'albero del Lettore.

Si scrive come domanda (e si chiama `fermati`):

- se uno dei due criteri nasce verde sulla base: vuol dire che il 522 è cambiato dopo questo PBI.
