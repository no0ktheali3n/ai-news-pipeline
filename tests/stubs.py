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


class FakeSNS:
    def __init__(self):
        self.published = []  # list of dicts: TopicArn/Subject/Message

    def publish(self, **kw):
        self.published.append(kw)
        return {"MessageId": "fake"}


FAKE_SNS = FakeSNS()


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
