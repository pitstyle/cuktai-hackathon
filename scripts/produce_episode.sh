#!/bin/bash
# CUKTAI — Full Episode Production Pipeline
# Autonomous episode production — runs from terminal (Hermes skill or cron)
#
# Usage:
#   ./produce_episode.sh "Przebudzenie Petera" rashomon
#   ./produce_episode.sh "120h Mega Techno" nolan
#   ./produce_episode.sh --tts-only /path/to/EP_folder  # skip narrate+translate
#
# Pipeline: narrate → translate → TTS (PL+EN) → metadata → notify
# Requirements: VoiceBox on localhost:17493, DeepSeek API key, ffmpeg

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# ─── HELPERS ─────────────────────────────────────────────────────
kill_llama_server() {
    # Kill ALL llama-server processes — try SIGTERM first, then SIGKILL
    if pgrep -f "llama-server" > /dev/null 2>&1; then
        echo "  Stopping llama-server..."
        pkill -f "llama-server" 2>/dev/null || true
        sleep 3
        # Force kill if still alive
        if pgrep -f "llama-server" > /dev/null 2>&1; then
            pkill -9 -f "llama-server" 2>/dev/null || true
            sleep 2
        fi
        pgrep -f "llama-server" > /dev/null 2>&1 && echo "  ⚠️  llama-server still alive!" || echo "  llama-server stopped"
    else
        echo "  llama-server not running — GPU free"
    fi
}

start_llama_server() {
    echo "  Starting llama-server..."
    nohup /home/macstorm/llama.cpp/build/bin/llama-server \
        -m /home/macstorm/models/Qwen3.5-35B-A3B-IQ3_S-3.26bpw.gguf \
        --host 0.0.0.0 --port 11435 -ngl 99 -c 98304 --parallel 1 \
        --jinja --reasoning-budget 0 > /tmp/llama.log 2>&1 &
    echo "  llama-server PID: $!"
}

restart_voicebox() {
    echo "  Restarting VoiceBox..."
    curl -s -X POST "http://localhost:17493/shutdown" 2>/dev/null || true
    sleep 4

    # Kill any remaining VoiceBox processes
    pkill -f "backend.main.*17493" 2>/dev/null || true
    sleep 2

    cd /home/macstorm/voicebox
    source backend/venv/bin/activate
    export HSA_OVERRIDE_GFX_VERSION=10.3.0
    export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
    nohup python -m backend.main --host 0.0.0.0 --port 17493 >> /home/macstorm/voicebox/voicebox.log 2>&1 &

    # Wait for ready
    for i in $(seq 1 30); do
        sleep 2
        if curl -s "http://localhost:17493/health" > /dev/null 2>&1; then
            echo "  VoiceBox ready"
            return 0
        fi
    done
    echo "  ❌ VoiceBox failed to start!"
    return 1
}

# ─── PARSE ARGS ──────────────────────────────────────────────────
MODE="full"
TOPIC="${1:-}"
STRUCTURE="${2:-rashomon}"
MODEL="${NARRATE_MODEL:-deepseek/deepseek-v4-flash}"
EP_DIR=""

if [ "$TOPIC" = "--tts-only" ]; then
    MODE="tts-only"
    EP_DIR="${2:-}"
    if [ -z "$EP_DIR" ] || [ ! -d "$EP_DIR" ]; then
        echo "❌ --tts-only requires episode folder path"
        exit 1
    fi
fi

if [ "$MODE" = "full" ] && [ -z "$TOPIC" ]; then
    echo "Usage: produce_episode.sh \"Topic\" [rashomon|nolan|kronika|sledztwo]"
    echo "       produce_episode.sh --tts-only /path/to/EP_folder"
    exit 1
fi

echo '═══════════════════════════════════════════════════════════'
echo '  🎬 CUKTAI FULL EPISODE PRODUCTION'
echo "  Mode: $MODE"
echo '═══════════════════════════════════════════════════════════'

# ─── STEP 1: Narrate (Polish) ────────────────────────────────────
if [ "$MODE" = "full" ]; then
    echo ''
    echo '━━━ STEP 1: NARRATIVE (Polish) ━━━'
    cd "$REPO_DIR"
    python3 "$SCRIPT_DIR/narrate_orchestrator.py" --model "$MODEL" --structure "$STRUCTURE" "$TOPIC"

    # Find the episode folder just created (newest EP folder)
    EP_DIR=$(ls -td "$REPO_DIR/episodes/produced/EP"* 2>/dev/null | head -1)
    if [ -z "$EP_DIR" ]; then
        echo '❌ No episode folder found after narration'
        exit 1
    fi
    echo "  📂 Episode: $EP_DIR"

    # ─── STEP 2: Translate to English ────────────────────────────
    echo ''
    echo '━━━ STEP 2: TRANSLATE (Polish → English) ━━━'
    cd "$REPO_DIR"
    python3 "$SCRIPT_DIR/translate_episode.py" "$EP_DIR"
fi

echo "  📂 Working on: $EP_DIR"

# ─── STEP 3: TTS — Polish audio ─────────────────────────────────
echo ''
echo '━━━ STEP 3: TTS — POLISH AUDIO ━━━'

kill_llama_server
restart_voicebox

# Find Polish voices file
cd "$REPO_DIR"
PL_VOICES="$EP_DIR/voices_pl.json"
[ ! -f "$PL_VOICES" ] && PL_VOICES="$EP_DIR/voices.json"

if [ ! -f "$PL_VOICES" ]; then
    echo "❌ No voices file found in $EP_DIR"
    start_llama_server
    exit 1
fi

echo "  Using: $PL_VOICES"
VOICEBOX_URL="http://localhost:17493" VOICEBOX_ENGINE="chatterbox" \
    python3 "$SCRIPT_DIR/voicebox_generate.py" "$PL_VOICES"

# Rename output
[ -f "$EP_DIR/episode.mp3" ] && mv "$EP_DIR/episode.mp3" "$EP_DIR/episode_pl.mp3" && echo "  ✅ episode_pl.mp3"

# ─── STEP 4: TTS — English audio ────────────────────────────────
echo ''
echo '━━━ STEP 4: TTS — ENGLISH AUDIO ━━━'

EN_VOICES="$EP_DIR/voices_en.json"
if [ -f "$EN_VOICES" ]; then
    # Clear audio cache (different text = different audio)
    rm -f "$EP_DIR/audio"/scene_*.wav "$EP_DIR/audio"/scene_*.hash 2>/dev/null

    restart_voicebox

    cd "$REPO_DIR"
    VOICEBOX_URL="http://localhost:17493" VOICEBOX_ENGINE="chatterbox" \
        python3 "$SCRIPT_DIR/voicebox_generate.py" "$EN_VOICES"

    [ -f "$EP_DIR/episode.mp3" ] && mv "$EP_DIR/episode.mp3" "$EP_DIR/episode_en.mp3" && echo "  ✅ episode_en.mp3"
else
    echo '  ⚠️  No voices_en.json — skipping English audio'
fi

# ─── STEP 5: Free GPU + Restart llama-server ────────────────────
echo ''
echo '━━━ STEP 5: CLEANUP ━━━'
echo '  Shutting down VoiceBox (free GPU for llama-server)...'
curl -s -X POST "http://localhost:17493/shutdown" 2>/dev/null || true
sleep 2
pkill -f "backend.main.*17493" 2>/dev/null || true
sleep 3
start_llama_server

# ─── STEP 6: Publish to website ──────────────────────────────────
echo ''
echo '━━━ STEP 6: PUBLISH TO WEBSITE ━━━'
EP_NAME=$(basename "$EP_DIR")
WEBSITE_DIR="/home/macstorm/cukt-website"

if [ -d "$WEBSITE_DIR" ]; then
    # Get episode number from folder name
    EP_NUM=$(echo "$EP_NAME" | grep -oP 'EP\d+' | head -1)

    # Copy audio files
    mkdir -p "$WEBSITE_DIR/public/audio/episodes"
    [ -f "$EP_DIR/episode_pl.mp3" ] && cp "$EP_DIR/episode_pl.mp3" "$WEBSITE_DIR/public/audio/episodes/${EP_NUM}_pl.mp3"
    [ -f "$EP_DIR/episode_en.mp3" ] && cp "$EP_DIR/episode_en.mp3" "$WEBSITE_DIR/public/audio/episodes/${EP_NUM}_en.mp3"

    # Generate content page with full transcript + meta-connections
    python3 "$SCRIPT_DIR/publish_episode.py" "$EP_DIR" "$WEBSITE_DIR" "$STRUCTURE" \
        && echo "  ✅ Content page created"

    # Git commit and push
    cd "$WEBSITE_DIR"
    git add -A
    git commit -m "publish: ${EP_NUM} — ${TOPIC:-auto-produced episode}" --no-verify 2>/dev/null
    git push 2>/dev/null && echo "  ✅ Website pushed"

    # Trigger Render deploy
    curl -s -X POST -H "Authorization: Bearer rnd_lo8UPnqcVHaC5zvF8qGC6EawPToN" \
        "https://api.render.com/v1/services/srv-d7kfccvlk1mc73cufph0/deploys" \
        -H "Content-Type: application/json" -d '{"clearCache":"do_not_clear"}' > /dev/null 2>&1 \
        && echo "  ✅ Render deploy triggered"
else
    echo "  ⚠️  Website dir not found — skipping publish"
fi

# ─── STEP 7: Notify ─────────────────────────────────────────────
echo ''
echo '━━━ STEP 7: NOTIFY ━━━'
bash "$REPO_DIR/tools/send_telegram.sh" \
    "🎬 NOWY EPIZOD CUKTAI: ${TOPIC:-$EP_NAME}

📂 $EP_NAME
🇵🇱 episode_pl.mp3
🇬🇧 episode_en.mp3
🎙️ 5 głosów, struktura: ${STRUCTURE}
🌐 https://cukt.click/podcasts/${EP_NUM}/" --group 2>/dev/null || true

# ─── DONE ────────────────────────────────────────────────────────
echo ''
echo '═══════════════════════════════════════════════════════════'
echo "  🎉 EPISODE COMPLETE: $EP_NAME"
echo "  📂 $EP_DIR"
echo ''
ls -lh "$EP_DIR/"*.mp3 "$EP_DIR/"*.md "$EP_DIR/"*.json 2>/dev/null
echo ''
echo '═══════════════════════════════════════════════════════════'
