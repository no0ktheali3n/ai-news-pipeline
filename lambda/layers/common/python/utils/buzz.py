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


def _env_float(name, default):
    """Best-effort float env: a malformed value must degrade to the default,
    never break the module import (the scraper handler imports this module)."""
    try:
        return float(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


# Cedes this much of the hook weight to observed buzz; clamped so a mis-set
# env can never produce a negative hook weight (Lambda must not crash a run).
W_BUZZ = max(0.0, min(_env_float("SCORING_W_BUZZ", W_HOOK / 2), W_HOOK))
HTTP_TIMEOUT_S = _env_float("BUZZ_HTTP_TIMEOUT_S", 3.0)
WALL_BUDGET_S = _env_float("BUZZ_WALL_BUDGET_S", 20.0)

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
    None when no source produced a number: no signal is not zero buzz.
    Zero counts are treated as no-signal — a zero count carries no positive
    attention signal and must not move the composite down."""
    parts = [_saturate(raw[k], CAPS[k]) for k in CAPS if raw.get(k)]
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


def _fetch_hf(ids):
    """One call: today's HF Daily Papers list -> {arxiv_id: upvotes} for ids
    we hold. The daily list is small and human-curated: most freshly-scraped
    ids will simply not be on it — absent is the normal case, not an error."""
    resp = requests.get(HF_DAILY_URL, timeout=HTTP_TIMEOUT_S)
    resp.raise_for_status()
    wanted = set(ids)
    out = {}
    for row in resp.json():
        paper = row.get("paper") or {}
        pid = str(paper.get("id"))
        if pid in wanted:
            out[pid] = int(paper.get("upvotes") or 0)
    return out


def _fetch_s2(ids):
    """One batch call -> {arxiv_id: citationCount}. S2 returns one row per
    requested id, in order; null rows mean the paper is unknown to S2. The
    unauthenticated tier 429s under load — raise_for_status degrades that
    to a caught source failure."""
    resp = requests.post(
        S2_BATCH_URL, params={"fields": "citationCount"},
        json={"ids": [f"ARXIV:{i}" for i in ids]}, timeout=HTTP_TIMEOUT_S)
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list):   # error-shaped body: no signal, not garbage pairings
        return {}
    out = {}
    for i, row in zip(ids, rows):
        if isinstance(row, dict) and row.get("citationCount") is not None:
            out[i] = int(row["citationCount"])
    return out


def _fetch_hn(paper_id):
    """(points, comments) summed across HN SUBMISSIONS of the paper —
    story-tagged hits whose url contains the arXiv id. Algolia's free-text
    match is loose (comments and unrelated stories match the digits), so we
    query the abs URL with tags=story AND re-filter by url. (None, None)
    when HN has no submission of this paper."""
    resp = requests.get(
        HN_SEARCH_URL,
        params={"query": f"arxiv.org/abs/{paper_id}", "tags": "story"},
        timeout=HTTP_TIMEOUT_S)
    resp.raise_for_status()
    hits = [h for h in resp.json().get("hits", [])
            if paper_id in (h.get("url") or "")]
    if not hits:
        return None, None
    return (sum(int(h.get("points") or 0) for h in hits),
            sum(int(h.get("num_comments") or 0) for h in hits))


def fetch_buzz(candidates):
    """Best-effort raw buzz per candidate: {arxiv_id: {source: count, ...}}.
    Sources are isolated (one failing never hides another); the per-candidate
    HN loop stops when WALL_BUDGET_S is spent. Only ids with data appear."""
    ids = [arxiv_id(c["url"]) for c in candidates]
    raw = {i: {} for i in ids}
    started = time.monotonic()

    try:
        for i, upvotes in _fetch_hf(ids).items():
            raw[i]["hf_upvotes"] = upvotes
    except Exception as e:
        logger.warning("buzz: HF daily papers unavailable: %s", e)

    try:
        for i, citations in _fetch_s2(ids).items():
            raw[i]["s2_citations"] = citations
    except Exception as e:
        logger.warning("buzz: Semantic Scholar unavailable: %s", e)

    skipped = 0
    for i in ids:
        if time.monotonic() - started > WALL_BUDGET_S:
            skipped += 1
            continue
        try:
            points, comments = _fetch_hn(i)
            if points is not None:
                raw[i]["hn_points"] = points
                raw[i]["hn_comments"] = comments
        except Exception as e:
            logger.warning("buzz: HN lookup failed for %s: %s", i, e)
    if skipped:
        logger.warning("buzz: wall budget exhausted; skipped %d HN lookups", skipped)

    return {i: r for i, r in raw.items() if r}
