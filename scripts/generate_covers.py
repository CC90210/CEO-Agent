"""Generate branded cover images for the prior community Skool courses.
Each cover: 1460x752px, dark theme, course title + icon/accent.
"""
from PIL import Image, ImageDraw, ImageFont
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', '.playwright-mcp', 'covers')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Course data: (filename, day_label, title, accent_color, icon_emoji)
COURSES = [
    ("day-00-ai-foundations", "DAY 0", "AI Foundations", "#6366F1", "AI"),
    ("day-01-environment-setup", "DAY 1", "Environment Setup", "#10B981", "DEV"),
    ("day-02-claude-code", "DAY 2", "Claude Code Mastery", "#F59E0B", "CC"),
    ("day-03-mcps", "DAY 3", "MCPs & Integrations", "#8B5CF6", "MCP"),
    ("day-04-apis", "DAY 4", "APIs & Scripting", "#EF4444", "API"),
    ("day-05-database", "DAY 5", "Database & Backend", "#3ECF8E", "DB"),
    ("day-06-automation", "DAY 6", "Automation & Workflows", "#FF6D5A", "n8n"),
    ("day-07-deployment", "DAY 7", "Deployment & Hosting", "#000000", "SHIP"),
    ("day-08-business", "DAY 8", "Business Tools", "#635BFF", "BIZ"),
    ("day-09-agents", "DAY 9", "Advanced Agents", "#FF4500", "AGT"),
    ("day-10-capstone", "DAY 10", "Capstone Project", "#FFD700", "CAP"),
]

WIDTH, HEIGHT = 1460, 752
BG_COLOR = "#0D1117"
TEXT_COLOR = "#F0F6FC"
SUBTITLE_COLOR = "#8B949E"
BRAND_TEXT = "AGENCY ACCELERANTS"


def create_cover(filename, day_label, title, accent, icon_text):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Accent gradient bar at top
    for y in range(6):
        draw.rectangle([0, y, WIDTH, y + 1], fill=accent)

    # Accent bar at bottom
    for y in range(HEIGHT - 6, HEIGHT):
        draw.rectangle([0, y, WIDTH, y + 1], fill=accent)

    # Large icon/badge circle
    cx, cy, r = 730, 280, 120
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)

    # Icon text inside circle
    try:
        icon_font = ImageFont.truetype("arial.ttf", 60)
    except OSError:
        icon_font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), icon_text, font=icon_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw // 2, cy - th // 2 - 5), icon_text, fill="#FFFFFF", font=icon_font)

    # Day label
    try:
        day_font = ImageFont.truetype("arial.ttf", 36)
    except OSError:
        day_font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), day_label, font=day_font)
    tw = bbox[2] - bbox[0]
    draw.text((WIDTH // 2 - tw // 2, 440), day_label, fill=accent, font=day_font)

    # Title
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 64)
    except OSError:
        try:
            title_font = ImageFont.truetype("arial.ttf", 64)
        except OSError:
            title_font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text((WIDTH // 2 - tw // 2, 490), title, fill=TEXT_COLOR, font=title_font)

    # Brand subtitle
    try:
        brand_font = ImageFont.truetype("arial.ttf", 24)
    except OSError:
        brand_font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), BRAND_TEXT, font=brand_font)
    tw = bbox[2] - bbox[0]
    draw.text((WIDTH // 2 - tw // 2, 580), BRAND_TEXT, fill=SUBTITLE_COLOR, font=brand_font)

    # Decorative dots/grid pattern (subtle)
    for x in range(50, WIDTH, 80):
        for y in range(50, 220, 80):
            draw.ellipse([x, y, x + 4, y + 4], fill="#161B22")

    path = os.path.join(OUTPUT_DIR, f"{filename}.png")
    img.save(path, "PNG")
    print(f"Created: {path}")
    return path


if __name__ == "__main__":
    paths = []
    for course in COURSES:
        p = create_cover(*course)
        paths.append(p)
    print(f"\nGenerated {len(paths)} cover images in {OUTPUT_DIR}")
