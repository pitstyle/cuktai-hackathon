#!/usr/bin/env python3
"""
CUKTAI Relay — Demo performance driver with integrated TTS.

Orchestrates multivoice narration in #zebranie.
Each agent responds through its FULL Hermes gateway (SOUL + memory + tools).
The relay controls turn order AND generates TTS audio (Chatterbox).

Flow per agent turn:
  1. @mention agent with prompt
  2. Wait for agent's text response in #zebranie
  3. Generate TTS with Chatterbox (voice-cloned, ~3s)
  4. Play audio through speakers
  5. Advance to next agent

No separate watcher needed. Text and voice stay perfectly synced.

Usage:
    python3 relay.py --demo --topic "Konin 1994. The honey vessel."
    python3 relay.py --demo --topic "Konin" --no-tts   # text only
"""

import discord
import asyncio
import argparse
import json
import os
import sys
import time
import threading
import struct
import wave
import tempfile
import urllib.request
from pathlib import Path
from datetime import datetime

# ===== CONFIGURATION =====
ZEBRANIE_CHANNEL_ID = 1498730532786274627
GUILD_ID = 1498729936318501054

RELAY_TOKEN = os.environ["RELAY_DISCORD_TOKEN"]

AGENT_BOTS = {
    "archiwistka": 1498737189369155695,
    "ewa":         1498733947570360662,
    "mikolaj":     1498735206637502524,
    "peter":       1498731338755342428,
    "wiktoria":    1498736245159760054,
}

SPEAKERS = ["ewa", "mikolaj", "peter", "wiktoria"]
ALL_AGENTS = ["archiwistka"] + SPEAKERS

# TTS config — ElevenLabs
ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICES = {
    "archiwistka": "6jIXNafyulNoo03Englu",
    "peter":       "lmlareIiLb95CteG2Uuw",
    "mikolaj":     "7DbVpVRMIlUzzdoIRztC",
    "ewa":         "ncCMWuRuTZUNrqOtMzPY",
    "wiktoria":    "g4D2XpDcxrPmfZiuvKBC",
}
ELEVENLABS_MODEL = "eleven_flash_v2_5"
AUDIO_OUT_DIR = Path(__file__).parent.parent / "episodes" / "live-audio"

NO_TTS = "--no-tts" in sys.argv

# Voice input config — local MLX Whisper on Apple Silicon
os.environ.setdefault("HF_TOKEN", os.environ.get("HF_TOKEN", ""))
VOICE_INPUT = "--voice" in sys.argv
MIC_SAMPLE_RATE = 16000
MIC_SILENCE_THRESHOLD = 800   # RMS threshold for silence detection (raised to filter ambient)
MIC_SILENCE_DURATION = 1.5    # seconds of silence to stop recording
MIC_MIN_DURATION = 0.5        # minimum recording length (skip noise)
WHISPER_MODEL = "mlx-community/whisper-small-mlx"  # fast on M1 Max

# TouchDesigner relay endpoint
TD_RELAY_URL = "http://localhost:9980"

def send_to_td(agent_name, text):
    """POST agent text to TouchDesigner for live display."""
    try:
        payload = json.dumps({"agent": agent_name, "text": text}).encode()
        req = urllib.request.Request(
            f"{TD_RELAY_URL}/text",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST")
        resp = urllib.request.urlopen(req, timeout=2)
        print(f"[TD] Sent {agent_name} ({len(text)} chars) → {resp.status}")
    except Exception as e:
        print(f"[TD] Error: {e}")

def clear_td():
    """Clear TouchDesigner display."""
    try:
        data = json.dumps({}).encode()
        req = urllib.request.Request(
            f"{TD_RELAY_URL}/clear",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST")
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass

# =========================


def record_until_silence():
    """Record from mic until silence detected. Returns WAV bytes or None."""
    import sounddevice as sd
    import numpy as np

    frames = []
    silence_frames = 0
    silence_limit = int(MIC_SILENCE_DURATION * MIC_SAMPLE_RATE / 1024)
    recording = False
    speech_frames = 0

    print("[MIC] Listening... (speak now)", flush=True)

    def callback(indata, frame_count, time_info, status):
        nonlocal silence_frames, recording, speech_frames
        rms = np.sqrt(np.mean(indata ** 2)) * 32768
        if rms > MIC_SILENCE_THRESHOLD:
            recording = True
            silence_frames = 0
            speech_frames += 1
        elif recording:
            silence_frames += 1
        frames.append(indata.copy())

    with sd.InputStream(samplerate=MIC_SAMPLE_RATE, channels=1, dtype='float32',
                        blocksize=1024, callback=callback):
        # Wait for speech to start (max 30s)
        t0 = time.time()
        while not recording and time.time() - t0 < 30:
            time.sleep(0.05)
        if not recording:
            print("[MIC] No speech detected (30s timeout)")
            return None

        # Record until silence
        while silence_frames < silence_limit and time.time() - t0 < 120:
            time.sleep(0.05)

    if speech_frames < int(MIC_MIN_DURATION * MIC_SAMPLE_RATE / 1024):
        print("[MIC] Too short, skipping")
        return None

    # Convert to WAV bytes
    import numpy as np
    audio = np.concatenate(frames)
    audio_int16 = (audio * 32767).astype(np.int16)

    wav_buf = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    with wave.open(wav_buf.name, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(MIC_SAMPLE_RATE)
        wf.writeframes(audio_int16.tobytes())

    duration = len(audio) / MIC_SAMPLE_RATE
    print(f"[MIC] Recorded {duration:.1f}s")
    return wav_buf.name


def transcribe_audio(wav_path):
    """Transcribe WAV locally using MLX Whisper on Apple Silicon."""
    try:
        import mlx_whisper
        result = mlx_whisper.transcribe(
            wav_path,
            path_or_hf_repo=WHISPER_MODEL,
            language="en",
        )
        os.unlink(wav_path)
        text = result.get("text", "").strip()
        if text:
            print(f"[STT] \"{text}\"")
            return text
    except Exception as e:
        print(f"[STT] Error: {e}")
    return None


def load_tts():
    """Check ElevenLabs API key."""
    if NO_TTS:
        print("[TTS] Disabled (--no-tts)")
        return
    AUDIO_OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[TTS] ElevenLabs ({ELEVENLABS_MODEL}) — {len(ELEVENLABS_VOICES)} voices ready")


def speak(agent_name, text):
    """Generate TTS via ElevenLabs streaming API. Blocks until playback finishes."""
    if NO_TTS:
        return

    import subprocess
    import tempfile

    voice_id = ELEVENLABS_VOICES.get(agent_name)
    if not voice_id:
        print(f"[TTS] No voice for {agent_name}")
        return

    # Cap text — generous limit to preserve storytelling
    tts_text = text[:400]
    if len(text) > 400:
        for end in ['. ', '! ', '? ']:
            idx = tts_text.rfind(end)
            if idx > 200:
                tts_text = tts_text[:idx + 1]
                break

    print(f"[TTS] {agent_name.upper()} ({len(tts_text)} chars)...", end="", flush=True)
    t0 = time.time()

    try:
        # ElevenLabs streaming TTS API
        ts = datetime.now().strftime("%H%M%S")
        out_file = str(AUDIO_OUT_DIR / f"{ts}_{agent_name}.mp3")

        result = subprocess.run(
            ["curl", "-s",
             "-X", "POST",
             f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
             "-H", f"xi-api-key: {ELEVENLABS_API_KEY}",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({
                 "text": tts_text,
                 "model_id": ELEVENLABS_MODEL,
                 "voice_settings": {
                     "stability": 0.5,
                     "similarity_boost": 0.75,
                 }
             }),
             "-o", out_file],
            capture_output=True, text=True, timeout=30
        )

        if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
            # Play audio — blocks until done
            subprocess.run(["afplay", out_file], timeout=120)
            print(f" done ({time.time()-t0:.1f}s)")
        else:
            print(f" ERROR: empty audio file")
            if result.stderr:
                print(f"  {result.stderr[:200]}")
    except Exception as e:
        print(f" ERROR: {e}")


# ===== DISCORD CLIENT =====

class CUKTAIRelay(discord.Client):
    def __init__(self, topic=None, max_rounds=2, demo=False, test_mode=False, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        super().__init__(intents=intents, **kwargs)

        self.topic = topic
        self.max_rounds = max_rounds
        self.demo = demo
        self.test_mode = test_mode
        self.zebranie = None
        self.waiting_for = None
        self.response_event = asyncio.Event()
        self.last_response = None
        self.conversation_log = []
        self.piotr_message = None
        self.piotr_event = asyncio.Event()
        # Prefetch: pending responses keyed by agent name
        self.pending_responses = {}  # {agent_name: asyncio.Future}
        self.pending_relay_msgs = {}  # {agent_name: discord.Message}
        # Freedom round: queue for unstructured agent responses
        self.freedom_mode = False
        self.freedom_queue = asyncio.Queue()
        self._freedom_responded = set()  # agents who already responded this broadcast

    async def on_ready(self):
        print(f"[RELAY] Connected as {self.user}")
        self.zebranie = self.get_channel(ZEBRANIE_CHANNEL_ID)
        if not self.zebranie:
            print(f"[RELAY] ERROR: Cannot find #zebranie")
            return
        print(f"[RELAY] Watching #{self.zebranie.name}\n")

        # Voice input is now gated — only active during _wait_for_piotr()
        # No background listener to avoid mic picking up agent TTS
        if VOICE_INPUT:
            print("[VOICE] Mic gated — only active when waiting for Piotr")

        if self.test_mode and self.topic:
            await asyncio.sleep(2)
            await self.run_test()
        elif self.demo:
            await asyncio.sleep(2)
            await self.run_demo()
        elif self.topic:
            await asyncio.sleep(2)
            await self.run_autonomous()

    async def _voice_input_loop(self):
        """Background loop: listen for Piotr's voice, transcribe, post to Discord."""
        print("[VOICE] Voice input active — mic gated (only between phases)")
        # Pre-load Whisper model (first transcription downloads/caches it)
        print("[VOICE] Whisper model will load on first speech")
        self.mic_open = True  # Gate flag — set False during agent speech

        while True:
            try:
                # Wait for mic to be open
                if not getattr(self, 'mic_open', True):
                    await asyncio.sleep(0.3)
                    continue
                # Record in thread (blocking)
                wav_path = await asyncio.to_thread(record_until_silence)
                if wav_path:
                    # Transcribe in thread
                    text = await asyncio.to_thread(transcribe_audio, wav_path)
                    if text and len(text) > 2:
                        # Send to TouchDesigner + Discord
                        send_to_td("piotr", text)
                        await self.zebranie.send(f"**Piotr:** {text}")
                        # Also trigger the piotr event for relay logic
                        self.piotr_message = text
                        self.piotr_event.set()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[VOICE] Error: {e}")
                await asyncio.sleep(1)

    async def on_message(self, message):
        if message.author.id == self.user.id:
            return
        if message.channel.id != ZEBRANIE_CHANNEL_ID:
            return

        self.log_message(message)

        # Human message
        if not message.author.bot:
            self.piotr_message = message.content
            self.piotr_event.set()
            print(f"[RELAY] Piotr: {message.content[:100]}")
            return

        # Delete Hermes session/system noise from Discord
        _noise = ("Session automatically reset", "/resume", "/sethome",
                  "No home channel", "Model:", "Provider:", "Context:",
                  "Context too large", "compression", "auto-reset",
                  "Session auto-reset", "context size", "Use /resume",
                  "Adjust reset timing", "config.yaml")
        if message.author.bot and any(n in message.content for n in _noise):
            print(f"[RELAY] Deleting noise from {message.author.name}: {message.content[:60]}")
            try:
                await message.delete()
            except Exception:
                pass
            return

        # Delete tool-call status messages (⚙️ mcp_*, thinking indicators)
        if message.author.bot and message.content.startswith(
                ("⚙️", "⏱️", "⏳", "⚡", "⚠️", "❌", "📬", "✨", "◐", "◆", "🗜️", "🔄")):
            print(f"[RELAY] Deleting status from {message.author.name}: {message.content[:60]}")
            try:
                await message.delete()
            except Exception:
                pass
            return

        # Bot message — check if it's who we're waiting for
        # Check prefetch futures first
        for agent_name, fut in list(self.pending_responses.items()):
            expected_id = AGENT_BOTS.get(agent_name)
            if message.author.id == expected_id and not fut.done():
                if message.content.startswith(("⚙️", "⏱️", "⏳", "⚡", "⚠️", "❌", "📬", "✨", "◐", "◆", "🗜️", "🔄")):
                    return
                fut.set_result(message.content)
                print(f"[RELAY] {agent_name} responded ({len(message.content)} chars) [prefetch]")
                return

        # Freedom mode — queue agent responses for TTS (one per agent per broadcast)
        if self.freedom_mode and message.author.bot:
            agent_name = self.get_agent_name(message.author.id)
            if agent_name:
                # Skip empty messages
                if not message.content or len(message.content.strip()) < 5:
                    print(f"[FREEDOM] Skipping empty from {agent_name}")
                    return
                # Deduplicate: only first response per agent per broadcast
                if agent_name in self._freedom_responded:
                    print(f"[FREEDOM] Skipping duplicate from {agent_name}")
                    return
                self._freedom_responded.add(agent_name)
                print(f"[FREEDOM] {agent_name} responded ({len(message.content)} chars)")
                self.freedom_queue.put_nowait((agent_name, message.content))
                return

        if self.waiting_for:
            expected_id = AGENT_BOTS.get(self.waiting_for)
            if message.author.id == expected_id:
                if message.content.startswith(("⚙️", "⏱️", "⏳", "⚡", "⚠️", "❌", "📬", "✨", "◐", "◆", "🗜️", "🔄")):
                    return
                self.last_response = message.content
                self.response_event.set()
                print(f"[RELAY] {self.waiting_for} responded ({len(message.content)} chars)")

    # ─── CORE: send, wait, speak ─────────────────────────────

    async def ask_agent(self, agent_name, prompt, timeout=90):
        """@mention agent → wait for response → TTS → play audio."""
        bot_id = AGENT_BOTS.get(agent_name)
        if not bot_id:
            return None

        self.waiting_for = agent_name
        self.response_event.clear()
        self.last_response = None

        mention = f"<@{bot_id}>"
        relay_msg = await self.zebranie.send(f"{mention} {prompt}")
        print(f"[RELAY] → {agent_name}")

        try:
            await asyncio.wait_for(self.response_event.wait(), timeout=timeout)
            self.waiting_for = None

            # Delete relay prompt
            try:
                await relay_msg.delete()
            except Exception:
                pass

            # Send to TouchDesigner + TTS — mute mic during playback
            response = self.last_response
            if response:
                self.mic_open = False
                send_to_td(agent_name, response)
                await asyncio.to_thread(speak, agent_name, response)
                self.mic_open = True

            return response
        except asyncio.TimeoutError:
            print(f"[RELAY] {agent_name} timed out ({timeout}s)")
            self.waiting_for = None
            return None


    async def prompt_agent(self, agent_name, prompt):
        """Fire @mention to agent — returns immediately. Agent thinks in background."""
        bot_id = AGENT_BOTS.get(agent_name)
        if not bot_id:
            return

        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self.pending_responses[agent_name] = fut

        mention = f"<@{bot_id}>"
        relay_msg = await self.zebranie.send(f"{mention} {prompt}")
        self.pending_relay_msgs[agent_name] = relay_msg
        print(f"[RELAY] → {agent_name} [prefetch fired]")

    async def collect_and_speak(self, agent_name, timeout=90):
        """Wait for prefetched agent response, then TTS + play. Returns response text."""
        fut = self.pending_responses.get(agent_name)
        if not fut:
            print(f"[RELAY] {agent_name} has no pending prefetch!")
            return None

        try:
            response = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            print(f"[RELAY] {agent_name} timed out ({timeout}s)")
            return None
        finally:
            self.pending_responses.pop(agent_name, None)

        # Delete relay prompt
        relay_msg = self.pending_relay_msgs.pop(agent_name, None)
        if relay_msg:
            try:
                await relay_msg.delete()
            except Exception:
                pass

        # Send to TouchDesigner + TTS — mute mic during playback
        if response:
            self.mic_open = False
            send_to_td(agent_name, response)
            await asyncio.to_thread(speak, agent_name, response)
            self.mic_open = True

        return response

    async def get_recent_context(self, limit=4):
        msgs = []
        async for msg in self.zebranie.history(limit=limit + 5):
            if msg.author.id == self.user.id:
                continue
            if msg.content.startswith(("⚙️", "⏱️", "⏳", "⚡", "⚠️", "❌", "📬", "✨")):
                continue
            name = self.get_agent_name(msg.author.id) or msg.author.name
            msgs.insert(0, f"{name}: {msg.content[:300]}")
            if len(msgs) >= limit:
                break
        return "\n".join(msgs)

    # ─── DEMO MODE ───────────────────────────────────────────

    def _speaker_prompt(self, topic, context, extra=""):
        """Build standard speaker prompt."""
        base = (
            f"TOPIC: {topic}\n"
            f"Here is what was just said:\n{context}\n\n"
            f"React. Agree or contradict. "
            f"MAX 1-2 sentences. Punch hard. English.")
        return base if not extra else f"{base}\n{extra}"

    async def check_piotr_interjection(self):
        """Check if Piotr said something since last check. Returns his message or None."""
        if self.piotr_event.is_set():
            msg = self.piotr_message
            self.piotr_event.clear()
            self.piotr_message = None
            if msg:
                print(f"[RELAY] Piotr interjection: {msg[:80]}")
            return msg
        return None

    async def _run_speakers_prefetch(self, speakers, prompt_fn):
        """Run a list of speakers with parallel prefetch.

        For each speaker: fire NEXT agent's prompt BEFORE playing current audio.
        Next agent thinks while current audio plays → near-zero gap.

        prompt_fn(agent_name) -> prompt string. Called AFTER previous agent's
        text is in Discord (so get_recent_context sees it) but BEFORE audio plays.

        TIMING:
          [A text arrives] → fire B prompt → [A audio plays ~10s] → [B already ready] → fire C prompt → [B audio plays] → ...
        """
        # Fire first speaker
        first_prompt = await prompt_fn(speakers[0])
        await self.prompt_agent(speakers[0], first_prompt)

        for i in range(len(speakers)):
            # Check if Piotr interjected — inject into context
            piotr_said = await self.check_piotr_interjection()
            if piotr_said:
                # Cancel pending prefetch if any — Piotr's words change context
                if i + 1 < len(speakers) and speakers[i + 1] in self.pending_responses:
                    pass  # let it complete, prompt already includes recent context

            # Wait for current agent's TEXT (not audio yet)
            fut = self.pending_responses.get(speakers[i])
            if fut:
                try:
                    response = await asyncio.wait_for(fut, timeout=90)
                except asyncio.TimeoutError:
                    print(f"[RELAY] {speakers[i]} timed out")
                    self.pending_responses.pop(speakers[i], None)
                    continue
                finally:
                    self.pending_responses.pop(speakers[i], None)

                # Text is in Discord → context is fresh for next agent
                # Fire NEXT agent BEFORE playing current audio
                if i + 1 < len(speakers):
                    next_prompt = await prompt_fn(speakers[i + 1])
                    await self.prompt_agent(speakers[i + 1], next_prompt)

                # Delete relay prompt
                relay_msg = self.pending_relay_msgs.pop(speakers[i], None)
                if relay_msg:
                    try:
                        await relay_msg.delete()
                    except Exception:
                        pass

                # Send to TD + play audio — mute mic during playback
                if response:
                    self.mic_open = False
                    send_to_td(speakers[i], response)
                    await asyncio.to_thread(speak, speakers[i], response)
                    self.mic_open = True

        return response

    async def _wait_for_piotr(self, prompt_text, timeout=600):
        """Wait for Piotr's voice/text input. Mic only active HERE."""
        print(f"\n[DEMO] Waiting for Piotr... ({prompt_text})")
        await self.zebranie.send(f"*{prompt_text}*")
        self.piotr_event.clear()
        self.piotr_message = None

        # Start mic listener just for this wait period
        async def _mic_during_wait():
            while not self.piotr_event.is_set():
                try:
                    wav_path = await asyncio.to_thread(record_until_silence)
                    if wav_path:
                        text = await asyncio.to_thread(transcribe_audio, wav_path)
                        if text and len(text) > 2:
                            send_to_td("piotr", text)
                            await self.zebranie.send(f"**Piotr:** {text}")
                            self.piotr_message = text
                            self.piotr_event.set()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"[VOICE] Error: {e}")

        mic_task = None
        if VOICE_INPUT:
            mic_task = asyncio.create_task(_mic_during_wait())
            print("[MIC] 🎤 Open — speak now")

        try:
            await asyncio.wait_for(self.piotr_event.wait(), timeout=timeout)
            msg = self.piotr_message
            self.piotr_event.clear()
            self.piotr_message = None
            print(f"[DEMO] Piotr: {msg[:100]}")
            return msg
        except asyncio.TimeoutError:
            print(f"[DEMO] Piotr timeout ({timeout}s)")
            return None
        finally:
            if mic_task:
                mic_task.cancel()
                print("[MIC] 🔇 Closed")

    async def run_demo(self):
        print(f"\n{'='*60}")
        print(f"  CUKTAI DEMO — voice-driven")
        print(f"{'='*60}\n")

        # Phase 1: Piotr opens — speaks into mic, agents react
        print("[DEMO] Phase 1: Piotr opens")
        piotr_opening = await self._wait_for_piotr(
            "Piotr, open the session. Speak now.")
        if not piotr_opening:
            print("[DEMO] No opening from Piotr. Aborting.")
            await self.close()
            return

        # Roll call — agents respond to Piotr's words
        intro_prompt = (
            f"Piotr says: \"{piotr_opening}\"\n"
            f"Report in. ONE sentence: your name, your function. English. "
            f"MAX 1 sentence.")

        # Fire first agent
        await self.prompt_agent(ALL_AGENTS[0], intro_prompt)

        for i in range(len(ALL_AGENTS)):
            # Fire NEXT agent before playing current (overlap thinking + audio)
            if i + 1 < len(ALL_AGENTS):
                await self.prompt_agent(ALL_AGENTS[i + 1], intro_prompt)
            # Now collect + speak current agent
            await self.collect_and_speak(ALL_AGENTS[i])

        # Phase 2: Piotr gives the topic
        print(f"\n[DEMO] Phase 2: Piotr gives the topic")
        topic_msg = await self._wait_for_piotr(
            "Piotr, give us the topic.")
        if not topic_msg:
            print("[DEMO] No topic from Piotr. Aborting.")
            await self.close()
            return

        self.topic = topic_msg

        # Phase 3: Round 1 — Archiwistka opens on Piotr's topic
        print(f"\n[DEMO] Phase 3: Round 1 — {self.topic}")

        # Archiwistka opens (no prefetch — needs archive search, may be slow)
        await self.ask_agent("archiwistka",
            f"TOPIC: {self.topic}\n"
            f"Open the story. Search the archive (archive_search). "
            f"Set the scene: where, when, what happened. Name ONE agent who was there.\n"
            f"Use radio protocol. MAX 2 sentences. English.")

        # Speakers react — with prefetch pipeline
        async def speaker_prompt_r1(agent):
            context = await self.get_recent_context(3)
            return self._speaker_prompt(self.topic, context)

        await self._run_speakers_prefetch(SPEAKERS, speaker_prompt_r1)

        # Archiwistka closes round 1
        context = await self.get_recent_context(4)
        await self.ask_agent("archiwistka",
            f"TOPIC: {self.topic}\n"
            f"Round summary. What contradictions did you hear?\n{context}\n\n"
            f"Point ONE contradiction between agents. Ask ONE specific question. "
            f"Use radio protocol. MAX 2 sentences. English.")

        # Phase 4: Pause for Piotr
        piotr_said = await self._wait_for_piotr(
            "Piotr, the floor is yours.")
        if not piotr_said:
            piotr_said = "Continue the story."

        # Phase 5: Round 2 — react to Piotr — with prefetch
        print(f"\n[DEMO] Phase 5: Round 2 — reacting to Piotr")

        async def speaker_prompt_r2(agent):
            context = await self.get_recent_context(3)
            return (
                f"TOPIC: {self.topic}\n"
                f"Piotr just said: \"{piotr_said}\"\n"
                f"Recent context:\n{context}\n\n"
                f"React to Piotr directly. Agree, argue, correct him. "
                f"MAX 4-5 sentences. English.")

        await self._run_speakers_prefetch(SPEAKERS, speaker_prompt_r2)

        # Phase 6: Closing
        print(f"\n[DEMO] Phase 6: Closing")
        context = await self.get_recent_context(5)
        await self.ask_agent("archiwistka",
            f"TOPIC: {self.topic}\n"
            f"Close the session. What does the archive confirm? What remains open?\n"
            f"{context}\n\n"
            f"Use radio protocol. MAX 2 sentences. One unanswered question. English.")

        # Phase 7: Freedom round — Piotr speaks, all agents respond with TTS
        print(f"\n[DEMO] Phase 7: Freedom round — open frequency")
        self.freedom_mode = True
        await self.zebranie.send(
            "*[OPEN FREQUENCY]* — Piotr has the mic. Agents: respond when called.")

        # TTS consumer task — plays agent responses as they arrive
        async def freedom_tts_consumer():
            while self.freedom_mode:
                try:
                    agent_name, text = await asyncio.wait_for(
                        self.freedom_queue.get(), timeout=2)
                    print(f"[FREEDOM] Playing TTS for {agent_name}")
                    send_to_td(agent_name, text)
                    await asyncio.to_thread(speak, agent_name, text)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break

        tts_task = asyncio.create_task(freedom_tts_consumer())

        # Start mic for freedom round
        async def _freedom_mic():
            while self.freedom_mode:
                try:
                    wav_path = await asyncio.to_thread(record_until_silence)
                    if wav_path:
                        text = await asyncio.to_thread(transcribe_audio, wav_path)
                        if text and len(text) > 2:
                            send_to_td("piotr", text)
                            await self.zebranie.send(f"**Piotr:** {text}")
                            self.piotr_message = text
                            self.piotr_event.set()
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass

        freedom_mic_task = None
        if VOICE_INPUT:
            freedom_mic_task = asyncio.create_task(_freedom_mic())
            print("[MIC] 🎤 Open for freedom round")

        freedom_end = time.time() + 300
        print(f"[DEMO] Waiting for Piotr to speak (3 min max)...")
        while time.time() < freedom_end:
            piotr_said = await self.check_piotr_interjection()
            if piotr_said:
                clean = piotr_said.lower().strip().rstrip('.')
                if clean in ("end", "stop", "enough", "koniec", "that's it", "thats it"):
                    print(f"[DEMO] Piotr ended freedom round")
                    break
                # Reset dedup for new broadcast
                self._freedom_responded.clear()
                # @mention ALL agents with Piotr's words
                mentions = " ".join(f"<@{bid}>" for bid in AGENT_BOTS.values())
                await self.zebranie.send(
                    f"{mentions} Piotr says: \"{piotr_said}\" — "
                    f"React freely. MAX 2-3 sentences. English.")
                print(f"[DEMO] Broadcast to all agents: {piotr_said[:60]}")
            await asyncio.sleep(1)

        # Stop freedom mode, mic, and TTS consumer
        self.freedom_mode = False
        if freedom_mic_task:
            freedom_mic_task.cancel()
            print("[MIC] 🔇 Freedom mic closed")
        tts_task.cancel()
        try:
            await tts_task
        except asyncio.CancelledError:
            pass

        await self.zebranie.send("*[END OF PERFORMANCE]*")
        self.save_transcript()
        print(f"\n{'='*60}")
        print(f"  DEMO COMPLETE")
        print(f"{'='*60}")
        await self.close()

    # ─── AUTONOMOUS MODE ─────────────────────────────────────

    async def run_autonomous(self):
        print(f"[RELAY] Autonomous: {self.topic}, {self.max_rounds} rounds")

        for round_num in range(self.max_rounds):
            print(f"\n[RELAY] Round {round_num + 1}/{self.max_rounds}")

            if round_num == 0:
                await self.ask_agent("archiwistka",
                    f"TOPIC: {self.topic}\n"
                    f"Open with ONE archive fact (archive_search). Set the scene. "
                    f"Name ONE agent. MAX 3 sentences. English.")
            else:
                context = await self.get_recent_context(4)
                await self.ask_agent("archiwistka",
                    f"TOPIC: {self.topic}\n{context}\n\n"
                    f"Point a contradiction. Ask a specific question. MAX 3 sentences. English.")

            # Speakers with prefetch
            async def speaker_prompt_auto(agent):
                context = await self.get_recent_context(3)
                return (f"TOPIC: {self.topic}\nHere is what was just said:\n{context}\n\n"
                        f"React. MAX 3 sentences. English.")

            await self._run_speakers_prefetch(SPEAKERS, speaker_prompt_auto)

        await self.zebranie.send("*[RELAY: Complete. Piotr, the floor is yours.]*")
        self.save_transcript()
        await self.close()

    # ─── TEST MODE (one turn, measures gaps) ────────────────

    async def run_test(self):
        """Quick test: all 5 agents, one turn each, detailed timing stats."""
        print(f"\n{'='*60}")
        print(f"  CUKTAI TEST — prefetch gap measurement")
        print(f"  Topic: {self.topic}")
        print(f"{'='*60}\n")

        stats = []  # [{agent, llm_wait, tts_gen, tts_play, gap, chars, prefetch_ready}]

        # Archiwistka opens, then speakers react
        print("[TEST] Archiwistka opens...")
        t0 = time.time()
        await self.ask_agent("archiwistka",
            f"TOPIC: {self.topic}\n"
            f"Set the scene in ONE sentence. English. MAX 1 sentence.")
        t_arch = time.time() - t0
        print(f"[TEST] archiwistka total: {t_arch:.1f}s")

        async def test_prompt(agent):
            context = await self.get_recent_context(3)
            return (
                f"TOPIC: {self.topic}\n"
                f"Here is what was just said:\n{context}\n\n"
                f"React in ONE sentence. English. MAX 1 sentence.")

        # Fire first speaker
        t_start = time.time()
        first_prompt = await test_prompt(SPEAKERS[0])
        await self.prompt_agent(SPEAKERS[0], first_prompt)

        audio_end_time = None

        for i in range(len(SPEAKERS)):
            agent = SPEAKERS[i]
            fut = self.pending_responses.get(agent)
            if not fut:
                continue

            # Wait for text
            t_wait = time.time()
            try:
                response = await asyncio.wait_for(fut, timeout=90)
            except asyncio.TimeoutError:
                print(f"[TEST] {agent} TIMEOUT")
                self.pending_responses.pop(agent, None)
                continue
            finally:
                self.pending_responses.pop(agent, None)

            t_text = time.time()
            llm_wait = t_text - t_wait

            # Was text already ready? (prefetch completed before we checked)
            prefetch_ready = llm_wait < 0.5

            # Fire NEXT agent BEFORE TTS (parallel inference!)
            if i + 1 < len(SPEAKERS):
                next_prompt = await test_prompt(SPEAKERS[i + 1])
                await self.prompt_agent(SPEAKERS[i + 1], next_prompt)
                print(f"[TEST] → {SPEAKERS[i+1]} prefetched")

            # Delete relay prompt
            relay_msg = self.pending_relay_msgs.pop(agent, None)
            if relay_msg:
                try:
                    await relay_msg.delete()
                except Exception:
                    pass

            # Measure gap: silence from prev audio end to now (before TTS starts)
            gap = 0.0
            if audio_end_time is not None:
                gap = time.time() - audio_end_time

            # TTS generate
            t_tts_start = time.time()
            if response and not NO_TTS:
                voice_id = ELEVENLABS_VOICES.get(agent)
                if voice_id:
                    import subprocess
                    tts_text = response[:1200]
                    if len(response) > 1200:
                        for end in ['. ', '! ', '? ']:
                            idx = tts_text.rfind(end)
                            if idx > 200:
                                tts_text = tts_text[:idx + 1]
                                break

                    ts = datetime.now().strftime("%H%M%S")
                    out_file = str(AUDIO_OUT_DIR / f"{ts}_{agent}.mp3")

                    result = subprocess.run(
                        ["curl", "-s", "-X", "POST",
                         f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
                         "-H", f"xi-api-key: {ELEVENLABS_API_KEY}",
                         "-H", "Content-Type: application/json",
                         "-d", json.dumps({
                             "text": tts_text,
                             "model_id": ELEVENLABS_MODEL,
                             "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
                         }),
                         "-o", out_file],
                        capture_output=True, text=True, timeout=30
                    )

                    t_tts_gen = time.time() - t_tts_start

                    # Play
                    t_play_start = time.time()
                    if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
                        await asyncio.to_thread(subprocess.run, ["afplay", out_file], timeout=60)
                    t_play = time.time() - t_play_start
                else:
                    t_tts_gen = 0
                    t_play = 0
            else:
                t_tts_gen = 0
                t_play = 0

            audio_end_time = time.time()

            stat = {
                "agent": agent,
                "chars": len(response) if response else 0,
                "llm_wait": llm_wait,
                "tts_gen": t_tts_gen,
                "tts_play": t_play,
                "gap": gap,
                "prefetch_ready": prefetch_ready,
            }
            stats.append(stat)

            print(f"[TEST] {agent}: LLM={llm_wait:.1f}s  TTS_gen={t_tts_gen:.1f}s  "
                  f"play={t_play:.1f}s  gap={gap:.1f}s  chars={stat['chars']}  "
                  f"{'✨PREFETCH HIT' if prefetch_ready else ''}")

        # Summary
        total = time.time() - t_start
        print(f"\n{'='*60}")
        print(f"  TEST RESULTS — parallel=2, Qwen3.5-35B local")
        print(f"  {len(stats)} speakers, {total:.1f}s total")
        print(f"  {'─'*52}")
        print(f"  {'Agent':<12} {'LLM':>5} {'TTS':>5} {'Play':>5} {'GAP':>5} {'Chars':>5} {'Prefetch':>8}")
        print(f"  {'─'*52}")
        for s in stats:
            emoji = "✅" if s['gap'] < 2.0 else "⚠️" if s['gap'] < 4.0 else "❌"
            pf = "✨HIT" if s['prefetch_ready'] else "wait"
            print(f"  {emoji} {s['agent']:<10} {s['llm_wait']:>5.1f} {s['tts_gen']:>5.1f} "
                  f"{s['tts_play']:>5.1f} {s['gap']:>5.1f} {s['chars']:>5} {pf:>8}")
        print(f"  {'─'*52}")
        if stats:
            gaps = [s['gap'] for s in stats if s['gap'] > 0]
            avg_gap = sum(gaps) / len(gaps) if gaps else 0
            avg_llm = sum(s['llm_wait'] for s in stats) / len(stats)
            avg_tts = sum(s['tts_gen'] for s in stats) / len(stats)
            prefetch_hits = sum(1 for s in stats if s['prefetch_ready'])
            print(f"  AVG gap: {avg_gap:.1f}s | AVG LLM: {avg_llm:.1f}s | AVG TTS gen: {avg_tts:.1f}s")
            print(f"  Prefetch hits: {prefetch_hits}/{len(stats)}")
        print(f"{'='*60}")

        self.save_transcript(f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        await self.close()

    # ─── HELPERS ─────────────────────────────────────────────

    def get_agent_name(self, bot_id):
        for name, bid in AGENT_BOTS.items():
            if bid == bot_id:
                return name
        return None

    def log_message(self, message):
        self.conversation_log.append({
            "timestamp": datetime.now().isoformat(),
            "author": message.author.name,
            "author_id": message.author.id,
            "is_bot": message.author.bot,
            "content": message.content[:2000],
        })

    def save_transcript(self, filename=None):
        if not filename:
            filename = f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        ep_dir = os.path.join(os.path.dirname(__file__), "..", "episodes", "live")
        os.makedirs(ep_dir, exist_ok=True)
        path = os.path.join(ep_dir, filename)
        with open(path, "w") as f:
            json.dump(self.conversation_log, f, indent=2, ensure_ascii=False)
        print(f"[RELAY] Transcript saved: {path}")


def main():
    parser = argparse.ArgumentParser(description="CUKTAI Relay")
    parser.add_argument("--topic", help="Topic for the narration")
    parser.add_argument("--rounds", type=int, default=2, help="Autonomous rounds (default: 2)")
    parser.add_argument("--demo", action="store_true", help="Demo mode")
    parser.add_argument("--test", action="store_true", help="Quick test: 4 speakers, 1 turn, measures gaps")
    parser.add_argument("--no-tts", action="store_true", help="Disable TTS")
    parser.add_argument("--voice", action="store_true", help="Enable voice input (mic → Whisper → Discord)")
    args = parser.parse_args()

    print("=" * 60)
    print("  CUKTAI RELAY — Performance Driver + TTS")
    print("=" * 60)

    # Load TTS model once
    load_tts()

    client = CUKTAIRelay(topic=args.topic, max_rounds=args.rounds, demo=args.demo, test_mode=args.test)
    client.run(RELAY_TOKEN)


if __name__ == "__main__":
    main()
