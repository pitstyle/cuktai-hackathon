"""
CUKTAI — Episode Publisher
Generates rich website content page from episode data.
Includes: full transcript, meta-connections, bilingual metadata.

Usage:
    python publish_episode.py /path/to/EP003_folder /path/to/website
"""

import json, sys, re, os
from pathlib import Path
from datetime import date

VOICE_DISPLAY = {
    "archiwistka": "Archiwistka",
    "ewa": "Ewa Virus",
    "peter": "Peter",
    "mikolaj": "Mikołaj",
    "wiktoria": "Wiktoria Cukt 2.0",
}

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def extract_transcript(voices_data):
    """Format transcript from voices.json segments."""
    lines = []
    for seg in voices_data.get("segments", []):
        if seg.get("status") != "ok":
            continue
        name = VOICE_DISPLAY.get(seg["voice_key"], seg["voice_key"])
        text = seg["text"].strip()
        # Remove agent self-identification prefixes (already in bold name)
        for prefix in ["Archiwistka tutaj.", "Archiwistka here.", "Tu Peter.", "Peter.",
                       "Ewa. Słuchaj.", "Ewa.", "Mikołaj...", "Mikołaj... cicho.",
                       "Wiktoria Cukt 2.0, protokół.", "Wiktoria Cukt 2.0, protocol."]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        lines.append(f"**{name}** — {text}")
    return "\n\n".join(lines)

def find_connections(ep_dir, website_dir):
    """Find meta-connections to other episodes."""
    podcasts_dir = website_dir / "src/content/podcasts"
    if not podcasts_dir.exists():
        return [], []

    # Current episode's project name
    voices = load_json(ep_dir / "voices.json") if (ep_dir / "voices.json").exists() else {}
    current_project = voices.get("project", "").lower()
    current_structure = voices.get("structure", "")

    connects_to = []
    all_archive_refs = set()

    for md_file in sorted(podcasts_dir.glob("EP*.md")):
        ep_name = md_file.stem
        # Skip self
        current_ep = ep_dir.name.split("_")[0]  # EP003
        if ep_name == current_ep:
            continue

        content = md_file.read_text(encoding="utf-8")

        # Extract frontmatter
        fm_match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not fm_match:
            continue
        fm = fm_match.group(1)

        # Check for project overlap
        # Look for shared archive_refs or title similarity
        title_match = re.search(r'title:\s*"([^"]*)"', fm)
        title = title_match.group(1) if title_match else ""

        refs_match = re.search(r'archive_refs:\s*\[(.*?)\]', fm)
        refs = refs_match.group(1) if refs_match else ""

        tags_match = re.search(r'tags:\s*\[(.*?)\]', fm)
        tags = tags_match.group(1) if tags_match else ""

        # Connection criteria: shared project references, shared CUKT themes
        connection_reasons = []

        # Project name appears in other episode
        if current_project and current_project in (title + refs + tags + content).lower():
            connection_reasons.append(f"shared project: {current_project}")

        # Extract other episode's archive refs for cross-referencing
        if refs:
            for ref in re.findall(r'"([^"]*)"', refs):
                all_archive_refs.add(ref)

        # CUKT-era overlap (both reference same era/events)
        cukt_keywords = ["technopera", "antyelekcja", "venom", "infomaja", "bytów", "cyborg",
                        "120h", "virus", "copyright", "dzień sztuki"]
        shared_keywords = [kw for kw in cukt_keywords
                          if kw in current_project and kw in (title + tags).lower()]
        if shared_keywords:
            connection_reasons.append(f"shared theme: {', '.join(shared_keywords)}")

        # All episodes connect via the CUKTAI system itself
        if not connection_reasons:
            connection_reasons.append("CUKTAI multivoice system")

        connects_to.append(ep_name)

    return connects_to, list(all_archive_refs)

def generate_tags(voices_data, current_project):
    """Generate content-aware tags from the episode."""
    tags = set(["CUKTAI"])

    # Structure as tag
    structure = voices_data.get("structure", "")
    if structure:
        tags.add(structure)

    # Project name keywords — only proper nouns and key terms
    skip_words = {"cukt", "cuktai", "projekt", "dlaczego", "czyli", "jako", "przez",
                  "przy", "gdzie", "kiedy", "kogo", "czym", "tego", "jest", "były",
                  "było", "były", "będzie", "tylko", "sfałszował", "wybory"}
    for word in re.split(r'[\s\-_]+', current_project):
        word = re.sub(r'[^a-ząćęłńóśźż0-9]', '', word.strip().lower())
        if len(word) > 4 and word not in skip_words:
            tags.add(word)

    # Scan content for era/theme tags
    all_text = " ".join(seg["text"] for seg in voices_data.get("segments", []))
    era_tags = {
        "1990s": r"199[0-9]",
        "1980s": r"198[0-9]",
        "2000s": r"200[0-9]",
        "performance": r"performan|akcj|instalac",
        "archive": r"archiwum|archiv|teczk",
        "memory": r"pamięć|wspomnie|remember|memory",
        "politics": r"polity|władz|elekcj|power|control",
        "technology": r"technolog|cyber|system|protocol",
        "identity": r"tożsamo|identity|persona",
    }
    for tag, pattern in era_tags.items():
        if re.search(pattern, all_text, re.IGNORECASE):
            tags.add(tag)

    return sorted(tags)

def generate_page(ep_dir, website_dir, structure=""):
    """Generate the full content page."""
    ep_dir = Path(ep_dir)
    website_dir = Path(website_dir)

    # Load data
    voices_pl = load_json(ep_dir / "voices_pl.json") if (ep_dir / "voices_pl.json").exists() else load_json(ep_dir / "voices.json")
    voices_en = load_json(ep_dir / "voices_en.json") if (ep_dir / "voices_en.json").exists() else None

    project = voices_pl.get("project", "Unknown")
    structure = structure or voices_pl.get("structure", "unknown")
    ep_name = ep_dir.name
    ep_num = re.search(r'EP(\d+)', ep_name)
    ep_num_str = f"EP{ep_num.group(1).zfill(3)}" if ep_num else ep_name.split("_")[0]
    ep_int = int(ep_num.group(1)) if ep_num else 0

    # Transcripts
    transcript_pl = extract_transcript(voices_pl)
    transcript_en = extract_transcript(voices_en) if voices_en else ""

    # Meta-connections
    connects_to, cross_refs = find_connections(ep_dir, website_dir)
    tags = generate_tags(voices_pl, project)

    # Duration from mp3
    dur_pl = dur_en = ""
    pl_mp3 = ep_dir / "episode_pl.mp3"
    en_mp3 = ep_dir / "episode_en.mp3"
    if pl_mp3.exists():
        secs = pl_mp3.stat().st_size * 8 / 128000
        dur_pl = f"{int(secs)//60}:{int(secs)%60:02d}"
    if en_mp3.exists():
        secs = en_mp3.stat().st_size * 8 / 128000
        dur_en = f"{int(secs)//60}:{int(secs)%60:02d}"

    voices_list = list(dict.fromkeys(seg["voice_key"] for seg in voices_pl.get("segments", [])))

    # Build frontmatter
    fm_lines = [
        f'title: "{project}"',
        f'episode: {ep_int}',
        f'date: "{date.today().isoformat()}"',
        f'structure: {structure}',
        f'duration_pl: "{dur_pl}"',
        f'duration_en: "{dur_en}"',
        f'audio_pl: "/audio/episodes/{ep_num_str}_pl.mp3"',
        f'audio_en: "/audio/episodes/{ep_num_str}_en.mp3"',
        f'voices: [{", ".join(voices_list)}]',
        f'archive_refs: ["{project}"]',
    ]
    if connects_to:
        fm_lines.append(f'connects_to: [{", ".join(f"{c}" for c in connects_to)}]')
    fm_lines.extend([
        f'tags: [{", ".join(f"{t}" for t in tags)}]',
        f'description: "CUKTAI multivoice narration — {structure} structure, {len(voices_list)} voices."',
    ])

    frontmatter = "---\n" + "\n".join(fm_lines) + "\n---"

    # Build body
    body_parts = ["\n## Transcript (PL)\n", transcript_pl]
    if transcript_en:
        body_parts.extend(["\n\n## Transcript (EN)\n", transcript_en])

    # Connection footer
    if connects_to:
        body_parts.append("\n\n## Connected Episodes\n")
        for conn in connects_to:
            body_parts.append(f"- [{conn}](/podcasts/{conn}/)")

    page = frontmatter + "\n" + "\n".join(body_parts) + "\n"

    # Write
    out_path = website_dir / f"src/content/podcasts/{ep_num_str}.md"
    out_path.write_text(page, encoding="utf-8")
    print(f"Published: {out_path}")
    print(f"  Project: {project}")
    print(f"  Transcript PL: {len(transcript_pl)} chars")
    print(f"  Transcript EN: {len(transcript_en)} chars")
    print(f"  Tags: {tags}")
    print(f"  Connects to: {connects_to}")
    return out_path

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python publish_episode.py /path/to/EP_folder /path/to/website [structure]")
        sys.exit(1)

    ep_dir = sys.argv[1]
    website_dir = sys.argv[2]
    structure = sys.argv[3] if len(sys.argv) > 3 else ""
    generate_page(ep_dir, website_dir, structure)
