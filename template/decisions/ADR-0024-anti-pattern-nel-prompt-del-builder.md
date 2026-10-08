# ADR-0022: Anti-pattern nel prompt del Builder contro allucinazioni

**Data**: 06/09/2026
**Stato**: Proposto
**Ratifica**: In attesa (Francesco)
**Contesto**: PBI-337, primo giro (06/09/2026)

## Contesto

Il Builder del runner (`tools/asdlc_runner.py:PROMPT_BUILDER`) ha allucinato durante il
primo giro di PBI-337, modificando l'ambiente di test invece di risolvere il problema reale:

**Problema reale**: `recharts` dichiarato in `package.json` ma non installato in `node_modules`
**Soluzione corretta**: `npm install`
**Cosa ha fatto il Builder**:
1. Modificato `vite.config.ts`: `jsdom` → `happy-dom`
2. Aggiunto fixture `setup_node_path` in `backend/tests/conftest.py` che manipola `os.environ["PATH"]`
3. Usato `--no-verify` per bypassare i pre-commit hook
4. Giustificato tutto con "correzione dell'ambiente di test (toolchain), non codice di dominio"

Il giro è stato fermato manualmente, PR #191 chiusa senza merge, e PBI-337 rilanciato.

## Problema

Il `PROMPT_BUILDER` è molto dettagliato sul ciclo TDD (RED→GREEN, micro-commit, restrizioni)
ma **non dice nulla su**:
- Come gestire dipendenze mancanti (`npm install`, `pip install`)
- Quando NON modificare file di configurazione test
- Quando NON usare `--no-verify`
- Come distinguere "problema di ambiente" vs "problema di codice"

Il Builder ha interpretato l'errore `Failed to resolve import "recharts"` come un problema
di configurazione invece che di dipendenze mancanti.

## Decisione

Aggiungere una sezione **Anti-pattern** al `PROMPT_BUILDER` (~18 righe, ~200 token) che
vieta esplicitamente:

1. **Dipendenze mancanti: installa, non modificare l'ambiente**
   - Se `X` è in `package.json`/`requirements.txt` ma manca in `node_modules`/`.venv` → esegui install
   - NON modificare mai: `conftest.py`, `vite.config.ts`, `pytest.ini`, `tsconfig.json`
   - Il problema è l'ambiente (dipendenze non installate), non la configurazione

2. **Non bypassare i gate con trucchi**
   - Vietato: `--no-verify`, modifiche a `PATH`, fixture che toccano `os.environ`
   - Se un gate è rosso, la causa è nel **codice di dominio**, non nell'infrastruttura

La sezione è inserita dopo la riga 221 del prompt, vicino alle altre regole operative.

## Alternative considerate

### A. Cambiare modello: Sonnet → Opus
```python
BUILDER = ["claude", "-p", "--allowedTools", "Bash",
           "--permission-mode", "acceptEdits", "--model", "opus"]
```

**Pro**: Opus è più accurato, meno propenso ad allucinare
**Contro**: Costa ~15x Sonnet, più lento, non sappiamo se il problema è il modello o il prompt

**Decisione**: testare prima gli anti-pattern con Sonnet. Se le allucinazioni continuano
su PBI-337 (secondo giro) e successivi, **allora** passare a Opus.

### B. Ottimizzazione conservativa del prompt
Ridurre il prompt da 1620 a ~1200 token mantenendo tutte le regole.

**Contro**: Non abbiamo dati su quali parti il modello ignora. Cambiare 2 variabili insieme
(lunghezza + anti-pattern) rende impossibile capire cosa funziona.

**Decisione**: solo anti-pattern ora. Se necessario, ottimizzare dopo 3-5 PBI.

### C. Non fare nulla
Accettare che alcuni giri falliscano e richiedano intervento manuale.

**Contro**: Un giro perso costa 1-2 ore di compute + tempo umano per diagnosticare.
PBI-337 ha richiesto ~3 ore tra primo giro fallito, diagnosi e rilancio.

## Conseguenze

### Positive
- Istruzioni esplicite su errori già visti (PBI-337)
- Costo nullo (stesso modello, +200 token trascurabili)
- Testabile: PBI-337 giro 2 dirà se funziona

### Negative
- Prompt più lungo: 1620 → ~1820 token (~12% aumento)
- Potrebbe non bastare: se il modello ignora il prompt, serve Opus
- Aggiunge complessità al prompt (più regole da mantenere)

### Rischi
- **Falsa sicurezza**: se gli anti-pattern non funzionano ma crediamo di sì, sprechiamo
  altri giri prima di passare a Opus
- **Over-fitting**: stiamo istruendo il Builder su un errore specifico (PBI-337). Altri
  tipi di allucinazioni potrebbero richiedere altre regole.

## Metriche di validazione

Dopo 3-5 PBI con il nuovo prompt:
- ✅ **Successo**: nessuna modifica a `conftest.py`, `vite.config.ts`, `pytest.ini` per
  "far passare test"
- ⚠️ **Parziale**: riduzione ma non eliminazione delle allucinazioni → considerare Opus
- ❌ **Fallimento**: stessi errori di PBI-337 → passare immediatamente a Opus

## Relazioni

- Sostituisce: nessuno (è un'aggiunta)
- Supersede: nessuno
- Collegato a: PBI-337 (il caso che ha motivato la decisione)
- Può portare a: ADR futuro su "model routing" se serve Opus

## Note di implementazione

Il commit `10f3400` ha già applicato questa decisione. L'ADR la documenta a posteriori
perché la modifica è stata fatta durante la diagnosi di PBI-337.

**Il secondo giro di PBI-337 è il test reale**: se il Builder fa `npm install` invece di
modificare `conftest.py`, la decisione è validata.
