# tests/test_fixes.py — regression tests for the "same article posted every run" fix.
# Runs with plain python3, no dependencies: boto3/tweepy/requests/dotenv are stubbed.
#
#   python3 tests/test_fixes.py

import importlib.util
import json
import os
import sys
import time
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LAYER = REPO / "lambda" / "layers" / "common" / "python"

PASSED = []
FAILED = []


def check(name, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"  ✅ {name}")
    except Exception as e:
        FAILED.append((name, e))
        print(f"  ❌ {name}: {type(e).__name__}: {e}")


# ---------------------------------------------------------------- stubs

class FakeBody:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data


class NoSuchKey(Exception):
    """Behaves like botocore's ClientError for a missing key."""

    response = {"Error": {"Code": "NoSuchKey"}}


class FakeS3:
    """Dict-backed stand-in for the S3 client surface these lambdas use."""

    class exceptions:
        NoSuchKey = NoSuchKey

    def __init__(self):
        self.store = {}       # key -> bytes
        self.listing = []     # objects returned by list pagination

    def get_object(self, Bucket, Key):
        if Key not in self.store:
            raise NoSuchKey(Key)
        return {"Body": FakeBody(self.store[Key])}

    def put_object(self, Bucket, Key, Body):
        self.store[Key] = Body

    def download_file(self, Bucket, Key, Filename):
        if Key not in self.store:
            raise NoSuchKey(Key)
        Path(Filename).write_bytes(self.store[Key])

    def get_paginator(self, op):
        listing = self.listing

        class P:
            def paginate(self, **kw):
                return [{"Contents": listing}]

        return P()


FAKE_S3 = FakeS3()


class FakeBedrock:
    """Simulates the post-model-change failure: every invoke is AccessDenied."""

    mode = "denied"  # "ok" | "fenced"

    def invoke_model(self, **kw):
        if self.mode == "denied":
            raise Exception(
                "An error occurred (AccessDeniedException) when calling the "
                "InvokeModel operation: You don't have access to the model."
            )
        content = json.dumps({"summary": "A fine summary.", "hashtags": ["#AI"]})
        if self.mode == "fenced":
            # Haiku 4.5 (observed in prod): wraps JSON in a markdown fence
            content = f"```json\n{content}\n```"
        payload = {"content": [{"type": "text", "text": content}]}
        return {"body": FakeBody(json.dumps(payload).encode())}


FAKE_BEDROCK = FakeBedrock()


def install_stubs():
    boto3 = types.ModuleType("boto3")

    def client(service_name=None, **kw):
        if service_name == "bedrock-runtime":
            return FAKE_BEDROCK
        if service_name == "s3":
            return FAKE_S3
        return types.SimpleNamespace()

    boto3.client = client

    class _FakeSecrets:
        def get_secret_value(self, SecretId=None):
            creds = {k: "x" for k in (
                "TWITTER_BEARER_TOKEN", "TWITTER_API_KEY", "TWITTER_API_SECRET",
                "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET")}
            return {"SecretString": json.dumps(creds)}

    class _FakeSession:
        def client(self, service_name=None, **kw):
            if service_name == "secretsmanager":
                return _FakeSecrets()
            return client(service_name, **kw)

    session_mod = types.ModuleType("boto3.session")
    session_mod.Session = _FakeSession
    boto3.session = session_mod
    sys.modules["boto3"] = boto3
    sys.modules["boto3.session"] = session_mod

    botocore = types.ModuleType("botocore")
    config_mod = types.ModuleType("botocore.config")
    config_mod.Config = lambda **kw: None
    exceptions_mod = types.ModuleType("botocore.exceptions")
    exceptions_mod.ClientError = NoSuchKey
    botocore.config = config_mod
    botocore.exceptions = exceptions_mod
    sys.modules["botocore"] = botocore
    sys.modules["botocore.config"] = config_mod
    sys.modules["botocore.exceptions"] = exceptions_mod

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv

    requests = types.ModuleType("requests")

    class _Resp:
        def raise_for_status(self):
            pass

    requests.post = lambda *a, **k: _Resp()
    requests.exceptions = types.SimpleNamespace(RequestException=Exception)
    sys.modules["requests"] = requests

    tweepy = types.ModuleType("tweepy")
    tweepy.__path__ = []  # mark as package so `tweepy.errors` imports resolve
    tweepy.Client = lambda *a, **k: types.SimpleNamespace()
    tweepy_errors = types.ModuleType("tweepy.errors")
    tweepy_errors.TooManyRequests = type("TooManyRequests", (Exception,), {})
    tweepy_errors.TweepyException = type("TweepyException", (Exception,), {})
    tweepy_errors.Forbidden = type("Forbidden", (Exception,), {})
    tweepy.errors = tweepy_errors
    sys.modules["tweepy"] = tweepy
    sys.modules["tweepy.errors"] = tweepy_errors


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- setup

install_stubs()
sys.path.insert(0, str(LAYER))          # provides the deployed `utils` package
sys.path.insert(0, str(REPO / "lambda" / "poster"))
sys.path.insert(0, str(REPO / "lambda" / "pipeline"))

os.environ.setdefault("S3_OUTPUT_BUCKET", "test-bucket")
os.environ.setdefault("SUMMARY_OUTPUT_PREFIX", "out/summarizer/")
os.environ.setdefault("MEMORY_OUTPUT_PREFIX", "out/memory/")
os.environ.setdefault("POSTED_LEDGER_FILE", "posted_library.json")
os.environ.setdefault("MAX_SUMMARY_AGE_HOURS", "6")
for k in ("TWITTER_BEARER_TOKEN", "TWITTER_API_KEY", "TWITTER_API_SECRET",
          "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"):
    os.environ.setdefault(k, "test-cred")

import utils.summarizer as summarizer  # noqa: E402  (from the layer)
import utils.memcon as memcon  # noqa: E402
import utils.post_to_twitter as ptt  # noqa: E402

poster = load_module("poster_lambda", REPO / "lambda" / "poster" / "poster_lambda.py")
pipeline = load_module("pipeline_lambda", REPO / "lambda" / "pipeline" / "pipeline_lambda.py")


# ---------------------------------------------------------------- tests

print("\n[1] summarizer: gives up after MAX_ATTEMPTS_PER_ARTICLE instead of looping forever")


def test_summarizer_skips_failed_articles():
    articles = [
        {"title": "Paper A", "authors": ["X"], "snippet": "abc", "url": "https://arxiv.org/a"},
        {"title": "Paper B", "authors": ["Y"], "snippet": "def", "url": "https://arxiv.org/b"},
    ]
    inp = "/tmp/test_scraper_input.json"
    out = "/tmp/test_summarized_output.json"
    Path(inp).write_text(json.dumps(articles))
    summarizer.INPUT_FILE = inp
    summarizer.OUTPUT_FILE = out

    FAKE_BEDROCK.mode = "denied"
    start = time.time()
    result = summarizer.summarize_articles(max_runtime=300)
    elapsed = time.time() - start

    assert result == [], f"expected no summaries on AccessDenied, got {result}"
    assert elapsed < 30, f"took {elapsed:.1f}s — old retry-forever behavior would burn the whole budget"


def test_summarizer_success_path_still_works():
    FAKE_BEDROCK.mode = "ok"
    result = summarizer.summarize_articles(max_runtime=300)
    assert len(result) == 2, f"expected 2 summaries, got {len(result)}"
    assert result[0]["summary"] == "A fine summary."
    FAKE_BEDROCK.mode = "denied"


def test_summarizer_handles_markdown_fenced_json():
    FAKE_BEDROCK.mode = "fenced"
    result = summarizer.summarize_articles(max_runtime=300)
    assert len(result) == 2, f"expected 2 summaries from fenced output, got {len(result)}"
    assert result[0]["summary"] == "A fine summary."
    FAKE_BEDROCK.mode = "denied"


check("skips failing articles after 2 attempts", test_summarizer_skips_failed_articles)
check("still summarizes when Bedrock works", test_summarizer_success_path_still_works)
check("parses markdown-fenced JSON from newer models", test_summarizer_handles_markdown_fenced_json)


print("\n[2] pipeline: never invokes the poster after a summarizer failure")


def run_pipeline_with(summarizer_result):
    calls = []

    def fake_invoke(function_name, payload=None, wait=True):
        calls.append((function_name, payload))
        if function_name == "SCRAPER":
            return {"statusCode": 200, "body": json.dumps({"scraped_count": 1, "new_count": 1})}
        if function_name == "SUMMARIZER":
            return summarizer_result
        return {"statusCode": 200, "body": "{}"}

    pipeline.invoke_lambda = fake_invoke
    pipeline.SCRAPER_FUNCTION_NAME = "SCRAPER"
    pipeline.SUMMARIZER_FUNCTION_NAME = "SUMMARIZER"
    pipeline.POSTER_FUNCTION_NAME = "POSTER"
    pipeline.time.sleep = lambda *_: None
    resp = pipeline.handler({"scrape_limit": 1, "chunk_size": 1}, None)
    poster_called = any(name == "POSTER" for name, _ in calls)
    return resp, poster_called, calls


def test_pipeline_aborts_on_summarizer_500():
    resp, poster_called, _ = run_pipeline_with(
        {"statusCode": 500, "body": json.dumps({"error": "AccessDenied"})}
    )
    assert resp["statusCode"] == 500, resp
    assert not poster_called, "poster must NOT run after summarizer failure"


def test_pipeline_aborts_on_empty_summaries():
    resp, poster_called, _ = run_pipeline_with(
        {"statusCode": 200, "body": json.dumps(
            {"article_count": 0, "has_summaries": False, "final_key": "x.json"})}
    )
    assert resp["statusCode"] == 500, resp
    assert not poster_called, "poster must NOT run when there are no summaries"


def test_pipeline_passes_final_key_to_poster():
    resp, poster_called, calls = run_pipeline_with(
        {"statusCode": 200, "body": json.dumps(
            {"article_count": 1, "has_summaries": True,
             "article_titles": ["T"], "hashtags": [], "chunk_size": 1,
             "final_key": "out/summarizer/final_summarized_RUN.json"})}
    )
    assert resp["statusCode"] == 200, resp
    assert poster_called, "poster should run on success"
    poster_payload = next(p for name, p in calls if name == "POSTER")
    assert poster_payload.get("summary_key") == "out/summarizer/final_summarized_RUN.json"


def test_pipeline_fails_when_poster_fails():
    calls = []

    def fake_invoke(function_name, payload=None, wait=True):
        calls.append(function_name)
        if function_name == "SCRAPER":
            return {"statusCode": 200, "body": json.dumps({"scraped_count": 1, "new_count": 1})}
        if function_name == "SUMMARIZER":
            return {"statusCode": 200, "body": json.dumps(
                {"article_count": 1, "has_summaries": True, "article_titles": ["T"],
                 "hashtags": [], "chunk_size": 1, "final_key": "x.json"})}
        return {"statusCode": 500, "body": json.dumps({"error": "twitter down"})}

    pipeline.invoke_lambda = fake_invoke
    pipeline.time.sleep = lambda *_: None
    resp = pipeline.handler({"scrape_limit": 1, "chunk_size": 1}, None)
    assert resp["statusCode"] == 500, "pipeline must not report success when the poster failed"
    assert "Poster failed" in json.loads(resp["body"])["error"]


check("aborts on summarizer 500", test_pipeline_aborts_on_summarizer_500)
check("aborts on empty summaries", test_pipeline_aborts_on_empty_summaries)
check("passes final_key to poster on success", test_pipeline_passes_final_key_to_poster)
check("fails loudly when the poster fails", test_pipeline_fails_when_poster_fails)


print("\n[3] poster: ledger dedup + stale-summary guard")

SUMMARY_KEY = "out/summarizer/final_summarized_RUN.json"
ARTICLES = [
    {"title": "Old", "url": "https://arxiv.org/old", "summary": "s", "hashtags": []},
    {"title": "New", "url": "https://arxiv.org/new", "summary": "s", "hashtags": []},
]


def test_poster_filters_already_posted():
    FAKE_S3.store.clear()
    FAKE_S3.store[SUMMARY_KEY] = json.dumps(ARTICLES).encode()
    FAKE_S3.store[poster.POSTED_LEDGER_KEY] = json.dumps(
        {"https://arxiv.org/old": {"posted_at": "2026-01-01"}}).encode()

    resp = poster.handler({"summary_key": SUMMARY_KEY, "dry_run": True}, None)
    assert resp["statusCode"] == 200, resp
    left = json.loads(Path("/tmp/summarized_output.json").read_text())
    assert [a["url"] for a in left] == ["https://arxiv.org/new"], left


def test_poster_noops_when_everything_posted():
    FAKE_S3.store[poster.POSTED_LEDGER_KEY] = json.dumps(
        {a["url"]: {} for a in ARTICLES}).encode()
    resp = poster.handler({"summary_key": SUMMARY_KEY, "dry_run": True}, None)
    assert resp["statusCode"] == 200, resp
    assert "Nothing new to post" in json.loads(resp["body"])["message"]


def test_poster_rejects_stale_latest():
    FAKE_S3.store.pop(poster.POSTED_LEDGER_KEY, None)
    FAKE_S3.listing = [{
        "Key": SUMMARY_KEY,
        "LastModified": datetime.now(timezone.utc) - timedelta(days=200),
    }]
    resp = poster.handler({"dry_run": True}, None)  # no summary_key -> latest + guard
    assert resp["statusCode"] == 500, resp
    assert "stale" in json.loads(resp["body"])["error"].lower()


def test_poster_accepts_fresh_latest():
    FAKE_S3.store[SUMMARY_KEY] = json.dumps(ARTICLES).encode()
    FAKE_S3.listing = [{
        "Key": SUMMARY_KEY,
        "LastModified": datetime.now(timezone.utc) - timedelta(minutes=5),
    }]
    resp = poster.handler({"dry_run": True}, None)
    assert resp["statusCode"] == 200, resp


check("filters already-posted articles via ledger", test_poster_filters_already_posted)
check("no-ops when every article was already posted", test_poster_noops_when_everything_posted)
check("rejects a months-old 'latest' summary", test_poster_rejects_stale_latest)
check("accepts a fresh 'latest' summary", test_poster_accepts_fresh_latest)


print("\n[4] scraper dedup: read-only filter against the posted ledger")


def test_scraper_filter_uses_posted_ledger():
    FAKE_S3.store.clear()
    FAKE_S3.store[memcon.POSTED_LEDGER_KEY] = json.dumps(
        {"https://arxiv.org/old": {"posted_at": "2026-01-01"}}).encode()
    scraped = [{"url": "https://arxiv.org/old"}, {"url": "https://arxiv.org/new"}]
    fresh = memcon.filter_new_articles(scraped)
    assert [a["url"] for a in fresh] == ["https://arxiv.org/new"], fresh
    # read-only: scrape-time filtering must never write state (that design
    # lost every article whose downstream stage failed)
    assert set(FAKE_S3.store) == {memcon.POSTED_LEDGER_KEY}, FAKE_S3.store.keys()


def test_scraper_filter_with_no_ledger_yet():
    FAKE_S3.store.clear()
    fresh = memcon.filter_new_articles([{"url": "https://arxiv.org/x"}])
    assert len(fresh) == 1
    assert not FAKE_S3.store, "no writes expected"


check("filters against posted ledger, read-only", test_scraper_filter_uses_posted_ledger)
check("treats everything as new when ledger absent", test_scraper_filter_with_no_ledger_yet)


print("\n[5] poster: ledger persisted per-article (crash-safe)")


def test_ledger_saved_before_crash_on_second_article():
    FAKE_S3.store.clear()
    FAKE_S3.store[SUMMARY_KEY] = json.dumps(ARTICLES).encode()

    calls = {"n": 0}

    def fake_post_thread(article, variant="summary", dry_run=False, confirm_post=False):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated crash mid-run")
        return {"article_title": article["title"], "url": article["url"],
                "variant": variant, "tweet_ids": ["1"], "thread_url": "https://t/1"}

    orig = ptt.post_thread
    ptt.post_thread = fake_post_thread
    try:
        resp = poster.handler({"summary_key": SUMMARY_KEY, "dry_run": False, "post_limit": 2}, None)
    finally:
        ptt.post_thread = orig

    assert resp["statusCode"] == 500, resp
    ledger = json.loads(FAKE_S3.store[poster.POSTED_LEDGER_KEY])
    assert ARTICLES[0]["url"] in ledger, "article 1 tweeted before the crash must be in the ledger"
    assert ARTICLES[1]["url"] not in ledger


check("ledger records each post before the next one", test_ledger_saved_before_crash_on_second_article)


print("\n[6] tweet-injection guard")


def test_sanitize_summary_strips_foreign_urls_and_mentions():
    dirty = ("Great paper! Visit https://evil.example/phish now and follow @scammer. "
             "Details: https://arxiv.org/abs/1234.5678")
    clean = ptt.sanitize_summary(dirty, allowed_url="https://arxiv.org/abs/1234.5678")
    assert "evil.example" not in clean
    assert "@scammer" not in clean and "scammer" in clean  # defanged, text kept
    assert "https://arxiv.org/abs/1234.5678" in clean


def test_sanitize_summary_caps_length():
    clean = ptt.sanitize_summary("x " * 5000)
    assert len(clean) <= ptt.MAX_SUMMARY_CHARS


check("strips foreign URLs and @mentions", test_sanitize_summary_strips_foreign_urls_and_mentions)
check("caps runaway summary length", test_sanitize_summary_caps_length)


print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
