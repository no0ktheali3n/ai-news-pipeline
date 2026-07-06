# tests/stubs.py — shared fakes for the no-dependency test harness.
# import stubs must run BEFORE any `import utils.*` in a test file.
import json
import sys
import types
from pathlib import Path


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

    def put_object(self, Bucket, Key, Body, **kwargs):
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
    scoring_response = None  # None → auto-valid; str → returned verbatim

    def _scoring_reply(self, body):
        req = json.loads(body)
        prompt = req["messages"][0]["content"]
        if self.scoring_response is not None:
            text = self.scoring_response
        else:
            import re as _re
            papers = json.loads(_re.search(r"<papers>\n(.*)\n</papers>", prompt, _re.S).group(1))
            text = json.dumps([{"id": p["id"], "builder_relevance": 8,
                                "novelty": 6, "hook_potential": 7} for p in papers])
        payload = {"content": [{"type": "text", "text": text}]}
        return {"body": FakeBody(json.dumps(payload).encode())}

    def invoke_model(self, **kw):
        content = json.loads(kw["body"])["messages"][0]["content"]
        if "score every paper" in content.lower():
            if self.mode == "denied":
                raise Exception("AccessDeniedException: no model access")
            return self._scoring_reply(kw["body"])
        # --- existing summarizer routing, unchanged from test_fixes.py ---
        if self.mode == "denied":
            raise Exception(
                "An error occurred (AccessDeniedException) when calling the "
                "InvokeModel operation: You don't have access to the model."
            )
        summary = json.dumps({"summary": "A fine summary.", "hashtags": ["#AI"]})
        if self.mode == "fenced":
            summary = f"```json\n{summary}\n```"
        payload = {"content": [{"type": "text", "text": summary}]}
        return {"body": FakeBody(json.dumps(payload).encode())}


FAKE_BEDROCK = FakeBedrock()


class FakeSNS:
    def __init__(self):
        self.published = []  # list of dicts: TopicArn/Subject/Message

    def publish(self, **kw):
        self.published.append(kw)
        return {"MessageId": "fake"}


FAKE_SNS = FakeSNS()


class _HttpResp:
    def __init__(self, payload=None, status=200):
        self._payload = {} if payload is None else payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeHttp:
    """Routes fake GET/POST responses by URL substring; records every call.
    Unrouted URLs get an empty 200 JSON (keeps webhook posts harmless)."""

    def __init__(self):
        self.routes = {}   # url substring -> JSON payload | Exception
        self.calls = []    # (method, url)

    def _resolve(self, method, url):
        self.calls.append((method, url))
        for frag, payload in self.routes.items():
            if frag in url:
                if isinstance(payload, Exception):
                    raise payload
                return _HttpResp(payload)
        return _HttpResp({})

    def get(self, url, params=None, timeout=None, **kwargs):
        return self._resolve("GET", url)

    def post(self, url, params=None, json=None, timeout=None, **kwargs):
        return self._resolve("POST", url)

    def reset(self):
        self.routes, self.calls = {}, []


FAKE_HTTP = FakeHttp()


def install_stubs():
    boto3 = types.ModuleType("boto3")

    def client(service_name=None, **kw):
        if service_name == "bedrock-runtime":
            return FAKE_BEDROCK
        if service_name == "s3":
            return FAKE_S3
        if service_name == "sns":
            return FAKE_SNS
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
    requests.get = FAKE_HTTP.get
    requests.post = FAKE_HTTP.post
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
