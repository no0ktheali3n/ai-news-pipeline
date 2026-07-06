"""utils/report_html.py — Self-contained HTML report renderer.

Pure stdlib, no I/O, no external requests.
Single public function: render_report(agg, generated_at) -> str
"""
from __future__ import annotations

import html
from typing import Optional

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 Helvetica, Arial, sans-serif;
    font-size: 14px;
    color: #222;
    background: #f7f8fa;
    padding: 24px;
    max-width: 860px;
    margin: 0 auto;
}
h1 { font-size: 20px; color: #1a1a2e; margin-bottom: 4px; }
.generated { color: #888; font-size: 12px; margin-bottom: 28px; }
h2 { font-size: 15px; color: #444; border-bottom: 1px solid #ddd;
     padding-bottom: 6px; margin: 28px 0 12px; }
table { border-collapse: collapse; width: 100%; margin-bottom: 8px; }
th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
th { background: #eef0f4; font-weight: 600; font-size: 13px; }
tr:nth-child(even) { background: #f9f9fb; }
.placeholder { color: #999; font-style: italic; padding: 8px 0; }
.chart { margin-bottom: 8px; }
.prog-wrap { background: #e0e0e0; border-radius: 4px;
             height: 16px; width: 100%; max-width: 400px;
             margin-top: 8px; overflow: hidden; }
.prog-bar  { background: #4a90d9; height: 16px; border-radius: 4px; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
"""


def _fmt(val, decimals: int = 1) -> str:
    """Format a numeric value or return '—' for None."""
    if val is None:
        return "&#8212;"
    if isinstance(val, float):
        return f"{val:.{decimals}f}"
    return str(val)


def _placeholder(n_deltas: int) -> str:
    return f'<p class="placeholder">collecting data &#8212; {n_deltas} posts so far</p>'


def _follower_chart(series: list) -> str:
    """Return inline SVG polyline or empty string if fewer than 2 points."""
    if not series or len(series) < 2:
        return ""

    values = [v for _, v in series]
    min_v = min(values)
    max_v = max(values)
    n = len(values)

    points_parts = []
    for i, v in enumerate(values):
        x = round(i * 600 / (n - 1), 2)
        if max_v == min_v:
            y = 60.0
        else:
            # invert: high follower count → low y (top of chart)
            y = round(10 + (max_v - v) / (max_v - min_v) * 100, 2)
        points_parts.append(f"{x},{y}")

    points_str = " ".join(points_parts)

    svg = (
        '<div class="chart">'
        '<svg viewBox="0 0 600 120" width="600" height="120" '
        'style="background:#fff;border:1px solid #ddd;border-radius:4px;">'
        f'<polyline points="{points_str}" '
        'fill="none" stroke="#4a90d9" stroke-width="2"/>'
        "</svg>"
        "</div>"
    )
    return svg


def _section_follower_curve(series: list, n_deltas: int) -> str:
    parts = ["<h2>1. Follower Curve</h2>"]
    if not series or len(series) < 2:
        parts.append(_placeholder(n_deltas))
    else:
        parts.append(_follower_chart(series))
        parts.append(
            f"<p style='color:#666;font-size:12px;'>{len(series)} data points</p>"
        )
    return "\n".join(parts)


def _section_top_posts(deltas: list) -> str:
    parts = ["<h2>2. Top Posts by Follower &#916;</h2>"]
    n = len(deltas)
    if not deltas:
        parts.append(_placeholder(0))
        return "\n".join(parts)

    # Sort: non-None deltas descending, None deltas last
    sorted_deltas = sorted(
        deltas,
        key=lambda d: (d.get("delta") is None, -(d.get("delta") or 0)),
    )

    rows = []
    for d in sorted_deltas:
        title_raw = d.get("title") or ""
        title_esc = html.escape(title_raw)
        # Prefer thread_url (links to the tweet thread); fall back to arXiv url.
        link_url = d.get("thread_url") or d.get("url")
        if link_url:
            title_cell = f'<a href="{html.escape(link_url)}">{title_esc}</a>'
        else:
            title_cell = title_esc

        composite = _fmt(d.get("composite"), 1)
        buzz = _fmt(d.get("buzz"), 1)
        delta = _fmt(d.get("delta"), 0)
        rows.append(
            f"<tr><td>{title_cell}</td><td>{composite}</td>"
            f"<td>{buzz}</td><td>{delta}</td></tr>"
        )

    header = (
        "<table><thead><tr>"
        "<th>Title</th><th>Composite</th><th>Buzz</th><th>Follower &#916;</th>"
        "</tr></thead><tbody>"
    )
    parts.append(header + "\n".join(rows) + "</tbody></table>")
    return "\n".join(parts)


def _section_lanes(lanes: dict, n_deltas: int) -> str:
    parts = ["<h2>3. Lane Performance</h2>"]
    if not lanes:
        parts.append(_placeholder(n_deltas))
        return "\n".join(parts)

    rows = []
    for lane, stats in sorted(lanes.items()):
        posts = stats.get("posts", 0)
        avg_c = _fmt(stats.get("avg_composite"), 2)
        rows.append(f"<tr><td>{html.escape(str(lane))}</td><td>{posts}</td><td>{avg_c}</td></tr>")

    header = (
        "<table><thead><tr>"
        "<th>Lane</th><th>Posts</th><th>Avg Composite</th>"
        "</tr></thead><tbody>"
    )
    parts.append(header + "\n".join(rows) + "</tbody></table>")
    return "\n".join(parts)


def _section_buzz(buzz: dict, n_deltas: int) -> str:
    parts = ["<h2>4. Buzz vs Outcome</h2>"]
    if not buzz:
        parts.append(_placeholder(n_deltas))
        return "\n".join(parts)

    rows = []
    for key in ("buzzed", "unbuzzed"):
        b = buzz.get(key, {})
        posts = b.get("posts", 0)
        avg_d = _fmt(b.get("avg_delta"), 1)
        rows.append(f"<tr><td>{html.escape(key)}</td><td>{posts}</td><td>{avg_d}</td></tr>")

    header = (
        "<table><thead><tr>"
        "<th>Category</th><th>Posts</th><th>Avg Follower &#916;</th>"
        "</tr></thead><tbody>"
    )
    parts.append(header + "\n".join(rows) + "</tbody></table>")
    return "\n".join(parts)


def _section_runs(runs: dict, n_deltas: int) -> str:
    parts = ["<h2>5. Runs &amp; Posts</h2>"]
    if not runs:
        parts.append(_placeholder(n_deltas))
        return "\n".join(parts)

    r = runs.get("runs", 0)
    p = runs.get("posts", 0)
    partials = runs.get("partials", 0)
    rows = [
        f"<tr><td>Runs</td><td>{r}</td></tr>",
        f"<tr><td>Posts</td><td>{p}</td></tr>",
        f"<tr><td>Partials</td><td>{partials}</td></tr>",
    ]
    header = (
        "<table><thead><tr>"
        "<th>Metric</th><th>Value</th>"
        "</tr></thead><tbody>"
    )
    parts.append(header + "\n".join(rows) + "</tbody></table>")
    return "\n".join(parts)


def _section_milestone(milestone: Optional[dict], n_deltas: int) -> str:
    parts = ["<h2>6. Milestone</h2>"]
    if not milestone:
        parts.append(_placeholder(n_deltas))
        return "\n".join(parts)

    target = milestone.get("target", 500)
    current = milestone.get("current")

    if not isinstance(current, int):
        parts.append("<p>not yet captured</p>")
        return "\n".join(parts)

    pct = min(100, round(current / target * 100)) if target else 100
    parts.append(f"<p>{current} / {target} followers</p>")
    parts.append(
        f'<div class="prog-wrap">'
        f'<div class="prog-bar" style="width:{pct}%;"></div>'
        f"</div>"
    )
    return "\n".join(parts)


def render_report(agg: dict, generated_at: str) -> str:
    """Render a self-contained HTML report from aggregated pipeline data.

    Parameters
    ----------
    agg:
        Dict with keys: series, deltas, lanes, buzz, runs, milestone.
        All keys are optional — missing/empty produces placeholder sections.
    generated_at:
        ISO timestamp string shown in the report header.

    Returns
    -------
    str
        A complete, self-contained HTML document (no external resources).
    """
    series = agg.get("series") or []
    deltas = agg.get("deltas") or []
    lanes = agg.get("lanes") or {}
    buzz = agg.get("buzz") or {}
    runs = agg.get("runs") or {}
    milestone = agg.get("milestone") or {}

    n_deltas = len(deltas)

    sections = [
        _section_follower_curve(series, n_deltas),
        _section_top_posts(deltas),
        _section_lanes(lanes, n_deltas),
        _section_buzz(buzz, n_deltas),
        _section_runs(runs, n_deltas),
        _section_milestone(milestone, n_deltas),
    ]

    body = "\n\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ai-research-pipeline &#8212; weekly report</title>
<style>
{_CSS}
</style>
</head>
<body>
<h1>ai-research-pipeline &#8212; weekly report</h1>
<p class="generated">Generated: {html.escape(generated_at)}</p>

{body}
</body>
</html>"""
