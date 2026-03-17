"""usage_tracker.py — Dual-track: Kiro Credits + Claude API tokens."""

import json, os
from datetime import datetime, timezone
from pathlib import Path

STATS_FILE = os.environ.get("USAGE_STATS_FILE", "usage_stats.json")

CLAUDE_PRICING = {
    "input":       3.00,   # claude-sonnet-4 per 1M tokens
    "output":     15.00,
    "cache_read":  0.30,
}


def _load() -> dict:
    try:
        with open(STATS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"tasks": [], "totals": {}}


def _save(data: dict):
    with open(STATS_FILE, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')


def record_task(task_name, kiro_credits=0.0, kiro_context_pct=0.0,
                kiro_tool_calls=0, claude_input=0, claude_output=0,
                claude_cache_read=0) -> dict:
    data = _load()
    entry = {
        "id": len(data["tasks"]) + 1,
        "task": task_name,
        "ts": datetime.now(timezone.utc).isoformat(),
        "kiro": {"credits": kiro_credits, "context_pct": kiro_context_pct,
                 "tool_calls": kiro_tool_calls},
        "claude": {
            "input": claude_input, "output": claude_output,
            "cache_read": claude_cache_read,
            "cost_usd": round(
                claude_input * CLAUDE_PRICING["input"] / 1e6
                + claude_output * CLAUDE_PRICING["output"] / 1e6
                + claude_cache_read * CLAUDE_PRICING["cache_read"] / 1e6, 6),
        },
    }
    data["tasks"].append(entry)
    t = data["totals"]
    t["kiro_credits"]  = t.get("kiro_credits", 0) + kiro_credits
    t["claude_input"]  = t.get("claude_input", 0) + claude_input
    t["claude_output"] = t.get("claude_output", 0) + claude_output
    _save(data)
    return entry
