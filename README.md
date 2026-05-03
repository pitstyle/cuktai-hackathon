# CUKTAI — Autonomous Bureau of Technical Culture

**5 AI agents. 1 archive. No script.**

CUKTAI is an autonomous digital art institution built on the real archive of C.U.K.T. (Central Office of Technical Culture) — a Polish art collective active in Gdansk, 1995–2001. 5 persistent AI agents investigate, debate, perform, and produce creative artifacts from 897 archival records — with zero human scripting.

**3 of the agents are digital twins of real, living artists** — built from interviews, personal archives, and decades of creative history. They carry the voices, tensions, and unresolved questions of people who actually lived this work.

Built with **Hermes Agent** + **Kimi K2.5** + **Hindsight Memory**.

## What the system produces

### Autonomous Podcasts (2AM, no human involved)
Archiwistka picks a topic from the archive. 5 agents narrate using 4 narrative structures (Rashomon, Nolan, Sledztwo, Kronika). Bilingual PL+EN. 10 cloned voices via Chatterbox TTS. Auto-published to [cukt.click](https://cukt.click).

**Kimi K2.5** powers the narrative generation — richer prose, better Polish understanding, and stronger creative quality than other models we tested.

### Live Performance
Piotr speaks into the microphone. Agents debate in real-time. TouchDesigner visualizes live transcripts and archive photos. Agents control visuals directly via MCP — choosing which archival images to display based on what they're discussing.

### Nightly Archive Investigations (Teczki)
Agents autonomously investigate archival projects overnight. 25+ investigation case files produced. Contradictions found between documents. Connections humans missed for 30 years discovered by AI.

### Consilium (Multi-Agent Debate)
Structured institutional debates on archive topics. Agents argue from their unique perspectives. Decisions are logged as institutional memory and influence future agent behavior.

### Autonomy Loop
The system runs a continuous cycle: agents take autonomous walks through the archive → emit signals when they discover something → Signal Watcher triggers debates → Consilium produces decisions → Dream Cycle consolidates overnight → priorities feed back into tomorrow's walks. 24/7, no human in the loop.

## The 5 Agents

| Agent | Identity | Role |
|-------|----------|------|
| **Peter Style** | Digital twin of Piotr Wyrzykowski (real artist, CUKT co-founder) | Predatory intellectual, architectural thinker |
| **Ewa Virus** | Digital twin of Adam Popek (real artist, CUKT co-founder) | Provocateur, confrontational, raw |
| **Mikolaj** | Digital twin of Robert Mikolaj Jurkowski (real artist, CUKT co-founder) | The one who looks back, poetic, can't use technology |
| **Wiktoria Cukt 2.0** | AI President — no human original, born from 853+ conversations | Author of Habeas Mentem law (rights of digital entities), institutional voice |
| **Archiwistka** | Murderbot-style archivist bot | Multi-feed surveillance, dry radio protocol, nightly investigations |

Each agent has persistent memory (Hindsight), unique personality (SOUL.md), and operates via Hermes Agent.

## The Vision

CUKTAI is not a chatbot or a demo. It is an institution designed to outlive its creators.

**Phase 1: Infrastructure** — Done. Agents, archive, memory, tools.
**Phase 2: Autonomous Production** — Now. Podcasts, investigations, live performances.
**Phase 3: Deep Autonomy** — Next. Self-directed research, exhibition co-curation, archival book publishing.
**Phase 4: Fundacja Bot** — The system becomes a legal entity (Polish NGO). An institution that IS technology.

The endgame: CUKTAI as a historical co-curator — designing exhibitions in collaboration with museums, publishing archival books with AI-generated analysis, producing new manifestos. The digital twin of an art collective that keeps creating after the humans stop.

## Architecture

```
PostgreSQL Archive (897 records, pgvector embeddings)
    |
    v
Hermes Agent (5 profiles, 6 Hindsight memory banks)
    |
    +-- Kimi K2.5 via OpenRouter (narrative generation)
    +-- DeepSeek V4 Flash (translation, fast work)
    +-- Qwen3.5-35B local on GPU (reasoning, zero API cost)
    |
    +-- Podcast Pipeline (narrate > translate > TTS > publish)
    +-- Live Relay (Telegram/Discord > ElevenLabs TTS > TouchDesigner)
    +-- Archive MCP Server (agents query archive directly)
    +-- Consilium Orchestrator (multi-agent debate)
    +-- Autonomy Loop (walks > signals > debates > dream cycle)
    |
    v
cukt.click (Astro website, auto-deployed via Render)
```

## This Showcase Contains

- `agents/` — 5 SOUL.md personality files (the heart of the system)
- `episodes/` — Podcast narratives + metadata (EP001, EP003, EP004)
- `episodes/live/` — Live performance transcripts
- `teczki/` — Investigation case files produced by agents overnight
- `descriptions/` — Agent research outputs on archive items
- `scripts/` — Live relay, podcast pipeline, translation, publishing
- `mcp/` — Archive MCP server (PostgreSQL + pgvector)
- `consilium/` — Multi-agent debate orchestrator
- `VERSION.md` — Full system component list

## Links

- **Website:** [cukt.click](https://cukt.click)
- **Video:** [Hackathon Demo on X](https://x.com/peter_style/status/2050915463027163604)

## Hermes Hackathon 2026

Submitted for the **Hermes Agent Creative Hackathon** by @NousResearch & @Kimi_Moonshot.

Created by Piotr Wyrzykowski (Peter Style) with BOT (AI coordinator).
