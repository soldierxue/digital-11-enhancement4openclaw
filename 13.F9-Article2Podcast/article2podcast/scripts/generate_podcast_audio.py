#!/usr/bin/env python3
"""Phase 2: Generate per-turn audio using multi-speaker TTS.

Produces individual MP3 files for each dialogue turn with role-specific voices,
plus a timing.json with durations.

Supports multiple TTS backends:
  - edge-tts: Free, Microsoft Edge TTS
  - elevenlabs: High-quality, supports custom cloned voices (requires API key)
  - minimax: Chinese-optimized TTS (requires API key)
  - auto: Round-robin host voice rotation + guest priority fallback (default)

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


# ── Host Voice Rotation State ────────────────────────────────────────

# Persists the index of the last-used host voice so consecutive episodes
# always rotate through host_voice_options instead of repeating.

HOST_VOICE_STATE_FILE = os.path.join(
    os.path.expanduser("~/.openclaw/workspace"), ".host_voice_state.json"
)


def _load_host_voice_state() -> dict:
    """Load the last-used host voice index from disk."""
    try:
        if os.path.exists(HOST_VOICE_STATE_FILE):
            with open(HOST_VOICE_STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_host_voice_state(state: dict):
    """Persist the host voice state to disk."""
    os.makedirs(os.path.dirname(HOST_VOICE_STATE_FILE), exist_ok=True)
    with open(HOST_VOICE_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ── Auto Mode: Voice Selection with Fallback ────────────────────────

def select_host_voice(config: dict, credentials: dict) -> dict:
    """Select host voice by round-robin rotation across host_voice_options.

    Each call picks the *next* option after the one used last time (persisted
    in HOST_VOICE_STATE_FILE), ensuring consecutive episodes never repeat the
    same host voice.  Falls back gracefully when a backend is unavailable.

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

    # --- Round-robin: pick the next index after last used ---------------
    state = _load_host_voice_state()
    last_index = state.get("last_host_voice_index", -1)
    n = len(options)

    # Try each option starting from the one after last_index
    for offset in range(1, n + 1):
        candidate_index = (last_index + offset) % n
        chosen = options[candidate_index]
        gender = chosen.get("gender", "female")
        edge_voice = edge_fallback.get(gender, "zh-CN-XiaoxiaoNeural")

        if check_backend_available(chosen["backend"], credentials):
            # Persist the choice for next run
            state["last_host_voice_index"] = candidate_index
            state["last_host_voice_label"] = chosen.get("label", chosen["voice_id"])
            _save_host_voice_state(state)

            print(f"  🔄 主持人轮换选择: {chosen['label']} ({chosen['backend']}) "
                  f"[index {candidate_index}/{n-1}]", flush=True)
            return {**chosen, "edge_voice": edge_voice}

        print(f"  ⚠️ 主持人选项 {chosen['label']} 不可用（{chosen['backend']} API key 缺失），"
              f"尝试下一个", flush=True)

    # All premium backends unavailable, fall back to edge-tts
    gender = options[0].get("gender", "female")
    edge_voice = edge_fallback.get(gender, "zh-CN-XiaoxiaoNeural")
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

# MiniMax reference audio file_id cache (uploaded once per session)
_minimax_ref_audio_file_id = None


def _upload_minimax_ref_audio(credentials: dict, config: dict) -> int:
    """Upload the guest reference audio to MiniMax once, return file_id.

    Uses audio_sample_file_id approach: instead of a pre-cloned voice_id,
    we pass a short reference audio in every T2A request so MiniMax mimics
    the voice on-the-fly.  This avoids clone voice training-data leakage.
    """
    global _minimax_ref_audio_file_id
    if _minimax_ref_audio_file_id is not None:
        return _minimax_ref_audio_file_id

    import requests

    ref_path = config.get("guest_voice_ref_audio", "")
    if not ref_path:
        # Default: look in assets/bgm/
        ref_path = os.path.join(SKILL_DIR, "assets", "bgm", "jason_voice_prompt_5s.m4a")

    # Resolve relative paths against SKILL_DIR
    ref_path = os.path.expanduser(ref_path)
    if not os.path.isabs(ref_path):
        ref_path = os.path.join(SKILL_DIR, ref_path)
    if not os.path.exists(ref_path):
        raise FileNotFoundError(f"Guest voice reference audio not found: {ref_path}")

    api_key = credentials.get("minimax_api_key", "")
    upload_url = "https://api.minimaxi.com/v1/files/upload"
    headers = {"Authorization": f"Bearer {api_key}"}

    with open(ref_path, "rb") as f:
        resp = requests.post(
            upload_url, headers=headers,
            data={"purpose": "voice_clone"},
            files={"file": (os.path.basename(ref_path), f)},
            timeout=60)
    resp.raise_for_status()
    result = resp.json()
    if result.get("base_resp", {}).get("status_code", 0) != 0:
        raise RuntimeError(f"MiniMax upload failed: {result}")

    _minimax_ref_audio_file_id = result["file"]["file_id"]
    print(f"  📤 嘉宾参考音频已上传: file_id={_minimax_ref_audio_file_id}", flush=True)
    return _minimax_ref_audio_file_id


def generate_turn_audio_minimax(turn_data: dict, output_dir: str,
                                 voice_id: str, credentials: dict,
                                 config: dict,
                                 use_ref_audio: bool = False) -> dict:
    """Generate audio for a single turn using MiniMax T2A API.

    If use_ref_audio is True, uses audio_sample_file_id for instant voice
    reference instead of a pre-cloned voice_id.  This avoids clone voice
    training-data leakage where the cloned voice prepends a fixed greeting.
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

    api_key = credentials.get("minimax_api_key", "")
    group_id = credentials.get("minimax_group_id", "")
    api_base = "https://api.minimaxi.com/v1"
    model = config.get("minimax_model", "speech-02-hd")

    url = f"{api_base}/t2a_v2?GroupId={group_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    voice_setting = {
        "voice_id": voice_id,
        "speed": 1.0,
        "vol": 1.0,
        "pitch": 0,
    }

    # Use reference audio for instant voice mimicry (no clone needed)
    if use_ref_audio:
        ref_file_id = _upload_minimax_ref_audio(credentials, config)
        voice_setting["audio_sample_file_id"] = ref_file_id

    payload = {
        "model": model,
        "text": text,
        "stream": False,
        "voice_setting": voice_setting,
        "audio_setting": {
            "sample_rate": 32000,
            "format": "mp3",
        },
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=180)
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
                                rate: str, pitch: str,
                                use_ref_audio: bool = False) -> dict:
    """Generate audio for a single turn using a specific backend. No fallback.
    Raises on failure so the caller can handle episode-level fallback."""
    if backend == "minimax":
        return generate_turn_audio_minimax(
            turn_data, output_dir, voice_id, credentials, config,
            use_ref_audio=use_ref_audio)
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
                                 rate: str, pitch: str,
                                 max_retries: int = 3) -> list:
    """Generate all turns for an episode using auto mode with per-turn retry.

    Key rule: within one episode, each role (host/guest) uses exactly ONE voice
    from start to finish. Voice IDs NEVER change mid-episode.
    If a turn fails, retry up to max_retries times. If still failing, abort.
    Already-generated audio files are cached and reused on re-run.
    """
    h_backend = host_info["backend"]
    h_voice = host_info["voice_id"]
    g_backend = guest_info["backend"]
    g_voice = guest_info["voice_id"]

    label = f"host={h_backend}/{h_voice}, guest={g_backend}/{g_voice}"
    print(f"  🎯 Voices: {label}", flush=True)

    results = []
    for i, turn in enumerate(turns):
        role = turn["role"]
        backend = h_backend if role == "host" else g_backend
        voice_id = h_voice if role == "host" else g_voice

        # Use reference audio for guest MiniMax turns (avoids clone leakage)
        use_ref = (role == "guest" and backend == "minimax"
                   and config.get("guest_voice_ref_audio", ""))

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                result = await generate_single_turn(
                    turn, output_dir, backend, voice_id,
                    credentials, config, rate, pitch,
                    use_ref_audio=use_ref)
                results.append(result)
                last_error = None
                break
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait = attempt * 5  # 5s, 10s backoff
                    print(f"  ⚠️ Turn {turn['turn']} ({role}): 第 {attempt} 次失败 ({e})，"
                          f"{wait}s 后重试...", flush=True)
                    # Remove partial/corrupt file before retry
                    remove_cached_turn(output_dir, turn)
                    await asyncio.sleep(wait)

        if last_error:
            print(f"  ❌ Turn {turn['turn']} ({role}): {max_retries} 次重试均失败，终止生成", flush=True)
            raise RuntimeError(
                f"Turn {turn['turn']} ({role}) 在 {backend} 上 {max_retries} 次重试均失败: {last_error}"
            )

        # Rate-limit protection between turns
        if i < len(turns) - 1:
            await asyncio.sleep(1.5)

    print(f"  ✅ 全集 {len(results)} turns 完成 (host={h_backend}, guest={g_backend})", flush=True)
    return results


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

    # ── Auto mode: round-robin host + priority guest with fallback ────
    if tts_backend == "auto":
        print(f"   🤖 Auto 模式: 主持人轮换 + 嘉宾优先级降级", flush=True)

        # Per-episode voice persistence: reuse previous selection on re-run
        workdir = os.path.dirname(args.output_dir) if os.path.basename(args.output_dir) == "audio" \
                  else args.output_dir
        voice_selection_file = os.path.join(workdir, "voice_selection.json")

        saved_selection = None
        if os.path.exists(voice_selection_file):
            try:
                with open(voice_selection_file, encoding="utf-8") as f:
                    saved_selection = json.load(f)
                print(f"   ♻️  复用上次选定的音色 (voice_selection.json)", flush=True)
            except (json.JSONDecodeError, OSError):
                saved_selection = None

        if saved_selection:
            host_info = saved_selection["host"]
            guest_info = saved_selection["guest"]
        else:
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

        # Persist voice selection for this episode (enables safe re-run)
        if not saved_selection:
            os.makedirs(os.path.dirname(voice_selection_file) or ".", exist_ok=True)
            with open(voice_selection_file, "w", encoding="utf-8") as f:
                json.dump({"host": host_info, "guest": guest_info},
                          f, ensure_ascii=False, indent=2)

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
