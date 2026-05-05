from pathlib import Path
import sys
from pathlib import Path

# ensure repo root is on sys.path so we can import csma_ca_sim
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from csma_ca_sim import (
    SimulationConfig,
    sweep_stations,
    sweep_wmin,
    run_single_experiment,
    plot_points,
    ExperimentPoint,
)

import math

OUT_DIR = Path("diagrams")
OUT_DIR.mkdir(exist_ok=True)

# 1) Create combined comparison by reading existing SVGs' data via sweep_stations
base = SimulationConfig()
# baseline points
base.rtscts = False
points_baseline = sweep_stations(base, 2, 20, 2, runs=10)
# rtscts points
base.rtscts = True
points_rts = sweep_stations(base, 2, 20, 2, runs=10)

# build combined SVG using plot_points for baseline but overlay rtscts series
# We'll generate a simple combined SVG by reusing plot_points logic but adding second series

def make_combined(points_a, points_b, title, x_label, outpath: Path):
    # Build three panels (throughput bits, collision %, mean delay ms)
    width = 980
    height = 1160
    panel_width = 880
    panel_height = 270
    left = 50
    top_margin = 80
    panel_gap = 60
    inner_left = 90
    inner_right = 35
    inner_top = 35
    inner_bottom = 48

    x_values = [p.x_value for p in points_a]
    a_bits = [p.throughput_bits_per_s for p in points_a]
    b_bits = [p.throughput_bits_per_s for p in points_b]
    a_coll = [p.collision_rate * 100 for p in points_a]
    b_coll = [p.collision_rate * 100 for p in points_b]
    a_delay = [p.mean_delay_s * 1000 for p in points_a]
    b_delay = [p.mean_delay_s * 1000 for p in points_b]

    def scale_x(idx, count):
        plot_w = panel_width - inner_left - inner_right
        if count == 1:
            return left + inner_left + plot_w / 2
        return left + inner_left + (plot_w * idx / (count - 1))

    def scale_y(value, minimum, maximum, panel_top):
        plot_h = panel_height - inner_top - inner_bottom
        if math.isclose(minimum, maximum):
            return panel_top + inner_top + plot_h / 2
        return panel_top + inner_top + (maximum - value) * plot_h / (maximum - minimum)

    def panel(panel_top, panel_title, y_label, seriesA, seriesB, colorA, colorB):
        # determine y range from both series
        y_min = min(min(seriesA), min(seriesB))
        y_max = max(max(seriesA), max(seriesB))
        if math.isclose(y_min, y_max):
            y_min = 0.0
            y_max = y_max + 1.0
        y_padding = (y_max - y_min) * 0.08 or 1.0
        y_min = max(0.0, y_min - y_padding)
        y_max = y_max + y_padding

        plot_left = left + inner_left
        plot_top = panel_top + inner_top
        plot_w = panel_width - inner_left - inner_right
        plot_h = panel_height - inner_top - inner_bottom

        elems = []
        elems.append(f'<rect x="{left}" y="{panel_top}" width="{panel_width}" height="{panel_height}" rx="18" fill="#fbfbfd" stroke="#d9dce3"/>')
        elems.append(f'<text x="{left + 18}" y="{panel_top + 26}" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" fill="#1f2937">{panel_title}</text>')
        elems.append(f'<text x="{left + 18}" y="{panel_top + 50}" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#4b5563">{y_label}</text>')

        # axes ticks
        for tick_index in range(5):
            tick_value = y_min + (y_max - y_min) * tick_index / 4
            y = scale_y(tick_value, y_min, y_max, panel_top)
            elems.append(f'<line x1="{plot_left - 5}" y1="{y}" x2="{plot_left}" y2="{y}" stroke="#334155" stroke-width="1"/>')
            elems.append(f'<text x="{plot_left - 10}" y="{y + 4}" text-anchor="end" font-family="Arial, Helvetica, sans-serif" font-size="11" fill="#475569">{tick_value:.2f}</text>')

        # x ticks
        for idx, xv in enumerate(x_values):
            x = scale_x(idx, len(x_values))
            elems.append(f'<line x1="{x}" y1="{plot_top + plot_h}" x2="{x}" y2="{plot_top + plot_h + 5}" stroke="#334155" stroke-width="1"/>')
            elems.append(f'<text x="{x}" y="{plot_top + plot_h + 20}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="11" fill="#475569">{xv}</text>')

        # series A polyline
        coords = []
        coordsB = []
        for idx, v in enumerate(seriesA):
            x = scale_x(idx, len(x_values))
            y = scale_y(v, y_min, y_max, panel_top)
            coords.append(f"{x:.2f},{y:.2f}")
        for idx, v in enumerate(seriesB):
            x = scale_x(idx, len(x_values))
            y = scale_y(v, y_min, y_max, panel_top)
            coordsB.append(f"{x:.2f},{y:.2f}")
        elems.append(f'<polyline fill="none" stroke="{colorA}" stroke-width="3" points="{" ".join(coords)}"/>')
        elems.append(f'<polyline fill="none" stroke="{colorB}" stroke-width="3" points="{" ".join(coordsB)}"/>')

        # legend
        legend_x = left + panel_width - 170
        elems.append(f'<rect x="{legend_x}" y="{panel_top + 26}" width="10" height="10" fill="{colorA}"/>')
        elems.append(f'<text x="{legend_x + 16}" y="{panel_top + 35}" font-family="Arial, Helvetica, sans-serif" font-size="11" fill="#334155">Baseline</text>')
        elems.append(f'<rect x="{legend_x}" y="{panel_top + 46}" width="10" height="10" fill="{colorB}"/>')
        elems.append(f'<text x="{legend_x + 16}" y="{panel_top + 55}" font-family="Arial, Helvetica, sans-serif" font-size="11" fill="#334155">RTS/CTS</text>')

        return "\n".join(elems)

    throughput_panel = panel(top_margin, "Throughput", "Bits/s", a_bits, b_bits, "#dc2626", "#2563eb")
    collision_panel = panel(top_margin + panel_height + panel_gap, "Collision rate", "Collision rate (%)", a_coll, b_coll, "#dc2626", "#2563eb")
    delay_panel = panel(top_margin + (panel_height + panel_gap) * 2, "Transmission delay", "Delay (ms)", a_delay, b_delay, "#059669", "#2563eb")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n  <defs>\n    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">\n      <stop offset="0%" stop-color="#f8fafc"/>\n      <stop offset="100%" stop-color="#eef2ff"/>\n    </linearGradient>\n  </defs>\n  <rect width="100%" height="100%" fill="url(#bg)"/>\n  <text x="{width/2}" y="40" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="24" font-weight="700" fill="#111827">{title}</text>\n  <text x="{width/2}" y="64" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#475569">{x_label}</text>\n  {throughput_panel}\n  {collision_panel}\n  {delay_panel}\n  <text x="{width-24}" y="{height-18}" text-anchor="end" font-family="Arial, Helvetica, sans-serif" font-size="11" fill="#64748b">Generated by csma_ca_sim.py</text>\n</svg>"""

    outpath.write_text(svg, encoding="utf-8")

# generate combined
make_combined(points_baseline, points_rts, "CSMA/CA: baseline vs RTS/CTS", "Number of stations", OUT_DIR / "combined_results.svg")
print("Wrote diagrams/combined_results.svg")

# 2) Wmin sweep
base = SimulationConfig()
points_wmin = sweep_wmin(base, 15, 63, 8, runs=10)
plot_points(points_wmin, "CSMA/CA: impact of Wmin", "Wmin", OUT_DIR / "wmin_sweep.svg")
print("Wrote diagrams/wmin_sweep.svg")

# 3) Histogram/CDF of mean delays for heavy load (N=20)
from statistics import mean

delays = []
for i in range(100):
    cfg = SimulationConfig(station_count=20, arrival_rate=50.0, simulation_time=5.0, seed=None if base.seed is None else base.seed + i)
    r = run_single_experiment(cfg)
    delays.append(r.mean_delay_s * 1000.0)  # ms

# simple histogram SVG

def make_histogram(values, outpath: Path, title: str, x_label: str, bins: int = 20):
    width = 700
    height = 400
    left = 60
    right = 20
    top = 40
    bottom = 60

    minv = min(values)
    maxv = max(values)
    if math.isclose(minv, maxv):
        minv = 0.0
        maxv = maxv + 1.0
    bin_w = (maxv - minv) / bins
    counts = [0] * bins
    for v in values:
        idx = int((v - minv) / (maxv - minv) * bins)
        if idx == bins:
            idx = bins - 1
        counts[idx] += 1
    max_count = max(counts)

    elems = []
    elems.append(f'<rect width="100%" height="100%" fill="#ffffff"/>')
    elems.append(f'<text x="{width/2}" y="20" text-anchor="middle" font-family="Arial" font-size="16">{title}</text>')

    plot_w = width - left - right
    plot_h = height - top - bottom
    for i, c in enumerate(counts):
        bx = left + plot_w * i / bins
        bw = plot_w / bins * 0.9
        bh = (c / max_count) * plot_h if max_count > 0 else 0
        by = top + (plot_h - bh)
        elems.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bw:.2f}" height="{bh:.2f}" fill="#2563eb" opacity="0.9"/>')
    # x axis labels
    for i in range(bins + 1):
        xv = minv + (maxv - minv) * i / bins
        x = left + plot_w * i / bins
        elems.append(f'<text x="{x:.2f}" y="{top + plot_h + 20}" font-family="Arial" font-size="10" text-anchor="middle">{xv:.2f}</text>')

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">{"".join(elems)}</svg>'
    outpath.write_text(svg, encoding="utf-8")

make_histogram(delays, OUT_DIR / "delay_histogram.svg", "Histogram of mean delays (N=20, 100 runs)", "Delay (ms)")
print("Wrote diagrams/delay_histogram.svg")

# CDF

def make_cdf(values, outpath: Path, title: str):
    sorted_v = sorted(values)
    n = len(sorted_v)
    width = 700
    height = 400
    left = 60
    right = 20
    top = 40
    bottom = 60
    plot_w = width - left - right
    plot_h = height - top - bottom
    minv = sorted_v[0]
    maxv = sorted_v[-1]
    elems = [f'<rect width="100%" height="100%" fill="#ffffff"/>', f'<text x="{width/2}" y="20" text-anchor="middle" font-family="Arial" font-size="16">{title}</text>']
    coords = []
    for i, v in enumerate(sorted_v):
        x = left + (v - minv) / (maxv - minv) * plot_w if not math.isclose(minv, maxv) else left + plot_w/2
        y = top + plot_h - (i / (n - 1)) * plot_h if n > 1 else top + plot_h
        coords.append(f"{x:.2f},{y:.2f}")
    elems.append(f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{" ".join(coords)}"/>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">{"".join(elems)}</svg>'
    outpath.write_text(svg, encoding="utf-8")

make_cdf(delays, OUT_DIR / "delay_cdf.svg", "CDF of mean delays (N=20, 100 runs)")
print("Wrote diagrams/delay_cdf.svg")
