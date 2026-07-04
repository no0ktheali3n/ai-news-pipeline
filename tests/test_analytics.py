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

print("[7] report_html: render_report")

from utils import report_html  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixture for render_report tests
# ---------------------------------------------------------------------------
_SERIES_3 = [
    ("2026-01-02T10:00:00", 100),
    ("2026-01-03T10:00:00", 110),
    ("2026-01-04T10:00:00", 105),
]
_SERIES_1 = [("2026-01-02T10:00:00", 100)]

_DELTAS_FIXTURE = [
    {
        "title": "Good Paper",
        "url": "https://twitter.com/user/status/1",
        "composite": 7.5,
        "buzz": 8.0,
        "delta": 10,
    },
    {
        "title": "Bad Paper <b>evil</b>",
        "url": "https://twitter.com/user/status/2",
        "composite": 5.0,
        "buzz": None,
        "delta": None,
    },
]

_FULL_AGG = {
    "series": _SERIES_3,
    "deltas": _DELTAS_FIXTURE,
    "lanes": {"agents": {"posts": 2, "avg_composite": 6.5}},
    "buzz": {
        "buzzed": {"posts": 1, "avg_delta": 10.0},
        "unbuzzed": {"posts": 1, "avg_delta": None},
    },
    "runs": {"runs": 3, "posts": 2, "partials": 0},
    "milestone": {"target": 500, "current": 42},
}


# ---------------------------------------------------------------------------
# Test 1: empty agg → placeholders, no svg, no script
# ---------------------------------------------------------------------------

def test_render_empty_agg():
    html_out = report_html.render_report({}, "2026-07-04")
    assert "<html" in html_out, "must contain <html"
    assert "collecting data" in html_out, "must contain placeholder text"
    assert "<svg" not in html_out, "no SVG when empty"
    assert "<script" not in html_out, "no <script tags ever"


# ---------------------------------------------------------------------------
# Test 2: follower series SVG presence/absence
# ---------------------------------------------------------------------------

def test_render_svg_with_3_points():
    agg = {"series": _SERIES_3, "deltas": []}
    html_out = report_html.render_report(agg, "2026-07-04")
    assert "<svg" in html_out, "3-point series must produce <svg"
    # polyline points — count coordinate pairs (x,y separated by space)
    import re
    m = re.search(r'<polyline points="([^"]+)"', html_out)
    assert m, "must have a <polyline points=...>"
    pairs = m.group(1).strip().split()
    assert len(pairs) == 3, f"expected 3 coordinate pairs, got {len(pairs)}: {pairs}"


def test_render_no_svg_with_1_point():
    agg = {"series": _SERIES_1, "deltas": []}
    html_out = report_html.render_report(agg, "2026-07-04")
    assert "<svg" not in html_out, "1-point series must NOT produce <svg"


# ---------------------------------------------------------------------------
# Test 3: delta ordering and HTML escaping
# ---------------------------------------------------------------------------

def test_render_delta_ordering_and_escaping():
    agg = {"series": [], "deltas": _DELTAS_FIXTURE}
    html_out = report_html.render_report(agg, "2026-07-04")
    idx_good = html_out.index("Good Paper")
    idx_bad = html_out.index("Bad Paper")
    assert idx_good < idx_bad, "delta=10 row must appear before delta=None row"
    # evil title must be escaped
    assert "&lt;b&gt;" in html_out, "< in title must be HTML-escaped to &lt;"
    assert "<b>evil</b>" not in html_out, "raw <b> tags must not appear in output"


# ---------------------------------------------------------------------------
# Test 4: http only in allowed href attributes
# ---------------------------------------------------------------------------

def test_render_http_only_in_hrefs():
    import re
    html_out = report_report = report_html.render_report(_FULL_AGG, "2026-07-04")
    # Collect all href values that contain http
    href_pattern = re.compile(r'href="([^"]*http[^"]*)"')
    allowed_urls = {m.group(1) for m in href_pattern.finditer(html_out)}
    # Strip those hrefs from the output
    stripped = href_pattern.sub('href="STRIPPED"', html_out)
    assert "http" not in stripped, (
        f"'http' found outside of href attributes in the rendered HTML.\n"
        f"Allowed URLs: {allowed_urls}"
    )


# ---------------------------------------------------------------------------
# Test 5: milestone rendering
# ---------------------------------------------------------------------------

def test_render_milestone_with_current():
    agg = {"milestone": {"target": 500, "current": 42}}
    html_out = report_html.render_report(agg, "2026-07-04")
    assert "42 / 500" in html_out, "must show 'current / target'"


def test_render_milestone_none_current():
    agg = {"milestone": {"target": 500, "current": None}}
    html_out = report_html.render_report(agg, "2026-07-04")
    assert "not yet captured" in html_out, "None current must show 'not yet captured'"


check("render empty agg → placeholders, no svg, no script", test_render_empty_agg)
check("render 3-point series → svg with 3 pairs", test_render_svg_with_3_points)
check("render 1-point series → no svg", test_render_no_svg_with_1_point)
check("render delta ordering + html escaping", test_render_delta_ordering_and_escaping)
check("render http only in hrefs", test_render_http_only_in_hrefs)
check("render milestone current=42", test_render_milestone_with_current)
check("render milestone current=None", test_render_milestone_none_current)

# ── Reporter Lambda tests ─────────────────────────────────────────────────────
print("[8] reporter: lambda handler")

import json  # noqa: E402 — needed for reporter tests (not imported at top of this file)

# Set up envs and path for reporter lambda BEFORE import
os.environ.setdefault("MEMORY_OUTPUT_PREFIX", "out/memory/")
os.environ.setdefault("POSTED_LEDGER_FILE", "posted_library.json")
os.environ.setdefault("SCORED_OUTPUT_PREFIX", "out/scored/")
os.environ.setdefault("REPORTS_OUTPUT_PREFIX", "out/reports/")
os.environ.setdefault("REPORT_TOPIC_ARN", "arn:fake:report-topic")

sys.path.insert(0, str(REPO / "lambda" / "reporter"))

# Re-import FAKE_S3 / FAKE_SNS so tests can inspect/reset them
from stubs import FAKE_S3, FAKE_SNS  # noqa: E402

import reporter_lambda  # noqa: E402


def test_reporter_happy_path():
    """Happy path: ledger with 2 entries + 3 sidecar keys → 200, HTML written, SNS published."""
    FAKE_S3.store.clear()
    FAKE_SNS.published.clear()

    # Seed ledger: two full entries (one with follower_count chain)
    ledger = {
        "https://arxiv.org/abs/2607.00001": {
            "title": "First Paper",
            "posted_at": "2026-07-01T10:00:00",
            "composite": 7.0,
            "buzz": None,
            "buzz_raw": None,
            "query_source": ["agents"],
            "follower_count": 100,
            "tweet_count": 3,
            "status": "posted",
        },
        "https://arxiv.org/abs/2607.00002": {
            "title": "Second Paper",
            "posted_at": "2026-07-02T10:00:00",
            "composite": 8.0,
            "buzz": 7.0,
            "buzz_raw": {"hf_upvotes": 50},
            "query_source": ["agents"],
            "follower_count": 115,
            "tweet_count": 5,
            "status": "posted",
        },
    }
    ledger_key = f"{reporter_lambda.MEMORY_OUTPUT_PREFIX}{reporter_lambda.POSTED_LEDGER_FILE}"
    FAKE_S3.store[ledger_key] = json.dumps(ledger).encode()

    # Seed 3 sidecar keys under scored prefix
    for i in range(1, 4):
        FAKE_S3.listing = [
            {"Key": f"out/scored/scored_candidates_2026-07-0{i}.json"}
            for i in range(1, 4)
        ]

    resp = reporter_lambda.handler({}, None)
    assert resp["statusCode"] == 200, f"expected 200, got {resp}"

    body = json.loads(resp["body"])
    assert body["posts"] == 2, f"expected 2 posts, got {body['posts']}"

    # HTML object written under reports prefix
    reports_keys = [k for k in FAKE_S3.store if k.startswith("out/reports/") and k.endswith(".html")]
    assert reports_keys, "no HTML object written under out/reports/"
    html_bytes = FAKE_S3.store[reports_keys[0]]
    html_str = html_bytes if isinstance(html_bytes, str) else html_bytes.decode("utf-8")
    assert "<html" in html_str.lower(), "report must contain <html"

    # SNS: exactly one publish with presigned URL and "2" posts
    assert len(FAKE_SNS.published) == 1, f"expected 1 SNS publish, got {len(FAKE_SNS.published)}"
    msg = FAKE_SNS.published[0]
    assert msg["Subject"].startswith("[report]"), f"bad subject: {msg['Subject']}"
    assert "fake-presigned" in msg["Message"], "digest must contain presigned URL"
    assert "2" in msg["Message"], "digest must mention post count (2)"


def test_reporter_empty_world():
    """Empty world: no ledger key, no sidecars → 200, report written, no crash."""
    FAKE_S3.store.clear()
    FAKE_S3.listing = []
    FAKE_SNS.published.clear()

    resp = reporter_lambda.handler({}, None)
    assert resp["statusCode"] == 200, f"expected 200, got {resp}"

    body = json.loads(resp["body"])
    assert body["posts"] == 0, f"expected 0 posts, got {body['posts']}"

    reports_keys = [k for k in FAKE_S3.store if k.startswith("out/reports/") and k.endswith(".html")]
    assert reports_keys, "no HTML object written under out/reports/ in empty-world case"

    assert len(FAKE_SNS.published) == 1, "must still publish digest in empty-world case"
    msg = FAKE_SNS.published[0]
    # digest must mention 0 posts
    assert "0" in msg["Message"], f"digest must mention 0: {msg['Message']}"


check("reporter happy path: HTML written + SNS presigned URL + 2 posts", test_reporter_happy_path)
check("reporter empty world: 200 + HTML written + digest published", test_reporter_empty_world)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
