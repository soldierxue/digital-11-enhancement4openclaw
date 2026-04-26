#!/usr/bin/env python3
"""Phase 1: Split an article into a speech script using AI.

Reads a Markdown file or URL and produces a JSON array of slide objects,
each containing: slide, title, speech, visual.

Usage:
    python3 split_article.py <article_path_or_url> --output speech-script.json --slides 10
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
        # Simple HTML → text stripping (good enough for AI processing)
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    else:
        with open(os.path.expanduser(source), encoding="utf-8") as f:
            return f.read()


def generate_speech_script(article_text: str, num_slides: int, model: str) -> list:
    """Use LiteLLM to generate a speech script from the article."""
    from litellm import completion

    prompt = f"""你是一个视频脚本编剧。请将以下文章改写为 {num_slides} 段演讲稿，用于制作口播短视频。

## 要求

1. 输出 JSON 数组，每个元素包含：
   - "slide": 序号 (1-{num_slides})
   - "title": 幻灯片标题（简短有力，5-15 字）
   - "speech": 口播文本（200-300 字，口语化、短句、设问、数据支撑。每段必须至少 200 字以保证 40-50 秒时长）
   - "visual": 视觉描述（英文，用于搜索配图，描述画面内容和氛围）
   - "key_facts": 结构化数据对象（仅中间段落需要，第1段开场和最后一段不需要）

2. key_facts 字段说明（为每个中间段落选择最匹配的类型）：
   - **stats**: 大数字卡片，2-4 个关键数据点。items 数组中每个元素包含 value（数字/百分比）、label（说明）、color（十六进制色值）
   - **list**: 图标列表，3-5 条要点。items 数组中每个元素包含 icon（emoji）、title（标题）、desc（简短描述）、color（十六进制色值）
   - **comparison**: 对比视图，2 列 "之前 vs 之后" 或 "A vs B"。items 包含 left_title、right_title、left_items（数组）、right_items（数组），每个 item 有 text 和 icon
   - **quote**: 引言。items 包含 text（引用原文）和 source（来源）
   - **grid**: 2×2 网格，4 个概念/维度。items 数组中每个元素包含 icon（emoji）、title（标题）、desc（简短描述）、color（十六进制色值）

   示例（stats 类型）：
   ```json
   "key_facts": {{
     "type": "stats",
     "items": [
       {{"value": "1.2亿", "label": "年化 Sales Pipeline", "color": "#22d3ee"}},
       {{"value": "90%", "label": "试点项目用错误方法", "color": "#fb923c"}}
     ]
   }}
   ```

3. 风格规范：
   - 第 1 段 = 开场引入（自我介绍 + 主题预告），不需要 key_facts
   - 最后一段 = 总结呼吁（3 条建议 + 金句收尾），不需要 key_facts
   - 中间段落 = 按文章逻辑拆分，每段聚焦一个要点，必须包含 key_facts
   - 口播风格：像给朋友讲课一样，不要书面语
   - 选择颜色时请使用高对比度、醒目的颜色如 #22d3ee #fb923c #4ade80 #f87171 #facc15 #c084fc #60a5fa

4. 只输出 JSON，不要其他文字。

## 文章内容

{article_text[:8000]}
"""

    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=8000,
    )

    content = response.choices[0].message.content.strip()
    # Extract JSON from potential markdown code blocks
    json_match = re.search(r"\[[\s\S]*\]", content)
    raw = json_match.group() if json_match else content

    def try_parse(s):
        """Try parsing JSON, with progressive fixes."""
        # Attempt 1: direct parse
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
        # Attempt 2: remove control chars
        import re as _re
        cleaned = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # Attempt 3: fix smart quotes (common LLM mistake)
        cleaned = cleaned.replace('\u201c', '\\"').replace('\u201d', '\\"')
        cleaned = cleaned.replace('\u2018', "\\'").replace('\u2019', "\\'")
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        return None

    result = try_parse(raw)
    if result is not None:
        return result

    # Last resort: retry generation with lower temperature
    for attempt in range(2):
        print(f"⚠️ JSON parse failed, retrying generation (attempt {attempt+2}/3)...", flush=True)
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=8000,
        )
        content2 = response.choices[0].message.content.strip()
        json_match2 = re.search(r"\[[\s\S]*\]", content2)
        raw2 = json_match2.group() if json_match2 else content2
        result = try_parse(raw2)
        if result is not None:
            return result

    raise ValueError(f"Failed to parse speech script JSON after 3 attempts. Last output:\n{raw2[:500]}")


def main():
    parser = argparse.ArgumentParser(description="Split article into speech script")
    parser.add_argument("article", help="Path to Markdown file or URL")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--slides", type=int, default=10, help="Number of slides")
    parser.add_argument("--model", default="anthropic/claude-sonnet-4-20250514",
                        help="LiteLLM model name")
    args = parser.parse_args()

    print(f"📖 Loading article: {args.article}", flush=True)
    article_text = load_article(args.article)
    print(f"   Article length: {len(article_text)} chars", flush=True)

    print(f"🤖 Generating {args.slides}-slide speech script with {args.model}...", flush=True)
    script = generate_speech_script(article_text, args.slides, args.model)

    # Validate structure
    for item in script:
        assert "slide" in item and "title" in item and "speech" in item and "visual" in item, \
            f"Invalid slide structure: {list(item.keys())}"
        # key_facts is optional (expected for middle slides)
        if "key_facts" in item:
            kf = item["key_facts"]
            if kf is None:
                # AI returned null, remove it
                del item["key_facts"]
            else:
                assert isinstance(kf, dict) and "type" in kf and kf["type"] in ("stats", "list", "comparison", "quote", "grid"), \
                    f"Invalid key_facts type: {kf.get('type') if isinstance(kf, dict) else kf}"

    os.makedirs(os.path.dirname(args.output), exist_ok=True) if os.path.dirname(args.output) else None
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    total_chars = sum(len(s["speech"]) for s in script)
    print(f"✅ Generated {len(script)} slides, ~{total_chars} chars total", flush=True)
    print(f"   Output: {args.output}", flush=True)


if __name__ == "__main__":
    main()
