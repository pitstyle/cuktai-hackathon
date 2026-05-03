"""
CUKTAI — Episode Translator
Translates Polish narrative to English while preserving voice structure.
Uses DeepSeek API (OpenAI-compatible) for translation.

Usage:
    python3 translate_episode.py episodes/produced/EP001_slug/
"""
import os, sys, json, re
from pathlib import Path

DEEPSEEK_API_KEY = os.environ['DEEPSEEK_API_KEY']
DEEPSEEK_URL = 'https://api.deepseek.com/v1/chat/completions'

def translate_text(text, voice_key, context=''):
    """Translate Polish text to English, preserving character voice."""
    import subprocess
    
    voice_instructions = {
        'archiwistka': 'Dry, factual, radio protocol style. Keep "Over" at end.',
        'peter': 'Intellectual, architectural thinking, occasional swearing (fuck, damn).',
        'ewa': 'Raw, confrontational, swears heavily (fuck, shit). Keep "Voilà" untranslated.',
        'mikolaj': 'Poetic, fragmentary, introspective, gentle.',
        'wiktoria': 'Formal, institutional, decree-like. Keep legal terminology precise.',
    }
    
    style = voice_instructions.get(voice_key, 'Direct translation.')
    
    prompt = f"""Translate this Polish text to English. Output ONLY the English translation, nothing else.

CHARACTER: {voice_key} — {style}

CRITICAL RULES:
- Output ONLY English text. No Polish words. No diacritics. No meta-commentary.
- Names without diacritics: Piotr (not Piotr), Mikolaj (not Mikołaj), Gdansk (not Gdańsk)
- Keep "Voila" (no accent) and CUKT/CUKTAI as-is
- Natural spoken English. Same length as original.
- Swear words in English (fuck, shit, damn)
- DO NOT write "Here's the translation" or any prefix — ONLY the translated text
- DO NOT keep any Polish sentences or phrases

TEXT TO TRANSLATE:
{text}"""

    payload = json.dumps({
        'model': 'deepseek-chat',
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.3,
        'max_tokens': 1000,
    })
    
    result = subprocess.run(
        ['curl', '-s', '-X', 'POST', DEEPSEEK_URL,
         '-H', f'Authorization: Bearer {DEEPSEEK_API_KEY}',
         '-H', 'Content-Type: application/json',
         '-d', payload],
        capture_output=True, text=True, timeout=30
    )
    
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            if 'choices' in data:
                text_out = data['choices'][0]['message']['content'].strip()
                # Clean up any meta-commentary the model might add
                for prefix in ['Here\'s the translation:', 'Here is the translation:',
                               'Translation:', 'English translation:', 'English:']:
                    if text_out.lower().startswith(prefix.lower()):
                        text_out = text_out[len(prefix):].strip()
                # Remove any remaining Polish diacritics
                for pl, en in [('ą','a'),('ę','e'),('ó','o'),('ś','s'),('ź','z'),('ż','z'),('ć','c'),('ł','l'),('ń','n'),('Ą','A'),('Ę','E'),('Ó','O'),('Ś','S'),('Ź','Z'),('Ż','Z'),('Ć','C'),('Ł','L'),('Ń','N')]:
                    text_out = text_out.replace(pl, en)
                return text_out
            elif 'error' in data:
                print(f"API error: {data['error'].get('message', data['error'])}")
                return None
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Parse error: {e}")
            return None
    print(f"curl failed: {result.stderr[:200] if result.stderr else 'no error output'}")
    return None


def translate_episode(ep_dir):
    """Translate an entire episode from Polish to English."""
    ep_path = Path(ep_dir)
    
    # Read Polish voices.json
    voices_pl = ep_path / 'voices.json'
    if not voices_pl.exists():
        print(f'No voices.json in {ep_dir}')
        return
    
    data = json.loads(voices_pl.read_text())
    
    print(f'Translating: {data["project"]}')
    print(f'Segments: {len(data["segments"])}')
    
    # Translate each segment
    en_segments = []
    for seg in data['segments']:
        if seg.get('status') == 'empty':
            en_segments.append(seg)
            continue
        
        print(f'  {seg["voice_key"]}... ', end='', flush=True)
        en_text = translate_text(seg['text'], seg['voice_key'])
        if en_text:
            en_seg = dict(seg)
            en_seg['text'] = en_text
            en_segments.append(en_seg)
            print(f'OK ({len(en_text)} chars)')
        else:
            print('FAILED — keeping Polish')
            en_segments.append(seg)
    
    # Save English voices.json
    en_data = dict(data)
    en_data['segments'] = en_segments
    en_data['language'] = 'en'
    
    voices_en = ep_path / 'voices_en.json'
    voices_en.write_text(json.dumps(en_data, ensure_ascii=False, indent=2))
    
    # Save English narrative markdown
    narrative_en = ep_path / 'narrative_en.md'
    md_parts = [f'# {data["project"]} (English)\n']
    md_parts.append(f'*Structure: {data.get("structure", "?")} | Translated from Polish*\n\n---\n')
    for seg in en_segments:
        md_parts.append(f'—— {seg["name"]} ({seg.get("didaskalia", "")}) ——\n')
        md_parts.append(f'{seg["text"]}\n')
    narrative_en.write_text('\n'.join(md_parts))
    
    # Rename original to _pl
    narrative_orig = ep_path / 'narrative.md'
    narrative_pl = ep_path / 'narrative_pl.md'
    if narrative_orig.exists() and not narrative_pl.exists():
        narrative_orig.rename(narrative_pl)
    
    voices_orig = ep_path / 'voices.json'
    voices_pl_new = ep_path / 'voices_pl.json'
    if not voices_pl_new.exists():
        import shutil
        shutil.copy2(str(voices_orig), str(voices_pl_new))
    
    print(f'\nSaved: {voices_en}')
    print(f'Saved: {narrative_en}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python3 translate_episode.py <episode_dir>')
        sys.exit(1)
    translate_episode(sys.argv[1])
