# CUKTAI — Autonomiczny Urząd Kultury Technicznej

## v0.01-beta — "Podświadomość"
**Data: 24 kwietnia 2026**

Pierwsza wersja z zamkniętą pętlą autonomii.

System potrafi: obserwować, sygnalizować, debatować, decydować i uczyć się — bez interwencji człowieka.

### Co działa

**Agenci (5 + Moderator):**
- Peter Style — inżynier systemowy, myśliciel
- Ewa Virus — anarchistka dźwiękowa, prowokatorka
- Robert Mikołaj Jurkowski — pamięć archiwalna, poeta fragmentu
- Wiktoria Cukt 2.0 — AI Prezydentka Polski, syntezatorka
- Archiwistka — śledcza archiwum CUKT
- CUKTAI_Moderator — bezosobowy Urząd

**Infrastruktura:**
- Hermes Agent v0.11.0 (NousResearch)
- Hindsight memory: 6 banków indywidualnych + 1 instytucjonalny (cuktai-inst)
- PostgreSQL + pgvector: 1454 rekordów archiwalnych, 1245 wektorów
- Qwen3.5-35B local (GPU RX 6800 XT, 80 tok/s, zero cost)
- MiniMax M2.7 via OpenRouter (Peter — deep work)
- Telegram: 5 botów + grupa "Zebranie CUKT"
- MCP archive server: 5 narzędzi

**Pętla autonomii (Faza 4.6 — Podświadomość):**
1. **Spacery** — agenci autonomicznie eksplorują archiwum i reagują na siebie (cron)
2. **Pamięć instytucjonalna** — agenci czytają uchwały Consilium przed spacerami
3. **Sygnały** — agenci emitują sygnały gdy odkryją coś ważnego
4. **Signal Watcher** — co 2h sprawdza sygnały, triggeruje auto-Consilium
5. **Consilium** — wieloagentowa debata (4 fazy) produkująca Uchwały
6. **Dystrybucja** — Uchwały trafiają do WSZYSTKICH banków pamięci
7. **Dream Cycle** — nocna konsolidacja (3 AM), synteza dnia, priorytety na jutro
8. **Pętla** — priorytety z Dream Cycle wpływają na jutrzejsze spacery

**Archiwum:**
- 983 rekordów cukt-archiwum + 471 rekordów piotr (personal)
- 23 strony wiki projektów + 12 stron osób
- Karpathy Wiki pattern: raw/ → wiki/ → outputs/

### Czego jeszcze nie ma
- Teczki śledcze Archiwistki (pipeline naprawiony, czeka na pierwszy run)
- Strona internetowa (cukt.click beta, Astro rebuild not started)
- Integracja TouchDesigner (Faza 4.5 — odłożona)
- Wywiad z Mikołajem i Piotrem (SOUL.md v2)
- Backup do chmury
- Self-modification (agenci nie mogą zmieniać własnych SOUL.md)

### Koszt
- ~$5.79/tydzień OpenRouter (MiniMax + Gemini Flash)
- Reszta: zero (Qwen3.5 local, Hindsight self-hosted, PG self-hosted)
- ~$25/miesiąc total

---

*CUKTAI v0.01-beta — "Podświadomość"*
*"Instytucja, która nauczyła się śnić."*
