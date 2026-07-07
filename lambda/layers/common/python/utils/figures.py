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
                  if "info.arxiv.org/help/license" in x["href"]
                  and "#licenses-available" in x["href"]), None)
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


def _jpeg_exif_dims(b):
    """Extract pixel dimensions from JPEG EXIF APP1 segment (0xFFE1)."""
    try:
        if b[2:4] != b"\xff\xe1":
            return None
        if b[6:10] != b"Exif":
            return None
        tiff = 12  # offset of TIFF header in b
        endian = ">" if b[tiff:tiff + 2] == b"MM" else "<"
        ifd0_off = struct.unpack(endian + "I", b[tiff + 4:tiff + 8])[0]
        ifd0 = tiff + ifd0_off
        n = struct.unpack(endian + "H", b[ifd0:ifd0 + 2])[0]
        exif_ifd_abs = None
        for idx in range(n):
            es = ifd0 + 2 + idx * 12
            if es + 12 > len(b):
                break
            tag = struct.unpack(endian + "H", b[es:es + 2])[0]
            if tag == 0x8769:
                off = struct.unpack(endian + "I", b[es + 8:es + 12])[0]
                exif_ifd_abs = tiff + off
                break
        if exif_ifd_abs is None:
            return None
        n2 = struct.unpack(endian + "H", b[exif_ifd_abs:exif_ifd_abs + 2])[0]
        w = h = None
        for idx in range(n2):
            es = exif_ifd_abs + 2 + idx * 12
            if es + 12 > len(b):
                break
            tag = struct.unpack(endian + "H", b[es:es + 2])[0]
            val_raw = b[es + 8:es + 12]
            if tag == 0xA002:
                w = struct.unpack(endian + "I", val_raw)[0]
            elif tag == 0xA003:
                h = struct.unpack(endian + "I", val_raw)[0]
        if w and h:
            return (w, h)
    except Exception:
        pass
    return None


def jpeg_dims(b):
    if b[:2] != b"\xff\xd8":
        return None
    # Try SOF markers first
    i = 2
    while i < len(b) - 9:
        if b[i] != 0xFF:
            i += 1
            continue
        marker = b[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return (w, h)
        if i + 4 > len(b):
            break
        seg_len = struct.unpack(">H", b[i + 2:i + 4])[0]
        next_i = i + 2 + seg_len
        if next_i >= len(b):
            break
        i = next_i
    # Fall back to EXIF PixelXDimension/PixelYDimension
    return _jpeg_exif_dims(b)


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
