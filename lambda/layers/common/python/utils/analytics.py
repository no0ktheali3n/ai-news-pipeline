"""utils/analytics.py — Pure analytics aggregates for the posted ledger.

No boto3, no I/O, stdlib only. Every function:
  - returns a sensible empty for entries=[]
  - tolerates entries missing ANY field (old-format entries may have only
    title/posted_at — never KeyError).
"""
from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# load_entries
# ---------------------------------------------------------------------------

def load_entries(ledger: dict) -> list[dict]:
    """Return ledger values sorted ascending by posted_at, each with url injected.

    Entries missing posted_at sort first (treated as empty string "").
    The original ledger dicts are NOT mutated — each returned dict is a shallow copy.
    """
    result = []
    for url, entry in ledger.items():
        copy = dict(entry)
        copy["url"] = url
        result.append(copy)
    result.sort(key=lambda e: e.get("posted_at") or "")
    return result


# ---------------------------------------------------------------------------
# follower_series
# ---------------------------------------------------------------------------

def follower_series(entries: list) -> list[tuple[str, int]]:
    """Return (posted_at, follower_count) pairs where follower_count is an int."""
    out = []
    for e in entries:
        fc = e.get("follower_count")
        if isinstance(fc, int):
            out.append((e.get("posted_at", ""), fc))
    return out


# ---------------------------------------------------------------------------
# post_deltas
# ---------------------------------------------------------------------------

def post_deltas(entries: list) -> list[dict]:
    """Return per-entry dicts {title, url, thread_url, composite, buzz, delta} in chronological order.

    delta = this entry's follower_count minus the PREVIOUS entry's follower_count.
    delta is None when either side is missing/None. First entry delta is always None.
    A None follower_count on either side resets the chain — no carry-forward of prev_fc.
    """
    out = []
    prev_fc: Optional[int] = None
    for e in entries:
        fc = e.get("follower_count")
        if not isinstance(fc, int):
            fc = None

        if fc is None or prev_fc is None:
            delta = None
        else:
            delta = fc - prev_fc

        out.append({
            "title": e.get("title"),
            "url": e.get("url"),
            "thread_url": e.get("thread_url"),
            "composite": e.get("composite"),
            "buzz": e.get("buzz"),
            "delta": delta,
        })
        # None fc resets the chain: next entry's delta is also None (no carry-forward).
        prev_fc = fc
    return out


# ---------------------------------------------------------------------------
# lane_stats
# ---------------------------------------------------------------------------

def lane_stats(entries: list) -> dict[str, dict]:
    """Return per-lane stats keyed by first element of query_source ("unknown" fallback).

    Value: {"posts": int, "avg_composite": float|None} (avg rounded to 2dp;
    None when no entry in that lane has a composite).
    """
    lanes: dict[str, list] = {}
    for e in entries:
        qs = e.get("query_source")
        if qs and isinstance(qs, list) and len(qs) > 0:
            lane = qs[0]
        else:
            lane = "unknown"
        lanes.setdefault(lane, []).append(e)

    result = {}
    for lane, lane_entries in lanes.items():
        composites = [
            e["composite"]
            for e in lane_entries
            if isinstance(e.get("composite"), (int, float))
        ]
        avg = round(sum(composites) / len(composites), 2) if composites else None
        result[lane] = {"posts": len(lane_entries), "avg_composite": avg}
    return result


# ---------------------------------------------------------------------------
# buzz_outcome
# ---------------------------------------------------------------------------

def buzz_outcome(entries: list) -> dict:
    """Return {"buzzed": {...}, "unbuzzed": {...}} with posts count and avg_delta.

    buzzed = entry.get("buzz") is not None.
    avg_delta is computed over the post_deltas deltas that are not None (2dp),
    or None when no computable deltas exist for that bucket.
    """
    deltas = post_deltas(entries)

    buzzed_deltas: list[int | float] = []
    unbuzzed_deltas: list[int | float] = []
    buzzed_posts = 0
    unbuzzed_posts = 0

    for entry, d in zip(entries, deltas):
        is_buzzed = entry.get("buzz") is not None
        delta_val = d["delta"]

        if is_buzzed:
            buzzed_posts += 1
            if delta_val is not None:
                buzzed_deltas.append(delta_val)
        else:
            unbuzzed_posts += 1
            if delta_val is not None:
                unbuzzed_deltas.append(delta_val)

    def _avg(vals: list) -> Optional[float]:
        return round(sum(vals) / len(vals), 2) if vals else None

    return {
        "buzzed": {"posts": buzzed_posts, "avg_delta": _avg(buzzed_deltas)},
        "unbuzzed": {"posts": unbuzzed_posts, "avg_delta": _avg(unbuzzed_deltas)},
    }


# ---------------------------------------------------------------------------
# run_stats
# ---------------------------------------------------------------------------

def run_stats(n_sidecars: int, entries: list) -> dict:
    """Return {"runs": n_sidecars, "posts": len(entries), "partials": count}."""
    partials = sum(1 for e in entries if e.get("status") == "partial")
    return {"runs": n_sidecars, "posts": len(entries), "partials": partials}
