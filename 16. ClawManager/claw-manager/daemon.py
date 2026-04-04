#!/usr/bin/env python3
"""Claw Manager Daemon — OpenClaw 任务神经系统守护进程 v2"""

import json, os, sys, time, re, signal, tempfile, shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

import psutil

BASE = Path.home() / ".openclaw" / "claw-manager"
WATCH = BASE / "watch.json"
STATE = BASE / "state.json"
EVENTS = BASE / "events.jsonl"
ALERTS = BASE / "alerts.jsonl"
DASHBOARD = BASE / "dashboard.html"
PROFILES_FILE = BASE / "task_profiles.json"
KB_FILE = BASE / "knowledge_base.json"
PIDS_DIR = BASE / "pids"
POLL_INTERVAL = 30
API_PORT = 17890
FEISHU_URL = "http://localhost:18789/feishu/messages"
FEISHU_USER = "ou_65860c1079b77609db7c77be7f133531"

# 北京时间 timezone
TZ_CST = timezone(timedelta(hours=8))

# 队友固定列表
TEAMMATES = [
    {"id": "Scout",  "emoji": "🔍", "name": "情报官 Scout",  "skill": "AI资讯采集"},
    {"id": "Quill",  "emoji": "✍️",  "name": "主笔 Quill",    "skill": "协作写作"},
    {"id": "Frame",  "emoji": "🎬", "name": "导演 Frame",    "skill": "视频制作"},
    {"id": "Echo",   "emoji": "📢", "name": "运营 Echo",     "skill": "内容发布"},
    {"id": "Forge",  "emoji": "🔧", "name": "工程师 Forge",  "skill": "代码开发"},
    {"id": "Warden", "emoji": "🛡️", "name": "守卫 Warden",  "skill": "系统监控"},
]

# ── Skill 档案数据 ────────────────────────────────────────────────────────
SKILL_PROFILES = {
    "Scout": {
        "emoji": "🔍",
        "cn": "情报官",
        "en": "Scout",
        "skill": "tech-updates-collector",
        "desc": "全网 AI 资讯采集，覆盖 A-G 共7大维度，每日6次定时运行，输出结构化日报供 Quill 使用。",
        "phases": [
            ("维度 A-G 搜索", "normal"),
            ("去重 & 质量过滤", "normal"),
            ("日报写入", "normal"),
        ],
        "state_file": "~/.openclaw/skills/tech-updates-collector/output/",
        "achievements_check": "collector"
    },
    "Quill": {
        "emoji": "✍️",
        "cn": "主笔",
        "en": "Quill",
        "skill": "tech-updates-writer",
        "desc": "虾群协作写作系统，Phase 0-10 全流程，每日产出 21 篇初稿，精选 7 篇发布，均分 85+。",
        "phases": [
            ("Phase 0: 候选题采集", "normal"),
            ("Phase 1: 编辑选题", "normal"),
            ("Phase 2: v1 批量写作", "risky"),
            ("Phase 3: 质量评审", "normal"),
            ("Phase 4: v2 润色修改", "normal"),
            ("Phase 5: 编辑终选", "normal"),
            ("Phase 6: 发布前审查", "normal"),
            ("Phase 7: GitHub 发布", "normal"),
            ("Phase 7.5: 飞书上传", "normal"),
            ("Phase 8-10: 收尾质检", "normal"),
        ],
        "state_file": "~/.openclaw/skills/tech-updates-writer/state.json",
        "achievements_check": "writer"
    },
    "Frame": {
        "emoji": "🎬",
        "cn": "导演",
        "en": "Frame",
        "skill": "article2video",
        "desc": "将文章转化为带语音、字幕、Ken Burns 动效的短视频，支持横版+竖版双格式，每批 7 个。",
        "phases": [
            ("文章解析 & 分段", "normal"),
            ("TTS 语音合成", "normal"),
            ("图片获取 (Unsplash)", "normal"),
            ("Remotion 渲染", "risky"),
            ("FFmpeg 压缩", "normal"),
        ],
        "state_file": "~/.openclaw/skills/article2video/batch-state.json",
        "achievements_check": "video"
    },
    "Echo": {
        "emoji": "📢",
        "cn": "运营",
        "en": "Echo",
        "skill": "channels-publisher / weixin-publisher",
        "desc": "多平台内容发布，覆盖微信公众号（图文+封面）和视频号（横版视频）。当前视频号上传受 AWS 网络限制。",
        "phases": [
            ("读取文章/视频", "normal"),
            ("生成封面/标题", "normal"),
            ("上传媒体文件", "risky"),
            ("填写元数据", "normal"),
            ("保存草稿/发布", "normal"),
        ],
        "state_file": None,
        "achievements_check": "publisher"
    },
    "Forge": {
        "emoji": "🔧",
        "cn": "工程师",
        "en": "Forge",
        "skill": "kiro-cli",
        "desc": "代码开发与调研，通过 Kiro CLI ACP 协议执行，内置 Exa 搜索和 AWS 文档 MCP，节省 60-80% Claude Token。",
        "phases": [
            ("任务解析", "normal"),
            ("Kiro ACP 连接", "normal"),
            ("代码生成/执行", "normal"),
            ("验证 & 汇报", "normal"),
        ],
        "state_file": None,
        "achievements_check": "forge"
    },
    "Warden": {
        "emoji": "🛡️",
        "cn": "守卫",
        "en": "Warden",
        "skill": "claw-manager",
        "desc": "系统监控守护进程，30秒轮询，检测任务崩溃、资源异常，自动重启并飞书告警，内存常驻 ~15MB。",
        "phases": [
            ("资源采集", "normal"),
            ("任务存活检测", "normal"),
            ("崩溃诊断", "normal"),
            ("自动重启决策", "normal"),
            ("Dashboard 生成", "normal"),
            ("飞书告警", "normal"),
        ],
        "state_file": "~/.openclaw/claw-manager/state.json",
        "achievements_check": "warden"
    }
}

# --- Atomic file helpers ---

def read_json(path):
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def write_atomic(path, content):
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, content.encode() if isinstance(content, str) else content)
        os.close(fd)
        shutil.move(tmp, path)
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

def append_event(event_dict):
    event_dict.setdefault("ts", int(time.time()))
    with open(EVENTS, "a") as f:
        f.write(json.dumps(event_dict, ensure_ascii=False) + "\n")

def append_alert(alert_dict):
    alert_dict.setdefault("ts", int(time.time()))
    with open(ALERTS, "a") as f:
        f.write(json.dumps(alert_dict, ensure_ascii=False) + "\n")

# --- Resource checking ---

def check_system_resources():
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    remotion = count_remotion_instances()
    return {
        "cpu_pct": cpu,
        "mem_pct": mem.percent,
        "mem_available_mb": int(mem.available / 1024 / 1024),
        "mem_total_mb": int(mem.total / 1024 / 1024),
        "disk_pct": disk.percent,
        "disk_free_gb": round(disk.free / 1024**3, 1),
        "remotion_instances": remotion,
    }

def count_remotion_instances():
    count = 0
    for p in psutil.process_iter(["cmdline"]):
        try:
            cmd = " ".join(p.info["cmdline"] or [])
            if "remotion" in cmd.lower() and "render" in cmd.lower():
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return count

# --- Cost accumulation ---

def load_model_pricing():
    """Load model pricing from task_profiles.json"""
    profiles_data = read_json(PROFILES_FILE)
    return profiles_data.get("model_pricing", {}), profiles_data.get("usd_to_cny", 7.25)

def calc_cost_usd(tokens_in, tokens_out, model, pricing):
    """Calculate cost in USD given token counts and model name."""
    if not model or not pricing:
        return 0.0
    # Try exact match, then fuzzy match
    rate = pricing.get(model)
    if not rate:
        for key in pricing:
            if key in model or model in key:
                rate = pricing[key]
                break
    if not rate:
        return 0.0
    cost = (tokens_in / 1_000_000) * rate.get("input_per_million", 0)
    cost += (tokens_out / 1_000_000) * rate.get("output_per_million", 0)
    return round(cost, 6)

def process_cost_events(watch_data):
    """Scan recent events.jsonl and accumulate costs into watch_data tasks."""
    pricing, usd_to_cny = load_model_pricing()
    task_map = {t["taskId"]: t for t in watch_data.get("tasks", [])}
    # Also map by label/source
    source_map = {}
    for t in watch_data.get("tasks", []):
        src = t.get("label", "")
        if src:
            source_map[src] = t

    processed_key = "_cost_processed_lines"
    already_processed = watch_data.get(processed_key, 0)

    try:
        lines = EVENTS.read_text().strip().split("\n")
    except Exception:
        return

    new_count = 0
    for i, line in enumerate(lines):
        if i < already_processed:
            continue
        line = line.strip()
        if not line:
            new_count += 1
            continue
        try:
            ev = json.loads(line)
        except Exception:
            new_count += 1
            continue

        tokens_in = ev.get("cost_tokens_in", 0) or 0
        tokens_out = ev.get("cost_tokens_out", 0) or 0
        model = ev.get("model", "")
        if tokens_in == 0 and tokens_out == 0:
            new_count += 1
            continue

        # Find matching task
        task = None
        if ev.get("taskId") and ev["taskId"] in task_map:
            task = task_map[ev["taskId"]]
        elif ev.get("source") and ev["source"] in source_map:
            task = source_map[ev["source"]]

        if task:
            cost = task.setdefault("cost", {"tokens_in": 0, "tokens_out": 0, "usd": 0.0, "budget_usd": 0.0})
            cost["tokens_in"] = cost.get("tokens_in", 0) + tokens_in
            cost["tokens_out"] = cost.get("tokens_out", 0) + tokens_out
            new_usd = calc_cost_usd(tokens_in, tokens_out, model, pricing)
            cost["usd"] = round(cost.get("usd", 0.0) + new_usd, 6)

        new_count += 1

    watch_data[processed_key] = already_processed + new_count

# --- Crash diagnosis (rule-driven, no LLM) ---

def load_knowledge_base():
    return read_json(KB_FILE).get("patterns", [])

def is_task_alive(task):
    """Three-mode liveness check: local PID → session heartbeat → stateFile mtime."""
    now = time.time()
    started = task.get("startedAt", 0)
    grace = started and (now - started) < 300  # 5-minute grace period

    # Mode 1: local PID
    pid = task.get("pid")
    if pid:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, TypeError):
            pass

    # Mode 2: session heartbeat file
    session_key = task.get("sessionKey")
    if session_key and not pid:
        pid_file = PIDS_DIR / f"{task['taskId']}.json"
        if pid_file.exists():
            try:
                hb = json.loads(pid_file.read_text())
                if (now - hb.get("lastHeartbeat", 0)) < POLL_INTERVAL * 3:
                    return True
            except (json.JSONDecodeError, KeyError):
                pass
        elif grace:
            return True  # hasn't written pid file yet

    # Mode 3: stateFile mtime
    state_file = task.get("stateFile")
    if state_file and os.path.exists(state_file):
        if (now - os.path.getmtime(state_file)) < POLL_INTERVAL * 2:
            return True

    # Grace period fallback
    if grace:
        return True

    return False

def update_session_heartbeat(task_id, session_key):
    """Write/update heartbeat pid file for a session-based task."""
    PIDS_DIR.mkdir(parents=True, exist_ok=True)
    pid_file = PIDS_DIR / f"{task_id}.json"
    now = int(time.time())
    data = {"sessionKey": session_key, "lastHeartbeat": now}
    if pid_file.exists():
        try:
            existing = json.loads(pid_file.read_text())
            data["startedAt"] = existing.get("startedAt", now)
        except (json.JSONDecodeError, KeyError):
            data["startedAt"] = now
    else:
        data["startedAt"] = now
    write_atomic(pid_file, json.dumps(data))

def diagnose_crash(task, resources):
    """Returns (reason, detail)"""
    if is_task_alive(task):
        return None, None

    # Restart count check
    if task.get("restartCount", 0) >= task.get("maxRestarts", 3):
        return "REPEATED_CRASH", f"已重启{task['restartCount']}次，达到上限"

    # Timeout check
    started = task.get("startedAt", 0)
    est = task.get("estimatedMinutes", 60)
    if started and (time.time() - started) > est * 60 * 2:
        return "STALL", f"运行超过预估时间2倍({est*2}min)"

    # Memory check at crash time
    if resources["mem_pct"] > 80:
        return "OOM_LIKELY", f"崩溃时内存使用{resources['mem_pct']}%"

    # Knowledge base pattern matching (check last log lines if state file exists)
    kb = load_knowledge_base()
    state_file = task.get("stateFile")
    if state_file and os.path.exists(state_file):
        try:
            content = Path(state_file).read_text()[-2000:]
            for pat in kb:
                if pat.get("skill") not in ("*", task.get("skill")):
                    continue
                if re.search(pat["pattern"], content, re.IGNORECASE):
                    return pat["crash_reason"], pat.get("fix", pat["pattern"])
        except Exception:
            pass

    return "UNKNOWN", "进程消失，原因未知"

# --- Resource assessment ---

def assess_resources(task, resources, profiles):
    profile = profiles.get(task.get("skill"), {})
    required = profile.get("peak_memory_mb", 500)
    available = resources["mem_available_mb"]

    if available < required * 1.3:
        return False, f"内存不足：可用{available}MB < 需要{int(required*1.3)}MB"

    if task.get("skill") == "article2video":
        if resources["remotion_instances"] >= profile.get("concurrent_limit", 2):
            return False, f"Remotion实例数{resources['remotion_instances']}已达上限"

    return True, f"资源充足：可用{available}MB"

# --- Restart decision ---

def decide_restart(task, reason, detail, resources, profiles):
    """Returns (action, message) where action is 'restart'|'queue'|'alert_human'"""
    profile = profiles.get(task.get("skill"), {})
    auto = task.get("autoRestart", profile.get("auto_restart", False))
    max_r = task.get("maxRestarts", profile.get("max_restarts", 0))

    if reason == "REPEATED_CRASH":
        return "alert_human", detail

    if reason == "UNKNOWN":
        return "alert_human", detail

    if not auto:
        return "alert_human", f"任务需人工确认重启: {detail}"

    if task.get("restartCount", 0) >= max_r:
        return "alert_human", f"已达最大重启次数{max_r}"

    ok, res_msg = assess_resources(task, resources, profiles)
    if not ok:
        return "queue", res_msg

    return "restart", detail

# --- Feishu alert ---

def send_feishu_alert(msg):
    try:
        import requests
        requests.post(FEISHU_URL, json={
            "channel": "feishu",
            "receive_id": FEISHU_USER,
            "msg_type": "text",
            "content": json.dumps({"text": f"🔮 Claw Manager 告警\n{msg}"})
        }, timeout=5)
    except Exception as e:
        append_event({"event": "feishu_error", "detail": str(e)})

# --- Trigger API server ---

pending_triggers = []

class TriggerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        elif self.path == "/state":
            try:
                data = STATE.read_text().encode()
            except Exception:
                data = b'{}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/trigger":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            pending_triggers.append(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, *args):
        pass  # suppress logs

def start_api_server():
    server = HTTPServer(("127.0.0.1", API_PORT), TriggerHandler)
    server.serve_forever()

# --- Process triggers ---

def process_triggers(watch_data):
    while pending_triggers:
        t = pending_triggers.pop(0)
        action = t.get("action")
        tid = t.get("taskId")
        for task in watch_data.get("tasks", []):
            if task["taskId"] == tid:
                if action == "restart":
                    task["status"] = "running"
                    task["restartCount"] = task.get("restartCount", 0) + 1
                    task["startedAt"] = int(time.time())
                    append_event({"event": "manual_restart", "taskId": tid})
                elif action == "skip":
                    task["status"] = "done"
                    append_event({"event": "skipped", "taskId": tid})
                elif action == "pause":
                    task["status"] = "queued"
                    append_event({"event": "paused", "taskId": tid})
        if action == "pause_queue":
            for task in watch_data.get("tasks", []):
                if task["status"] == "queued":
                    task["status"] = "paused"

# --- Queue processing ---

def process_queue(watch_data, resources, profiles):
    queue = watch_data.get("queue", [])
    remaining = []
    for item in queue:
        tid = item["taskId"]
        task = next((t for t in watch_data["tasks"] if t["taskId"] == tid), None)
        if not task:
            continue
        ok, _ = assess_resources(task, resources, profiles)
        if ok:
            task["status"] = "running"
            task["startedAt"] = int(time.time())
            task["restartCount"] = task.get("restartCount", 0) + 1
            append_event({"event": "dequeued_restart", "taskId": tid})
        elif (time.time() - item.get("enqueuedAt", 0)) > item.get("maxWaitMin", 60) * 60:
            task["status"] = "failed"
            msg = f"任务 {tid} 队列等待超时"
            append_alert({"event": "queue_timeout", "taskId": tid, "detail": msg})
            send_feishu_alert(msg)
        else:
            remaining.append(item)
    watch_data["queue"] = remaining



# --- Skill profile stats & achievements ---

def _compute_skill_stats(teammate_id, tasks, events):
    """Compute 7-day stats for a given teammate."""
    seven_days_ago = time.time() - 7 * 86400
    my_tasks = [t for t in tasks
                if t.get("assignedTo") == teammate_id
                and t.get("startedAt", 0) > seven_days_ago]

    run_count = len(my_tasks)
    success_count = len([t for t in my_tasks if t.get("status") == "done"])
    success_rate = int(success_count / run_count * 100) if run_count else 0

    durations = []
    for t in my_tasks:
        if t.get("endTime") and t.get("startedAt"):
            durations.append(t["endTime"] - t["startedAt"])
    avg_duration = int(sum(durations) / len(durations)) if durations else 0

    total_cost = sum(
        (t.get("cost", {}) or {}).get("usd", 0) if isinstance(t.get("cost"), dict) else (t.get("cost") or 0)
        for t in my_tasks
    )

    skill_name = SKILL_PROFILES.get(teammate_id, {}).get("skill", "").split("/")[0].strip()
    error_events = [e for e in events
                    if e.get("event") in ("crash_detected", "task_fail")
                    and skill_name in (e.get("source", "") + e.get("taskId", ""))]

    return {
        "run_count": run_count,
        "success_rate": success_rate,
        "avg_duration_sec": avg_duration,
        "total_cost_usd": total_cost,
        "error_count": len(error_events),
    }


def _compute_achievements(teammate_id, tasks, events):
    """Compute achievement list for a teammate."""
    achievements = []
    my_tasks = [t for t in tasks if t.get("assignedTo") == teammate_id]
    done_tasks = [t for t in my_tasks if t.get("status") == "done"]

    if teammate_id == "Quill":
        week_tasks = [t for t in done_tasks if t.get("startedAt", 0) > time.time() - 7 * 86400]
        articles = sum(t.get("batchProgress", {}).get("completed", 0) for t in week_tasks)
        if articles > 0:
            achievements.append(f"✅ 本周发布 {articles} 篇文章")
        if len(done_tasks) >= 3:
            achievements.append(f"🔥 已连续运行 {len(done_tasks)} 天")
        best = max((t.get("batchProgress", {}).get("completed", 0) for t in done_tasks), default=0)
        if best > 0:
            achievements.append(f"🏆 单日最高产出 {best} 篇")

    elif teammate_id == "Frame":
        total_videos = sum(t.get("batchProgress", {}).get("completed", 0) for t in done_tasks)
        if total_videos > 0:
            achievements.append(f"✅ 累计渲染 {total_videos} 个视频")

    elif teammate_id == "Warden":
        achievements.append("🛡️ 系统守卫，24/7 在线")
        achievements.append(f"📊 监控 {len(tasks)} 个历史任务")

    if len(done_tasks) >= 5:
        achievements.append(f"⭐ 老兵：已完成 {len(done_tasks)} 次任务")

    return achievements


def _fmt_duration(secs):
    """Format seconds to human-readable string like 2h15m or 45m."""
    h = secs // 3600
    m = (secs % 3600) // 60
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m"


def _build_skill_profile_html(teammate_id, tasks, events):
    """Build the HTML for a single teammate's skill profile page."""
    profile = SKILL_PROFILES.get(teammate_id)
    if not profile:
        return f'<div style="color:#8b949e;padding:20px">未找到 {teammate_id} 的档案</div>'

    stats = _compute_skill_stats(teammate_id, tasks, events)
    achievements = _compute_achievements(teammate_id, tasks, events)

    # Phases HTML
    phases_rows = ""
    for i, (phase_name, phase_type) in enumerate(profile["phases"]):
        if phase_type == "risky":
            indicator = '<span style="color:#d29922">▲ 高风险</span>'
            row_style = 'background:rgba(210,153,34,0.05);'
        else:
            indicator = '<span style="color:#484f58">○</span>'
            row_style = ''
        phases_rows += f'''<div class="sp-phase-row" style="{row_style}">
  <span class="sp-phase-num">Phase {i}</span>
  <span class="sp-phase-name">{phase_name}</span>
  <span class="sp-phase-indicator">{indicator}</span>
</div>'''

    # Stats box
    avg_dur_str = _fmt_duration(stats["avg_duration_sec"]) if stats["avg_duration_sec"] else "—"
    cost_str = f'${stats["total_cost_usd"]:.1f}' if stats["total_cost_usd"] else "—"
    success_str = f'{stats["success_rate"]}%' if stats["run_count"] else "—"

    stats_html = f'''<div class="sp-stats-box">
  <div class="sp-stats-row">
    <div class="sp-stat"><div class="sp-stat-val">{stats["run_count"]}次</div><div class="sp-stat-lbl">执行次数</div></div>
    <div class="sp-stat"><div class="sp-stat-val">{avg_dur_str}</div><div class="sp-stat-lbl">平均耗时</div></div>
    <div class="sp-stat"><div class="sp-stat-val">{success_str}</div><div class="sp-stat-lbl">成功率</div></div>
    <div class="sp-stat"><div class="sp-stat-val">{cost_str}</div><div class="sp-stat-lbl">总消耗</div></div>
  </div>
</div>'''

    # Achievements HTML
    if achievements:
        ach_items = "".join(f'<div class="sp-achievement">{a}</div>' for a in achievements)
    else:
        ach_items = '<div style="color:#484f58;font-size:11px">暂无成就</div>'

    return f'''<div class="skill-profile" id="profile-{teammate_id}">
  <div class="sp-header">
    <button class="sp-back-btn" onclick="showMainPanel()">← 返回看板</button>
    <div class="sp-title">
      <span class="sp-emoji">{profile["emoji"]}</span>
      <span class="sp-cn">{profile["cn"]}</span>
      <span class="sp-en">{profile["en"]}</span>
    </div>
  </div>
  <div class="sp-divider"></div>

  <div class="sp-section">
    <div class="sp-section-title">📋 Skill 简介</div>
    <div class="sp-desc">{profile["desc"]}</div>
  </div>

  <div class="sp-section">
    <div class="sp-section-title">⚙️ 执行环节 &nbsp;<span style="font-weight:400;color:#6e7681">({len(profile["phases"])} 个 Phase)</span></div>
    <div class="sp-phases">{phases_rows}</div>
  </div>

  <div class="sp-section">
    <div class="sp-section-title">📊 近7天统计</div>
    {stats_html}
  </div>

  <div class="sp-section">
    <div class="sp-section-title">🏆 成就</div>
    <div class="sp-achievements">{ach_items}</div>
  </div>
</div>'''


# --- Dashboard generation (v2 GitHub Dark + Linear style) ---

def _assignee_to_teammate_id(skill_or_label: str) -> str | None:
    """Map a task's skill/label to a teammate ID."""
    sl = (skill_or_label or "").lower()
    mapping = {
        "tech-updates-collector": "Scout",
        "tech-updates-writer": "Quill",
        "article2video": "Frame",
        "channels-publisher": "Echo",
        "weixin-publisher": "Echo",
        "bili-publisher": "Echo",
        "kiro-cli": "Forge",
        "healthcheck": "Warden",
        "claw-manager": "Warden",
    }
    for key, val in mapping.items():
        if key in sl:
            return val
    return None


def _build_gantt_html(tasks: list) -> str:
    """Generate a full-width Gantt timeline section below the main dashboard."""
    if not tasks:
        return ""

    # Collect tasks that have startedAt
    today_str = datetime.now(TZ_CST).strftime("%Y-%m-%d")
    gantt_tasks = []
    for t in tasks:
        started = t.get("startedAt")
        if not started:
            continue
        d = datetime.fromtimestamp(started, tz=TZ_CST).strftime("%Y-%m-%d")
        gantt_tasks.append((d, t))

    if not gantt_tasks:
        return ""

    # Group by date, pick the most recent date
    from collections import defaultdict
    by_date: dict[str, list] = defaultdict(list)
    for d, t in gantt_tasks:
        by_date[d].append(t)

    # Build sections for all dates, most recent first
    sections = []
    for date_str in sorted(by_date.keys(), reverse=True):
        day_tasks = by_date[date_str]
        # Find time axis range
        ts_starts = [t["startedAt"] for t in day_tasks if t.get("startedAt")]
        ts_ends = []
        for t in day_tasks:
            end = t.get("endTime") or t.get("completedAt")
            if end:
                ts_ends.append(end)
            else:
                est = t.get("estimatedMinutes", 60)
                ts_ends.append(t["startedAt"] + est * 60)
        if not ts_starts:
            continue
        axis_start = min(ts_starts)
        axis_end = max(ts_ends) if ts_ends else axis_start + 3600
        axis_span = max(axis_end - axis_start, 3600)  # at least 1 hour

        axis_start_dt = datetime.fromtimestamp(axis_start, tz=TZ_CST)
        axis_end_dt = datetime.fromtimestamp(axis_end, tz=TZ_CST)
        axis_start_label = axis_start_dt.strftime("%H:%M")
        axis_end_label = axis_end_dt.strftime("%H:%M")

        STATUS_COLOR = {
            "done":    "#3fb950",
            "failed":  "#f85149",
            "running": "#58a6ff",
            "queued":  "#d29922",
            "skipped": "#8b949e",
            "paused":  "#8b949e",
        }

        TASK_EMOJI = {
            "Scout":  "🔍",
            "Quill":  "✍️",
            "Frame":  "🎬",
            "Echo":   "📢",
            "Forge":  "🔧",
            "Warden": "🛡️",
        }

        # Build a map taskId → task for dependency arrows
        task_map = {t["taskId"]: t for t in day_tasks if t.get("taskId")}

        rows_html = ""
        for t in day_tasks:
            status = t.get("status", "queued")
            color = STATUS_COLOR.get(status, "#8b949e")
            assignee = t.get("assignedTo") or _assignee_to_teammate_id(t.get("skill","")) or "?"
            emoji = TASK_EMOJI.get(assignee, "⚙️")
            label_short = assignee

            ts = t["startedAt"]
            end_ts = t.get("endTime") or t.get("completedAt")
            if not end_ts:
                est = t.get("estimatedMinutes", 60)
                end_ts = ts + est * 60

            left_pct  = (ts - axis_start) / axis_span * 100
            width_pct = (end_ts - ts) / axis_span * 100
            left_pct  = max(0, min(99, left_pct))
            width_pct = max(0.5, min(100 - left_pct, width_pct))

            start_label = datetime.fromtimestamp(ts, tz=TZ_CST).strftime("%H:%M")
            end_label   = datetime.fromtimestamp(end_ts, tz=TZ_CST).strftime("%H:%M")

            pulse_style = ' animation: gantt-pulse 2s ease-in-out infinite;' if status == "running" else ''
            bar_style = (
                f'left:{left_pct:.1f}%;width:{width_pct:.1f}%;'
                f'background:{color};{pulse_style}'
            )

            time_label = f"{start_label}-{end_label}"

            # Status icon
            status_icon = {"done": "✅", "failed": "❌", "running": "🔄", "queued": "⏳"}.get(status, "•")

            # Dependency arrow row
            dep_html = ""
            depends_on = t.get("dependsOn", [])
            for dep_id in depends_on:
                dep_task = task_map.get(dep_id)
                if dep_task:
                    dep_status = dep_task.get("status", "queued")
                    arrow_color = STATUS_COLOR.get(dep_status, "#8b949e")
                    dep_ts = dep_task["startedAt"]
                    dep_left_pct = (dep_ts - axis_start) / axis_span * 100
                    dep_left_pct = max(0, min(99, dep_left_pct))
                    dep_html += f'''<div class="gantt-dep-row">
  <div class="gantt-row-label"></div>
  <div class="gantt-row-track">
    <span class="dependency-arrow" style="position:absolute;left:{dep_left_pct:.1f}%;color:{arrow_color}">↓</span>
  </div>
</div>'''

            # Sub-batch bars
            sub_html = ""
            bp = t.get("batchProgress")
            if bp:
                total = bp.get("total", 0)
                completed = bp.get("completed", bp.get("done", 0))
                if total > 0:
                    sub_width = width_pct / total if total > 0 else 0
                    sub_bars = ""
                    for i in range(total):
                        sc = color if i < completed else "#30363d"
                        sub_bars += f'<span style="position:absolute;left:{left_pct + i*sub_width:.1f}%;width:{max(0.3,sub_width - 0.2):.1f}%;height:8px;top:4px;background:{sc};opacity:0.65;border-radius:2px;"></span>'
                    sub_html = f'''<div class="gantt-dep-row">
  <div class="gantt-row-label" style="font-size:10px;color:#484f58">  {completed}/{total}</div>
  <div class="gantt-row-track" style="position:relative;height:16px">{sub_bars}</div>
</div>'''

            result_text = ""
            res = t.get("result", "")
            if res and status in ("done", "failed"):
                result_text = res[:60] + ("…" if len(res) > 60 else "")

            rows_html += f'''{dep_html}<div class="gantt-task-row">
  <div class="gantt-row-label">
    <span class="gantt-emoji">{emoji}</span>
    <span class="gantt-assignee">{label_short}</span>
  </div>
  <div class="gantt-row-track">
    <div class="gantt-bar" style="{bar_style}"></div>
    <span class="gantt-time-label" style="position:absolute;left:{left_pct + width_pct + 0.5:.1f}%;top:0;font-size:10px;color:#8b949e;white-space:nowrap">{status_icon} {time_label}</span>
  </div>
</div>{sub_html}'''
            if result_text:
                rows_html += f'''<div class="gantt-result-row">
  <div class="gantt-row-label"></div>
  <div class="gantt-row-track" style="font-size:10px;color:#484f58;padding-left:{left_pct:.1f}%">{result_text}</div>
</div>'''

        date_label = date_str
        if date_str == today_str:
            date_label += "（今天）"

        sections.append(f'''<div class="gantt-section">
  <div class="gantt-header">
    <span class="gantt-title">📊 今日时间线</span>
    <span class="gantt-date">{date_label}</span>
  </div>
  <div class="gantt-axis-row">
    <div class="gantt-row-label"></div>
    <div class="gantt-row-track">
      <div class="gantt-axis-line"></div>
      <span class="gantt-axis-label" style="left:0">{axis_start_label}</span>
      <span class="gantt-axis-label" style="right:0">{axis_end_label}</span>
    </div>
  </div>
  {rows_html}
</div>''')

    if not sections:
        return ""

    return f'''<style>
.gantt-wrapper {{
  max-width: 1400px;
  margin: 24px auto;
  padding: 0 16px;
}}
.gantt-section {{
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 16px;
}}
.gantt-header {{
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}}
.gantt-title {{
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
}}
.gantt-date {{
  font-size: 12px;
  color: #8b949e;
}}
.gantt-axis-row {{
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}}
.gantt-row-label {{
  width: 90px;
  min-width: 90px;
  font-size: 12px;
  color: #8b949e;
  display: flex;
  align-items: center;
  gap: 4px;
  overflow: hidden;
}}
.gantt-row-track {{
  flex: 1;
  position: relative;
  height: 24px;
  display: flex;
  align-items: center;
}}
.gantt-axis-line {{
  position: absolute;
  left: 0; right: 0;
  height: 1px;
  background: #21262d;
  top: 50%;
}}
.gantt-axis-label {{
  position: absolute;
  font-size: 10px;
  color: #484f58;
  top: 0;
}}
.gantt-task-row {{
  display: flex;
  align-items: center;
  margin-bottom: 2px;
}}
.gantt-dep-row {{
  display: flex;
  align-items: center;
  height: 16px;
}}
.gantt-result-row {{
  display: flex;
  margin-bottom: 4px;
}}
.gantt-bar {{
  height: 20px;
  border-radius: 3px;
  position: absolute;
  min-width: 4px;
}}
.gantt-sub-bar {{
  height: 12px;
  border-radius: 2px;
  position: absolute;
  opacity: 0.7;
}}
.dependency-arrow {{
  color: #8b949e;
  font-size: 18px;
}}
.gantt-time-label {{
  white-space: nowrap;
}}
.gantt-emoji {{
  font-size: 13px;
}}
.gantt-assignee {{
  font-size: 11px;
  color: #8b949e;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 70px;
}}
@keyframes gantt-pulse {{
  0%, 100% {{ opacity: 1; }}
  50% {{ opacity: 0.6; }}
}}
</style>
<div class="gantt-wrapper">
{"".join(sections)}
</div>'''


def generate_dashboard(state):
    res = state.get("resources", {})
    tasks = state.get("tasks", [])

    # Read alerts & events
    alerts_lines = []
    try:
        for line in Path(ALERTS).read_text().strip().split("\n"):
            if line.strip():
                alerts_lines.append(json.loads(line))
        alerts_lines = alerts_lines[-20:]
    except Exception:
        pass

    events_lines = []
    try:
        for line in Path(EVENTS).read_text().strip().split("\n"):
            if line.strip():
                events_lines.append(json.loads(line))
        events_lines = events_lines[-30:]
    except Exception:
        pass

    running = [t for t in tasks if t.get("status") == "running"]
    done    = [t for t in tasks if t.get("status") == "done"]
    failed  = [t for t in tasks if t.get("status") == "failed"]

    # ── Determine active teammates ─────────────────────────
    active_tids = set()
    for t in running:
        tid = (
            t.get("assignedTo")
            or _assignee_to_teammate_id(t.get("skill", ""))
            or _assignee_to_teammate_id(t.get("label", ""))
        )
        if tid:
            active_tids.add(tid)

    # Cost per active teammate (sum running tasks)
    teammate_cost: dict[str, float] = {}
    for t in running:
        tid = (
            t.get("assignedTo")
            or _assignee_to_teammate_id(t.get("skill", ""))
            or _assignee_to_teammate_id(t.get("label", ""))
        )
        if tid:
            cost_val = t.get("cost", 0)
            if isinstance(cost_val, dict):
                cost_val = cost_val.get("usd", 0)
            teammate_cost[tid] = teammate_cost.get(tid, 0) + (cost_val or 0)

    # Teammate descriptions
    TEAMMATE_DESC = {
        "Scout":  "AI资讯采集 · 6维度",
        "Quill":  "协作写作 · 21篇/天",
        "Frame":  "视频制作 · Ken Burns",
        "Echo":   "内容发布 · 多平台",
        "Forge":  "代码开发 · 搜索调研",
        "Warden": "系统监控 · 30s轮询",
    }

    # ── Build teammates HTML ───────────────────────────────
    teammates_html_parts = []
    for tm in TEAMMATES:
        tid = tm["id"]
        is_warden = tid == "Warden"
        is_active = tid in active_tids

        if is_warden:
            cls = "teammate resident"
            dot_cls = "resident"
            label_cls = "resident"
            status_text = "常驻"
        elif is_active:
            cls = "teammate active"
            dot_cls = "active"
            label_cls = "active"
            status_text = "活跃"
        else:
            cls = "teammate"
            dot_cls = "idle"
            label_cls = "idle"
            status_text = "待机"

        cost_html = ""
        if tid in teammate_cost and teammate_cost[tid] > 0:
            cost_html = f'<span class="teammate-cost">¥{teammate_cost[tid]:.1f}</span>'

        desc = TEAMMATE_DESC.get(tid, "")
        teammates_html_parts.append(f'''<div class="{cls}" id="teammate-{tid}" onclick="showSkillProfile('{tid}')" style="cursor:pointer">
  <div class="teammate-header">
    <span class="teammate-emoji">{tm["emoji"]}</span>
    <span class="teammate-name">{tm["name"]}</span>
  </div>
  <div class="teammate-skill">{desc}</div>
  <div class="teammate-status">
    <span class="status-dot {dot_cls}"></span>
    <span class="status-label {label_cls}">{status_text}</span>
    {cost_html}
  </div>
</div>''')

    teammates_html = "\n".join(teammates_html_parts)

    # ── Build task cards grouped by date ──────────────────
    from collections import defaultdict
    today_str = datetime.now(TZ_CST).strftime("%Y-%m-%d")

    groups: dict[str, list] = defaultdict(list)
    for t in tasks:
        if t.get("startedAt"):
            d = datetime.fromtimestamp(t["startedAt"], tz=TZ_CST).strftime("%Y-%m-%d")
        else:
            d = today_str
        groups[d].append(t)

    def make_status_badge(status):
        label_map = {"running": "🔄 RUNNING", "done": "✅ DONE", "failed": "❌ FAILED",
                     "queued": "⏳ QUEUED", "paused": "⏸️ PAUSED"}
        label = label_map.get(status, status.upper())
        return f'<span class="status-badge {status}">{label}</span>'

    def make_task_card(t):
        status = t.get("status", "")
        label = t.get("label", "")
        skill = t.get("skill", "")
        tid_str = t.get("taskId", "")
        goal = t.get("successCriteria", "") or t.get("goal", "")
        rc = t.get("restartCount", 0)

        assignee_id = (
            t.get("assignedTo")
            or _assignee_to_teammate_id(skill)
            or _assignee_to_teammate_id(label)
        )
        # Find emoji for assignee
        assignee_emoji = ""
        if assignee_id:
            for tm in TEAMMATES:
                if tm["id"] == assignee_id:
                    assignee_emoji = tm["emoji"] + " " + assignee_id
                    break

        elapsed_html = ""
        est_remain_html = ""
        if t.get("startedAt"):
            elapsed_s = int(time.time() - t["startedAt"])
            h, m = divmod(elapsed_s // 60, 60)
            elapsed_str = f"{h}h{m:02d}m" if h else f"{m}m"
            elapsed_html = f'<span class="elapsed">运行 {elapsed_str}</span>'
            est = t.get("estimatedMinutes", 0)
            if est and status == "running":
                remain_min = max(0, est - elapsed_s // 60)
                est_remain_html = f'<span>预估剩余 {remain_min}m</span>'

        cost_raw = t.get("cost", 0) or 0
        if isinstance(cost_raw, dict):
            cost_raw = cost_raw.get("usd", 0)
        cost = cost_raw or 0
        budget_raw = t.get("budget", 0) or 0
        if isinstance(budget_raw, dict):
            budget_raw = budget_raw.get("budget_usd", 0)
        budget = budget_raw or 0
        cost_html = ""
        if cost or budget:
            cost_html = f'<span class="cost">¥{cost:.1f}{"/" + "¥"+str(int(budget)) if budget else ""}</span>'

        restart_html = f'<span class="restart-badge">⚠️ 重启{rc}次</span>' if rc > 0 else ""

        # Batch progress
        bp = t.get("batchProgress")
        batch_html = ""
        if bp:
            done_n = bp.get("completed", bp.get("done", 0))
            total = bp.get("total", 0)
            if total > 0:
                blocks = ""
                for i in range(total):
                    cls = "filled" if i < done_n else ""
                    blocks += f'<span class="progress-block {cls}"></span>'
                batch_html = f'''<div class="batch-progress">
  <div class="progress-track">{blocks}</div>
  <span class="progress-text">{done_n}/{total}</span>
</div>'''

        goal_html = f'<div class="task-goal">{goal}</div>' if goal else ""

        # Buttons
        if status in ("failed", "queued", "paused"):
            btns = f'''<button class="btn" onclick="trigger('restart','{tid_str}')">🔄 重启</button>
<button class="btn danger" onclick="trigger('skip','{tid_str}')">⏭️ 跳过</button>'''
        elif status == "running":
            btns = f'''<button class="btn" onclick="trigger('pause','{tid_str}')">⏸️ 暂停</button>'''
        else:
            btns = ""

        btns_html = f'<div class="task-btns">{btns}</div>' if btns else ""

        footer_parts = [elapsed_html, est_remain_html, cost_html]
        footer_inner = "".join(p for p in footer_parts if p)
        footer_html = f'<div class="task-footer">{footer_inner}{restart_html}</div>' if footer_inner or restart_html else ""

        return f'''<div class="task-card {status}">
  <div class="task-top">
    {make_status_badge(status)}
    <div class="task-meta-line">
      <span class="task-assignee">{assignee_emoji}</span>
      <span class="task-label">{label}</span>
    </div>
  </div>
  {goal_html}
  {batch_html}
  {footer_html}
  {btns_html}
</div>'''

    tasks_by_date_parts = []
    for date_str in sorted(groups.keys(), reverse=True):
        title = f"📅 {date_str}"
        if date_str == today_str:
            title += "（今天）"
        cards = "".join(make_task_card(t) for t in groups[date_str])
        tasks_by_date_parts.append(f'''<div class="date-group">
  <div class="date-group-title">{title}</div>
  {cards}
</div>''')

    if not tasks_by_date_parts:
        tasks_by_date_parts = ['''<div class="empty-state">
  <div class="icon">🌙</div>
  <div>暂无任务</div>
</div>''']

    tasks_by_date_html = "\n".join(tasks_by_date_parts)

    # ── Build skill profiles HTML ──────────────────────────
    all_profile_html_parts = []
    for tm in TEAMMATES:
        all_profile_html_parts.append(
            _build_skill_profile_html(tm["id"], tasks, events_lines)
        )
    all_profiles_html = "\n".join(all_profile_html_parts)

    # ── Alerts HTML ───────────────────────────────────────
    alerts_recent = list(reversed(alerts_lines[-10:]))
    alerts_html_parts = []
    for a in alerts_recent:
        ts = a.get("ts", 0)
        msg = a.get("detail", a.get("event", ""))
        time_str = datetime.fromtimestamp(ts).astimezone(TZ_CST).strftime("%H:%M") if ts else ""
        alerts_html_parts.append(f'''<div class="alert-card">
  <span class="alert-msg">⚠️ {msg}</span>
  <span class="alert-time">{time_str}</span>
</div>''')

    if not alerts_html_parts:
        alerts_html_parts = ['<div style="color:#484f58;font-size:11px;padding:8px 0">无告警</div>']
    alerts_html = "\n".join(alerts_html_parts)

    alert_count = len(alerts_recent)
    alerts_count_badge = f'<span class="count-badge">{alert_count}</span>' if alert_count > 0 else ""

    # ── Events HTML ───────────────────────────────────────
    EVENT_CLASS_MAP = {
        "phase_done": "phase_done",
        "task_registered": "registered",
        "crash_detected": "crash",
        "task_fail": "crash",
        "manual_restart": "warn",
        "auto_restart": "warn",
    }
    events_recent = list(reversed(events_lines[-20:]))
    events_html_parts = []
    for ev in events_recent:
        ts = ev.get("ts", 0)
        event_name = ev.get("event", "")
        task_id_short = (ev.get("taskId", "") or "")[:24]
        time_str = datetime.fromtimestamp(ts).astimezone(TZ_CST).strftime("%H:%M:%S") if ts else ""
        ev_cls = EVENT_CLASS_MAP.get(event_name, "")
        events_html_parts.append(f'''<div class="event-item {ev_cls}">
  <span class="event-time">{time_str}</span>
  <span class="event-name">{event_name}</span>
  <span class="event-task">{task_id_short}</span>
</div>''')

    if not events_html_parts:
        events_html_parts = ['<div style="color:#484f58;font-size:11px;padding:8px 0">无事件</div>']
    events_html = "\n".join(events_html_parts)

    # ── Topbar data ───────────────────────────────────────
    cpu_pct   = res.get("cpu_pct", 0)
    mem_pct   = res.get("mem_pct", 0)
    disk_pct  = res.get("disk_pct", 0)
    now_str   = datetime.now(TZ_CST).strftime("%Y-%m-%d %H:%M")

    # ── Read template and inject ───────────────────────────
    TEMPLATE = Path(__file__).parent / "dashboard_v2_template.html"
    try:
        html = TEMPLATE.read_text()
    except Exception:
        # fallback: minimal inline template
        html = "<html><body>{{TASKS_BY_DATE_HTML}}</body></html>"

    html = (html
        .replace("{{CPU_PCT}}", f"{cpu_pct:.1f}")
        .replace("{{MEM_PCT}}", f"{mem_pct:.1f}")
        .replace("{{DISK_PCT}}", f"{disk_pct:.1f}")
        .replace("{{RUNNING_N}}", str(len(running)))
        .replace("{{DONE_N}}", str(len(done)))
        .replace("{{FAILED_N}}", str(len(failed)))
        .replace("{{NOW_STR}}", now_str)
        .replace("{{TEAMMATES_HTML}}", teammates_html)
        .replace("{{TASKS_BY_DATE_HTML}}", tasks_by_date_html)
        .replace("{{SKILL_PROFILES_HTML}}", all_profiles_html)
        .replace("{{ALERTS_COUNT_BADGE}}", alerts_count_badge)
        .replace("{{ALERTS_HTML}}", alerts_html)
        .replace("{{EVENTS_HTML}}", events_html)
    )

    # ── Build Gantt Timeline HTML ─────────────────────────
    gantt_html = _build_gantt_html(tasks)

    # Append gantt below the three-column layout
    html = html.replace("</body>", gantt_html + "\n</body>")

    write_atomic(DASHBOARD, html)


# --- Session heartbeat helper ---

def _process_session_heartbeats(watch_data):
    """Read events.jsonl tail and update heartbeats for session-based tasks."""
    task_map = {t["taskId"]: t for t in watch_data.get("tasks", []) if t.get("sessionKey")}
    if not task_map:
        return
    try:
        lines = Path(EVENTS).read_text().strip().split("\n")[-50:]
        for line in lines:
            ev = json.loads(line)
            tid = ev.get("taskId")
            if tid in task_map:
                update_session_heartbeat(tid, task_map[tid]["sessionKey"])
    except Exception:
        pass


# --- Main poll loop ---

def poll_once():
    watch_data = read_json(WATCH)
    if not watch_data.get("tasks"):
        watch_data["tasks"] = []
    if not watch_data.get("queue"):
        watch_data["queue"] = []

    profiles = read_json(PROFILES_FILE).get("profiles", {})
    resources = check_system_resources()

    process_triggers(watch_data)
    _process_session_heartbeats(watch_data)

    new_alerts = []

    for task in watch_data["tasks"]:
        # Bug Fix: skip liveness check for already-terminal tasks
        if task.get("status") in ("done", "failed", "skipped"):
            continue
        if task.get("status") != "running":
            continue

        reason, detail = diagnose_crash(task, resources)
        if reason is None:
            continue

        append_event({"event": "crash_detected", "taskId": task["taskId"], "detail": f"{reason}: {detail}"})
        action, msg = decide_restart(task, reason, detail, resources, profiles)

        if action == "restart":
            task["restartCount"] = task.get("restartCount", 0) + 1
            task["startedAt"] = int(time.time())
            append_event({"event": "auto_restart", "taskId": task["taskId"], "detail": msg})
        elif action == "queue":
            task["status"] = "queued"
            watch_data["queue"].append({
                "taskId": task["taskId"],
                "enqueuedAt": int(time.time()),
                "reason": msg,
                "maxWaitMin": 60,
                "notifiedUser": True,
            })
            alert_msg = f"任务 {task['label']} 入队等待: {msg}"
            new_alerts.append(alert_msg)
            append_event({"event": "queued", "taskId": task["taskId"], "detail": msg})
        else:
            task["status"] = "failed"
            alert_msg = f"任务 {task['label']} 需人工介入: {msg}"
            new_alerts.append(alert_msg)
            append_event({"event": "task_fail", "taskId": task["taskId"], "detail": msg})

    process_queue(watch_data, resources, profiles)

    state = {
        "updated_at": datetime.now(TZ_CST).strftime("%Y-%m-%d %H:%M:%S"),
        "resources": resources,
        "tasks": watch_data["tasks"],
        "queue": watch_data["queue"],
        "summary": build_summary(watch_data, resources),
    }

    write_atomic(WATCH, json.dumps(watch_data, ensure_ascii=False, indent=2))
    write_atomic(STATE, json.dumps(state, ensure_ascii=False, indent=2))
    generate_dashboard(state)

    for msg in new_alerts:
        append_alert({"event": "alert", "detail": msg})
        send_feishu_alert(msg)

    return state


def build_summary(watch_data, resources):
    tasks = watch_data.get("tasks", [])
    r = len([t for t in tasks if t.get("status") == "running"])
    q = len([t for t in tasks if t.get("status") in ("queued", "paused")])
    d = len([t for t in tasks if t.get("status") == "done"])
    f = len([t for t in tasks if t.get("status") == "failed"])
    mem = resources.get("mem_pct", 0)
    return f"运行{r} 队列{q} 完成{d} 失败{f} | 内存{mem}% Remotion×{resources.get('remotion_instances',0)}"


# --- Entry point ---

def main():
    test_once = "--test-once" in sys.argv

    if not test_once:
        api_thread = Thread(target=start_api_server, daemon=True)
        api_thread.start()
        print(f"[Claw Manager] API server on 127.0.0.1:{API_PORT}")

    print(f"[Claw Manager] 守护进程启动 {'(测试模式)' if test_once else ''}")

    if test_once:
        state = poll_once()
        print(f"[Claw Manager] Poll 完成: {state['summary']}")
        print(f"[Claw Manager] state.json 已更新: {STATE}")
        print(f"[Claw Manager] dashboard.html 已生成: {DASHBOARD}")
        return

    while True:
        try:
            state = poll_once()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {state['summary']}")
        except Exception as e:
            print(f"[Claw Manager] Poll 错误: {e}", file=sys.stderr)
            append_event({"event": "daemon_error", "detail": str(e)})
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
