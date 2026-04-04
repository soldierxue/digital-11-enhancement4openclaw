#!/usr/bin/env python3
"""Phase 2: Generate per-turn audio using multi-speaker TTS.

Produces individual MP3 files for each dialogue turn with role-specific voices,
plus a timing.json with durations.

Supports multiple TTS backends:
  - edge-tts: Free, Microsoft Edge TTS
  - elevenlabs: High-quality, supports custom cloned voices (requires API key)
  - minimax: Chinese-optimized TTS (requires API key)
  - auto: Random host voice selection + guest priority fallback (default)

Usage:
    python3 generate_podcast_audio.py podcast-script.json \
        --output-dir audio/ \
        --timing-output timing.json \
        --host-voice zh-CN-YunxiNeural \
        --guest-voice zh-CN-XiaoyiNeural \
        --tts-backend auto
"""

import argparse
import asyncio
import json
import os
import random
import subprocess
import sys

import edge_tts


VOICE_MAP = {}  # populated at runtime
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_credentials() -> dict:
    """Load API keys from credentials.json (not committed to git)."""
    cred_path = os.path.join(SKILL_DIR, "credentials.json")
    if os.path.exists(cred_path):
        with open(cred_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_config() -> dict:
    """Load config.json for non-sensitive settings."""
    config_path = os.path.join(SKILL_DIR, "config.json")
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


# ── Backend Availability Check ──────────────────────────────────────

def check_backend_available(backend: str, credentials: dict) -> bool:
    """Check if a TTS backend is available (API key present and non-empty)."""
    if backend == "edge-tts":
        return True
    elif backend == "elevenlabs":
        key = credentials.get("elevenlabs_api_key", "")
        return bool(key and not key.startswith("<"))
    elif backend == "minimax":
        key = credentials.get("minimax_api_key", "")
        group_id = credentials.get("minimax_group_id", "")
        return bool(key and not key.startswith("<") and group_id and not group_id.startswith("<"))
    return False


# ── Auto Mode: Voice Selection with Fallback ────────────────────────

def select_host_voice(config: dict, credentials: dict) -> dict:
    """Select host voice: random choice from host_voice_options with fallback.

    Returns dict with keys: backend, voice_id, gender, label, edge_voice
    """
    options = config.get("host_voice_options", [])
    edge_fallback = config.get("host_edge_fallback", {})

    if not options:
        # No options configured, fall back to edge-tts defaults
        return {
            "backend": "edge-tts",
            "voice_id": edge_fallback.get("female", "zh-CN-XiaoxiaoNeural"),
            "gender": "female",
            "label": "Edge 默认女声",
            "edge_voice": edge_fallback.get("female", "zh-CN-XiaoxiaoNeural"),
        }

    # Randomly pick one option
    chosen = random.choice(options)
    gender = chosen.get("gender", "female")
    edge_voice = edge_fallback.get(gender, "zh-CN-XiaoxiaoNeural")

    # Check if chosen backend is available
    if check_backend_available(chosen["backend"], credentials):
        print(f"  🎲 主持人随机选择: {chosen['label']} ({chosen['backend']})", flush=True)
        return {**chosen, "edge_voice": edge_voice}

    print(f"  ⚠️ 主持人首选 {chosen['label']} 不可用（{chosen['backend']} API key 缺失）", flush=True)

    # Try the other option
    for alt in options:
        if alt["backend"] != chosen["backend"] and check_backend_available(alt["backend"], credentials):
            alt_gender = alt.get("gender", "female")
            alt_edge_voice = edge_fallback.get(alt_gender, "zh-CN-XiaoxiaoNeural")
            print(f"  ↪ 降级到: {alt['label']} ({alt['backend']})", flush=True)
            return {**alt, "edge_voice": alt_edge_voice}

    # All premium backends unavailable, fall back to edge-tts
    print(f"  ↪ 所有后端不可用，最终降级到 edge-tts ({edge_voice})", flush=True)
    return {
        "backend": "edge-tts",
        "voice_id": edge_voice,
        "gender": gender,
        "label": f"Edge {'男声' if gender == 'male' else '女声'}",
        "edge_voice": edge_voice,
    }


def select_guest_voice(config: dict, credentials: dict) -> dict:
    """Select guest voice: fixed priority with fallback.

    Returns dict with keys: backend, voice_id, label, edge_voice
    """
    guest_cfg = config.get("guest_voice", {})
    edge_fallback_voice = "zh-CN-YunyangNeural"

    # Priority chain: primary → fallback → edge_fallback
    chain = []
    if "primary" in guest_cfg:
        chain.append(guest_cfg["primary"])
    if "fallback" in guest_cfg:
        chain.append(guest_cfg["fallback"])
    if "edge_fallback" in guest_cfg:
        chain.append(guest_cfg["edge_fallback"])
        edge_fallback_voice = guest_cfg["edge_fallback"].get("voice_id", edge_fallback_voice)

    for option in chain:
        backend = option.get("backend", "edge-tts")
        if check_backend_available(backend, credentials):
            print(f"  🎤 嘉宾音色: {option.get('label', option['voice_id'])} ({backend})", flush=True)
            return {**option, "edge_voice": edge_fallback_voice}

    # Nothing available, ultimate fallback
    print(f"  ↪ 嘉宾降级到 edge-tts ({edge_fallback_voice})", flush=True)
    return {
        "backend": "edge-tts",
        "voice_id": edge_fallback_voice,
        "label": "Edge 男声",
        "edge_voice": edge_fallback_voice,
    }


# ── MiniMax TTS Backend ─────────────────────────────────────────────

def generate_turn_audio_minimax(turn_data: dict, output_dir: str,
                                 voice_id: str, credentials: dict,
                                 config: dict) -> dict:
    """Generate audio for a single turn using MiniMax T2A API."""
    import requests

    idx = turn_data["turn"]
    role = turn_data["role"]
    text = turn_data["text"]

    out_mp3 = os.path.join(output_dir, f"turn-{idx:02d}-{role}.mp3")

    # Skip if cached
    if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 0:
        duration = get_duration(out_mp3)
        print(f"  Turn {idx} ({role}): {duration:.1f}s (cached)", flush=True)
        return {"turn": idx, "role": role, "audio": out_mp3, "duration": duration}

    api_key = credentials.get("minimax_api_key", "")
    group_id = credentials.get("minimax_group_id", "")
    api_base = config.get("minimax_api_base", "https://api.minimax.chat/v1")
    model = config.get("minimax_model", "speech-02-hd")

    url = f"{api_base}/t2a_v2?GroupId={group_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 192000,
            "format": "mp3",
        },
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    resp_data = resp.json()

    # MiniMax returns hex-encoded audio in data.audio
    audio_hex = resp_data.get("data", {}).get("audio", "")
    if not audio_hex:
        raise ValueError(f"MiniMax returned empty audio for turn {idx}")

    audio_bytes = bytes.fromhex(audio_hex)
    with open(out_mp3, "wb") as f:
        f.write(audio_bytes)

    duration = get_duration(out_mp3)
    print(f"  Turn {idx} ({role}): {duration:.1f}s → {out_mp3}", flush=True)
    return {"turn": idx, "role": role, "audio": out_mp3, "duration": duration}


# ── ElevenLabs TTS Backend ──────────────────────────────────────────

def resolve_elevenlabs_voice_id(voice_name: str, api_key: str, api_base: str) -> str:
    """Resolve a voice name to an ElevenLabs voice ID.

    Supports:
      - Direct voice ID (passed through)
      - Voice name lookup via /v1/voices API
    """
    import requests

    # If it looks like a raw voice ID (hex-ish, 20+ chars), use directly
    if len(voice_name) >= 20 and voice_name.isalnum():
        return voice_name

    # Otherwise search by name
    resp = requests.get(
        f"{api_base}/voices",
        headers={"xi-api-key": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    for v in resp.json().get("voices", []):
        if v["name"].lower() == voice_name.lower():
            return v["voice_id"]

    raise ValueError(f"ElevenLabs voice '{voice_name}' not found. "
                     f"Check your voice library at https://elevenlabs.io/app/voice-library")


def generate_turn_audio_elevenlabs(turn_data: dict, output_dir: str,
                                    api_key: str, config: dict,
                                    voice_id_override: str = None) -> dict:
    """Generate audio for a single turn using ElevenLabs API.

    If voice_id_override is provided, use it directly instead of looking up from
    VOICE_MAP / config.
    """
    import requests

    idx = turn_data["turn"]
    role = turn_data["role"]
    text = turn_data["text"]

    out_mp3 = os.path.join(output_dir, f"turn-{idx:02d}-{role}.mp3")

    # Skip if cached
    if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 0:
        duration = get_duration(out_mp3)
        print(f"  Turn {idx} ({role}): {duration:.1f}s (cached)", flush=True)
        return {"turn": idx, "role": role, "audio": out_mp3, "duration": duration}

    api_base = config.get("elevenlabs_api_base", "https://api.elevenlabs.io/v1")
    model_id = config.get("elevenlabs_model", "eleven_multilingual_v2")

    # Determine voice_id
    if voice_id_override:
        voice_id = voice_id_override
    else:
        # Legacy path: use config elevenlabs_voice_{role} if available,
        # otherwise fall back to VOICE_MAP and try name→id resolution
        voice_key = f"elevenlabs_voice_{role}"
        voice_id = config.get(voice_key, "")
        if not voice_id:
            voice_name = VOICE_MAP.get(role, "jasonsh")
            voice_id = resolve_elevenlabs_voice_id(voice_name, api_key, api_base)

    resp = requests.post(
        f"{api_base}/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        },
        timeout=120,
    )
    resp.raise_for_status()

    with open(out_mp3, "wb") as f:
        f.write(resp.content)

    duration = get_duration(out_mp3)
    print(f"  Turn {idx} ({role}): {duration:.1f}s → {out_mp3}", flush=True)
    return {"turn": idx, "role": role, "audio": out_mp3, "duration": duration}


# ── Edge TTS Backend ────────────────────────────────────────────────

async def generate_turn_audio_edge(turn_data: dict, output_dir: str,
                                    rate: str, pitch: str,
                                    voice_override: str = None) -> dict:
    """Generate audio for a single dialogue turn using Edge TTS.

    If voice_override is provided, use it instead of VOICE_MAP lookup.
    """
    idx = turn_data["turn"]
    role = turn_data["role"]
    text = turn_data["text"]
    voice = voice_override or VOICE_MAP.get(role, "zh-CN-YunxiNeural")

    out_mp3 = os.path.join(output_dir, f"turn-{idx:02d}-{role}.mp3")

    # Skip if cached
    if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 0:
        duration = get_duration(out_mp3)
        print(f"  Turn {idx} ({role}): {duration:.1f}s (cached)", flush=True)
        return {"turn": idx, "role": role, "audio": out_mp3, "duration": duration}

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    audio_chunks = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])

    with open(out_mp3, "wb") as f:
        for data in audio_chunks:
            f.write(data)

    duration = get_duration(out_mp3)
    print(f"  Turn {idx} ({role}): {duration:.1f}s → {out_mp3}", flush=True)
    return {"turn": idx, "role": role, "audio": out_mp3, "duration": duration}


# ── Shared Utilities ────────────────────────────────────────────────

def get_duration(path: str) -> float:
    """Get audio duration in seconds. Tries ffprobe first, falls back to mutagen."""
    # Try ffprobe
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except FileNotFoundError:
        pass

    # Fallback: use mutagen
    try:
        from mutagen.mp3 import MP3
        audio = MP3(path)
        return audio.info.length
    except Exception:
        pass

    # Last resort: estimate from file size (128kbps MP3 ≈ 16KB/s)
    try:
        size = os.path.getsize(path)
        return size / 16000.0
    except Exception:
        return 0.0


def remove_cached_turn(output_dir: str, turn_data: dict):
    """Remove a cached audio file for a turn so it can be regenerated."""
    idx = turn_data["turn"]
    role = turn_data["role"]
    out_mp3 = os.path.join(output_dir, f"turn-{idx:02d}-{role}.mp3")
    if os.path.exists(out_mp3):
        os.remove(out_mp3)


# ── Per-Role TTS Generation with Fallback ───────────────────────────

async def generate_single_turn(turn_data: dict, output_dir: str,
                                backend: str, voice_id: str,
                                credentials: dict, config: dict,
                                rate: str, pitch: str) -> dict:
    """Generate audio for a single turn using a specific backend. No fallback.
    Raises on failure so the caller can handle episode-level fallback."""
    if backend == "minimax":
        return generate_turn_audio_minimax(
            turn_data, output_dir, voice_id, credentials, config)
    elif backend == "elevenlabs":
        api_key = credentials.get("elevenlabs_api_key", "")
        return generate_turn_audio_elevenlabs(
            turn_data, output_dir, api_key, config, voice_id_override=voice_id)
    else:  # edge-tts
        return await generate_turn_audio_edge(
            turn_data, output_dir, rate, pitch, voice_override=voice_id)


async def generate_episode_auto(turns: list, output_dir: str,
                                 host_info: dict, guest_info: dict,
                                 credentials: dict, config: dict,
                                 rate: str, pitch: str) -> list:
    """Generate all turns for an episode using auto mode with episode-level fallback.

    Key rule: within one episode, each role (host/guest) uses exactly ONE voice
    from start to finish. If a backend fails on any turn, the ENTIRE episode
    is retried with the next backend in the fallback chain for that role.
    """
    import shutil

    def build_attempt_chain(voice_info):
        """Build ordered list of (backend, voice_id) attempts for a role."""
        chain = [(voice_info["backend"], voice_info["voice_id"])]
        for fb in voice_info.get("fallback_chain", []):
            chain.append((fb["backend"], fb["voice_id"]))
        edge = voice_info.get("edge_voice", "zh-CN-YunxiNeural")
        if not any(b == "edge-tts" for b, _ in chain):
            chain.append(("edge-tts", edge))
        return chain

    host_chain = build_attempt_chain(host_info)
    guest_chain = build_attempt_chain(guest_info)

    # Try each combination: iterate guest chain (outer) × host chain (inner)
    # because guest voice consistency matters most (clone voice)
    for gi, (g_backend, g_voice) in enumerate(guest_chain):
        for hi, (h_backend, h_voice) in enumerate(host_chain):
            label = f"host={h_backend}/{h_voice[:20]}, guest={g_backend}/{g_voice[:20]}"
            attempt_num = gi * len(host_chain) + hi + 1

            if attempt_num > 1:
                print(f"\n  🔄 Episode retry #{attempt_num}: {label}", flush=True)
                # Clear all audio from previous failed attempt
                if os.path.isdir(output_dir):
                    for f in os.listdir(output_dir):
                        if f.endswith(".mp3"):
                            os.remove(os.path.join(output_dir, f))
                    print(f"  🗑️  Cleared partial audio from previous attempt", flush=True)
            else:
                print(f"  🎯 Voices: {label}", flush=True)

            results = []
            failed = False
            for i, turn in enumerate(turns):
                role = turn["role"]
                backend = h_backend if role == "host" else g_backend
                voice_id = h_voice if role == "host" else g_voice

                try:
                    result = await generate_single_turn(
                        turn, output_dir, backend, voice_id,
                        credentials, config, rate, pitch)
                    results.append(result)
                except Exception as e:
                    print(f"  ❌ Turn {turn['turn']} ({role}): {backend} 失败 ({e})", flush=True)
                    print(f"  🔄 将切换整集到下一个后端组合", flush=True)
                    failed = True
                    break

                # Rate-limit protection
                if i < len(turns) - 1:
                    await asyncio.sleep(1.5)

            if not failed:
                print(f"  ✅ 全集 {len(results)} turns 完成 (host={h_backend}, guest={g_backend})", flush=True)
                return results

    # All combinations exhausted
    raise RuntimeError("所有 TTS 后端组合均失败，无法生成本集音频")


# ── Main ────────────────────────────────────────────────────────────

async def main_async(args):
    global VOICE_MAP
    VOICE_MAP = {
        "host": args.host_voice,
        "guest": args.guest_voice,
    }

    with open(args.podcast_script, encoding="utf-8") as f:
        turns = json.load(f)

    os.makedirs(args.output_dir, exist_ok=True)

    tts_backend = args.tts_backend
    config = load_config()
    credentials = load_credentials()

    print(f"🔊 Generating {len(turns)} audio clips (multi-speaker)", flush=True)
    print(f"   TTS backend: {tts_backend}", flush=True)

    # ── Auto mode: random host + priority guest with fallback ────────
    if tts_backend == "auto":
        print(f"   🤖 Auto 模式: 随机选择主持人 + 嘉宾优先级降级", flush=True)

        host_info = select_host_voice(config, credentials)
        guest_info = select_guest_voice(config, credentials)

        # Build fallback chains for runtime call failures
        # Host fallback: try the other premium option, then edge-tts
        host_fallback_chain = []
        for opt in config.get("host_voice_options", []):
            if opt["backend"] != host_info["backend"]:
                host_fallback_chain.append({
                    "backend": opt["backend"],
                    "voice_id": opt["voice_id"],
                })
        host_info["fallback_chain"] = host_fallback_chain

        # Guest fallback chain from config priority
        guest_fallback_chain = []
        guest_cfg = config.get("guest_voice", {})
        for key in ("primary", "fallback", "edge_fallback"):
            if key in guest_cfg:
                fb = guest_cfg[key]
                if fb["backend"] != guest_info["backend"] or fb["voice_id"] != guest_info["voice_id"]:
                    guest_fallback_chain.append({
                        "backend": fb["backend"],
                        "voice_id": fb["voice_id"],
                    })
        guest_info["fallback_chain"] = guest_fallback_chain

        role_voice = {"host": host_info, "guest": guest_info}

        print(f"   Host:  {host_info['label']} ({host_info['backend']}, {host_info['voice_id']})", flush=True)
        print(f"   Guest: {guest_info['label']} ({guest_info['backend']}, {guest_info['voice_id']})", flush=True)

        results = await generate_episode_auto(
            turns, args.output_dir,
            host_info, guest_info,
            credentials, config,
            args.rate, args.pitch)

    else:
        # ── Legacy modes: edge-tts, elevenlabs, minimax, mixed ───────
        print(f"   Host voice:  {args.host_voice}", flush=True)
        print(f"   Guest voice: {args.guest_voice}", flush=True)

        # Determine per-role TTS backend
        role_backend = {}
        if tts_backend == "mixed":
            role_backend = {"host": "edge-tts", "guest": "elevenlabs"}
            print(f"   Mode: mixed (host=edge-tts, guest=elevenlabs)", flush=True)
        else:
            role_backend = {"host": tts_backend, "guest": tts_backend}

        # Pre-validate ElevenLabs key if needed
        api_key = ""
        if "elevenlabs" in role_backend.values():
            api_key = credentials.get("elevenlabs_api_key", "")
            if not api_key or api_key.startswith("<"):
                print("❌ ElevenLabs API key not found in credentials.json", file=sys.stderr)
                print("   Please copy credentials.json.example → credentials.json and fill in your key.", file=sys.stderr)
                sys.exit(1)

        # Pre-validate MiniMax key if needed
        if "minimax" in role_backend.values():
            mm_key = credentials.get("minimax_api_key", "")
            mm_group = credentials.get("minimax_group_id", "")
            if not mm_key or mm_key.startswith("<") or not mm_group or mm_group.startswith("<"):
                print("❌ MiniMax API key or Group ID not found in credentials.json", file=sys.stderr)
                sys.exit(1)

        results = []
        for turn in turns:
            role = turn["role"]
            backend = role_backend.get(role, "edge-tts")

            if backend == "minimax":
                voice_id = VOICE_MAP.get(role, "male-qn-jingying")
                result = generate_turn_audio_minimax(
                    turn, args.output_dir, voice_id, credentials, config)
            elif backend == "elevenlabs":
                result = generate_turn_audio_elevenlabs(
                    turn, args.output_dir, api_key, config)
            else:
                result = await generate_turn_audio_edge(
                    turn, args.output_dir, args.rate, args.pitch)
            results.append(result)

    # Save timing
    with open(args.timing_output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    total = sum(r["duration"] for r in results)
    print(f"\n📊 Total duration: {total:.1f}s ({total/60:.1f} min)", flush=True)
    print(f"   Timing saved to: {args.timing_output}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Generate multi-speaker podcast audio")
    parser.add_argument("podcast_script", help="Path to podcast-script.json")
    parser.add_argument("--output-dir", required=True, help="Audio output directory")
    parser.add_argument("--timing-output", required=True, help="Timing JSON output path")
    parser.add_argument("--host-voice", default="zh-CN-XiaoxiaoNeural")
    parser.add_argument("--guest-voice", default="zh-CN-YunyangNeural")
    parser.add_argument("--tts-backend", default="edge-tts",
                        choices=["edge-tts", "elevenlabs", "minimax", "mixed", "auto"])
    parser.add_argument("--rate", default="-5%", type=str)
    parser.add_argument("--pitch", default="+0Hz", type=str)
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
