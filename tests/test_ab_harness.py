# tests/test_ab_harness.py — A/B writer evaluation harness unit tests.
#   uv run python tests/test_ab_harness.py
#
# Dependency-free: boto3/requests are faked via tests/stubs.py install_stubs.
# Does NOT test real Bedrock calls (those are Task 7 / controller-run).

import sys
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from stubs import install_stubs  # noqa: E402
install_stubs()

LAYER = REPO / "lambda" / "layers" / "common" / "python"
sys.path.insert(0, str(LAYER))
sys.path.insert(0, str(REPO / "scripts"))

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


# ---------------------------------------------------------------------------
# Import the module under test (after stubs installed)
# ---------------------------------------------------------------------------
import ab_writer_eval as harness  # noqa: E402


# ---------------------------------------------------------------------------
# [1] top_n ordering and empty-snippet skip
# ---------------------------------------------------------------------------
print("[1] top_n: ordering + empty-snippet skip")


def test_top_n_ordering():
    candidates = [
        {"id": "a", "title": "A", "url": "http://a", "snippet": "text", "composite": 0.5},
        {"id": "b", "title": "B", "url": "http://b", "snippet": "text", "composite": 0.9},
        {"id": "c", "title": "C", "url": "http://c", "snippet": "text", "composite": 0.7},
    ]
    result = harness.top_n(candidates, n=3)
    assert result[0]["id"] == "b", f"Expected b first, got {result[0]['id']}"
    assert result[1]["id"] == "c", f"Expected c second, got {result[1]['id']}"
    assert result[2]["id"] == "a", f"Expected a third, got {result[2]['id']}"


def test_top_n_skips_empty_snippet():
    candidates = [
        {"id": "a", "title": "A", "url": "http://a", "snippet": "text", "composite": 0.9},
        {"id": "b", "title": "B", "url": "http://b", "snippet": "", "composite": 1.0},
        {"id": "c", "title": "C", "url": "http://c", "snippet": None, "composite": 0.95},
    ]
    result = harness.top_n(candidates, n=3)
    ids = [r["id"] for r in result]
    assert "b" not in ids, "Empty snippet should be excluded"
    assert "c" not in ids, "None snippet should be excluded"
    assert "a" in ids, "Non-empty snippet should be included"


def test_top_n_respects_n_limit():
    candidates = [
        {"id": str(i), "title": f"T{i}", "url": f"http://{i}", "snippet": "x", "composite": float(i)}
        for i in range(20)
    ]
    result = harness.top_n(candidates, n=5)
    assert len(result) == 5, f"Expected 5, got {len(result)}"


check("top_n ordering (highest composite first)", test_top_n_ordering)
check("top_n skips empty snippet", test_top_n_skips_empty_snippet)
check("top_n skips None snippet", lambda: test_top_n_skips_empty_snippet())
check("top_n respects n limit", test_top_n_respects_n_limit)


# ---------------------------------------------------------------------------
# [2] legacy_thread freeze — must produce #AI tag block
# ---------------------------------------------------------------------------
print("[2] legacy_thread freeze: #AI tag block")


def test_legacy_thread_ai_default():
    """Calling legacy_thread with no hashtags must produce the #AI default tag."""
    thread = harness.legacy_thread(
        summary="This paper proposes a new approach to transformers.",
        title="",
        url="https://arxiv.org/abs/2607.00001",
        hashtags=None,  # triggers the ["#AI"] default
    )
    assert isinstance(thread, list), "legacy_thread must return a list"
    assert len(thread) >= 1, "Thread must have at least one tweet"
    # The closing tweet must contain #AI
    closing = thread[-1]
    assert "#AI" in closing, f"Expected #AI in closing tweet, got: {closing!r}"


def test_legacy_thread_tag_block_in_closing():
    """Hashtags passed explicitly appear in the closing tweet."""
    thread = harness.legacy_thread(
        summary="Transformers are becoming more efficient.",
        title="Efficient Transformers",
        url="https://arxiv.org/abs/2607.00002",
        hashtags=["#AI", "#MachineLearning", "#NLP"],
    )
    closing = thread[-1]
    assert "https://arxiv.org/abs/2607.00002" in closing, "URL must be in closing"
    assert "#AI" in closing, "#AI must be in closing"
    assert "#MachineLearning" in closing, "#MachineLearning must be in closing"


def test_legacy_thread_none_hashtags_uses_ai_default():
    """None hashtags → uses frozen ["#AI"] default (v0.9 behavior)."""
    thread = harness.legacy_thread(
        summary="A short summary.",
        title="Title",
        url="https://arxiv.org/abs/2607.00003",
        hashtags=None,
    )
    closing = thread[-1]
    assert "#AI" in closing, f"#AI default not found in closing: {closing!r}"


check("legacy_thread #AI default (no hashtags)", test_legacy_thread_ai_default)
check("legacy_thread tag block in closing tweet", test_legacy_thread_tag_block_in_closing)
check("legacy_thread None hashtags -> #AI default", test_legacy_thread_none_hashtags_uses_ai_default)


# ---------------------------------------------------------------------------
# [3] blinding order mapping: new_first parity → pair_index % 2 == 0
# ---------------------------------------------------------------------------
print("[3] blinding order: new_first parity mapping")


def test_blinding_order_even_index_new_first():
    """Even pair_index → new_first=True (Version 1 = new)."""
    pair = harness.make_pair_dict(
        pair_index=0,
        article={"id": "x", "title": "X", "url": "http://x", "composite": 0.8},
        old_thread=["old tweet"],
        new_thread=["new tweet"],
        new_contract_error=None,
    )
    assert pair["new_first"] is True, f"Even index should give new_first=True, got {pair['new_first']}"


def test_blinding_order_odd_index_old_first():
    """Odd pair_index → new_first=False (Version 1 = old)."""
    pair = harness.make_pair_dict(
        pair_index=1,
        article={"id": "y", "title": "Y", "url": "http://y", "composite": 0.6},
        old_thread=["old tweet"],
        new_thread=["new tweet"],
        new_contract_error=None,
    )
    assert pair["new_first"] is False, f"Odd index should give new_first=False, got {pair['new_first']}"


def test_blinding_pair_dict_fields():
    """make_pair_dict returns all required fields."""
    pair = harness.make_pair_dict(
        pair_index=2,
        article={"id": "z", "title": "Z", "url": "http://z", "composite": 0.75},
        old_thread=["t1", "t2"],
        new_thread=["n1", "n2"],
        new_contract_error="hook too long",
    )
    assert "id" in pair
    assert "title" in pair
    assert "url" in pair
    assert "composite" in pair
    assert "old" in pair
    assert "new" in pair
    assert "new_contract_error" in pair
    assert "new_first" in pair
    assert pair["new_contract_error"] == "hook too long"


def test_blinding_order_multiple_pairs():
    """Check parity alternates correctly across several pairs."""
    expected = [True, False, True, False, True]
    for idx, exp in enumerate(expected):
        pair = harness.make_pair_dict(
            pair_index=idx,
            article={"id": str(idx), "title": "T", "url": "http://x", "composite": 0.5},
            old_thread=[],
            new_thread=[],
            new_contract_error=None,
        )
        assert pair["new_first"] == exp, f"idx={idx}: expected new_first={exp}, got {pair['new_first']}"


check("blinding: even index → new_first=True", test_blinding_order_even_index_new_first)
check("blinding: odd index → new_first=False", test_blinding_order_odd_index_old_first)
check("make_pair_dict has all required fields", test_blinding_pair_dict_fields)
check("blinding parity alternates correctly", test_blinding_order_multiple_pairs)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
total = len(PASSED) + len(FAILED)
print(f"\n{'='*50}")
print(f"test_ab_harness: {len(PASSED)}/{total} passed")
if FAILED:
    for name, err in FAILED:
        print(f"  FAIL: {name} — {err}")
    sys.exit(1)
print("All tests passed.")
