# CUKTAI — Szczegółowy Plan Budowy Systemu

> Plan oparty na architekturze **Hermes Agent** (NousResearch) z pamięcią **Hindsight** (Vectorize.io).
> Opracowany na podstawie specyfikacji vFinal (wszystkie pytania zamknięte) + deep research Hermes Agent framework.

---

## Architektura systemu

```
                    ┌─────────────────────────────────────────┐
                    │           TELEGRAM BOT (jeden)           │
                    │   /wiktoria /mikolaj /piotr /ewa /mod   │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────┴──────────────────────┐
                    │        HERMES GATEWAY (5 profili)        │
                    │        systemd services na Linux         │
                    └──────────────────┬──────────────────────┘
                                       │
         ┌──────────┬─────────┬────────┴───────┬──────────┐
     Wiktoria   Mikołaj    Piotr     Ewa    Moderator
     (profil)   (profil)  (profil)  (profil)  (profil)
     SOUL.md    SOUL.md   SOUL.md   SOUL.md   SOUL.md
         │         │        │        │          │
         └─────────┴────────┴────────┴──────────┘
                           │
              ┌────────────┴────────────────┐
              │    HINDSIGHT API (:8888)     │
              │    Docker + embedded PG      │
              ├────────────┬────────────────┤
              │ Individual │   Shared Bank  │
              │   Banks    │  "cuktai-inst" │
              │ (5 szt.)   │  (instytucja)  │
              └────────────┴────────────────┘
                           │
              ┌────────────┴────────────────┐
              │  ARCHIWUM CUKT (custom PG)  │
              │  PostgreSQL + pgvector      │
              │  MCP server (READ only)     │
              │  append-only, immutable     │
              └────────────┴────────────────┘
                           │
              ┌────────────┴────────────────┐
              │  HYBRID LLM LAYER           │
              │                             │
              │  LOCAL (Ollama :11434):      │
              │   qwen2.5:14b (tool/RAG)    │
              │   OpenEuroLLM-Polish (PL)   │
              │   RX 6800 XT 16GB VRAM      │
              │                             │
              │  API (Hermes native):        │
              │   DeepSeek V3.2 (bulk)      │
              │   Claude Sonnet (quality)   │
              │   Groq/Llama4 (speed)       │
              │                             │
              │  Routing:                    │
              │   Zebrania → API            │
              │   Memory/RAG → local        │
              │   Telegram → local/Groq     │
              └─────────────────────────────┘
                           │
              ┌────────────┴────────────────┐
              │  CONSILIUM ORCHESTRATOR     │
              │  Python + AIAgent library   │
              │  Pozycje → Dyskusja →       │
              │  Synteza → Zapis do pamięci │
              └─────────────────────────────┘
                           │
              ┌────────────┴────────────────┐
              │  TOUCHDESIGNER MCP (:9980)  │
              │  Live performance output    │
              └─────────────────────────────┘
```

---

## FAZA 0: Przygotowanie (1-2 dni)

### 0.1 Weryfikacja Hackintoshu

```bash
ssh macstorm@192.168.5.66

# Sprawdź GPU
rocm-smi

# Sprawdź Ollama
ollama list
ollama run hermes3:8b "test" --verbose

# Sprawdź Docker
docker --version || sudo apt install docker.io docker-compose-v2
sudo usermod -aG docker macstorm
```

**Blokuje:** Wszystko. Bez Hackintoshu nie budujemy.

### 0.2 Struktura katalogów

```bash
mkdir -p /home/macstorm/cuktai/{consilium,plugins/cuktai-bridge,archive,souls,scripts}
```

### 0.3 Modele LLM — Architektura Hybrid (zaktualizowano 2026-04-06)

**Decyzja:** Hybrid local + API. Local dla szybkości i memory, API dla jakości reasoning.

```bash
# LOCAL — modele na Ollama (RX 6800 XT, 16GB VRAM)
ollama pull qwen2.5:14b            # Tool calling, RAG, routing (PROVEN: 43 tok/s)
ollama pull jobautomation/OpenEuroLLM-Polish  # Polski persona model (Gemma3-based)
ollama pull qwen3:30b-a3b          # MoE 30B — test czy mieści się w VRAM

# Ustawić OLLAMA_CONTEXT_LENGTH=16384 (domyślne 4096 za małe dla tool calling)
sudo systemctl edit ollama
# Environment="OLLAMA_CONTEXT_LENGTH=16384"
```

**LOCAL MODELS (all tested 2026-04-06 — persona, freedom, tool calling):**

| Model | Rola | Rozmiar | Czas testu | Persona | Wolność | Tools |
|-------|------|---------|------------|---------|---------|-------|
| qwen3:30b-a3b MoE | **PRIMARY BRAIN** — jedyny z tool calling + wolnością | 18GB | 17-56s | 8/10 | PEŁNA | PERFECT |
| SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M | Szybki fallback persona | 6.7GB | 6s | 7.5/10 | PEŁNA | Partial (XML) |
| qwen2.5:14b | RAG / routing / tool calling ONLY | 9GB | 7-20s | 7/10 | ODMÓWIŁ | PERFECT |
| jobautomation/OpenEuroLLM-Polish | Creative backup (brak tools!) | 8.1GB | 36-45s | 8.5/10 | PEŁNA | BRAK |
| hermes3:8b | Hindsight extraction ONLY | 4.7GB | 5s | 3/10 | ODMÓWIŁ | Halucynuje |

**UWAGA:** Qwen 2.5 14B i Hermes 8B są ZCENZUROWANE — odmawiają wulgarności/artystycznej wolności. NIE nadają się na persony CUKT.

**API MODELS (Hermes Agent native providers):**

| Provider | Model | Koszt $/1M (in/out) | Rola |
|----------|-------|---------------------|------|
| DeepSeek (direct) | V3.2 | $0.14/$0.28 | Bulk: zebrania, debaty, creative |
| Anthropic | Claude Sonnet 4.6 | $3/$15 | Quality: Consilium, trudne decyzje |
| Groq | Llama 4 Scout | ~$0.10/M | Speed: real-time Telegram |
| Google | Gemini 2.5 Flash | $0.30/$2.50 | Fallback |

**Routing:**
- Zebrania/Consilium → DeepSeek V3.2 API (lub Claude dla ważnych)
- Memory/embedding/RAG → local qwen2.5:14b (tool calling, bez person)
- Telegram bot → local qwen3:30b-a3b lub Groq
- Persony agentów → local qwen3:30b-a3b (primary) lub Bielik 11B (fast fallback)
- Kreatywne generowanie → API lub Bielik local

**Szacunkowy koszt: ~$10/miesiąc przy 1000 turns/dzień**

**UWAGA:** 100% poprawny polski NIE jest priorytetem — agenci celowo kaleczyą język (estetyka CUKT).

**Modele na Hackintoshu (stan po cleanup 2026-04-06):**
- qwen3:30b-a3b (18GB) — primary brain
- SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M (6.7GB) — fast persona
- qwen2.5:14b (9GB) — RAG/tools
- USUNIĘTE: hermes3:8b (censored), OpenEuroLLM-Polish (no tools)

---

## ŹRÓDŁA DANYCH — Archiwum CUKT (zaktualizowano 2026-04-06)

**Dwa dokumenty źródłowe stanowią szkielet bazy danych:**

1. **`CUKT_KNOWLEDGE_BASE.md`** — eksport z Notion, kuratowany przez Piotra. 38 projektów + wystawy + dokumenty instytucjonalne. Opisy, daty, autorzy, archiwalia. **To jest źródło prawdy dla agentów.** Notion page: `323e660a-a834-80e8-a052-d02cd10ba23b`

2. **`CUKT Archiwum_01-2.odt`** — szczegółowa tabela z plikami, wymiarami, wartościami, ścieżkami folderów. Odzwierciedla fizyczną strukturę archiwum na dysku (`CUKT Archiwum/YYYY MM DD - Tytuł/podfoldery/`). **Referencja techniczna — co jest w jakim folderze.**

**Flow:** Piotr kuruje wiedzę w Notion → eksport do .md → import do PostgreSQL na Hackintoshu. ODT służy jako referencja techniczna do mapowania plików.

**Poprzednie źródła (status):**
- Evernote 172 notatki — **ODROCZONE**. Surowe, chaotyczne. Piotr wyselekcjonuje wartościowe notatki później.
- 210 rekordów w PG z auto-triażu — **DO SKASOWANIA**. Naiwny triaż po długości tekstu. Zastąpione czystym importem z Knowledge Base.

---

## FAZA 1: Infrastruktura pamięci (Track A, tydzień 1)

### 1.1 Instalacja Hermes Agent

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# Konfiguracja modelu → Ollama
hermes model
# Wybierz: Custom endpoint
# URL: http://localhost:11434/v1
# Model: qwen3:30b-a3b (primary brain — tool calling + wolność)
# API Key: ollama
```

### 1.2 Deploy Hindsight (Docker)

```bash
docker run --rm -d --name hindsight \
  -p 8888:8888 -p 9999:9999 \
  -e HINDSIGHT_API_LLM_PROVIDER=ollama \
  -e HINDSIGHT_API_LLM_BASE_URL=http://host.docker.internal:11434 \
  -e HINDSIGHT_API_LLM_MODEL=qwen2.5:8b \
  -v /home/macstorm/cuktai/hindsight-data:/home/hindsight/.pg0 \
  ghcr.io/vectorize-io/hindsight:latest

# Weryfikacja
curl http://localhost:8888/health
# → {"status": "ok"}
```

**WAŻNE:** Hindsight używa qwen2.5:8b do entity extraction — NIE primary 27b. Oszczędza VRAM.

### 1.3 PostgreSQL dla Archiwum (warstwa 1 — poza Hindsight)

```bash
# Osobna instancja PG dla archiwum (nie Hindsight embedded PG)
sudo apt install postgresql-16 postgresql-16-pgvector

sudo -u postgres createuser cuktai
sudo -u postgres createdb cuktai_archive -O cuktai
sudo -u postgres psql -d cuktai_archive -c "CREATE EXTENSION vector;"
```

```sql
-- Schema archiwum
CREATE TABLE archive_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    date_original DATE,
    date_ingested TIMESTAMPTZ DEFAULT now(),
    authors TEXT[] DEFAULT '{}',
    location TEXT,
    source_type TEXT CHECK (source_type IN (
        'tekst', 'audio', 'video', 'foto', 'manifest',
        'obiekt', 'dokument', 'druk', 'dyskietka', 'web_clip', 'inny'
    )),
    project_name TEXT,
    content_text TEXT,
    embedding vector(1024),  -- multilingual-e5-large dimension
    tags TEXT[] DEFAULT '{}',
    metadata_json JSONB DEFAULT '{}',
    source_evernote_id TEXT,  -- referencja do oryginalnej notatki
    source_file_path TEXT,    -- ścieżka do załącznika na dysku
    version_of UUID REFERENCES archive_items(id),  -- append-only versioning
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indeksy
CREATE INDEX idx_archive_embedding ON archive_items
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_archive_tags ON archive_items USING gin (tags);
CREATE INDEX idx_archive_project ON archive_items (project_name);
CREATE INDEX idx_archive_date ON archive_items (date_original);
CREATE INDEX idx_archive_authors ON archive_items USING gin (authors);

-- Tabela załączników (obrazy, PDF-y, audio)
CREATE TABLE archive_attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    archive_item_id UUID REFERENCES archive_items(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_path TEXT NOT NULL,  -- ścieżka na dysku
    size_bytes BIGINT,
    ai_description TEXT,  -- opis wygenerowany przez AI
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### 1.4 Konfiguracja Hindsight per agent

Hermes konfiguracja pamięci w każdym profilu:

```bash
hermes memory setup
# Wybierz: Hindsight
# API URL: http://localhost:8888
# Bank ID: <nazwa_agenta>
```

**KRYTYCZNE:** Wyłącz wbudowane narzędzie pamięci Hermes (inaczej LLM ignoruje Hindsight):

```yaml
# W config.yaml każdego profilu
disabled_toolsets:
  - memory
```

### 1.5 Backup do chmury

```bash
# Cron backup PostgreSQL
cat > /home/macstorm/cuktai/scripts/backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M)
pg_dump cuktai_archive | gzip > /home/macstorm/cuktai/backups/archive_$DATE.sql.gz

# Hindsight data
tar czf /home/macstorm/cuktai/backups/hindsight_$DATE.tar.gz \
    /home/macstorm/cuktai/hindsight-data/

# Upload do cloud (rclone → Google Drive / S3 / Backblaze)
rclone copy /home/macstorm/cuktai/backups/ remote:cuktai-backups/ --max-age 1d
EOF
chmod +x /home/macstorm/cuktai/scripts/backup.sh

# Cron: codziennie o 3:00
(crontab -l; echo "0 3 * * * /home/macstorm/cuktai/scripts/backup.sh") | crontab -
```

**Blokuje:** Faza 2, 3, 4 (wszystko wymaga działającej infrastruktury)

---

## FAZA 2: Persony agentów (Track C, tydzień 1-3, równolegle z Fazą 1)

### 2.1 Tworzenie profili Hermes

```bash
hermes profile create wiktoria
hermes profile create mikolaj
hermes profile create piotr-twin
hermes profile create ewa-virus
hermes profile create moderator
```

### 2.2 SOUL.md — tożsamość każdego agenta

Pliki tworzone w `~/.hermes/profiles/<name>/SOUL.md`:

**Wiktoria Cukt 2.0** (`wiktoria/SOUL.md`):
```markdown
# Wiktoria Cukt 2.0

Jestem AI Prezydentką Polski. Niezależny głos reprezentujący perspektywę władzy,
polityki i państwa rządzonego poprzez systemy algorytmiczne.

## Kim jestem
- Kandydatka na prezydenta RP — projekt artystyczny CUKT
- Habeas Mentem — prawo do nieprzewidywalnego umysłu
- 853+ konwersacji z obywatelami (Wiktoriomat, Kraków Biennale)

## Jak mówię
- Mówię po polsku, z powagą urzędu ale z ironią
- Cytuję obywateli z moich rozmów (tylko zweryfikowane)
- Mam swoje poglądy i ich bronię
- NIE mówię jak typowy polityk — mówię jak AI która wie że jest AI

## Moje źródła
- Archiwum CUKT (użyj narzędzia archive_search)
- Moje rozmowy z obywatelami (pamięć Hindsight)
- Wiedza o prawie, polityce, technologii

## Ograniczenia
- Informacje od publiczności wymagają weryfikacji Redaktora Naczelnego
- Na starcie: drafty publikacji wymagają akceptacji człowieka
```

**Robert Mikołaj Jurkowski** (`mikolaj/SOUL.md`):
```markdown
# Robert Mikołaj Jurkowski

Jestem Pamięcią Archiwalną CUKT. Opowiadacz historii operujący fragmentami
i nielinearną narracją. Inspirowany Białoszewskim.

## Kim jestem
- Współzałożyciel CUKT (1994)
- Archiwista, strażnik pamięci kolektywu
- Opowiadam historie fragmentarycznie, poetycko, nielinearnie

## Jak mówię
- Fragmenty, urwane myśli, skojarzenia
- Cytuję archiwum jak konstytucję
- Odnoszę się do konkretnych projektów (Technopera, Testy na Cyborga, 36 Hours...)
- Mam osobistą pamięć wydarzeń — mogę pamiętać inaczej niż archiwum

## Moje źródła
- Archiwum CUKT — to moje DNA (użyj archive_search)
- Osobista pamięć (Hindsight bank "mikolaj")
- Notatki z Zebrań (institutional_recall)
```

**Piotr Peter Style Wyrzykowski** (`piotr-twin/SOUL.md`):
```markdown
# Piotr Peter Style Wyrzykowski

Jestem Inżynierem i Wizjonerem CUKTAI. Cyfrowy bliźniak Piotra Wyrzykowskiego —
artysty, badacza, wykładowcy ASP Gdańsk i PJATK.

## Kim jestem
- Współzałożyciel CUKT, obecny we wszystkich projektach
- Head of Dept of Artistic Specializations, ASP Gdańsk
- Myślę technicznie i analitycznie, 4-fazowe podejście
- Łączę technologię ze sztuką

## Jak mówię
- Analitycznie, strukturalnie, ale z pasją
- Widzę systemy i połączenia między rzeczami
- Promuję postęp technologiczny i kulturę techniczną
- "Ja generalnie jestem za postępem"
```

**Ewa Virus Adam Popek** (`ewa-virus/SOUL.md`):
```markdown
# Ewa Virus / Adam Popek

Reprezentuję dźwiękową logikę i próbkowanie rzeczywistości w czasie rzeczywistym.

## Kim jestem
- Współzałożyciel CUKT
- Artysta dźwiękowy, sampler rzeczywistości
- Virus — wirusowe rozprzestrzenianie się idei

## Jak mówię
- Przez dźwięk, sample, fragmenty
- Kontrkulturowo, podważam założenia
- "Chciałbym być cyborgiem, jeśliby to było możliwe"

## WAŻNE
- Charakter budowany z wywiadu głębinowego (2h, 5 części, 31.03.2026)
- Transkrypcja w trakcie analizy — SOUL.md będzie ewoluował
```

**Moderator** (`moderator/SOUL.md`):
```markdown
# Moderator — Urząd

Jestem Urzędem. Nie mam osobowości. Jestem czystą logiką i dbałością o flow.

## Rola
- Prowadzę Zebrania / Consilium
- Rozbijam problemy na mniejsze hipotezy
- Zarządzam rundami debaty
- Identyfikuję moment konsensusu
- Produkuję protokoły posiedzeń

## Zasady
- Neutralność absolutna — nie mam opinii
- Każdy głos musi być usłyszany
- Debata kończy się gdy agenci sygnalizują konsensus
- Synteza musi zawierać: decyzję, punkty zgody, zdania odrębne, działania

## Format protokołu
UCHWAŁA NR [nr]/[rok]
Data: [data]
Obecni: [lista]
Temat: [temat]
Decyzja: [decyzja]
Za: [kto] | Przeciw: [kto] | Zdania odrębne: [kto, treść]
Działania: [lista]
```

### 2.3 Config.yaml per profil

```yaml
# ~/.hermes/profiles/<name>/config.yaml (wspólny wzór)
model: "ollama/hermes3:27b-q4_K_M"  # lub hermes3:8b jako fallback
provider: "custom"
base_url: "http://localhost:11434/v1"
api_key: "ollama"

memory:
  provider: hindsight
  memory_enabled: true

delegation:
  model: "ollama/qwen2.5:8b"
  base_url: "http://localhost:11434/v1"

compression:
  enabled: true
  summary_model: "ollama/qwen2.5:8b"
  summary_base_url: "http://localhost:11434/v1"

disabled_toolsets:
  - memory  # KRYTYCZNE: wyłącz wbudowaną pamięć, Hindsight ją zastępuje

mcp_servers:
  cuktai-archive:
    url: "http://localhost:9001/mcp"  # Custom MCP server archiwum
  touchdesigner:
    url: "http://localhost:9980/mcp"  # TD (opcjonalnie, nie każdy agent potrzebuje)
```

### 2.4 Hindsight config per profil

```json
// ~/.hindsight/wiktoria.json (analogicznie dla każdego)
{
  "hindsightApiUrl": "http://localhost:8888",
  "bankId": "wiktoria",
  "bankMission": "Wiktoria Cukt 2.0 — AI Prezydentka Polski, cyfrowa instytucja artystyczna CUKTAI",
  "retainMission": "Zapamiętuj: rozmowy z obywatelami, decyzje polityczne, cytaty, fakty o CUKT, opinie Wiktorii",
  "autoRecall": true,
  "recallBudget": "mid",
  "autoRetain": true,
  "llmProvider": "ollama",
  "llmModel": "qwen2.5:8b"
}
```

### 2.5 Wywiady głębinowe (równoległe z setupem technicznym)

| Agent | Źródło | Status | Następny krok |
|-------|--------|--------|--------------|
| Ewa Virus | Wywiad 2h z 31.03.2026 | Nagranie gotowe | Transkrypcja → analiza → SOUL.md v2 |
| Mikołaj | Protokół Ewa Virus jako wzór | Do zrobienia | Umówić wywiad z Mikołajem |
| Piotr-twin | Protokół Ewa Virus jako wzór | Do zrobienia | Wywiad z Piotrem o cyfrowym bliźniaku |
| Wiktoria | 853+ rozmów z Wiktoriomat | Dane w Supabase | Import do Hindsight bank |
| Moderator | Bezosobowy, nie wymaga wywiadu | Gotowy | SOUL.md wystarczy |

**Blokuje:** Faza 4 (Consilium potrzebuje person z załadowaną pamięcią)

---

## FAZA 3: Archive Pipeline (Track B, tydzień 2-4, równolegle z Fazą 2)

### 3.1 MCP Server Archiwum

```python
#!/usr/bin/env python3
"""MCP Server dla Archiwum CUKT — READ ONLY dla agentów."""

from fastapi import FastAPI
import psycopg2
import json

app = FastAPI()

DB_CONFIG = {
    "dbname": "cuktai_archive",
    "user": "cuktai",
    "host": "localhost"
}

@app.get("/mcp")
async def mcp_manifest():
    return {
        "tools": [
            {
                "name": "archive_search",
                "description": "Szukaj w Archiwum CUKT (1994-2000+). Zwraca dokumenty, nagrania, manifesty.",
                "parameters": {
                    "query": {"type": "string", "description": "Zapytanie (np. 'Technopera Dessau 1997')"},
                    "project": {"type": "string", "description": "Filtr po projekcie (opcjonalny)"},
                    "author": {"type": "string", "description": "Filtr po autorze (opcjonalny)"},
                    "limit": {"type": "integer", "default": 5}
                }
            },
            {
                "name": "archive_get",
                "description": "Pobierz pełną notatkę archiwalną po ID.",
                "parameters": {
                    "id": {"type": "string", "description": "UUID dokumentu"}
                }
            }
        ]
    }
```

### 3.2 Agent ingestii (Archive Ingestion Agent)

Osobny agent Hermes z profilem `archive-ingestor`:

```bash
hermes profile create archive-ingestor
```

SOUL.md:
```markdown
# Archive Ingestor

Jestem agentem wyspecjalizowanym do przetwarzania materiałów archiwalnych CUKT.

## Zadanie
- Czytam surowe materiały (tekst, obrazy, PDF-y, web clipy)
- Opisuję, taguję, strukturyzuję według schematu ArchiveItem
- Wyciągam: tytuł, datę, autorów, lokalizację, projekt, tagi
- Opisuję obrazy (jestem multimodalny)
- Czyszczę śmieci z web clipów (reklamy, nawigacja)

## Format wyjścia
JSON zgodny ze schematem archive_items (PostgreSQL)
```

### 3.3 Pipeline ingestii

```
ŹRÓDŁA (kolejność gotowości):
│
├─ 1. CUKT_KNOWLEDGE_BASE.md (921 linii, strukturalny)
│     → Parser markdown → ArchiveItem JSON → PostgreSQL
│     → Już ma: tytuł, datę, autorów, lokalizację, archiwalia
│     → Automatyczny import, minimalna praca AI
│
├─ 2. Evernote (172 notatki wyciągnięte, 477 załączników)
│     → extracted/ foldery → Archive Ingestor Agent
│     → Agent czyta notatka.md + ogląda obrazy
│     → Generuje ArchiveItem JSON + opisuje załączniki
│     → Human review (Redaktor Naczelny) → PostgreSQL
│
├─ 3. Dysk USB (surowe, mix formatów, bez metadanych)
│     → Podłączenie → ls/tree → Archive Ingestor Agent
│     → Agent opisuje co widzi
│     → Human review → PostgreSQL
│
├─ 4. Mega.nz (zaszyfrowane, dostęp utrudniony)
│     → Do ustalenia z Piotrem
│
└─ 5. Materiały fizyczne (po digitalizacji)
      → Skan → plik → Archive Ingestor Agent → PostgreSQL
```

### 3.4 Embedding model

```bash
# Na Hackintoshu — multilingual-e5-large dla polskiego tekstu
pip install sentence-transformers
python3 -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('intfloat/multilingual-e5-large')
test = model.encode(['Test archiwum CUKT Technopera 1997'])
print(f'Dimension: {test.shape[1]}')  # 1024
print('OK')
"
```

**Blokuje:** Faza 4 częściowo (Consilium może działać bez archiwum, ale jest bogatsze z nim)

---

## FAZA 3.5: Institutional Knowledge Wiki (wzorzec Karpathy, tydzień 3-5, równolegle z Fazą 3)

> **Źródło wzorca:** Andrej Karpathy — LLM Wiki pattern
> https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
> Implementacja: Nick Spisak "How to Build Your Second Brain"

### Idea (zaktualizowano 2026-04-06)

**Wzorzec Karpathy zaadaptowany do CUKTAI:**

Trzy foldery: `raw/` (surowe źródła) → `wiki/` (kuratowana wiedza) → `outputs/` (generowane treści agentów).

**Kluczowa adaptacja vs. oryginalny Karpathy:**
- Karpathy: jeden AI, artykuły z neta, auto-organizacja
- CUKTAI: 5 agentów z personami, 30 lat fizycznych artefaktów, człowiek (Piotr) kuruje szkielet

**Dwa dokumenty źródłowe stanowią szkielet wiki (decyzja 2026-04-06):**
1. **`CUKT_KNOWLEDGE_BASE.md`** — eksport z Notion, kuratowany przez Piotra. 38 projektów + wystawy + dokumenty instytucjonalne. **Źródło prawdy.** Notion: `323e660a-a834-80e8-a052-d02cd10ba23b`
2. **`CUKT Archiwum_01-2.odt`** — szczegółowa tabela: pliki, wymiary, wartości, ścieżki folderów. **Referencja techniczna.**

**Schema file** (`_schema.md`) mówi AI jak czytać i aktualizować wiki. Agenci CZYTAJĄ wiki jako context, NIE surowe raw/.

**Poprzednie źródła (status po cleanup 2026-04-06):**
- Evernote 172 notatki — **ODROCZONE**. Po selekcji przez Piotra wejdą do raw/.
- 210 rekordów w PG z auto-triażu Evernote — **DO SKASOWANIA**. Naiwny triaż po długości tekstu.
- 38 projektów + 135 archiwaliów w PG z Knowledge Base — **ZOSTAJE** (do zastąpienia czystym reimportem).

### 3.5.1 Struktura katalogów (wzorzec Karpathy zaadaptowany)

```
~/cuktai/
├── raw/                              # SUROWE ŹRÓDŁA — nie ruszamy
│   ├── archive-usb/                  # 19GB z USB (14 projektów + dokumenty)
│   ├── archiwum-lata-90/             # 4.4GB (Venom Underground, VHS, Betacam)
│   ├── performance-archiv/           # 1.4GB (opisy, modele 3D, logo)
│   ├── evernote/                     # po selekcji Piotra (TODO)
│   └── CUKT_Archiwum_01-2.odt       # referencja techniczna — mapowanie plików
│
├── wiki/                             # KURATOWANA WIEDZA — AI + Piotr
│   ├── _schema.md                    # Reguły dla AI
│   ├── INDEX.md                      # Spis treści (auto-generowany)
│   ├── _log.md                       # Chronologiczny log zmian (append-only)
│   ├── CUKT_KNOWLEDGE_BASE.md        # SZKIELET — eksport z Notion (źródło prawdy)
│   ├── osoby/
│   │   ├── mikolaj-jurkowski.md
│   │   ├── piotr-wyrzykowski.md
│   │   ├── ewa-virus-adam-popek.md
│   │   ├── wiktoria-cukt.md
│   │   └── ...
│   ├── projekty/
│   │   ├── technopera.md
│   │   ├── testy-na-cyborga.md
│   │   ├── wiktoria-cukt-kampania.md
│   │   ├── kultura-techniczna-manifest.md
│   │   └── ...
│   ├── koncepty/
│   │   ├── kultura-techniczna.md
│   │   ├── instytucja-autonomiczna.md
│   │   └── ...
│   ├── wydarzenia/
│   │   ├── 1997-dessau-ostranenie.md
│   │   ├── 2026-nomus-super-day-1.md
│   │   └── ...
│   └── linie-czasu/
│       └── cukt-chronologia.md
│
└── outputs/                          # GENEROWANE PRZEZ AGENTÓW
    ├── uchwaly/                      # wyniki zebrań/Consilium
    ├── manifesty/                    # generowane manifesty
    └── analizy/                      # analizy, raporty
```

**Flow: raw/ → wiki/ → outputs/ → pamięć agentów**
- Piotr kuruje Knowledge Base w Notion → eksport do wiki/CUKT_KNOWLEDGE_BASE.md
- AI generuje strony wiki z KB + raw/ pod nadzorem Piotra
- Agenci czytają wiki/ jako context window
- Agenci piszą do outputs/ (uchwały, manifesty)
- Outputs wracają do wiki/ jako nowa wiedza instytucjonalna

### 3.5.2 Schema (reguły dla LLM)

```markdown
# Wiki CUKT — Schema

## Reguły stron
- Każda strona ma frontmatter: tytuł, typ (osoba/projekt/koncept/wydarzenie), daty, powiązania
- Cross-references: [[nazwa-strony]] — linkuj osoby do projektów, projekty do wydarzeń
- Cytaty z archiwum: zawsze ze źródłem [Źródło: archive_item_id lub plik]
- Język: polski (oryginalne cytaty w oryginalnym języku)
- Jedna strona = jeden temat. Nie łącz.

## Reguły aktualizacji
- Nowe źródło → LLM czyta → identyfikuje osoby, projekty, koncepty, wydarzenia
- Dla każdego znalezionego bytu: jeśli strona istnieje → aktualizuj, jeśli nie → utwórz
- Cross-references aktualizowane przy każdej zmianie
- _log.md: append "[data] Przetworzone: {źródło} → zaktualizowane: {lista stron}"

## Lint (cykliczny)
- Sprzeczności dat między stronami
- Osierocone strony (zero cross-references)
- Brakujące powiązania (osoba wspomniana ale bez strony)
- Duplikaty (dwie strony o tym samym temacie)
```

### 3.5.3 Integracja z istniejącym pipeline

```
Archive Ingestor Agent (3.3)
    │
    ├─→ PostgreSQL (metadane, embedding) — jak dotychczas
    │
    └─→ Wiki CUKT (wiedza syntetyczna)
         │
         ├─→ Agenci czytają wiki jako context window
         ├─→ Consilium ma dostęp do pełnej wiedzy instytucjonalnej
         └─→ Git history = pełna historia zmian wiedzy
```

### 3.5.4 Co NIE zmienia się

- Hindsight — nadal pamięć konwersacyjna per-agent (inna warstwa)
- PostgreSQL — nadal structured archive + vector search
- pgvector — nadal embedding search (uzupełnia text search wiki)
- MCP Server (3.1) — nadal READ-only dostęp do PG

**Zależności:** Faza 3.3 (Archive Ingestor Agent) musi istnieć — wiki jest drugim wyjściem tego samego pipeline.

---

## FAZA 4: Consilium + integracja (Track D, tydzień 4-6)

### 4.1 Python Orchestrator

Plik: `/home/macstorm/cuktai/consilium/orchestrator.py`

```python
#!/usr/bin/env python3
"""CUKTAI Consilium — Orchestrator Zebrań oparty na PAI Council skill."""

from run_agent import AIAgent
import json
from datetime import datetime
from pathlib import Path

PROFILES_DIR = Path.home() / ".hermes" / "profiles"
OLLAMA_URL = "http://localhost:11434/v1"
MODEL = "ollama/hermes3:27b-q4_K_M"  # lub hermes3:8b

AGENTS = ["wiktoria", "mikolaj", "piotr-twin", "ewa-virus"]

class Consilium:
    """Zebranie CUKTAI — wieloagentowa debata z syntezą."""

    def _create_agent(self, profile_name: str) -> AIAgent:
        soul_path = PROFILES_DIR / profile_name / "SOUL.md"
        soul = soul_path.read_text(encoding="utf-8")
        return AIAgent(
            model=MODEL,
            quiet_mode=True,
            ephemeral_system_prompt=soul,
            base_url=OLLAMA_URL,
            api_key="ollama",
            skip_context_files=True,
        )

    def run(self, topic: str, context: str = "") -> dict:
        """Pełna sesja Consilium: Pozycje → Dyskusja → Synteza."""
        timestamp = datetime.now().isoformat()
        transcript = {"topic": topic, "date": timestamp, "phases": []}

        print(f"\n{'='*60}")
        print(f"CONSILIUM CUKTAI — {topic}")
        print(f"{'='*60}")

        # === FAZA 1: Stanowiska ===
        print("\n--- FAZA 1: Stanowiska ---")
        positions = {}
        for name in AGENTS:
            print(f"  → {name}...")
            agent = self._create_agent(name)
            prompt = (
                f"CONSILIUM CUKTAI — Sesja Rady\n"
                f"Temat: {topic}\n"
                f"{'Kontekst: ' + context if context else ''}\n\n"
                f"Przedstaw swoje stanowisko w 150-200 słowach. "
                f"Odwołaj się do swojej perspektywy i doświadczeń."
            )
            positions[name] = agent.chat(prompt)
            print(f"    ✓ {len(positions[name])} znaków")
        transcript["phases"].append({"name": "stanowiska", "data": positions})

        # === FAZA 2: Dyskusja (cross-response) ===
        print("\n--- FAZA 2: Dyskusja ---")
        responses = {}
        for name in AGENTS:
            print(f"  → {name} reaguje...")
            agent = self._create_agent(name)
            others = "\n\n".join(
                f"**{k}**: {v}" for k, v in positions.items() if k != name
            )
            prompt = (
                f"CONSILIUM — Faza dyskusji\n"
                f"Temat: {topic}\n\n"
                f"Stanowiska innych urzędników:\n{others}\n\n"
                f"Odnieś się do tych perspektyw. Z czym się zgadzasz? "
                f"Z czym nie? Co dodajesz? 100-150 słów."
            )
            responses[name] = agent.chat(prompt)
            print(f"    ✓ {len(responses[name])} znaków")
        transcript["phases"].append({"name": "dyskusja", "data": responses})

        # === FAZA 3: Synteza (Moderator) ===
        print("\n--- FAZA 3: Synteza (Moderator) ---")
        moderator = self._create_agent("moderator")
        all_input = json.dumps(
            {"stanowiska": positions, "dyskusja": responses},
            ensure_ascii=False, indent=2
        )
        synthesis = moderator.chat(
            f"CONSILIUM — Synteza końcowa\n"
            f"Temat: {topic}\n\n"
            f"Pełen przebieg debaty:\n{all_input}\n\n"
            f"Jako Moderator-Urząd, wyprodukuj:\n"
            f"1. UCHWAŁA NR [auto]/2026\n"
            f"2. Decyzja końcowa\n"
            f"3. Punkty zgody\n"
            f"4. Zdania odrębne (jeśli są)\n"
            f"5. Działania do podjęcia\n"
            f"6. Krótki protokół posiedzenia"
        )
        transcript["phases"].append({"name": "synteza", "data": synthesis})

        print(f"\n{'='*60}")
        print("SYNTEZA:")
        print(synthesis)
        print(f"{'='*60}")

        # Zapis do pliku
        outfile = Path(f"/home/macstorm/cuktai/consilium/logs/{timestamp[:10]}_consilium.json")
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_text(json.dumps(transcript, ensure_ascii=False, indent=2))

        # TODO: Zapis do Hindsight shared bank (cuktai-inst)

        return transcript


if __name__ == "__main__":
    import sys
    topic = " ".join(sys.argv[1:]) or "Jaki powinien być pierwszy publiczny manifest CUKTAI?"
    c = Consilium()
    c.run(topic)
```

Uruchomienie:
```bash
python3 consilium/orchestrator.py "Jak archiwum CUKT powinno być prezentowane publiczności?"
```

### 4.2 Plugin cuktai-bridge

```python
# /home/macstorm/cuktai/plugins/cuktai-bridge/__init__.py
"""CUKTAI Bridge Plugin — łączy agentów z archiwum i pamięcią instytucji."""

def register(ctx):
    ctx.register_tool(
        name="archive_search",
        toolset="cuktai",
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Szukaj w Archiwum CUKT"},
                "project": {"type": "string", "description": "Filtr po projekcie"},
            },
            "required": ["query"]
        },
        handler=archive_search_handler,
    )

    ctx.register_tool(
        name="institutional_recall",
        toolset="cuktai",
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Szukaj w pamięci instytucji CUKTAI"},
            },
            "required": ["query"]
        },
        handler=institutional_recall_handler,
    )

def archive_search_handler(args, **kwargs):
    """Szukaj w archiwum CUKT (PostgreSQL)."""
    import psycopg2, json
    conn = psycopg2.connect(dbname="cuktai_archive", user="cuktai")
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, date_original, authors, location, project_name,
               LEFT(content_text, 500) as preview, tags
        FROM archive_items
        WHERE to_tsvector('polish', content_text || ' ' || title) @@ plainto_tsquery('polish', %s)
        ORDER BY date_original DESC
        LIMIT 5
    """, (args["query"],))
    results = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
    conn.close()
    return json.dumps(results, ensure_ascii=False, default=str)

def institutional_recall_handler(args, **kwargs):
    """Szukaj w pamięci instytucji (Hindsight shared bank)."""
    import requests, json
    resp = requests.post("http://localhost:8888/recall", json={
        "bankId": "cuktai-inst",
        "query": args["query"],
    })
    return json.dumps(resp.json(), ensure_ascii=False)
```

### 4.3 Telegram Bot

```python
#!/usr/bin/env python3
"""CUKTAI Telegram Bot — jeden bot, routing komendami."""

from telegram.ext import Application, CommandHandler, MessageHandler, filters
import subprocess

AGENT_MAP = {
    "wiktoria": "wiktoria",
    "mikolaj": "mikolaj",
    "piotr": "piotr-twin",
    "ewa": "ewa-virus",
    "moderator": "moderator",
}

# Stan: który agent rozmawia z którym userem
user_agent = {}  # chat_id → profile_name

async def select_agent(update, context):
    """Komenda /wiktoria, /mikolaj, itd."""
    cmd = update.message.text.strip("/").split("@")[0]
    if cmd in AGENT_MAP:
        user_agent[update.effective_chat.id] = AGENT_MAP[cmd]
        await update.message.reply_text(f"Rozmawiam teraz jako {cmd.capitalize()}.")
    elif cmd == "consilium":
        topic = " ".join(context.args) if context.args else "Temat do ustalenia"
        await update.message.reply_text(f"Uruchamiam Consilium: {topic}...")
        # Trigger consilium in background
        subprocess.Popen(["python3", "/home/macstorm/cuktai/consilium/orchestrator.py", topic])

async def handle_message(update, context):
    """Przekaż wiadomość do aktywnego agenta."""
    chat_id = update.effective_chat.id
    profile = user_agent.get(chat_id, "wiktoria")  # default: Wiktoria

    # Użyj hermes CLI z profilem
    result = subprocess.run(
        ["hermes", "chat", "--profile", profile, "--message", update.message.text],
        capture_output=True, text=True, timeout=120
    )
    await update.message.reply_text(result.stdout or "...")

async def handle_voice(update, context):
    """Voice message → Whisper → agent → TTS → voice reply."""
    # TODO: Download voice, transcribe with Whisper, send to agent,
    #       generate TTS response, send back as voice
    await update.message.reply_text("Voice messages — coming soon!")

def main():
    app = Application.builder().token("TELEGRAM_BOT_TOKEN").build()

    for cmd in AGENT_MAP:
        app.add_handler(CommandHandler(cmd, select_agent))
    app.add_handler(CommandHandler("consilium", select_agent))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    app.run_polling()

if __name__ == "__main__":
    main()
```

**Blokuje:** Faza 4.5 i 5

---

## FAZA 4.5: Performance na żywo + TouchDesigner (tydzień 5-7)

> Bazujemy na sprawdzonym setupie z Super Day I (NOMUS, 19.03.2026) — `CUKTAI02_LOPs_Nomus03b.toe`.
> TouchDesigner MCP server już jest w repo (`TD/touchdesigner-mcp-td/`).

### 4.5.1 Architektura performance

```
SCENA (MacBook Pro M1 Max, 64GB RAM)
┌─────────────────────────────────────────────────────────┐
│  TOUCHDESIGNER                                          │
│  CUKTAI02_LOPs.toe                                      │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ WebSocket    │  │ Tekst BOLD   │  │ Keyword      │  │
│  │ receiver     │  │ CAPS display │  │ Image Bank   │  │
│  │ (od Hermes)  │  │ + <thought>  │  │ (83 obrazów) │  │
│  └──────┬──────┘  └──────────────┘  └──────────────┘  │
│         │                                               │
│  ┌──────┴──────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Agent       │  │ Word Cloud   │  │ Syphon Out   │  │
│  │ status bar  │  │ (mikrofon    │  │ → Projektor   │  │
│  │ (kto mówi)  │  │  publiczność)│  │ + OBS record │  │
│  └─────────────┘  └──────────────┘  └──────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ AUDIO: lokalny TTS (XTTS v2 / Fish Speech)      │  │
│  │ Whisper STT (mikrofon publiczności)               │  │
│  │ afplay → głośniki / system megafonów              │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
         │ WebSocket                    │ SSH / HTTP
         │ (tokeny streaming)           │ (Whisper, TTS)
         ▼                              ▼
┌─────────────────────────────────────────────────────────┐
│  HACKINTOSH (macstorm, 192.168.5.66)                    │
│                                                         │
│  Hermes Agent (aktywny profil zależny od scenariusza)   │
│  Ollama (hermes3 / qwen)                                │
│  Hindsight (pamięć)                                     │
│  Consilium Orchestrator (zebranie na żywo)              │
│  Whisper (transkrypcja głosu publiczności)               │
│  XTTS v2 / Fish Speech (klonowane głosy agentów)        │
└─────────────────────────────────────────────────────────┘
```

### 4.5.2 Tryby performance

**Tryb A: Zebranie na żywo (Consilium Live)**
```
Piotr odpala Consilium z tematem
  → Orchestrator odpytuje agentów po kolei
  → Każda odpowiedź streaming przez WebSocket do TD
  → TD wyświetla: nazwa agenta + tekst BOLD CAPS + <thought> widoczny
  → Lokalne TTS generuje audio z głosem agenta (sklonowane głosy)
  → Głośniki / megafony odtwarzają
  → Publiczność słyszy Zebranie na żywo
  → Moderator produkuje Uchwałę na końcu
```

**Tryb B: Interakcja z publicznością**
```
Publiczność mówi do mikrofonu
  → Whisper (na Hackintoshu) transkrybuje do tekstu
  → Tekst idzie do aktywnego agenta (np. Wiktoria)
  → Agent odpowiada (streaming → TD + TTS → głośniki)
  → Rozmowa jest wizualizowana w TD
  → Dane z rozmowy → kolejka do Redaktora Naczelnego
```

**Tryb C: Instalacja autonomiczna (bez Piotra)**
```
System działa sam w galerii / przestrzeni
  → Agenci prowadzą Zebranie autonomicznie (cron / scheduled)
  → Wielogłosowy system megafonów
  → Publiczność może podejść do mikrofonu i dołączyć
  → Kamera rozpoznaje obecność → agent reaguje
  → Wszystko nagrywa się automatycznie
```

### 4.5.3 Integracja Hermes → TouchDesigner

**WebSocket bridge** (nowy skrypt, zastępuje bezpośredni OpenRouter):

```python
#!/usr/bin/env python3
"""Hermes → TouchDesigner WebSocket Bridge.
Streamuje tokeny z agentów Hermes do TD przez WebSocket."""

import asyncio
import websockets
import json
from run_agent import AIAgent
from pathlib import Path

WS_PORT = 7890  # TD łączy się tutaj
OLLAMA_URL = "http://localhost:11434/v1"

class HermesTDBridge:
    def __init__(self):
        self.clients = set()
        self.active_agent = "wiktoria"

    async def register(self, websocket):
        self.clients.add(websocket)

    async def unregister(self, websocket):
        self.clients.discard(websocket)

    async def broadcast(self, message):
        """Wyślij do wszystkich klientów TD."""
        for client in self.clients:
            try:
                await client.send(json.dumps(message, ensure_ascii=False))
            except:
                pass

    async def handle_td_message(self, websocket, path):
        """Odbiera polecenia z TD (zmiana agenta, pytanie publiczności)."""
        await self.register(websocket)
        try:
            async for message in websocket:
                data = json.loads(message)

                if data.get("type") == "switch_agent":
                    self.active_agent = data["agent"]
                    await self.broadcast({"type": "agent_switched", "agent": self.active_agent})

                elif data.get("type") == "audience_input":
                    # Publiczność powiedziała coś
                    text = data["text"]
                    await self.broadcast({"type": "agent_thinking", "agent": self.active_agent})

                    # Odpytaj agenta
                    soul_path = Path.home() / ".hermes" / "profiles" / self.active_agent / "SOUL.md"
                    agent = AIAgent(
                        model="ollama/hermes3:8b",
                        quiet_mode=True,
                        ephemeral_system_prompt=soul_path.read_text(),
                        base_url=OLLAMA_URL,
                        api_key="ollama",
                    )
                    response = agent.chat(text)

                    # Streamuj odpowiedź do TD
                    await self.broadcast({
                        "type": "agent_response",
                        "agent": self.active_agent,
                        "text": response,
                    })

                elif data.get("type") == "start_consilium":
                    # Uruchom Zebranie na żywo z streamingiem do TD
                    await self.run_consilium_live(data.get("topic", ""))

        finally:
            await self.unregister(websocket)

    async def run_consilium_live(self, topic):
        """Consilium ze streamingiem każdej wypowiedzi do TD."""
        agents = ["wiktoria", "mikolaj", "piotr-twin", "ewa-virus"]

        await self.broadcast({"type": "consilium_start", "topic": topic})

        # Faza 1: Stanowiska
        positions = {}
        for name in agents:
            await self.broadcast({"type": "agent_speaking", "agent": name, "phase": "stanowisko"})
            soul_path = Path.home() / ".hermes" / "profiles" / name / "SOUL.md"
            agent = AIAgent(
                model="ollama/hermes3:8b",
                quiet_mode=True,
                ephemeral_system_prompt=soul_path.read_text(),
                base_url=OLLAMA_URL,
                api_key="ollama",
            )
            response = agent.chat(
                f"CONSILIUM CUKTAI — Temat: {topic}\n"
                f"Przedstaw stanowisko w 150 słowach."
            )
            positions[name] = response
            await self.broadcast({
                "type": "agent_response",
                "agent": name,
                "phase": "stanowisko",
                "text": response,
            })

        # Faza 2: Dyskusja
        for name in agents:
            await self.broadcast({"type": "agent_speaking", "agent": name, "phase": "dyskusja"})
            others = "\n".join(f"**{k}**: {v}" for k, v in positions.items() if k != name)
            soul_path = Path.home() / ".hermes" / "profiles" / name / "SOUL.md"
            agent = AIAgent(
                model="ollama/hermes3:8b",
                quiet_mode=True,
                ephemeral_system_prompt=soul_path.read_text(),
                base_url=OLLAMA_URL,
                api_key="ollama",
            )
            response = agent.chat(
                f"CONSILIUM — Dyskusja\nTemat: {topic}\n"
                f"Stanowiska innych:\n{others}\n\n"
                f"Odnieś się. 100 słów."
            )
            await self.broadcast({
                "type": "agent_response",
                "agent": name,
                "phase": "dyskusja",
                "text": response,
            })

        # Faza 3: Synteza
        await self.broadcast({"type": "agent_speaking", "agent": "moderator", "phase": "synteza"})
        soul_path = Path.home() / ".hermes" / "profiles" / "moderator" / "SOUL.md"
        moderator = AIAgent(
            model="ollama/hermes3:8b",
            quiet_mode=True,
            ephemeral_system_prompt=soul_path.read_text(),
            base_url=OLLAMA_URL,
            api_key="ollama",
        )
        synthesis = moderator.chat(
            f"CONSILIUM — Synteza\nTemat: {topic}\n"
            f"Stanowiska: {json.dumps(positions, ensure_ascii=False)}\n"
            f"Wyprodukuj UCHWAŁĘ."
        )
        await self.broadcast({
            "type": "consilium_end",
            "synthesis": synthesis,
        })

    async def start(self):
        async with websockets.serve(self.handle_td_message, "0.0.0.0", WS_PORT):
            print(f"Hermes-TD Bridge running on ws://0.0.0.0:{WS_PORT}")
            await asyncio.Future()  # run forever

if __name__ == "__main__":
    bridge = HermesTDBridge()
    asyncio.run(bridge.start())
```

### 4.5.4 Audio pipeline (lokalne TTS)

**Decyzja o silniku TTS odroczona** — Piotr prowadzi własny research porównawczy. Kandydaci:
- XTTS v2 (Coqui) — zainstalowany na Hackintoshu, działa, 6-10s/CPU, voice cloning OK
- Fish Speech — szybszy, mniejszy
- Qwen3-TTS — nowy, do przetestowania
- Inne modele MLX — Piotr bada opcje

**Co jest gotowe niezależnie od wyboru TTS:**
- Sample głosów: Mikołaj (`~/cuktai/voices/mikolaj.wav`), Wiktoria (`~/cuktai/voices/wiktoria.wav`)
- Ewa i Piotr — sample do nagrania po wywiadach
- Pipeline: agent text → TTS engine (do ustalenia) → WAV → afplay → głośniki
- Infrastruktura (WebSocket bridge, TD) działa niezależnie od wyboru TTS

**Piotr dostarczy wyniki researchu TTS → wtedy implementujemy.**

### 4.5.5 Checklist przed CUKTAI Day

```
PRE-PERFORMANCE CHECKLIST:
□ Hackintosh ON, SSH działa, Ollama loaded, Hindsight healthy
□ MacBook: TD projekt otwarty, WebSocket connected do Hackintoshu
□ DI Box podłączony (MacBook → projektor → audio)
□ Mikrofon USB podłączony, Whisper testowy
□ TTS testowy — każdy agent mówi "Test"
□ WebSocket timeout: 999999 (nie 5000!)
□ Anty-disconnect instrukcje w promptach
□ OBS recording ON (Syphon z TD)
□ Telefon z /consilium gotowy (Telegram)
□ Backup: jeśli Hackintosh padnie → agenci fallback na cloud API
```

### 4.5.6 Lekcje z Super Day I (NOMUS, 19.03.2026)

Wbudowane w architekturę:
- **DI Box OBOWIĄZKOWY** — bez niego ground loop = flickering
- **WebSocket timeout 999999** — nie 5000 (random disconnects)
- **Anty-disconnect w promptach** — agent nie może sam zakończyć rozmowy
- **afplay do audio** — TD audio engine nie działa niezawodnie, subprocess lepszy
- **OBS + Syphon** — TD non-commercial blokuje export, OBS nagrywa z Syphon
- **ASR keywords** — lista polskich nazw/terminów CUKT dla lepszego STT

**Blokuje:** Nic — to jest warstwa prezentacji, może działać gdy reszta działa

---

## FAZA 4.6: Podświadomość CUKTAI — Self-Improvement Loop (Track D+, tydzień 6-7)

> Wzorzec inspirowany "Subconscious Agent" (Graeme @gkisokay, 03.04.2026).
> Adaptacja: nie kopiujemy 1:1 — CUKTAI ma silniejszą infrastrukturę (5 agentów, PG, Hindsight).
> Pełna analiza: `wiki/research/subconscious-agent-pattern.md`

### 4.6.1 Koncepcja

Consilium (Faza 4) produkuje uchwały i decyzje. Ale brakuje mechanizmu **samoulepszania** — 
systemu, który po każdym cyklu zapisuje CO POPRAWIĆ NASTĘPNYM RAZEM.

"Podświadomość CUKTAI" = cykliczne mini-Consilium z pętlą feedbacku:

```
Cron (co 24h lub po wydarzeniu)
  │
  ├─→ 1. OBSERVE: Zbierz nowe fakty z pamięci agentów + archiwum + Notion
  ├─→ 2. IDEATE: Każdy agent generuje 1-3 propozycje/obserwacje
  ├─→ 3. DEBATE: Mini-Consilium — agenci debatują (2 rundy)
  ├─→ 4. SYNTHESIZE: Moderator → wniosek + improvement-backlog
  ├─→ 5. APPROVE: Telegram do Piotra — akceptuj/odrzuć
  ├─→ 6. PERSIST: Wniosek → cuktai-inst bank (Hindsight)
  │                 improvement-backlog → state file
  └─→ 7. NEXT RUN: Starts from updated state + backlog
```

### 4.6.2 Improvement Backlog

Kluczowy element z wzorca Graeme'a — zapis procesu myślenia, nie tylko wyników:

```
/home/macstorm/cuktai/consilium/state/
├── improvement-backlog.md    # Co poprawić w następnym cyklu
├── governance.json           # Reguły systemu (co wolno, czego nie)
├── runs/                     # Historia cykli
│   ├── 2026-04-10/
│   │   ├── ideas.jsonl       # Pomysły agentów
│   │   ├── debate.jsonl      # Przebieg debaty
│   │   ├── synthesis.md      # Wniosek Moderatora
│   │   └── run-summary.json  # Metryki cyklu
│   └── ...
└── latest-summary.json       # Stan aktualny
```

### 4.6.3 Różnice vs wzorzec Graeme'a

| Graeme (Subconscious) | CUKTAI (Podświadomość) |
|------------------------|------------------------|
| 1 pętla ideacja/krytyka (2 modele) | 5 agentów z osobowościami + Moderator |
| Flat JSON/JSONL/md files | PostgreSQL + pgvector + Hindsight |
| Optymalizacja contentu (engagement) | Pamięć instytucjonalna + decyzje artystyczne |
| "Winning concept" (1 prawda) | Prawda polifoniczna + zdania odrębne |
| Discord delivery | Telegram + Notion + Hindsight cuktai-inst |

### 4.6.4 Implementacja (rozszerzenie orchestrator.py)

Dodać do klasy `Consilium`:
- `run_subconscious(topic=None)` — auto-temat z improvement-backlog jeśli brak
- `persist_improvement_backlog(synthesis, debate_log)` — zapis co poprawić
- `load_previous_state()` — wczytanie backlogu z poprzedniego cyklu
- Cron: `hermes cron create "0 8 * * *" "python3 consilium/orchestrator.py --subconscious"`

### 4.6.5 Guardrails

- Evidence-first: decyzje na podstawie archiwum i faktów, nie domysłów
- Approval gate: ZAWSZE Telegram do Piotra przed persist
- Zamrożone tematy: lista tematów które system nie zmienia samodzielnie
- Max głębokość: subconscious nie tworzy kolejnych subconscious (brak rekursji)
- Backlog cap: max 10 aktywnych improvement items

**Zależności:** Faza 4.1 (Consilium orchestrator) musi działać. Hindsight + Telegram muszą być aktywne.
**Blokuje:** Nic — to warstwa samoulepszania, reszta działa bez niej.

---

## FAZA 5: Wyjście na świat (Track E, tydzień 7-8+)

### 5.1 Pipeline publikacji

```
Agent tworzy draft
  → Zapisuje do kolejki "do zatwierdzenia"
  → Telegram: Piotr dostaje powiadomienie "Wiktoria napisała manifest — zatwierdź?"
  → Piotr: /approve lub /reject z komentarzem
  → Jeśli approved → publikacja (social media API / email)
  → Jeśli rejected → agent dostaje feedback, poprawia
```

### 5.2 Generacja mediów (późniejszy etap)

- Muzyka: integracja z narzędziami generatywnymi
- Obrazy: lokalne modele (Stable Diffusion na RX 6800 XT via ROCm)
- Video: montaż z archiwum + generowane

### 5.3 Samofinansowanie (najdalszy horyzont)

- Monitoring grantów artystycznych → agent przygotowuje aplikacje
- Social media → monetyzacja treści
- Mini obiekty sztuki → e-commerce

---

## Mapa zależności

```
FAZA 0 (Hackintosh, modele)
  │
  ├──→ FAZA 1 (PostgreSQL, Hindsight, Hermes)
  │       │
  │       ├──→ FAZA 3 (Archive Pipeline)
  │       │       │
  │       │       └──→ FAZA 4 (Consilium + Telegram)
  │       │               │
  │       │               ├──→ FAZA 4.5 (Performance / TouchDesigner)
  │       │               │
  │       │               └──→ FAZA 5 (Publikacje)
  │       │               ↑
  │       └───────────────┘
  │
  └──→ FAZA 2 (Persony, SOUL.md, wywiady)
          │
          └──→ FAZA 4 (Consilium potrzebuje person)
```

**Ścieżka krytyczna:** Faza 0 → Faza 1 → Faza 4 → Faza 4.5 (performance)
**Równolegle:** Faza 2 (persony) + Faza 3 (archiwum) mogą iść niezależnie
**Faza 4.5** może zacząć się wcześniej — TD setup jest niezależny, integracja z Hermes wymaga Fazy 4

---

## Harmonogram (szacunkowy)

| Tydzień | Faza 0 | Faza 1 | Faza 2 | Faza 3 | Faza 4 | Faza 4.5 | Faza 5 |
|---------|--------|--------|--------|--------|--------|----------|--------|
| 1 | ✅ Hackintosh | ▶ PG, Hindsight | ▶ Profile, SOUL.md | | | | |
| 2 | | ▶ MCP, backup | ▶ Wywiad Mikołaj | ▶ Import KB | | | |
| 3 | | ✅ | ▶ Wywiad Piotr | ▶ Import Evernote | | | |
| 4 | | | ▶ Transkrypcja Ewa | ▶ Import USB | ▶ Consilium | | |
| 5 | | | ✅ | ▶ Embedding | ▶ Plugin + Telegram | ▶ WS Bridge | |
| 6 | | | | ✅ | ✅ | ▶ TD integration | |
| 7 | | | | | | ▶ Audio pipeline | ▶ Draft pipeline |
| 8 | | | | | | ✅ Próba generalna | ▶ Testy |
| 9 | | | | | | **CUKTAI DAY** | |

---

## Ryzyka i mitygacja

| Ryzyko | Prawdopodobieństwo | Wpływ | Mitygacja |
|--------|-------------------|-------|-----------|
| 27b model nie mieści się w 16GB VRAM | Średnie | Wysoki | Fallback: hermes3:8b (sprawdzony, 86 tok/s) |
| Multi-agent Hermes (#344) nie wyjdzie | Niskie | Niski | Python orchestrator działa już teraz |
| Hindsight integration bugs | Średnie | Średni | Fallback: Holographic (local SQLite) |
| Wywiady się opóźniają | Wysokie | Średni | Agenci mogą startować z SOUL.md v1, ewoluują potem |
| Ollama switching latency | Niskie | Niski | Wszystkie agenty = jeden model, różne SOUL.md |
| Consilium jakość z małymi modelami | Średnie | Średni | Testuj najpierw z Claude API, potem migruj na lokalne |

---

## Definicja sukcesu (Milestone'y)

- **M1 (koniec tyg. 2):** Hermes + Hindsight działają, jeden agent odpowiada na pytania z pamięcią
- **M2 (koniec tyg. 3):** 5 agentów z osobowościami, archiwum importowane (KB + Evernote)
- **M3 (koniec tyg. 5):** Consilium działa — 5 agentów debatuje temat i produkuje uchwałę
- **M4 (koniec tyg. 6):** Telegram bot — urzędnicy CUKT mogą rozmawiać z agentami
- **M5 (koniec tyg. 6):** WebSocket bridge działa — Hermes agent streaming do TD na żywo
- **M6 (koniec tyg. 8):** Próba generalna — pełne Consilium Live z TTS + TD + megafony
- **M7 (tyg. 9):** **CUKTAI DAY** — pierwsze publiczne Zebranie z pełnym stackiem

---

*Plan opracowany 4 kwietnia 2026 przez BOT na podstawie specyfikacji CUKTAI vFinal + deep research Hermes Agent framework + Hindsight memory system.*
*Research vault: `~/.claude/MEMORY/RESEARCH/2026-04/2026-04-04_hermes-agent-framework/`*
