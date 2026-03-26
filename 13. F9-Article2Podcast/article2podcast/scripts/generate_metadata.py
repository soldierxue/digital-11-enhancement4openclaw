#!/usr/bin/env python3
"""Phase 4: Generate podcast metadata (title, description, chapters).

Uses LLM to generate a compelling title and description,
and creates chapter markers from the dialogue timing.

Usage:
    python3 generate_metadata.py podcast-script.json \
        --timing timing.json \
        --article article.md \
        --output metadata.json
"""

import argparse
import json
import os
import re
import sys


def load_config() -> dict:
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config.json"
    )
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def generate_chapters(script: list, timing: list, gap_ms: int = 400) -> list:
    """Generate chapter markers from dialogue timing.

    Groups consecutive turns about the same topic into chapters.
    """
    chapters = []
    current_offset_ms = 0

    # Simple approach: create a chapter every ~5 turns
    chapter_interval = max(3, len(timing) // 5)

    for i, t in enumerate(timing):
        if i % chapter_interval == 0:
            # Find corresponding script entry for context
            script_entry = next(
                (s for s in script if s["turn"] == t["turn"]), None
            )
            label = f"Part {len(chapters) + 1}"
            if script_entry:
                text_preview = script_entry["text"][:30].strip()
                label = text_preview + "..."

            chapters.append({
                "start_ms": int(current_offset_ms),
                "start_formatted": format_time(current_offset_ms / 1000),
                "label": label,
            })

        current_offset_ms += t["duration"] * 1000 + gap_ms

    return chapters


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def generate_title_and_desc(script: list, article_path: str, model: str,
                             podcast_name: str) -> dict:
    """Use LLM to generate podcast title and description."""
    from litellm import completion

    # Collect dialogue text for context
    dialogue_preview = "\n".join(
        f"[{s['role']}] {s['text']}" for s in script[:10]
    )

    # Load article title if available
    article_hint = ""
    if article_path and os.path.exists(os.path.expanduser(article_path)):
        with open(os.path.expanduser(article_path), encoding="utf-8") as f:
            first_lines = f.read(500)
        article_hint = f"\n原文开头：\n{first_lines}"

    prompt = f"""请为以下科技播客节目生成标题和描述。

播客名称：{podcast_name}

对话预览：
{dialogue_preview}
{article_hint}

请输出 JSON：
{{
  "title": "播客标题（15-30字，吸引人，体现核心话题）",
  "description": "播客描述（100-200字，概述讨论内容和亮点，适合在播客平台展示）",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"]
}}

只输出 JSON，不要其他文字。"""

    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500,
    )

    content = response.choices[0].message.content.strip()
    json_match = re.search(r"\{[\s\S]*\}", content)
    if json_match:
        return json.loads(json_match.group())
    return json.loads(content)


def main():
    parser = argparse.ArgumentParser(description="Generate podcast metadata")
    parser.add_argument("podcast_script", help="Path to podcast-script.json")
    parser.add_argument("--timing", required=True, help="Path to timing.json")
    parser.add_argument("--article", default=None, help="Original article path")
    parser.add_argument("--output", required=True, help="Output metadata JSON path")
    parser.add_argument("--model", default=None, help="LiteLLM model name")
    parser.add_argument("--gap-ms", type=int, default=400, help="Gap between turns (ms)")
    args = parser.parse_args()

    cfg = load_config()
    model = args.model or cfg.get("ai_model", "anthropic/claude-sonnet-4-20250514")
    podcast_name = cfg.get("podcast_name", "科技播客")

    with open(args.podcast_script, encoding="utf-8") as f:
        script = json.load(f)
    with open(args.timing, encoding="utf-8") as f:
        timing = json.load(f)

    print("📋 Generating podcast metadata...", flush=True)

    # Generate chapters
    chapters = generate_chapters(script, timing, args.gap_ms)
    print(f"   Chapters: {len(chapters)}", flush=True)

    # Generate title and description
    print(f"   Generating title/description with {model}...", flush=True)
    meta = generate_title_and_desc(script, args.article, model, podcast_name)

    # Calculate total duration
    total_duration = sum(t["duration"] for t in timing)
    total_duration += len(timing) * args.gap_ms / 1000  # add gaps

    # Assemble metadata
    metadata = {
        "title": meta.get("title", "科技播客"),
        "description": meta.get("description", ""),
        "tags": meta.get("tags", []),
        "podcast_name": podcast_name,
        "duration_seconds": round(total_duration, 1),
        "duration_formatted": format_time(total_duration),
        "total_turns": len(script),
        "host_turns": sum(1 for s in script if s["role"] == "host"),
        "guest_turns": sum(1 for s in script if s["role"] == "guest"),
        "chapters": chapters,
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"✅ Metadata generated:", flush=True)
    print(f"   Title: {metadata['title']}", flush=True)
    print(f"   Duration: {metadata['duration_formatted']}", flush=True)
    print(f"   Chapters: {len(chapters)}", flush=True)
    print(f"   Output: {args.output}", flush=True)


if __name__ == "__main__":
    main()
