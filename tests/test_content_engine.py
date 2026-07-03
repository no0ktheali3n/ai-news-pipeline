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

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
