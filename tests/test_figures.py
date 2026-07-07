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

# ---------------------------------------------------------------------------
# [3] figures.py — Task 2
# ---------------------------------------------------------------------------
import pathlib
import sys as _sys

FIX = pathlib.Path(__file__).parent / "fixtures"
HTML_02116 = (FIX / "2607.02116.html").read_text(encoding="utf-8")
HTML_01641 = (FIX / "2607.01641.html").read_text(encoding="utf-8")
HTML_01600 = (FIX / "2607.01600.html").read_text(encoding="utf-8")
JPG_HEAD = (FIX / "2607.02116_fig1.jpg.head").read_bytes()
PNG_HEAD = (FIX / "2607.01641_fig1.png.head").read_bytes()

# Import figures (LAYER already on sys.path from harness setup above)
import utils.figures as figures  # noqa: E402

print("\n[3] figures.py — license / caption / resolver / dims / end-to-end")

# ---------------------------------------------------------------------------
# Helper: context manager that installs a custom requests.get into the fake
# requests module, routing by URL substring to pre-built _HttpResp objects.
# ---------------------------------------------------------------------------
import contextlib

_IMG_BYTES = JPG_HEAD + b"0" * 50_000  # real JPEG header + padding


class _FakeGetRouter:
    """Minimal requests.get replacement for figures tests.
    Routes URLs by substring; falls back to 404 for unregistered paths."""

    def __init__(self, routes):
        # routes: list of (substring, _HttpResp)
        self._routes = routes

    def __call__(self, url, **kwargs):
        for frag, resp in self._routes:
            if frag in url:
                return resp
        return stubs._HttpResp(status=404)


@contextlib.contextmanager
def _patch_requests_get(routes):
    import sys
    req_mod = sys.modules["requests"]
    old = req_mod.get
    req_mod.get = _FakeGetRouter(routes)
    try:
        yield
    finally:
        req_mod.get = old


def monkeypatched_http():
    """Context manager: 02116 → HTML; *.jpg/*.png under that paper → JPEG image.
    Route ordering matters: image-file fragments must come before the page fragment
    so that /figures/*.jpg URLs route to the image resp, not the HTML resp.
    """
    html_resp = stubs._HttpResp(text=HTML_02116, status=200)
    html_resp.url = "https://arxiv.org/html/2607.02116"
    img_resp = stubs._HttpResp(
        content=_IMG_BYTES,
        headers={"Content-Type": "image/jpeg"},
        status=200,
    )
    # 01641 HTML (non-CC)
    html_01641 = stubs._HttpResp(text=HTML_01641, status=200)
    html_01641.url = "https://arxiv.org/html/2607.01641"
    img_01641 = stubs._HttpResp(
        content=PNG_HEAD + b"0" * 50_000,
        headers={"Content-Type": "image/png"},
        status=200,
    )
    routes = [
        # Image file routes first (more specific — contain /figures/ path)
        ("2607.02116v", img_resp),   # matches /html/2607.02116vN/figures/...
        ("2607.01641v", img_01641),  # matches /html/2607.01641vN/figures/...
        # Page HTML routes (exact abs-page fetch: /html/2607.02116 without vN suffix)
        ("arxiv.org/html/2607.02116", html_resp),
        ("arxiv.org/html/2607.01641", html_01641),
    ]
    return _patch_requests_get(routes)


def monkeypatched_http_404():
    """Context manager: all arxiv HTML requests → 404."""
    routes = [
        ("arxiv.org/html/", stubs._HttpResp(status=404)),
    ]
    return _patch_requests_get(routes)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_license_classify_cc_and_noncc_and_decoy():
    from bs4 import BeautifulSoup
    assert "cc by" in figures.classify_license(BeautifulSoup(HTML_02116, "html.parser")).lower()
    lic = figures.classify_license(BeautifulSoup(HTML_01641, "html.parser"))
    assert "perpetual" in lic.lower()                      # non-CC anchor text, parsed
    # decoy: strip the license anchor from 02116; table-cell CC-BY-4.0 must NOT match
    soup = BeautifulSoup(HTML_02116, "html.parser")
    a = soup.select_one("a#license-tr")
    a.decompose()
    assert figures.classify_license(soup) is None


def test_caption_cleaning_strips_mathml():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(HTML_01600, "html.parser")
    figs = [f for f in soup.find_all("figure")
            if f.find("figcaption") and f.find("figcaption").get_text(strip=True).lower().startswith("figure")]
    caps = [figures.clean_caption(f) for f in figs]
    joined = " ".join(caps)
    assert "\\leq" not in joined
    assert "p<0.001p<0.001" not in joined.replace(" ", "")  # no doubled math tokens
    assert all(len(c) <= 400 for c in caps)


def test_resolver_three_branches():
    page = "https://arxiv.org/html/2607.02116"
    assert figures.resolve_src("2607.02116v1/figures/a.jpg", page, "2607.02116v1") == \
        "https://arxiv.org/html/2607.02116v1/figures/a.jpg"          # verified form
    assert figures.resolve_src("x1.png", page, None) == \
        "https://arxiv.org/html/2607.02116/x1.png"                    # defensive (synthetic)
    assert figures.resolve_src("https://arxiv.org/html/2607.02116v1/b.png", page, None) == \
        "https://arxiv.org/html/2607.02116v1/b.png"                   # absolute arxiv
    assert figures.resolve_src("https://evil.example/c.png", page, None) is None  # foreign host
    assert figures.resolve_src("https://evilarxiv.org/c.png", page, None) is None  # look-alike host
    assert figures.resolve_src("https://static.arxiv.org/c.png", page, None) == \
        "https://static.arxiv.org/c.png"                              # true subdomain ok


def test_dims_parsers_on_real_bytes():
    w, h = figures.jpeg_dims(JPG_HEAD)
    assert w > 0 and h > 0                                            # real jpg fixture
    w2, h2 = figures.png_dims(PNG_HEAD)
    assert (w2, h2) == (996, 673)                                     # audited value


def test_image_ok_caps_wire_read_and_rejects_oversize():
    big = figures.IMG_READ_CAP + 500_000
    # (a) over-cap declared Content-Length is rejected before any body read
    over = stubs._HttpResp(content=PNG_HEAD + b"0" * 1000,
                           headers={"Content-Type": "image/png",
                                    "Content-Length": str(big)}, status=200)
    with _patch_requests_get([("x.png", over)]):
        assert figures._image_ok("https://arxiv.org/html/p/x.png") is None
    # (b) an over-cap body (no/short Content-Length) is stream-read to the cap;
    # dims still parse from the leading header bytes (996x673)
    huge = stubs._HttpResp(content=PNG_HEAD + b"0" * big,
                           headers={"Content-Type": "image/png"}, status=200)
    with _patch_requests_get([("x.png", huge)]):
        assert figures._image_ok("https://arxiv.org/html/p/x.png") == (996, 673)


def test_fetch_figures_end_to_end_cc_paper():
    with monkeypatched_http():
        out = figures.fetch_figures("https://arxiv.org/abs/2607.02116")
    assert out["reason"] is None and out["license"]
    assert 1 <= len(out["figures"]) <= 4
    f = out["figures"][0]
    assert set(f) == {"index", "url", "caption", "width", "height"}
    assert f["url"].startswith("https://arxiv.org/")


def test_fetch_figures_noncc_gated():
    with monkeypatched_http():
        out = figures.fetch_figures("https://arxiv.org/abs/2607.01641")   # perpetual license
    assert out["figures"] == [] and out["reason"] == "license"
    assert "perpetual" in out["license"].lower()


def test_fetch_figures_no_html():
    with monkeypatched_http_404():
        out = figures.fetch_figures("https://arxiv.org/abs/9999.00001")
    assert out == {"figures": [], "license": None, "reason": "no_html"}


def test_multi_img_and_table_figures_excluded():
    # 02116 fixture contains multi-<img> subfigure grids (audit: 21 across lane)
    # and the candidate filter must yield only single-img Figure-captioned ones.
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(HTML_02116, "html.parser")
    cands = figures._candidates(soup)
    assert all(len(f.find_all("img")) == 1 for f in cands)
    assert all(f.find("figcaption").get_text(strip=True).lower().startswith("figure") for f in cands)
    assert len(cands) <= 4


check("license: CC, non-CC, decoy isolation", test_license_classify_cc_and_noncc_and_decoy)
check("caption: MathML stripped, len<=400", test_caption_cleaning_strips_mathml)
check("resolve_src: versioned / relative / absolute arxiv / foreign blocked", test_resolver_three_branches)
check("dims: jpeg_dims + png_dims on real .head fixtures", test_dims_parsers_on_real_bytes)
check("_image_ok: caps wire read + rejects oversize Content-Length", test_image_ok_caps_wire_read_and_rejects_oversize)
check("fetch_figures: CC paper end-to-end", test_fetch_figures_end_to_end_cc_paper)
check("fetch_figures: non-CC gated with reason=license", test_fetch_figures_noncc_gated)
check("fetch_figures: 404 HTML → reason=no_html", test_fetch_figures_no_html)
check("candidates: single-img Figure-captioned only, <=4", test_multi_img_and_table_figures_excluded)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
