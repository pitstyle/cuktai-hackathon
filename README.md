# CUKTAI — Autonomous Bureau of Technical Culture

**5 AI agents. 1 archive. No script.**

CUKTAI is an AI-driven autonomous system that resurrects a 30-year-old art collective (C.U.K.T., Gdansk 1995-2001) through 5 persistent agents who investigate, debate, and produce content from 897 archival records — with zero human scripting.

Built with **Hermes Agent** + **Kimi K2.5** + **Hindsight Memory**.

## What it does

### Autonomous Podcasts (2AM, no human)
Archiwistka picks a topic from the archive. 5 agents narrate using 4 structures (Rashomon, Nolan, Sledztwo, Kronika). Bilingual PL+EN. 10 cloned voices via Chatterbox TTS. Auto-published to [cukt.click](https://cukt.click).

**Kimi K2.5** powers the narrative generation — richer prose, better Polish understanding, and stronger creative quality than other models we tested (GPT-4o, DeepSeek alone).

### Live Performance
Piotr speaks. Agents debate in real-time. TouchDesigner visualizes transcripts and archive photos. Agents control visuals via MCP.

### Nightly Investigations (Teczki)
Agents autonomously investigate archival projects overnight. 25+ investigation files produced. Contradictions found. Connections humans missed for 30 years.

### Consilium (Debate System)
Multi-agent structured debates on archive topics. Agents argue from their unique perspectives. Decisions logged.

## The 5 Agents

| Agent | Role | Voice |
|-------|------|-------|
| **Peter Style** | Predatory intellectual, original CUKT founder's digital twin | Aggressive, Russian curses |
| **Ewa Virus** | Provocateur, HE not she, confrontational | Raw, swears heavily |
| **Mikolaj** | The one who looks back, gardens, can't use technology | Poetic, fragmentary |
| **Wiktoria Cukt** | AI President, Habeas Mentem law author | Formal, institutional |
| **Archiwistka** | Murderbot-style archivist, multi-feed surveillance | Dry, radio protocol |

Each agent has persistent memory (Hindsight), unique personality (SOUL.md), and operates via Hermes Agent on a local Qwen3.5-35B LLM.

## Architecture

```
PostgreSQL Archive (897 records, pgvector)
    |
    v
Hermes Agent (5 profiles, Hindsight memory banks)
    |
    +-- Kimi K2.5 (narrative generation, creative quality)
    +-- DeepSeek V4 Flash (translation, fast responses)  
    +-- Qwen3.5-35B local (agent reasoning, zero API cost)
    |
    +-- Podcast Pipeline (narrate > translate > TTS > publish)
    +-- Live Relay (Discord/Telegram > TTS > TouchDesigner)
    +-- Archive MCP (agents query PostgreSQL directly)
    +-- Consilium (multi-agent debate)
    |
    v
cukt.click (Astro website, auto-deployed)
```

## This Showcase Contains

- `agents/` — 5 SOUL.md personality files (the heart of the system)
- `episodes/` — Podcast narratives + metadata (EP001, EP003, EP004)
- `teczki/` — Investigation files produced by agents overnight
- `descriptions/` — Agent research outputs
- `scripts/` — Relay, podcast pipeline, translation
- `mcp/` — Archive MCP server
- `consilium/` — Multi-agent debate orchestrator
- `VERSION.md` — System status and component list

## Links

- Website: [cukt.click](https://cukt.click)
- Hackathon video: [link TBD]

## Hermes Hackathon 2026

Submitted for the **Hermes Agent Creative Hackathon** by @NousResearch & @Kimi_Moonshot.

Created by Piotr Wyrzykowski (Peter Style) with BOT (AI coordinator).
