#!/usr/bin/env python3
"""Phase 2B (ai mode): Generate AI illustrations using AWS Bedrock Nova Canvas.

Generates cinematic, text-free illustrations based on visual descriptions.

Usage:
    python3 generate_ai_images.py speech-script.json \
        --output-dir /tmp/workdir/images \
        --region us-east-1 \
        --model-id amazon.nova-canvas-v1:0
"""

import argparse
import base64
import json
import os
import sys

STYLE_PREFIX_BASE = (
    "IMPORTANT: Do NOT include any text, words, letters, numbers, labels, "
    "watermarks, or writing of any kind in the image. Pure visual illustration only."
)

NEGATIVE_TEXT = (
    "text, words, letters, numbers, labels, watermarks, writing, "
    "typography, captions, subtitles, logos, signatures, stamps, "
    "any readable characters"
)


def generate_visual_style(slides: list, model: str) -> str:
    """Use AI to define a unified visual style for all slides based on article context."""
    from litellm import completion

    article_title = slides[0].get("title", "") if slides else ""
    all_visuals = "\n".join(f"Slide {s['slide']} ({s.get('title','')}): {s.get('visual','')}"
                            for s in slides)

    prompt = f"""You are an art director designing illustrations for a narrated video about:
"{article_title}"

The video has {len(slides)} slides with these visual descriptions:
{all_visuals}

Define a SINGLE unified visual style that ALL illustrations must follow.
Include:
1. Color palette (2-3 dominant colors as descriptive words, e.g., "deep navy blue, electric cyan, dark charcoal")
2. Art style (e.g., "flat vector", "3D isometric", "photorealistic render", "digital painting")
3. Lighting mood (e.g., "moody neon glow", "soft ambient", "dramatic rim lighting")
4. Recurring visual motifs that tie the series together (e.g., "circuit board patterns", "glowing data streams")

Output ONLY a single paragraph (3-4 sentences) describing the style. No JSON, no bullet points.
This will be prepended to every image generation prompt to ensure visual consistency."""

    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=300,
    )

    style = response.choices[0].message.content.strip()
    # Remove any markdown formatting
    style = style.replace("```", "").strip()
    return style


def generate_image(bedrock_client, model_id: str, prompt: str, style_prefix: str,
                   output_path: str) -> bool:
    """Generate a single image via Bedrock."""
    full_prompt = f"{style_prefix} {STYLE_PREFIX_BASE}, {prompt}"

    body = json.dumps({
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {
            "text": full_prompt,
            "negativeText": NEGATIVE_TEXT,
        },
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": 720,
            "width": 1280,
            "quality": "standard",
        },
    })

    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        result = json.loads(response["body"].read())
        if "images" in result and result["images"]:
            img_data = base64.b64decode(result["images"][0])
            with open(output_path, "wb") as f:
                f.write(img_data)
            return True
        else:
            print(f"    No image in response: {list(result.keys())}", flush=True)
            return False
    except Exception as e:
        print(f"    Error: {e}", flush=True)
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate AI images via Bedrock")
    parser.add_argument("speech_script", help="Path to speech-script.json")
    parser.add_argument("--output-dir", required=True, help="Image output directory")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--model-id", default="amazon.nova-canvas-v1:0", help="Bedrock model ID")
    parser.add_argument("--model", default="anthropic/claude-sonnet-4-20250514",
                        help="LiteLLM model for style generation")
    args = parser.parse_args()

    import boto3
    bedrock = boto3.client("bedrock-runtime", region_name=args.region)

    with open(args.speech_script, encoding="utf-8") as f:
        slides = json.load(f)

    os.makedirs(args.output_dir, exist_ok=True)

    # Generate unified visual style from article context
    print("🎨 Generating unified visual style for all slides...", flush=True)
    try:
        style_prefix = generate_visual_style(slides, args.model)
        print(f"   Style: {style_prefix[:120]}...", flush=True)
    except Exception as e:
        print(f"⚠️ Style generation failed ({e}), using default style", flush=True)
        style_prefix = (
            "Digital illustration, dark blue-purple gradient background, "
            "modern tech aesthetic, cinematic lighting, 16:9 aspect ratio."
        )

    success_count = 0
    for slide in slides:
        idx = slide["slide"]
        # AI images are saved as PNG
        out_path = os.path.join(args.output_dir, f"slide-{idx:02d}.png")

        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            print(f"  Slide {idx}: already exists, skipping.", flush=True)
            success_count += 1
            continue

        visual = slide.get("visual", "abstract tech background")
        print(f"  Slide {idx}: generating ({visual[:50]}...)", flush=True)

        if generate_image(bedrock, args.model_id, visual, style_prefix, out_path):
            size_kb = os.path.getsize(out_path) // 1024
            print(f"    ✅ {size_kb} KB", flush=True)
            success_count += 1
        else:
            print(f"    ❌ Failed", flush=True)

    print(f"\n📊 Generated: {success_count}/{len(slides)}", flush=True)


if __name__ == "__main__":
    main()
