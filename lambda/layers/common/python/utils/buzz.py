# utils/buzz.py — free attention signals blended into scoring (Phase 1.5).
#
# Three public sources ground hook_potential in observed attention: Hugging
# Face Daily Papers (upvotes), Hacker News via Algolia (points + comments),
# Semantic Scholar (early citations). Everything is best-effort: any source
# failing degrades to LLM-only scoring; fetch_buzz/apply_buzz never raise.

import math
import os
import time

import requests

from utils.logger import get_logger
from utils.scoring import W_HOOK, arxiv_id, composite

logger = get_logger("buzz")

BUZZ_ENABLED = os.getenv("BUZZ_ENABLED", "true").lower() == "true"
# Cedes this much of the hook weight to observed buzz; clamped so a mis-set
# env can never produce a negative hook weight (Lambda must not crash a run).
W_BUZZ = min(float(os.getenv("SCORING_W_BUZZ", str(W_HOOK / 2))), W_HOOK)
HTTP_TIMEOUT_S = float(os.getenv("BUZZ_HTTP_TIMEOUT_S", "3"))
WALL_BUDGET_S = float(os.getenv("BUZZ_WALL_BUDGET_S", "20"))

HF_DAILY_URL = "https://huggingface.co/api/daily_papers"
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"

# Saturation caps: a source at its cap contributes a full 10.
CAPS = {"hf_upvotes": 100, "hn_points": 500, "hn_comments": 200, "s2_citations": 50}


def _saturate(value, cap):
    """0..10 on a log curve that reaches 10 at `cap`."""
    v = max(0.0, float(value))
    return min(10.0, 10.0 * math.log1p(v) / math.log1p(cap))


def buzz_score(raw):
    """One 0-10 buzz value from raw per-source counts; the strongest source
    wins (sources are sparse — a mean would punish single-source hits).
    None when no source produced a number: no signal is not zero buzz."""
    parts = [_saturate(raw[k], CAPS[k]) for k in CAPS if raw.get(k) is not None]
    return round(max(parts), 2) if parts else None


def blend_composite(scores, buzz):
    """LLM composite with W_BUZZ of the hook weight ceded to observed buzz."""
    if buzz is None:
        return round(composite(scores), 2)
    return round(composite(scores)
                 - W_BUZZ * scores["hook_potential"] + W_BUZZ * buzz, 2)


def apply_buzz(scored, buzz_map):
    """Return a NEW composite-desc list. Candidates with an entry in buzz_map
    gain buzz_raw/buzz and a blended composite; the rest stay LLM-only."""
    out = []
    for c in scored:
        raw = buzz_map.get(arxiv_id(c["url"]))
        value = buzz_score(raw) if raw else None
        entry = {**c, "buzz_raw": raw or None, "buzz": value}
        if value is not None:
            entry["composite"] = blend_composite(c["scores"], value)
        out.append(entry)
    out.sort(key=lambda c: c["composite"], reverse=True)
    return out
