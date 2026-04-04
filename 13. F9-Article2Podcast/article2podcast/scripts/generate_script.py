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


def generate_dialogue_script(article_text: str, num_turns: int, model: str,
                              host_name: str, guest_name: str,
                              opening_line: str, closing_line: str) -> list:
    """Use LiteLLM to generate a podcast dialogue script from the article."""
    from litellm import completion

    opening_instruction = ""
    if opening_line:
        opening_instruction = f'\n   - 第 1 轮（host）的 text 必须以此开头："{opening_line}"'

    closing_instruction = ""
    if closing_line:
        closing_instruction = f'\n   - 最后一轮（host）的 text 必须以此结尾："{closing_line}"'

    prompt = f"""你是一个科技播客脚本编剧。请将以下文章改写为一期双人对话播客脚本，约 {num_turns} 轮对话。

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

{article_text[:10000]}
"""

    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=6000,
    )

    content = response.choices[0].message.content.strip()
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
    parser.add_argument("--turns", type=int, default=None, help="Number of dialogue turns")
    parser.add_argument("--model", default=None, help="LiteLLM model name")
    args = parser.parse_args()

    cfg = load_config()
    num_turns = args.turns or cfg.get("default_turns", 20)
    model = args.model or cfg.get("ai_model", "anthropic/claude-sonnet-4-20250514")
    host_name = cfg.get("host_name", "小薛")
    guest_name = cfg.get("guest_name", "老张")
    opening_line = cfg.get("opening_line", "")
    closing_line = cfg.get("closing_line", "")

    print(f"📖 Loading article: {args.article}", flush=True)
    article_text = load_article(args.article)
    print(f"   Article length: {len(article_text)} chars", flush=True)

    print(f"🤖 Generating {num_turns}-turn dialogue script with {model}...", flush=True)
    print(f"   Roles: {host_name} (host) + {guest_name} (guest)", flush=True)
    script = generate_dialogue_script(
        article_text, num_turns, model,
        host_name, guest_name, opening_line, closing_line
    )

    # Validate structure
    valid_roles = {"host", "guest"}
    for item in script:
        assert "turn" in item and "role" in item and "text" in item, \
            f"Invalid turn structure: {list(item.keys())}"
        assert item["role"] in valid_roles, f"Invalid role: {item['role']}"
        if "emotion" not in item:
            item["emotion"] = "cheerful" if item["role"] == "host" else "thoughtful"

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    total_chars = sum(len(s["text"]) for s in script)
    host_turns = sum(1 for s in script if s["role"] == "host")
    guest_turns = sum(1 for s in script if s["role"] == "guest")
    print(f"✅ Generated {len(script)} turns ({host_turns} host, {guest_turns} guest), ~{total_chars} chars", flush=True)
    print(f"   Output: {args.output}", flush=True)


if __name__ == "__main__":
    main()
