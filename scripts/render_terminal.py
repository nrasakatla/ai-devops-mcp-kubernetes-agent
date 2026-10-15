#!/usr/bin/env python
"""Render a text file (real terminal output) to a PNG 'screenshot'.

Produces an authentic-looking dark terminal screenshot from actual command
output captured to a .txt file. Used to generate portfolio screenshots from
real demo runs (no fabricated content — the text is verbatim from the demos).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BG = (15, 23, 42)          # slate-900
FG = (226, 232, 240)       # slate-200
GREEN = (52, 211, 153)
YELLOW = (245, 158, 11)
PURPLE = (167, 139, 250)
BLUE = (56, 189, 248)
RED = (248, 113, 113)
GRAY = (100, 116, 139)
TITLEBAR = (30, 41, 59)    # slate-800


def load_mono_font(size: int):
    for candidate in [
        "/System/Library/Fonts/Supplemental/Menlo.ttc",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Courier New.ttf",
    ]:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def color_for(line: str):
    s = line.rstrip("\n")
    if s.startswith("==") or "[1]" in s or "[2]" in s:
        return BLUE
    if "Failure class" in s:
        return GREEN
    if "Analysis source" in s or "Collecting" in s:
        return PURPLE
    if "Report written" in s:
        return GRAY
    if "CrashLoopBackOff" in s and "STATUS" not in s:
        return RED
    if "OOMKilled" in s and "STATUS" not in s:
        return RED
    if "Pending" in s and "STATUS" not in s:
        return YELLOW
    if line.startswith("$") or line.startswith("python") or line.startswith("export") or line.startswith("kubectl"):
        return GREEN
    return FG


def render(text_path: str, out_path: str, title: str = "bash — 80x24"):
    lines = Path(text_path).read_text().split("\n")
    font = load_mono_font(16)
    line_h = 22
    pad = 20
    width = 900
    height = pad * 2 + len(lines) * line_h + 40  # title bar

    img = Image.new("RGB", (width, max(height, 200)), BG)
    draw = ImageDraw.Draw(img)

    # title bar
    draw.rectangle([0, 0, width, 34], fill=TITLEBAR)
    draw.text((pad, 8), title, fill=(148, 163, 184), font=load_mono_font(14))

    y = 50
    for line in lines:
        color = color_for(line)
        draw.text((pad, y), line if line else " ", fill=color, font=font)
        y += line_h

    img.save(out_path)
    print(f"wrote {out_path} ({img.width}x{img.height})")


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "bash")
