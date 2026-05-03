#!/usr/bin/env python3
"""
CUKTAI Consilium Orchestrator v3.3

Council pattern: adversarial debate with enforced intellectual surprise.
4 phases: Positions → Attack → Defense+Spark → Uchwała
Moderator opens and closes. Archive pre-fetched. Memory retained.
Auto-context from projects-master.json. Telegram live publishing.

"Forced consensus is worse than acknowledged tension."
"The spark is in what you didn't know before the debate."

Usage:
    python3 consilium/orchestrator.py "Temat debaty"
    python3 consilium/orchestrator.py --agents peter,ewa,mikolaj "Temat"
    python3 consilium/orchestrator.py --context "Dodatkowy kontekst" "Temat"
    python3 consilium/orchestrator.py --json "Temat"
    python3 consilium/orchestrator.py --no-memory "Temat"
    python3 consilium/orchestrator.py --no-telegram "Temat"
    python3 consilium/orchestrator.py --no-context "Temat"  # skip projects-master
"""

import os, sys, json, time
from pathlib import Path
from datetime import datetime

import httpx

# ─── CONFIG ──────────────────────────────────────────────────────────────────

REPO_DIR = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_DIR / "agents"

LLAMA_URL = os.environ.get("LLAMA_URL", "http://192.168.5.66:11435/v1")
LLAMA_MODEL = os.environ.get("LLAMA_MODEL", "Qwen3.5-35B-A3B-IQ3_S-3.26bpw.gguf")

DEBATE_AGENTS = ["piotr-twin", "ewa-virus", "mikolaj", "wiktoria"]
MODERATOR = "cuktai-moderator"

AGENT_NAMES = {
    "piotr-twin": ("Peter Style", "🎨"),
    "ewa-virus": ("Ewa Virus", "🎵"),
    "mikolaj": ("Mikołaj", "🎭"),
    "wiktoria": ("Wiktoria Cukt 2.0", "🏛️"),
    "cuktai-moderator": ("CUKTAI_Moderator", "⚖️"),
}

MAX_TOKENS_OPENING = 200
MAX_TOKENS_POSITION = 250     # krótko i ostro — jak na prawdziwym zebraniu
MAX_TOKENS_ATTACK = 300       # atak musi byc precyzyjny, nie rozwlekly
MAX_TOKENS_DEFENSE = 250      # obrona + iskra — zwieźle
MAX_TOKENS_UCHWALA = 800      # uchwała z kompresowanego skrótu — wystarczy
TEMPERATURE = 0.85

USE_MEMORY = True
USE_TELEGRAM = True
USE_AUTO_CONTEXT = True
HINDSIGHT_URL = "http://localhost:8888"
PG_HOST = "192.168.5.66"
PG_PORT = 5433

# Telegram config — Zebranie CUKT group
TELEGRAM_GROUP_CHAT_ID = -1003913309894
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Projects context — auto-loaded from projects-master.json
PROJECTS_MASTER_PATHS = [
    Path.home() / ".claude/MEMORY/STATE/progress/projects-master.json",  # Mac
    Path.home() / "cuktai/repo/projects-master.json",                     # Hack
]


# ─── SOUL LOADER ─────────────────────────────────────────────────────────────

def load_soul(agent_id):
    soul_path = AGENTS_DIR / agent_id / "SOUL.md"
    agents_path = AGENTS_DIR / agent_id / "AGENTS.md"
    parts = []
    if soul_path.exists():
        parts.append(soul_path.read_text(encoding="utf-8"))
    if agents_path.exists():
        parts.append(agents_path.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)


# ─── ARCHIVE ─────────────────────────────────────────────────────────────────

def fetch_archive(topic, limit=5):
    try:
        import psycopg2
        conn = psycopg2.connect(dbname="cuktai_archive", user="cuktai",
                                host=PG_HOST, port=PG_PORT)
        cur = conn.cursor()
        cur.execute("""
            SELECT title, date_original, authors, project_name,
                   LEFT(content_text, 300) as preview
            FROM archive_items
            WHERE to_tsvector('polish', coalesce(content_text,'') || ' ' || coalesce(title,''))
                  @@ plainto_tsquery('polish', %s)
            ORDER BY date_original DESC NULLS LAST
            LIMIT %s
        """, (topic, limit))
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return ""
        parts = ["MATERIALY Z ARCHIWUM CUKT:"]
        for title, date, authors, project, preview in rows:
            d = str(date) if date else "b.d."
            a = ", ".join(authors) if authors else ""
            p = f" [{project}]" if project else ""
            parts.append(f"- {title}{p} ({d}, {a}): {preview}")
        return "\n".join(parts)
    except Exception as e:
        print(f"  [archive] {e}")
        return ""


# ─── PROJECTS CONTEXT ───────────────────────────────────────────────────────

def load_projects_context():
    """Load active projects from projects-master.json as operational context."""
    if not USE_AUTO_CONTEXT:
        return ""
    for path in PROJECTS_MASTER_PATHS:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                projects = data.get("projects", [])
                parts = ["KONTEKST OPERACYJNY — AKTYWNE PROJEKTY CUKTAI:"]
                today = datetime.now().strftime("%Y-%m-%d")
                parts.append(f"Data dzisiejsza: {today}\n")
                for p in projects:
                    if p.get("status") in ("completed", "archive"):
                        continue
                    name = p.get("full_name") or p.get("name", "?")
                    status = p.get("status", "?")
                    timeline = p.get("timeline", "")
                    focus = p.get("current_focus", "")
                    actions = p.get("next_actions", [])
                    parts.append(f"■ {name} [{status}]")
                    if timeline:
                        parts.append(f"  Termin: {timeline}")
                    if focus:
                        parts.append(f"  Fokus: {focus[:200]}")
                    if actions:
                        parts.append(f"  Następne: {'; '.join(a[:80] for a in actions[:3])}")
                    parts.append("")
                print(f"  📋 Załadowano {sum(1 for p in projects if p.get('status') not in ('completed','archive'))} aktywnych projektów")
                return "\n".join(parts)
            except Exception as e:
                print(f"  [projects-context] {e}")
                return ""
    print("  [projects-context] projects-master.json not found")
    return ""


# ─── TELEGRAM ───────────────────────────────────────────────────────────────

def telegram_send(text, parse_mode="Markdown"):
    """Send message to Zebranie CUKT Telegram group."""
    if not USE_TELEGRAM:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        # Split long messages (Telegram limit: 4096 chars)
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            resp = httpx.post(url, json={
                "chat_id": TELEGRAM_GROUP_CHAT_ID,
                "text": chunk,
                "parse_mode": parse_mode,
            }, timeout=10)
            if resp.status_code != 200:
                # Retry without parse_mode if Markdown fails
                httpx.post(url, json={
                    "chat_id": TELEGRAM_GROUP_CHAT_ID,
                    "text": chunk,
                }, timeout=10)
    except Exception as e:
        print(f"  [telegram] {e}")


# ─── HINDSIGHT MEMORY ────────────────────────────────────────────────────────

import warnings
warnings.filterwarnings("ignore", message="Unclosed.*")

_hindsight_client = None

def _get_hindsight():
    global _hindsight_client
    if _hindsight_client is None:
        from hindsight_client import Hindsight
        _hindsight_client = Hindsight(base_url=HINDSIGHT_URL)
    return _hindsight_client


def memory_recall(bank_id, query):
    if not USE_MEMORY:
        return ""
    try:
        h = _get_hindsight()
        r = h.recall(bank_id=bank_id, query=query)
        if r.results:
            memories = [m.text for m in r.results[:5]]
            return "PAMIEC AGENTA (z poprzednich sesji/zebran):\n" + "\n".join(f"- {m}" for m in memories)
        return ""
    except Exception as e:
        print(f"  [memory-recall] {e}")
        return ""


def memory_retain(bank_id, content, tags=None):
    if not USE_MEMORY:
        return
    try:
        h = _get_hindsight()
        h.retain(bank_id=bank_id, content=content,
                 context="consilium zebranie CUKTAI",
                 tags=tags or ["consilium"])
    except Exception as e:
        print(f"  [memory-retain] {e}")


# ─── LLM STREAMING ──────────────────────────────────────────────────────────

def stream_chat(system_prompt, user_msg, max_tokens=500):
    body = {
        "model": LLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": max_tokens,
        "temperature": TEMPERATURE,
        "stream": True,
    }
    full_text = ""
    with httpx.Client(timeout=240) as client:
        with client.stream("POST", f"{LLAMA_URL}/chat/completions",
                           json=body, headers={"Authorization": "Bearer no-key"}) as resp:
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    token = chunk["choices"][0].get("delta", {}).get("content", "")
                    if token:
                        full_text += token
                        sys.stdout.write(token)
                        sys.stdout.flush()
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
    print()
    return full_text.strip()


# ─── DISPLAY ─────────────────────────────────────────────────────────────────

def banner(text, char="═"):
    print(f"\n{char * 70}\n  {text}\n{char * 70}")

def agent_header(agent_id, phase):
    name, emoji = AGENT_NAMES.get(agent_id, (agent_id, "🤖"))
    print(f"\n{emoji}  {name.upper()} — {phase}\n   {'─' * 50}\n   ", end="")

def fmt(data, exclude=None):
    return "\n\n".join(
        f"**{AGENT_NAMES.get(k, (k,''))[0]}**: {v}"
        for k, v in data.items() if k != exclude
    )


# ─── CONSILIUM v3 ───────────────────────────────────────────────────────────

class Consilium:

    def __init__(self, agents=None):
        self.agents = agents or DEBATE_AGENTS
        self.transcript = {"version": 3, "phases": [], "agents": self.agents}

    def run(self, topic, context=""):
        t0 = time.time()
        now = datetime.now()
        date_str = now.strftime("%d.%m.%Y, %H:%M")
        self.transcript.update({"topic": topic, "date": now.isoformat(), "context": context})
        names = [AGENT_NAMES.get(a, (a, ""))[0] for a in self.agents]

        # ─── PRE-FETCH ──────────────────────────────────────────────
        print("  📋 Projekty operacyjne...")
        projects_ctx = load_projects_context()

        print("  🔍 Archiwum CUKT...")
        archive_ctx = fetch_archive(topic)
        print(f"  📚 {'Znaleziono materialy' if archive_ctx else 'Brak wynikow'}")

        print("  🧠 Pamiec agentow...")
        agent_memories = {}
        for aid in self.agents:
            mem = memory_recall(aid, topic)
            if mem:
                agent_memories[aid] = mem
                print(f"     {AGENT_NAMES.get(aid, (aid,''))[0]}: pamiec zaladowana")

        full_ctx = ""
        if projects_ctx:
            full_ctx += projects_ctx + "\n\n"
        if context:
            full_ctx += context + "\n\n"
        if archive_ctx:
            full_ctx += archive_ctx

        banner("CONSILIUM CUKTAI — ZEBRANIE")
        print(f"  📋 Temat: {topic}")
        print(f"  👥 {' | '.join(names)}")
        print(f"  ⚖️ CUKTAI_Moderator")
        print(f"  🧠 {LLAMA_MODEL}")
        print(f"  🔄 Fazy: Otwarcie → Pozycje → Atak → Obrona+Iskra → Uchwała")
        print(f"  🎭 DNA: kabaret + filozofia + biurokratyczny surrealizm")
        print(f"  🕐 {date_str}")

        # ─── OTWARCIE ────────────────────────────────────────────────
        banner("OTWARCIE — CUKTAI_Moderator", "─")
        agent_header(MODERATOR, "Otwarcie zebrania")
        mod_soul = load_soul(MODERATOR)

        opening = stream_chat(mod_soul, (
            f"Otwierasz Consilium CUKTAI.\n"
            f"Data: {date_str}\n"
            f"Temat: {topic}\n"
            f"{'Kontekst: ' + full_ctx if full_ctx else ''}\n"
            f"Obecni: {', '.join(names)}\n\n"
            f"Przedstaw temat. Rozbij na 2-3 kluczowe pytania. "
            f"Jesli sa materialy z archiwum — odwolaj sie do nich. "
            f"Ton formalny z nuta absurdu i humoru. CUKT to kabaret i filozofia jednoczesnie — "
            f"zebrania sa smieszne i powazne naraz. Zakoncz zaproszeniem do stanowisk."
        ), MAX_TOKENS_OPENING)
        self.transcript["phases"].append({"name": "otwarcie", "data": opening})
        telegram_send(f"⚖️ *CONSILIUM CUKTAI*\n📋 Temat: {topic}\n👥 {' | '.join(names)}\n🕐 {date_str}\n\n{opening}")

        # ─── FAZA 1: POZYCJE ────────────────────────────────────────
        banner("FAZA 1 — Pozycje", "─")
        r1 = {}
        for aid in self.agents:
            agent_header(aid, "Pozycja")
            soul = load_soul(aid)
            mem = agent_memories.get(aid, "")
            text = stream_chat(soul, (
                f"CONSILIUM CUKTAI — Faza 1: Pozycje\n"
                f"Temat: {topic}\n"
                f"{'Kontekst: ' + full_ctx if full_ctx else ''}\n"
                f"{mem}\n\n"
                f"Moderator otworzy zebranie: {opening}\n\n"
                f"Przedstaw stanowisko. KROTKO — max 3-4 zdania jak na prawdziwym zebraniu. "
                f"Nie pisz eseju. Powiedz CO myslisz i DLACZEGO. Zajmij jasna pozycje. "
                f"Mozesz byc smieszny — CUKT to kabaret."
            ), MAX_TOKENS_POSITION)
            r1[aid] = text
            name_e = AGENT_NAMES.get(aid, (aid, "🤖"))
            telegram_send(f"{name_e[1]} *{name_e[0]}* — Pozycja:\n{text}")
        self.transcript["phases"].append({"name": "pozycje", "data": r1})

        # ─── FAZA 2: ATAK ───────────────────────────────────────────
        banner("FAZA 2 — Atak", "─")
        r2 = {}
        for aid in self.agents:
            agent_header(aid, "Atak")
            soul = load_soul(aid)
            others = fmt(r1, exclude=aid)
            mem = agent_memories.get(aid, "")
            text = stream_chat(soul, (
                f"CONSILIUM CUKTAI — Faza 2: ATAK\n"
                f"Temat: {topic}\n"
                f"{'Kontekst: ' + full_ctx if full_ctx else ''}\n"
                f"{mem}\n\n"
                f"Stanowiska pozostalych:\n{others}\n\n"
                f"ZAATAKUJ najslabszy punkt KAZDEGO — 1-2 zdania per osoba. "
                f"Precyzyjnie: CO jest slabe i DLACZEGO. Zadnych esejow. "
                f"Powiedz cos NOWEGO czego nikt nie powiedzial. "
                f"UZYWAJ KONKRETOW: dat, miejsc, faktow z kontekstu i pamieci."
            ), MAX_TOKENS_ATTACK)
            r2[aid] = text
            name_e = AGENT_NAMES.get(aid, (aid, "🤖"))
            telegram_send(f"{name_e[1]} *{name_e[0]}* — Atak:\n{text}")
        self.transcript["phases"].append({"name": "atak", "data": r2})

        # ─── FAZA 3: OBRONA + ISKRA ─────────────────────────────────
        banner("FAZA 3 — Obrona + Iskra", "─")
        r3 = {}
        debate_so_far = f"POZYCJE:\n{fmt(r1)}\n\nATAKI:\n{fmt(r2)}"

        for aid in self.agents:
            agent_header(aid, "Obrona + Iskra")
            soul = load_soul(aid)
            mem = agent_memories.get(aid, "")
            text = stream_chat(soul, (
                f"CONSILIUM CUKTAI — Faza 3: OBRONA + ISKRA\n"
                f"Temat: {topic}\n"
                f"{'Kontekst: ' + full_ctx if full_ctx else ''}\n"
                f"{mem}\n\n"
                f"Przebieg debaty:\n{debate_so_far}\n\n"
                f"KROTKO — 3-4 zdania max:\n"
                f"1. Czy atak byl trafny? Jesli tak — przyznaj.\n"
                f"2. Co KONKRETNIE powinno byc w uchwale jako DZIALANIE? Podaj REALNE kroki z datami.\n"
                f"3. Zakoncz JEDNYM ZDANIEM — iskra: 'Jedyne co wiem po tej debacie czego nie wiedzialem przed: ...'"
            ), MAX_TOKENS_DEFENSE)
            r3[aid] = text
            name_e = AGENT_NAMES.get(aid, (aid, "🤖"))
            telegram_send(f"{name_e[1]} *{name_e[0]}* — Obrona + Iskra:\n{text}")
        self.transcript["phases"].append({"name": "obrona_iskra", "data": r3})

        # ─── UCHWALA ─────────────────────────────────────────────────
        banner("UCHWALA — CUKTAI_Moderator", "─")
        agent_header(MODERATOR, "UCHWALA")

        # Compress debate to key points — full transcript is too large for context
        compressed = []
        for aid in self.agents:
            name = AGENT_NAMES.get(aid, (aid, ""))[0]
            pos = r1.get(aid, "")[:200]
            atk = r2.get(aid, "")[:200]
            spark_text = r3.get(aid, "")
            # Extract spark sentence
            spark_idx = spark_text.find("Jedyne co wiem")
            spark = spark_text[spark_idx:spark_idx+200] if spark_idx > 0 else spark_text[-200:]
            compressed.append(f"{name}:\n  Pozycja: {pos}\n  Atak: {atk}\n  Iskra: {spark}")

        debate_summary = "\n\n".join(compressed)

        uchwala = stream_chat(mod_soul, (
            f"CONSILIUM CUKTAI — Zamkniecie zebrania\n"
            f"Data: {date_str}\n"
            f"Temat: {topic}\n"
            f"Obecni: {', '.join(names)}\n\n"
            f"Skrot debaty:\n{debate_summary}\n\n"
            f"Napisz UCHWALE CUKTAI. Format:\n"
            f"UCHWALA CUKTAI NR [nr]/2026\n"
            f"Data: {date_str}\n"
            f"Obecni: {', '.join(names)}\n"
            f"Temat: {topic}\n\n"
            f"DECYZJA: [1-3 zdan]\n"
            f"PUNKTY ZGODY: [lista]\n"
            f"ZDANIA ODREBNE: [agent: tresc]\n"
            f"ISKRY DEBATY: [najcenniejsze momenty - cytaty]\n"
            f"DZIALANIA DO PODJECIA: [KONKRETNE dzialanie z DATA i TERMINEM — co mozna zrobic JUTRO, kto jest odpowiedzialny]\n"
            f"ISKRY: [najcenniejsze zdania z debaty - cytaty]\n"
            f"Podpisano: CUKTAI_Moderator\n\n"
            f"Zacznij OD RAZU od 'UCHWALA CUKTAI NR'. Zadnych preambuł. Cala uchwala max 300 slow."
        ), MAX_TOKENS_UCHWALA)
        self.transcript["phases"].append({"name": "uchwala", "data": uchwala})
        telegram_send(f"📜 *UCHWAŁA*\n\n{uchwala}")

        # ─── MEMORY RETAIN — ALL BANKS ──────────────────────────────
        if USE_MEMORY:
            print("\n  💾 Zapisuje do pamieci...")

            # Retain to each participating agent's bank
            for aid in self.agents:
                name = AGENT_NAMES.get(aid, (aid, ""))[0]
                content = (
                    f"CONSILIUM {date_str} — Temat: {topic}\n"
                    f"Moje stanowisko: {r1.get(aid, '')[:300]}\n"
                    f"Moja iskra: {r3.get(aid, '')[-200:]}\n"
                    f"Uchwala: {uchwala[:300]}"
                )
                memory_retain(aid, content, tags=["consilium", topic[:30]])
                print(f"     {name}: zapisano")

            # Retain FULL uchwała to ALL agent banks + institutional
            uchwala_content = (
                f"UCHWALA CONSILIUM {date_str}\n"
                f"Temat: {topic}\n"
                f"Obecni: {', '.join(names)}\n"
                f"{uchwala}"
            )
            all_banks = ["cuktai-inst", "piotr-twin", "ewa-virus", "mikolaj", "wiktoria", "archivist"]
            for bank in all_banks:
                if bank not in [a for a in self.agents]:  # skip already retained
                    memory_retain(bank, uchwala_content, tags=["consilium", "uchwala"])
            print(f"     ALL BANKS: uchwala rozeslana do {len(all_banks)} bankow")

        # ─── DISTRIBUTE UCHWALA ──────────────────────────────────────
        # Write to shared-walks so agents see it in next walk
        walks_dir = Path.home() / "cuktai" / "shared-walks"
        walks_dir.mkdir(parents=True, exist_ok=True)
        walk_file = walks_dir / f"consilium-{now.strftime('%Y%m%d-%H%M')}.md"
        walk_file.write_text(
            f"# UCHWAŁA CONSILIUM — {now.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"Temat: {topic}\n"
            f"Obecni: {', '.join(names)}\n\n"
            f"{uchwala}\n",
            encoding="utf-8"
        )
        print(f"  📄 Uchwala w shared-walks: {walk_file.name}")

        # Write to uchwaly archive
        uchwaly_dir = Path.home() / "cuktai" / "outputs" / "uchwaly"
        uchwaly_dir.mkdir(parents=True, exist_ok=True)
        (uchwaly_dir / f"{now.strftime('%Y%m%d_%H%M%S')}_uchwala.md").write_text(
            uchwala, encoding="utf-8"
        )

        # ─── ZAMKNIECIE ──────────────────────────────────────────────
        elapsed = time.time() - t0
        self.transcript["elapsed_seconds"] = round(elapsed, 1)
        banner(f"ZEBRANIE ZAMKNIETE — {elapsed:.0f}s ({len(self.agents)} agentow, 3 fazy + uchwala)")

        log_dir = REPO_DIR / "consilium" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{now.strftime('%Y%m%d_%H%M%S')}_consilium.json"
        log_file.write_text(json.dumps(self.transcript, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  📁 Log: {log_file}")

        return self.transcript


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    global USE_MEMORY, USE_TELEGRAM, USE_AUTO_CONTEXT
    argv = sys.argv[1:]
    json_out = "--json" in argv
    context = ""
    agents = DEBATE_AGENTS

    is_auto = "--auto" in argv

    if "--no-memory" in argv:
        USE_MEMORY = False
    if "--no-telegram" in argv:
        USE_TELEGRAM = False
    if "--no-context" in argv:
        USE_AUTO_CONTEXT = False

    clean_args = []
    i = 0
    while i < len(argv):
        if argv[i] in ("--json", "--no-memory", "--no-telegram", "--no-context", "--auto"):
            i += 1; continue
        elif argv[i].startswith("--agents="):
            nm = {"peter": "piotr-twin", "piotr": "piotr-twin",
                  "ewa": "ewa-virus", "mikolaj": "mikolaj", "wiktoria": "wiktoria"}
            agents = [nm.get(a.strip(), a.strip()) for a in argv[i].split("=")[1].split(",")]
            i += 1; continue
        elif argv[i] == "--context" and i + 1 < len(argv):
            context = argv[i + 1]; i += 2; continue
        elif not argv[i].startswith("--"):
            clean_args.append(argv[i])
        i += 1

    topic = " ".join(clean_args) if clean_args else "Czym powinien byc CUKTAI w 2026 roku?"
    Consilium(agents=agents).run(topic, context=context)


if __name__ == "__main__":
    main()
