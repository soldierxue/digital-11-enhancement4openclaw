#!/usr/bin/env python3
"""Phase 4: Generate podcast metadata + Show Notes.

Uses LLM to generate:
  1. Title, description, tags (existing)
  2. Show Notes — structured listener-facing episode notes (NEW)
  3. Chapter markers from dialogue timing (existing, improved with LLM titles)

Show Notes format (inspired by 硅谷坐标 SV-Vector style):
  - Episode summary (1-2 sentences)
  - Key discussion points with timestamps
  - Notable quotes / golden sentences
  - Related links (original article)
  - Tags / keywords

Usage:
    python3 generate_metadata.py podcast-script.json \\
        --timing timing.json \\
        --article article.md \\
        --output metadata.json \\
        --show-notes-output show-notes.md
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


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def compute_turn_timestamps(timing: list, gap_ms: int = 400) -> dict:
    """Compute start timestamp for each turn number."""
    timestamps = {}
    current_ms = 0
    for t in timing:
        timestamps[t["turn"]] = current_ms / 1000  # seconds
        current_ms += t["duration"] * 1000 + gap_ms
    return timestamps


def generate_metadata_and_shownotes(script: list, timing: list, article_path: str,
                                     model: str, config: dict, gap_ms: int) -> dict:
    """Single LLM call to generate title, description, chapters, and show notes."""
    from llm_client import llm_completion

    podcast_name = config.get("podcast_name", "科技播客")
    host_name = config.get("host_name", "主持人")
    guest_name = config.get("guest_name", "嘉宾")

    # Compute timestamps for each turn
    turn_ts = compute_turn_timestamps(timing, gap_ms)

    # Build full dialogue with timestamps
    dialogue_with_ts = []
    for s in script:
        ts = turn_ts.get(s["turn"], 0)
        ts_str = format_time(ts)
        role_name = host_name if s["role"] == "host" else guest_name
        dialogue_with_ts.append(f"[{ts_str}] {role_name}: {s['text']}")

    full_dialogue = "\n\n".join(dialogue_with_ts)

    # Load article content if available
    article_content = ""
    article_title = ""
    if article_path and os.path.exists(os.path.expanduser(article_path)):
        with open(os.path.expanduser(article_path), encoding="utf-8") as f:
            raw = f.read()
        article_content = raw[:3000]
        # Try to extract title from frontmatter or first heading
        title_match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', raw, re.MULTILINE)
        if title_match:
            article_title = title_match.group(1)
        else:
            heading_match = re.search(r'^#\s+(.+)$', raw, re.MULTILINE)
            if heading_match:
                article_title = heading_match.group(1)

    total_duration = sum(t["duration"] for t in timing) + len(timing) * gap_ms / 1000

    prompt = f"""你是一个播客节目编辑，需要为以下播客节目生成完整的元数据和 Show Notes。

## 播客信息
- 播客名称：{podcast_name}
- 主持人：{host_name}
- 嘉宾：{guest_name}
- 总时长：{format_time(total_duration)}
{f'- 原文标题：{article_title}' if article_title else ''}

## 完整对话内容（含时间戳）

{full_dialogue}

{f'## 原文摘要（前3000字）：{chr(10)}{article_content}' if article_content else ''}

---

请生成以下 JSON（所有内容使用中文）：

{{
  "title": "播客标题（15-30字，吸引人，体现核心话题，不要用冒号分隔）",
  "subtitle": "副标题（10-20字，补充说明）",
  "description": "节目简介（150-250字，概述讨论内容和亮点，适合播客平台展示。语气轻松专业，像写给朋友的推荐语）",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5", "标签6", "标签7", "标签8"],
  "chapters": [
    {{
      "title": "章节标题（简短有力，4-10字）",
      "start_turn": 1,
      "summary": "这个章节讨论了什么（30-60字）"
    }}
  ],
  "highlights": [
    {{
      "turn": 5,
      "quote": "对话中的金句原文（选最有洞察力的 5-8 句）",
      "speaker": "host 或 guest"
    }}
  ],
  "show_notes_sections": [
    {{
      "heading": "段落标题",
      "points": ["要点1（含时间戳引用如 [03:45]）", "要点2", "要点3"]
    }}
  ],
  "one_liner": "一句话总结本期内容（30字以内，适合社交媒体分享）"
}}

## 要求
1. **chapters**：根据话题转换自然分段，通常 5-8 个章节，用 start_turn 标记起始轮次
2. **highlights**：选 5-8 句最精彩的金句，必须是对话原文
3. **show_notes_sections**：3-5 个主题段落，每段 3-5 个要点，要点中引用时间戳 [MM:SS]
4. 时间戳必须与对话中的实际时间戳对应
5. 风格参考科技播客（如硅谷坐标、硬地骇客、津津乐道），专业但不枯燥

只输出 JSON，不要其他文字。"""

    content = llm_completion(
        model=model,
        prompt=prompt,
        max_tokens=4000,
        temperature=0.7,
        config=config,
    ).strip()
    json_match = re.search(r"\{[\s\S]*\}", content)
    raw = json_match.group() if json_match else content
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Attempt repair: fix unescaped quotes
        raw = raw.replace('\u201c', '\\"').replace('\u201d', '\\"')
        raw = raw.replace('\u2018', "\\'").replace('\u2019', "\\'")
        return json.loads(raw)


def build_chapters_with_timestamps(chapters_raw: list, turn_timestamps: dict) -> list:
    """Resolve chapter start_turn to actual timestamps."""
    chapters = []
    for ch in chapters_raw:
        start_turn = ch.get("start_turn", 1)
        start_sec = turn_timestamps.get(start_turn, 0)
        chapters.append({
            "title": ch["title"],
            "start_time": round(start_sec, 1),
            "start_formatted": format_time(start_sec),
            "summary": ch.get("summary", ""),
        })
    return chapters


def build_highlights_with_timestamps(highlights_raw: list, turn_timestamps: dict,
                                      host_name: str, guest_name: str) -> list:
    """Resolve highlight turns to timestamps and speaker names."""
    highlights = []
    for h in highlights_raw:
        turn = h.get("turn", 1)
        ts = turn_timestamps.get(turn, 0)
        speaker = host_name if h.get("speaker") == "host" else guest_name
        highlights.append({
            "timestamp": format_time(ts),
            "quote": h["quote"],
            "speaker": speaker,
        })
    return highlights


def render_show_notes_markdown(metadata: dict, config: dict,
                                article_url: str = None) -> str:
    """Render Show Notes as a Markdown document."""
    podcast_name = config.get("podcast_name", "科技播客")
    host_name = config.get("host_name", "主持人")
    guest_name = config.get("guest_name", "嘉宾")

    lines = []
    lines.append(f"# 🎙️ {metadata['title']}")
    if metadata.get("subtitle"):
        lines.append(f"### {metadata['subtitle']}")
    lines.append("")
    lines.append(f"**{podcast_name}** | 时长 {metadata['duration_formatted']} | "
                 f"主持 {host_name} · 嘉宾 {guest_name}")
    lines.append("")

    # One-liner
    if metadata.get("one_liner"):
        lines.append(f"> {metadata['one_liner']}")
        lines.append("")

    # Description
    lines.append("## 📋 节目简介")
    lines.append("")
    lines.append(metadata.get("description", ""))
    lines.append("")

    # Chapters / Timeline
    if metadata.get("chapters"):
        lines.append("## ⏱️ 时间线")
        lines.append("")
        for ch in metadata["chapters"]:
            summary = f" — {ch['summary']}" if ch.get("summary") else ""
            lines.append(f"- **{ch['start_formatted']}** {ch['title']}{summary}")
        lines.append("")

    # Show Notes Sections
    if metadata.get("show_notes_sections"):
        lines.append("## 📝 Show Notes")
        lines.append("")
        for section in metadata["show_notes_sections"]:
            lines.append(f"### {section['heading']}")
            lines.append("")
            for point in section.get("points", []):
                lines.append(f"- {point}")
            lines.append("")

    # Highlights / Golden Quotes
    if metadata.get("highlights"):
        lines.append("## 💬 金句摘录")
        lines.append("")
        for h in metadata["highlights"]:
            lines.append(f"> 「{h['quote']}」 —— {h['speaker']} [{h['timestamp']}]")
            lines.append("")

    # Tags
    if metadata.get("tags"):
        lines.append("## 🏷️ 标签")
        lines.append("")
        lines.append(" ".join(f"#{t}" for t in metadata["tags"]))
        lines.append("")

    # Links
    lines.append("## 🔗 相关链接")
    lines.append("")
    if article_url:
        lines.append(f"- 原文：{article_url}")
    lines.append(f"- 播客：{podcast_name}")
    lines.append("")

    lines.append("---")
    lines.append(f"*本期节目由 AI 辅助生成，基于原创文章自动转换为双人对话播客。*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate podcast metadata + show notes")
    parser.add_argument("podcast_script", help="Path to podcast-script.json")
    parser.add_argument("--timing", required=True, help="Path to timing.json")
    parser.add_argument("--article", default=None, help="Original article path")
    parser.add_argument("--article-url", default=None, help="Original article URL (for show notes)")
    parser.add_argument("--output", required=True, help="Output metadata JSON path")
    parser.add_argument("--show-notes-output", default=None,
                        help="Output show notes Markdown path (default: same dir as --output, .show-notes.md)")
    parser.add_argument("--model", default=None, help="Model name (bedrock/<id> or minimax/<id>)")
    parser.add_argument("--gap-ms", type=int, default=400, help="Gap between turns (ms)")
    args = parser.parse_args()

    cfg = load_config()
    model = args.model or cfg.get("ai_model", "anthropic/claude-sonnet-4-20250514")
    host_name = cfg.get("host_name", "主持人")
    guest_name = cfg.get("guest_name", "嘉宾")

    with open(args.podcast_script, encoding="utf-8") as f:
        script = json.load(f)
    with open(args.timing, encoding="utf-8") as f:
        timing = json.load(f)

    print("📋 Generating podcast metadata + show notes...", flush=True)

    # Compute turn timestamps
    turn_ts = compute_turn_timestamps(timing, args.gap_ms)

    # Calculate total duration
    total_duration = sum(t["duration"] for t in timing)
    total_duration += len(timing) * args.gap_ms / 1000

    # Single LLM call for everything
    print(f"   Calling {model} for metadata + show notes...", flush=True)
    raw = generate_metadata_and_shownotes(script, timing, args.article, model, cfg, args.gap_ms)

    # Post-process: resolve turn numbers to real timestamps
    chapters = build_chapters_with_timestamps(raw.get("chapters", []), turn_ts)
    highlights = build_highlights_with_timestamps(raw.get("highlights", []), turn_ts,
                                                   host_name, guest_name)

    # Assemble metadata
    metadata = {
        "title": raw.get("title", "科技播客"),
        "subtitle": raw.get("subtitle", ""),
        "description": raw.get("description", ""),
        "one_liner": raw.get("one_liner", ""),
        "tags": raw.get("tags", []),
        "podcast_name": cfg.get("podcast_name", "科技播客"),
        "host": f"{host_name}",
        "guest": f"{guest_name}",
        "duration_seconds": round(total_duration, 1),
        "duration_formatted": format_time(total_duration),
        "total_turns": len(script),
        "host_turns": sum(1 for s in script if s["role"] == "host"),
        "guest_turns": sum(1 for s in script if s["role"] == "guest"),
        "chapters": chapters,
        "highlights": highlights,
        "show_notes_sections": raw.get("show_notes_sections", []),
    }

    if args.article:
        metadata["source_article"] = args.article
    if args.article_url:
        metadata["source_url"] = args.article_url

    # Write metadata JSON
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    # Write Show Notes Markdown
    show_notes_path = args.show_notes_output
    if not show_notes_path:
        base = os.path.splitext(args.output)[0]
        show_notes_path = base.replace("-metadata", "-show-notes") + ".md"

    show_notes_md = render_show_notes_markdown(metadata, cfg, args.article_url)
    with open(show_notes_path, "w", encoding="utf-8") as f:
        f.write(show_notes_md)

    print(f"✅ Metadata + Show Notes generated:", flush=True)
    print(f"   Title: {metadata['title']}", flush=True)
    print(f"   Subtitle: {metadata.get('subtitle', '')}", flush=True)
    print(f"   Duration: {metadata['duration_formatted']}", flush=True)
    print(f"   Chapters: {len(chapters)}", flush=True)
    print(f"   Highlights: {len(highlights)}", flush=True)
    print(f"   Show Notes sections: {len(metadata.get('show_notes_sections', []))}", flush=True)
    print(f"   Metadata: {args.output}", flush=True)
    print(f"   Show Notes: {show_notes_path}", flush=True)


if __name__ == "__main__":
    main()
