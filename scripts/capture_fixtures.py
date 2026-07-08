# scripts/capture_fixtures.py
"""Capture REAL arXiv pages + figure-image byte prefixes into tests/fixtures/.

Run manually (network required): uv run python scripts/capture_fixtures.py
Tests NEVER hit the network; they read these captured files. Byte-prefix
image fixtures (.head) are the real first 4096 bytes — enough for PNG IHDR
and JPEG SOF dimension parsing.
"""
import pathlib
import time

import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
FIX = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures"
PAGES = ["2607.02116", "2607.01641", "2607.01600"]
IMAGES = {
    "2607.02116_fig1.jpg.head": "https://arxiv.org/html/2607.02116v1/figures/cn-in-agent-stack.jpg",
    "2607.01641_fig1.png.head": "https://arxiv.org/html/2607.01641v1/x1.png",
}

FIX.mkdir(parents=True, exist_ok=True)
for pid in PAGES:
    r = requests.get(f"https://arxiv.org/html/{pid}", timeout=20, headers=UA)
    r.raise_for_status()
    (FIX / f"{pid}.html").write_text(r.text, encoding="utf-8")
    time.sleep(2)
for name, url in IMAGES.items():
    r = requests.get(url, timeout=20, headers=UA)
    r.raise_for_status()
    (FIX / name).write_bytes(r.content[:4096])
    time.sleep(2)
print("captured:", sorted(p.name for p in FIX.iterdir()))
