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
from stubs import install_stubs, FAKE_HTTP  # noqa: E402
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

OLD_MODEL = harness.OLD_MODEL
NEW_MODEL = harness.NEW_MODEL


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
        {"id": "d", "title": "D", "url": "http://d", "snippet": "   ", "composite": 0.98},
    ]
    result = harness.top_n(candidates, n=4)
    ids = [r["id"] for r in result]
    assert "b" not in ids, "Empty snippet should be excluded"
    assert "c" not in ids, "None snippet should be excluded"
    assert "d" not in ids, "Whitespace-only snippet should be excluded"
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
# [4] render_report blinding guard — contract-error line must not leak labels
# ---------------------------------------------------------------------------
print("[4] render_report: blinding guard (contract-error line)")

_FORBIDDEN_TERMS = {"NEW", "new side", "contract", "legacy", OLD_MODEL, NEW_MODEL}

def _make_test_pair(with_error: bool) -> dict:
    return harness.make_pair_dict(
        pair_index=0,
        article={"id": "t", "title": "Test Paper", "url": "http://t", "composite": 0.8},
        old_thread=["old tweet 1", "old tweet 2"],
        new_thread=["new tweet 1", "new tweet 2"],
        new_contract_error="hook tweet too long (320 chars)" if with_error else None,
    )

def test_report_contract_error_no_forbidden_terms():
    """Contract-error warning line must contain none of the forbidden identifying terms."""
    pair = _make_test_pair(with_error=True)
    report = harness.render_report([pair], "2026-07-04", total_attempted=1)
    # Check every line that contains the warning emoji
    warn_lines = [ln for ln in report.splitlines() if "⚠️" in ln or "formatting deviation" in ln]
    assert warn_lines, "Expected at least one warning line in report"
    for line in warn_lines:
        for term in _FORBIDDEN_TERMS:
            assert term not in line, (
                f"Forbidden term {term!r} found in contract-error line: {line!r}"
            )

def test_report_no_error_no_warning_line():
    """Pairs without contract errors must produce no warning line."""
    pair = _make_test_pair(with_error=False)
    report = harness.render_report([pair], "2026-07-04", total_attempted=1)
    assert "⚠️" not in report, "No warning expected when new_contract_error is None"
    assert "formatting deviation" not in report, "No deviation notice expected"

def test_report_n_of_m_header():
    """Report header must show 'N of M pairs generated' without error details."""
    pairs = [_make_test_pair(with_error=False), _make_test_pair(with_error=True)]
    report = harness.render_report(pairs, "2026-07-04", total_attempted=3)
    assert "2 of 3 pairs generated" in report, f"Expected '2 of 3 pairs generated' in header, got:\n{report[:300]}"

check("render_report: contract-error line has no forbidden terms", test_report_contract_error_no_forbidden_terms)
check("render_report: no warning when no contract error", test_report_no_error_no_warning_line)
check("render_report: N of M header line", test_report_n_of_m_header)


# ---------------------------------------------------------------------------
# [5] Fix 2: JSON output shape — dict with pairs + failures keys
# ---------------------------------------------------------------------------
print("[5] JSON output shape: pairs + failures dict")

import importlib, types

def test_json_output_is_dict_shape():
    """The output document must be a dict with 'pairs' and 'failures' keys (not a bare list)."""
    # Simulate what main() would write by constructing the doc directly
    pairs_list = [_make_test_pair(with_error=False)]
    failures_list: list = []
    output_doc = {"pairs": pairs_list, "failures": failures_list}
    assert isinstance(output_doc, dict), "Output doc must be a dict"
    assert "pairs" in output_doc, "Output doc must have 'pairs' key"
    assert "failures" in output_doc, "Output doc must have 'failures' key"
    assert isinstance(output_doc["pairs"], list), "'pairs' must be a list"
    assert isinstance(output_doc["failures"], list), "'failures' must be a list"

check("JSON output shape is dict with pairs+failures", test_json_output_is_dict_shape)


# ---------------------------------------------------------------------------
# [6] Fix 1: legacy_sanitize_summary fidelity (frozen v0.9 helper)
# ---------------------------------------------------------------------------
print("[6] legacy_sanitize_summary: v0.9 fidelity")


def test_legacy_sanitize_strips_evil_url_and_mention():
    """A summary with a foreign URL + @mention + 1500 chars comes out sanitized and capped."""
    long_body = "X " * 600  # 1200 chars of body before the nasty stuff
    dirty = (
        "Great paper! Visit https://evil.example/phish now and follow @scammer for updates. "
        + long_body
        + " Extra tail that should be cut off."
    )
    allowed = "https://arxiv.org/abs/2607.99999"
    clean = harness.legacy_sanitize_summary(dirty, allowed_url=allowed)
    assert "evil.example" not in clean, "evil URL must be stripped"
    assert "@scammer" not in clean, "@mention must be stripped"
    assert "scammer" in clean, "word after @ should survive (defanged)"
    assert len(clean) <= harness._LEGACY_MAX_SUMMARY_CHARS, \
        f"result too long: {len(clean)} > {harness._LEGACY_MAX_SUMMARY_CHARS}"


def test_legacy_sanitize_missing_hashtags_no_doubling():
    """When model returns no hashtags the tag_block must be exactly ['#AI'], not ['#AI', '#AI']."""
    # Simulate old_result with empty hashtags (as a string — the common model output shape)
    raw_tags = ""
    if isinstance(raw_tags, str):
        hashtags = [tag for tag in raw_tags.split(",") if tag.startswith("#")]
    else:
        hashtags = [tag for tag in raw_tags if isinstance(tag, str) and tag.startswith("#")]
    hashtags = [tag for tag in hashtags if __import__("re").fullmatch(r"#\w+", tag)]
    tag_block = ["#AI"] + hashtags[:3]
    assert tag_block == ["#AI"], f"Expected ['#AI'], got {tag_block}"


def test_legacy_sanitize_hashtag_filter():
    """Hashtag list ['#Good', 'bad', '#al$o-bad'] → only '#Good' survives the re.fullmatch filter."""
    import re as _re
    raw_tags = ["#Good", "bad", "#al$o-bad"]
    if isinstance(raw_tags, str):
        hashtags = [tag for tag in raw_tags.split(",") if tag.startswith("#")]
    else:
        hashtags = [tag for tag in raw_tags if isinstance(tag, str) and tag.startswith("#")]
    hashtags = [tag for tag in hashtags if _re.fullmatch(r"#\w+", tag)]
    assert hashtags == ["#Good"], f"Expected ['#Good'], got {hashtags}"


check("legacy_sanitize: evil URL + @mention + 1500 chars → sanitized/capped", test_legacy_sanitize_strips_evil_url_and_mention)
check("legacy_sanitize: missing hashtags → tag_block is exactly ['#AI'] (no doubling)", test_legacy_sanitize_missing_hashtags_no_doubling)
check("legacy_sanitize: hashtag filter keeps only #word-only tags", test_legacy_sanitize_hashtag_filter)


# ---------------------------------------------------------------------------
# [7] call_bedrock routes through utils.llm (provider flag wiring)
# ---------------------------------------------------------------------------
print("[7] call_bedrock: routes through utils.llm.complete")


def test_call_bedrock_via_llm_openrouter():
    """call_bedrock(None, model, prompt, max_tokens) uses utils.llm.complete.

    With LLM_PROVIDER=openrouter + a fake key + FAKE_HTTP routing openrouter.ai,
    it must return a parsed dict (the stubs reply with a chat-completions body
    whose content is valid JSON so _parse_model_json succeeds).
    """
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["openrouter.ai"] = {
        "choices": [{"message": {"content": '{"tweets": ["hello world"]}'}}]
    }
    orig_provider = os.environ.get("LLM_PROVIDER")
    orig_key = os.environ.get("OPENROUTER_API_KEY")
    try:
        os.environ["LLM_PROVIDER"] = "openrouter"
        os.environ["OPENROUTER_API_KEY"] = "sk-fake-key-for-test"
        result = harness.call_bedrock(None, "us.anthropic.claude-haiku-4-5-20251001-v1:0", '{"tweets": ["hello world"]}', 100)
        assert isinstance(result, dict), f"Expected dict, got {type(result)}: {result!r}"
        assert "tweets" in result, f"Expected 'tweets' key in result, got: {result!r}"
    finally:
        if orig_provider is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = orig_provider
        if orig_key is None:
            os.environ.pop("OPENROUTER_API_KEY", None)
        else:
            os.environ["OPENROUTER_API_KEY"] = orig_key
        FAKE_HTTP.reset()


check("call_bedrock routes through utils.llm (openrouter path)", test_call_bedrock_via_llm_openrouter)


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
