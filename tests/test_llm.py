# tests/test_llm.py — provider-agnostic llm.complete unit tests.
#
#   uv run python tests/test_llm.py
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from stubs import install_stubs, FAKE_BEDROCK, FAKE_HTTP  # noqa: E402

install_stubs()

LAYER = REPO / "lambda" / "layers" / "common" / "python"
sys.path.insert(0, str(LAYER))

PASSED, FAILED = [], []


def check(name, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"  ✅ {name}")
    except Exception as e:
        FAILED.append((name, e))
        print(f"  ❌ {name}: {e}")


print("[1] llm: provider-agnostic completion layer")

from utils.llm import complete, LLMError, to_openrouter_model  # noqa: E402

# ── Test 1: bedrock-ok ─────────────────────────────────────────────────────

def test_bedrock_ok():
    """LLM_PROVIDER unset → complete() routes through Bedrock, returns text."""
    FAKE_BEDROCK.mode = "ok"
    try:
        result = complete(
            "Summarise this paper briefly.",
            model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            max_tokens=256,
        )
        assert isinstance(result, str) and len(result) > 0, (
            f"Expected non-empty str, got {result!r}"
        )
    finally:
        FAKE_BEDROCK.mode = "ok"  # reset to safe default


check("bedrock-ok: returns non-empty string", test_bedrock_ok)

# ── Test 2: openrouter-ok ──────────────────────────────────────────────────

def test_openrouter_ok():
    """LLM_PROVIDER='openrouter' + key set → returns the routed content exactly."""
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["openrouter.ai"] = {
        "choices": [{"message": {"content": "OpenRouter reply text"}}]
    }
    os.environ["LLM_PROVIDER"] = "openrouter"
    os.environ["OPENROUTER_API_KEY"] = "or-testkey"
    try:
        result = complete(
            "Hello",
            model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            max_tokens=64,
        )
        assert result == "OpenRouter reply text", f"Unexpected: {result!r}"
        assert any("openrouter.ai" in url for _, url in FAKE_HTTP.calls), (
            "Expected HTTP call to openrouter.ai"
        )
    finally:
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("OPENROUTER_API_KEY", None)
        FAKE_HTTP.reset()


check("openrouter-ok: routes and returns content exactly", test_openrouter_ok)

# ── Test 3: fallback engages ───────────────────────────────────────────────

def test_fallback_engages():
    """bedrock denied + fallback=openrouter + key set → uses openrouter."""
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["openrouter.ai"] = {
        "choices": [{"message": {"content": "Fallback content"}}]
    }
    FAKE_BEDROCK.mode = "denied"
    os.environ["LLM_PROVIDER"] = "bedrock"
    os.environ["LLM_FALLBACK_PROVIDER"] = "openrouter"
    os.environ["OPENROUTER_API_KEY"] = "or-testkey"
    try:
        result = complete(
            "Hello fallback",
            model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            max_tokens=64,
        )
        assert result == "Fallback content", f"Unexpected: {result!r}"
    finally:
        FAKE_BEDROCK.mode = "ok"
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("LLM_FALLBACK_PROVIDER", None)
        os.environ.pop("OPENROUTER_API_KEY", None)
        FAKE_HTTP.reset()


check("fallback-engages: openrouter used when bedrock denied", test_fallback_engages)

# ── Test 4: no-key degrade ─────────────────────────────────────────────────

def test_no_key_degrade():
    """Fallback configured but key empty → LLMError raised, openrouter never called."""
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["openrouter.ai"] = {
        "choices": [{"message": {"content": "Should never arrive"}}]
    }
    FAKE_BEDROCK.mode = "denied"
    os.environ["LLM_PROVIDER"] = "bedrock"
    os.environ["LLM_FALLBACK_PROVIDER"] = "openrouter"
    os.environ.pop("OPENROUTER_API_KEY", None)  # ensure absent
    os.environ["OPENROUTER_API_KEY"] = ""
    try:
        try:
            complete(
                "Hello no-key",
                model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                max_tokens=64,
            )
            raise AssertionError("Expected LLMError but no exception raised")
        except LLMError as exc:
            assert exc.provider == "bedrock", (
                f"Expected provider='bedrock', got {exc.provider!r}"
            )
        # openrouter must not have been contacted
        or_calls = [url for _, url in FAKE_HTTP.calls if "openrouter.ai" in url]
        assert or_calls == [], f"openrouter was called unexpectedly: {or_calls}"
    finally:
        FAKE_BEDROCK.mode = "ok"
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("LLM_FALLBACK_PROVIDER", None)
        os.environ.pop("OPENROUTER_API_KEY", None)
        FAKE_HTTP.reset()


check("no-key-degrade: LLMError(bedrock), openrouter never called", test_no_key_degrade)

# ── Test 5: both-fail ──────────────────────────────────────────────────────

def test_both_fail():
    """bedrock denied + openrouter routed to Exception → LLMError(provider='openrouter')."""
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["openrouter.ai"] = Exception("openrouter 503")
    FAKE_BEDROCK.mode = "denied"
    os.environ["LLM_PROVIDER"] = "bedrock"
    os.environ["LLM_FALLBACK_PROVIDER"] = "openrouter"
    os.environ["OPENROUTER_API_KEY"] = "or-testkey"
    try:
        try:
            complete(
                "Hello both-fail",
                model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                max_tokens=64,
            )
            raise AssertionError("Expected LLMError but no exception raised")
        except LLMError as exc:
            assert exc.provider == "openrouter", (
                f"Expected provider='openrouter', got {exc.provider!r}"
            )
    finally:
        FAKE_BEDROCK.mode = "ok"
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("LLM_FALLBACK_PROVIDER", None)
        os.environ.pop("OPENROUTER_API_KEY", None)
        FAKE_HTTP.reset()


check("both-fail: LLMError(provider='openrouter')", test_both_fail)

# ── Test 6: model id mapping ───────────────────────────────────────────────

def test_mapping():
    """Table hits, regex derivation, passthrough, env override, garbage."""
    # explicit table — us. prefix
    assert to_openrouter_model("us.anthropic.claude-haiku-4-5-20251001-v1:0") == "anthropic/claude-haiku-4.5"
    assert to_openrouter_model("us.anthropic.claude-sonnet-4-6-20260101-v1:0") == "anthropic/claude-sonnet-4.6"
    assert to_openrouter_model("us.anthropic.claude-sonnet-4-5-20251001-v1:0") == "anthropic/claude-sonnet-4.5"
    # explicit table — global. prefix
    assert to_openrouter_model("global.anthropic.claude-haiku-4-5-20251001-v1:0") == "anthropic/claude-haiku-4.5"
    assert to_openrouter_model("global.anthropic.claude-sonnet-4-6-20260101-v1:0") == "anthropic/claude-sonnet-4.6"
    # regex derivation — synthetic id not in table
    assert to_openrouter_model("us.anthropic.claude-opus-4-8") == "anthropic/claude-opus-4.8"
    # passthrough: already a slug
    assert to_openrouter_model("anthropic/claude-haiku-4.5") == "anthropic/claude-haiku-4.5"
    # LLM_MODEL_MAP override wins
    os.environ["LLM_MODEL_MAP"] = json.dumps(
        {"us.anthropic.claude-haiku-4-5-20251001-v1:0": "my-provider/my-model"}
    )
    try:
        assert to_openrouter_model("us.anthropic.claude-haiku-4-5-20251001-v1:0") == "my-provider/my-model"
    finally:
        os.environ.pop("LLM_MODEL_MAP", None)
    # garbage id raises
    try:
        to_openrouter_model("garbage-model-id")
        raise AssertionError("Expected LLMError for garbage id")
    except LLMError:
        pass  # expected


check("mapping: table + derivation + passthrough + override + garbage", test_mapping)

# ── Summary ────────────────────────────────────────────────────────────────

print(f"\n{'='*50}")
print(f"  Passed: {len(PASSED)}  Failed: {len(FAILED)}")
if FAILED:
    print("\nFailed tests:")
    for name, exc in FAILED:
        import traceback
        print(f"\n  ✗ {name}")
        traceback.print_exception(type(exc), exc, exc.__traceback__)
    sys.exit(1)
else:
    print("  All tests passed.")
