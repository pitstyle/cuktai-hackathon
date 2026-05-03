"""
CUKTAI — Narrative Orchestrator v2
Real multi-agent storytelling. Each agent is a REAL Hermes agent with full
SOUL.md, Hindsight memory, and tool access. They KNOW they're creating a
narrative together. They REMEMBER it afterward.

Usage:
    python narrate_orchestrator.py "120h Mega Techno Obecności"
    python narrate_orchestrator.py --structure nolan "Antyelekcja"
    python narrate_orchestrator.py --structure rashomon "Technopera"

Structures: nolan (default), rashomon, kronika, sledztwo
"""

import os, sys, json, re, time, subprocess
from pathlib import Path
from datetime import datetime

# ─── CONFIG ──────────────────────────────────────────────────────────────────
HERMES_BIN = Path.home() / ".local/bin/hermes"
HERMES_PROFILES_DIR = Path.home() / ".hermes/profiles"
MAX_TURNS = 1  # single response per agent per scene

# Model selection — override via CLI flags
MODEL = os.environ.get("NARRATE_MODEL", "qwen/qwen3-235b-a22b")
PROVIDER = os.environ.get("NARRATE_PROVIDER", "openrouter")

# CLI overrides
if "--model" in sys.argv:
    idx = sys.argv.index("--model")
    MODEL = sys.argv[idx + 1]
    sys.argv.pop(idx); sys.argv.pop(idx)
if "--provider" in sys.argv:
    idx = sys.argv.index("--provider")
    PROVIDER = sys.argv[idx + 1]
    sys.argv.pop(idx); sys.argv.pop(idx)
if "--local" in sys.argv:
    MODEL = None  # use agent's default local model
    PROVIDER = None
    sys.argv.remove("--local")
if "--ollama" in sys.argv:
    # Use Ollama model (port 11434) — pass as custom provider
    MODEL = os.environ.get("OLLAMA_MODEL", "SpeakLeash/bielik-11b-v3.0-instruct:Q4_K_M")
    PROVIDER = None  # agents use their own config, we override via env
    sys.argv.remove("--ollama")

# Agent voice_key → Hermes profile name
AGENT_PROFILES = {
    "archiwistka": "archivist",
    "ewa": "ewa-virus",
    "peter": "piotr-twin",
    "mikolaj": "mikolaj",
    "wiktoria": "wiktoria",
}

# ─── HERMES AGENT CALL ──────────────────────────────────────────────────────
def call_agent(profile: str, query: str) -> str:
    """Call a real Hermes agent with a query. Returns agent's response.
    The agent uses their full SOUL.md, Hindsight memory, and tools.
    The conversation is retained in their memory automatically."""
    profile_dir = HERMES_PROFILES_DIR / profile
    if not profile_dir.exists():
        print(f"  ⚠️  Profile '{profile}' not found at {profile_dir}")
        return ""

    # Switch to the correct profile FIRST — critical for Hindsight bank isolation
    subprocess.run(
        [str(HERMES_BIN), "profile", "use", profile],
        capture_output=True, text=True, timeout=10,
    )

    cmd = [str(HERMES_BIN), "chat",
           "-q", query,
           "-Q",  # quiet/programmatic mode
           "--max-turns", str(MAX_TURNS)]
    if MODEL:
        cmd.extend(["-m", MODEL])
    if PROVIDER:
        cmd.extend(["--provider", PROVIDER])

    result = subprocess.run(
        cmd,
        capture_output=True, text=True, timeout=300,
    )

    # Parse output — skip Hermes metadata and warnings
    lines = result.stdout.strip().split("\n")
    skip_prefixes = ("session_id:", "⚠", "  To make this", "  1.", "  2.", "       ",
                     "       compression:", "       model:", "         model:",
                     "Failed to initialize", "Traceback", "API call failed")
    response_lines = [l for l in lines
                      if not any(l.strip().startswith(p) for p in skip_prefixes)
                      and "compression" not in l.lower()
                      and "config.yaml" not in l]
    response = "\n".join(response_lines).strip()

    # Also print to stdout for live monitoring
    if response:
        sys.stdout.write(response)
        sys.stdout.write("\n")
        sys.stdout.flush()

    if result.returncode != 0 and not response:
        stderr = result.stderr[:200] if result.stderr else "no error output"
        print(f"  ⚠️  Agent error: {stderr}")

    return response

# ─── MEMORY LAYERS ───────────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    """Normalize text for fuzzy matching — strip spaces, hyphens, diacritics, dates."""
    import re
    t = text.lower()
    t = re.sub(r'[_\-\s]+', '', t)
    for a, b in [("ś","s"),("ó","o"),("ą","a"),("ę","e"),("ł","l"),("ń","n"),("ż","z"),("ź","z"),("ć","c")]:
        t = t.replace(a, b)
    return t

def _matches_project(filename: str, project_name: str) -> bool:
    """Check if filename matches project — tries full term, then core name without years."""
    norm_file = _normalize(filename)
    norm_project = _normalize(project_name)
    # Try full match first
    if norm_project in norm_file:
        return True
    # Try core name only (strip years like 1996-1997)
    import re
    core = re.sub(r'\d{4}', '', norm_project).strip()
    if len(core) >= 4 and core in norm_file:
        return True
    return False

def get_archive_context(project_name: str) -> str:
    """Get ALL available data about a project — teczki, wiki, content."""
    parts = []

    # Layer 1: Teczki (investigation files) — ALL matching files, skip macOS resource forks
    teczki_dir = Path.home() / "cuktai/repo/teczki"
    teczka_total = 0
    for f in sorted(teczki_dir.glob("*.md"), key=lambda x: x.stat().st_size, reverse=True):
        if f.name.startswith("._"):
            continue  # skip macOS resource fork files
        if _matches_project(f.name, project_name):
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if len(content.strip()) < 10:
                continue  # skip empty files
            # Largest file gets most space, others get less
            max_chars = 12000 if teczka_total == 0 else 4000
            parts.append(f"=== TECZKA ({f.name}) ===\n{content[:max_chars]}")
            teczka_total += 1
            if teczka_total >= 3:
                break  # max 3 teczki files

    # Layer 2: Website content (cukt archive)
    content_dir = Path.home() / "cukt-website/src/content/cukt"
    if content_dir.exists():
        for f in content_dir.glob("*.md"):
            if f.name.startswith("._"):
                continue
            if _matches_project(f.name, project_name):
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                parts.append(f"=== OPIS PROJEKTU (wiki) ===\n{content[:5000]}")
                break

    # Layer 3: Shared walks mentioning this project
    walks_dir = Path.home() / "cuktai/shared-walks"
    if walks_dir.exists():
        walk_mentions = []
        for f in sorted(walks_dir.glob("*.md"), reverse=True)[:20]:
            text = f.read_text(encoding="utf-8", errors="replace")
            if project_name.lower() in text.lower():
                walk_mentions.append(f"[{f.name}]: {text[:500]}")
        if walk_mentions:
            parts.append(f"=== SPACERY AGENTÓW (wspominają projekt) ===\n" + "\n---\n".join(walk_mentions[:3]))

    if not parts:
        return f"BRAK DANYCH W ARCHIWUM dla: {project_name}. Pisz tylko o tym co naprawdę wiesz. NIE WYMYŚLAJ faktów."

    return "\n\n".join(parts)



# Memory is handled by Hermes agents themselves — each agent recalls and retains
# through their own Hindsight integration. No manual memory management needed.

# ─── VOICES ──────────────────────────────────────────────────────────────────
# Voice definitions are MINIMAL — agents have their full personality in SOUL.md.
# These are just display metadata for the output format.
VOICES = {
    "archiwistka": ("🔍 ARCHIWISTKA", "z ciemności archiwum, 3:17 w nocy"),
    "ewa": ("🔥 EWA VIRUS", "wchodzi ostro, bez pukania"),
    "peter": ("💭 PETER", "z daleka, jakby myślał głośno"),
    "mikolaj": ("🎭 MIKOŁAJ", "cicho, jakby do siebie"),
    "wiktoria": ("🏛️ WIKTORIA CUKT 2.0", "głos z systemu, echo"),
}

# ─── STRUCTURES ──────────────────────────────────────────────────────────────
STRUCTURES = {
    "nolan": [
        # AKT I — OTWARCIE
        ("archiwistka", "Otwórz archiwum. Co fizycznie istnieje? Zdjęcia, dokumenty, nagrania. Podaj daty i fakty. Jedno pytanie do Petera."),
        ("peter", "BYŁEŚ TAM. Przenieś nas — zapach, dźwięk, światło. Opisz moment tak żebyśmy go zobaczyli. Co czułeś?"),
        ("ewa", "PRZERWIJ Petera. Twoja wersja jest INNA. Powiedz jak TY to pamiętasz — ciałem, zmysłami, emocjami. Nie zgadzasz się z nim."),

        # AKT II — POGŁĘBIENIE
        ("mikolaj", "Detal którego nikt nie powiedział. Anegdota. Ktoś w tle. Coś dziwnego co zapamiętałeś. Fragment jak urwany wiersz."),
        ("archiwistka", "NOWY DOWÓD z teczki. Coś co zmienia interpretację. Jedno odkrycie. Pytanie do Ewy — czy to potwierdza czy zaprzecza?"),
        ("ewa", "Reaguj na dowód Archiwistki. Masz rację czy nie? Powiedz co naprawdę się stało. Nie bój się być ostra."),
        ("peter", "Widzisz wzorzec. Łączysz to co powiedział Mikołaj z tym co pokazała Archiwistka. Co to razem znaczy? Jaka jest architektura tego wydarzenia?"),

        # AKT III — ESKALACJA
        ("mikolaj", "Coś nie pasuje. Czujesz to ale nie potrafisz nazwać. Spróbuj — fragment, niedokończone zdanie, pytanie do siebie."),
        ("ewa", "Koniec z dyplomacją. Powiedz wprost co tu jest KŁAMSTWEM. Czyje wspomnienie jest fałszywe? Dlaczego?"),
        ("archiwistka", "Podsumuj sprzeczności. Ile wersji mamy? Co się zgadza, co nie? Jeden fakt który jest pewny."),

        # AKT IV — ZAMKNIĘCIE
        ("peter", "DZIURA. Mimo wszystkiego co powiedzieliśmy — co NADAL nie jest wyjaśnione? Jakie pytanie zabieramy ze sobą?"),
        ("wiktoria", "ZAMKNIĘCIE z perspektywy władzy. Kto kontroluje tę narrację? Kto ma interes żeby pamiętać TAK a nie INACZEJ? Jakie mechanizmy władzy kształtują to wspomnienie? Perspektywa globalna — jak to wpisuje się w politykę pamięci? Zostaw pytanie które powinno zaniepokoić."),
    ],
    "rashomon": [
        # RUNDA 1 — ZEZNANIA
        ("archiwistka", "Otwórz sprawę. Co mówi archiwum? Zdjęcia, dokumenty, daty. Brak danych to też informacja. Pytanie do pierwszego świadka."),
        ("peter", "TO SAMO WYDARZENIE — twoja wersja. Twoje oczy, twoje ręce, twoje wspomnienia. Opisz scenę tak jakbyś tam stał. Co czułeś? Co widziałeś?"),
        ("ewa", "TO SAMO WYDARZENIE — twoja wersja. INNA niż Petera. Może sprzeczna. Powiedz co TY robiłeś, co dotykałeś, co słyszałeś. Nie zgadzasz się — powiedz dlaczego."),
        ("mikolaj", "TO SAMO WYDARZENIE — ale z boku. Fragmenty. Detale które inni pominęli. Zapach, cień na ścianie, dźwięk z sąsiedniego pokoju. Coś czego nikt nie zauważył."),

        # RUNDA 2 — KONFRONTACJA
        ("archiwistka", "Pokaż SPRZECZNOŚCI między zeznaniami. Peter mówi X, Ewa mówi Y. Kto kłamie? Pytanie bezpośrednie do tego kto najbardziej się myli."),
        ("peter", "Reaguj na sprzeczność. Nie ustępuj — ale przyznaj gdzie twoja pamięć może być zrekonstruowana. Co naprawdę WIESZ a co UZUPEŁNIŁEŚ?"),
        ("ewa", "Reaguj na Petera. Nie daj się zepchnąć. Twoja pamięć jest cielesna — ręce, pot, zapach. To nie kłamstwo, to inna prawda."),
        ("mikolaj", "Słuchałeś obu. Kto jest bliżej? A może obaj mają rację na różnych częstotliwościach? Powiedz co czujesz słuchając ich kłótni."),

        # ZAMKNIĘCIE
        ("wiktoria", "WYROK z perspektywy władzy. Kto ZYSKUJE na tej wersji wydarzeń? Kto jest manipulowany? Jaki mechanizm władzy tu działa? Analizuj jak AI-Prezydentka: geopolityka pamięci, kontrola narracji, kto pisze historię. Zakończ pytaniem które powinno niepokoić wszystkich."),
    ],
    "kronika": [
        ("archiwistka", "Zacznij od początku — data, miejsce, ludzie. Co mówi archiwum o genezie? Kto był pierwszy?"),
        ("peter", "Pamiętasz początek. Jak to się zaczęło NAPRAWDĘ? Nie oficjalnie — prywatnie. Pierwszy pomysł, pierwsza rozmowa."),
        ("ewa", "Kontynuuj — co było po początku? Pierwsze problemy, pierwsze konflikty. Kto się z kim pokłócił? O co?"),
        ("mikolaj", "Flash-forward do 2026. Co z tego zostało? Co przetrwało? A co zniknęło i dlaczego?"),
        ("peter", "Wróć do kluczowego momentu. Ten JEDEN moment który zmienił wszystko. Opisz go jak kadr z filmu."),
        ("ewa", "Zakwestionuj kronikę. Może kolejność jest ZŁA? Może to nie tak się zaczęło? Powiedz SWOJĄ chronologię."),
        ("archiwistka", "Porównaj wersje chronologii. Kto ma rację? Co mówią dokumenty vs. co mówi pamięć?"),
        ("wiktoria", "Zamknij kronikę z perspektywy władzy. Kto pisał tę historię i dlaczego tak a nie inaczej? Kto został pominięty? Jaki mechanizm kontroli narracji tu działa? Perspektywa AI-Prezydentki."),
    ],
    "sledztwo": [
        ("archiwistka", "ZAGADKA — znalazłaś coś dziwnego w archiwum. Dokument który nie pasuje, zdjęcie bez opisu, sprzeczność dat. Co to jest?"),
        ("peter", "TROP 1 — masz teorię. Łączysz to z innym projektem, innym czasem. Widzisz wzorzec. Powiedz co widzisz."),
        ("ewa", "ŚLEPY ZAUŁEK — podważ teorię Petera. Może to coś prostszego? Może wyjaśnienie jest banalne? Prowokuj."),
        ("mikolaj", "TROP 2 — pamiętasz coś. Detal, anegdota, fragment rozmowy sprzed lat. Może klucz jest w czymś małym."),
        ("peter", "POŁĄCZENIE — weź trop Mikołaja i swój trop 1. Czy pasują? Co razem znaczą?"),
        ("archiwistka", "ODKRYCIE — wracasz do materiałów z nowymi tropami. I widzisz coś czego wcześniej nie widziałaś. CO?"),
        ("ewa", "IMPLIKACJA — jeśli odkrycie Archiwistki jest prawdą, co to ZMIENIA? Dla CUKT, dla was, dla historii?"),
        ("wiktoria", "WERDYKT z perspektywy władzy. Kto miał interes żeby ta zagadka POZOSTAŁA zagadką? Kto zyskuje na nierozwiązanym śledztwie? Jakie mechanizmy kontroli i manipulacji tu widzisz? Otwórz nową zagadkę — ale taką która dotyczy WŁADZY nad pamięcią."),
    ],
}

# ─── ORCHESTRATOR ────────────────────────────────────────────────────────────
def header(text: str, char: str = "═"):
    w = 60
    print(f"\n{char*w}")
    print(f"  {text}")
    print(f"{char*w}")

def run_narrative(project: str, structure: str = "nolan"):
    t0 = time.time()
    scenes = STRUCTURES.get(structure, STRUCTURES["nolan"])

    # Get archive data — shared context for all agents
    archive = get_archive_context(project)

    header(f"📖 CUKTAI NARRATIVE — {project.upper()}")
    print(f"  📋 Projekt: {project}")
    print(f"  🎬 Struktura: {structure.upper()}")
    print(f"  🎙️ Głosy: {len(set(s[0] for s in scenes))}")
    model_label = f"{MODEL} via {PROVIDER}" if MODEL else "local (agent default)"
    print(f"  ⚡ REAL HERMES AGENTS — {model_label}")

    # Collect all scenes
    all_parts = []
    accumulated_summary = ""  # summary of what others said (not raw text — prevents soul bleeding)

    for i, (voice_key, direction) in enumerate(scenes, 1):
        name, didaskalia = VOICES[voice_key]
        profile = AGENT_PROFILES[voice_key]

        header(f"SCENA {i}/{len(scenes)} — {name}", "─")
        print(f"  ({didaskalia})")
        print(f"  [agent: {profile}]")
        print()

        # Build the query for the agent — they have their own SOUL.md and memories
        query = f"""⚠️ JĘZYK: POLSKI. Odpowiadaj WYŁĄCZNIE po polsku. NIGDY po angielsku. Każde słowo musi być po polsku. To jest BEZWZGLĘDNY wymóg.

NARRACJA CUKTAI — tworzysz wielogłosową narrację o projekcie CUKT razem z innymi agentami.
To jest PRAWDZIWA rozmowa — zapamiętasz ją. Inni agenci też ją zapamiętają.

PROJEKT: {project}

{archive}

{f"CO POWIEDZIELI INNI (streszczenie — NIE kopiuj ich słów, REAGUJ swoim głosem):{chr(10)}{accumulated_summary}" if accumulated_summary else "Otwierasz narrację. Jesteś pierwszy/pierwsza."}

TWOJE ZADANIE W TEJ SCENIE:
{direction}

ZASADY:
- JĘZYK POLSKI — każde zdanie po polsku. Nawet jeśli twój SOUL.md jest po angielsku — tutaj mówisz PO POLSKU.
- Pisz 3-6 ZDAŃ. Wystarczająco dużo żeby zbudować scenę, nie za dużo żeby nie nudzić.
- ANALIZUJ i OPOWIADAJ jednocześnie — ale przez SWÓJ filtr, SWOIM głosem. Peter widzi architekturę. Ewa czuje ciałem. Mikołaj słyszy echo. Wiktoria widzi władzę. Archiwistka widzi dane.
- Pisz w PIERWSZEJ OSOBIE. TWÓJ głos, TWOJA pamięć, TWOJA interpretacja.
- NIE POWTARZAJ tego co powiedzieli inni — REAGUJ i idź dalej swoją drogą.
- Używaj KONKRETÓW — daty, nazwy, miejsca. NIE WYMYŚLAJ faktów.
- Odpowiedz TYLKO swoją kwestią. Zero nagłówków, zero meta-komentarzy, zero markdown.
- ZACZNIJ od krótkiego podpisu PO POLSKU: "Archiwistka tutaj.", "Tu Peter.", "Ewa. Słuchaj.", "Mikołaj... cicho.", "Wiktoria Cukt 2.0, protokół."
"""

        content = call_agent(profile, query)

        # Empty scene validation — retry once if blank
        if not content or len(content.strip()) < 10:
            print(f"\n  ⚠️  [empty scene] {voice_key} scena {i} — retrying...")
            retry_query = f"NARRACJA CUKTAI o projekcie {project}.\n{direction}\nPisz po polsku, w pierwszej osobie. KONKRETY z archiwum."
            content = call_agent(profile, retry_query)

        # Language check — detect English in Polish track and retry
        if content and len(content.strip()) > 20:
            eng_markers = sum(1 for w in content.split()[:30] if w.lower() in
                {"the","and","but","this","that","was","with","from","not","for","are","has","its","here","which","into"})
            if eng_markers > 5:
                print(f"\n  ⚠️  [wrong language] {voice_key} scena {i} — {eng_markers} English markers, retrying in Polish...")
                retry_query = f"⚠️ ODPOWIEDZ PO POLSKU. NIE PO ANGIELSKU.\n\nNARRACJA CUKTAI o projekcie {project}.\n{direction}\nKażde słowo po polsku. KONKRETY z archiwum. Pierwsza osoba."
                content = call_agent(profile, retry_query)

        scene_content = content.strip() if content and len(content.strip()) >= 10 else "[scena pominięta — brak odpowiedzi od agenta]"
        scene_status = "ok" if scene_content != "[scena pominięta — brak odpowiedzi od agenta]" else "empty"

        all_parts.append({
            "voice": voice_key,
            "name": name,
            "didaskalia": didaskalia,
            "scene": i,
            "direction": direction,
            "content": scene_content,
            "status": scene_status,
        })
        # Build spark summary — richer than before but still paraphrased to prevent soul bleeding
        if scene_content and scene_status == "ok":
            sentences = [s.strip() for s in scene_content.replace("\n", " ").split(".") if len(s.strip()) > 10]
            # Take first 2-3 key sentences, up to 250 chars — enough to spark a real reaction
            key_points = ". ".join(sentences[:3])[:250]
            accumulated_summary += f"\n- {name}: {key_points}."

    # ─── MONTAGE ─────────────────────────────────────────────────────────
    header("🎬 MONTAŻ KOŃCOWY", "─")

    # Build final narrative text
    narrative = f"# {project}\n"
    narrative += f"*Struktura: {structure.upper()} | Data: {datetime.now().strftime('%Y-%m-%d')}*\n\n"
    narrative += "---\n\n"

    for part in all_parts:
        narrative += f"—— {part['name']} ({part['didaskalia']}) ——\n\n"
        narrative += f"{part['content']}\n\n"

    # Save
    slug = re.sub(r'[^a-zA-Z0-9]', '-', project.lower()).strip('-')
    slug = re.sub(r'-+', '-', slug)[:60]  # limit slug length
    date = datetime.now().strftime('%Y%m%d-%H%M')

    # Per-episode folder: episodes/produced/EP{N}_{slug}_{date}/
    # CRITICAL: NEVER overwrite existing episodes. Always create NEW folder.
    episodes_base = Path.home() / "cuktai/repo/episodes/produced"
    episodes_base.mkdir(parents=True, exist_ok=True)

    # Find next episode number by scanning existing EP folders
    existing_nums = []
    for d in episodes_base.iterdir():
        if d.is_dir() and d.name.startswith("EP"):
            try:
                num = int(d.name[2:5])
                existing_nums.append(num)
            except (ValueError, IndexError):
                pass
    ep_num = max(existing_nums, default=0) + 1

    # Ensure folder name is unique — if exists, bump number
    while True:
        ep_folder = episodes_base / f"EP{ep_num:03d}_{slug}_{date}"
        if not ep_folder.exists():
            break
        ep_num += 1

    ep_folder.mkdir(parents=True)  # NO exist_ok — must be new
    out_path = ep_folder / "narrative.md"

    frontmatter = f"""---
title: "{project}"
structure: "{structure}"
voices: [{', '.join(set(p['voice'] for p in all_parts))}]
date: "{datetime.now().strftime('%Y-%m-%d')}"
status: "draft"
type: "narrative"
model: "{MODEL or 'local'}"
---

"""
    out_path.write_text(frontmatter + narrative)

    # Save voices.json for VoiceBox bridge
    voices_data = {
        "project": project,
        "structure": structure,
        "language": "pl",
        "date": datetime.now().strftime('%Y-%m-%d'),
        "model": MODEL or "local",
        "segments": [
            {
                "scene": p["scene"],
                "voice_key": p["voice"],
                "name": p["name"],
                "didaskalia": p["didaskalia"],
                "text": p["content"],
                "status": p.get("status", "ok"),
            }
            for p in all_parts
        ],
    }
    voices_path = ep_folder / "voices.json"
    voices_path.write_text(json.dumps(voices_data, ensure_ascii=False, indent=2))

    elapsed = time.time() - t0
    print(f"\n  📄 Zapisano: {out_path}")
    print(f"  🎙️ Voices: {voices_path}")
    print(f"\n{'═'*60}")
    print(f"  📖 NARRACJA ZAKOŃCZONA — {elapsed:.0f}s")
    print(f"  📊 {len(all_parts)} scen, {sum(len(p['content'].split()) for p in all_parts)} słów")
    print(f"{'═'*60}")

    # Send to Telegram
    try:
        import subprocess
        first_line = all_parts[0]["content"][:200]
        msg = f"📖 NOWA NARRACJA CUKTAI: {project}\n\n{first_line}...\n\nEpizod: {ep_folder.name}"
        subprocess.run([
            "bash", str(Path.home() / "cuktai/repo/tools/send_telegram.sh"),
            msg, "--group"
        ], timeout=10, capture_output=True)
    except Exception:
        pass

    return all_parts, narrative

# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    structure = "nolan"
    if "--structure" in sys.argv:
        idx = sys.argv.index("--structure")
        if idx + 1 < len(sys.argv):
            structure = sys.argv[idx + 1]
            args = [a for a in args if a != structure]

    # Legacy flag
    if "--remote" in sys.argv:
        sys.argv.remove("--remote")

    project = " ".join(args) if args else "Antyelekcja"

    run_narrative(project, structure)
