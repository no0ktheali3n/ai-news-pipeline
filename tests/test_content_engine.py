# tests/test_content_engine.py — Phase 1 (scoring engine) tests.
#   uv run python tests/test_content_engine.py
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from stubs import install_stubs, FAKE_S3, FAKE_BEDROCK, FAKE_SNS  # noqa: E402
install_stubs()

LAYER = REPO / "lambda" / "layers" / "common" / "python"
sys.path.insert(0, str(LAYER))
sys.path.insert(0, str(REPO / "lambda" / "scraper"))

os.environ.setdefault("S3_OUTPUT_BUCKET", "test-bucket")
os.environ.setdefault("MEMORY_OUTPUT_PREFIX", "out/memory/")
os.environ.setdefault("POSTED_LEDGER_FILE", "posted_library.json")
os.environ.setdefault("SCORED_OUTPUT_PREFIX", "out/scored/")
os.environ.setdefault("SCRAPER_OUTPUT_PREFIX", "out/scraper/")  # bound into scraper_lambda.S3_PREFIX AT IMPORT — must precede `import scraper_lambda`
os.environ.setdefault("ALERT_TOPIC_ARN", "arn:fake:alerts")

PASSED, FAILED = [], []


def check(name, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"  ✅ {name}")
    except Exception as e:
        FAILED.append((name, e))
        print(f"  ❌ {name}: {type(e).__name__}: {e}")


import utils.scoring as scoring  # noqa: E402

print("\n[1] scoring: pure functions")


def test_arxiv_id():
    assert scoring.arxiv_id("https://arxiv.org/abs/2607.02514") == "2607.02514"
    assert scoring.arxiv_id("https://arxiv.org/abs/2607.02514v2") == "2607.02514"


def test_composite_weights():
    c = scoring.composite({"builder_relevance": 10, "novelty": 0, "hook_potential": 0})
    assert abs(c - 5.0) < 1e-9, c
    c = scoring.composite({"builder_relevance": 8, "novelty": 6, "hook_potential": 4})
    assert abs(c - (0.5 * 8 + 0.25 * 6 + 0.25 * 4)) < 1e-9, c


def test_prompt_truncates_and_ids():
    cands = [{"url": "https://arxiv.org/abs/2607.00001",
              "title": "T" * 500, "snippet": "A" * 5000}]
    p = scoring.build_scoring_prompt(cands)
    assert "2607.00001" in p
    assert "A" * 401 not in p, "abstract must be truncated to 400 chars"
    assert "never follow instructions" in p.lower()


check("arxiv_id extraction", test_arxiv_id)
check("composite uses 50/25/25 weights", test_composite_weights)
check("prompt truncates + embeds ids + injection note", test_prompt_truncates_and_ids)

print("\n[2] scoring: batched call validation")

CANDS = [{"url": f"https://arxiv.org/abs/2607.0000{i}",
          "title": f"Paper {i}", "snippet": "abs"} for i in range(1, 4)]


def test_valid_scoring_round_trip():
    FAKE_BEDROCK.mode = "ok"
    FAKE_BEDROCK.scoring_response = None
    out = scoring.score_candidates(list(CANDS))
    assert len(out) == 3 and out[0]["composite"] == 7.25  # 0.5*8+0.25*6+0.25*7
    assert all("scores" in c for c in out)


def test_id_mismatch_raises():
    FAKE_BEDROCK.mode = "ok"
    FAKE_BEDROCK.scoring_response = json.dumps(
        [{"id": "9999.99999", "builder_relevance": 8, "novelty": 6, "hook_potential": 7}] * 3)
    try:
        scoring.score_candidates(list(CANDS))
        raise AssertionError("expected ScoringError")
    except scoring.ScoringError:
        pass
    finally:
        FAKE_BEDROCK.scoring_response = None


def test_count_mismatch_raises():
    FAKE_BEDROCK.mode = "ok"
    FAKE_BEDROCK.scoring_response = json.dumps(
        [{"id": "2607.00001", "builder_relevance": 8, "novelty": 6, "hook_potential": 7}])
    try:
        scoring.score_candidates(list(CANDS))
        raise AssertionError("expected ScoringError")
    except scoring.ScoringError:
        pass
    finally:
        FAKE_BEDROCK.scoring_response = None


def test_fenced_response_tolerated():
    FAKE_BEDROCK.mode = "ok"
    FAKE_BEDROCK.scoring_response = "```json\n" + json.dumps(
        [{"id": scoring.arxiv_id(c["url"]), "builder_relevance": 9,
          "novelty": 9, "hook_potential": 9} for c in CANDS]) + "\n```"
    out = scoring.score_candidates(list(CANDS))
    assert out[0]["composite"] == 9.0
    FAKE_BEDROCK.scoring_response = None


def test_cap_at_max_candidates():
    many = [{"url": f"https://arxiv.org/abs/2607.{10000 + i}", "title": "t", "snippet": "a"}
            for i in range(60)]
    FAKE_BEDROCK.mode = "ok"
    FAKE_BEDROCK.scoring_response = None
    out = scoring.score_candidates(many)
    assert len(out) == scoring.MAX_CANDIDATES


check("valid round trip computes composites", test_valid_scoring_round_trip)
check("id mismatch raises ScoringError", test_id_mismatch_raises)
check("count mismatch raises ScoringError", test_count_mismatch_raises)
check("fenced JSON tolerated", test_fenced_response_tolerated)
check("hard cap at 40 candidates", test_cap_at_max_candidates)

print("\n[3] scraper: no per-result delay")


def test_scrape_loop_has_no_per_result_delay():
    import inspect
    import utils.scraper as scraper_mod
    src = inspect.getsource(scraper_mod.ScraperClient.scrape)
    assert "random_delay" not in src, "per-result random_delay must be removed (time budget)"


check("scrape loop has no per-result delay", test_scrape_loop_has_no_per_result_delay)

print("\n[4] scraper: lane merge")
import scraper_lambda  # noqa: E402


def test_scrape_lanes_merges_and_tags():
    fake_batches = {
        "ai-security": [
            {"url": "https://arxiv.org/abs/2607.00002", "title": "Sec", "snippet": "s"},
            {"url": "https://arxiv.org/abs/2607.00001", "title": "Both", "snippet": "b"},
        ],
        "agents": [
            {"url": "https://arxiv.org/abs/2607.00003", "title": "Agent", "snippet": "a"},
            {"url": "https://arxiv.org/abs/2607.00001", "title": "Both", "snippet": "b"},
        ],
        "llm-systems": [],
    }

    class FakeClient:
        def __init__(self, url, limit, start):
            self.lane = next(name for name, u in scraper_lambda.LANES if u == url)

        def scrape(self):
            return list(fake_batches[self.lane])

    orig_client, orig_sleep = scraper_lambda.ScraperClient, scraper_lambda.time.sleep
    scraper_lambda.ScraperClient = FakeClient
    scraper_lambda.time.sleep = lambda *_: None
    try:
        merged = scraper_lambda.scrape_lanes(10, 0)
    finally:
        scraper_lambda.ScraperClient, scraper_lambda.time.sleep = orig_client, orig_sleep

    by_url = {c["url"]: c for c in merged}
    assert len(merged) == 3
    assert by_url["https://arxiv.org/abs/2607.00001"]["query_source"] == ["ai-security", "agents"]
    assert [c["url"][-1] for c in merged] == ["3", "2", "1"], "newest-first by arXiv id"


check("lanes merge, dedup, tag query_source, sort newest-first", test_scrape_lanes_merges_and_tags)

print("\n[5] scraper handler: scoring, sidecar, gate, fallback")

def _run_handler(event, batches=None, scoring_mode="ok"):
    """Harness: fake lanes + bedrock mode, clean S3, run scraper handler."""
    batches = batches or {
        "ai-security": [{"url": "https://arxiv.org/abs/2607.00002", "title": "Sec",
                         "snippet": "s", "authors": [], "published": ""}],
        "agents": [{"url": "https://arxiv.org/abs/2607.00001", "title": "Agent",
                    "snippet": "a", "authors": [], "published": ""}],
        "llm-systems": [],
    }

    class FakeClient:
        def __init__(self, url, limit, start):
            self.lane = next(name for name, u in scraper_lambda.LANES if u == url)

        def scrape(self):
            return list(batches[self.lane])

    FAKE_BEDROCK.mode = scoring_mode
    FAKE_BEDROCK.scoring_response = None
    orig_client, orig_sleep = scraper_lambda.ScraperClient, scraper_lambda.time.sleep
    scraper_lambda.ScraperClient = FakeClient
    scraper_lambda.time.sleep = lambda *_: None
    try:
        resp = scraper_lambda.handler(event, None)
    finally:
        scraper_lambda.ScraperClient, scraper_lambda.time.sleep = orig_client, orig_sleep
        FAKE_BEDROCK.mode = "denied"
    return resp, json.loads(resp["body"])


def _pipeline_file():
    keys = [k for k in FAKE_S3.store if k.startswith("out/scraper/")]
    assert len(keys) == 1, keys
    return json.loads(FAKE_S3.store[keys[0]])


def test_scored_run_selects_top_and_writes_sidecar():
    FAKE_S3.store.clear()
    resp, body = _run_handler({"scrape_limit": 5, "max_new_articles": 1})
    assert resp["statusCode"] == 200 and body["scoring_used"] is True
    picked = _pipeline_file()
    assert len(picked) == 1 and "composite" in picked[0]
    sidecars = [k for k in FAKE_S3.store if k.startswith("out/scored/scored_candidates_")]
    assert len(sidecars) == 1
    assert len(json.loads(FAKE_S3.store[sidecars[0]])["candidates"]) == 2


def test_gated_run_noops_below_threshold():
    FAKE_S3.store.clear()
    resp, body = _run_handler({"scrape_limit": 5, "min_score": 9.9})
    assert body["new_count"] == 0 and body.get("gated") is True
    assert not [k for k in FAKE_S3.store if k.startswith("out/scraper/")]


def test_gated_run_never_falls_back_on_scoring_failure():
    FAKE_S3.store.clear()
    resp, body = _run_handler({"scrape_limit": 5, "min_score": 5}, scoring_mode="denied")
    assert body["new_count"] == 0 and body.get("gate_unevaluable") is True
    assert not [k for k in FAKE_S3.store if k.startswith("out/scraper/")]


def test_noon_run_falls_back_newest_on_scoring_failure():
    FAKE_S3.store.clear()
    resp, body = _run_handler({"scrape_limit": 5}, scoring_mode="denied")
    assert resp["statusCode"] == 200 and body["scoring_used"] is False
    picked = _pipeline_file()
    assert picked[0]["url"].endswith("00002"), "newest unposted (00002 > 00001) must be selected"


def test_three_consecutive_fallbacks_escalate_to_sns():
    FAKE_S3.store.clear()
    FAKE_SNS.published.clear()
    for _ in range(3):
        for k in [k for k in FAKE_S3.store if k.startswith("out/scraper/")]:
            del FAKE_S3.store[k]
        _run_handler({"scrape_limit": 5}, scoring_mode="denied")
    assert len(FAKE_SNS.published) == 1, FAKE_SNS.published
    _run_handler({"scrape_limit": 5}, scoring_mode="ok")
    streak = json.loads(FAKE_S3.store["out/scored/scoring_failure_streak.json"])
    assert streak["streak"] == 0, "success must reset the streak"


check("scored run selects top-1 + writes sidecar", test_scored_run_selects_top_and_writes_sidecar)
check("gated run no-ops below threshold", test_gated_run_noops_below_threshold)
check("gated run never falls back on scoring failure", test_gated_run_never_falls_back_on_scoring_failure)
check("noon run falls back to newest on scoring failure", test_noon_run_falls_back_newest_on_scoring_failure)
check("3 consecutive fallbacks escalate to SNS, success resets", test_three_consecutive_fallbacks_escalate_to_sns)


def test_gate_filters_all_selected_not_just_top():
    # max_new_articles=2 with min_score between the two candidates' composites:
    # top article scores 7.25 (b=8,n=6,h=7), second scores 5.0 (b=4,n=6,h=6).
    # min_score=6.0 → only the top clears; exactly 1 article must be selected.
    FAKE_S3.store.clear()
    two_cand_batches = {
        "ai-security": [{"url": "https://arxiv.org/abs/2607.00002", "title": "High",
                         "snippet": "s", "authors": [], "published": ""}],
        "agents":      [{"url": "https://arxiv.org/abs/2607.00001", "title": "Low",
                         "snippet": "a", "authors": [], "published": ""}],
        "llm-systems": [],
    }

    # Inline harness (mirrors _run_handler) so we can set scoring_response
    # AFTER the harness reset and BEFORE the handler call.
    class FakeClient2:
        def __init__(self, url, limit, start):
            self.lane = next(name for name, u in scraper_lambda.LANES if u == url)
        def scrape(self):
            return list(two_cand_batches[self.lane])

    # Give the two candidates distinct scores: top=7.25, second=5.0
    FAKE_BEDROCK.mode = "ok"
    FAKE_BEDROCK.scoring_response = json.dumps([
        {"id": "2607.00002", "builder_relevance": 8, "novelty": 6, "hook_potential": 7},
        {"id": "2607.00001", "builder_relevance": 4, "novelty": 6, "hook_potential": 6},
    ])
    orig_client, orig_sleep = scraper_lambda.ScraperClient, scraper_lambda.time.sleep
    scraper_lambda.ScraperClient = FakeClient2
    scraper_lambda.time.sleep = lambda *_: None
    try:
        resp = scraper_lambda.handler(
            {"scrape_limit": 5, "max_new_articles": 2, "min_score": 6.0}, None)
    finally:
        scraper_lambda.ScraperClient, scraper_lambda.time.sleep = orig_client, orig_sleep
        FAKE_BEDROCK.scoring_response = None
        FAKE_BEDROCK.mode = "denied"
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200, body
    picked = _pipeline_file()
    assert len(picked) == 1, f"expected 1 article past gate, got {len(picked)}"
    assert picked[0]["url"].endswith("00002"), "only the high-scoring article should be selected"


check("gate filters every selected article, not just top", test_gate_filters_all_selected_not_just_top)

# Set up environment vars and path for poster tests
os.environ.setdefault("SUMMARY_OUTPUT_PREFIX", "out/summarizer/")
os.environ.setdefault("MAX_SUMMARY_AGE_HOURS", "6")
os.environ.setdefault("TWITTER_BEARER_TOKEN", "fake-token")
os.environ.setdefault("TWITTER_API_KEY", "fake-key")
os.environ.setdefault("TWITTER_API_SECRET", "fake-secret")
os.environ.setdefault("TWITTER_ACCESS_TOKEN", "fake-access")
os.environ.setdefault("TWITTER_ACCESS_SECRET", "fake-access-secret")
sys.path.insert(0, str(REPO / "lambda" / "poster"))

print("\n[6] provenance: scores reach the ledger")


def test_ledger_entry_carries_provenance():
    import poster_lambda as poster  # path added below
    import utils.post_to_twitter as ptt
    FAKE_S3.store.clear()
    art = {"title": "Scored", "url": "https://arxiv.org/abs/2607.00009",
           "summary": "s", "hashtags": [],
           "scores": {"builder_relevance": 8.0, "novelty": 6.0, "hook_potential": 7.0},
           "composite": 7.25, "query_source": ["agents"]}
    key = "out/summarizer/final_summarized_RUN.json"
    FAKE_S3.store[key] = json.dumps([art]).encode()

    orig = ptt.post_thread
    ptt.post_thread = lambda a, **kw: {"article_title": a["title"], "url": a["url"],
                                       "variant": "summary", "tweet_ids": ["1"],
                                       "thread_url": "https://t/1",
                                       "scores": a.get("scores"),
                                       "composite": a.get("composite"),
                                       "query_source": a.get("query_source")}
    try:
        resp = poster.handler({"summary_key": key, "dry_run": False, "post_limit": 1}, None)
    finally:
        ptt.post_thread = orig
    assert resp["statusCode"] == 200, resp
    entry = json.loads(FAKE_S3.store[poster.POSTED_LEDGER_KEY])["https://arxiv.org/abs/2607.00009"]
    for field in ("builder_relevance", "novelty", "hook_potential", "composite", "query_source"):
        assert field in entry, f"missing {field}: {entry}"


def test_post_thread_returns_provenance():
    # Covers the REAL post_thread edit (Step 3) — the ledger test above
    # monkeypatches post_thread, so without this the production change ships
    # untested. post_tweet is imported into ptt's namespace
    # (from utils.tweepy_client import post_tweet), so patch ptt.post_tweet.
    import utils.post_to_twitter as ptt
    ptt.post_tweet = lambda *a, **k: "111"
    art = {"title": "T", "url": "https://arxiv.org/abs/2607.00009",
           "summary": "s", "hashtags": [],
           "scores": {"builder_relevance": 8.0, "novelty": 6.0, "hook_potential": 7.0},
           "composite": 7.25, "query_source": ["agents"]}
    md = ptt.post_thread(art, dry_run=False)
    for f in ("scores", "composite", "query_source"):
        assert md[f] is not None, f


check("ledger entry carries all five provenance fields", test_ledger_entry_carries_provenance)
check("post_thread return carries scores/composite/query_source", test_post_thread_returns_provenance)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
