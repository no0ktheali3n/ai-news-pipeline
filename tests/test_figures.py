# tests/test_figures.py — media/figures feature tests (Task 1: harness only).
#   uv run python tests/test_figures.py
import io
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from stubs import install_stubs  # noqa: E402
import stubs  # noqa: E402
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


FIXTURES = Path(__file__).resolve().parent / "fixtures"

# ---------------------------------------------------------------------------
# [1] Stub harness extensions
# ---------------------------------------------------------------------------
print("[1] stub harness: _HttpResp bytes/headers + fake tweepy v1.1")


def test_httpresp_carries_bytes_headers_text():
    r = stubs._HttpResp(content=b"\x89PNG12", headers={"Content-Type": "image/png"}, status=200)
    assert r.content == b"\x89PNG12"
    assert r.headers["Content-Type"] == "image/png"
    assert isinstance(r.text, str)
    r2 = stubs._HttpResp(content=b"hello")
    assert r2.text == "hello"


def test_httpresp_back_compat():
    """Existing call sites: _HttpResp() and _HttpResp(payload, status) must still work."""
    r0 = stubs._HttpResp()
    assert r0.status_code == 200
    assert r0.json() == {}
    r1 = stubs._HttpResp({"key": "val"}, 201)
    assert r1.status_code == 201
    assert r1.json() == {"key": "val"}


def test_httpresp_raise_for_status():
    r = stubs._HttpResp(status=404)
    try:
        r.raise_for_status()
        raise AssertionError("expected exception")
    except Exception as e:
        assert "404" in str(e)
    stubs._HttpResp(status=200).raise_for_status()  # must not raise


def test_fake_tweepy_v1_media():
    import tweepy
    tweepy.API.reset()
    api = tweepy.API(tweepy.OAuth1UserHandler("k", "s", "t", "ts"))
    m = api.media_upload(filename="f.png", file=io.BytesIO(b"12345"))
    api.create_media_metadata(m.media_id, alt_text="alt")
    assert m.media_id == "777000"
    assert tweepy.API.uploads == [("f.png", 5)]
    assert tweepy.API.metadata_calls == [("777000", "alt")]
    tweepy.API.fail_upload = True
    try:
        api.media_upload(filename="g.png", file=io.BytesIO(b"1"))
        raise AssertionError("expected upload failure")
    except RuntimeError:
        pass
    finally:
        tweepy.API.fail_upload = False


check("_HttpResp carries bytes/headers/text", test_httpresp_carries_bytes_headers_text)
check("_HttpResp back-compat (no-arg + positional)", test_httpresp_back_compat)
check("_HttpResp raise_for_status", test_httpresp_raise_for_status)
check("fake tweepy v1.1 media upload + metadata", test_fake_tweepy_v1_media)

# ---------------------------------------------------------------------------
# [2] Captured fixtures present + sane
# ---------------------------------------------------------------------------
print("\n[2] captured fixtures: presence + magic bytes")


def test_fixtures_present():
    expected = [
        "2607.02116.html",
        "2607.01641.html",
        "2607.01600.html",
        "2607.02116_fig1.jpg.head",
        "2607.01641_fig1.png.head",
    ]
    for name in expected:
        p = FIXTURES / name
        assert p.exists(), f"missing fixture: {name}"
        assert p.stat().st_size > 0, f"empty fixture: {name}"


def test_png_magic():
    data = (FIXTURES / "2607.01641_fig1.png.head").read_bytes()
    assert data[:4] == b"\x89PNG", f"bad PNG magic: {data[:4]!r}"


def test_jpeg_magic():
    data = (FIXTURES / "2607.02116_fig1.jpg.head").read_bytes()
    assert data[:2] == b"\xff\xd8", f"bad JPEG magic: {data[:2]!r}"


def test_html_sanity():
    html = (FIXTURES / "2607.02116.html").read_text(encoding="utf-8")
    assert "license-tr" in html, "license-tr not found in 2607.02116.html"
    assert "CC-BY-4.0" in html, "CC-BY-4.0 not found in 2607.02116.html"


check("all fixture files present + non-empty", test_fixtures_present)
check("PNG magic bytes", test_png_magic)
check("JPEG magic bytes", test_jpeg_magic)
check("HTML sanity (license-tr, CC-BY-4.0)", test_html_sanity)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
