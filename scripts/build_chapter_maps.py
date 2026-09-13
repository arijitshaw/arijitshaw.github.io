#!/usr/bin/env python3
"""Draw the chapter maps of the Spiti long read as small SVGs from OpenStreetMap data.

    python3 scripts/build_chapter_maps.py --fetch      # download OSM extracts into the data dir (once)
    python3 scripts/build_chapter_maps.py              # draw spiti/book/img/map-*.svg + spiti/book/maps.json

The drawings are made here from raw OSM geometry (roads, rivers, lakes, places); nothing is traced
from a published map. Map data © OpenStreetMap contributors, ODbL.

Each map is a spec in MAPS below: a bounding box, the markers (looked up by name in the OSM data,
or given as coordinates), and annotations. build_spiti_book.py reads maps.json and embeds every
map inline, so the SVGs take the page's fonts, colours and dark mode, and work offline.

Marker vocabulary (same on every map): filled numbered circle = night halt · hollow circle = daytime
stop · triangle = pass · small square = checkpost · pump = fuel · open book = something the text
sends you to. Places whose position is not confirmed are marked approx and listed as TODO(verify).
"""
import argparse
import json
import math
import re
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "spiti" / "book" / "img"
INDEX = ROOT / "spiti" / "book" / "maps.json"
UNVERIFIED = ROOT / "content" / "unverified-maps.json"
DEFAULT_DATA = Path.home() / ".cache" / "spiti-osm"

W = 420                        # viewBox width; ~0.85 px per unit on a 380 px phone
FS, FS_MINOR, FS_NOTE = 13.5, 12, 11.5

OVERPASS = "https://overpass-api.de/api/interpreter"
BBOX = "30.85,76.95,32.75,78.95"
FETCH = {
    "roads": f'[out:json][timeout:240];(way["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"]({BBOX}););out geom;',
    "rivers": f'[out:json][timeout:240];(way["waterway"="river"]({BBOX}););out geom;',
    "lakes": f'[out:json][timeout:240];(way["natural"="water"]["name"]({BBOX});relation["natural"="water"]["name"]({BBOX}););out geom;',
    "places": f'[out:json][timeout:240];(node["place"~"^(city|town|village|hamlet|locality|isolated_dwelling)$"]({BBOX}););out;',
    "peaks_passes": f'[out:json][timeout:240];(node["mountain_pass"="yes"]({BBOX});node["natural"~"^(peak|saddle|glacier)$"]["name"]({BBOX});way["natural"="glacier"]["name"]({BBOX}););out geom;',
    "pois": f'[out:json][timeout:240];(nwr["amenity"~"^(fuel|hospital|clinic|police|atm|bank|post_office)$"]({BBOX});nwr["tourism"~"^(attraction|viewpoint|museum)$"]["name"]({BBOX});nwr["amenity"="place_of_worship"]["name"]({BBOX});nwr["barrier"~"^(border_control|checkpoint)$"]({BBOX});nwr["historic"]["name"]({BBOX});nwr["bridge"="yes"]["name"]({BBOX}););out center;',
    "districts": '[out:json][timeout:240];(relation["boundary"="administrative"]["admin_level"="5"]["name"~"^(Kinnaur|Lahaul and Spiti|Shimla|Kullu)$"];);out geom;',
    "tunnels": f'[out:json][timeout:240];(way["tunnel"]["highway"]({BBOX}););out geom;',
    "named": ('[out:json][timeout:240];(nwr["name"~"Gramph|Grampoo|Batal|Shichling|Sichling|Schilling|Gete|Gette|Gulling|Guling|Chicham|'
              'Karcham|Jeori|Barobagh|Hatu|Kinner|Kinnaur Kailash|Jorkanden|Dhankar|Shigri|Atal|Rampur Bushahr|Chandra Dhaba|Kunzum|'
              f'Sumdo|Koksar|Losar",i]({BBOX}););out center tags;'),
}
AREAS = {"baspa": "31.15,78.05,31.60,78.70", "kalpa": "31.46,78.15,31.64,78.42", "dhankar_pin": "31.88,77.95,32.18,78.45",
         "kaza": "32.15,77.92,32.40,78.18", "kunzum_chandra": "32.20,77.05,32.56,77.85"}
for _k, _b in AREAS.items():
    FETCH[f"tracks_{_k}"] = (f'[out:json][timeout:240];(way["highway"~"^(unclassified|track|path|footway|residential|service)$"]({_b}););'
                             'out geom;')


def fetch(data):
    import requests
    data.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = "SpitiLongReadBuilder/1.0 (map data for a personal travel page)"
    for name, q in FETCH.items():
        if (data / f"{name}.json").exists():
            continue
        for attempt in range(5):
            r = s.post(OVERPASS, data={"data": q}, timeout=300)
            if r.status_code in (429, 504):
                time.sleep(30 * (attempt + 1))
                continue
            r.raise_for_status()
            (data / f"{name}.json").write_bytes(r.content)
            print("fetched", name)
            break
        time.sleep(10)


# --------------------------------------------------------------------------- data

def norm(s):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower())


class OSM:
    def __init__(self, data):
        load = lambda n: json.loads((data / f"{n}.json").read_text()).get("elements", []) if (data / f"{n}.json").exists() else []
        self.roads = load("roads") + [e for k in AREAS for e in load(f"tracks_{k}")] + load("tunnels")
        seen, uniq = set(), []
        for e in self.roads:
            if e.get("id") not in seen and e.get("geometry"):
                seen.add(e.get("id"))
                uniq.append(e)
        self.roads = uniq
        self.rivers = [e for e in load("rivers") if e.get("geometry")]
        self.lakes = [e for e in load("lakes") if e.get("geometry") or e.get("members")]
        self.districts = load("districts")
        self.points = []
        for f in ("places", "peaks_passes", "pois", "named", "lakes"):
            for e in load(f):
                t = e.get("tags", {})
                lat = e.get("lat") or (e.get("center") or {}).get("lat")
                lon = e.get("lon") or (e.get("center") or {}).get("lon")
                if lat is None and e.get("geometry"):
                    g = e["geometry"]
                    lat, lon = sum(p["lat"] for p in g) / len(g), sum(p["lon"] for p in g) / len(g)
                if lat is None:
                    continue
                names = {t.get(k) for k in ("name", "name:en", "alt_name", "old_name", "official_name") if t.get(k)}
                kind = (t.get("place") or t.get("natural") or t.get("amenity") or t.get("tourism")
                        or ("pass" if t.get("mountain_pass") else None) or t.get("barrier") or t.get("historic") or "")
                for n in names:
                    for part in re.split(r"[;/]", n):
                        self.points.append((norm(part), part.strip(), lat, lon, kind))

    def find(self, queries, bbox, kinds=None):
        s, w, n, e = bbox
        pad = 0.25
        for q in queries:
            k = norm(q)
            hits = [p for p in self.points if p[0] == k and s - pad < p[2] < n + pad and w - pad < p[3] < e + pad]
            if kinds:
                preferred = [p for p in hits if p[4] in kinds]
                hits = preferred or hits
            order = ["city", "town", "village", "hamlet", "locality", "isolated_dwelling"]
            hits.sort(key=lambda p: order.index(p[4]) if p[4] in order else len(order))
            if hits:
                return hits[0][2], hits[0][3]
        return None


# --------------------------------------------------------------------------- geometry

class Proj:
    def __init__(self, bbox):
        self.s, self.w, self.n, self.e = bbox
        ym = lambda lat: math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
        self.ym = ym
        self.H = W * (ym(self.n) - ym(self.s)) / math.radians(self.e - self.w)

    def __call__(self, lat, lon):
        return ((lon - self.w) / (self.e - self.w) * W,
                (self.ym(self.n) - self.ym(lat)) / (self.ym(self.n) - self.ym(self.s)) * self.H)

    def km_to_px(self, km):
        lat = (self.s + self.n) / 2
        return km / (111.32 * math.cos(math.radians(lat)) * (self.e - self.w)) * W


def simplify(pts, tol=0.7):
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy) or 1e-9
    idx, dmax = 0, -1
    for i in range(1, len(pts) - 1):
        d = abs(dy * pts[i][0] - dx * pts[i][1] + x2 * y1 - y2 * x1) / L
        if d > dmax:
            idx, dmax = i, d
    if dmax <= tol:
        return [pts[0], pts[-1]]
    return simplify(pts[:idx + 1], tol)[:-1] + simplify(pts[idx:], tol)


def runs_inside(pts, H, margin=24):
    """Split a polyline into runs that stay near the viewBox, so off-map geometry costs nothing."""
    run, out = [], []
    inside = lambda p: -margin <= p[0] <= W + margin and -margin <= p[1] <= H + margin
    for i, p in enumerate(pts):
        if inside(p) or (run and i + 1 < len(pts) and inside(pts[i + 1])) or (i + 1 < len(pts) and inside(pts[i + 1])):
            run.append(p)
        elif run:
            run.append(p)
            out.append(run)
            run = []
    if len(run) > 1:
        out.append(run)
    return out


def d_attr(pts):
    return "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# --------------------------------------------------------------------------- styles

STYLE = """
.m-bg{fill:var(--map-land,#efebe4)}
.m-water{fill:var(--map-water,#b9d3e3);stroke:none}
.m-river{fill:none;stroke:var(--map-water,#9cc0d8);stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.m-river-major{stroke-width:2.6}
.m-road{fill:none;stroke:var(--map-road,#c9c2b7);stroke-width:1.1;stroke-linecap:round;stroke-linejoin:round}
.m-road-major{stroke-width:1.8}
.m-track{fill:none;stroke:var(--map-road,#c9c2b7);stroke-width:.9;stroke-dasharray:3 2}
.m-route{fill:none;stroke:var(--route,#3F7FBF);stroke-width:3.4;stroke-linecap:round;stroke-linejoin:round}
.m-route-casing{fill:none;stroke:var(--map-halo,#f3f2f2);stroke-width:6;stroke-linecap:round;stroke-linejoin:round}
.m-alt{fill:none;stroke:var(--route-alt,#8A8A85);stroke-width:2;stroke-dasharray:5 3;stroke-linecap:round}
.m-walk{fill:none;stroke:var(--route,#3F7FBF);stroke-width:2;stroke-dasharray:1.5 3.5;stroke-linecap:round}
.m-boundary{fill:none;stroke:var(--map-boundary,#a39a8e);stroke-width:1.2;stroke-dasharray:7 3 1.5 3}
.m-caution{fill:none;stroke:var(--caution,#D9A441);stroke-width:4;stroke-linecap:round;opacity:.9}
.m-caution-zone{fill:var(--caution,#D9A441);fill-opacity:.28;stroke:var(--caution,#D9A441);stroke-width:1.4}
.m-note-line{fill:none;stroke:var(--map-label,#201f1d);stroke-width:1.1;stroke-dasharray:4 3;opacity:.75}
.m-bearing{fill:none;stroke:var(--map-label,#201f1d);stroke-width:1.1;stroke-dasharray:2 3}
.m-arrow{fill:none;stroke:var(--route,#3F7FBF);stroke-width:2.2}
.m-arrowhead{fill:var(--route,#3F7FBF)}
.m-night{fill:var(--route,#3F7FBF);stroke:var(--map-halo,#f3f2f2);stroke-width:1.6}
.m-night-num{fill:#fff;font-size:11px;font-weight:600;text-anchor:middle}
.m-end{fill:var(--map-halo,#f3f2f2);stroke:var(--map-label,#201f1d);stroke-width:2.2}
.m-stop{fill:var(--map-halo,#f3f2f2);stroke:var(--map-label,#201f1d);stroke-width:1.8}
.m-pass{fill:var(--map-label,#201f1d);stroke:var(--map-halo,#f3f2f2);stroke-width:1.2}
.m-check{fill:var(--map-halo,#f3f2f2);stroke:var(--map-label,#201f1d);stroke-width:1.6}
.m-glyph{fill:var(--practical,#6FA8C7);stroke:var(--map-halo,#f3f2f2);stroke-width:.8}
.m-book{fill:var(--map-halo,#f3f2f2);stroke:var(--accent,#a06f24);stroke-width:1.4;stroke-linejoin:round}
text{font-family:inherit;paint-order:stroke;stroke:var(--map-halo,#f3f2f2);stroke-width:3.2px;stroke-linejoin:round}
.m-label{fill:var(--map-label,#201f1d);font-size:13.5px}
.m-label-night{font-weight:600}
.m-label-minor{fill:var(--map-label,#201f1d);font-size:12px}
.m-label-water{fill:var(--map-water-label,#3b6e8f);font-size:11.5px;font-style:italic}
.m-label-note{fill:var(--map-label,#201f1d);font-size:11.5px;font-style:italic}
.m-label-caution{fill:var(--caution-ink,#8a5c12);font-size:11.5px;font-weight:600}
.m-small{fill:var(--map-muted,#6b6661);font-size:10.5px}
"""


# --------------------------------------------------------------------------- drawing

class Label:
    def __init__(self, text, x, y, r, cls="m-label", size=FS, prefer=None, pinned=None):
        self.text, self.x, self.y, self.r, self.cls, self.size = text, x, y, r, cls, size
        self.prefer, self.pinned = prefer, pinned


def text_box(text, size, x, y, anchor):
    w = len(text) * size * 0.56
    left = {"start": x, "end": x - w, "middle": x - w / 2}[anchor]
    return (left - 1, y - size * 0.85, left + w + 1, y + size * 0.3)


def overlap(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def place_labels(labels, H, occupied):
    out = []
    for lb in labels:
        r, s = lb.r, lb.size
        cands = {
            "e": (lb.x + r + 3, lb.y + s * 0.35, "start"), "w": (lb.x - r - 3, lb.y + s * 0.35, "end"),
            "n": (lb.x, lb.y - r - 4, "middle"), "s": (lb.x, lb.y + r + s * 0.95, "middle"),
            "ne": (lb.x + r + 1, lb.y - r - 1, "start"), "nw": (lb.x - r - 1, lb.y - r - 1, "end"),
            "se": (lb.x + r + 1, lb.y + r + s * 0.8, "start"), "sw": (lb.x - r - 1, lb.y + r + s * 0.8, "end"),
        }
        order = ([lb.pinned] if lb.pinned else []) + ([lb.prefer] if lb.prefer else []) + list(cands)
        best, best_cost = None, None
        for key in order:
            x, y, anchor = cands[key]
            box = text_box(lb.text, s, x, y, anchor)
            out_of = max(0, 3 - box[0]) + max(0, box[2] - (W - 3)) + max(0, 3 - box[1]) + max(0, box[3] - (H - 3))
            cost = sum(overlap(box, o) for o in occupied) + out_of * 40
            if lb.pinned and key == lb.pinned:
                best, best_cost = (x, y, anchor, box), -1
                break
            if best_cost is None or cost < best_cost:
                best, best_cost = (x, y, anchor, box), cost
            if cost == 0:
                break
        x, y, anchor, box = best
        occupied.append(box)
        out.append(f'<text class="{lb.cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">{esc(lb.text)}</text>')
    return out


def glyph(kind, x, y, num=None):
    if kind == "night":
        return (f'<circle class="m-night" cx="{x:.1f}" cy="{y:.1f}" r="8"/>'
                + (f'<text class="m-night-num" x="{x:.1f}" y="{y + 3.9:.1f}" style="stroke:none">{num}</text>' if num else ""), 9)
    if kind == "end":
        return f'<circle class="m-end" cx="{x:.1f}" cy="{y:.1f}" r="5.5"/>', 6
    if kind == "pass":
        return f'<path class="m-pass" d="M{x:.1f} {y - 6:.1f}L{x + 6:.1f} {y + 4.5:.1f}L{x - 6:.1f} {y + 4.5:.1f}Z"/>', 6
    if kind == "check":
        return f'<rect class="m-check" x="{x - 4:.1f}" y="{y - 4:.1f}" width="8" height="8"/>', 5
    if kind == "fuel":
        return (f'<path class="m-glyph" d="M{x - 4:.1f} {y + 5:.1f}V{y - 5:.1f}H{x + 2:.1f}V{y + 5:.1f}Z'
                f'M{x + 2:.1f} {y - 2:.1f}H{x + 4.5:.1f}V{y + 3:.1f}"/>', 6)
    if kind == "book":
        return (f'<path class="m-book" d="M{x:.1f} {y - 3:.1f}C{x - 2:.1f} {y - 5:.1f} {x - 5:.1f} {y - 5:.1f} {x - 6:.1f} {y - 4:.1f}'
                f'V{y + 4:.1f}C{x - 5:.1f} {y + 3:.1f} {x - 2:.1f} {y + 3:.1f} {x:.1f} {y + 5:.1f}'
                f'C{x + 2:.1f} {y + 3:.1f} {x + 5:.1f} {y + 3:.1f} {x + 6:.1f} {y + 4:.1f}V{y - 4:.1f}'
                f'C{x + 5:.1f} {y - 5:.1f} {x + 2:.1f} {y - 5:.1f} {x:.1f} {y - 3:.1f}ZM{x:.1f} {y - 3:.1f}V{y + 5:.1f}"/>', 7)
    return f'<circle class="m-stop" cx="{x:.1f}" cy="{y:.1f}" r="4.2"/>', 5


LEGEND_TEXT = {"night": "night halt", "end": "start / end", "stop": "daytime stop", "pass": "pass or peak",
               "check": "checkpost", "fuel": "fuel", "book": "the text sends you here"}


def draw(spec, osm, unverified):
    pid = spec["id"]
    bbox = spec["bbox"]
    P = Proj(bbox)
    H = P.H                                   # map area; legend, scale and credit sit in a band below
    tol = spec.get("simplify", 0.7)
    body, occupied, labels, places = [], [], [], []

    def ll_of(m):
        if "ll" in m:
            return tuple(m["ll"])
        found = osm.find(m.get("q", [m["name"]]), bbox, m.get("kinds"))
        if not found:
            raise SystemExit(f"{pid}: cannot find {m['name']!r} in OSM data; give 'll' and approx")
        return found

    # rivers and lakes
    major = set(spec.get("major_rivers", []))
    for e in osm.lakes:
        pts = [P(p["lat"], p["lon"]) for p in e.get("geometry", [])]
        if len(pts) > 2 and any(0 <= x <= W and 0 <= y <= H for x, y in pts):
            body.append(f'<path class="m-water" d="{d_attr(simplify(pts, 0.5))}Z"/>')
    for e in osm.rivers:
        name = e.get("tags", {}).get("name", "")
        is_major = any(m.lower() in name.lower() for m in major)
        if spec.get("major_rivers_only") and not is_major:
            continue
        pts = [P(p["lat"], p["lon"]) for p in e["geometry"]]
        cls = "m-river m-river-major" if is_major else "m-river"
        for run in runs_inside(pts, H):
            run = simplify(run, tol)
            if len(run) > 1:
                body.append(f'<path class="{cls}" d="{d_attr(run)}"/>')

    # district boundaries
    for e in osm.districts:
        for mem in e.get("members", []):
            if mem.get("role") != "outer" or not mem.get("geometry"):
                continue
            pts = [P(p["lat"], p["lon"]) for p in mem["geometry"]]
            for run in runs_inside(pts, H, margin=4):
                run = simplify(run, max(tol, 1.0))
                if len(run) > 1:
                    body.append(f'<path class="m-boundary" d="{d_attr(run)}"/>')

    # roads, then the route on top
    rank = {"path": -1, "footway": -1, "service": -1, "residential": -1, "track": 0, "unclassified": 0,
            "tertiary": 1, "secondary": 2, "primary": 3, "trunk": 3, "motorway": 3}
    route_refs = set(spec.get("route_refs", []))
    route_names = [re.compile(p, re.I) for p in spec.get("route_names", [])]
    alt_refs = set(spec.get("alt_refs", []))
    alt_names = [re.compile(p, re.I) for p in spec.get("alt_names", [])]
    routes, alts = [], []
    for e in osm.roads:
        t = e.get("tags", {})
        hw = t.get("highway", "")
        pts = [P(p["lat"], p["lon"]) for p in e["geometry"]]
        if not any(-10 <= x <= W + 10 and -10 <= y <= H + 10 for x, y in pts):
            continue
        is_route = t.get("ref") in route_refs or any(r.search(t.get("name", "")) for r in route_names)
        is_alt = not is_route and (t.get("ref") in alt_refs or any(r.search(t.get("name", "")) for r in alt_names))
        if not (is_route or is_alt) and rank.get(hw, -1) < spec.get("min_road", 0):
            continue
        cls = ("m-track" if hw in ("track", "unclassified") else
               "m-road m-road-major" if hw in ("trunk", "primary", "motorway") else "m-road")
        for run in runs_inside(pts, H):
            run = simplify(run, tol)
            if len(run) < 2:
                continue
            if is_route:
                routes.append(d_attr(run))
            elif is_alt:
                alts.append(d_attr(run))
            else:
                body.append(f'<path class="{cls}" d="{d_attr(run)}"/>')
    body.extend(f'<path class="m-alt" d="{d}"/>' for d in alts)
    body.extend(f'<path class="m-route-casing" d="{d}"/>' for d in routes)
    body.extend(f'<path class="m-route" d="{d}"/>' for d in routes)

    # annotations
    defs = (f'<marker id="{pid}-ah" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" orient="auto">'
            f'<path class="m-arrowhead" d="M0 0L10 5L0 10Z"/></marker>')
    named = {m["name"]: ll_of(m) for m in spec["markers"]}
    pt = lambda ref: named[ref] if isinstance(ref, str) else tuple(ref)

    def shorten(pts, by):
        if by <= 0 or len(pts) < 2:
            return pts
        (x1, y1), (x2, y2) = pts[0], pts[1]
        L = math.hypot(x2 - x1, y2 - y1) or 1
        pts = [(x1 + (x2 - x1) * by / L, y1 + (y2 - y1) * by / L)] + pts[1:]
        (x1, y1), (x2, y2) = pts[-1], pts[-2]
        L = math.hypot(x2 - x1, y2 - y1) or 1
        return pts[:-1] + [(x1 + (x2 - x1) * by / L, y1 + (y2 - y1) * by / L)]

    for a in spec.get("annotations", []):
        kind = a["type"]
        if kind in ("line", "caution-line", "walk", "arrow", "alt"):
            pts = shorten([P(*pt(r)) for r in a["points"]], a.get("shorten", 0))
            cls = {"line": "m-note-line", "caution-line": "m-caution", "walk": "m-walk", "arrow": "m-arrow", "alt": "m-alt"}[kind]
            extra = f' marker-end="url(#{pid}-ah)"' if kind == "arrow" else ""
            body.append(f'<path class="{cls}" d="{d_attr(pts)}"{extra}/>')
            if a.get("label"):
                i = a.get("label_at", len(pts) // 2)
                x, y = pts[min(i, len(pts) - 1)]
                labels.append(Label(a["label"], x, y, 2, "m-label-caution" if kind == "caution-line" else "m-label-note",
                                    FS_NOTE, a.get("side"), a.get("pin")))
        elif kind == "offmap":
            x, y = P(*pt(a["from"]))
            tx, ty = P(*pt(a["toward"]))
            dx, dy = tx - x, ty - y
            L = math.hypot(dx, dy) or 1
            ux, uy = dx / L, dy / L
            t_edge = min([(v - c) / d for c, d, v in ((x, ux, W - 8 if ux > 0 else 8), (y, uy, H - 8 if uy > 0 else 8)) if abs(d) > 1e-9])
            ex, ey = x + ux * t_edge, y + uy * t_edge
            sx, sy = x + ux * 10, y + uy * 10
            body.append(f'<path class="m-walk" d="M{sx:.1f} {sy:.1f}L{ex:.1f} {ey:.1f}" marker-end="url(#{pid}-ah)"/>')
            labels.append(Label(a["label"], ex, ey, 4, "m-label-note", FS_NOTE, a.get("side"), a.get("pin")))
        elif kind == "zone":
            x, y = P(*pt(a["at"]))
            r = P.km_to_px(a.get("r_km", 1.5))
            body.append(f'<circle class="m-caution-zone" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"/>')
            if a.get("label"):
                labels.append(Label(a["label"], x, y, r, "m-label-caution", FS_NOTE, a.get("side"), a.get("pin")))
        elif kind == "text":
            x, y = P(*pt(a["at"]))
            labels.append(Label(a["text"], x, y, a.get("r", 0), a.get("cls", "m-label-note"), a.get("size", FS_NOTE),
                                a.get("side"), a.get("pin", "e")))
        elif kind == "deadend":
            x, y = P(*pt(a["at"]))
            ang = math.radians(a.get("angle", 90))
            dx, dy = 6 * math.cos(ang), 6 * math.sin(ang)
            body.append(f'<path class="m-route" style="stroke-width:3" d="M{x - dx:.1f} {y - dy:.1f}L{x + dx:.1f} {y + dy:.1f}"/>')
            if a.get("label"):
                labels.append(Label(a["label"], x, y, 6, "m-label-note", FS_NOTE, a.get("side"), a.get("pin")))

    # markers
    kinds_used, marks = set(), []
    for m in spec["markers"]:
        lat, lon = named[m["name"]]
        x, y = P(lat, lon)
        if m.get("offmap"):   # listed with the map's places, pointed at by an "offmap" annotation, not drawn
            places.append({"name": m.get("list_name", m["name"]), "kind": m.get("kind", "stop"), "also": []})
            continue
        if not (0 <= x <= W and 0 <= y <= H):
            raise SystemExit(f"{pid}: {m['name']} at {lat:.4f},{lon:.4f} falls outside the frame")
        kind = m.get("kind", "stop")
        svg, r = glyph(kind, x, y, m.get("num"))
        marks.append(svg)
        kinds_used.add(kind)
        occupied.append((x - r, y - r, x + r, y + r))
        for extra in m.get("also", []):
            ex, ey = x + r + 5, y - r - 3
            s2, r2 = glyph(extra, ex, ey)
            marks.append(s2)
            kinds_used.add(extra)
            occupied.append((ex - r2, ey - r2, ex + r2, ey + r2))
        if m.get("label", True) is not False:
            text = m.get("label") if isinstance(m.get("label"), str) else m["name"]
            cls = "m-label m-label-night" if kind in ("night", "end") else "m-label" if m.get("major") else "m-label-minor"
            labels.insert(0 if kind in ("night", "end") else len(labels),
                          Label(text, x, y, r + 1, cls, FS if cls != "m-label-minor" else FS_MINOR, m.get("side"), m.get("pin")))
        places.append({"name": m.get("list_name", m["name"]), "kind": kind, "also": m.get("also", []),
                       **({"note": m["note"]} if m.get("note") else {}), **({"approx": True} if m.get("approx") else {})})
        if m.get("approx"):
            unverified.append({"map": pid, "place": m["name"], "why": m.get("note", "position approximate")})
    for w in spec.get("water_labels", []):
        x, y = P(*w["at"])
        labels.append(Label(w["text"], x, y, 0, "m-label-water", FS_NOTE, w.get("side"), w.get("pin", "e")))

    # north arrow inside the map; legend, scale bar and credit in a band underneath
    north = [f'<path d="M{W - 14} 26L{W - 9} 12L{W - 4} 26L{W - 9} 22Z" fill="var(--map-label,#201f1d)"/>',
             f'<text class="m-small" x="{W - 9}" y="38" text-anchor="middle">N</text>']
    occupied.append((W - 20, 6, W, 42))
    label_svg = place_labels(labels, H, occupied)

    legend_items = [k for k in ("night", "end", "stop", "pass", "check", "fuel", "book") if k in kinds_used]
    rows, row, cx = [], [], 8
    for k in legend_items:
        wdt = 22 + len(LEGEND_TEXT[k]) * 6.1 + 14
        if cx + wdt > W - 4 and row:
            rows.append(row)
            row, cx = [], 8
        row.append((k, cx))
        cx += wdt
    if row:
        rows.append(row)
    band = 8 + len(rows) * 18 + 22
    TH = H + band
    legend = [f'<rect x="0" y="{H:.1f}" width="{W}" height="{band:.1f}" fill="var(--map-halo,#f3f2f2)"/>',
              f'<path d="M0 {H:.1f}H{W}" stroke="var(--divider,#d8d3cc)" stroke-width="1"/>']
    for ri, items in enumerate(rows):
        gy = H + 8 + ri * 18 + 9
        for k, lx in items:
            g, _ = glyph(k, lx + 8, gy, "1" if k == "night" else None)
            g = g.replace('r="8"', 'r="6.5"').replace('class="m-night-num"', 'class="m-night-num" style="font-size:9px;stroke:none"')
            legend.append(g)
            legend.append(f'<text class="m-small" x="{lx + 20}" y="{gy + 3.8:.1f}" style="stroke:none">{LEGEND_TEXT[k]}</text>')
    km = next(k for k in (0.5, 1, 2, 5, 10, 20, 50) if P.km_to_px(k) >= 45)
    sb = P.km_to_px(km)
    by = TH - 10
    km_text = f"{km:g} km"
    legend += [
        f'<path d="M10 {by - 2:.1f}h{sb:.1f}" stroke="var(--map-label,#201f1d)" stroke-width="2"/>',
        f'<path d="M10 {by - 6:.1f}v8M{10 + sb:.1f} {by - 6:.1f}v8" stroke="var(--map-label,#201f1d)" stroke-width="1.2"/>',
        f'<text class="m-small" x="{10 + sb + 5:.1f}" y="{by + 2:.1f}" style="stroke:none">{km_text}</text>',
        f'<text class="m-small" x="{W - 6}" y="{by + 2:.1f}" text-anchor="end" style="stroke:none">© OpenStreetMap contributors</text>',
    ]

    title = spec["title"]
    desc = spec.get("desc", "") + " Places: " + ", ".join(p["name"] for p in places) + "."
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {TH:.0f}" role="img" aria-labelledby="{pid}-t {pid}-d" '
           f'class="chapter-map">'
           f'<title id="{pid}-t">{esc(title)}</title><desc id="{pid}-d">{esc(desc)}</desc>'
           f'<defs>{defs}<clipPath id="{pid}-clip"><rect width="{W}" height="{H:.1f}"/></clipPath></defs>'
           f'<style>{STYLE}</style>'
           f'<rect class="m-bg" width="{W}" height="{H:.1f}"/>'
           f'<g clip-path="url(#{pid}-clip)">{"".join(body)}</g>'
           f'{"".join(marks)}{"".join(north)}{"".join(label_svg)}{"".join(legend)}</svg>')
    svg = re.sub(r"\s*\n\s*", "", svg)
    return svg, places


# --------------------------------------------------------------------------- the maps

MAPS = [
    {
        "id": "map-ch01-03", "file": "map-ch01-03-shimla-sarahan.svg", "anchor": "Narkanda, Kotgarh, Rampur",
        "title": "Day 1: Shimla to Sarahan",
        "caption": "Day 1, Shimla to Sarahan: over the Narkanda ridge and down into the Sutlej valley.",
        "desc": "The first day's drive from Shimla over the Narkanda ridge, down to the Sutlej at Rampur and up to Sarahan.",
        "bbox": (30.99, 77.12, 31.60, 77.86), "major_rivers": ["Sutlej"], "major_rivers_only": True,
        "min_road": 2, "simplify": 1.3,
        "route_refs": ["NH5"], "route_names": [r"sarahan"],
        "markers": [
            {"name": "Shimla", "kind": "end", "q": ["Shimla"], "kinds": ["city"], "side": "s"},
            {"name": "Fagu", "q": ["Fagu"], "side": "s"},
            {"name": "Theog", "q": ["Theog"], "side": "e"},
            {"name": "Narkanda", "q": ["Narkanda"], "major": True, "side": "w"},
            {"name": "Hatu Peak", "kind": "book", "q": ["Hatu Peak", "Hatu Mata Temple"], "note": "Hatu Mata temple", "side": "e"},
            {"name": "Kotgarh", "kind": "book", "q": ["Kotgarh"], "side": "w"},
            {"name": "Nirath", "kind": "book", "q": ["Nirath"], "note": "sun temple", "side": "e"},
            {"name": "Rampur", "q": ["Rampur Bushahr", "Rampur"], "kinds": ["town", "city"], "major": True, "side": "w"},
            {"name": "Jeori", "kind": "book", "ll": (31.5172, 77.7788), "approx": True, "side": "w",
             "note": "memorial to the 122 road-builders; drawn at the Sarahan turn-off, exact spot to confirm"},
            {"name": "Sarahan", "kind": "night", "num": 1, "q": ["Sarahan"], "kinds": ["town"], "side": "s"},
        ],
        "annotations": [
            {"type": "text", "at": (31.36, 77.50), "text": "down about 1,800 m to the river", "pin": "e"},
        ],
        "water_labels": [{"text": "Sutlej", "at": (31.43, 77.64)}],
    },
    {
        "id": "map-ch04", "file": "map-ch04-baspa.svg", "anchor": "The Baspa Valley — Sangla, Kamru, Rakcham, Chitkul",
        "title": "Chapter 4: the Baspa valley",
        "caption": "The Baspa valley: a side valley that ends at Chitkul. Beyond it there is only the footpath.",
        "desc": "The Baspa valley from the Karcham turn-off to the road end beyond Chitkul, with the footpath towards Lamkhaga La.",
        "bbox": (31.32, 78.12, 31.53, 78.48), "major_rivers": ["Baspa", "Sutlej"],
        "route_refs": ["NH5"], "route_names": [r"sangla", r"chitkul", r"karch", r"baspa", r"rakcham"],
        "markers": [
            {"name": "Karcham", "q": ["Karcham Bridge", "Karcham"], "major": True, "note": "turn-off from NH-5", "side": "w"},
            {"name": "Sangla", "q": ["Sangla"], "major": True, "side": "s"},
            {"name": "Kamru", "kind": "book", "q": ["Kamru"], "note": "fort", "side": "n"},
            {"name": "Batseri", "q": ["Batseri"], "side": "s"},
            {"name": "Rakcham", "q": ["Rakcham"], "side": "n"},
            {"name": "Chitkul", "kind": "night", "num": 2, "q": ["Chitkul"], "side": "n"},
            {"name": "Lamkhaga La", "kind": "pass", "ll": (31.1980, 78.6530), "offmap": True, "list_name": "Lamkhaga La (off the map, south-east)"},
        ],
        "annotations": [
            {"type": "deadend", "at": "Chitkul", "label": "road ends", "angle": 30, "side": "s"},
            {"type": "offmap", "from": "Chitkul", "toward": (31.1980, 78.6530), "label": "footpath to Lamkhaga La", "side": "w"},
            {"type": "text", "at": (31.515, 78.30), "text": "Kinner Kailash massif to the north", "pin": "e"},
        ],
        "water_labels": [{"text": "Baspa", "at": (31.41, 78.215)}],
    },
    {
        "id": "map-ch05", "file": "map-ch05-kalpa.svg", "anchor": "Kalpa, and the Mountain That Is a God",
        "title": "Chapter 5: Kalpa and Reckong Peo",
        "caption": "Kalpa sits above Reckong Peo, facing the Kinner Kailash range across the Sutlej.",
        "desc": "Kalpa, Reckong Peo, Powari and Roghi, with the sightline from Kalpa to the Kinner Kailash summit.",
        "bbox": (31.47, 78.17, 31.60, 78.40), "major_rivers": ["Sutlej"],
        "route_refs": ["NH5"], "route_names": [r"kalpa", r"peo"],
        "markers": [
            {"name": "Powari", "q": ["Powari"], "side": "w"},
            {"name": "Reckong Peo", "q": ["Reckong Peo"], "kinds": ["town"], "major": True, "also": ["fuel"], "note": "last reliable ATM, market and fuel", "side": "e"},
            {"name": "Kalpa", "kind": "night", "num": 3, "q": ["Kalpa"], "side": "w"},
            {"name": "Roghi", "q": ["Roghi"], "side": "e"},
            {"name": "Kinnaur Kailash", "kind": "pass", "q": ["Kinnaur Kailash"], "kinds": ["peak"], "label": "Kinner Kailash 6,050 m",
             "list_name": "Kinner Kailash (the shivling stands on its shoulder)", "side": "s"},
        ],
        "annotations": [
            {"type": "line", "points": ["Kalpa", "Kinnaur Kailash"], "shorten": 10, "label": "sightline", "side": "s", "label_at": 1},
        ],
        "water_labels": [{"text": "Sutlej", "at": (31.585, 78.305)}],
        "unverified": ["Chapter 5: the sightline is drawn to the Kinnaur Kailash summit in OSM; the shivling itself is on a shoulder of the massif, position not mapped"],
    },
    {
        "id": "map-ch06", "file": "map-ch06-the-long-drive.svg", "anchor": "The Road Itself",
        "title": "Day 4: Kalpa to Tabo",
        "caption": "Day 4, the long drive: the Sutlej gorge, the Khab confluence, the climb to Nako and into Spiti.",
        "desc": "The long drive from Reckong Peo up the Sutlej gorge to Khab, up the Ka loops to Nako and on to Sumdo and Tabo.",
        "bbox": (31.45, 77.80, 32.18, 78.80), "major_rivers": ["Sutlej", "Spiti"], "major_rivers_only": True,
        "min_road": 3, "simplify": 1.1,
        "route_refs": ["NH5", "NH505"],
        "markers": [
            {"name": "Karcham", "q": ["Karcham Bridge", "Karcham"], "side": "s"},
            {"name": "Wangtu", "kind": "check", "q": ["Wangtu"], "note": "check post", "side": "e"},
            {"name": "Reckong Peo", "q": ["Reckong Peo"], "kinds": ["town"], "major": True, "side": "e"},
            {"name": "Spillow", "q": ["Spillow"], "side": "e"},
            {"name": "Pooh", "q": ["Pooh"], "side": "e"},
            {"name": "Khab", "q": ["Khab"], "major": True, "note": "Spiti–Sutlej confluence", "side": "e"},
            {"name": "Nako", "kind": "book", "q": ["Nako"], "side": "e"},
            {"name": "Chango", "q": ["Chango"], "side": "e"},
            {"name": "Sumdo", "kind": "check", "q": ["Sumdo"], "note": "check post: register", "side": "e"},
            {"name": "Gue", "kind": "book", "q": ["Gue"], "note": "detour to the mummy", "side": "e"},
            {"name": "Tabo", "kind": "night", "num": 4, "q": ["Tabo"], "side": "s"},
        ],
        "annotations": [
            {"type": "zone", "at": (31.5568, 77.8838), "r_km": 2.2, "label": "Nigulsari slides", "side": "n"},
            {"type": "zone", "at": (31.5687, 77.8492), "r_km": 2.0, "label": "Chaura", "side": "s"},
            {"type": "line", "points": [(31.84, 78.57), (31.84, 78.70)], "label": "trees stop, above the Ka loops", "side": "w", "label_at": 0},
            {"type": "line", "points": [(31.905, 78.56), (31.905, 78.69)], "label": "monsoon India ends, around Nako", "side": "w", "label_at": 0},
        ],
        "water_labels": [{"text": "Sutlej", "at": (31.62, 78.08)}, {"text": "Spiti", "at": (32.00, 78.585)}],
        "unverified": ["Chapter 6: the tree line and the monsoon edge are drawn where the text places them (above Khab, around Nako), not surveyed",
                       "Chapter 6: Nigulsari and Chaura slide zones are drawn as circles around the villages; the active stretches move"],
    },
    {
        "id": "map-ch08-10", "file": "map-ch08-10-tabo-dhankar-pin.svg", "anchor": "Dhankar and Lhalung",
        "title": "Day 5: Tabo, Dhankar, Lhalung and the Pin valley",
        "caption": "Day 5: Tabo to Mud by way of Dhankar, with the Lhalung side trip. The Dhankar close-up is below.",
        "desc": "The Spiti valley from Tabo to the Pin confluence at Attargo, the turn-offs to Dhankar and Lhalung, and up the Pin valley past Kungri to Mud.",
        "bbox": (31.93, 77.98, 32.17, 78.42), "major_rivers": ["Spiti", "Pin"],
        "route_refs": ["NH505"], "route_names": [r"dhankar", r"schichiling", r"\bpin\b", r"mudh?\b", r"kungri"],
        "markers": [
            {"name": "Tabo", "kind": "night", "num": 4, "q": ["Tabo"], "side": "n"},
            {"name": "Dhankar", "kind": "book", "q": ["Dhankar"], "kinds": ["village"], "side": "n", "list_name": "Dhankar (village, old gompa and lake: see close-up)"},
            {"name": "Shichilling", "q": ["Shichling", "Shichilling"], "note": "newer monastery below Dhankar", "side": "e"},
            {"name": "Lhalung", "kind": "book", "q": ["Lhalung", "Lalung"], "kinds": ["village"], "side": "e"},
            {"name": "Attargo", "q": ["Attargo"], "note": "bridge at the Pin confluence", "side": "w"},
            {"name": "Sagnam", "q": ["Sagnam"], "side": "w"},
            {"name": "Guling", "q": ["Guling", "Gulling"], "side": "e"},
            {"name": "Kungri", "kind": "book", "q": ["Kungri"], "kinds": ["village"], "note": "Nyingma gompa", "side": "n"},
            {"name": "Mud", "kind": "night", "num": 5, "q": ["Mud"], "label": "Mud (Mudh)", "side": "e"},
        ],
        "annotations": [],
        "water_labels": [{"text": "Spiti", "at": (32.065, 78.30)}, {"text": "Pin", "at": (32.00, 78.06)}],
    },
    {
        "id": "map-ch09-dhankar", "file": "map-ch09-dhankar-closeup.svg", "anchor": "The fort on the cliff",
        "title": "Dhankar close-up: village, old gompa and lake",
        "caption": "Three places people run together: Dhankar village, the old gompa on its spur, and Dhankar Lake up the hill.",
        "desc": "Close-up of Dhankar: the village, the old gompa on the cliff, the lake above them, and the link road down to Shichilling.",
        "bbox": (32.056, 78.198, 32.100, 78.240), "major_rivers": ["Spiti"], "simplify": 0.4,
        "route_names": [r"dhankar", r"schichiling"], "route_refs": ["NH505"],
        "markers": [
            {"name": "Dhankar village", "q": ["Dhankar"], "kinds": ["village"], "major": True, "side": "w"},
            {"name": "Old gompa", "kind": "book", "q": ["Dhankara Old Monastery"], "side": "s", "list_name": "Dhankar old gompa (fort on the cliff)"},
            {"name": "Dhankar Lake", "kind": "book", "q": ["Dhankar Tso", "Dhankar Lake"], "kinds": ["water"], "side": "e"},
            {"name": "Shichilling", "q": ["Shichling", "Shichilling"], "note": "newer monastery", "side": "e"},
        ],
        "annotations": [
            {"type": "walk", "points": ["Dhankar village", "Dhankar Lake"], "shorten": 7, "label": "walk: about 45 min, up to 4,100 m", "side": "n", "label_at": 1},
        ],
        "unverified": ["Chapter 9: Dhankar Lake walk is drawn as a straight line; the path, its length and the climb need confirming (text gives a hard 45 minutes to 4,100 m)"],
    },
    {
        "id": "map-ch11-12", "file": "map-ch11-12-kaza-high-villages.svg", "anchor": "The High Villages",
        "title": "Days 6–7: Kaza and the high villages",
        "caption": "Kaza, Ki and the high villages. The arrows show the Langza–Hikkim–Komic loop in the direction the plan drives it.",
        "desc": "Kaza and Ki, the road north to Kibber and the Chicham bridge, and the Langza, Hikkim and Komic loop above Kaza.",
        "bbox": (32.19, 77.94, 32.37, 78.16), "major_rivers": ["Spiti"],
        "route_refs": ["NH505"], "route_names": [r"kibber", r"chicham", r"langza", r"hikkim", r"komic"],
        "markers": [
            {"name": "Kaza", "kind": "night", "num": 6, "q": ["Kaza"], "kinds": ["town"], "also": ["fuel"], "side": "w"},
            {"name": "Ki", "kind": "book", "q": ["Ki", "Key"], "kinds": ["village"], "label": "Ki gompa", "side": "e"},
            {"name": "Kibber", "q": ["Kibber"], "kinds": ["village"], "major": True, "side": "e"},
            {"name": "Chicham", "kind": "book", "q": ["Chicham Bridge", "Chicham"], "label": "Chicham bridge", "side": "w"},
            {"name": "Gette", "q": ["Gete Chorten", "Gette", "Gete"], "note": "chorten", "side": "w"},
            {"name": "Tashigang", "q": ["Tashigang"], "side": "e"},
            {"name": "Langza", "kind": "book", "q": ["Langza"], "kinds": ["village"], "side": "n"},
            {"name": "Hikkim", "kind": "book", "q": ["Hikkim"], "note": "post office", "side": "e"},
            {"name": "Komic", "q": ["Komic"], "side": "e"},
            {"name": "Rangrik", "q": ["Rangrik"], "side": "w"},
        ],
        "annotations": [
            {"type": "arrow", "points": ["Kaza", "Langza"], "shorten": 13},
            {"type": "arrow", "points": ["Langza", "Hikkim"], "shorten": 11},
            {"type": "arrow", "points": ["Hikkim", "Komic"], "shorten": 9},
            {"type": "arrow", "points": ["Komic", "Kaza"], "shorten": 12},
        ],
        "water_labels": [{"text": "Spiti", "at": (32.215, 78.00)}],
        "unverified": ["Chapter 12: the loop direction follows the trip plan (Kaza → Langza → Hikkim → Komic → Kaza); confirm road condition and direction locally"],
    },
    {
        "id": "map-ch13-14", "file": "map-ch13-14-losar-kunzum-chandratal.svg", "anchor": "Losar and Kunzum La",
        "title": "Day 8: Losar, Kunzum La and Chandratal",
        "caption": "Day 8: up from Losar over Kunzum La, down to Batal, and back up to Chandratal. The last stretch is on foot.",
        "desc": "Losar, the climb to Kunzum La on the watershed, the descent to Batal and Chandra Dhaba, and the road and footpath to Chandratal.",
        "bbox": (32.33, 77.56, 32.50, 77.80), "major_rivers": ["Chandra", "Spiti"],
        "route_refs": ["NH505"], "route_names": [r"chandra ?ta+l"],
        "markers": [
            {"name": "Losar", "kind": "night", "num": 7, "q": ["Losar"], "kinds": ["village"], "also": ["check"], "side": "s"},
            {"name": "Kunzum La", "kind": "pass", "q": ["Kunzum La", "Kunzum Pass"], "kinds": ["saddle", "pass"], "label": "Kunzum La 4,590 m", "side": "e"},
            {"name": "Batal", "kind": "book", "q": ["Chandra Dhaba", "Batal Bridge"], "label": "Batal · Chandra Dhaba", "note": "Chandra Dhaba", "side": "e"},
            {"name": "Chandratal parking", "q": ["Chandratal lake foot route - alt: 4254m"], "label": "parking",
             "list_name": "Chandratal parking and camps (the foot route starts here)", "side": "e"},
            {"name": "Chandratal", "kind": "night", "num": 8, "q": ["Chandratal Lake", "Chandra Tal Lake", "Chandratal"], "kinds": ["water"], "side": "w"},
        ],
        "annotations": [
            {"type": "walk", "points": ["Chandratal parking", "Chandratal"], "shorten": 8, "label": "on foot to the lake", "side": "e", "label_at": 1},
            {"type": "text", "at": (32.3946, 77.6351), "text": "watershed", "pin": "s", "r": 8},
        ],
        "water_labels": [{"text": "Chandra", "at": (32.35, 77.585)}, {"text": "Losar", "at": (32.44, 77.73)}],
        "unverified": ["Chapter 14: the walk from the Chandratal parking to the lake is drawn straight; distance and time to confirm"],
    },
    {
        "id": "map-ch15", "file": "map-ch15-chandra-valley-manali.svg", "anchor": "The Chandra Valley",
        "title": "Day 9: down the Chandra valley to Manali",
        "caption": "Day 9: Batal to Manali. Cross the streams early; at Gramphu choose the Atal Tunnel or Rohtang La.",
        "desc": "The Chandra valley from Batal past Chhota Dara and the Bara Shigri glacier to Gramphu, then Koksar and the Atal Tunnel, or Rohtang La, down to Manali.",
        "bbox": (32.22, 77.10, 32.49, 77.66), "major_rivers": ["Chandra", "Beas"], "major_rivers_only": True,
        "min_road": 2, "simplify": 0.9,
        "route_refs": ["NH505", "NH3"], "route_names": [r"atal"], "alt_names": [r"rohtang"],
        "markers": [
            {"name": "Batal", "kind": "book", "q": ["Chandra Dhaba", "Batal Bridge"], "label": "Batal", "note": "Chandra Dhaba", "side": "n"},
            {"name": "Chhota Dara", "q": ["Chhota Dara"], "side": "n"},
            {"name": "Bara Shigri", "ll": (32.27, 77.62), "approx": True, "label": "Bara Shigri glacier", "note": "glacier snout; position approximate", "side": "w"},
            {"name": "Gramphu", "q": ["Gramphoo", "Gramphu", "Grampoo"], "side": "e"},
            {"name": "Koksar", "kind": "check", "q": ["Koksar"], "note": "check post", "side": "n"},
            {"name": "Rohtang La", "kind": "pass", "q": ["Rohtang Pass"], "kinds": ["saddle", "pass"], "side": "s"},
            {"name": "Sissu", "q": ["Sissu"], "side": "n"},
            {"name": "Manali", "kind": "end", "q": ["Manali"], "kinds": ["town"], "side": "e"},
        ],
        "annotations": [
            {"type": "caution-line", "points": [(32.3586, 77.6201), (32.3038, 77.5700), (32.3022, 77.4049)],
             "label": "stream crossings: cross early", "side": "s", "label_at": 1},
            {"type": "text", "at": (32.4377, 77.1628), "text": "Atal Tunnel", "pin": "w", "r": 4},
        ],
        "water_labels": [{"text": "Chandra", "at": (32.345, 77.33)}, {"text": "Beas", "at": (32.27, 77.19)}],
        "unverified": ["Chapter 15: stream crossings are shown as the Batal–Chhota Dara–Gramphu stretch, not individual crossings"],
    },
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--only")
    args = ap.parse_args()
    if args.fetch:
        fetch(args.data)
        return
    osm = OSM(args.data)
    index, unverified = [], []
    for spec in MAPS:
        if args.only and spec["id"] != args.only:
            continue
        svg, places = draw(spec, osm, unverified)
        unverified += [{"map": spec["id"], "place": "", "why": u} for u in spec.get("unverified", [])]
        (IMG / spec["file"]).write_text(svg, encoding="utf-8")
        index.append({"file": spec["file"], "anchor": spec["anchor"], "title": spec["title"],
                      "caption": spec["caption"], "places": places})
        print(f"{spec['file']:44} {len(svg) / 1024:5.1f} KB  {len(places)} places")
    if not args.only:
        INDEX.write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        UNVERIFIED.parent.mkdir(exist_ok=True)
        UNVERIFIED.write_text(json.dumps(unverified, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
