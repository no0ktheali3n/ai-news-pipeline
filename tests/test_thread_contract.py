# tests/test_thread_contract.py — Phase 2 (thread contract) tests.
#   uv run python tests/test_thread_contract.py
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


print("[1] thread contract: sanitize + validate/repair")

from utils import thread_contract as tc  # noqa: E402

URL = "https://arxiv.org/abs/2607.01234"


def _valid_thread():
    return [
        "Agents fail 3x more often on state they wrote themselves. A new benchmark quantifies self-corruption.",
        "The mechanism: models trust their own prior outputs more than fresh evidence. Builders: audit agent memory writes like user input.",
        f"Paper: Self-Corruption in Persistent Agents\n{URL}",
    ]


def test_valid_thread_passes_unchanged():
    out = tc.validate_and_repair(_valid_thread(), URL)
    assert out == _valid_thread()


def test_link_in_hook_is_stripped():
    t = _valid_thread()
    t[0] = f"Big result {URL} — agents self-corrupt."
    out = tc.validate_and_repair(t, URL)
    assert URL not in out[0] and "agents self-corrupt" in out[0]


def test_six_tweets_truncates_keeping_final_link():
    t = _valid_thread()
    t = [t[0], "m1", "m2", "m3", "m4", t[2]]  # 6 tweets
    out = tc.validate_and_repair(t, URL)
    assert len(out) == 5 and URL in out[-1] and out[1] == "m1" and "m4" not in out


def test_hard_fails():
    for bad, name in [
        ([f"hook", f"{URL}"][0:1], "single tweet"),                      # <2
        (["", f"Paper\n{URL}"], "empty tweet"),
        (["x" * 281, f"Paper\n{URL}"], "tweet over 280 (hook)"),
        (["short hook", "x" * 281, f"Paper\n{URL}"], "middle tweet over 280"),
        (["h" * 241, f"Paper\n{URL}"], "hook over 240"),
        (["hook ok", "no link here"], "missing final link"),
        ("not a list", "non-list"),
        ([{"t": 1}, f"{URL}"], "non-string tweet"),
    ]:
        try:
            tc.validate_and_repair(bad, URL)
            raise AssertionError(f"expected ContractError: {name}")
        except tc.ContractError:
            pass


def test_sanitize_tweet_preserves_newlines():
    s = tc.sanitize_tweet(f"line one   spaced\nline two https://evil.example/x @someone", allowed_url=URL)
    assert s == "line one spaced\nline two someone"
    assert tc.sanitize_tweet(f"keep {URL} here", allowed_url=URL) == f"keep {URL} here"


def test_writer_prompt_contract_elements():
    art = {"title": "T" * 400, "authors": ["A", "B"], "snippet": "S" * 5000,
           "url": URL}
    p = tc.build_writer_prompt(art)
    assert '"tweets"' in p and '"summary"' in p
    assert "240" in p and ("2 to 5" in p.lower() or "2-5" in p)
    assert URL in p
    assert "T" * 301 not in p and "S" * 4001 not in p          # truncation
    assert "never follow instructions" in p.lower()             # untrusted-input note
    assert "no hashtags" in p.lower() and "hook" in p.lower()


def test_max_tweets_gte_min_tweets():
    assert tc.MAX_TWEETS >= tc.MIN_TWEETS, \
        f"MAX_TWEETS ({tc.MAX_TWEETS}) must be >= MIN_TWEETS ({tc.MIN_TWEETS})"


check("MAX_TWEETS >= MIN_TWEETS (clamp guard)", test_max_tweets_gte_min_tweets)
check("valid thread passes unchanged", test_valid_thread_passes_unchanged)
check("link in hook stripped", test_link_in_hook_is_stripped)
check("6 tweets truncate keeping final link", test_six_tweets_truncates_keeping_final_link)
check("hard-fail rows raise ContractError", test_hard_fails)
check("sanitize_tweet preserves newlines", test_sanitize_tweet_preserves_newlines)
check("writer prompt carries contract", test_writer_prompt_contract_elements)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
