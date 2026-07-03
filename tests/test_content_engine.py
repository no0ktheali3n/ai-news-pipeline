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

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
