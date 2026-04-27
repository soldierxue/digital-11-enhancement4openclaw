#!/usr/bin/env python3
"""Phase 1: Generate a multi-speaker podcast dialogue script from an article.

Reads a Markdown file or URL and produces a JSON array of dialogue turns,
each containing: turn, role, text, emotion.

Usage:
    python3 generate_script.py <article_path_or_url> \
        --output podcast-script.json --turns 20
"""

import argparse
import json
import os
import re
import sys


def load_article(source: str) -> str:
    """Load article content from a file path or URL."""
    if source.startswith("http://") or source.startswith("https://"):
        import urllib.request
        req = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    else:
        with open(os.path.expanduser(source), encoding="utf-8") as f:
            return f.read()


def load_config() -> dict:
    """Load config.json from skill directory."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config.json"
    )
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------------------------
# Adaptive turn calculation based on article information density
# ---------------------------------------------------------------------------
# Assumptions for duration estimation:
#   - Average Chinese TTS speed: ~250 chars/min
#   - Each dialogue turn: 50-150 chars → avg ~100 chars → ~24 sec/turn
#   - 30-min podcast ≈ 7500 chars spoken ≈ 75 turns (upper bound)
#   - 5-min podcast  ≈ 1250 chars spoken ≈ 12 turns (lower bound)

MIN_TURNS = 12          # ~5 min podcast
MAX_TURNS = 75          # ~30 min podcast
CHARS_PER_TURN = 100    # average spoken chars per turn
TTS_CHARS_PER_MIN = 250 # Chinese TTS speaking rate


def estimate_information_density(article_text: str) -> float:
    """Return a density score (0.0-1.0) for the article.

    Heuristics considered:
      - code block ratio (code-heavy → lower spoken density)
      - heading count (more structure → more topics to cover)
      - unique technical term density
      - list / bullet point density
    """
    total_len = max(len(article_text), 1)

    # 1. Code blocks — strip them for density calc; they inflate char count
    #    but don't translate well to spoken dialogue
    code_blocks = re.findall(r"```[\s\S]*?```", article_text)
    code_chars = sum(len(b) for b in code_blocks)
    code_ratio = code_chars / total_len  # 0-1, higher = more code

    # 2. Headings → topic breadth
    headings = re.findall(r"^#{1,4}\s+.+", article_text, re.MULTILINE)
    heading_score = min(len(headings) / 20.0, 1.0)  # cap at 20 headings

    # 3. Bullet / numbered list items → detail density
    list_items = re.findall(r"^[\s]*[-*+]\s+|^\s*\d+\.\s+", article_text, re.MULTILINE)
    list_score = min(len(list_items) / 40.0, 1.0)

    # 4. Prose length (excluding code)
    prose_len = total_len - code_chars
    prose_score = min(prose_len / 8000.0, 1.0)  # 8000 chars = fairly long article

    # Weighted combination
    density = (
        0.35 * prose_score
        + 0.25 * heading_score
        + 0.20 * list_score
        + 0.20 * (1.0 - code_ratio)  # less code → more speakable content
    )
    return round(max(0.0, min(density, 1.0)), 3)


def compute_adaptive_turns(article_text: str, max_duration_min: int = 30) -> int:
    """Compute the number of dialogue turns based on article content.

    Returns a value between MIN_TURNS and MAX_TURNS, capped by max_duration_min.
    """
    density = estimate_information_density(article_text)

    # Map density linearly to turn range
    duration_cap_turns = int(max_duration_min * TTS_CHARS_PER_MIN / CHARS_PER_TURN)
    upper = min(MAX_TURNS, duration_cap_turns)

    turns = int(MIN_TURNS + density * (upper - MIN_TURNS))
    turns = max(MIN_TURNS, min(turns, upper))

    return turns


def generate_dialogue_script(article_text: str, num_turns: int, model: str,
                              host_name: str, guest_name: str,
                              opening_line: str, closing_line: str,
                              config: dict = None) -> list:
    """Generate a podcast dialogue script from the article via LLM."""
    from llm_client import llm_completion

    opening_instruction = ""
    if opening_line:
        opening_instruction = f'\n   - 第 1 轮（host）的 text 必须以此开头："{opening_line}"'

    closing_instruction = ""
    if closing_line:
        closing_instruction = f'\n   - 最后一轮（host）的 text 必须以此结尾："{closing_line}"'

    # Estimate podcast duration for the prompt
    est_duration_min = round(num_turns * CHARS_PER_TURN / TTS_CHARS_PER_MIN)

    # Scale max_tokens with turn count: ~80 tokens per turn is a safe estimate
    max_tokens = max(6000, num_turns * 120)

    # For longer articles with many turns, allow more source text
    article_budget = min(len(article_text), 6000 + num_turns * 100)

    prompt = f"""你是一个科技播客脚本编剧。请将以下文章改写为一期双人对话播客脚本。

## 目标时长与轮次

- 目标时长：约 **{est_duration_min} 分钟**
- 对话轮次：约 **{num_turns} 轮**（根据文章信息密度自动计算）
- 如果文章内容丰富，请充分展开讨论，不要压缩遗漏重要信息
- 如果文章较短或信息密度低，保持精炼，不要注水

## 角色设定

- **{host_name}**（host）：播客主持人，负责引导话题、提问、总结。语气轻松专业，善于用通俗语言解释复杂概念。
- **{guest_name}**（guest）：技术嘉宾，负责深入解读、举例说明、分享独到观点。语气热情有见地，喜欢用具体案例和数据说话。

## 输出格式

输出 JSON 数组，每个元素包含：
- "turn": 序号 (1-{num_turns})
- "role": "host" 或 "guest"
- "text": 对话内容（50-150 字，口语化）
- "emotion": 情感标签，从以下选择：cheerful, thoughtful, excited, serious, curious, humorous

## 对话风格要求

1. **自然对话体**：像两个朋友在聊天，不是念稿
2. **互动感强**：有追问、补充、认同、反驳
3. **语气词自然**：适当使用"对"、"没错"、"这个很有意思"、"说到这个"等
4. **信息密度高**：每轮对话都要有实质内容，不要空洞寒暄
5. **节奏感**：长短交替，有时一句话回应，有时展开讲

## 结构要求

- 第 1-2 轮：开场寒暄 + 主题引入{opening_instruction}
- 第 3-{num_turns-2} 轮：按文章逻辑逐层深入讨论
  - 每个要点由 host 提问/引导，guest 解答/展开
  - 穿插具体数据、案例、类比
  - 适当加入个人观点和行业洞察
- 最后 2 轮：总结要点 + 展望 + 结束语{closing_instruction}

## 注意事项

- host 和 guest 交替发言（允许偶尔同一角色连续 2 轮）
- 每轮 50-150 字，不要太长
- 保持科技博主的专业感，但不要学术化
- 只输出 JSON，不要其他文字

## 文章内容

{article_text[:article_budget]}
"""

    content = llm_completion(
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=0.8,
        config=config,
    ).strip()
    json_match = re.search(r"\[[\s\S]*\]", content)
    raw = json_match.group() if json_match else content
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Attempt repair: fix unescaped quotes in text values
        import re as _re
        # Replace smart quotes
        raw = raw.replace('\u201c', '\\"').replace('\u201d', '\\"')
        raw = raw.replace('\u2018', "\\'").replace('\u2019', "\\'")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try line-by-line repair: find objects individually
            objects = []
            for m in _re.finditer(r'\{[^{}]+\}', raw):
                try:
                    obj = json.loads(m.group())
                    objects.append(obj)
                except json.JSONDecodeError:
                    continue
            if objects:
                return objects
            raise


def main():
    parser = argparse.ArgumentParser(description="Generate podcast dialogue script")
    parser.add_argument("article", help="Path to Markdown file or URL")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--turns", type=int, default=None,
                        help="Number of dialogue turns (omit to auto-detect from article density)")
    parser.add_argument("--max-duration", type=int, default=30,
                        help="Maximum podcast duration in minutes (default: 30)")
    parser.add_argument("--model", default=None, help="Model name (bedrock/<id> or minimax/<id>)")
    args = parser.parse_args()

    cfg = load_config()
    model = args.model or cfg.get("ai_model", "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0")
    host_name = cfg.get("host_name", "小薛")
    guest_name = cfg.get("guest_name", "老张")
    opening_line = cfg.get("opening_line", "")
    closing_line = cfg.get("closing_line", "")

    print(f"📖 Loading article: {args.article}", flush=True)
    article_text = load_article(args.article)
    print(f"   Article length: {len(article_text)} chars", flush=True)

    # Determine turn count: explicit > auto-adaptive > config default
    if args.turns:
        num_turns = args.turns
        print(f"   Turn count: {num_turns} (explicit --turns)", flush=True)
    else:
        density = estimate_information_density(article_text)
        num_turns = compute_adaptive_turns(article_text, args.max_duration)
        est_min = round(num_turns * CHARS_PER_TURN / TTS_CHARS_PER_MIN)
        print(f"   Information density: {density:.2f}", flush=True)
        print(f"   Adaptive turns: {num_turns} (~{est_min} min podcast, "
              f"max {args.max_duration} min)", flush=True)

    print(f"🤖 Generating {num_turns}-turn dialogue script with {model}...", flush=True)
    print(f"   Roles: {host_name} (host) + {guest_name} (guest)", flush=True)
    script = generate_dialogue_script(
        article_text, num_turns, model,
        host_name, guest_name, opening_line, closing_line,
        config=cfg
    )

    # Validate structure
    valid_roles = {"host", "guest"}
    for item in script:
        assert "turn" in item and "role" in item and "text" in item, \
            f"Invalid turn structure: {list(item.keys())}"
        assert item["role"] in valid_roles, f"Invalid role: {item['role']}"
        if "emotion" not in item:
            item["emotion"] = "cheerful" if item["role"] == "host" else "thoughtful"

    # Detect degenerate repetition: if the same text appears in multiple turns,
    # the LLM likely got stuck in a loop. Warn and deduplicate.
    seen_texts = {}
    duplicates = []
    for item in script:
        normalized = item["text"].strip()
        if normalized in seen_texts:
            duplicates.append((item["turn"], seen_texts[normalized]))
        else:
            seen_texts[normalized] = item["turn"]

    if duplicates:
        print(f"⚠️  检测到 {len(duplicates)} 处重复对话（LLM 退化）：", flush=True)
        for dup_turn, orig_turn in duplicates[:5]:
            print(f"     Turn {dup_turn} 与 Turn {orig_turn} 内容完全相同", flush=True)
        # Remove duplicate turns, keeping the first occurrence
        dup_turns = {d[0] for d in duplicates}
        original_count = len(script)
        script = [s for s in script if s["turn"] not in dup_turns]
        # Re-number turns sequentially
        for i, item in enumerate(script):
            item["turn"] = i + 1
        print(f"     已去重: {original_count} → {len(script)} 轮", flush=True)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    total_chars = sum(len(s["text"]) for s in script)
    host_turns = sum(1 for s in script if s["role"] == "host")
    guest_turns = sum(1 for s in script if s["role"] == "guest")
    est_duration = round(total_chars / TTS_CHARS_PER_MIN, 1)
    print(f"✅ Generated {len(script)} turns ({host_turns} host, {guest_turns} guest), "
          f"~{total_chars} chars, ~{est_duration} min", flush=True)
    print(f"   Output: {args.output}", flush=True)


if __name__ == "__main__":
    main()
