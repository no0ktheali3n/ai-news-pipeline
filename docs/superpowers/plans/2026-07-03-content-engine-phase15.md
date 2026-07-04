# Content Engine Phase 1.5 — Buzz Signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ground `hook_potential` in observed attention: enrich Phase 1's LLM scores with free buzz signals (HF Daily Papers upvotes, HN points/comments, Semantic Scholar citations) blended into the composite, stored in sidecar + ledger.

**Architecture:** A new `utils/buzz.py` module owns everything buzz: three best-effort fetchers (two batched single calls + a budget-capped per-candidate HN loop), a log-saturation normalizer to a 0–10 `buzz` value, and an `apply_buzz` re-ranker that cedes part of the hook weight to observed buzz. The scraper handler calls it between `score_candidates` and the sidecar/gate, wrapped so any failure degrades to Phase 1 LLM-only behavior. Provenance flows through the existing post_thread → record_posted path.

**Tech Stack:** Python 3.12, `requests` (already in the scraper's Lambda deps), AWS SAM. No new dependencies, no API keys, no new IAM (outbound HTTPS needs none).

## Global Constraints (from spec §5)

- **Buzz never blocks a run.** Every source fetch is individually try/excepted; the whole enrichment in the handler is try/excepted. If everything fails, behavior is byte-identical Phase 1 LLM-only scoring. `fetch_buzz`/`apply_buzz` never raise out.
- **Blend:** `composite = W_RELEVANCE*rel + W_NOVELTY*nov + (W_HOOK − W_BUZZ)*hook + W_BUZZ*buzz`. `W_BUZZ` from env `SCORING_W_BUZZ`, default `W_HOOK / 2` (= 0.125 with stock weights). `W_BUZZ` must not exceed `W_HOOK`.
- **No signal ≠ zero buzz:** a candidate with no source data keeps its pure LLM composite and gets `buzz: None` (never scored down for obscurity).
- **Raw per-source values stored:** each sidecar row and each ledger entry carries `buzz_raw` (dict of per-source counts, or None) and `buzz` (blended 0–10, or None).
- **Free tier only:** no API keys, no paid endpoints (Semantic Scholar unauthenticated tier; HF and HN public JSON).
- **HTTP budget:** per-call timeout `BUZZ_HTTP_TIMEOUT_S` (default 3s); total wall budget `BUZZ_WALL_BUDGET_S` (default 20s) — the per-candidate HN loop stops fetching when the budget is spent (remaining candidates simply lack HN data).
- **Kill switch:** env `BUZZ_ENABLED` (template parameter). When false: zero HTTP calls, Phase 1 behavior exactly.
- **The min_score gate operates on the blended composite** — buzz enrichment and re-sort happen before `max_composite`, the sidecar write, and the gate check.
- Tests are dependency-free scripts: `uv run python tests/<file>.py`, NOT pytest. All 35 existing tests (17 fixes + 18 content_engine) stay green.
- All work on branch `feat/content-engine-phase15` off main (`9714ff7f`, v0.8.0).
- **Deploy (Task 6) is GATED:** per spec, buzz "ships only after Phase 1's LLM-only scoring is proven live" — do not execute Task 6 before the Mon 2026-07-06 16:00 UTC scheduled run is verified (ledger provenance fields present).
- The pipeline keeps the one-article invariant (`max_new_articles: 1` semantics preserved).

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `lambda/layers/common/python/utils/buzz.py` | Create | Buzz fetchers, normalization, blend, apply_buzz re-ranker |
| `tests/test_buzz.py` | Create | All buzz unit tests (module-level; new file — content_engine file already ~500 lines) |
| `tests/stubs.py` | Modify | Fake `requests` grows a routable GET/POST recorder (`FAKE_HTTP`) |
| `lambda/scraper/scraper_lambda.py` | Modify | Buzz enrichment between scoring and sidecar/gate |
| `tests/test_content_engine.py` | Modify | Handler-level buzz tests (re-rank, degrade, kill switch) |
| `lambda/layers/common/python/utils/post_to_twitter.py` | Modify | `post_thread` return carries `buzz` + `buzz_raw` |
| `lambda/poster/poster_lambda.py` | Modify | Ledger entry stores `buzz` + `buzz_raw` |
| `template.yaml` | Modify | `BuzzEnabled` param, buzz envs, scoring-weight envs (closes v0.8.0 review deferral), scraper `Timeout: 180` |
| `docs/FIX_NOTES.md` | Modify | Known-remaining refresh (lifecycle applied; weights now template-tunable) |

---

### Task 1: Buzz module — pure functions (normalize, blend, re-rank)

**Files:**
- Create: `lambda/layers/common/python/utils/buzz.py`
- Create: `tests/test_buzz.py`

**Interfaces:**
- Consumes: `utils.scoring.composite(scores) -> float`, `utils.scoring.arxiv_id(url) -> str`, `utils.scoring.W_HOOK` (Phase 1).
- Produces (later tasks rely on these exact names):
  - `buzz_score(raw: dict) -> float | None` — raw is a dict with any of `hf_upvotes`, `hn_points`, `hn_comments`, `s2_citations` (ints); None when none present.
  - `blend_composite(scores: dict, buzz: float | None) -> float` — rounded to 2 decimals.
  - `apply_buzz(scored: list[dict], buzz_map: dict[str, dict]) -> list[dict]` — NEW list, composite-desc.
  - Module constants: `W_BUZZ`, `CAPS`, `BUZZ_ENABLED`, `HTTP_TIMEOUT_S`, `WALL_BUDGET_S`, URLs `HF_DAILY_URL`, `HN_SEARCH_URL`, `S2_BATCH_URL`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_buzz.py`:

```python
# tests/test_buzz.py — Phase 1.5 (buzz signal) tests.
#   uv run python tests/test_buzz.py
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


print("[1] buzz: normalization + blend (pure)")

from utils import buzz  # noqa: E402


def test_buzz_score_none_without_signal():
    assert buzz.buzz_score({}) is None, "empty raw must be None"
    assert buzz.buzz_score({"hf_upvotes": None}) is None, "None values must not count"


def test_buzz_score_saturates_at_cap():
    v = buzz.buzz_score({"hf_upvotes": buzz.CAPS["hf_upvotes"]})
    assert v == 10.0, f"upvotes at cap must score 10, got {v}"
    small = buzz.buzz_score({"hf_upvotes": 1})
    big = buzz.buzz_score({"hf_upvotes": 50})
    assert 0 < small < big < 10, f"log curve must be monotonic: {small}, {big}"


def test_buzz_score_takes_strongest_source():
    v = buzz.buzz_score({"hf_upvotes": 1, "hn_points": buzz.CAPS["hn_points"]})
    assert v == 10.0, f"strongest source wins, got {v}"


def test_blend_composite_math():
    scores = {"builder_relevance": 8.0, "novelty": 6.0, "hook_potential": 4.0}
    # LLM-only: 0.5*8 + 0.25*6 + 0.25*4 = 6.5
    assert buzz.blend_composite(scores, None) == 6.5
    # With buzz 10: 0.5*8 + 0.25*6 + 0.125*4 + 0.125*10 = 7.25
    assert buzz.blend_composite(scores, 10.0) == 7.25
    # Buzz equal to hook is a no-op: blend == composite
    assert buzz.blend_composite(scores, 4.0) == 6.5


def test_apply_buzz_reranks_and_annotates():
    scored = [
        {"url": "https://arxiv.org/abs/2607.00001", "title": "A",
         "scores": {"builder_relevance": 8.0, "novelty": 6.0, "hook_potential": 4.0},
         "composite": 6.5},
        {"url": "https://arxiv.org/abs/2607.00002", "title": "B",
         "scores": {"builder_relevance": 7.0, "novelty": 6.0, "hook_potential": 6.0},
         "composite": 6.5},
    ]
    buzz_map = {"2607.00002": {"hn_points": buzz.CAPS["hn_points"]}}  # B gets buzz 10
    out = buzz.apply_buzz(scored, buzz_map)
    assert out[0]["title"] == "B", f"buzzed candidate must lead, got {out[0]['title']}"
    # B: 0.5*7 + 0.25*6 + 0.125*6 + 0.125*10 = 7.0
    assert out[0]["composite"] == 7.0, f"blended composite wrong: {out[0]['composite']}"
    assert out[0]["buzz"] == 10.0 and out[0]["buzz_raw"] == {"hn_points": buzz.CAPS["hn_points"]}
    assert out[1]["buzz"] is None and out[1]["buzz_raw"] is None, "no-signal candidate stays LLM-only"
    assert out[1]["composite"] == 6.5, "no-signal composite untouched"
    assert scored[0]["title"] == "A", "input list must not be mutated"


check("buzz_score None without signal", test_buzz_score_none_without_signal)
check("buzz_score saturates at cap", test_buzz_score_saturates_at_cap)
check("buzz_score takes strongest source", test_buzz_score_takes_strongest_source)
check("blend_composite math", test_blend_composite_math)
check("apply_buzz re-ranks + annotates", test_apply_buzz_reranks_and_annotates)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
```

Note: `FAKE_HTTP` does not exist in `tests/stubs.py` yet — Task 2 adds it. For THIS task only, temporarily import just `install_stubs` (`from stubs import install_stubs`) and add the `FAKE_HTTP` import in Task 2. Keep the file header exactly as above otherwise.

- [ ] **Step 2: Run to verify failure**

Run: `uv run python tests/test_buzz.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'utils.buzz'` (import error before any test runs).

- [ ] **Step 3: Implement the pure parts** — create `lambda/layers/common/python/utils/buzz.py`:

```python
# utils/buzz.py — free attention signals blended into scoring (Phase 1.5).
#
# Three public sources ground hook_potential in observed attention: Hugging
# Face Daily Papers (upvotes), Hacker News via Algolia (points + comments),
# Semantic Scholar (early citations). Everything is best-effort: any source
# failing degrades to LLM-only scoring; fetch_buzz/apply_buzz never raise.

import math
import os
import time

import requests

from utils.logger import get_logger
from utils.scoring import W_HOOK, arxiv_id, composite

logger = get_logger("buzz")

BUZZ_ENABLED = os.getenv("BUZZ_ENABLED", "true").lower() == "true"
# Cedes this much of the hook weight to observed buzz. Must stay <= W_HOOK.
W_BUZZ = float(os.getenv("SCORING_W_BUZZ", str(W_HOOK / 2)))
HTTP_TIMEOUT_S = float(os.getenv("BUZZ_HTTP_TIMEOUT_S", "3"))
WALL_BUDGET_S = float(os.getenv("BUZZ_WALL_BUDGET_S", "20"))

HF_DAILY_URL = "https://huggingface.co/api/daily_papers"
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"

# Saturation caps: a source at its cap contributes a full 10.
CAPS = {"hf_upvotes": 100, "hn_points": 500, "hn_comments": 200, "s2_citations": 50}


def _saturate(value, cap):
    """0..10 on a log curve that reaches 10 at `cap`."""
    v = max(0.0, float(value))
    return min(10.0, 10.0 * math.log1p(v) / math.log1p(cap))


def buzz_score(raw):
    """One 0-10 buzz value from raw per-source counts; the strongest source
    wins (sources are sparse — a mean would punish single-source hits).
    None when no source produced a number: no signal is not zero buzz."""
    parts = [_saturate(raw[k], CAPS[k]) for k in CAPS if raw.get(k) is not None]
    return round(max(parts), 2) if parts else None


def blend_composite(scores, buzz):
    """LLM composite with W_BUZZ of the hook weight ceded to observed buzz."""
    if buzz is None:
        return round(composite(scores), 2)
    return round(composite(scores)
                 - W_BUZZ * scores["hook_potential"] + W_BUZZ * buzz, 2)


def apply_buzz(scored, buzz_map):
    """Return a NEW composite-desc list. Candidates with an entry in buzz_map
    gain buzz_raw/buzz and a blended composite; the rest stay LLM-only."""
    out = []
    for c in scored:
        raw = buzz_map.get(arxiv_id(c["url"]))
        value = buzz_score(raw) if raw else None
        entry = {**c, "buzz_raw": raw or None, "buzz": value}
        if value is not None:
            entry["composite"] = blend_composite(c["scores"], value)
        out.append(entry)
    out.sort(key=lambda c: c["composite"], reverse=True)
    return out
```

(The fetchers come in Task 2 — this module compiles and passes Task 1's tests without them.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run python tests/test_buzz.py`
Expected: `5 passed, 0 failed`

- [ ] **Step 5: Regression + commit**

Run: `uv run python tests/test_fixes.py` (17 green) and `uv run python tests/test_content_engine.py` (18 green).

```bash
git add lambda/layers/common/python/utils/buzz.py tests/test_buzz.py
git commit -m "feat: buzz module pure parts — saturation, blend, re-rank"
```

---

### Task 2: Buzz fetchers + routable fake requests

**Files:**
- Modify: `lambda/layers/common/python/utils/buzz.py` (append fetchers)
- Modify: `tests/stubs.py` (fake `requests` grows `FAKE_HTTP` router)
- Modify: `tests/test_buzz.py` (append section [2])

**Interfaces:**
- Consumes: Task 1's module constants and `buzz_score`.
- Produces: `fetch_buzz(candidates: list[dict]) -> dict[str, dict]` — keys are arXiv ids, values are raw dicts with any of the four count fields; only ids with ≥1 datum appear. `tests.stubs.FAKE_HTTP` with `.routes: dict[str, dict|Exception]` (URL substring → JSON payload or exception to raise), `.calls: list[tuple[str, str]]`, `.reset()`.

- [ ] **Step 1: Upgrade the fake `requests` in `tests/stubs.py`**

Replace the current block (around lines 160–168):

```python
    requests = types.ModuleType("requests")

    class _Resp:
        def raise_for_status(self):
            pass

    requests.post = lambda *a, **k: _Resp()
    requests.exceptions = types.SimpleNamespace(RequestException=Exception)
    sys.modules["requests"] = requests
```

with a module-level router (define `_HttpResp`/`FakeHttp`/`FAKE_HTTP` at module level next to the other fakes like `FAKE_S3`, and wire it inside `install_stubs`):

```python
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
```

and inside `install_stubs`, the requests wiring becomes:

```python
    requests = types.ModuleType("requests")
    requests.get = FAKE_HTTP.get
    requests.post = FAKE_HTTP.post
    requests.exceptions = types.SimpleNamespace(RequestException=Exception)
    sys.modules["requests"] = requests
```

The Make-webhook `requests.post` in existing code hits the unrouted default (empty 200) — all 35 existing tests must stay green.
Also update `tests/test_buzz.py`'s import line to `from stubs import install_stubs, FAKE_HTTP` (Task 1 left it as install_stubs only).

- [ ] **Step 2: Write the failing tests** — append to `tests/test_buzz.py` before the summary lines:

```python
print("[2] buzz: fetchers (best-effort, budget-capped)")

CANDS = [
    {"url": "https://arxiv.org/abs/2607.00001", "title": "A"},
    {"url": "https://arxiv.org/abs/2607.00002", "title": "B"},
]


def test_fetch_buzz_happy_path():
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["huggingface.co/api/daily_papers"] = [
        {"paper": {"id": "2607.00001", "upvotes": 40}},
        {"paper": {"id": "9999.99999", "upvotes": 7}},   # not ours — ignored
    ]
    FAKE_HTTP.routes["semanticscholar.org"] = [
        {"citationCount": 3}, {"citationCount": 0},
    ]
    FAKE_HTTP.routes["hn.algolia.com"] = {
        "hits": [{"points": 120, "num_comments": 45}, {"points": 10, "num_comments": 2}],
    }
    out = buzz.fetch_buzz(CANDS)
    assert out["2607.00001"]["hf_upvotes"] == 40
    assert out["2607.00001"]["s2_citations"] == 3
    assert out["2607.00001"]["hn_points"] == 130, out["2607.00001"]
    assert out["2607.00001"]["hn_comments"] == 47
    assert out["2607.00002"]["s2_citations"] == 0
    assert "hf_upvotes" not in out["2607.00002"]


def test_fetch_buzz_source_failure_isolated():
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["huggingface.co"] = Exception("HF down")
    FAKE_HTTP.routes["semanticscholar.org"] = Exception("S2 down")
    FAKE_HTTP.routes["hn.algolia.com"] = {"hits": [{"points": 50, "num_comments": 5}]}
    out = buzz.fetch_buzz(CANDS)  # must not raise
    assert out["2607.00001"] == {"hn_points": 50, "hn_comments": 5}, out


def test_fetch_buzz_all_down_returns_empty():
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["huggingface.co"] = Exception("down")
    FAKE_HTTP.routes["semanticscholar.org"] = Exception("down")
    FAKE_HTTP.routes["hn.algolia.com"] = Exception("down")
    assert buzz.fetch_buzz(CANDS) == {}


def test_fetch_buzz_wall_budget_skips_hn():
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["hn.algolia.com"] = {"hits": [{"points": 50, "num_comments": 5}]}
    old = buzz.WALL_BUDGET_S
    buzz.WALL_BUDGET_S = -1.0   # budget already spent
    try:
        out = buzz.fetch_buzz(CANDS)
    finally:
        buzz.WALL_BUDGET_S = old
    hn_calls = [c for c in FAKE_HTTP.calls if "hn.algolia" in c[1]]
    assert not hn_calls, f"HN must be skipped on exhausted budget: {hn_calls}"
    assert out == {}, "no other source routed → empty map"


check("fetch_buzz happy path", test_fetch_buzz_happy_path)
check("fetch_buzz source failure isolated", test_fetch_buzz_source_failure_isolated)
check("fetch_buzz all-down returns empty", test_fetch_buzz_all_down_returns_empty)
check("fetch_buzz wall budget skips HN", test_fetch_buzz_wall_budget_skips_hn)
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run python tests/test_buzz.py`
Expected: 5 pass, 4 FAIL with `AttributeError: module 'utils.buzz' has no attribute 'fetch_buzz'`.

- [ ] **Step 4: Implement the fetchers** — append to `lambda/layers/common/python/utils/buzz.py`:

```python
def _fetch_hf(ids):
    """One call: today's HF Daily Papers list -> {arxiv_id: upvotes} for ids we hold."""
    resp = requests.get(HF_DAILY_URL, timeout=HTTP_TIMEOUT_S)
    resp.raise_for_status()
    wanted = set(ids)
    out = {}
    for row in resp.json():
        paper = row.get("paper") or {}
        pid = str(paper.get("id"))
        if pid in wanted:
            out[pid] = int(paper.get("upvotes") or 0)
    return out


def _fetch_s2(ids):
    """One batch call -> {arxiv_id: citationCount}. S2 returns one row per
    requested id, in order; null rows mean the paper is unknown to S2."""
    resp = requests.post(
        S2_BATCH_URL, params={"fields": "citationCount"},
        json={"ids": [f"ARXIV:{i}" for i in ids]}, timeout=HTTP_TIMEOUT_S)
    resp.raise_for_status()
    out = {}
    for i, row in zip(ids, resp.json()):
        if isinstance(row, dict) and row.get("citationCount") is not None:
            out[i] = int(row["citationCount"])
    return out


def _fetch_hn(paper_id):
    """(points, comments) summed across HN submissions mentioning the id;
    (None, None) when HN has never seen it."""
    resp = requests.get(HN_SEARCH_URL, params={"query": paper_id},
                        timeout=HTTP_TIMEOUT_S)
    resp.raise_for_status()
    hits = resp.json().get("hits", [])
    if not hits:
        return None, None
    return (sum(int(h.get("points") or 0) for h in hits),
            sum(int(h.get("num_comments") or 0) for h in hits))


def fetch_buzz(candidates):
    """Best-effort raw buzz per candidate: {arxiv_id: {source: count, ...}}.
    Sources are isolated (one failing never hides another); the per-candidate
    HN loop stops when WALL_BUDGET_S is spent. Only ids with data appear."""
    ids = [arxiv_id(c["url"]) for c in candidates]
    raw = {i: {} for i in ids}
    started = time.monotonic()

    try:
        for i, upvotes in _fetch_hf(ids).items():
            raw[i]["hf_upvotes"] = upvotes
    except Exception as e:
        logger.warning("buzz: HF daily papers unavailable: %s", e)

    try:
        for i, citations in _fetch_s2(ids).items():
            raw[i]["s2_citations"] = citations
    except Exception as e:
        logger.warning("buzz: Semantic Scholar unavailable: %s", e)

    skipped = 0
    for i in ids:
        if time.monotonic() - started > WALL_BUDGET_S:
            skipped += 1
            continue
        try:
            points, comments = _fetch_hn(i)
            if points is not None:
                raw[i]["hn_points"] = points
                raw[i]["hn_comments"] = comments
        except Exception as e:
            logger.warning("buzz: HN lookup failed for %s: %s", i, e)
    if skipped:
        logger.warning("buzz: wall budget exhausted; skipped %d HN lookups", skipped)

    return {i: r for i, r in raw.items() if r}
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run python tests/test_buzz.py`
Expected: `9 passed, 0 failed`

- [ ] **Step 6: Regression + commit**

Run: `uv run python tests/test_fixes.py` (17 green) and `uv run python tests/test_content_engine.py` (18 green) — the stubs change touches every test file's fake requests.

```bash
git add lambda/layers/common/python/utils/buzz.py tests/stubs.py tests/test_buzz.py
git commit -m "feat: buzz fetchers (HF/HN/S2, best-effort, budget-capped) + routable fake requests"
```

---

### Task 3: Scraper integration — blend before sidecar and gate

**Files:**
- Modify: `lambda/scraper/scraper_lambda.py` (imports + the scoring-success block, currently lines ~165–181)
- Modify: `tests/test_content_engine.py` (append handler buzz tests before the summary lines)

**Interfaces:**
- Consumes: `buzz.BUZZ_ENABLED`, `buzz.fetch_buzz`, `buzz.apply_buzz` (Tasks 1–2); existing handler structure (Phase 1 Task 6).
- Produces: sidecar rows and selected articles now carry `buzz`/`buzz_raw`; the gate operates on blended composites. Response body unchanged in shape.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_content_engine.py` (follow the existing handler-test pattern in the file for the ScraperClient/scrape_lanes monkeypatch, FAKE_S3 reset, and env values; reuse its scored-candidates fixture style). Import `FAKE_HTTP` at the top where `FAKE_S3` etc. are imported:

```python
print("[8] scraper: buzz enrichment")


def test_buzz_reranks_selection():
    # Two candidates; LLM scoring puts A first. Route huge HN buzz to B only:
    # blended composite must flip the order and the handler must select B.
    FAKE_HTTP.reset()
    FAKE_HTTP.routes["hn.algolia.com"] = {"hits": [{"points": 500, "num_comments": 100}]}
    # ^ every HN lookup returns this — give A no advantage by routing HF/S2 dead:
    FAKE_HTTP.routes["huggingface.co"] = Exception("down")
    FAKE_HTTP.routes["semanticscholar.org"] = Exception("down")
    ...
    # (fixture: FAKE_BEDROCK.scoring_response gives A hook 9 / B hook 3 with
    #  A composite marginally above B; with both getting buzz 10, B's lower
    #  hook cedes more weight — assert per the blend math which article wins,
    #  computing expected composites with the same formula as utils.buzz.)
```

**Write these three tests concretely** (the implementer writes real fixtures, not the sketch above — compute exact expected composites by hand in the test body as comments):
1. `test_buzz_reranks_selection` — craft `FAKE_BEDROCK.scoring_response` so LLM order is [A, B], route buzz so blended order is [B, A]; invoke the handler with `min_score: 0, max_new_articles: 1, skip_memory: true, dry-run-safe env`; assert the uploaded pipeline file contains B, and the sidecar rows carry `buzz` and `buzz_raw` keys with B's buzz non-null.
2. `test_buzz_failure_keeps_llm_order` — route ALL three buzz hosts to `Exception`; assert handler still 200, selected article is A (LLM order), sidecar rows have `buzz: None`, and `scoring_used` true in response.
3. `test_buzz_disabled_no_http` — monkeypatch `scraper_lambda` 's imported flag (`import utils.buzz as buzz_mod; old = buzz_mod.BUZZ_ENABLED; buzz_mod.BUZZ_ENABLED = False` — see Step 3 for why the handler must read the flag from the module at call time) plus `FAKE_HTTP.reset()`; run the handler; assert `FAKE_HTTP.calls` contains no huggingface/hn/semanticscholar URLs and selection matches LLM order. Restore in `finally`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run python tests/test_content_engine.py`
Expected: 18 pass, 3 FAIL (no buzz fields in sidecar; selection unchanged; HTTP calls absent-check may pass trivially — assert buzz keys in sidecar rows so it genuinely fails pre-implementation).

- [ ] **Step 3: Implement** — in `lambda/scraper/scraper_lambda.py`:

Import (top of file, next to the scoring import):

```python
import utils.buzz as buzz_mod
```

(Module-object access — `buzz_mod.BUZZ_ENABLED`, `buzz_mod.fetch_buzz(...)` — so tests can monkeypatch the flag; a `from` import would freeze the boolean at import time.)

Modify the scoring-success block (currently):

```python
        scored = score_candidates(candidates)
        scoring_used = True
        _reset_failure_streak()
        max_composite = scored[0]["composite"]
        _write_sidecar(scored)
```

to:

```python
        scored = score_candidates(candidates)
        scoring_used = True
        _reset_failure_streak()
        if buzz_mod.BUZZ_ENABLED:
            try:
                buzz_map = buzz_mod.fetch_buzz(scored)
                scored = buzz_mod.apply_buzz(scored, buzz_map)
                logger.info("Buzz blended for %d/%d candidates.",
                            sum(1 for c in scored if c.get("buzz") is not None),
                            len(scored))
            except Exception as e:
                logger.warning(f"Buzz enrichment failed; LLM-only order kept: {e}")
        max_composite = scored[0]["composite"]
        _write_sidecar(scored)
```

Nothing else in the handler changes — the gate lines below already read `scored[0]["composite"]`/filter on `composite`, which is now the blended value.

- [ ] **Step 4: Run to verify pass**

Run: `uv run python tests/test_content_engine.py`
Expected: `21 passed, 0 failed`

- [ ] **Step 5: Regression + commit**

Run: `uv run python tests/test_fixes.py` (17 green) and `uv run python tests/test_buzz.py` (9 green).

```bash
git add lambda/scraper/scraper_lambda.py tests/test_content_engine.py
git commit -m "feat: blend buzz into selection before sidecar and gate (best-effort)"
```

---

### Task 4: Buzz provenance to the ledger

**Files:**
- Modify: `lambda/layers/common/python/utils/post_to_twitter.py` (the `post_thread` return dict, currently lines ~161–170)
- Modify: `lambda/poster/poster_lambda.py` (the `record_posted` entry dict, currently lines ~107–119)
- Modify: `tests/test_content_engine.py` (extend the two existing provenance tests)

**Interfaces:**
- Consumes: articles now carry `buzz`/`buzz_raw` (Task 3); existing `post_thread` → `on_posted(metadata)` → `record_posted` path (Phase 1 Task 7).
- Produces: ledger entries gain `buzz` (float|None) and `buzz_raw` (dict|None).

- [ ] **Step 1: Extend the failing tests** — in `tests/test_content_engine.py`, find the two Phase 1 provenance tests (`test_ledger_entry_carries_provenance`, `test_post_thread_returns_provenance`). Add `"buzz": 7.5, "buzz_raw": {"hn_points": 120}` to their article fixtures, and add assertions:

```python
    # in test_post_thread_returns_provenance:
    assert md["buzz"] == 7.5 and md["buzz_raw"] == {"hn_points": 120}
    # in test_ledger_entry_carries_provenance (on the saved ledger entry):
    assert entry["buzz"] == 7.5 and entry["buzz_raw"] == {"hn_points": 120}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python tests/test_content_engine.py`
Expected: the two extended tests FAIL with `KeyError: 'buzz'`.

- [ ] **Step 3: Implement** — two dict additions:

`post_to_twitter.py` return dict gains:

```python
        "buzz": article.get("buzz"),
        "buzz_raw": article.get("buzz_raw"),
```

`poster_lambda.py` `record_posted` entry gains:

```python
                "buzz": metadata.get("buzz"),
                "buzz_raw": metadata.get("buzz_raw"),
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run python tests/test_content_engine.py`
Expected: `21 passed, 0 failed`

- [ ] **Step 5: Regression + commit**

Run: `uv run python tests/test_fixes.py` (17 green — it exercises post_thread; `.get()` keeps unbuzzed articles None-safe).

```bash
git add lambda/layers/common/python/utils/post_to_twitter.py lambda/poster/poster_lambda.py tests/test_content_engine.py
git commit -m "feat: buzz provenance into the posted ledger"
```

---

### Task 5: Template envs + docs refresh

**Files:**
- Modify: `template.yaml` (ScraperFunction env + Parameters + Timeout)
- Modify: `docs/FIX_NOTES.md` (known-remaining refresh)

**Interfaces:**
- Consumes: env names from Tasks 1–3: `BUZZ_ENABLED`, `SCORING_W_BUZZ`, `BUZZ_HTTP_TIMEOUT_S`, `BUZZ_WALL_BUDGET_S`; Phase 1 names `SCORING_W_RELEVANCE`, `SCORING_W_NOVELTY`, `SCORING_W_HOOK`, `SCORING_MAX_CANDIDATES` (read by `utils/scoring.py` but absent from the template — closes the v0.8.0 final-review deferral).
- Produces: deployable template for Task 6.

- [ ] **Step 1: Parameters** — add after `ScoredOutputPrefix`:

```yaml
  BuzzEnabled:
    Type: String
    Default: "true"
    AllowedValues: ["true", "false"]
    Description: Kill switch for Phase 1.5 buzz enrichment (no redeploy of code needed).
```

- [ ] **Step 2: ScraperFunction environment** — add to its `Environment.Variables`:

```yaml
          BUZZ_ENABLED: !Ref BuzzEnabled
          SCORING_W_BUZZ: "0.125"
          BUZZ_HTTP_TIMEOUT_S: "3"
          BUZZ_WALL_BUDGET_S: "20"
          SCORING_W_RELEVANCE: "0.5"
          SCORING_W_NOVELTY: "0.25"
          SCORING_W_HOOK: "0.25"
          SCORING_MAX_CANDIDATES: "40"
```

- [ ] **Step 3: Scraper timeout** — confirm `ScraperFunction` `Timeout` ≥ 180; if lower (or absent → 3s default!), set:

```yaml
      Timeout: 180
```

(3 lane fetches + one Bedrock scoring call + up to 20s buzz budget needs generous headroom.)

- [ ] **Step 4: FIX_NOTES refresh** — in `docs/FIX_NOTES.md` "Known remaining items": mark the lifecycle line done (`applied 2026-07-03: scraper 14d / summarizer 14d / scored 30d`) and remove the "weights not template-tunable" gap if listed; add a line: `Phase 1.5 buzz deployed behind BuzzEnabled parameter — flip to "false" to restore pure Phase 1 selection without a code change.`

- [ ] **Step 5: Validate + commit**

Run: `sam validate --lint` — must pass. Run both Python suites once (no code change expected, but the template task must not break the tree): `uv run python tests/test_fixes.py`, `uv run python tests/test_content_engine.py`, `uv run python tests/test_buzz.py`.

```bash
git add template.yaml docs/FIX_NOTES.md
git commit -m "infra: buzz envs + kill switch param; scoring weights template-tunable; scraper timeout 180"
```

---

### Task 6: Deploy + live verification (controller-run — NOT delegated)

**GATE: do not start this task until the Mon 2026-07-06 16:00 UTC scheduled run has been verified** (newest `posted_library.json` entry has non-null `builder_relevance`, `novelty`, `hook_potential`, `composite`, `query_source`). Spec §5: buzz ships only after Phase 1's LLM-only scoring is proven live.

**Files:** none (operational)

- [ ] **Step 1: Build + changeset + execute** (established two-step flow):

```bash
export AWS_PROFILE=pipeline-admin
cd ~/projects/ai-news-pipeline
sam build
sam deploy --no-execute-changeset   # inspect changeset table
aws cloudformation execute-change-set --change-set-name <ARN from output>
aws cloudformation wait stack-update-complete --stack-name ai-research-pipeline
```

Expected changeset: Modify ScraperFunction (+ new layer version, Timeout, envs); no IAM changes.

- [ ] **Step 2: Dry-run E2E with buzz** (manual runs use dry_run per spec):

```bash
aws lambda invoke --function-name ai-research-pipeline \
  --cli-binary-format raw-in-base64-out \
  --payload '{"scrape_limit":15,"max_new_articles":1,"chunk_size":1,"skip_memory":true,"dry_run":true}' \
  --cli-read-timeout 900 /tmp/p15_verify.json && cat /tmp/p15_verify.json
```

Expected: 200, one article. Then verify:
- Scraper log shows `Buzz blended for N/M candidates.` (N may be 0 on a quiet day — the LINE must exist; if it reads `Buzz enrichment failed`, investigate before proceeding).
- Newest `scored_candidates_*.json` under `output/scored/` — every row has `buzz` and `buzz_raw` keys; spot-check one candidate with non-null buzz against the public HF/HN pages.
- Wall-clock ≤ 750s budget (expect ≤ 90s: Phase 1's 41s + buzz budget).

- [ ] **Step 3: Kill-switch check** — redeploy nothing; invoke with the parameter as-is but confirm the code path: temporarily invoke the SCRAPER directly with `dry_run` semantics is not available — instead verify the switch statically: `aws lambda get-function-configuration --function-name ai-research-scraper --query 'Environment.Variables.BUZZ_ENABLED'` → `"true"`. (Flipping it to `"false"` is a one-parameter redeploy documented in FIX_NOTES; do not exercise it live unless buzz misbehaves.)

- [ ] **Step 4: Version, tag, push, merge** (gated by Steps 1–3):

```bash
# bump pyproject version to 0.9.0, run: uv lock
git add -A && git commit -m "chore: v0.9.0 — content engine phase 1.5 (buzz signal) deployed"
git tag -a v0.9.0 -m "Content engine Phase 1.5: free buzz signal (HF/HN/S2) blended into scoring"
git push origin feat/content-engine-phase15 v0.9.0   # (PAT-inline push per repo convention)
# merge to main after final whole-branch review, per SDD flow
```

**Async post-deploy checklist (does NOT block the tag):** after the next scheduled run, confirm the newest ledger entry carries `buzz`/`buzz_raw` (may legitimately be None on a no-buzz day — the KEYS must exist).

---

## Self-Review

- **Spec coverage (§5):** three sources ✓ (T2 fetchers); per-candidate at scoring time, batched ✓ (HF+S2 single calls, HN loop, T2); best-effort/never blocks ✓ (per-source try/except T2, handler try/except T3, kill switch T5); blend replacing half the hook weight, env-tunable ✓ (W_BUZZ default W_HOOK/2, T1); raw values in sidecar ✓ (T3 — rows carry buzz_raw pre-write) and ledger ✓ (T4); ships after Phase 1 proven live ✓ (T6 gate).
- **Placeholder scan:** Task 3 Step 1 deliberately specifies three tests behaviorally with exact assertions listed rather than full fixture code (fixtures must mirror the file's existing handler-test pattern, which the implementer reads in place; the expected-composite math is fully determined by T1's blend formula). All other code steps carry complete code. No TBDs.
- **Type consistency:** `fetch_buzz` keys = `arxiv_id(url)` strings, consumed by `apply_buzz` via the same function ✓; `buzz_raw` dict field names match `CAPS` keys everywhere (T1 tests, T2 fetchers, T4 assertions) ✓; `blend_composite` rounds to 2 decimals like Phase 1's `composite` usage ✓; env names in T5 template match the `os.getenv` names in T1 (`BUZZ_ENABLED`, `SCORING_W_BUZZ`, `BUZZ_HTTP_TIMEOUT_S`, `BUZZ_WALL_BUDGET_S`) ✓.
