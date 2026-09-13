#!/usr/bin/env python3
"""Put the route map (spiti/book/img/spiti_circuit_route_map_sept_2026.svg) on an OpenStreetMap base.

    python3 scripts/build_route_map.py [--tiles-dir DIR]

Writes, next to the source SVG:
  route-map-base.webp     OSM raster for the region (map data © OpenStreetMap contributors)
  route-map-overlay.svg   the route, with every point moved onto its real position

The book stacks the overlay on the base (see build_spiti_book.py). Needs network the first
time; tiles are cached in --tiles-dir. Re-run after editing the source SVG.

The source SVG is already roughly geographic, so it is fitted to Web Mercator with an affine
transform on the town markers below; the small leftover error at each town is then spread
smoothly (inverse-distance weighting) so every marker sits exactly on its town.
"""
import argparse
import math
import re
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "spiti" / "book" / "img"
SRC = IMG / "spiti_circuit_route_map_sept_2026.svg"
BASE, OVERLAY = IMG / "route-map-base.webp", IMG / "route-map-overlay.svg"
ZOOM = 10
MAX_W = 1400
PAPER = (243, 242, 242)
LEGEND_Y = 595          # source elements below this line are the legend, not geography

# marker centre in the source SVG -> (lat, lon)
TOWNS = {
    "Shimla": ((122, 560), (31.1048, 77.1734)), "Manali": ((127, 158), (32.2432, 77.1892)),
    "Sarahan": ((308, 415), (31.5117, 77.7937)), "Chitkul": ((500, 474), (31.3517, 78.4370)),
    "Kalpa": ((447, 407), (31.5360, 78.2573)), "Tabo": ((485, 210), (32.0934, 78.3843)),
    "Mudh": ((379, 262), (31.9594, 78.0317)), "Kaza": ((391, 164), (32.2276, 78.0710)),
    "Losar": ((310, 91), (32.4370, 77.7520)), "Chandratal": ((255, 75), (32.4833, 77.6167)),
    "Nako": ((559, 287), (31.8830, 78.6280)), "Kibber": ((375, 127), (32.3325, 78.0080)),
    "Langza": ((403, 145), (32.2690, 78.0880)), "Kunzum La": ((260, 103), (32.3960, 77.6380)),
}


def world_px(lat, lon):
    n = 256 * 2 ** ZOOM
    return ((lon + 180) / 360 * n,
            (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)


def fetch_base(x0, y0, x1, y1, tiles_dir):
    """Stitch OSM tiles covering world-pixel box [x0,x1) x [y0,y1) and crop to it."""
    tiles_dir.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = "SpitiLongReadBuilder/1.0 (one-off static map for a personal travel page)"
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int((x1 - 1) // 256), int((y1 - 1) // 256)
    mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), PAPER)
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            f = tiles_dir / f"{ZOOM}_{tx}_{ty}.png"
            if not f.exists():
                r = s.get(f"https://tile.openstreetmap.org/{ZOOM}/{tx}/{ty}.png", timeout=60)
                r.raise_for_status()
                f.write_bytes(r.content)
                time.sleep(0.4)
            mosaic.paste(Image.open(f).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
    ox, oy = tx0 * 256, ty0 * 256
    return mosaic.crop((round(x0 - ox), round(y0 - oy), round(x1 - ox), round(y1 - oy)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles-dir", type=Path, default=Path.home() / ".cache" / "spiti-osm-tiles")
    args = ap.parse_args()

    svg = re.sub(r"<metadata>.*?</metadata>", "", SRC.read_text(encoding="utf-8"), flags=re.S)
    if re.search(r'\sd="[^"]*[a-z]', svg.split("</defs>", 1)[1]):
        raise SystemExit("relative path commands are not supported; use absolute M/L/Q/C")

    # ---- fit: affine on the towns, then inverse-distance spread of what is left ----
    src = np.array([p for p, _ in TOWNS.values()], float)
    dst = np.array([world_px(*ll) for _, ll in TOWNS.values()])
    A = np.c_[src, np.ones(len(src))]
    coef = np.linalg.lstsq(A, dst, rcond=None)[0]
    resid = dst - A @ coef
    k = math.sqrt(abs(np.linalg.det(coef[:2, :2])))   # world px per source unit

    def warp(x, y):
        base = np.array([x, y, 1.0]) @ coef
        d2 = ((src - (x, y)) ** 2).sum(1)
        if d2.min() < 1e-6:
            return base + resid[d2.argmin()]
        w = 1 / d2
        return base + (w[:, None] * resid).sum(0) / w.sum()

    head, body = svg.split("</defs>", 1)
    defs = re.search(r"<defs>.*", head, re.S).group(0) + "</defs>"
    title = "".join(re.findall(r"<title>.*?</title>|<desc>.*?</desc>", head, re.S))
    body = body.rsplit("</svg>", 1)[0]

    # ---- crop: everything geographic, including label text, plus room for the legend ----
    xs, ys = [], []
    for d in re.findall(r'\sd="([^"]+)"', body):
        for x, y in re.findall(r"(-?\d+(?:\.\d+)?)[ ,]+(-?\d+(?:\.\d+)?)", d):
            X, Y = warp(float(x), float(y)); xs.append(X); ys.append(Y)
    for tag in re.findall(r"<(?:circle|text)\b[^>]*>(?:[^<]*</text>)?", body):
        a = dict(re.findall(r'\b(cx|cy|x|y|text-anchor)="([^"]*)"', tag))
        x, y = float(a.get("cx", a.get("x", 0))), float(a.get("cy", a.get("y", 0)))
        if y >= LEGEND_Y:
            continue
        X, Y = warp(x, y)
        text = re.sub(r"<[^>]+>", "", tag)
        w = len(text) * 7 * k
        left = {"end": w, "middle": w / 2}.get(a.get("text-anchor"), 0)
        xs += [X - left, X - left + w]; ys += [Y - 12 * k, Y + 12 * k]
    pad = 18 * k
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad + 46 * k
    Wu, Hu = (x1 - x0) / k, (y1 - y0) / k

    def to_out(x, y):
        X, Y = warp(x, y)
        return (X - x0) / k, (Y - y0) / k

    legend = (lambda x, y: (x - 30, y - 616 + Hu - 26))

    # ---- rewrite coordinates ----
    def path_repl(m):
        d = re.sub(r"(-?\d+(?:\.\d+)?)[ ,]+(-?\d+(?:\.\d+)?)",
                   lambda p: "%.1f %.1f" % to_out(float(p[1]), float(p[2])), m[1])
        return f' d="{d}"'

    def tag_repl(m):
        tag = m[0]
        xa, ya = ("cx", "cy") if tag.startswith("<circle") else ("x", "y")
        mx, my = re.search(rf'\b{xa}="([^"]*)"', tag), re.search(rf'\b{ya}="([^"]*)"', tag)
        if not (mx and my):
            return tag
        x, y = float(mx[1]), float(my[1])
        u, v = legend(x, y) if y >= LEGEND_Y else to_out(x, y)
        tag = re.sub(rf'\b{xa}="[^"]*"', f'{xa}="{u:.1f}"', tag, count=1)
        return re.sub(rf'\b{ya}="[^"]*"', f'{ya}="{v:.1f}"', tag, count=1)

    body = re.sub(r'\sd="([^"]+)"', path_repl, body)
    body = re.sub(r"<(?:circle|text)\b[^>]*>", tag_repl, body)

    casings = "".join(f'<path class="casing" d="{d}"/>' for d in
                      re.findall(r'<path[^>]*stroke="#378ADD"[^>]*\sd="([^"]+)"', body) +
                      re.findall(r'<path[^>]*\sd="([^"]+)"[^>]*stroke="#378ADD"', body))
    out = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {Wu:.1f} {Hu:.1f}" role="img">'
           f'{title}{defs}'
           '<style>'
           'text{paint-order:stroke fill;stroke:rgba(255,255,255,.9)!important;stroke-width:3.5px!important;'
           'stroke-linejoin:round!important}'
           '.casing{fill:none;stroke:#fff;stroke-opacity:.85;stroke-width:6.5px;stroke-linecap:round;stroke-linejoin:round}'
           '</style>'
           f'{casings}'
           f'<rect x="8" y="{Hu - 46:.1f}" width="{Wu - 16:.1f}" height="38" rx="8" fill="#f3f2f2" fill-opacity=".92"/>'
           f'{body}'
           f'<text x="{Wu - 8:.1f}" y="14" text-anchor="end" font-size="10" fill="#555" '
           'font-family="system-ui, sans-serif">© OpenStreetMap contributors</text>'
           '</svg>')
    OVERLAY.write_text(out, encoding="utf-8")

    # ---- base map: softened so the route reads first ----
    im = fetch_base(x0, y0, x1, y1, args.tiles_dir)
    im = Image.blend(ImageEnhance.Color(im).enhance(0.7), Image.new("RGB", im.size, PAPER), 0.2)
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
    im.save(BASE, "WEBP", quality=80, method=6)
    worst = max(np.linalg.norm(resid, axis=1)) / k
    print(f"wrote {BASE.relative_to(ROOT)} {im.width}x{im.height}, {OVERLAY.relative_to(ROOT)} "
          f"(viewBox {Wu:.0f}x{Hu:.0f}; largest correction {worst:.1f} source units)")


if __name__ == "__main__":
    main()
