#!/usr/bin/env python3
"""Task Parser — 从对话/命令行提炼结构化任务并注册到 watch.json"""

import argparse, json, os, sys, time, uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

BASE = Path.home() / ".openclaw" / "claw-manager"
WATCH = BASE / "watch.json"
PROFILES_FILE = BASE / "task_profiles.json"
LITELLM_URL = "http://localhost:4000/chat/completions"
EVENTS = BASE / "events.jsonl"

# 北京时间 timezone
TZ_CST = timezone(timedelta(hours=8))

SYSTEM_PROMPT = """你是 OpenClaw 任务解析器。根据用户描述，输出一个 JSON 对象（不要 markdown 包裹）：
{
  "label": "简短标签",
  "skill": "匹配的 skill 名称（article2video/weixin-publisher/channels-publisher/tech-updates-writer/tech-updates-collector/unknown）",
  "estimatedMinutes": 预估分钟数,
  "stateFile": "对应 skill 的 state.json 路径（如 ~/.openclaw/skills/SKILL/state.json）",
  "successCriteria": "成功判定条件描述",
  "autoRestart": true或false,
  "maxRestarts": 最大重启次数
}
只输出 JSON，不要其他文字。"""

def parse_with_llm(label, desc, context=""):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context:
        messages.append({"role": "user", "content": f"最近对话上下文:\n{context}"})
    messages.append({"role": "user", "content": f"任务标签: {label}\n任务描述: {desc}"})

    try:
        r = requests.post(LITELLM_URL, json={
            "model": "claude-sonnet-4-20250514",
            "messages": messages,
            "temperature": 0,
            "max_tokens": 500,
        }, timeout=30)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(content)
    except Exception as e:
        print(f"[TaskParser] LLM 调用失败: {e}，使用本地推断", file=sys.stderr)
        return None

def local_infer(label, desc, skill=None):
    """Fallback: infer task structure without LLM"""
    profiles = json.loads(PROFILES_FILE.read_text()).get("profiles", {}) if PROFILES_FILE.exists() else {}

    if not skill:
        desc_lower = (desc + label).lower()
        if "video" in desc_lower or "视频" in desc_lower:
            skill = "article2video"
        elif "weixin" in desc_lower or "公众号" in desc_lower or "微信" in desc_lower:
            skill = "weixin-publisher"
        elif "channel" in desc_lower or "视频号" in desc_lower:
            skill = "channels-publisher"
        elif "writ" in desc_lower or "写作" in desc_lower or "writer" in desc_lower:
            skill = "tech-updates-writer"
        elif "collect" in desc_lower or "采集" in desc_lower:
            skill = "tech-updates-collector"
        else:
            skill = "unknown"

    profile = profiles.get(skill, {})
    return {
        "label": label,
        "skill": skill,
        "estimatedMinutes": profile.get("avg_duration_min", 30),
        "stateFile": str(Path.home() / f".openclaw/skills/{skill}/state.json"),
        "successCriteria": "任务正常完成",
        "autoRestart": profile.get("auto_restart", False),
        "maxRestarts": profile.get("max_restarts", 0),
    }

def register_task(task_info, args):
    watch = json.loads(WATCH.read_text()) if WATCH.exists() else {"tasks": [], "queue": []}
    
    # 北京时间今日日期
    now_cst = datetime.now(TZ_CST)
    today_str = now_cst.strftime("%Y-%m-%d")
    
    task = {
        "taskId": f"{task_info['label']}-{uuid.uuid4().hex[:6]}",
        "label": task_info["label"],
        "skill": task_info["skill"],
        "status": "running",
        "pid": getattr(args, 'pid', None),
        "stateFile": task_info.get("stateFile"),
        "startedAt": int(time.time()),
        "estimatedMinutes": task_info.get("estimatedMinutes", 30),
        "autoRestart": task_info.get("autoRestart", False),
        "maxRestarts": task_info.get("maxRestarts", 0),
        "restartCount": 0,
        "successCriteria": task_info.get("successCriteria", ""),
        "sessionKey": task_info.get("sessionKey"),
        # Phase 1 新增字段
        "assignedTo": getattr(args, 'assigned_to', None) or task_info.get("assignedTo"),
        "goal": getattr(args, 'goal', None) or task_info.get("goal", ""),
        "project": getattr(args, 'project', None) or task_info.get("project", ""),
        "dependsOn": _parse_list(getattr(args, 'depends_on', None)) or task_info.get("dependsOn", []),
        "date": getattr(args, 'date', None) or task_info.get("date", today_str),
        "cost": {
            "tokens_in": 0,
            "tokens_out": 0,
            "usd": 0.0,
            "budget_usd": float(getattr(args, 'budget_usd', None) or task_info.get("cost", {}).get("budget_usd", 0.0))
        },
        "batchProgress": task_info.get("batchProgress", None),
    }
    
    watch["tasks"].append(task)
    WATCH.write_text(json.dumps(watch, ensure_ascii=False, indent=2))

    # Log event
    with open(EVENTS, "a") as f:
        f.write(json.dumps({"ts": int(time.time()), "event": "task_registered", "taskId": task["taskId"], "detail": task["label"]}, ensure_ascii=False) + "\n")

    return task

def _parse_list(val):
    """Parse comma-separated string into list, or return empty list."""
    if not val:
        return []
    if isinstance(val, list):
        return val
    return [v.strip() for v in str(val).split(",") if v.strip()]

def main():
    parser = argparse.ArgumentParser(description="OpenClaw Task Parser")
    parser.add_argument("--label", required=True, help="任务标签")
    parser.add_argument("--desc", required=True, help="任务描述")
    parser.add_argument("--skill", default=None, help="直接指定 skill（跳过 LLM）")
    parser.add_argument("--context", default="", help="最近对话上下文")
    parser.add_argument("--no-llm", action="store_true", help="不调用 LLM，使用本地推断")
    parser.add_argument("--session-key", default=None, help="子代理 session key（无本地 PID 时用于心跳检测）")
    parser.add_argument("--pid", default=None, type=int, help="本地进程 PID（本地脚本任务用）")
    parser.add_argument("--state-file", default=None, dest="state_file", help="任务状态文件路径")
    # Phase 1 新增参数
    parser.add_argument("--assigned-to", default=None, dest="assigned_to", help="负责的队友角色名（如 Quill, Scout）")
    parser.add_argument("--goal", default=None, help="SMART 目标描述")
    parser.add_argument("--project", default=None, help="所属项目/流水线")
    parser.add_argument("--depends-on", default=None, dest="depends_on", help="依赖的 taskId（逗号分隔）")
    parser.add_argument("--date", default=None, help="日期（格式 YYYY-MM-DD，默认今天北京时间）")
    parser.add_argument("--budget-usd", default=None, type=float, dest="budget_usd", help="预算上限（USD）")
    args = parser.parse_args()

    if args.no_llm or args.skill:
        task_info = local_infer(args.label, args.desc, args.skill)
    else:
        task_info = parse_with_llm(args.label, args.desc, args.context)
        if not task_info:
            task_info = local_infer(args.label, args.desc)

    task_info["label"] = args.label
    if args.session_key:
        task_info["sessionKey"] = args.session_key
    if args.state_file:
        task_info["stateFile"] = args.state_file
    task = register_task(task_info, args)
    print(json.dumps(task, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
