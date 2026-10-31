# ADR-0035: le notifiche su Slack sono accese in ogni progetto

**Stato:** **Proposta** · **Data:** 2026-10-31 · **Ratifica:** Francesco, con il merge
(`ADR-0012`, `ADR-0029`). Non cambia la costituzione: `AGENTS.md` non parla di notifiche.
Restringe la decisione 8 di `PBI-533` («spente se la sezione manca») per i progetti, non per il
codice: il default del runner resta spento, e ogni progetto le accende nel suo `asdlc.toml`.

## Contesto

`PBI-533` (`v1.1.0`) manda gli eventi del tick su Slack. Il 31/10 Francesco ha creato il canale
`#asdlc` (pubblico nel workspace Lara) e il webhook, in `~/.config/asdlc/slack-webhook` sulla
macchina dei tick; le notifiche erano accese solo in `ada_asdlc`. Francesco ha chiesto di
accenderle «di default per tutti i progetti, anche quelli futuri».

Il default del codice (`Notifiche.attive = False`, `config.py`) si potrebbe girare, ma ha due
costi: ogni test che costruisce un progetto senza `[notifiche]` proverebbe a mandare e scriverebbe
«notifica non inviata» nel log, e una macchina senza webhook scriverebbe quella riga a ogni evento.

## Decisione

1. **Ogni progetto ha `[notifiche]` con `attive = true` e tutti gli eventi.** I cinque di oggi
   (`ada_asdlc`, `ada_nlt`, `ada_dispense`, `ada_unical`, `ada_planning`) la ricevono con una PR di
   configurazione ciascuno (31/10); i progetti futuri dal `template/asdlc.toml`, che la porta
   accesa da questo ADR.
2. **Il default del runner resta spento:** un `asdlc.toml` senza la sezione non manda niente
   (`PBI-533`, decisione 8). È il default di chi usa il pacchetto senza il template, e dei test.
3. **Un progetto che le spegne lo scrive**, con `attive = false` e un commento che dice perché.
4. **Il canale è uno, `#asdlc`, e il webhook è uno per macchina:** ogni messaggio porta il nome
   del progetto. Un webhook che manca resta una riga «notifica non inviata» nel log, e il tick
   prosegue (`ADR-0008`).

## Conseguenze

- **Positive:** ciò che fa il tick di ogni progetto si vede su Slack senza aprire i log; un progetto
  nuovo nasce già collegato.
- **Negative:** il canale riceve i messaggi di cinque progetti; chi lo legge dal telefono deve
  regolarne le notifiche.
- **Neutre:** il codice non cambia; un canale per progetto resta possibile con un webhook per
  progetto, quando servirà (non oggi).

## Alternative considerate

- **Girare il default del codice a `true`:** scartata per i costi del *Contesto*: test e macchine
  senza webhook scriverebbero una riga a ogni evento.
- **Un canale per progetto:** scartata per ora. Il webhook è di macchina (`PBI-533`, decisione 6);
  un canale per progetto chiederebbe un webhook per progetto e una chiave nuova in `[notifiche]`.
