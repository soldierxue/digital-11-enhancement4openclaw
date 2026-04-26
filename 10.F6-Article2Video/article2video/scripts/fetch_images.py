#!/usr/bin/env python3
"""Phase 2B (photo mode): Fetch photos from Unsplash based on visual descriptions.

Uses AI to generate optimal search keywords from visual descriptions, then
downloads high-quality photos from Unsplash.

Usage:
    python3 fetch_images.py speech-script.json \
        --output-dir /tmp/workdir/images \
        --model anthropic/claude-sonnet-4-20250514
"""

import argparse
import json
import os
import re
import sys
import urllib.request


def generate_search_queries(slides: list, model: str) -> list:
    """Use AI to generate Unsplash search queries from visual descriptions.

    Provides full article context so the AI can select visually coherent photos
    across all slides — consistent color tone, subject matter, and mood.
    """
    from litellm import completion

    # Build context: article title (from slide 1) + all visual descriptions
    article_title = slides[0].get("title", "") if slides else ""
    all_titles = " → ".join(s.get("title", "") for s in slides)
    visuals = "\n".join(f"Slide {s['slide']} ({s.get('title','')}): {s['visual']}" for s in slides)

    prompt = f"""You are selecting background photos for a narrated video about:
"{article_title}"

The video has {len(slides)} slides covering these topics in order:
{all_titles}

## Visual consistency requirements

All {len(slides)} photos MUST form a visually coherent set:
1. **Unified color palette** — pick photos that share a similar dominant color tone
   (e.g., all cool blue-teal tech tones, or all warm amber tones). Avoid mixing
   wildly different color temperatures across slides.
2. **Consistent subject domain** — stay within the article's domain. If the article
   is about chips/servers/AI, all photos should be from that world (data centers,
   circuit boards, server racks, tech labs, etc.). Do NOT mix in unrelated stock
   photos (nature, food, random office scenes) unless the slide specifically calls
   for it.
3. **Similar photographic style** — all photos should have a similar level of
   abstraction, lighting mood (e.g., all moody/dark or all bright/clean), and
   composition style. Avoid mixing macro close-ups with wide aerial shots randomly.
4. **Narrative flow** — the sequence should feel like a visual story. Adjacent slides
   should transition smoothly in terms of visual weight and subject.

## Output format

For each slide, provide a direct Unsplash image URL:
https://images.unsplash.com/photo-XXXXXX?w=1920&h=1080&fit=crop

Output ONLY a JSON array of objects with "slide" and "url" keys. No other text.

## Per-slide visual descriptions

{visuals}
"""

    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=2000,
    )

    content = response.choices[0].message.content.strip()
    json_match = re.search(r"\[[\s\S]*\]", content)
    if json_match:
        return json.loads(json_match.group())
    return json.loads(content)


def download_image(url: str, output_path: str) -> bool:
    """Download an image from URL."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        with open(output_path, "wb") as f:
            f.write(data)
        print(f"  ✅ {len(data)//1024} KB → {os.path.basename(output_path)}", flush=True)
        return True
    except Exception as e:
        print(f"  ❌ Download failed: {e}", flush=True)
        return False


def fallback_unsplash_urls() -> list:
    """Fallback generic Unsplash URLs for common tech/business themes."""
    return [
        "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=1920&h=1080&fit=crop",
        "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1920&h=1080&fit=crop",
        "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=1920&h=1080&fit=crop",
        "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=1920&h=1080&fit=crop",
        "https://images.unsplash.com/photo-1461749280684-dccba630e2f6?w=1920&h=1080&fit=crop",
        "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=1920&h=1080&fit=crop",
        "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=1920&h=1080&fit=crop",
        "https://images.unsplash.com/photo-1552664730-d307ca884978?w=1920&h=1080&fit=crop",
        "https://images.unsplash.com/photo-1510797215324-95aa89f43c33?w=1920&h=1080&fit=crop",
        "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?w=1920&h=1080&fit=crop",
    ]


def main():
    parser = argparse.ArgumentParser(description="Fetch photos from Unsplash")
    parser.add_argument("speech_script", help="Path to speech-script.json")
    parser.add_argument("--output-dir", required=True, help="Image output directory")
    parser.add_argument("--model", default="anthropic/claude-sonnet-4-20250514",
                        help="LiteLLM model for query generation")
    args = parser.parse_args()

    with open(args.speech_script, encoding="utf-8") as f:
        slides = json.load(f)

    os.makedirs(args.output_dir, exist_ok=True)
    num_slides = len(slides)

    # Check which images already exist
    existing = set()
    for i in range(1, num_slides + 1):
        path = os.path.join(args.output_dir, f"slide-{i:02d}.jpg")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            existing.add(i)

    if len(existing) >= num_slides:
        print(f"✅ All {num_slides} images already downloaded.", flush=True)
        return

    # Generate search queries using AI
    print(f"🔍 Generating Unsplash URLs for {num_slides} slides...", flush=True)
    try:
        queries = generate_search_queries(slides, args.model)
    except Exception as e:
        print(f"⚠️ AI query generation failed ({e}), using fallback URLs", flush=True)
        queries = [{"slide": i+1, "url": url}
                    for i, url in enumerate(fallback_unsplash_urls()[:num_slides])]

    # Download images
    success_count = 0
    fallback_urls = fallback_unsplash_urls()

    for q in queries:
        idx = q["slide"]
        if idx in existing:
            print(f"  Slide {idx}: already exists, skipping.", flush=True)
            success_count += 1
            continue

        out_path = os.path.join(args.output_dir, f"slide-{idx:02d}.jpg")
        print(f"  Slide {idx}: downloading...", flush=True)

        if download_image(q["url"], out_path):
            success_count += 1
        elif idx - 1 < len(fallback_urls):
            # Try fallback
            print(f"  Slide {idx}: trying fallback URL...", flush=True)
            if download_image(fallback_urls[idx - 1], out_path):
                success_count += 1

    print(f"\n📊 Downloaded: {success_count}/{num_slides}", flush=True)


if __name__ == "__main__":
    main()
