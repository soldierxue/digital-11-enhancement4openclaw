#!/usr/bin/env python3
"""generate_covers.py — 播客封面图生成（9:16 竖版）

根据文章内容生成多张 9:16 竖版播客封面备选图。
使用 AWS Bedrock SD3.5 Large 生成，LiteLLM 生成 prompt。

用法:
    python3 generate_covers.py <article_path> \
        --output-dir covers/ \
        --styles cyberpunk scifi pixel comic ukiyoe \
        --slug my-article
"""

import argparse
import base64
import json
import os
import re
import sys

import boto3

# 预定义封面风格
COVER_STYLES = {
    "cyberpunk": {
        "name": "赛博朋克",
        "style_prompt": "cyberpunk neon city, digital art, glowing circuits, futuristic technology, dark background with neon lights, highly detailed, cinematic lighting"
    },
    "scifi": {
        "name": "科幻",
        "style_prompt": "science fiction concept art, space station, holographic displays, advanced technology, clean futuristic design, volumetric lighting, ultra detailed"
    },
    "pixel": {
        "name": "像素风",
        "style_prompt": "pixel art style, retro game aesthetic, 16-bit graphics, vibrant colors, nostalgic digital art, clean pixel design"
    },
    "comic": {
        "name": "漫画风",
        "style_prompt": "manga comic style illustration, bold lines, dramatic composition, vibrant colors, Japanese anime aesthetic, high contrast"
    },
    "ukiyoe": {
        "name": "浮世绘",
        "style_prompt": "ukiyo-e Japanese woodblock print style, traditional Asian art, waves and clouds, elegant composition, muted earth tones with accent colors"
    },
}

NEGATIVE_PROMPT = "text, words, letters, numbers, watermark, blurry, low quality, deformed, ugly, nsfw, photograph of real people, faces"


def load_article(path: str) -> str:
    """Load article content, strip YAML front matter."""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    # Strip YAML front matter
    content = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)
    return content[:3000]  # First 3000 chars for context


def generate_image_prompts(article_text: str, styles: list) -> dict:
    """Use kiro-cli to generate image prompts based on article content."""
    import shutil
    import subprocess
    
    # ANSI escape sequence regex
    _ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
    
    style_desc = "、".join(
        COVER_STYLES[s]["name"] for s in styles if s in COVER_STYLES
    )
    
    prompt = (
        f"基于以下文章内容，为每种视觉风格各生成一段英文文生图提示词。\n"
        f"要求：\n"
        f"1. 封面是 9:16 竖版（手机屏幕比例），用于播客封面\n"
        f"2. 每段 prompt 适合 Stable Diffusion 模型，50-80 个英文单词\n"
        f"3. 画面要能表达文章主题，但不要包含任何文字\n"
        f"4. 构图要适合竖版，中心焦点明确\n"
        f"5. 末尾加上 'vertical 9:16 aspect ratio, podcast cover art, high quality, detailed'\n"
        f"风格列表：{style_desc}。\n"
        f"输出严格 JSON 格式，key 为英文风格名："
        f'{{"cyberpunk": "...", "scifi": "...", "pixel": "...", '
        f'"comic": "...", "ukiyoe": "..."}}\n'
        f"只输出 JSON，不要输出任何其他内容。\n\n"
        f"文章内容（前 1500 字）：\n{article_text[:1500]}"
    )
    
    # Try kiro-cli first
    kiro_path = shutil.which("kiro-cli")
    if kiro_path:
        try:
            print("  使用 kiro-cli 生成定制化 prompt...", flush=True)
            result = subprocess.run(
                ["kiro-cli", "chat", "--no-interactive", "--trust-all-tools", prompt],
                capture_output=True, text=True, timeout=120
            )
            
            if result.returncode == 0:
                output = _ANSI_RE.sub('', result.stdout).strip()
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', output, re.DOTALL)
                if json_match:
                    prompts = json.loads(json_match.group())
                    # Merge with style visual cues
                    final = {}
                    for style in styles:
                        if style in prompts and style in COVER_STYLES:
                            final[style] = f"{prompts[style]}, {COVER_STYLES[style]['style_prompt']}, vertical 9:16 aspect ratio, podcast cover art"
                        elif style in COVER_STYLES:
                            final[style] = _fallback_prompt(style)
                    if final:
                        print(f"  ✅ kiro-cli 生成了 {len(final)} 个定制化 prompt", flush=True)
                        return final
        except Exception as e:
            print(f"  ⚠️ kiro-cli 调用失败: {e}", flush=True)
    
    # Fallback: try llm_client (direct Bedrock/MiniMax)
    try:
        from llm_client import llm_completion
        cfg = {}
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
        model = cfg.get("ai_model", "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0")
        print(f"  kiro-cli 不可用，尝试 {model}...", flush=True)
        
        raw = llm_completion(
            model=model,
            prompt=prompt,
            max_tokens=2000,
            temperature=0.8,
            config=cfg,
        ).strip()
        
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw, re.DOTALL)
        if json_match:
            prompts = json.loads(json_match.group())
            final = {}
            for style in styles:
                if style in prompts and style in COVER_STYLES:
                    final[style] = f"{prompts[style]}, {COVER_STYLES[style]['style_prompt']}, vertical 9:16 aspect ratio, podcast cover art"
                elif style in COVER_STYLES:
                    final[style] = _fallback_prompt(style)
            if final:
                print(f"  ✅ LLM 生成了 {len(final)} 个定制化 prompt", flush=True)
                return final
    except Exception as e:
        print(f"  ⚠️ LLM 调用也失败: {e}", flush=True)
    
    # Final fallback: generic prompts
    print("  使用默认通用 prompt...", flush=True)
    return {s: _fallback_prompt(s) for s in styles if s in COVER_STYLES}


def _fallback_prompt(style: str) -> str:
    """Generate a fallback generic prompt for a style."""
    return (
        f"Technology and AI themed podcast cover, abstract digital visualization, "
        f"{COVER_STYLES[style]['style_prompt']}, vertical composition 9:16 aspect ratio, podcast cover art"
    )


def generate_cover_image(prompt: str, style: str, output_path: str, 
                          region: str = "us-west-2") -> bool:
    """Generate a single cover image using Bedrock SD3.5 Large."""
    try:
        bedrock = boto3.client("bedrock-runtime", region_name=region)
        
        response = bedrock.invoke_model(
            modelId="stability.sd3-5-large-v1:0",
            body=json.dumps({
                "prompt": prompt,
                "negative_prompt": NEGATIVE_PROMPT,
                "aspect_ratio": "9:16",
                "output_format": "png"
            })
        )
        
        result = json.loads(response["body"].read())
        image_bytes = base64.b64decode(result["images"][0])
        
        with open(output_path, "wb") as f:
            f.write(image_bytes)
        
        file_size_kb = os.path.getsize(output_path) / 1024
        print(f"  ✅ [{COVER_STYLES.get(style, {}).get('name', style)}] 生成成功 ({file_size_kb:.0f} KB)", flush=True)
        return True
        
    except Exception as e:
        print(f"  ❌ [{COVER_STYLES.get(style, {}).get('name', style)}] 生成失败: {e}", flush=True)
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate podcast cover images")
    parser.add_argument("article", help="Path to article Markdown file")
    parser.add_argument("--output-dir", required=True, help="Output directory for covers")
    parser.add_argument("--slug", default="podcast", help="Filename prefix slug")
    parser.add_argument("--styles", nargs="+", 
                        default=["cyberpunk", "scifi", "pixel", "comic", "ukiyoe"],
                        help="Cover styles to generate")
    parser.add_argument("--region", default="us-west-2", help="AWS Bedrock region")
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Load article
    print(f"📖 加载文章: {args.article}", flush=True)
    article_text = load_article(args.article)
    
    # Generate prompts
    print(f"🎨 生成 {len(args.styles)} 种风格的封面 prompt...", flush=True)
    prompts = generate_image_prompts(article_text, args.styles)
    
    # Generate images
    print(f"🖼️ 开始生成封面图（9:16 竖版）...", flush=True)
    covers = []
    for style in args.styles:
        if style not in prompts:
            continue
        output_path = os.path.join(args.output_dir, f"{args.slug}-cover-{style}.png")
        success = generate_cover_image(prompts[style], style, output_path, args.region)
        if success:
            covers.append({
                "style": style,
                "style_name": COVER_STYLES.get(style, {}).get("name", style),
                "path": output_path,
                "prompt": prompts[style]
            })
    
    # Save covers manifest
    manifest_path = os.path.join(args.output_dir, f"{args.slug}-covers.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(covers, f, ensure_ascii=False, indent=2)
    
    print(f"\n🎨 封面生成完成: {len(covers)}/{len(args.styles)} 张成功", flush=True)
    print(f"   清单: {manifest_path}", flush=True)
    for c in covers:
        print(f"   - [{c['style_name']}] {c['path']}", flush=True)


if __name__ == "__main__":
    main()
