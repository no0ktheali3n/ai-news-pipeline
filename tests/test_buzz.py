# tests/test_buzz.py — Phase 1.5 (buzz signal) tests.
#   uv run python tests/test_buzz.py
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from stubs import install_stubs, FAKE_HTTP  # noqa: E402
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


print("[1] buzz: normalization + blend (pure)")

from utils import buzz  # noqa: E402


def test_buzz_score_none_without_signal():
    assert buzz.buzz_score({}) is None, "empty raw must be None"
    assert buzz.buzz_score({"hf_upvotes": None}) is None, "None values must not count"


def test_buzz_score_saturates_at_cap():
    v = buzz.buzz_score({"hf_upvotes": buzz.CAPS["hf_upvotes"]})
    assert v == 10.0, f"upvotes at cap must score 10, got {v}"
    small = buzz.buzz_score({"hf_upvotes": 1})
    big = buzz.buzz_score({"hf_upvotes": 50})
    assert 0 < small < big < 10, f"log curve must be monotonic: {small}, {big}"


def test_buzz_score_takes_strongest_source():
    v = buzz.buzz_score({"hf_upvotes": 1, "hn_points": buzz.CAPS["hn_points"]})
    assert v == 10.0, f"strongest source wins, got {v}"


def test_blend_composite_math():
    scores = {"builder_relevance": 8.0, "novelty": 6.0, "hook_potential": 4.0}
    # LLM-only: 0.5*8 + 0.25*6 + 0.25*4 = 6.5
    assert buzz.blend_composite(scores, None) == 6.5
    # With buzz 10: 0.5*8 + 0.25*6 + 0.125*4 + 0.125*10 = 7.25
    assert buzz.blend_composite(scores, 10.0) == 7.25
    # Buzz equal to hook is a no-op: blend == composite
    assert buzz.blend_composite(scores, 4.0) == 6.5


def test_apply_buzz_reranks_and_annotates():
    scored = [
        {"url": "https://arxiv.org/abs/2607.00001", "title": "A",
         "scores": {"builder_relevance": 8.0, "novelty": 6.0, "hook_potential": 4.0},
         "composite": 6.5},
        {"url": "https://arxiv.org/abs/2607.00002", "title": "B",
         "scores": {"builder_relevance": 7.0, "novelty": 6.0, "hook_potential": 6.0},
         "composite": 6.5},
    ]
    buzz_map = {"2607.00002": {"hn_points": buzz.CAPS["hn_points"]}}  # B gets buzz 10
    out = buzz.apply_buzz(scored, buzz_map)
    assert out[0]["title"] == "B", f"buzzed candidate must lead, got {out[0]['title']}"
    # B: 0.5*7 + 0.25*6 + 0.125*6 + 0.125*10 = 7.0
    assert out[0]["composite"] == 7.0, f"blended composite wrong: {out[0]['composite']}"
    assert out[0]["buzz"] == 10.0 and out[0]["buzz_raw"] == {"hn_points": buzz.CAPS["hn_points"]}
    assert out[1]["buzz"] is None and out[1]["buzz_raw"] is None, "no-signal candidate stays LLM-only"
    assert out[1]["composite"] == 6.5, "no-signal composite untouched"
    assert scored[0]["title"] == "A", "input list must not be mutated"


def test_w_buzz_clamped_to_hook_weight():
    from utils.scoring import W_HOOK
    assert buzz.W_BUZZ <= W_HOOK, f"W_BUZZ {buzz.W_BUZZ} must be clamped to W_HOOK {W_HOOK}"


check("buzz_score None without signal", test_buzz_score_none_without_signal)
check("W_BUZZ clamped to hook weight", test_w_buzz_clamped_to_hook_weight)
check("buzz_score saturates at cap", test_buzz_score_saturates_at_cap)
check("buzz_score takes strongest source", test_buzz_score_takes_strongest_source)
check("blend_composite math", test_blend_composite_math)
check("apply_buzz re-ranks + annotates", test_apply_buzz_reranks_and_annotates)

print("[2] buzz: fetchers (best-effort, budget-capped)")

CANDS = [
    {"url": "https://arxiv.org/abs/2607.00001", "title": "A"},
    {"url": "https://arxiv.org/abs/2607.00002", "title": "B"},
]


def test_fetch_buzz_happy_path():
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["huggingface.co/api/daily_papers"] = [
        {"paper": {"id": "2607.00001", "upvotes": 40}},
        {"paper": {"id": "9999.99999", "upvotes": 7}},   # not ours — ignored
    ]
    FAKE_HTTP.routes["semanticscholar.org"] = [
        {"citationCount": 3}, {"citationCount": 0},
    ]
    FAKE_HTTP.routes["hn.algolia.com"] = {
        "hits": [
            # real submission of the paper — the only hit that may count:
            {"url": "https://arxiv.org/abs/2607.00001", "points": 120, "num_comments": 45},
            # unrelated story that merely full-text-matched the digits:
            {"url": "https://example.com/other", "points": 999, "num_comments": 999},
            # comment-shaped hit (no url/points) — must be ignored, not crash:
            {"comment_text": "see 2607.00001", "points": None},
        ],
    }
    out = buzz.fetch_buzz(CANDS)
    assert out["2607.00001"]["hf_upvotes"] == 40
    assert out["2607.00001"]["s2_citations"] == 3
    assert out["2607.00001"]["hn_points"] == 120, out["2607.00001"]
    assert out["2607.00001"]["hn_comments"] == 45
    assert out["2607.00002"]["s2_citations"] == 0
    assert "hf_upvotes" not in out["2607.00002"]
    # 2607.00002's HN lookup sees the same fake payload but no hit whose url
    # contains ITS id — so it must get no hn_* fields:
    assert "hn_points" not in out["2607.00002"], out["2607.00002"]


def test_fetch_buzz_source_failure_isolated():
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["huggingface.co"] = Exception("HF down")
    FAKE_HTTP.routes["semanticscholar.org"] = Exception("S2 down")
    FAKE_HTTP.routes["hn.algolia.com"] = {
        "hits": [{"url": "https://arxiv.org/abs/2607.00001", "points": 50, "num_comments": 5}]}
    out = buzz.fetch_buzz(CANDS)  # must not raise
    assert out["2607.00001"] == {"hn_points": 50, "hn_comments": 5}, out


def test_fetch_buzz_all_down_returns_empty():
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["huggingface.co"] = Exception("down")
    FAKE_HTTP.routes["semanticscholar.org"] = Exception("down")
    FAKE_HTTP.routes["hn.algolia.com"] = Exception("down")
    assert buzz.fetch_buzz(CANDS) == {}


def test_fetch_buzz_wall_budget_skips_hn():
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["hn.algolia.com"] = {
        "hits": [{"url": "https://arxiv.org/abs/2607.00001", "points": 50, "num_comments": 5}]}
    old = buzz.WALL_BUDGET_S
    buzz.WALL_BUDGET_S = -1.0   # budget already spent
    try:
        out = buzz.fetch_buzz(CANDS)
    finally:
        buzz.WALL_BUDGET_S = old
    hn_calls = [c for c in FAKE_HTTP.calls if "hn.algolia" in c[1]]
    assert not hn_calls, f"HN must be skipped on exhausted budget: {hn_calls}"
    assert out == {}, "no other source routed → empty map"


check("fetch_buzz happy path", test_fetch_buzz_happy_path)
check("fetch_buzz source failure isolated", test_fetch_buzz_source_failure_isolated)
check("fetch_buzz all-down returns empty", test_fetch_buzz_all_down_returns_empty)
check("fetch_buzz wall budget skips HN", test_fetch_buzz_wall_budget_skips_hn)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
