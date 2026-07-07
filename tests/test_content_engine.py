# tests/test_content_engine.py — Phase 1 (scoring engine) tests.
#   uv run python tests/test_content_engine.py
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from stubs import install_stubs, FAKE_S3, FAKE_BEDROCK, FAKE_SNS, FAKE_HTTP, _HttpResp  # noqa: E402
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
import utils.buzz as buzz_mod  # noqa: E402
import utils.summarizer as summarizer  # noqa: E402

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

def _run_handler(event, batches=None, scoring_mode="ok", scoring_response=None, http_routes=None):
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
    FAKE_BEDROCK.scoring_response = scoring_response
    FAKE_HTTP.reset()   # buzz fetches must never leak routes between tests
    FAKE_HTTP.routes.update(http_routes or {})
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
           "composite": 7.25, "query_source": ["agents"],
           "buzz": 7.5, "buzz_raw": {"hn_points": 120}}
    key = "out/summarizer/final_summarized_RUN.json"
    FAKE_S3.store[key] = json.dumps([art]).encode()

    orig = ptt.post_thread
    ptt.post_thread = lambda a, **kw: {"article_title": a["title"], "url": a["url"],
                                       "variant": "summary", "tweet_ids": ["1"],
                                       "thread_url": "https://t/1",
                                       "scores": a.get("scores"),
                                       "composite": a.get("composite"),
                                       "query_source": a.get("query_source"),
                                       "buzz": a.get("buzz"),
                                       "buzz_raw": a.get("buzz_raw")}
    try:
        resp = poster.handler({"summary_key": key, "dry_run": False, "post_limit": 1}, None)
    finally:
        ptt.post_thread = orig
    assert resp["statusCode"] == 200, resp
    entry = json.loads(FAKE_S3.store[poster.POSTED_LEDGER_KEY])["https://arxiv.org/abs/2607.00009"]
    for field in ("builder_relevance", "novelty", "hook_potential", "composite", "query_source"):
        assert field in entry, f"missing {field}: {entry}"
    assert entry["buzz"] == 7.5 and entry["buzz_raw"] == {"hn_points": 120}


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
           "composite": 7.25, "query_source": ["agents"],
           "buzz": 7.5, "buzz_raw": {"hn_points": 120}}
    md = ptt.post_thread(art, dry_run=False)
    for f in ("scores", "composite", "query_source"):
        assert md[f] is not None, f
    assert md["buzz"] == 7.5 and md["buzz_raw"] == {"hn_points": 120}


check("ledger entry carries all five provenance fields", test_ledger_entry_carries_provenance)
check("post_thread return carries scores/composite/query_source", test_post_thread_returns_provenance)

print("[8] scraper: buzz enrichment")

# LLM scores: A=2607.00001 {8,6,9} → composite 7.75; B=2607.00002 {9,6,6} → 7.5.
# LLM order is [A, B]. HF buzz 100 upvotes → buzz 10 for B ONLY (HF payload is
# per-id; HN/S2 routed dead). Blend(B) = 7.5 − 0.125*6 + 0.125*10 = 8.0 > 7.75,
# so the blended order is [B, A].
BUZZ_SCORES = json.dumps([
    {"id": "2607.00001", "builder_relevance": 8, "novelty": 6, "hook_potential": 9},
    {"id": "2607.00002", "builder_relevance": 9, "novelty": 6, "hook_potential": 6},
])
BUZZ_ROUTES_B_ONLY = {
    "huggingface.co/api/daily_papers": [{"paper": {"id": "2607.00002", "upvotes": 100}}],
    "hn.algolia.com": Exception("down"),
    "semanticscholar.org": Exception("down"),
}


def test_buzz_reranks_selection():
    FAKE_S3.store.clear()
    resp, body = _run_handler({"scrape_limit": 5, "max_new_articles": 1},
                              scoring_response=BUZZ_SCORES,
                              http_routes=BUZZ_ROUTES_B_ONLY)
    assert resp["statusCode"] == 200 and body["scoring_used"] is True
    picked = _pipeline_file()
    assert picked[0]["url"].endswith("2607.00002"), f"buzzed B must win: {picked[0]['url']}"
    assert picked[0]["buzz"] == 10.0 and picked[0]["buzz_raw"] == {"hf_upvotes": 100}
    assert picked[0]["composite"] == 8.0, picked[0]["composite"]
    sidecars = [k for k in FAKE_S3.store if k.startswith("out/scored/scored_candidates_")]
    rows = json.loads(FAKE_S3.store[sidecars[0]])["candidates"]
    assert all("buzz" in r and "buzz_raw" in r for r in rows), "sidecar rows must carry buzz fields"


def test_buzz_failure_keeps_llm_order():
    FAKE_S3.store.clear()
    dead = {"huggingface.co": Exception("down"), "hn.algolia.com": Exception("down"),
            "semanticscholar.org": Exception("down")}
    resp, body = _run_handler({"scrape_limit": 5, "max_new_articles": 1},
                              scoring_response=BUZZ_SCORES, http_routes=dead)
    assert resp["statusCode"] == 200 and body["scoring_used"] is True
    picked = _pipeline_file()
    assert picked[0]["url"].endswith("2607.00001"), "LLM order must hold when buzz is dark"
    assert picked[0]["buzz"] is None and picked[0]["buzz_raw"] is None
    assert picked[0]["composite"] == 7.75


def test_buzz_disabled_no_http():
    FAKE_S3.store.clear()
    old = buzz_mod.BUZZ_ENABLED
    buzz_mod.BUZZ_ENABLED = False
    try:
        resp, body = _run_handler({"scrape_limit": 5, "max_new_articles": 1},
                                  scoring_response=BUZZ_SCORES)
    finally:
        buzz_mod.BUZZ_ENABLED = old
    assert resp["statusCode"] == 200
    buzz_hosts = [u for _, u in FAKE_HTTP.calls
                  if any(h in u for h in ("huggingface", "algolia", "semanticscholar"))]
    assert not buzz_hosts, f"kill switch must mean zero buzz HTTP calls: {buzz_hosts}"
    picked = _pipeline_file()
    assert picked[0]["url"].endswith("2607.00001") and "buzz" not in picked[0]


check("buzz re-ranks selection", test_buzz_reranks_selection)
check("buzz failure keeps LLM order", test_buzz_failure_keeps_llm_order)
check("buzz disabled makes no HTTP calls", test_buzz_disabled_no_http)

print("\n[9] summarizer: writer contract")

import tempfile  # noqa: E402

_WRITER_ARTICLE = {
    "url": "https://arxiv.org/abs/2607.00001",
    "title": "Paper Title",
    "snippet": "An abstract snippet about agents.",
    "authors": ["Author One", "Author Two"],
    "scores": {"builder_relevance": 8, "novelty": 6, "hook_potential": 7},
    "composite": 7.5,
    "query_source": ["agents"],
    "buzz": 8.05,
    "buzz_raw": {"hf_upvotes": 40},
}


def test_writer_produces_validated_tweets():
    FAKE_BEDROCK.mode = "ok"
    FAKE_BEDROCK.writer_response = None
    try:
        result = summarizer.write_thread_with_claude(_WRITER_ARTICLE)
        assert isinstance(result, dict), f"expected dict, got {type(result)}"
        assert "tweets" in result and "summary" in result
        tweets = result["tweets"]
        assert isinstance(tweets, list) and len(tweets) == 3, f"expected 3 tweets, got {tweets}"
        assert "https://arxiv.org/abs/2607.00001" in tweets[-1], f"final tweet missing url: {tweets[-1]}"
        assert result["summary"] == "A plain fallback summary."
    finally:
        FAKE_BEDROCK.mode = "denied"
        FAKE_BEDROCK.writer_response = None


def test_writer_contract_violation_falls_back_to_summary_only():
    FAKE_BEDROCK.mode = "ok"
    FAKE_BEDROCK.writer_response = json.dumps({"tweets": ["only one tweet"], "summary": "still a good summary"})
    try:
        result = summarizer.write_thread_with_claude(_WRITER_ARTICLE)
        assert result["tweets"] is None, f"expected tweets=None on contract violation, got {result['tweets']}"
        assert result["summary"] == "still a good summary", f"summary not preserved: {result['summary']}"
    finally:
        FAKE_BEDROCK.mode = "denied"
        FAKE_BEDROCK.writer_response = None


def test_summarize_articles_output_carries_tweets_and_provenance():
    FAKE_BEDROCK.mode = "ok"
    FAKE_BEDROCK.writer_response = None
    orig_in = summarizer.INPUT_FILE
    orig_out = summarizer.OUTPUT_FILE
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fin:
        json.dump([_WRITER_ARTICLE], fin)
        tmp_in = fin.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fout:
        tmp_out = fout.name
    summarizer.INPUT_FILE = tmp_in
    summarizer.OUTPUT_FILE = tmp_out
    try:
        summarizer.summarize_articles(limit=1)
        with open(tmp_out, "r") as f:
            output = json.load(f)
        assert len(output) == 1, f"expected 1 output article, got {len(output)}"
        art = output[0]
        assert "tweets" in art, "output article must have tweets key"
        assert "summary" in art, "output article must have summary key"
        assert "hashtags" not in art, f"output must not carry hashtags key, got: {list(art.keys())}"
        # provenance spread intact
        assert "scores" in art and isinstance(art["scores"], dict), "scores must survive spread"
        for axis in ("builder_relevance", "novelty", "hook_potential"):
            assert axis in art["scores"], f"missing scores.{axis}"
        for key in ("composite", "query_source", "buzz", "buzz_raw"):
            assert key in art, f"missing provenance key: {key}"
    finally:
        FAKE_BEDROCK.mode = "denied"
        FAKE_BEDROCK.writer_response = None
        summarizer.INPUT_FILE = orig_in
        summarizer.OUTPUT_FILE = orig_out


check("writer produces validated tweets", test_writer_produces_validated_tweets)
check("writer contract violation falls back to summary-only", test_writer_contract_violation_falls_back_to_summary_only)
check("summarize_articles output carries tweets and provenance", test_summarize_articles_output_carries_tweets_and_provenance)

print("\n[9b] summarizer: media/figures wiring")

import utils.figures as _figures  # noqa: E402

# Shared article for media tests — same shape as _WRITER_ARTICLE.
_MEDIA_ARTICLE = {
    "url": "https://arxiv.org/abs/2607.00001",
    "title": "Paper Title",
    "snippet": "An abstract snippet about agents.",
    "authors": ["Author One", "Author Two"],
    "scores": {"builder_relevance": 8, "novelty": 6, "hook_potential": 7},
    "composite": 7.5,
    "query_source": ["agents"],
    "buzz": 8.05,
    "buzz_raw": {"hf_upvotes": 40},
}


def _run_summarize_one(article, writer_response_json=None):
    """Seed a temp input file, run summarize_articles(limit=1), return the single output article."""
    orig_in = summarizer.INPUT_FILE
    orig_out = summarizer.OUTPUT_FILE
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fin:
        json.dump([article], fin)
        tmp_in = fin.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fout:
        tmp_out = fout.name
    FAKE_BEDROCK.mode = "ok"
    if writer_response_json is not None:
        FAKE_BEDROCK.writer_response = writer_response_json
    summarizer.INPUT_FILE = tmp_in
    summarizer.OUTPUT_FILE = tmp_out
    try:
        summarizer.summarize_articles(limit=1)
        with open(tmp_out, "r") as f:
            output = json.load(f)
        assert len(output) == 1, f"expected 1 output article, got {len(output)}"
        return output[0]
    finally:
        FAKE_BEDROCK.mode = "denied"
        FAKE_BEDROCK.writer_response = None
        summarizer.INPUT_FILE = orig_in
        summarizer.OUTPUT_FILE = orig_out


def test_summarizer_spreads_figure_onto_article():
    _fig = {"index": 0, "url": "https://arxiv.org/html/x/im.png",
            "caption": "Figure 1: c", "width": 900, "height": 500}
    orig_fetch = _figures.fetch_figures
    import utils.summarizer as summarizer_module
    orig_mod_fetch = summarizer_module.figures_mod.fetch_figures
    summarizer_module.figures_mod.fetch_figures = lambda url: {
        "figures": [_fig], "license": "CC BY 4.0", "reason": None
    }
    os.environ["MEDIA_ENABLED"] = "true"
    # Writer must return "figure": 0 so the summarizer resolves it to _fig.
    writer_json = json.dumps({
        "tweets": ["A concrete hook under the limit.",
                   "Middle substance for builders.",
                   "Paper Title\nhttps://arxiv.org/abs/2607.00001"],
        "summary": "A plain fallback summary.",
        "figure": 0,
    })
    try:
        out = _run_summarize_one(_MEDIA_ARTICLE, writer_response_json=writer_json)
        assert out["figure"] == _fig, f"figure mismatch: {out.get('figure')}"
        assert out["media_license"] == "CC BY 4.0", f"license mismatch: {out.get('media_license')}"
    finally:
        summarizer_module.figures_mod.fetch_figures = orig_mod_fetch
        os.environ.pop("MEDIA_ENABLED", None)


def test_summarizer_figure_index_out_of_range_is_null():
    _fig = {"index": 0, "url": "https://arxiv.org/html/x/im.png",
            "caption": "Figure 1: c", "width": 900, "height": 500}
    import utils.summarizer as summarizer_module
    orig_mod_fetch = summarizer_module.figures_mod.fetch_figures
    summarizer_module.figures_mod.fetch_figures = lambda url: {
        "figures": [_fig], "license": "CC BY 4.0", "reason": None
    }
    os.environ["MEDIA_ENABLED"] = "true"
    # Writer returns "figure": 7 — out of range with only 1 candidate.
    writer_json = json.dumps({
        "tweets": ["A concrete hook under the limit.",
                   "Middle substance for builders.",
                   "Paper Title\nhttps://arxiv.org/abs/2607.00001"],
        "summary": "A plain fallback summary.",
        "figure": 7,
    })
    try:
        out = _run_summarize_one(_MEDIA_ARTICLE, writer_response_json=writer_json)
        assert out["figure"] is None, f"expected figure=None for out-of-range index, got: {out.get('figure')}"
        # bool is an int subclass — "figure": true must not resolve index 1
        writer_json_bool = json.loads(writer_json)
        writer_json_bool["figure"] = True
        out2 = _run_summarize_one(_MEDIA_ARTICLE, writer_response_json=json.dumps(writer_json_bool))
        assert out2["figure"] is None, f"expected figure=None for boolean index, got: {out2.get('figure')}"
    finally:
        summarizer_module.figures_mod.fetch_figures = orig_mod_fetch
        os.environ.pop("MEDIA_ENABLED", None)


def test_summarizer_media_disabled_no_fetch():
    calls = []
    import utils.summarizer as summarizer_module
    orig_mod_fetch = summarizer_module.figures_mod.fetch_figures
    summarizer_module.figures_mod.fetch_figures = lambda url: calls.append(url)
    # MEDIA_ENABLED not set (default "false")
    os.environ.pop("MEDIA_ENABLED", None)
    try:
        out = _run_summarize_one(_MEDIA_ARTICLE)
        assert calls == [], f"fetch_figures must not be called when MEDIA_ENABLED != true: {calls}"
        assert out.get("figure") is None, f"figure must be None when disabled: {out.get('figure')}"
        assert out.get("media_reason") == "disabled", f"reason must be 'disabled', got: {out.get('media_reason')}"
    finally:
        summarizer_module.figures_mod.fetch_figures = orig_mod_fetch
        os.environ.pop("MEDIA_ENABLED", None)


check("summarizer spreads figure onto article", test_summarizer_spreads_figure_onto_article)
check("summarizer figure index out-of-range → None", test_summarizer_figure_index_out_of_range_is_null)
check("summarizer media disabled makes no fetch call", test_summarizer_media_disabled_no_fetch)

print("\n[10] poster: thread contract")

import utils.post_to_twitter as _ptt  # noqa: E402 — imported once, reused below

_VALID_URL = "https://arxiv.org/abs/2607.00099"


def test_contract_tweets_posted_verbatim_no_hashtags():
    """Valid contract tweets are posted byte-for-byte (after sanitization); no # anywhere."""
    captured = []
    _ptt.post_tweet = lambda text, reply_to_id=None, media_ids=None: (captured.append(text), "999")[1]
    art = {
        "title": "Hook title",
        "url": _VALID_URL,
        "summary": "Fallback summary sentence one. Sentence two.",
        "tweets": [
            "First tweet hook sentence for the thread.",
            "Second tweet with more detail about the paper.",
            f"Third and final tweet. {_VALID_URL}",
        ],
    }
    md = _ptt.post_thread(art, dry_run=False)
    assert md is not None, "post_thread must return metadata"
    assert captured == art["tweets"], f"posted texts differ: {captured}"
    assert all("#" not in t for t in captured), f"hashtag found in contract path: {captured}"
    assert captured[0] == art["tweets"][0], "hook tweet (tweet 1) must be verbatim"


def test_missing_tweets_falls_back_to_summary_no_hashtags():
    """tweets=None triggers summary fallback; final tweet has url; no # anywhere."""
    captured = []
    _ptt.post_tweet = lambda text, reply_to_id=None, media_ids=None: (captured.append(text), "999")[1]
    art = {
        "title": "Paper Title",
        "url": _VALID_URL,
        "summary": "Sentence one about the paper. Sentence two with more info.",
        "tweets": None,
    }
    md = _ptt.post_thread(art, dry_run=False)
    assert md is not None
    assert any(_VALID_URL in t for t in captured), f"url missing from thread: {captured}"
    assert all("#" not in t for t in captured), f"hashtag found in fallback path: {captured}"


def test_invalid_transit_tweets_fall_back():
    """tweets list where final tweet lacks url → fallback to summary path."""
    captured = []
    _ptt.post_tweet = lambda text, reply_to_id=None, media_ids=None: (captured.append(text), "999")[1]
    art = {
        "title": "Paper Title",
        "url": _VALID_URL,
        "summary": "Sentence one. Sentence two.",
        "tweets": ["ok hook", "no link final"],  # final tweet lacks url → re-check fails
    }
    md = _ptt.post_thread(art, dry_run=False)
    assert md is not None
    # Fallback path → a real multi-tweet thread was posted, not the rejected contract list
    assert len(captured) >= 2, f"fallback thread too short: {captured}"
    assert captured != art["tweets"], "rejected contract tweets were posted verbatim"
    assert any(_VALID_URL in t for t in captured), f"fallback url missing: {captured}"
    # The literal "ok hook" string must NOT be the first posted tweet (contract was rejected)
    assert captured[0] != "ok hook", "contract rejected; should have used summary path"


def test_hook_over_240_fails_transit_recheck():
    """Hook of 250 chars (valid ≤280 but >240) must fail the transit re-check → summary fallback."""
    captured = []
    _ptt.post_tweet = lambda text, reply_to_id=None, media_ids=None: (captured.append(text), "999")[1]
    long_hook = "A" * 250   # 250 chars: passes TWEET_MAX(280) but fails HOOK_MAX(240)
    art = {
        "title": "Paper Title",
        "url": _VALID_URL,
        "summary": "Sentence one. Sentence two.",
        "tweets": [long_hook, f"Paper details\n{_VALID_URL}"],
    }
    md = _ptt.post_thread(art, dry_run=False)
    assert md is not None
    # Transit re-check must have rejected it; fallback path posts summary thread
    assert captured[0] != long_hook, "hook with 250 chars should be rejected by transit re-check"
    assert any(_VALID_URL in t for t in captured), f"fallback url missing: {captured}"


def test_default_hashtags_constant_deleted():
    """DEFAULT_HASHTAGS must not exist on the ptt module."""
    assert not hasattr(_ptt, "DEFAULT_HASHTAGS"), \
        "DEFAULT_HASHTAGS still present — must be deleted from post_to_twitter"


check("contract tweets posted verbatim, no hashtags", test_contract_tweets_posted_verbatim_no_hashtags)
check("missing tweets falls back to summary, no hashtags", test_missing_tweets_falls_back_to_summary_no_hashtags)
check("invalid transit tweets fall back to summary path", test_invalid_transit_tweets_fall_back)
check("hook >240 chars fails transit re-check → summary fallback", test_hook_over_240_fails_transit_recheck)
check("DEFAULT_HASHTAGS constant deleted", test_default_hashtags_constant_deleted)

print("\n[11] poster: mid-thread policy")

import utils.post_to_twitter as ptt  # noqa: E402 — alias for section 11


def _scripted_post_tweet(script):
    calls = []
    def fake(text, reply_to_id=None):
        calls.append(text)
        return script.pop(0) if script else None
    return fake, calls


def test_mid_thread_retry_succeeds():
    """Tweet 2 fails once, retry succeeds → status=posted, 3 ids, 4 calls."""
    orig_sleep = ptt.time.sleep
    script = ["id1", None, "id2", "id3"]
    fake, calls = _scripted_post_tweet(script)
    ptt.post_tweet = fake
    ptt.time.sleep = lambda *_: None
    try:
        art = {
            "title": "T", "url": "https://arxiv.org/abs/2607.00099",
            "summary": "s", "hashtags": [],
            "tweets": [
                "First tweet hook sentence for the thread.",
                "Second tweet with more detail about the paper.",
                "Third and final tweet. https://arxiv.org/abs/2607.00099",
            ],
            "scores": None, "composite": None, "query_source": None,
            "buzz": None, "buzz_raw": None,
        }
        md = ptt.post_thread(art, dry_run=False)
        assert md is not None, "should return metadata"
        assert md["status"] == "posted", f"expected posted, got {md['status']}"
        assert len(md["tweet_ids"]) == 3, f"expected 3 ids: {md['tweet_ids']}"
        assert len(calls) == 4, f"expected 4 post_tweet calls: {len(calls)}"
    finally:
        ptt.time.sleep = orig_sleep


def test_mid_thread_double_failure_posts_closing_reply_and_partial():
    """Tweet 2 fails twice → closing reply with arXiv url, status=partial, provenance intact."""
    orig_sleep = ptt.time.sleep
    script = ["id1", None, None, "id9"]
    fake, calls = _scripted_post_tweet(script)
    ptt.post_tweet = fake
    ptt.time.sleep = lambda *_: None
    try:
        art = {
            "title": "T", "url": "https://arxiv.org/abs/2607.00099",
            "summary": "s", "hashtags": [],
            "tweets": [
                "First tweet hook sentence for the thread.",
                "Second tweet with more detail about the paper.",
                "Third and final tweet. https://arxiv.org/abs/2607.00099",
            ],
            "scores": {"builder_relevance": 8.0, "novelty": 6.0, "hook_potential": 7.0},
            "composite": 7.25, "query_source": ["agents"],
            "buzz": 7.5, "buzz_raw": {"hn_points": 120},
        }
        md = ptt.post_thread(art, dry_run=False)
        assert md is not None, "should return metadata on partial"
        assert md["status"] == "partial", f"expected partial, got {md['status']}"
        # The closing reply text must contain the arXiv url
        assert any("https://arxiv.org/abs/2607.00099" in t for t in calls), \
            f"no closing reply with arXiv url in calls: {calls}"
        # Provenance fields must still be present
        assert md["scores"] is not None, "scores must be in partial metadata"
        assert md["composite"] == 7.25, "composite must be in partial metadata"
        assert md["query_source"] == ["agents"], "query_source must be in partial metadata"
    finally:
        ptt.time.sleep = orig_sleep


def test_first_tweet_double_failure_returns_none():
    """Tweet 1 fails twice → returns None (nothing posted, no ledger)."""
    orig_sleep = ptt.time.sleep
    script = [None, None]
    fake, calls = _scripted_post_tweet(script)
    ptt.post_tweet = fake
    ptt.time.sleep = lambda *_: None
    try:
        art = {
            "title": "T", "url": "https://arxiv.org/abs/2607.00099",
            "summary": "s", "hashtags": [],
            "tweets": [
                "First tweet hook sentence for the thread.",
                "Second tweet with more detail about the paper.",
                "Third and final tweet. https://arxiv.org/abs/2607.00099",
            ],
            "scores": None, "composite": None, "query_source": None,
            "buzz": None, "buzz_raw": None,
        }
        md = ptt.post_thread(art, dry_run=False)
        assert md is None, f"expected None on tweet-1 double failure, got {md}"
    finally:
        ptt.time.sleep = orig_sleep


def test_ledger_stores_status():
    """record_posted persists the status field from metadata."""
    import poster_lambda as poster
    FAKE_S3.store.clear()
    art = {"title": "Scored", "url": "https://arxiv.org/abs/2607.00009",
           "summary": "s", "hashtags": [],
           "scores": {"builder_relevance": 8.0, "novelty": 6.0, "hook_potential": 7.0},
           "composite": 7.25, "query_source": ["agents"],
           "buzz": 7.5, "buzz_raw": {"hn_points": 120}}
    key = "out/summarizer/final_summarized_RUN.json"
    FAKE_S3.store[key] = json.dumps([art]).encode()

    orig = ptt.post_thread
    ptt.post_thread = lambda a, **kw: {"article_title": a["title"], "url": a["url"],
                                       "variant": "summary", "tweet_ids": ["1"],
                                       "thread_url": "https://t/1",
                                       "scores": a.get("scores"),
                                       "composite": a.get("composite"),
                                       "query_source": a.get("query_source"),
                                       "buzz": a.get("buzz"),
                                       "buzz_raw": a.get("buzz_raw"),
                                       "status": "posted"}
    try:
        resp = poster.handler({"summary_key": key, "dry_run": False, "post_limit": 1}, None)
    finally:
        ptt.post_thread = orig
    assert resp["statusCode"] == 200, resp
    entry = json.loads(FAKE_S3.store[poster.POSTED_LEDGER_KEY])["https://arxiv.org/abs/2607.00009"]
    assert "status" in entry, f"status missing from ledger entry: {entry}"
    assert entry["status"] == "posted", f"expected posted, got {entry['status']}"


check("mid-thread retry succeeds → posted", test_mid_thread_retry_succeeds)
check("mid-thread double failure → partial + closing reply", test_mid_thread_double_failure_posts_closing_reply_and_partial)
check("first-tweet double failure → None", test_first_tweet_double_failure_returns_none)
check("ledger stores status field", test_ledger_stores_status)

print("\n[12] follower_count + tweet_count capture")

import sys as _sys
_tweepy = _sys.modules["tweepy"]
_FAKE_TWEEPY_STATE = _tweepy.FAKE_TWEEPY_STATE


def _reset_tweepy_state():
    _FAKE_TWEEPY_STATE["get_me_error"] = False
    _FAKE_TWEEPY_STATE["followers"] = 42


def test_successful_post_carries_tweet_count_and_follower_count():
    """3-tweet post → metadata tweet_count == 3 and follower_count == 42."""
    _reset_tweepy_state()
    orig_sleep = ptt.time.sleep
    script = ["id1", "id2", "id3"]
    fake, calls = _scripted_post_tweet(script)
    ptt.post_tweet = fake
    ptt.time.sleep = lambda *_: None
    try:
        art = {
            "title": "T", "url": "https://arxiv.org/abs/2607.00099",
            "summary": "s", "hashtags": [],
            "tweets": [
                "First tweet hook sentence for the thread.",
                "Second tweet with more detail about the paper.",
                "Third and final tweet. https://arxiv.org/abs/2607.00099",
            ],
            "scores": None, "composite": None, "query_source": None,
            "buzz": None, "buzz_raw": None,
        }
        md = ptt.post_thread(art, dry_run=False)
        assert md is not None, "post_thread must return metadata"
        assert md["tweet_count"] == 3, f"expected tweet_count=3, got {md.get('tweet_count')}"
        assert md["follower_count"] == 42, f"expected follower_count=42, got {md.get('follower_count')}"
    finally:
        ptt.time.sleep = orig_sleep


def test_get_me_failure_does_not_block_post():
    """get_me failure → post still succeeds, follower_count is None."""
    _reset_tweepy_state()
    _FAKE_TWEEPY_STATE["get_me_error"] = True
    orig_sleep = ptt.time.sleep
    script = ["id1", "id2", "id3"]
    fake, calls = _scripted_post_tweet(script)
    ptt.post_tweet = fake
    ptt.time.sleep = lambda *_: None
    try:
        art = {
            "title": "T", "url": "https://arxiv.org/abs/2607.00099",
            "summary": "s", "hashtags": [],
            "tweets": [
                "First tweet hook sentence for the thread.",
                "Second tweet with more detail about the paper.",
                "Third and final tweet. https://arxiv.org/abs/2607.00099",
            ],
            "scores": None, "composite": None, "query_source": None,
            "buzz": None, "buzz_raw": None,
        }
        md = ptt.post_thread(art, dry_run=False)
        assert md is not None, "post must succeed even when get_me errors"
        assert md["follower_count"] is None, (
            f"expected follower_count=None on error, got {md.get('follower_count')}")
        assert md["tweet_count"] == 3, f"tweet_count must still be set: {md.get('tweet_count')}"
    finally:
        ptt.time.sleep = orig_sleep
        _reset_tweepy_state()


def test_ledger_entry_carries_tweet_count_and_follower_count():
    """Extend provenance test: ledger entry stores tweet_count and follower_count."""
    _reset_tweepy_state()
    import poster_lambda as poster
    import utils.post_to_twitter as _ptt2
    FAKE_S3.store.clear()
    art = {"title": "Scored", "url": "https://arxiv.org/abs/2607.00009",
           "summary": "s", "hashtags": [],
           "scores": {"builder_relevance": 8.0, "novelty": 6.0, "hook_potential": 7.0},
           "composite": 7.25, "query_source": ["agents"],
           "buzz": 7.5, "buzz_raw": {"hn_points": 120}}
    key = "out/summarizer/final_summarized_RUN.json"
    FAKE_S3.store[key] = json.dumps([art]).encode()

    orig = _ptt2.post_thread
    _ptt2.post_thread = lambda a, **kw: {
        "article_title": a["title"], "url": a["url"],
        "variant": "summary", "tweet_ids": ["1", "2", "3"],
        "thread_url": "https://t/1",
        "scores": a.get("scores"),
        "composite": a.get("composite"),
        "query_source": a.get("query_source"),
        "buzz": a.get("buzz"),
        "buzz_raw": a.get("buzz_raw"),
        "status": "posted",
        "tweet_count": 3,
        "follower_count": 42,
    }
    try:
        resp = poster.handler({"summary_key": key, "dry_run": False, "post_limit": 1}, None)
    finally:
        _ptt2.post_thread = orig
    assert resp["statusCode"] == 200, resp
    entry = json.loads(FAKE_S3.store[poster.POSTED_LEDGER_KEY])["https://arxiv.org/abs/2607.00009"]
    assert entry.get("tweet_count") == 3, f"tweet_count missing/wrong in ledger: {entry}"
    assert entry.get("follower_count") == 42, f"follower_count missing/wrong in ledger: {entry}"


check("successful 3-tweet post → tweet_count=3, follower_count=42", test_successful_post_carries_tweet_count_and_follower_count)
check("get_me failure → post succeeds, follower_count=None", test_get_me_failure_does_not_block_post)
check("ledger entry carries tweet_count + follower_count", test_ledger_entry_carries_tweet_count_and_follower_count)

print("\n[13] get_me timeout: hung network call does not block post")

import threading as _threading  # noqa: E402
import utils.tweepy_client as _tc  # noqa: E402


def test_get_me_hang_returns_none_and_post_succeeds():
    """get_me that sleeps forever is cut off by the 10s timeout (patched to 0.05s).

    The test completes in <2s and asserts follower_count is None while the post succeeds.
    Implementation: monkeypatch the timeout value module-side so the ThreadPoolExecutor
    future.result(timeout=...) fires quickly.
    """
    _reset_tweepy_state()

    # Patch the fake tweepy client to hang indefinitely inside get_me.
    barrier = _threading.Event()

    class _HangingClient:
        def get_me(self, user_fields=None):
            barrier.wait(timeout=5)  # blocks until test finishes or 5s safety timeout
            raise Exception("should never reach here in normal test flow")

    orig_get_twitter_client = _tc.get_twitter_client
    _tc.get_twitter_client = lambda: _HangingClient()

    # Patch the PRODUCTION timeout constant down so the real get_follower_count
    # (not a test copy) trips its ThreadPoolExecutor timeout fast.
    import utils.tweepy_client as _tc2
    orig_timeout_v = _tc2.GET_ME_TIMEOUT_S
    _tc2.GET_ME_TIMEOUT_S = 0.05

    orig_sleep = ptt.time.sleep
    script = ["id1", "id2", "id3"]
    fake, calls = _scripted_post_tweet(script)
    ptt.post_tweet = fake
    ptt.time.sleep = lambda *_: None
    try:
        art = {
            "title": "T", "url": "https://arxiv.org/abs/2607.00099",
            "summary": "s", "hashtags": [],
            "tweets": [
                "First tweet hook sentence for the thread.",
                "Second tweet with more detail about the paper.",
                "Third and final tweet. https://arxiv.org/abs/2607.00099",
            ],
            "scores": None, "composite": None, "query_source": None,
            "buzz": None, "buzz_raw": None,
        }
        import time as _time
        t0 = _time.monotonic()
        md = ptt.post_thread(art, dry_run=False)
        elapsed = _time.monotonic() - t0
        barrier.set()  # unblock the hanging thread so the thread pool can clean up
        assert elapsed < 2.0, f"post_thread took too long ({elapsed:.2f}s) — timeout not working"
        assert md is not None, "post must succeed even when get_me hangs"
        assert md["follower_count"] is None, (
            f"follower_count must be None on hang, got {md.get('follower_count')}")
        assert md["tweet_count"] == 3, f"tweet_count must still be 3, got {md.get('tweet_count')}"
    finally:
        barrier.set()
        ptt.time.sleep = orig_sleep
        _tc.get_twitter_client = orig_get_twitter_client
        _tc2.GET_ME_TIMEOUT_S = orig_timeout_v
        _reset_tweepy_state()


check("get_me hang → follower_count=None, post succeeds, completes <2s", test_get_me_hang_returns_none_and_post_succeeds)

print("\n[integration] scoring: bedrock-denied → openrouter fallback")

def test_scoring_falls_back_to_openrouter():
    """With Bedrock denied and OpenRouter configured, score_candidates succeeds."""
    FAKE_BEDROCK.mode = "denied"
    FAKE_BEDROCK.scoring_response = None
    # Valid chat-completions body whose content is a scoring array for CANDS
    or_content = json.dumps([
        {"id": "2607.00001", "builder_relevance": 8, "novelty": 6, "hook_potential": 7},
        {"id": "2607.00002", "builder_relevance": 7, "novelty": 5, "hook_potential": 6},
        {"id": "2607.00003", "builder_relevance": 9, "novelty": 8, "hook_potential": 8},
    ])
    FAKE_HTTP.routes["openrouter.ai"] = {
        "choices": [{"message": {"content": or_content}}]
    }
    os.environ["LLM_FALLBACK_PROVIDER"] = "openrouter"
    os.environ["OPENROUTER_API_KEY"] = "test-key"
    try:
        result = scoring.score_candidates(list(CANDS))
        assert len(result) == 3, f"expected 3 results, got {len(result)}"
        for r in result:
            assert "composite" in r and "scores" in r, f"missing composite/scores: {r}"
    finally:
        FAKE_HTTP.routes.pop("openrouter.ai", None)
        os.environ.pop("LLM_FALLBACK_PROVIDER", None)
        os.environ.pop("OPENROUTER_API_KEY", None)
        FAKE_BEDROCK.mode = "denied"

check("bedrock denied → openrouter fallback → scoring succeeds", test_scoring_falls_back_to_openrouter)

print("\n[15] poster: media upload subsystem")

import utils.post_to_twitter as _ptt_media  # noqa: E402 — fresh alias for media section

FIG_URL = "https://arxiv.org/html/2607.00001/fig1.png"
_PNG_HEADER = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
# Pad to >10KB (required by _download_figure guard)
_PNG_BYTES = _PNG_HEADER + b"\x00" * (10_500 - len(_PNG_HEADER))

article_with_figure = {
    "url": "https://arxiv.org/abs/2607.00001",
    "title": "Media Test Paper",
    "snippet": "A snippet about media.",
    "authors": ["Author A"],
    "scores": {"builder_relevance": 8, "novelty": 6, "hook_potential": 7},
    "composite": 7.5,
    "query_source": ["agents"],
    "buzz": 8.0,
    "buzz_raw": {"hf_upvotes": 30},
    "summary": "Summary sentence one. Sentence two about the paper.",
    "tweets": [
        "A concrete hook under the limit.",
        "Middle substance for builders.",
        "Paper Title\nhttps://arxiv.org/abs/2607.00001",
    ],
    "figure": {
        "index": 0,
        "url": FIG_URL,
        "caption": "Figure 1: test caption",
        "width": 900,
        "height": 500,
    },
    "media_license": "CC BY 4.0",
}


def _setup_figure_route():
    """Register FIG_URL in FAKE_HTTP to return valid image/png bytes >10KB."""
    FAKE_HTTP.routes[FIG_URL] = _HttpResp(
        status=200,
        content=_PNG_BYTES,
        headers={"Content-Type": "image/png"},
    )


def _teardown_media():
    """Clean up env and tweepy state after each media test."""
    os.environ.pop("MEDIA_ENABLED", None)
    import sys as _sys
    _tweepy2 = _sys.modules["tweepy"]
    _tweepy2.API.reset()
    FAKE_HTTP.reset()


def test_media_uploaded_once_and_attached_to_hook_only():
    _tweepy2 = __import__("sys").modules["tweepy"]
    _tweepy2.API.reset()
    os.environ["MEDIA_ENABLED"] = "true"
    _setup_figure_route()
    calls = []
    orig_pt = _ptt_media.post_tweet
    _ptt_media.post_tweet = lambda text, reply_to_id=None, media_ids=None: (calls.append(media_ids), f"id{len(calls)}")[1]
    try:
        md = _ptt_media.post_thread(article_with_figure, dry_run=False)
        assert len(_tweepy2.API.uploads) == 1, f"expected 1 upload, got {len(_tweepy2.API.uploads)}"
        assert calls[0] == ["777000"], f"hook tweet must carry media_id, got {calls[0]}"
        assert all(c is None for c in calls[1:]), f"only hook gets media, rest must be None: {calls[1:]}"
        assert md["media"] == {
            "attempted": True, "figure_url": FIG_URL, "license": "CC BY 4.0",
            "uploaded": True, "attached": True, "skip_reason": None,
        }, f"unexpected media dict: {md['media']}"
    finally:
        _ptt_media.post_tweet = orig_pt
        _teardown_media()


def test_media_upload_once_even_when_tweet1_retries():
    """Upload happens once; both initial and retry call to tweet-1 carry the same media_id."""
    _tweepy2 = __import__("sys").modules["tweepy"]
    _tweepy2.API.reset()
    os.environ["MEDIA_ENABLED"] = "true"
    _setup_figure_route()
    calls = []
    orig_pt = _ptt_media.post_tweet
    orig_sleep = _ptt_media.time.sleep
    _ptt_media.time.sleep = lambda *_: None
    # First call to tweet-1 returns None (simulates failure); retry returns id1
    script = [None, "id1", "id2", "id3"]
    def scripted(text, reply_to_id=None, media_ids=None):
        calls.append(media_ids)
        return script.pop(0) if script else None
    _ptt_media.post_tweet = scripted
    try:
        md = _ptt_media.post_thread(article_with_figure, dry_run=False)
        assert len(_tweepy2.API.uploads) == 1, f"expected 1 upload even after retry, got {len(_tweepy2.API.uploads)}"
        assert calls[0] == ["777000"], f"initial call must have media_id: {calls[0]}"
        assert calls[1] == ["777000"], f"retry call must carry same media_id: {calls[1]}"
    finally:
        _ptt_media.post_tweet = orig_pt
        _ptt_media.time.sleep = orig_sleep
        _teardown_media()


def test_media_download_fail_posts_text_only():
    """FAKE_HTTP returns 404 for figure URL → skip_reason=download_failed, no upload."""
    _tweepy2 = __import__("sys").modules["tweepy"]
    _tweepy2.API.reset()
    os.environ["MEDIA_ENABLED"] = "true"
    # Route returns 404 (not found)
    FAKE_HTTP.routes[FIG_URL] = _HttpResp(status=404, content=b"", headers={})
    orig_pt = _ptt_media.post_tweet
    _ptt_media.post_tweet = lambda text, reply_to_id=None, media_ids=None: "tid"
    try:
        md = _ptt_media.post_thread(article_with_figure, dry_run=False)
        assert md["media"]["attached"] is False, "should not attach on download failure"
        assert md["media"]["skip_reason"] == "download_failed", f"wrong skip_reason: {md['media']['skip_reason']}"
        assert len(_tweepy2.API.uploads) == 0, "no upload on download failure"
    finally:
        _ptt_media.post_tweet = orig_pt
        _teardown_media()


def test_media_poster_flag_off_skips():
    """MEDIA_ENABLED=false → skip_reason=disabled, no download, no upload."""
    _tweepy2 = __import__("sys").modules["tweepy"]
    _tweepy2.API.reset()
    os.environ["MEDIA_ENABLED"] = "false"
    orig_pt = _ptt_media.post_tweet
    _ptt_media.post_tweet = lambda text, reply_to_id=None, media_ids=None: "tid"
    try:
        md = _ptt_media.post_thread(article_with_figure, dry_run=False)
        assert md["media"]["skip_reason"] == "disabled", f"wrong skip_reason: {md['media']['skip_reason']}"
        assert len(_tweepy2.API.uploads) == 0, "no upload when flag off"
    finally:
        _ptt_media.post_tweet = orig_pt
        _teardown_media()


def test_media_upload_fail_posts_text_only():
    """upload failure → skip_reason=upload_failed, media not attached, post still succeeds."""
    _tweepy2 = __import__("sys").modules["tweepy"]
    _tweepy2.API.reset()
    _tweepy2.API.fail_upload = True
    os.environ["MEDIA_ENABLED"] = "true"
    _setup_figure_route()
    orig_pt = _ptt_media.post_tweet
    _ptt_media.post_tweet = lambda text, reply_to_id=None, media_ids=None: "tid"
    try:
        md = _ptt_media.post_thread(article_with_figure, dry_run=False)
        assert md["media"]["uploaded"] is False, "uploaded must be False on upload failure"
        assert md["media"]["skip_reason"] == "upload_failed", f"wrong skip_reason: {md['media']['skip_reason']}"
    finally:
        _ptt_media.post_tweet = orig_pt
        _teardown_media()


def test_media_dry_run_logs_but_never_uploads():
    """dry_run=True → no upload, metadata carries skip_reason=dry_run, media block attempted."""
    _tweepy2 = __import__("sys").modules["tweepy"]
    _tweepy2.API.reset()
    os.environ["MEDIA_ENABLED"] = "true"
    _setup_figure_route()
    try:
        md = _ptt_media.post_thread(article_with_figure, dry_run=True)
        assert len(_tweepy2.API.uploads) == 0, "dry_run must never upload"
        assert md is not None, "dry_run must return metadata (not None)"
        assert md["media"]["skip_reason"] == "dry_run", f"wrong skip_reason: {md.get('media', {}).get('skip_reason')}"
    finally:
        _teardown_media()


check("media: uploaded once, attached to hook only", test_media_uploaded_once_and_attached_to_hook_only)
check("media: uploaded once even when tweet-1 retries", test_media_upload_once_even_when_tweet1_retries)
check("media: download fail → text-only post", test_media_download_fail_posts_text_only)
check("media: MEDIA_ENABLED=false → disabled skip", test_media_poster_flag_off_skips)
check("media: upload fail → text-only post", test_media_upload_fail_posts_text_only)
check("media: dry_run never uploads, returns metadata", test_media_dry_run_logs_but_never_uploads)


def test_download_figure_revalidates_host_and_scheme():
    # Poster-side re-validation: the figure URL travels via an S3 artifact,
    # so the poster is an independent enforcement point (security review).
    from utils import tweepy_client as _twc
    assert _twc._download_figure("https://evil.example/x.png") is None
    assert _twc._download_figure("https://evilarxiv.org/x.png") is None   # look-alike
    assert _twc._download_figure("http://arxiv.org/x.png") is None        # https only


check("media: poster re-validates figure host/scheme", test_download_figure_revalidates_host_and_scheme)

# ---------------------------------------------------------------------------
# Task 5: ledger persists media key
# ---------------------------------------------------------------------------
print("\n[16] poster: media ledger persistence")


def test_record_posted_persists_media():
    """record_posted stores the media key from metadata into the ledger entry."""
    import poster_lambda as poster
    FAKE_S3.store.clear()
    art = {
        "title": "Media Paper",
        "url": "https://arxiv.org/abs/2607.00009",
        "summary": "s",
        "hashtags": [],
        "scores": {"builder_relevance": 8.0, "novelty": 6.0, "hook_potential": 7.0},
        "composite": 7.25,
        "query_source": ["agents"],
        "buzz": 7.5,
        "buzz_raw": {"hn_points": 120},
    }
    key = "out/summarizer/final_summarized_RUN.json"
    FAKE_S3.store[key] = json.dumps([art]).encode()

    media_payload = {
        "attempted": True,
        "figure_url": "https://arxiv.org/html/2607.00009/fig1.png",
        "license": "CC-BY-4.0",
        "uploaded": True,
        "attached": True,
        "skip_reason": None,
    }

    orig = ptt.post_thread
    ptt.post_thread = lambda a, **kw: {
        "article_title": a["title"],
        "url": a["url"],
        "variant": "summary",
        "tweet_ids": ["1"],
        "thread_url": "https://t/1",
        "scores": a.get("scores"),
        "composite": a.get("composite"),
        "query_source": a.get("query_source"),
        "buzz": a.get("buzz"),
        "buzz_raw": a.get("buzz_raw"),
        "status": "posted",
        "media": media_payload,
    }
    try:
        resp = poster.handler({"summary_key": key, "dry_run": False, "post_limit": 1}, None)
    finally:
        ptt.post_thread = orig
    assert resp["statusCode"] == 200, resp
    entry = json.loads(FAKE_S3.store[poster.POSTED_LEDGER_KEY])["https://arxiv.org/abs/2607.00009"]
    assert "media" in entry, f"media key missing from ledger entry: {entry}"
    assert entry["media"]["attached"] is True, f"expected attached=True, got {entry['media']}"


check("record_posted persists media key into ledger", test_record_posted_persists_media)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
