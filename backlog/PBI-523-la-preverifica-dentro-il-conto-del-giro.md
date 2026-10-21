# PBI-523: la pre-verifica dentro il conto del giro

**Stato:** proposto il 21/10, letto il 21/10 su `main` `987c606` (la `v0.6.0`, che contiene
`PBI-522`): vedi in fondo.

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
- Il rapporto della lettura. Quando il secondo controllo ferma il giro, il rapporto
  `runs/<run>-<PBI>-preverifica.json` della lettura appena fatta resta: se è senza rilievi, al giro
  dopo la stessa versione del PBI non si rilegge (`preverifica_gia_letta`, decisione 3 del 522).
  È voluto: il PBI era pronto, era l'albero a essere sporco.

## ✅ Deciso

1. **Solo la fotografia si sposta.** `contati` si prende prima della pre-verifica; `e.inventario
   ["inizio"]`, `e`, `t0` e il resto restano dove sono.
2. **Il secondo controllo usa il motivo che c'è.** Con l'albero sporco dopo la pre-verifica il giro
   chiude `albero-sporco-all-ingresso`, la stessa uscita del primo controllo, senza ramo, commit, PR
   né Solver. Nessuna riga nuova in `USCITE`, quindi `USCITE_DEL_GIRO` non cambia.
3. **Solo quando la pre-verifica ha girato.** Il secondo controllo sta nel ramo `else` di
   `preverifica_gia_letta`, dopo i due `return` (`lettore-senza-esito` e `preverifica`), **con o
   senza Lettore**: con `lettore = false` la pre-verifica scrive lo stesso il suo rapporto. Con la
   sezione spenta, con `--riprendi` e con una versione del PBI già letta pronta non serve: il primo
   controllo ha appena guardato lo stesso albero. L'`Esito` della seconda uscita porta `base` e
   `sha_pbi`, come le altre due uscite della pre-verifica.

## Dipendenze

- Bloccato da: `PBI-522` (il blocco della pre-verifica in `esegui_pbi()`, i test e il `README`).

## Contesto

- `backlog/PBI-522-la-preverifica-nel-giro-e-nel-tick.md`: la decisione 2 e la sezione «Il giro 2,
  e cosa si riprende», con la domanda del Builder e la risposta.
- `tools/asdlc/runner.py`: `esegui_pbi()` (il controllo `albero-sporco-all-ingresso`, il blocco della
  pre-verifica, `inventario()`, `contati`, `chiudi()`), `USA_E_GETTA`, `worktree_usa_e_getta`.
- `tools/tests/test_asdlc_preverifica_nel_giro.py`: `giro_sul_clone` sostituisce `esegui` e lascia
  passare i `git` veri. `giro_sul_clone` non ha un parametro per intercettare: il test avvolge
  di nuovo `runner.esegui` **dopo** averlo chiamato. L'albero del Lettore è il `cwd` della sua
  invocazione, quindi il `git worktree remove` da far fallire è quello che nomina quella cartella.
  Il Lettore finto può scrivere un file nel clone prima di rendere `letto`, e il clone di prova
  non ha `.gitignore` (`FILE_DELLA_BASE`, `test_asdlc_preverifica.py`). Il Builder finto che chiama
  `fermati` è `fermati()` di `test_asdlc_runner.py`.

## Verifica

I test accendono `[preverifica]` col Lettore (`accendi(monkeypatch, lettore=True)`) e usano il Lettore
finto del 522, che chiama `letto` senza rilievi.

- [x] **Un albero del Lettore non smontato entra nel conto del giro.** `git worktree remove` fallisce
      per l'albero del Lettore, il Builder finto chiama `fermati`. La nota del giro contiene «1
      albero usa e getta montato e non smontato» e `e.inventario["usa_e_getta"]` è `{"montati": 1,
      "smontati": 0}` (pytest, `git` vero per tutto il resto). Rosso atteso: dopo il 522 il conto è
      `{"montati": 0, "smontati": 0}`.
- [x] **Un Lettore che sporca l'albero del giro ferma il giro prima del ramo.** Il Lettore finto
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

## La lettura avversariale del 21/10

Un lettore in sola lettura ha provato il PBI sul codice di `main` (`987c606`). Ha scritto i test dei
due criteri come sonde in un albero usa e getta:

- su `main` nascono **rossi** tutti e due, per la ragione che dice la Verifica (conto
  `{"montati": 0, "smontati": 0}`; il Builder parte e il ramo nasce);
- con un GREEN abbozzato (la fotografia più su e il secondo controllo nel ramo `else`) diventano
  verdi, e la suite dava `1188 passed`.

**Erano da correggere, tutti recepiti:**

- la riga «Stato» diceva il 522 non ancora su `main`, e il Builder l'avrebbe letta come una
  dipendenza aperta;
- la decisione 3 non diceva dove sta il secondo controllo né se vale senza Lettore;
- il Contesto non diceva come intercettare `git worktree remove` in `giro_sul_clone`;
- il rapporto della lettura che resta dopo il secondo controllo (Fuori scope), e la `base` e lo
  `sha_pbi` della seconda uscita (decisione 3).

**Verificato senza rilievi:**

- nessun altro albero usa e getta si monta prima di `fermati`, che passa da `chiudi()`;
- il secondo controllo non sporca ogni giro: in produzione `runs/` è ignorato (eccetto
  `runs/tempi.csv`), nei test `LOG_DIR` sta fuori dal clone, e l'albero del Lettore sta in `/tmp`;
- nessun test esistente si rompe: le uscite di `USCITE_DEL_GIRO` che passano dalla pre-verifica
  escono prima del secondo controllo, e nessun'altra suite accende `[preverifica]`;
- i due GREEN non fanno nascere verde l'altro criterio, e la guardia di fase in `IMPL` lascia
  scrivere `runner.py` e `README.md`;
- i nomi e i fatti citati esistono nel codice e dicono ciò che il PBI afferma.
