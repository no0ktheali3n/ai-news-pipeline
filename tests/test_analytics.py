# tests/test_analytics.py — Phase 4 (analytics aggregates) tests.
#   uv run python tests/test_analytics.py
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from stubs import install_stubs  # noqa: E402
install_stubs()

LAYER = REPO / "lambda" / "layers" / "common" / "python"
sys.path.insert(0, str(LAYER))

os.environ.setdefault("S3_OUTPUT_BUCKET", "test-bucket")

PASSED, FAILED = [], []


def check(name, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"  ✅ {name}")
    except Exception as e:
        FAILED.append((name, e))
        print(f"  ❌ {name}: {e}")


print("[1] analytics: load_entries")

from utils import analytics  # noqa: E402

# Fixture: 4-entry ledger (chronological order when sorted)
# Entry A: old-format — only title + posted_at
# Entry B: unbuzzed, follower_count 100, composite 6.0, lane "unknown" (no query_source)
# Entry C: buzzed (buzz 8.0), follower_count 110, composite 7.5, query_source ["agents"]
# Entry D: buzzed (buzz 5.0), follower_count None, status "partial", query_source ["agents"]

FIXTURE_LEDGER = {
    "https://arxiv.org/abs/2600.00001": {
        "title": "Old Paper",
        "posted_at": "2026-01-01T10:00:00",
    },
    "https://arxiv.org/abs/2600.00002": {
        "title": "Unbuzzed Paper",
        "posted_at": "2026-01-02T10:00:00",
        "builder_relevance": 6.0,
        "novelty": 6.0,
        "hook_potential": 6.0,
        "composite": 6.0,
        "buzz": None,
        "buzz_raw": None,
        "query_source": [],
        "follower_count": 100,
        "tweet_count": 3,
        "status": "posted",
    },
    "https://arxiv.org/abs/2600.00003": {
        "title": "Buzzed Paper",
        "posted_at": "2026-01-03T10:00:00",
        "builder_relevance": 8.0,
        "novelty": 7.0,
        "hook_potential": 7.0,
        "composite": 7.5,
        "buzz": 8.0,
        "buzz_raw": {"hf_upvotes": 80},
        "query_source": ["agents"],
        "follower_count": 110,
        "tweet_count": 5,
        "status": "posted",
    },
    "https://arxiv.org/abs/2600.00004": {
        "title": "Partial Paper",
        "posted_at": "2026-01-04T10:00:00",
        "builder_relevance": 5.0,
        "novelty": 5.0,
        "hook_potential": 5.0,
        "composite": 5.5,
        "buzz": 5.0,
        "buzz_raw": {"hn_points": 50},
        "query_source": ["agents"],
        "follower_count": None,
        "tweet_count": 2,
        "status": "partial",
    },
}


def test_load_entries_sorted_and_url_injected():
    entries = analytics.load_entries(FIXTURE_LEDGER)
    assert len(entries) == 4, f"expected 4, got {len(entries)}"
    # sorted ascending by posted_at
    dates = [e["posted_at"] for e in entries]
    assert dates == sorted(dates), f"not sorted: {dates}"
    # each entry has its url key
    urls = [e["url"] for e in entries]
    assert "https://arxiv.org/abs/2600.00001" in urls
    assert "https://arxiv.org/abs/2600.00003" in urls
    # original ledger not mutated (url not in original)
    assert "url" not in FIXTURE_LEDGER["https://arxiv.org/abs/2600.00001"]


def test_load_entries_missing_posted_at_sorts_first():
    ledger = {
        "https://arxiv.org/abs/9999.00001": {"title": "No date"},
        "https://arxiv.org/abs/9999.00002": {"title": "Has date", "posted_at": "2026-06-01T00:00:00"},
    }
    entries = analytics.load_entries(ledger)
    assert entries[0]["title"] == "No date", "missing posted_at must sort first (empty string)"


def test_load_entries_empty():
    assert analytics.load_entries({}) == []


def test_load_entries_old_format_no_crash():
    entries = analytics.load_entries(FIXTURE_LEDGER)
    old = next(e for e in entries if e["title"] == "Old Paper")
    assert old["url"] == "https://arxiv.org/abs/2600.00001"
    # no KeyError accessing the url or posted_at
    assert old.get("posted_at") == "2026-01-01T10:00:00"


print("[2] analytics: follower_series")


def test_follower_series_only_int_counts():
    entries = analytics.load_entries(FIXTURE_LEDGER)
    series = analytics.follower_series(entries)
    # Old (no follower_count), Unbuzzed (100), Buzzed (110), Partial (None) → 2 entries
    assert len(series) == 2, f"expected 2, got {len(series)}: {series}"
    # each element is (str, int)
    for posted_at, count in series:
        assert isinstance(posted_at, str)
        assert isinstance(count, int)
    counts = [c for _, c in series]
    assert counts == [100, 110], f"wrong counts: {counts}"


def test_follower_series_empty():
    assert analytics.follower_series([]) == []


def test_follower_series_no_follower_fields():
    entries = [{"title": "X", "posted_at": "2026-01-01T00:00:00", "url": "u"}]
    assert analytics.follower_series(entries) == []


print("[3] analytics: post_deltas")


def test_post_deltas_delta_chain():
    entries = analytics.load_entries(FIXTURE_LEDGER)
    deltas = analytics.post_deltas(entries)
    assert len(deltas) == 4
    # Each dict has the required keys
    for d in deltas:
        assert "title" in d
        assert "url" in d
        assert "composite" in d
        assert "buzz" in d
        assert "delta" in d
    # Entry 0 (old format, no follower_count): delta always None
    assert deltas[0]["delta"] is None, f"first entry delta must be None, got {deltas[0]['delta']}"
    # Entry 1 (unbuzzed, follower_count 100): prev has no follower_count → None
    assert deltas[1]["delta"] is None, f"prev missing follower_count → None, got {deltas[1]['delta']}"
    # Entry 2 (buzzed, follower_count 110): prev=100 → delta=10
    assert deltas[2]["delta"] == 10, f"110-100=10, got {deltas[2]['delta']}"
    # Entry 3 (partial, follower_count None): own None → delta=None
    assert deltas[3]["delta"] is None, f"None follower_count → delta None, got {deltas[3]['delta']}"


def test_post_deltas_empty():
    assert analytics.post_deltas([]) == []


def test_post_deltas_single():
    entries = analytics.load_entries({"u": {"title": "X", "posted_at": "2026-01-01T00:00:00"}})
    deltas = analytics.post_deltas(entries)
    assert len(deltas) == 1
    assert deltas[0]["delta"] is None


print("[4] analytics: lane_stats")


def test_lane_stats_correct_lanes():
    entries = analytics.load_entries(FIXTURE_LEDGER)
    lanes = analytics.lane_stats(entries)
    # Old format (no query_source) + Unbuzzed (empty query_source) → "unknown"
    # Buzzed + Partial → "agents"
    assert set(lanes.keys()) == {"unknown", "agents"}, f"wrong lanes: {set(lanes.keys())}"
    assert lanes["unknown"]["posts"] == 2
    assert lanes["agents"]["posts"] == 2


def test_lane_stats_avg_composite_2dp():
    entries = analytics.load_entries(FIXTURE_LEDGER)
    lanes = analytics.lane_stats(entries)
    # "unknown": old entry has no composite, unbuzzed has 6.0 → avg of [6.0] = 6.0
    assert lanes["unknown"]["avg_composite"] == 6.0, f"got {lanes['unknown']['avg_composite']}"
    # "agents": buzzed=7.5, partial=5.5 → avg = 6.5
    assert lanes["agents"]["avg_composite"] == 6.5, f"got {lanes['agents']['avg_composite']}"


def test_lane_stats_none_when_no_composite():
    entries = [{"title": "X", "posted_at": "t", "url": "u"}]  # no composite, no query_source
    lanes = analytics.lane_stats(entries)
    assert lanes["unknown"]["avg_composite"] is None


def test_lane_stats_empty():
    assert analytics.lane_stats([]) == {}


print("[5] analytics: buzz_outcome")


def test_buzz_outcome_counts():
    entries = analytics.load_entries(FIXTURE_LEDGER)
    outcome = analytics.buzz_outcome(entries)
    assert set(outcome.keys()) == {"buzzed", "unbuzzed"}
    # buzzed: entries where buzz is not None → Buzzed (8.0) + Partial (5.0) = 2
    assert outcome["buzzed"]["posts"] == 2, f"got {outcome['buzzed']['posts']}"
    # unbuzzed: Old (no buzz key) + Unbuzzed (buzz=None) = 2
    assert outcome["unbuzzed"]["posts"] == 2, f"got {outcome['unbuzzed']['posts']}"


def test_buzz_outcome_avg_delta():
    entries = analytics.load_entries(FIXTURE_LEDGER)
    outcome = analytics.buzz_outcome(entries)
    # Deltas: [None, None, 10, None]
    # buzzed entries (indices 2, 3): deltas [10, None] → only 10 is not None → avg = 10.0
    assert outcome["buzzed"]["avg_delta"] == 10.0, f"got {outcome['buzzed']['avg_delta']}"
    # unbuzzed entries (indices 0, 1): deltas [None, None] → no computable deltas → None
    assert outcome["unbuzzed"]["avg_delta"] is None, f"got {outcome['unbuzzed']['avg_delta']}"


def test_buzz_outcome_empty():
    outcome = analytics.buzz_outcome([])
    assert outcome["buzzed"]["posts"] == 0
    assert outcome["unbuzzed"]["posts"] == 0
    assert outcome["buzzed"]["avg_delta"] is None
    assert outcome["unbuzzed"]["avg_delta"] is None


print("[6] analytics: run_stats")


def test_run_stats_counts():
    entries = analytics.load_entries(FIXTURE_LEDGER)
    stats = analytics.run_stats(7, entries)
    assert stats["runs"] == 7
    assert stats["posts"] == 4
    # Only Entry D has status "partial"
    assert stats["partials"] == 1, f"got {stats['partials']}"


def test_run_stats_empty():
    stats = analytics.run_stats(0, [])
    assert stats == {"runs": 0, "posts": 0, "partials": 0}


def test_run_stats_no_status_field():
    entries = [{"title": "X", "posted_at": "t", "url": "u"}]
    stats = analytics.run_stats(1, entries)
    assert stats["partials"] == 0  # missing status field → not partial


# ── Run all checks ────────────────────────────────────────────────────────────

check("load_entries sorted + url injected", test_load_entries_sorted_and_url_injected)
check("load_entries missing posted_at sorts first", test_load_entries_missing_posted_at_sorts_first)
check("load_entries empty ledger", test_load_entries_empty)
check("load_entries old-format no crash", test_load_entries_old_format_no_crash)

check("follower_series only int counts", test_follower_series_only_int_counts)
check("follower_series empty", test_follower_series_empty)
check("follower_series no follower fields", test_follower_series_no_follower_fields)

check("post_deltas delta chain", test_post_deltas_delta_chain)
check("post_deltas empty", test_post_deltas_empty)
check("post_deltas single entry", test_post_deltas_single)

check("lane_stats correct lanes", test_lane_stats_correct_lanes)
check("lane_stats avg_composite 2dp", test_lane_stats_avg_composite_2dp)
check("lane_stats None when no composite", test_lane_stats_none_when_no_composite)
check("lane_stats empty", test_lane_stats_empty)

check("buzz_outcome counts", test_buzz_outcome_counts)
check("buzz_outcome avg_delta", test_buzz_outcome_avg_delta)
check("buzz_outcome empty", test_buzz_outcome_empty)

check("run_stats counts", test_run_stats_counts)
check("run_stats empty", test_run_stats_empty)
check("run_stats no status field", test_run_stats_no_status_field)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
