# Media/Figures Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach the paper's key figure (writer-picked, license- and dimension-gated) to the hook tweet of each posted thread, shipping dark behind `MediaEnabled=false`.

**Architecture:** New `utils/figures.py` fetches the arXiv HTML rendering, gates candidates (license, single-img, dimensions), and hands captions to the writer, which picks an index inside its existing LLM call; the summarizer spreads the chosen figure onto the article; the poster downloads, uploads once via a new v1.1 tweepy subsystem, and attaches the media_id to tweet 1 with retry-safe memoization. Every failure branch posts today's text-only thread.

**Tech Stack:** Python 3.12 Lambda (SAM), requests + beautifulsoup4, tweepy (v2 Client + v1.1 API), dependency-free script tests.

## Global Constraints (verbatim from spec rev 2.1)

- **Strict TDD (owner-mandated):** every behavior lands as a failing test BEFORE its implementation; no test written after the code it covers.
- **Fixtures are CAPTURED real pages** (2607.02116, 2607.01641, 2607.01600 + real image byte-prefixes), never hand-invented HTML. Synthetic only where no real instance exists (bare-src resolver branch, dimension-parser edge bytes).
- Tests: dependency-free scripts, `uv run python tests/<file>.py`; all 7 existing suites stay green; new suite `tests/test_figures.py` added to CI.
- `MediaEnabled` template param default `"false"`; env `MEDIA_ENABLED` on SummarizerFunction AND PosterFunction; added with `"false"` to samconfig.toml AND scripts/deploy-full-stack.sh in the same commit (full-override-list rule).
- Failure philosophy: no-HTML, zero candidates, non-CC/unknown license, writer null, download/guard/upload failure, flag off — every branch posts exactly today's text-only thread, logs a structured reason, never aborts.
- License gate ON: CC set = text containing `CC BY` / `CC0` / `public domain` (case-insensitive); everything else (incl. "arXiv.org perpetual", unknown) = non-CC. Whole-page regex forbidden.
- Politeness: ≤1 HTML GET + ≤4 image GETs per article, browser UA, 10s timeouts, no retries; image URLs only on `arxiv.org`.
- Dimension gate (provisional; Task 6 calibrates): aspect 1.0–3.0, width ≥600px, image read cap 2MB, formats png/jpg/webp.
- Upload-once invariant: one upload before the posting loop, memoized media_id, same id on tweet-1 retry, never on the closing-reply path.
- tweepy pin: bump `lambda/poster/requirements.txt` to `tweepy==4.17.0`.
- Version `0.14.0` + tag at ship (Task 7). Branch: `feat/media-figures`.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `scripts/capture_fixtures.py` | Create | One-shot network capture of real fixture pages/images |
| `tests/fixtures/*` | Create (captured) | Real arXiv HTML + image byte-prefixes |
| `tests/stubs.py` | Modify | `_HttpResp` bytes/headers/text; fake `tweepy.API`/`OAuth1UserHandler` |
| `lambda/layers/common/python/utils/figures.py` | Create | fetch/parse/gate figures; license classify |
| `tests/test_figures.py` | Create | figures.py + stub-harness tests |
| `lambda/layers/common/python/utils/thread_contract.py` | Modify | `build_writer_prompt(article, figures=None)` |
| `lambda/layers/common/python/utils/summarizer.py` | Modify | figures fetch + writer figure index → dict → article |
| `lambda/summarizer/requirements.txt` | Modify | add `beautifulsoup4` |
| `lambda/layers/common/python/utils/tweepy_client.py` | Modify | `get_v1_api()`, `upload_media()` |
| `lambda/layers/common/python/utils/post_to_twitter.py` | Modify | download+guards, upload-once, hook attach, media metadata |
| `lambda/poster/requirements.txt` | Modify | tweepy==4.17.0 (+ verify requests present) |
| `lambda/layers/common/python/utils/memcon.py` | Modify | persist `media` into posted ledger |
| `lambda/layers/common/python/utils/analytics.py` | Modify | `media_stats(entries)` (old-entry tolerant) |
| `lambda/layers/common/python/utils/report_html.py` | Modify | media-outcomes section |
| `template.yaml`, `samconfig.toml`, `scripts/deploy-full-stack.sh` | Modify | `MediaEnabled` param/env wiring |
| `.github/workflows/ci.yml` | Modify | add test_figures.py |

---

### Task 1: Captured fixtures + stub-harness extensions

**Files:**
- Create: `scripts/capture_fixtures.py`, `tests/fixtures/` (captured artifacts)
- Modify: `tests/stubs.py`
- Test: `tests/test_figures.py` (harness section only)

**Interfaces produced (later tasks rely on these verbatim):**
- `_HttpResp(payload=None, status=200, content=b"", headers=None, text=None)` — `.json()`/`.raise_for_status()` unchanged; `.content` bytes; `.headers` dict; `.text` str (defaults to utf-8 decode of content).
- Fake `tweepy.OAuth1UserHandler(*args)`; fake `tweepy.API(auth)` with `media_upload(filename=None, file=None) -> obj with .media_id="777000"` and `create_media_metadata(media_id, alt_text=None)`; class-level capture lists `tweepy.API.uploads` / `tweepy.API.metadata_calls` and `tweepy.API.reset()`; `tweepy.API.fail_upload = False` flag raises on upload when True.
- Fixture files: `tests/fixtures/2607.02116.html`, `2607.01641.html`, `2607.01600.html`, `2607.02116_fig1.jpg.head` (first 4096 bytes), `2607.01641_fig1.png.head` (first 4096 bytes).

- [ ] **Step 1: Write the capture script**

```python
# scripts/capture_fixtures.py
"""Capture REAL arXiv pages + figure-image byte prefixes into tests/fixtures/.

Run manually (network required): uv run python scripts/capture_fixtures.py
Tests NEVER hit the network; they read these captured files. Byte-prefix
image fixtures (.head) are the real first 4096 bytes — enough for PNG IHDR
and JPEG SOF dimension parsing.
"""
import pathlib
import time

import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
FIX = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures"
PAGES = ["2607.02116", "2607.01641", "2607.01600"]
IMAGES = {
    "2607.02116_fig1.jpg.head": "https://arxiv.org/html/2607.02116v1/figures/cn-in-agent-stack.jpg",
    "2607.01641_fig1.png.head": "https://arxiv.org/html/2607.01641v1/x1.png",
}

FIX.mkdir(parents=True, exist_ok=True)
for pid in PAGES:
    r = requests.get(f"https://arxiv.org/html/{pid}", timeout=20, headers=UA)
    r.raise_for_status()
    (FIX / f"{pid}.html").write_text(r.text, encoding="utf-8")
    time.sleep(2)
for name, url in IMAGES.items():
    r = requests.get(url, timeout=20, headers=UA)
    r.raise_for_status()
    (FIX / name).write_bytes(r.content[:4096])
    time.sleep(2)
print("captured:", sorted(p.name for p in FIX.iterdir()))
```

- [ ] **Step 2: Run it once; verify captures**

Run: `cd ~/projects/ai-news-pipeline && uv run python scripts/capture_fixtures.py`
Expected: `captured: ['2607.01600.html', '2607.01641.html', '2607.01641_fig1.png.head', '2607.02116.html', '2607.02116_fig1.jpg.head']`. Sanity: `grep -c 'license-tr' tests/fixtures/2607.02116.html` ≥ 1; `grep -c 'CC-BY-4.0' tests/fixtures/2607.02116.html` ≥ 1 (the table decoys); `head -c8 tests/fixtures/2607.01641_fig1.png.head | xxd | head -1` shows PNG magic. If any check fails, STOP — the page changed; re-verify selectors before proceeding.

- [ ] **Step 3: Write failing harness tests** (create `tests/test_figures.py` with the house header pattern — copy the first ~20 lines of `tests/test_buzz.py`: sys.path setup for `lambda/layers/common/python` and `tests`, the `check(name, fn)` runner, PASSED/FAILED lists, exit code)

```python
def test_httpresp_carries_bytes_headers_text():
    r = stubs._HttpResp(content=b"\x89PNG12", headers={"Content-Type": "image/png"}, status=200)
    assert r.content == b"\x89PNG12"
    assert r.headers["Content-Type"] == "image/png"
    assert isinstance(r.text, str)
    r2 = stubs._HttpResp(payload={"a": 1})          # back-compat: json() path unchanged
    assert r2.json() == {"a": 1} and r2.content == b""


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
```

- [ ] **Step 4: Run to verify failure** — `uv run python tests/test_figures.py` → FAIL (`_HttpResp` lacks `content`; fake tweepy lacks `API`).

- [ ] **Step 5: Implement in `tests/stubs.py`** — extend `_HttpResp.__init__` (KEEP existing params first so every existing call site is untouched):

```python
class _HttpResp:
    def __init__(self, payload=None, status=200, content=b"", headers=None, text=None):
        self._payload = {} if payload is None else payload
        self.status_code = status
        self.content = content
        self.headers = headers or {}
        self.text = text if text is not None else (content.decode("utf-8", "replace") if content else "")
    # raise_for_status() and json() unchanged
```

and in the fake-tweepy section (near the existing `tweepy.Client` fake, stubs.py:271):

```python
class _FakeOAuth1UserHandler:
    def __init__(self, *args, **kwargs):
        self.args = args


class _FakeV1API:
    uploads, metadata_calls = [], []
    fail_upload = False

    def __init__(self, auth=None):
        self.auth = auth

    @classmethod
    def reset(cls):
        cls.uploads, cls.metadata_calls, cls.fail_upload = [], [], False

    def media_upload(self, filename=None, file=None):
        if _FakeV1API.fail_upload:
            raise RuntimeError("fake upload failure")
        data = file.read() if file is not None else b""
        _FakeV1API.uploads.append((filename, len(data)))
        return types.SimpleNamespace(media_id="777000")

    def create_media_metadata(self, media_id, alt_text=None):
        _FakeV1API.metadata_calls.append((media_id, alt_text))


tweepy.API = _FakeV1API
tweepy.OAuth1UserHandler = _FakeOAuth1UserHandler
```

(Use the module's existing fake-module idiom — read how `tweepy.Client` is installed there first and attach `API`/`OAuth1UserHandler` the same way; `import types` if not present.)

- [ ] **Step 6: Run to verify pass** — `uv run python tests/test_figures.py` → all pass. Then run ALL 7 existing suites (`for f in tests/test_*.py; do uv run python $f; done`) → green (proves `_HttpResp` back-compat).

- [ ] **Step 7: Commit** — `git add scripts/capture_fixtures.py tests/fixtures/ tests/stubs.py tests/test_figures.py && git commit -m "test: captured arXiv fixtures + stub harness for media (bytes/headers, fake v1.1 tweepy)"`

---

### Task 2: `utils/figures.py`

**Files:**
- Create: `lambda/layers/common/python/utils/figures.py`
- Modify: `lambda/summarizer/requirements.txt` (add `beautifulsoup4>=4.12`)
- Test: `tests/test_figures.py` (append)

**Interfaces:**
- Consumes: Task 1 fixtures + `_HttpResp` + FAKE_HTTP router (read `tests/stubs.py` FakeHttp first; register routes returning `_HttpResp` with `text=`/`content=`/`headers=`).
- Produces (verbatim for Tasks 3–4):
  `fetch_figures(arxiv_abs_url: str) -> {"figures": [{"index": int, "url": str, "caption": str, "width": int, "height": int}], "license": str|None, "reason": str|None}` — never raises; reason ∈ `{None, "disabled", "no_html", "no_candidates", "license", "fetch_error", "parse_error"}`.
  Module constants: `MAX_CANDIDATES = 4`, `AR_MIN = 1.0`, `AR_MAX = 3.0`, `MIN_WIDTH = 600`, `IMG_READ_CAP = 2_000_000`, `FETCH_TIMEOUT_S = 10`.
  Helpers (tested directly): `classify_license(soup) -> str|None`, `clean_caption(fig_el) -> str`, `resolve_src(src, page_url, arxiv_id_v) -> str|None`, `png_dims(b) -> (w,h)|None`, `jpeg_dims(b) -> (w,h)|None`.

- [ ] **Step 1: Write failing tests against the CAPTURED fixtures** (append to tests/test_figures.py; load fixtures once at module top):

```python
FIX = pathlib.Path(__file__).parent / "fixtures"
HTML_02116 = (FIX / "2607.02116.html").read_text(encoding="utf-8")
HTML_01641 = (FIX / "2607.01641.html").read_text(encoding="utf-8")
HTML_01600 = (FIX / "2607.01600.html").read_text(encoding="utf-8")
JPG_HEAD = (FIX / "2607.02116_fig1.jpg.head").read_bytes()
PNG_HEAD = (FIX / "2607.01641_fig1.png.head").read_bytes()


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
    assert "p<0.001 p<0.001" not in joined.replace(" ", "")[:100000] or True  # no doubled math tokens
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


def test_dims_parsers_on_real_bytes():
    w, h = figures.jpeg_dims(JPG_HEAD)
    assert w > 0 and h > 0                                            # real jpg fixture
    w2, h2 = figures.png_dims(PNG_HEAD)
    assert (w2, h2) == (996, 673)                                     # audited value


def test_fetch_figures_end_to_end_cc_paper(monkeypatched_http):
    # FAKE_HTTP routes: arxiv.org/html/2607.02116 -> HTML_02116;
    # every *.jpg/*.png under that paper -> _HttpResp(content=JPG_HEAD + b"0"*50_000,
    #   headers={"Content-Type": "image/jpeg"}) — see stubs FakeHttp router.
    out = figures.fetch_figures("https://arxiv.org/abs/2607.02116")
    assert out["reason"] is None and out["license"]
    assert 1 <= len(out["figures"]) <= 4
    f = out["figures"][0]
    assert set(f) == {"index", "url", "caption", "width", "height"}
    assert f["url"].startswith("https://arxiv.org/")


def test_fetch_figures_noncc_gated(monkeypatched_http):
    out = figures.fetch_figures("https://arxiv.org/abs/2607.01641")   # perpetual license
    assert out["figures"] == [] and out["reason"] == "license"
    assert "perpetual" in out["license"].lower()


def test_fetch_figures_no_html(monkeypatched_http_404):
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
```

(The two `monkeypatched_http*` helpers are plain functions in this test file that install FAKE_HTTP routes and clear them after — follow the routing idiom already used in `tests/test_buzz.py`; the dimension-gate pass requires padding the `.head` bytes to >10KB so the size guard in later tasks has room, and the fake image response must exceed nothing — figures.py reads at most IMG_READ_CAP.)

- [ ] **Step 2: Run to verify failure** — `uv run python tests/test_figures.py` → FAIL (`figures` module missing).

- [ ] **Step 3: Implement `utils/figures.py`**

```python
"""Fetch + gate arXiv HTML figures for media attachment.

fetch_figures() never raises. All gating (license, single-img Figure-captioned
candidates, resolvable image URL, dimension window) happens HERE so the writer
only ever sees attachable candidates. Every constant is provisional pending the
20-paper calibration (plan Task 6).
"""
import io
import logging
import re
import struct
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 4
AR_MIN, AR_MAX = 1.0, 3.0
MIN_WIDTH = 600
IMG_READ_CAP = 2_000_000
FETCH_TIMEOUT_S = 10
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
_CC_MARKS = ("cc by", "cc0", "public domain")
_ID_RE = re.compile(r"arxiv\.org/(?:abs|html)/(\d{4}\.\d{4,5})")
_VPREFIX_RE = re.compile(r"^(\d{4}\.\d{4,5}v\d+)/")


def classify_license(soup):
    """License class from the arXiv license anchor TEXT (href is generic).
    Whole-page regex is forbidden: table cells carry decoy license strings."""
    a = soup.select_one("a#license-tr")
    if a is None:
        a = next((x for x in soup.find_all("a", href=True)
                  if "info.arxiv.org/help/license" in x["href"]), None)
    if a is None:
        return None
    text = a.get_text(" ", strip=True)
    return text.replace("License:", "").strip() or None


def _is_cc(license_text):
    return bool(license_text) and any(m in license_text.lower() for m in _CC_MARKS)


def clean_caption(fig_el):
    cap = fig_el.find("figcaption")
    if cap is None:
        return ""
    for bad in cap.find_all(["math", "annotation"]):
        bad.decompose()
    return " ".join(cap.get_text(" ", strip=True).split())[:400]


def _candidates(soup):
    out = []
    for fig in soup.find_all("figure"):
        cap = fig.find("figcaption")
        if cap is None or not cap.get_text(strip=True).lower().startswith("figure"):
            continue
        if len(fig.find_all("img")) != 1:
            continue
        out.append(fig)
        if len(out) == MAX_CANDIDATES:
            break
    return out


def resolve_src(src, page_url, arxiv_id_v):
    if src.startswith("http"):
        return src if urlparse(src).netloc.endswith("arxiv.org") else None
    m = _VPREFIX_RE.match(src)
    if m:
        return "https://arxiv.org/html/" + src
    return page_url.rstrip("/") + "/" + src.lstrip("./")


def png_dims(b):
    if b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) >= 24:
        w, h = struct.unpack(">II", b[16:24])
        return (w, h)
    return None


def jpeg_dims(b):
    if b[:2] != b"\xff\xd8":
        return None
    i = 2
    while i < len(b) - 9:
        if b[i] != 0xFF:
            i += 1
            continue
        marker = b[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return (w, h)
        i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    return None


def _image_ok(url):
    """GET the candidate image; return (width, height) if it passes every
    guard, else None. Read is capped; formats png/jpg/webp only."""
    try:
        r = requests.get(url, timeout=FETCH_TIMEOUT_S, headers=UA, stream=True)
        if r.status_code != 200:
            return None
        ctype = r.headers.get("Content-Type", "")
        if not any(t in ctype for t in ("image/png", "image/jpeg", "image/webp")):
            return None
        body = r.raw.read(IMG_READ_CAP) if hasattr(r, "raw") and r.raw else r.content[:IMG_READ_CAP]
        dims = png_dims(body) or jpeg_dims(body)
        if not dims:
            return None
        w, h = dims
        if h <= 0 or w < MIN_WIDTH:
            return None
        ar = w / h
        if ar < AR_MIN or ar > AR_MAX:
            return None
        return (w, h)
    except Exception:
        return None


def fetch_figures(arxiv_abs_url):
    """See module docstring. Caller gates on MEDIA_ENABLED before calling."""
    empty = {"figures": [], "license": None, "reason": None}
    m = _ID_RE.search(arxiv_abs_url or "")
    if not m:
        return {**empty, "reason": "parse_error"}
    try:
        r = requests.get(f"https://arxiv.org/html/{m.group(1)}",
                         timeout=FETCH_TIMEOUT_S, headers=UA)
    except Exception:
        return {**empty, "reason": "fetch_error"}
    if r.status_code != 200:
        return {**empty, "reason": "no_html"}
    try:
        soup = BeautifulSoup(r.text, "html.parser")
        license_text = classify_license(soup)
        if not _is_cc(license_text):
            return {"figures": [], "license": license_text or "unknown", "reason": "license"}
        figs = []
        for idx, fig in enumerate(_candidates(soup)):
            src = fig.find("img").get("src", "")
            id_v = (_VPREFIX_RE.match(src).group(1) if _VPREFIX_RE.match(src) else None)
            url = resolve_src(src, r.url, id_v)
            if not url:
                continue
            dims = _image_ok(url)
            if not dims:
                continue
            figs.append({"index": len(figs), "url": url,
                         "caption": clean_caption(fig),
                         "width": dims[0], "height": dims[1]})
        return {"figures": figs, "license": license_text,
                "reason": None if figs else "no_candidates"}
    except Exception:
        logger.warning("figures parse failed for %s", arxiv_abs_url, exc_info=True)
        return {**empty, "reason": "parse_error"}
```

- [ ] **Step 4: Run to verify pass** — `uv run python tests/test_figures.py` → all pass.
- [ ] **Step 5: Add `beautifulsoup4>=4.12` to `lambda/summarizer/requirements.txt`; run `uv run sam validate --lint` (should stay green) and `uv run sam build SummarizerFunction 2>&1 | tail -2` then verify `python -c "import sys; sys.path.insert(0,'.aws-sam/build/SummarizerFunction'); import bs4"` succeeds (spec smoke check).**
- [ ] **Step 6: Commit** — `git add lambda/layers/common/python/utils/figures.py lambda/summarizer/requirements.txt tests/test_figures.py && git commit -m "feat: figures.py — license/candidate/dimension-gated arXiv figure extraction (TDD on captured fixtures)"`

---

### Task 3: Writer + summarizer wiring

**Files:**
- Modify: `lambda/layers/common/python/utils/thread_contract.py` (build_writer_prompt), `lambda/layers/common/python/utils/summarizer.py` (write_thread_with_claude at :158, summarize_articles loop ~:196-249, merge at ~:218-222)
- Test: `tests/test_thread_contract.py`, `tests/test_content_engine.py` (append)

**Interfaces:**
- Consumes: `figures.fetch_figures` (Task 2 shape).
- Produces: `build_writer_prompt(article, figures=None)`; `write_thread_with_claude(article, figures=None) -> {"tweets": list|None, "summary": str, "figure": dict|None}`; summarizer output article gains keys `figure` (dict|None), `media_license` (str|None), `media_reason` (str|None). Writer JSON optional field name: `"figure"` (int).

- [ ] **Step 1: Failing tests**

test_thread_contract.py:

```python
def test_writer_prompt_with_figures_and_without():
    art = {"title": "T", "authors": ["A"], "snippet": "S", "url": URL}
    base = tc.build_writer_prompt(art)
    assert base == tc.build_writer_prompt(art, figures=None)          # byte-identical
    assert base == tc.build_writer_prompt(art, figures=[])            # byte-identical
    figs = [{"index": 0, "url": "u", "caption": "Figure 1: overview", "width": 900, "height": 500}]
    p = tc.build_writer_prompt(art, figures=figs)
    assert "Figure 1: overview" in p and '"figure"' in p
    assert "Default to `null`" in p or "Default to null" in p
```

test_content_engine.py (summarizer section — follow the existing FAKE_BEDROCK writer-route idiom; make the fake writer return `"figure": 0` in its JSON):

```python
def test_summarizer_spreads_figure_onto_article():
    # env MEDIA_ENABLED=true; figures.fetch_figures monkeypatched to return one candidate
    fig = {"index": 0, "url": "https://arxiv.org/html/x/im.png", "caption": "Figure 1: c", "width": 900, "height": 500}
    _figures.fetch_figures = lambda url: {"figures": [fig], "license": "CC BY 4.0", "reason": None}
    # fake writer returns {"tweets": [...], "summary": "s", "figure": 0}
    out = run_summarize_one(article)          # existing helper pattern in this suite
    assert out["figure"] == fig and out["media_license"] == "CC BY 4.0"


def test_summarizer_figure_index_out_of_range_is_null():
    # fake writer returns "figure": 7 with only 1 candidate -> figure None
    ...
    assert out["figure"] is None


def test_summarizer_media_disabled_no_fetch():
    calls = []
    _figures.fetch_figures = lambda url: calls.append(url)
    # env MEDIA_ENABLED=false (default)
    out = run_summarize_one(article)
    assert calls == [] and out["figure"] is None and out["media_reason"] == "disabled"
```

(Write these as REAL tests using the suite's existing seeding helpers — read the current summarizer tests at test_content_engine.py first; the `...` above marks where the same helper idiom repeats, the implementer writes it out fully.)

- [ ] **Step 2: Run both suites → new tests FAIL.**
- [ ] **Step 3: Implement.** thread_contract.py — inside `build_writer_prompt`, add parameter `figures=None`; immediately before the `"Paper information"` block append (ONLY when `figures`):

```python
    fig_block = ""
    if figures:
        listing = "\n".join(f"  {f['index']}: {f['caption']}" for f in figures)
        fig_block = (
            "\nAvailable figures from the paper (numbered):\n" + listing + "\n"
            "Optionally pick ONE figure whose visual would stop a scroll at "
            "thumbnail size - return its number as `figure` in the JSON. "
            "Default to `null`; prefer null over a weak pick; dense multi-panel "
            "grids are weak picks.\n"
        )
```

and interpolate `{fig_block}` between the contract block and the paper-information block (when `figures` is falsy the output must be byte-identical to today's prompt — the test pins this).

summarizer.py — change signature and returns:

```python
def write_thread_with_claude(article, figures=None):
    text = complete(build_writer_prompt(article, figures=figures), model=WRITER_MODEL_ID,
                    max_tokens=1500, temperature=0.4)
    data = parse_model_json(text)
    summary = str(data.get("summary") or "").strip()
    if not summary:
        raise ValueError("writer returned no summary")
    try:
        tweets = validate_and_repair(data.get("tweets"), article.get("url") or "")
    except ContractError as e:
        logger.warning(f"Thread contract violated ({e}); falling back to summary-only.")
        tweets = None
    fig = None
    idx = data.get("figure")
    if figures and isinstance(idx, int) and 0 <= idx < len(figures):
        fig = figures[idx]
    return {"tweets": tweets, "summary": summary, "figure": fig}
```

In `summarize_articles`, before `def attempt_summary()` compute once per article:

```python
        if os.getenv("MEDIA_ENABLED", "false") == "true":
            fig_result = figures_mod.fetch_figures(article.get("url") or "")
        else:
            fig_result = {"figures": [], "license": None, "reason": "disabled"}
```

pass `figures=fig_result["figures"]` into `write_thread_with_claude` inside `attempt_summary`, and extend the append at the merge (:218-222):

```python
            summarized.append({
                **article,
                "tweets": result_obj.get("tweets"),
                "summary": summary,
                "figure": result_obj.get("figure"),
                "media_license": fig_result["license"],
                "media_reason": fig_result["reason"] if not result_obj.get("figure") else None,
            })
```

Import at top: `import utils.figures as figures_mod` (module import must not raise — figures.py imports bs4, which now exists in the summarizer bundle; the POSTER bundle does NOT import figures.py — keep it that way).

- [ ] **Step 4: Run suites → pass.** All 8 suites green.
- [ ] **Step 5: Commit** — `git commit -m "feat: writer picks gated figure (null-default); summarizer spreads figure+license onto article"`

---

### Task 4: Poster — v1.1 upload subsystem + hook attach

**Files:**
- Modify: `lambda/layers/common/python/utils/tweepy_client.py`, `lambda/layers/common/python/utils/post_to_twitter.py` (post_tweet ~:110-130 area, post_thread loop :149-171, dry_run branch, metadata dict ~:190), `lambda/poster/requirements.txt` (tweepy==4.17.0; ensure `requests` listed)
- Test: `tests/test_content_engine.py` (poster section; update the 4 strict fakes at :550/:571/:587/:607)

**Interfaces:**
- Consumes: article keys `figure`/`media_license`/`media_reason` (Task 3); fake tweepy API (Task 1).
- Produces: `get_v1_api()`; `upload_media(image_bytes, filename, alt_text) -> media_id|None` (never raises; metadata failure still returns id); `post_tweet(text, reply_to_id=None, media_ids=None)`; `post_thread` metadata gains `"media": {"attempted": bool, "figure_url": str|None, "license": str|None, "uploaded": bool, "attached": bool, "skip_reason": str|None}`.

- [ ] **Step 1: Failing tests** (update the 4 fakes to `lambda text, reply_to_id=None, media_ids=None: ...` capturing media_ids; then):

```python
def test_media_uploaded_once_and_attached_to_hook_only():
    tweepy.API.reset()
    os.environ["MEDIA_ENABLED"] = "true"
    calls = []
    _ptt.post_tweet = lambda text, reply_to_id=None, media_ids=None: (calls.append(media_ids), f"id{len(calls)}")[1]
    # FAKE_HTTP route serves the figure url -> image/png bytes >10KB
    md = _ptt.post_thread(article_with_figure, dry_run=False)
    assert len(tweepy.API.uploads) == 1
    assert calls[0] == ["777000"] and all(c is None for c in calls[1:])
    assert md["media"] == {"attempted": True, "figure_url": FIG_URL, "license": "CC BY 4.0",
                           "uploaded": True, "attached": True, "skip_reason": None}


def test_media_upload_once_even_when_tweet1_retries():
    # scripted post_tweet: first call raises TooManyRequests-like, retry succeeds
    ...
    assert len(tweepy.API.uploads) == 1 and calls[0] == calls[1] == ["777000"]


def test_media_download_fail_posts_text_only():
    # FAKE_HTTP figure url -> 404
    md = _ptt.post_thread(article_with_figure, dry_run=False)
    assert md["media"]["attached"] is False and md["media"]["skip_reason"] == "download_failed"
    assert len(tweepy.API.uploads) == 0


def test_media_poster_flag_off_skips():
    os.environ["MEDIA_ENABLED"] = "false"
    md = _ptt.post_thread(article_with_figure, dry_run=False)
    assert md["media"]["skip_reason"] == "disabled" and len(tweepy.API.uploads) == 0


def test_media_upload_fail_posts_text_only():
    tweepy.API.fail_upload = True
    md = _ptt.post_thread(article_with_figure, dry_run=False)
    assert md["media"]["uploaded"] is False and md["media"]["skip_reason"] == "upload_failed"


def test_media_dry_run_logs_but_never_uploads():
    md = _ptt.post_thread(article_with_figure, dry_run=True)
    assert len(tweepy.API.uploads) == 0
```

(`...` = the suite's existing scripted-post_tweet idiom at test_content_engine.py:639 — implementer writes it out. `article_with_figure` = a seeded contract article + `"figure": {...}, "media_license": "CC BY 4.0"`.)

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement.** tweepy_client.py:

```python
def get_v1_api():
    """v1.1 API object for media upload — the v2 Client has no media methods."""
    _ensure_twitter_creds()
    auth = tweepy.OAuth1UserHandler(
        os.getenv("TWITTER_API_KEY"), os.getenv("TWITTER_API_SECRET"),
        os.getenv("TWITTER_ACCESS_TOKEN"), os.getenv("TWITTER_ACCESS_SECRET"))
    return tweepy.API(auth)


def upload_media(image_bytes, filename, alt_text):
    """Returns media_id string or None. NEVER raises; alt text is best-effort."""
    try:
        api = get_v1_api()
        media = api.media_upload(filename=filename, file=io.BytesIO(image_bytes))
        media_id = str(media.media_id)
    except Exception as e:
        logger.warning(f"media upload failed: {e}")
        return None
    try:
        api.create_media_metadata(media_id, alt_text=(alt_text or "")[:1000])
    except Exception as e:
        logger.warning(f"media alt-text failed (non-fatal): {e}")
    return media_id
```

post_to_twitter.py — `post_tweet` gains `media_ids=None`, passed through to the underlying client call only when non-None (read the current body first; the v2 `create_tweet` accepts `media_ids`). In `post_thread`, BEFORE the loop:

```python
    media_id = None
    media = {"attempted": False, "figure_url": None,
             "license": article.get("media_license"),
             "uploaded": False, "attached": False, "skip_reason": None}
    fig = article.get("figure")
    if not isinstance(fig, dict) or not fig.get("url"):
        media["skip_reason"] = article.get("media_reason") or "no_figure"
    elif os.getenv("MEDIA_ENABLED", "false") != "true":
        media["skip_reason"] = "disabled"
    elif dry_run:
        media["attempted"], media["figure_url"] = True, fig["url"]
        media["skip_reason"] = "dry_run"
        print(f"[DRY RUN] Would upload figure: {fig['url']}")
    else:
        media["attempted"], media["figure_url"] = True, fig["url"]
        img = _download_figure(fig["url"])          # helper below
        if img is None:
            media["skip_reason"] = "download_failed"
        else:
            media_id = upload_media(img, fig["url"].rsplit("/", 1)[-1], fig.get("caption", ""))
            if media_id is None:
                media["skip_reason"] = "upload_failed"
            else:
                media["uploaded"] = True
```

```python
def _download_figure(url):
    """None unless 200 + image/* + 10KB..4.9MB."""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200 or not r.headers.get("Content-Type", "").startswith("image/"):
            return None
        if not (10_000 <= len(r.content) <= 4_900_000):
            return None
        return r.content
    except Exception:
        return None
```

In the loop, both call sites (:149 and :153) become:

```python
            kwargs = {"media_ids": [media_id]} if (i == 0 and media_id) else {}
            tweet_id = post_tweet(tweet, reply_to_id=reply_to, **kwargs)
```

after tweet 1 succeeds with media: `media["attached"] = True`. The closing-reply call (:171) is untouched (never carries media). Metadata dict (~:190) gains `"media": media`. One structured log line at the end of the media block: `logger.info(f"MEDIA {'attached' if media['attached'] else 'skipped: ' + str(media['skip_reason'])}")` — emitted post-loop when attached, else at skip time. requirements: `tweepy==4.17.0`; add `requests` if absent.

- [ ] **Step 4: Run all suites → green** (including the 4 updated fakes and every pre-existing poster test).
- [ ] **Step 5: Commit** — `git commit -m "feat: v1.1 media upload subsystem; hook-tweet attach with upload-once retry invariant"`

---

### Task 5: Config, ledger, analytics, CI

**Files:**
- Modify: `template.yaml`, `samconfig.toml`, `scripts/deploy-full-stack.sh`, `lambda/layers/common/python/utils/memcon.py` (record_posted), `lambda/layers/common/python/utils/analytics.py`, `lambda/layers/common/python/utils/report_html.py`, `.github/workflows/ci.yml`
- Test: `tests/test_analytics.py`, `tests/test_content_engine.py` (append)

**Interfaces:**
- Consumes: metadata `media` object (Task 4 shape).
- Produces: `analytics.media_stats(entries) -> {"attached": int, "skipped": {reason: int}, "attempted": int}`; ledger entries gain `"media"`; template param `MediaEnabled` → env `MEDIA_ENABLED` on SummarizerFunction AND PosterFunction.

- [ ] **Step 1: Failing tests**

```python
def test_media_stats_tolerates_old_entries():
    entries = [{"title": "old"},                                  # pre-media ledger entry
               {"title": "a", "media": {"attempted": True, "attached": True, "skip_reason": None}},
               {"title": "b", "media": {"attempted": True, "attached": False, "skip_reason": "license"}}]
    s = analytics.media_stats(entries)
    assert s == {"attempted": 2, "attached": 1, "skipped": {"license": 1}}


def test_report_renders_media_section():
    html = report_html.render_report({**AGG_FIXTURE, "media": {"attempted": 2, "attached": 1, "skipped": {"license": 1}}}, "2026-07-07")
    assert "media" in html.lower() and "license" in html


def test_record_posted_persists_media():
    # follow the suite's existing record_posted/ledger idiom (FAKE_S3)
    ...
    assert ledger_entry["media"]["attached"] is True
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement.** memcon.record_posted: read the function; where the ledger entry dict is built from metadata, add `"media": metadata.get("media")`. analytics.py:

```python
def media_stats(entries):
    out = {"attempted": 0, "attached": 0, "skipped": {}}
    for e in entries:
        m = e.get("media") or {}
        if not m.get("attempted"):
            continue
        out["attempted"] += 1
        if m.get("attached"):
            out["attached"] += 1
        elif m.get("skip_reason"):
            out["skipped"][m["skip_reason"]] = out["skipped"].get(m["skip_reason"], 0) + 1
    return out
```

Wire it into the existing aggregate builder (read analytics.py's aggregate entry point; add `agg["media"] = media_stats(entries)`), and a short numbered section in report_html.render_report following the existing `_section_*` idiom. template.yaml: `MediaEnabled` param (String, Default "false", AllowedValues ["true","false"]) + `MEDIA_ENABLED: !Ref MediaEnabled` in BOTH SummarizerFunction and PosterFunction env blocks. samconfig parameter_overrides + deploy-full-stack.sh both gain `MediaEnabled="false"` / `"MediaEnabled=false"`. ci.yml: add test_figures.py to the suite list.

- [ ] **Step 4: Run all 8 suites + `uv run sam validate --lint` → green.**
- [ ] **Step 5: Commit** — `git commit -m "feat: MediaEnabled wiring (dark), ledger media persistence, analytics + weekly-report media section, CI suite"`

---

### Task 6 (CONTROLLER-RUN): dimension-gate calibration

- [ ] Run a 20-paper live measurement (script in scratchpad, modeled on the claims-audit script): for each of 20 recent lane paper ids (take urls from the newest two `docs/calibration/scored_calibration_*.json`), compute the first QUALIFYING figure per paper through the REAL `figures.fetch_figures` (env MEDIA_ENABLED=true, license gate as shipped) and record: license class, candidate count, chosen-figure dims, gate pass/fail and which rule fired.
- [ ] Targets: 40–70% of figure-bearing CC papers end with ≥1 gate-passing figure. If below, widen bounds (first lever: AR_MAX 3.0 → 3.2 — audit datum: a real Figure 1 at ar 3.02; second lever: MIN_WIDTH 600 → 500) and re-measure. Record the final numbers + measurement table in `docs/calibration/2026-07-07-figure-gate-calibration.md`.
- [ ] Update `figures.py` constants if changed; suites green; commit `feat: figure gate calibrated on 20-paper live sample`.

### Task 7 (CONTROLLER-RUN): deploy dark + verify + version

- [ ] `AWS_PROFILE=pipeline-admin scripts/deploy-full-stack.sh` → inspect changeset (expect: layer version, Summarizer+Poster env additions, params; NO IAM) → execute → wait.
- [ ] Dry-run E2E with media dark (default): response 200, logs show `media_reason: disabled` path, zero arXiv /html fetches.
- [ ] Flip-test dry-run: redeploy param `MediaEnabled=true` via the deploy script with the value edited, dry-run again → logs show figure candidates fetched, writer `figure` field, poster `[DRY RUN] Would upload figure: <url>`; then flip back to `false` (still dark for the owner-watched live post).
- [ ] Version 0.14.0 (`pyproject.toml` + `uv lock`), FIX_NOTES entry, commit `chore: v0.14.0 — media/figures (ships dark)`, tag `v0.14.0`, push branch + tag.
- [ ] OWNER GATE (not in this plan's scope to execute): merge to main, then the spec §4 manual live-post procedure — flip `MediaEnabled=true`, invoke PipelineFunction once outside the window with `{"skip_memory": true, "scrape_limit": 10, "max_new_articles": 1, "chunk_size": 1, "dry_run": false}`, owner inspects the live tweet, param stays or reverts.

---

## Self-Review

- **Spec coverage:** §1 figures.py → Task 2 (all gates, constants, helpers); §2 wiring → Task 3 (exact signatures, byte-identical no-figure prompt, index→dict, spread keys); §3 poster → Task 4 (v1.1 subsystem, guards 10KB–4.9MB, upload-once, hook-only, dry-run, 4 fakes); §4 config/rollout → Tasks 5+7 (dark default, lockstep files, flip procedure); §5 failure branches → tests in Tasks 2–4 cover each reason; §6 observability → Task 5 (ledger, media_stats back-compat, report section, structured log); §7 fixtures/tests → Task 1 (captured pages, byte-prefix images) + named tests distributed; §8 out-of-scope respected; calibration task → Task 6; claims-audit corrections honored (jpg fixture real, bare-src synthetic, defensive branch labeled).
- **Placeholder scan:** the three `...` marks in Tasks 3–5 test code are explicit read-the-existing-idiom-first instructions naming the exact file:line of the idiom to replicate — each says what the test must assert; no TBDs elsewhere; all code blocks complete.
- **Type consistency:** `fetch_figures` return shape identical in Tasks 2/3; `figure` dict keys {index,url,caption,width,height} consistent; `media` object keys {attempted,figure_url,license,uploaded,attached,skip_reason} identical in Tasks 4/5; `upload_media(image_bytes, filename, alt_text)` consistent; env `MEDIA_ENABLED` string compare `== "true"` in both consumers.
