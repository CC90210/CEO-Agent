#!/usr/bin/env python3
"""
Codex Image Generation Bridge — Generate images via OpenAI through Codex CLI.

Uses CC's existing ChatGPT subscription via Codex — no separate API key needed.
Delegates to Codex which has access to GPT Image generation.

Usage:
  python scripts/codex_image_gen.py generate "A futuristic AI dashboard with neon accents" --output media/exports/thumbnail.png
  python scripts/codex_image_gen.py generate "Quote card: 'Only good things from now on' with dark background" --style branded
  python scripts/codex_image_gen.py generate "Split screen overlay of AI code editor" --size 1080x1920
  python scripts/codex_image_gen.py --json generate "prompt here"
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = Path.home() / ".claude" / "codex-plugin"
EXPORT_DIR = PROJECT_ROOT / "media" / "exports"

# Brand context for image generation
BRAND_CONTEXT = """
Brand: OASIS AI Solutions / Kona Makana
Colors: Pearl White (#FAF9F5), Obsidian (#141413), OASIS Blue (#0A84FF), Signal Green (#30D158)
Style: Dark backgrounds, clean modern tech aesthetic, minimal but impactful
Font: Inter (bold for headlines)
Mood: Professional, cutting-edge, authentic
"""

STYLE_PRESETS = {
    "branded": f"Create this image with dark background (#141413), clean modern aesthetic, minimal design. {BRAND_CONTEXT}",
    "quote": f"Create a quote card image. Dark background (#141413), large bold white text (#FAF9F5), subtle blue accent (#0A84FF). Professional, not generic. {BRAND_CONTEXT}",
    "thumbnail": "Create a YouTube/Instagram thumbnail. Bold text, high contrast, face-forward composition, curiosity-gap visual. 1280x720.",
    "carousel": f"Create a carousel slide image. Dark background, clean layout, one key point per slide. {BRAND_CONTEXT}",
    "split": "Create a visual overlay suitable for split-screen video format (top half). Tech/AI themed, dark background, relevant to the topic.",
    "raw": "",  # No style injection — pure prompt
}


def generate_image(prompt, output_path=None, style="branded", size="1080x1920", output_json=False):
    """Generate an image via Codex CLI."""

    # Build the full prompt with style context
    style_context = STYLE_PRESETS.get(style, STYLE_PRESETS["branded"])
    full_prompt = f"{style_context}\n\nImage to generate: {prompt}" if style_context else prompt

    # Ensure output directory exists
    if output_path is None:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in prompt[:40])
        output_path = str(EXPORT_DIR / f"{safe_name}.png")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Build Codex task
    codex_task = (
        f"Generate an image with this specification and save it to {output_path}:\n\n"
        f"{full_prompt}\n\n"
        f"Size: {size}\n"
        f"Save the image file to: {output_path}\n"
        f"Use the OpenAI image generation API to create this image."
    )

    companion_script = str(PLUGIN_ROOT / "scripts" / "codex-companion.mjs")

    if not Path(companion_script).exists():
        # Fallback to project-local plugin
        companion_script = str(PROJECT_ROOT / ".claude" / "plugins" / "codex" / "scripts" / "codex-companion.mjs")

    if not Path(companion_script).exists():
        result = {"status": "error", "error": "Codex plugin not found", "fix": "Run /codex:setup"}
        if output_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"ERROR: Codex plugin not found. Run /codex:setup to install.")
        return None

    cmd = [
        "node", companion_script,
        "task", "--write", codex_task,
    ]

    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)}

    if not output_json:
        print(f"Generating image via Codex...")
        print(f"  Prompt: {prompt[:80]}...")
        print(f"  Style: {style}")
        print(f"  Size: {size}")
        print(f"  Output: {output_path}")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            env=env, encoding="utf-8",
        )

        if result.returncode == 0:
            response = {
                "status": "success",
                "prompt": prompt,
                "style": style,
                "size": size,
                "output_path": output_path,
                "codex_output": result.stdout[:500] if result.stdout else "",
            }

            # Check if image was actually created
            if os.path.exists(output_path):
                response["file_exists"] = True
                response["file_size"] = os.path.getsize(output_path)
            else:
                response["file_exists"] = False
                response["note"] = "Codex task completed but image file not found. May need manual download."

            if output_json:
                print(json.dumps(response, indent=2))
            else:
                if response.get("file_exists"):
                    print(f"SUCCESS: Image saved to {output_path}")
                else:
                    print(f"Codex completed task. Check output for image location.")
                    if result.stdout:
                        print(f"Codex output: {result.stdout[:300]}")

            return response
        else:
            error_result = {
                "status": "error",
                "error": result.stderr[:300] if result.stderr else "Unknown error",
            }
            if output_json:
                print(json.dumps(error_result, indent=2))
            else:
                print(f"ERROR: Codex image generation failed")
                if result.stderr:
                    print(f"  {result.stderr[:300]}")
            return None

    except subprocess.TimeoutExpired:
        error_result = {"status": "timeout", "error": "Codex task timed out after 5 minutes"}
        if output_json:
            print(json.dumps(error_result, indent=2))
        else:
            print("ERROR: Codex timed out after 5 minutes")
        return None


def list_styles(output_json=False):
    """List available image style presets."""
    if output_json:
        print(json.dumps({k: v[:80] + "..." if len(v) > 80 else v for k, v in STYLE_PRESETS.items()}, indent=2))
    else:
        print("Available image styles:")
        for name, desc in STYLE_PRESETS.items():
            preview = desc[:60] + "..." if desc else "(no style injection)"
            print(f"  {name:<12} {preview}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Codex Image Generation Bridge")
    parser.add_argument("--json", action="store_true", help="JSON output")

    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="Generate an image")
    gen.add_argument("prompt", help="Image description / prompt")
    gen.add_argument("--output", "-o", help="Output file path")
    gen.add_argument("--style", choices=list(STYLE_PRESETS.keys()), default="branded",
                     help="Style preset (default: branded)")
    gen.add_argument("--size", default="1080x1920", help="Image size (default: 1080x1920)")

    sub.add_parser("styles", help="List available style presets")

    args = parser.parse_args()

    if args.command == "generate":
        generate_image(args.prompt, args.output, args.style, args.size, args.json)
    elif args.command == "styles":
        list_styles(args.json)
    else:
        parser.print_help()
