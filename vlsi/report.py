"""
HTML report generator.
Embeds all charts as base64 PNGs — single self-contained .html file.
"""

import base64
import io
import os
from datetime import datetime
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _power_pie(stats: dict) -> str:
    data = stats.get("gate_type_power_uW", {})
    if not data:
        return ""
    labels = list(data.keys())
    values = list(data.values())

    fig, ax = plt.subplots(figsize=(5, 4))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct="%1.1f%%",
        startangle=90, pctdistance=0.75,
        textprops={"color": "white", "fontsize": 8}
    )
    for at in autotexts:
        at.set_fontsize(7)
    ax.set_title("Power Breakdown by Gate Type", color="white", fontsize=10)
    return _fig_to_b64(fig)


def _area_bar(stats: dict) -> str:
    data = stats.get("gate_type_area_um2", {})
    if not data:
        return ""
    types = list(data.keys())
    areas = list(data.values())

    fig, ax = plt.subplots(figsize=(6, 3.5))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")
    colors = plt.cm.viridis([i / len(types) for i in range(len(types))])  # type: ignore
    bars = ax.bar(types, areas, color=colors, edgecolor="white", linewidth=0.5)
    ax.set_xlabel("Gate Type", color="white")
    ax.set_ylabel("Area (um²)", color="white")
    ax.set_title("Area Utilization by Gate Type", color="white", fontsize=10)
    ax.tick_params(colors="white", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#444")
    # Value labels on bars
    for bar, val in zip(bars, areas):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                f"{val:.1f}", ha="center", va="bottom", color="white", fontsize=7)
    plt.tight_layout()
    return _fig_to_b64(fig)


def _slack_histogram(timing: dict) -> str:
    gate_timing = timing.get("gate_timing", [])
    if not gate_timing:
        return ""
    slacks = [g["slack_ns"] for g in gate_timing]

    fig, ax = plt.subplots(figsize=(5, 3.5))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")
    neg = [s for s in slacks if s < 0]
    pos = [s for s in slacks if s >= 0]
    if pos:
        ax.hist(pos, bins=10, color="#27ae60", edgecolor="white",
                linewidth=0.4, label="Positive slack", alpha=0.85)
    if neg:
        ax.hist(neg, bins=max(3, len(neg)), color="#e74c3c", edgecolor="white",
                linewidth=0.4, label="Negative slack (violation)", alpha=0.85)
    ax.axvline(0, color="yellow", linewidth=1, linestyle="--")
    ax.set_xlabel("Slack (ns)", color="white")
    ax.set_ylabel("Gate count", color="white")
    ax.set_title("Slack Distribution", color="white", fontsize=10)
    ax.tick_params(colors="white", labelsize=8)
    ax.legend(fontsize=7, facecolor="#16213e", labelcolor="white")
    for spine in ax.spines.values():
        spine.set_edgecolor("#444")
    plt.tight_layout()
    return _fig_to_b64(fig)


_CSS = """
body{font-family:'Segoe UI',Arial,sans-serif;background:#0f0f1a;color:#e0e0e0;margin:0;padding:20px}
h1{color:#a78bfa;border-bottom:2px solid #4c1d95;padding-bottom:8px}
h2{color:#7c3aed;margin-top:28px}
.ppa{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0}
.card{background:#1a1a2e;border:1px solid #312e81;border-radius:8px;padding:16px 20px;min-width:150px;flex:1}
.card .val{font-size:1.8em;font-weight:700;color:#a78bfa}
.card .lbl{font-size:.8em;color:#9ca3af;margin-top:4px}
.charts{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0}
.chart-box{background:#1a1a2e;border:1px solid #312e81;border-radius:8px;padding:12px}
.chart-box img{max-width:100%;border-radius:4px}
table{width:100%;border-collapse:collapse;margin-top:12px;font-size:.85em}
th{background:#312e81;padding:8px 12px;text-align:left;color:#c4b5fd}
td{padding:6px 12px;border-bottom:1px solid #1e1b4b}
tr:hover td{background:#1e1b4b}
.violation{color:#f87171;font-weight:bold}
.ok{color:#4ade80}
.badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:.75em;font-weight:700}
.badge-ok{background:#14532d;color:#4ade80}
.badge-fail{background:#450a0a;color:#f87171}
pre{background:#1a1a2e;border:1px solid #312e81;padding:14px;border-radius:6px;
    white-space:pre-wrap;font-size:.85em;color:#c4b5fd;line-height:1.5}
footer{margin-top:40px;font-size:.75em;color:#6b7280;text-align:center}
"""


def generate_report(
    stats: dict,
    timing: dict,
    floorplan_path: Optional[str],
    llm_suggestions: Optional[str],
    out_path: str,
    circuit_name: str = "Circuit",
) -> str:
    """Generate a self-contained HTML report and write to out_path."""

    power_pie_b64  = _power_pie(stats)
    area_bar_b64   = _area_bar(stats)
    slack_hist_b64 = _slack_histogram(timing)

    floorplan_b64 = ""
    if floorplan_path and os.path.exists(floorplan_path):
        with open(floorplan_path, "rb") as f:
            floorplan_b64 = base64.b64encode(f.read()).decode()

    def img_tag(b64: str, alt: str = "") -> str:
        return f'<img src="data:image/png;base64,{b64}" alt="{alt}">' if b64 else ""

    cp = timing.get("critical_path", [])
    cp_str = " → ".join(cp) if cp else "N/A"
    timing_met = timing.get("timing_met", True)
    badge = ('<span class="badge badge-ok">PASS</span>' if timing_met
             else '<span class="badge badge-fail">FAIL</span>')

    gate_rows = ""
    for g in timing.get("gate_timing", []):
        cls = "violation" if g["slack_ns"] < 0 else "ok"
        gate_rows += (
            f"<tr><td>{g['name']}</td><td>{g['type']}</td>"
            f"<td>{g['delay_ns']:.3f}</td><td>{g['arrival_ns']:.3f}</td>"
            f"<td>{g['required_ns']:.3f}</td>"
            f"<td class='{cls}'>{g['slack_ns']:.3f}</td></tr>\n"
        )

    llm_section = ""
    if llm_suggestions:
        llm_section = f"""
        <h2>LLM Optimization Suggestions</h2>
        <pre>{llm_suggestions}</pre>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VLSI Report — {circuit_name}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>VLSI Circuit Analysis Report</h1>
<p style="color:#9ca3af">Circuit: <strong style="color:#e0e0e0">{circuit_name}</strong>
&nbsp;|&nbsp; Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>

<h2>PPA Summary</h2>
<div class="ppa">
  <div class="card"><div class="val">{stats.get('total_gates', 0)}</div><div class="lbl">Total Gates</div></div>
  <div class="card"><div class="val">{stats.get('total_area_um2', 0):.1f} um²</div><div class="lbl">Total Area</div></div>
  <div class="card"><div class="val">{stats.get('total_power_uW', 0):.1f} uW</div><div class="lbl">Total Power</div></div>
  <div class="card"><div class="val">{timing.get('max_frequency_mhz', 0):.1f} MHz</div><div class="lbl">Est. Max Freq.</div></div>
  <div class="card"><div class="val">{timing.get('critical_path_ns', 0):.3f} ns</div><div class="lbl">Critical Path</div></div>
  <div class="card"><div class="val">{timing.get('wns_ns', 0):.3f} ns</div><div class="lbl">WNS {badge}</div></div>
</div>

<h2>Charts</h2>
<div class="charts">
  <div class="chart-box">{img_tag(power_pie_b64, "Power breakdown")}</div>
  <div class="chart-box">{img_tag(area_bar_b64, "Area breakdown")}</div>
  <div class="chart-box">{img_tag(slack_hist_b64, "Slack histogram")}</div>
</div>

<h2>Floorplan</h2>
{'<div class="chart-box" style="max-width:700px">' + img_tag(floorplan_b64, "Floorplan") + '</div>'
 if floorplan_b64 else '<p style="color:#6b7280">Floorplan not generated.</p>'}

<h2>Critical Path</h2>
<p style="font-family:monospace;background:#1a1a2e;padding:10px;border-radius:6px;color:#a78bfa">
{cp_str}</p>
<p>Delay: <strong>{timing.get('critical_path_ns', 0):.4f} ns</strong>
&nbsp;|&nbsp; Max Freq: <strong>{timing.get('max_frequency_mhz', 0):.2f} MHz</strong>
&nbsp;|&nbsp; Timing: {badge}</p>

<h2>Gate Timing Table</h2>
<table>
<thead><tr><th>Gate</th><th>Type</th><th>Delay (ns)</th>
<th>Arrival (ns)</th><th>Required (ns)</th><th>Slack (ns)</th></tr></thead>
<tbody>{gate_rows}</tbody>
</table>

{llm_section}

<footer>Generated by VLSI Circuit Analysis Tool &mdash; Claude-powered EDA</footer>
</body>
</html>
"""

    with open(out_path, "w") as f:
        f.write(html)

    return out_path
