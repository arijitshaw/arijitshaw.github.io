#!/usr/bin/env python3
"""Render spiti/book/spiti-circuit-the-long-read.md into a single-page web book.

Output: spiti/book/index.html (one scrollable page, with an always-available
contents sidebar / drawer, scroll tracking, resume, dark mode).

Conventions understood in the markdown:
  # The Long Read                 first H1 = cover; its ## sections are front matter
  # Chapter N · Title             also: Interlude One · …, Sidebar · …, Coda · …, Appendix A · …
  **Day 1 · …** / *Read this …*   bold- or italic-only lines right under an H1 = chapter meta
  ### In the rock: …              "In the rock", "The other story", "Who came through here" = boxes
  ## Contents                     **Group** lines + | num | name | when | rows drive the sidebar groups
  --- then *italic line*          at the very end = colophon
"""
import hashlib
import html
import json
import math
import re
import sys
from collections import Counter
import unicodedata
from pathlib import Path

import markdown

import spiti_extras

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "spiti" / "book" / "spiti-circuit-the-long-read.md"
OUT = ROOT / "spiti" / "book" / "index.html"
MAP_URL = ("https://www.google.com/maps/d/viewer?hl=en&mid=1u-k6Xo2r8bb7X1d2uw0fOrKS4oj_jdU"
           "&ll=31.598923869659814%2C77.71116500000001&z=8")
SPITI = ROOT / "spiti"
IMAGES = ROOT / "spiti" / "book" / "images.json"   # written by scripts/commons_image.py
MAPS = ROOT / "spiti" / "book" / "maps.json"       # written by scripts/build_chapter_maps.py
FIGURES = ROOT / "spiti" / "book" / "figures.json" # hand-drawn diagrams (spiti/book/img/figures/), edited by hand
# Third-party files the pages load; cached by the service worker so the site works offline.
EXTERNAL = [
    "https://unpkg.com/react@18.3.1/umd/react.production.min.js",
    "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js",
    "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=Lora:wght@400;600&display=swap",
    "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Lora:wght@400;600&display=swap",
    "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400"
    "&family=Lora:ital,wght@0,400;0,600;1,400&display=swap",
    # spiti/map/: Leaflet and its fonts (the map tiles themselves always come from the network)
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
    "https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Barlow+Semi+Condensed:wght@500;600&display=swap",
]
# only these third-party hosts are kept in the offline cache; anything else (map tiles) passes through
RUNTIME_HOSTS = ["fonts.googleapis.com", "fonts.gstatic.com", "unpkg.com"]

BOXES = {"In the rock": "rock", "The other story": "myth", "Who came through here": "people",
         # actionable boxes (todo colour system): blue = do something, amber = don't get hurt, green = don't be a problem
         "Practical": "practical", "Caution": "caution", "Respect": "respect",
         # T7.1 after the trip: "### Field notes: September 2026" at the end of a chapter
         "Field notes": "field"}
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
WORDS = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve"]
LIST_ITEM = re.compile(r"^\s*([-*+]|\d+\.)\s")

_used_ids = set()
_fig_ids = set()
TOKENS = {}   # placeholder paragraph -> gallery html, swapped in by md()
ITEM_LINE = re.compile(r"^(?:\s*[-*+]\s+)?\*\*([^*]+?)\*\*")


def slug(text, prefix=""):
    s = unicodedata.normalize("NFKD", re.sub(r"[*_`]", "", text)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60].strip("-")
    base = f"{prefix}-{s}" if prefix else s
    out, n = base, 2
    while out in _used_ids:
        out, n = f"{base}-{n}", n + 1
    _used_ids.add(out)
    return out


def plain(text):
    return re.sub(r"[*_`]", "", text).strip()


def md(lines):
    # Python-Markdown needs a blank line before a list that follows a paragraph line.
    fixed = []
    for line in lines:
        if LIST_ITEM.match(line) and fixed and fixed[-1].strip() and not LIST_ITEM.match(fixed[-1]):
            fixed.append("")
        fixed.append(line)
    out = markdown.markdown("\n".join(fixed), extensions=["tables", "smarty", "sane_lists"])
    out = re.sub(r"<thead>\s*<tr>\s*(<th[^>]*>\s*</th>\s*)+</tr>\s*</thead>\s*", "", out)  # empty header rows
    for token in re.findall(r"<p>(GALLERYPLACEHOLDER\d+)</p>", out):
        out = out.replace(f"<p>{token}</p>", TOKENS[token])
    # a floated thumbnail is boxed with the paragraph it belongs to, so short paragraphs
    # don't let the next thumbnail drift down beside the wrong text
    for token in re.findall(r"<p>(FLOATPLACEHOLDER\d+)</p>", out):
        fig = TOKENS[token]
        out = re.sub(rf"<p>{token}</p>\s*(<p>.*?</p>)", lambda m: f'<div class="with-float">{fig}{m.group(1)}</div>',
                     out, count=1, flags=re.S)
        out = out.replace(f"<p>{token}</p>", fig)
    # T4.2: "Source: …" / "Checked: …" paragraphs are the stamp at the foot of a practical box;
    # TODO(verify) markers show as a small chip and are collected into content/unverified.md
    out = re.sub(r"<p>((?:Source|Checked|Verified):)", r'<p class="checked">\1', out)
    out = out.replace("TODO(verify)", '<span class="todo-verify" title="Not yet checked on the ground">to verify</span>')
    return out.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")


def inline(text):
    return re.sub(r"^<p>|</p>$", "", md([text]))


def clean_credit(text):
    """Commons author fields are free text; keep just a readable name."""
    t = re.sub(r"^(This Photo was taken by|Photo by|Artist:)\s*", "", text or "").strip()
    t = re.sub(r"^No machine-readable author provided\.\s*(\S+?)~commonswiki.*", r"\1", t)
    if m := re.match(r"https?://(?:www\.)?([^/\s]+)", t):
        return m[1]
    # cut at the first sentence end, but not after an initial like "A. Gonsalves"
    t = re.split(r"(?<=[a-z]{2})\.\s+(?=[A-Z])|;\s*Engraver", t)[0].strip(" .")
    for half in (len(t) // 2,):
        if t and t[:half] == t[half:]:
            t = t[:half]
    return "" if t.lower() in ("as in description", "unknown author", "") else t


def fig_id(img):
    base = out = f"fig-{Path(img['file']).stem}"
    n = 2
    while out in _fig_ids:
        out, n = f"{base}-{n}", n + 1
    _fig_ids.add(out)
    return out


def credit_html(img):
    credit = clean_credit(img.get("credit"))
    return (f'<span class="credit">{html.escape(credit) + " · " if credit else ""}'
            f'<a href="{html.escape(img["source"])}" target="_blank" rel="noopener">{html.escape(img["license"])}</a></span>')


def gfig_html(img, cls="gfig"):
    return (f'<figure class="{cls}" id="{fig_id(img)}"><img src="img/{img["file"]}" '
            f'alt="{html.escape("" if (img.get("alt") or "").strip() == (img.get("caption") or "").strip() else img["alt"])}" '
            f'width="{img["w"]}" height="{img["h"]}" loading="lazy" decoding="async">'
            f'<figcaption>{inline(img.get("caption") or img["after"])} {credit_html(img)}</figcaption></figure>')


def gallery_html(imgs):
    return f'<div class="gallery">{"".join(gfig_html(img) for img in imgs)}</div>'


def inject_items(lines, title, items):
    """Images anchored to a bold item (**Day 1 · …**, - **Wallcreeper** …).
    A single image for a paragraph floats beside that paragraph; images for list items, or
    several for one paragraph, go in a grid after the list or paragraph.
    items: {(heading, item): [img]}."""
    heading, points = title, {}
    for i, line in enumerate(lines):
        if m := re.match(r"^#{2,4} (.+)$", line):
            heading = plain(m.group(1))
            continue
        b = ITEM_LINE.match(line)
        key = b and (heading, b.group(1).strip(" .:—"))
        if not key or key not in items:
            continue
        imgs, end = items.pop(key), i
        if LIST_ITEM.match(line):
            while end + 1 < len(lines) and LIST_ITEM.match(lines[end + 1]):
                end += 1
        else:
            while end + 1 < len(lines) and lines[end + 1].strip() and not LIST_ITEM.match(lines[end + 1]):
                end += 1
            if len(imgs) == 1:
                points.setdefault(i, {"float": [], "grid": []})["float"] += imgs   # before the paragraph
                continue
        points.setdefault(end + 1, {"float": [], "grid": []})["grid"] += imgs      # after the block
    out = list(lines)
    for pos in sorted(points, reverse=True):
        new = []
        if points[pos]["grid"]:
            token = f"GALLERYPLACEHOLDER{len(TOKENS)}"
            TOKENS[token] = gallery_html(points[pos]["grid"])
            new += ["", token, ""]
        if points[pos]["float"]:
            token = f"FLOATPLACEHOLDER{len(TOKENS)}"
            TOKENS[token] = "".join(gfig_html(img, "gfig float") for img in points[pos]["float"])
            new += ["", token, ""]
        out[pos:pos] = new
    return out


_map_count = Counter()
PLACE_KIND = {"night": "night halt", "end": "start / end", "stop": "stop", "pass": "pass", "check": "checkpost",
              "fuel": "fuel", "book": "in the text"}


def map_html(entry):
    """An inline SVG map or diagram: inherits the page's fonts, colours and dark mode, works offline.
    Ids inside the SVG get a per-instance suffix so the same drawing can appear twice."""
    src = (SPITI / "book" / "img" / entry["file"]).read_text(encoding="utf-8")
    _map_count[entry["file"]] += 1
    n = _map_count[entry["file"]]
    if entry.get("mode") == "img":
        # self-contained drawings with their own styles and dark mode: kept isolated in an <img>
        head = src[:3000]
        w, h = re.search(r'<svg[^>]*\bwidth="([\d.]+)"', head), re.search(r'<svg[^>]*\bheight="([\d.]+)"', head)
        title = re.search(r"<title[^>]*>([^<]*)</title>", head)
        alt = entry.get("alt") or (html.unescape(title.group(1)) if title else entry["caption"])
        stem = Path(entry["file"]).stem + ("" if n == 1 else f"-{n}")
        return (f'<figure class="map-fig diagram" id="fig-{stem}"><img src="img/{entry["file"]}" alt="{html.escape(alt)}" '
                f'{f"width={chr(34)}{w.group(1)}{chr(34)} height={chr(34)}{h.group(1)}{chr(34)} " if w and h else ""}'
                f'loading="lazy" decoding="async"><figcaption>{inline(entry["caption"])} '
                f'<span class="credit">{html.escape(entry.get("credit", "Drawn for this book."))}</span></figcaption></figure>')
    svg = re.sub(r"<\?xml[^>]*>\s*", "", src)
    if n > 1:
        for i in set(re.findall(r'\sid="([^"]+)"', svg)):
            svg = re.sub(rf'(["#(\s]){re.escape(i)}(["\s)])', rf"\g<1>{i}-{n}\g<2>", svg)
    stem = Path(entry["file"]).stem + ("" if n == 1 else f"-{n}")
    places = ""
    if entry.get("places"):
        items = "".join(
            f'<li>{html.escape(p["name"])} <span>· {" · ".join(PLACE_KIND.get(k, k) for k in [p["kind"], *p.get("also", [])])}'
            f'{" · " + html.escape(p["note"]) if p.get("note") else ""}{" · position approximate" if p.get("approx") else ""}</span></li>'
            for p in entry["places"])
        places = f'<details class="map-places"><summary>Places on this map</summary><ul>{items}</ul></details>'
    credit = entry.get("credit", "Map data © OpenStreetMap contributors (ODbL); drawn for this book.")
    return (f'<figure class="map-fig" id="{stem}">{svg}<figcaption>{inline(entry["caption"])} '
            f'<span class="credit">{html.escape(credit)}</span></figcaption>{places}</figure>')


def figure_html(img, hero=False):
    cap = f"{inline(img['caption'])} " if img.get("caption") else ""
    credit = clean_credit(img.get("credit"))
    # T5.3: when the alt text would only repeat the visible caption, leave alt empty so screen readers
    # read the caption once (the figcaption names the figure)
    alt = img.get("alt") or ""
    if alt.strip() == (img.get("caption") or "").strip():
        alt = ""
    return (f'<figure class="fig{" hero" if hero else ""}" id="{fig_id(img)}">'
            f'<img src="img/{img["file"]}" alt="{html.escape(alt)}" '
            f'width="{img["w"]}" height="{img["h"]}" loading="lazy" decoding="async">'
            f'<figcaption>{cap}<span class="credit">{html.escape(credit) + " · " if credit else ""}'
            f'<a href="{html.escape(img["source"])}" target="_blank" rel="noopener">{html.escape(img["license"])}</a>'
            f'</span></figcaption></figure>')


def render_body(lines, prefix, figs=None):
    """Render a section body; wrap the recurring boxes in <aside>; place each heading's
    figures after its first paragraph. Returns (html, toc)."""
    out, h2s, h3s, buf = [], [], [], []
    box_level, pending, placed = None, None, {}
    figs = {} if figs is None else figs

    def place():
        nonlocal pending
        token = f"FIGUREPLACEHOLDER{len(placed)}"
        placed[token], pending = pending, None
        buf.extend(["", token, ""])

    def flush():
        if pending:
            place()
        if any(l.strip() for l in buf):
            chunk = md(buf)
            for token, fig in placed.items():
                chunk = chunk.replace(f"<p>{token}</p>", fig)
            out.append(chunk)
        buf.clear()

    for line in lines:
        m = re.match(r"^(#{2,4}) (.+)$", line)
        if not m:
            if pending and not line.strip() and any(l.strip() and not re.match(r"(GALLERY|FLOAT)PLACEHOLDER", l) for l in buf):
                place()
            buf.append(line)
            continue
        flush()
        level, text = len(m.group(1)), m.group(2).strip()
        pending = figs.pop(plain(text), None)
        if box_level is not None and level <= box_level:
            out.append("</aside>")
            box_level = None
        hid = slug(text, prefix)
        label, sep, rest = text.partition(":")
        kind = BOXES.get(label.strip()) if sep else None
        if kind and box_level is None:
            rest = rest.strip()
            out.append(f'<aside class="box box-{kind}"><div class="box-label">{html.escape(label.strip())}</div>')
            out.append(f'<h{level} id="{hid}">{inline(rest[:1].upper() + rest[1:])}</h{level}>')
            box_level = level
        elif hist := re.fullmatch(r"([A-Z][a-z]+(?: [a-z]+)? section|PART [A-Z]+)\s*·\s*(.+)", text):
            # a labelled heading rather than a box: these sections don't mark where they end
            out.append(f'<div class="h-label">{hist[1].capitalize() if hist[1].startswith("PART") else hist[1]}</div>'
                       f'<h{level} id="{hid}" class="labelled">{inline(hist[2])}</h{level}>')
        else:
            out.append(f'<h{level} id="{hid}">{inline(text)}</h{level}>')
        (h2s if level == 2 else h3s if level == 3 else []).append((hid, plain(text)))
    flush()
    if box_level is not None:
        out.append("</aside>")
    return "\n".join(out), (h2s or h3s)


XREF = re.compile(r"\b(Chapters?|Interludes?) (\d+|[IVX]+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve)\b")
XREF_ALLOW = ROOT / "content" / "xref-allow.txt"   # one context substring per line: accepted mentions
_STOP = set("""the a an and or of in on at to for from with by as is it its this that these those you your he his she her
they them we our not but be are was were been has have had will would can could into over under than then there here what
which who when where why how all any each some more most very also just only even such about after before again still
chapter chapters interlude interludes see read short version detail same other first last whole part does done been""".split())


def plain_text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment))


def xref_target(kind, num):
    if kind.startswith("Chapter"):
        return f"ch-{num}" if num.isdigit() else None
    k = ROMAN.index(num) + 1 if num in ROMAN else WORDS.index(num) + 1 if num in WORDS else None
    return f"interlude-{k}" if k else None


def check_reference_numbers(md, errors):
    """T0.6 (b): catch a "Chapter N" / "Interlude N" whose sentence is clearly about another section.

    The words of the sentence holding the mention (plus the previous sentence when it says little
    on its own) are scored against every section of the same kind, weighted by how rare each word is
    across the book. It is an error when another section scores at least 5 and at least 1.5x the one
    named. Tuned on the stale references fixed in September 2026: catches 12 of 16 with no false
    alarms; mentions with almost no words around them ("Chapter 12.") cannot be judged. Accept a
    deliberate mention by adding a substring of its line to content/xref-allow.txt."""
    allow = [l.strip() for l in XREF_ALLOW.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")] if XREF_ALLOW.exists() else []
    saved = set(_used_ids)
    lines, heads, texts, sec = md.splitlines(), {}, {}, None
    for n, line in enumerate(lines):
        if m := re.match(r"^# (.+)$", line):
            _used_ids.clear()
            sec = heads[n] = classify(m.group(1).strip())[0]
            texts[sec] = [m.group(1)]
        elif sec:
            texts[sec].append(line)
    _used_ids.clear()
    _used_ids.update(saved)

    word = re.compile(r"[A-Za-z][A-Za-z’'-]{3,}")
    toks = lambda t: {w.lower() for w in word.findall(t)} - _STOP
    sec_words = {k: toks("\n".join(v)) for k, v in texts.items()}
    df = Counter(w for ws in sec_words.values() for w in ws)
    idf = {w: math.log(len(sec_words) / c) for w, c in df.items()}
    titles = {k: v[0] for k, v in texts.items()}

    sec, prev = None, ""
    for n, line in enumerate(lines):
        if n in heads:
            sec, prev = heads[n], ""
            continue
        if not line.strip() or line.startswith(("|", "#")):
            continue
        if not any(a in line for a in allow):
            sentences = re.split(r"(?<=[.!?])\s+", line)
            for mm in XREF.finditer(line):
                pos, idx = 0, 0
                for i, sentence in enumerate(sentences):
                    if pos <= mm.start() < pos + len(sentence) + 1:
                        idx = i
                        break
                    pos += len(sentence) + 1
                ctx = sentences[idx]
                if len(word.findall(XREF.sub("", ctx))) < 5:
                    ctx = (sentences[idx - 1] if idx else prev) + " " + ctx
                tid = xref_target(mm.group(1), mm.group(2))
                if tid not in sec_words:
                    continue   # reported as missing when the mention is linked
                cw = toks(XREF.sub("", ctx))
                scores = {k: sum(idf[w] for w in cw if w in ws) for k, ws in sec_words.items()
                          if k.split("-")[0] == tid.split("-")[0] and k != sec}
                best = max(scores, key=scores.get)
                if best != tid and scores[best] >= 5.0 and scores[best] >= 1.5 * max(scores.get(tid, 0), 0.01):
                    errors.append(f"line {n + 1}: {mm.group(0)} probably means {titles[best]!r}, not "
                                  f"{titles[tid]!r} — “…{ctx.strip()[:120]}…”")
        prev = line


def link_and_check_references(sections, errors, warnings):
    """T0.6 (a): every "Chapter N" / "Interlude N" in prose becomes a link to that section, and the
    section must exist."""
    titles = {s["id"]: s["here"] for s in sections}
    target = xref_target

    for s in sections:
        out, prev = [], ""
        for block in re.split(r"(?=<(?:p|li|td|h[1-6])\b)", s["body"]):
            ctx = plain_text(block)
            context = ctx if len(ctx.strip()) >= 80 else prev + " " + ctx
            parts, depth_a, depth_h, rebuilt = re.split(r"(<[^>]+>)", block), 0, 0, []
            for part in parts:
                if part.startswith("<"):
                    tag = re.match(r"</?\s*(\w+)", part)
                    name = tag.group(1).lower() if tag else ""
                    step = -1 if part.startswith("</") else (0 if part.endswith("/>") else 1)
                    if name == "a":
                        depth_a += step
                    elif re.fullmatch(r"h[1-6]", name):
                        depth_h += step
                    rebuilt.append(part)
                    continue
                if depth_a or depth_h:
                    rebuilt.append(part)
                    continue

                def repl(m):
                    tid = target(m.group(1), m.group(2))
                    where = f"{titles[s['id']]}: …{context.strip()[:110]}…"
                    if not tid or tid not in titles:
                        errors.append(f"{m.group(0)} does not exist ({where})")
                        return m.group(0)
                    return f'<a class="xref" href="#{tid}">{m.group(0)}</a>'
                rebuilt.append(XREF.sub(repl, part))
            out.append("".join(rebuilt))
            if ctx.strip():
                prev = ctx
        s["body"] = "".join(out)


def check_links(page, errors):
    """T0.6 (a) and (c): every #link resolves, no id is used twice."""
    ids = re.findall(r'\sid="([^"]+)"', page)
    counts = Counter(ids)
    for i, n in counts.items():
        if n > 1:
            errors.append(f'id="{i}" is used {n} times')
    known = set(ids)
    for h in sorted(set(re.findall(r'href="#([^"]+)"', page))):
        if "${" in h:          # a template literal in the page's own script, filled in at runtime
            continue
        if h not in known:
            errors.append(f"link to #{h} points at nothing")


def split_on(lines, pattern):
    """Split lines into [(heading_text|None, body_lines)] at lines matching pattern."""
    parts = [(None, [])]
    for line in lines:
        m = re.match(pattern, line)
        if m:
            parts.append((m.group(1).strip(), []))
        else:
            parts[-1][1].append(line)
    return parts


def classify(title):
    """'Interlude One · The People of the Road' -> (id, nav number, kind, label, name)."""
    m = re.match(r"^(.+?)\s+·\s+(.+)$", title)
    label, name = (m.group(1).strip(), m.group(2).strip()) if m else ("", title)
    if mm := re.fullmatch(r"Chapter (\d+)", label):
        return f"ch-{mm[1]}", mm[1], "chapter", label, name
    if mm := re.fullmatch(r"Interlude (\w+)", label):
        k = WORDS.index(mm[1]) + 1 if mm[1] in WORDS else ROMAN.index(mm[1]) + 1 if mm[1] in ROMAN else None
        return (f"interlude-{k}", ROMAN[k - 1], "interlude", label, name) if k else \
            (slug(title), mm[1], "interlude", label, name)
    if mm := re.fullmatch(r"Appendix ([A-Z])", label):
        return f"appendix-{mm[1].lower()}", mm[1], "appendix", label, name
    if label == "Coda":
        return "coda", "", "coda", label, name
    if label == "Sidebar":
        return slug(name, "sidebar"), "", "sidebar", label, name
    return slug(title), "", "back", label, name


def main(src=SRC, write=True):
    errors, warnings = [], []
    md_text = Path(src).read_text(encoding="utf-8")
    check_reference_numbers(md_text, errors)
    lines = md_text.splitlines()
    blocks = [b for b in split_on(lines, r"^# (.+)$") if b[0]]

    # ---- cover (first H1 block, up to its first rule) ----
    book_title, front = blocks[0]
    rule = front.index("---")
    cover_lines = [l for l in front[:rule] if l.strip()]
    subtitle = next((l.lstrip("# ").strip() for l in cover_lines if l.startswith("###")), "")
    tagline = next((l.strip("* ") for l in cover_lines if l.startswith("*")), "")

    # ---- images: anchor (chapter title or heading text) -> figure html ----
    images = json.loads(IMAGES.read_text(encoding="utf-8")) if IMAGES.exists() else []
    figs, items = {}, {}
    for img in images:
        if img.get("after"):
            items.setdefault((img["anchor"], img["after"]), []).append(img)
        else:
            figs[img["anchor"]] = figs.get(img["anchor"], "") + figure_html(img)
    # maps: under a chapter's hero image when anchored to a chapter title, else after a heading's first paragraph
    maps = [json.loads(f.read_text(encoding="utf-8")) for f in (MAPS, FIGURES) if f.exists()]
    section_maps, maps = {}, [m for group in maps for m in group]
    chapter_names = ({classify(t)[3 + 1] for t, _ in blocks[1:]}
                     | {t for t, _ in split_on(front[rule:], r"^## (.+)$") if t})
    _used_ids.clear()
    for m in maps:
        if m["anchor"] in chapter_names:
            section_maps[m["anchor"]] = section_maps.get(m["anchor"], "") + map_html(m)
        else:
            figs[m["anchor"]] = figs.get(m["anchor"], "") + map_html(m)

    # ---- chapters, interludes, sidebars, appendices ----
    sections, colophon = [], ""
    for bi, (title, body) in enumerate(blocks[1:], start=1):
        sid, n, kind, label, name = classify(title)
        _used_ids.add(sid)
        hero = figs.pop(name, "").replace('class="fig"', 'class="fig hero"') + section_maps.pop(name, "")

        # meta lines (**Day 1 · …** or *Read this …*) directly under the title
        i, meta = 0, []
        while i < len(body):
            s = body[i].strip()
            if s and not re.fullmatch(r"\*\*[^*]+\*\*|\*[^*]+\*", s):
                break
            if s:
                italic = not s.startswith("**")
                meta.append((inline(s.strip("*").strip()), italic))
            i += 1
        body = body[i:]

        # a lone italic line after the final rule of the book is the colophon
        if bi == len(blocks) - 1 and "---" in body:
            last = len(body) - 1 - body[::-1].index("---")
            tail = [l for l in body[last + 1:] if l.strip()]
            if len(tail) == 1 and re.fullmatch(r"\*[^*].*\*", tail[0].strip()):
                colophon = inline(tail[0].strip())
                body = body[:last]
        body = inject_items([l for l in body if l.strip() != "---"], name, items)

        body_html, toc = render_body(body, sid, figs)
        sections.append(dict(id=sid, n=n, kind=kind, label=label, title=name,
                             here=f"{label} · {name}" if label else name,
                             meta=meta, body=body_html, toc=toc, hero=hero))

    if images:
        seen, credit_items = set(), []
        for i in images:
            if i["anchor"] in figs or (i["anchor"], i.get("after")) in items or i["file"] in seen:
                continue
            seen.add(i["file"])
            credit_items.append(
                f'<li><a href="#fig-{Path(i["file"]).stem}">{html.escape(plain(i.get("caption") or i.get("after") or i["anchor"]))}</a>'
                f'{" — " + html.escape(clean_credit(i["credit"])) if clean_credit(i["credit"]) else ""}, '
                f'<a href="{html.escape(i["source"])}" target="_blank" rel="noopener">'
                f'{html.escape(i["license"])}</a></li>')
        credit_items = "".join(credit_items)
        _used_ids.add("image-credits")
        sections.append(dict(
            id="image-credits", n="", kind="back", label="", title="Image credits", here="Image credits",
            meta=[("Photographs and artwork from Wikimedia Commons and Wikipedia. "
                   "Each link goes to the original file, with its author and licence.", True)],
            body=f'<ol class="credits">{credit_items}</ol>', toc=[], hero=""))

    # ---- front matter; the Contents section also yields sidebar groups and "when" notes ----
    by_title = {s["title"].lower(): s["id"] for s in sections}
    ids = {s["id"] for s in sections}
    when, group_of = {}, {}

    def row_target(num, name):
        if num.isdigit():
            return f"ch-{num}"
        if num in ROMAN:
            return f"interlude-{ROMAN.index(num) + 1}"
        key = re.sub(r"^sidebar:\s*", "", plain(name).lower())
        return "coda" if key.startswith("coda") else by_title.get(key)

    front_sections = []
    for title, body in split_on(front[rule:], r"^## (.+)$"):
        if not title:
            continue
        sid = {"How to use this": "how-to-use", "Contents": "contents"}.get(title) or slug(title)
        _used_ids.add(sid)
        if sid == "contents":
            group, linked = None, []
            for l in body:
                g = re.fullmatch(r"\*\*([^*]+)\*\*(.*)", l.strip())
                row = re.fullmatch(r"\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|", l.strip())
                if g:
                    group = g[1].strip()

                    def appendix(m, group=group):
                        target = f"appendix-{m[1].lower()}"
                        group_of.setdefault(target, group)
                        return f"[{m[0].strip()}](#{target})" if target in ids else m[0]
                    l = f"**{group}**" + re.sub(r"(?:Appendix )?\b([A-Z]): [^·]+?(?=\s*·|\s*$)", appendix, g[2])
                elif row and row[2] and not re.fullmatch(r"[-: ]+", row[2]):
                    target = row_target(row[1], row[2])
                    if target in ids:
                        group_of.setdefault(target, group)
                        if row[3]:
                            when[target] = plain(row[3])
                        l = f"| {row[1]} | [{row[2]}](#{target}) | {row[3]} |"
                linked.append(l)
            body = linked
        body_html, toc = render_body(inject_items([l for l in body if l.strip() != "---"], title, items), sid, figs)
        front_sections.append(dict(id=sid, n="", kind="front", label="Before you start", title=title,
                                   here=title, meta=[], body=body_html, toc=toc, hero=section_maps.pop(title, "")))
    sections = front_sections + sections
    for anchor in list(figs) + list(section_maps):
        errors.append(f"image or map anchor {anchor!r} matches no chapter or heading (renamed?)")
    for anchor, after in items:
        errors.append(f"image anchor {after!r} under {anchor!r} matches no bold item (renamed?)")
    link_and_check_references(sections, errors, warnings)

    # glossary popovers (T2.7), A–Z index (T2.8), search records (T2.1), today (T2.9)
    gloss_data = spiti_extras.link_glossary(sections, spiti_extras.parse_glossary(md_text))
    index = spiti_extras.index_section(sections, ROOT / "content" / "index-terms.yml", warnings)
    if index:
        _used_ids.add("index")
        at = next((i for i, s in enumerate(sections) if s["id"] == "image-credits"), len(sections))
        sections.insert(at, index)
    search_docs = spiti_extras.search_records(sections)
    today_data = spiti_extras.today_links(ROOT / "content" / "today.json", sections, errors)

    # ---- sidebar: document order, a new group header whenever the Contents group changes ----
    def nav_item(s):
        sub = "".join(f'<li><a href="#{hid}">{html.escape(t)}</a></li>' for hid, t in s["toc"])
        note = " · ".join(x for x in ("Sidebar" if s["kind"] == "sidebar" else "", when.get(s["id"], "")) if x)
        return (f'<li class="k-{s["kind"]}"><a class="sec" href="#{s["id"]}"><span class="n">{s["n"]}</span>'
                f'<span class="t">{html.escape(s["title"])}'
                f'{f"<small>{html.escape(note)}</small>" if note else ""}</span></a>'
                f'{f"<ol class=sub>{sub}</ol>" if sub else ""}</li>')

    nav, current = [], None
    for s in sections:
        g = "Start here" if s["kind"] == "front" else group_of.get(s["id"], current)
        if g != current:
            if current is not None:
                nav.append("</ol>")
            nav.append(f'<div class="toc-group">{html.escape(g or "")}</div><ol class="toc-list">')
            current = g
        nav.append(nav_item(s))
    nav.append("</ol>")

    # ---- sections ----
    def section_html(s):
        kicker = f'<div class="kicker">{html.escape(s["label"])}</div>' if s["label"] else ""
        meta = "".join(f'<p class="meta{" note" if it else ""}">{x}</p>' for x, it in s["meta"])
        return (f'<section class="chapter k-{s["kind"]}" id="{s["id"]}" data-section data-here="{html.escape(s["here"])}">'
                f'<header class="chapter-head">{kicker}'
                f'<h1>{html.escape(s["title"])}</h1>{meta}</header>{s["hero"]}'
                f'<div class="chapter-body">{s["body"]}</div></section>')

    page = (TEMPLATE
            .replace("%%DARK%%", DARK_TOKENS)
            .replace("%%BOOK_TITLE%%", html.escape(book_title))
            .replace("%%SUBTITLE%%", html.escape(subtitle))
            .replace("%%TAGLINE%%", html.escape(tagline))
            .replace("%%NAV%%", "".join(nav))
            .replace("%%SECTIONS%%", "\n".join(section_html(s) for s in sections))
            .replace("%%COLOPHON%%", colophon)
            .replace("%%ROUTE_MAP%%", route_map_html())
            .replace("%%EXTRA_DATA%%", spiti_extras.data_scripts(gloss_data, today_data))
            .replace("%%MAP_URL%%", html.escape(MAP_URL)))
    check_links(page, errors)
    if write:
        OUT.write_text(page, encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)} ({len(sections)} sections, {len(images)} images)")
        index_json = json.dumps({"docs": [{k: v for k, v in d.items() if k not in ("st", "k")} for d in search_docs],
                                 "aliases": spiti_extras.load_aliases(SPITI / "book" / "search-aliases.json")},
                                ensure_ascii=False, separators=(",", ":"))
        (OUT.parent / "search-index.json").write_text(index_json, encoding="utf-8")
        import gzip
        print(f"wrote spiti/book/search-index.json ({len(search_docs)} records, "
              f"{len(index_json.encode()) / 1024:.0f} KB, {len(gzip.compress(index_json.encode())) / 1024:.0f} KB gzipped)")
        spiti_extras.build_practical(SPITI / "practical" / "practical.md", SPITI / "practical" / "index.html",
                                     render_body, inline, TEMPLATE, DARK_TOKENS, errors)
        spiti_extras.write_unverified(ROOT, warnings)
        spiti_extras.write_shot_list(ROOT, images, sections)
        write_service_worker()
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    if errors:
        print(f"{len(errors)} error(s) — fix the markdown, or accept a cross-reference in "
              f"{XREF_ALLOW.relative_to(ROOT)}", file=sys.stderr)
    return 1 if errors else 0


RIDGE = ('<svg class="ridge" viewBox="0 0 150 34" fill="none" stroke="currentColor" stroke-width="1.4" '
         'stroke-linejoin="round" stroke-linecap="round" aria-hidden="true"><path d="M1 33 24 14l10 8 22-21 16 15 9-6 '
         '20 17 11-9 18 15"/><path d="M50 7l6-6 6 6-3-1-3 3-3-3Z" fill="currentColor" stroke-width="1"/></svg>')


def route_map_html():
    """The route drawn over OpenStreetMap (made by scripts/build_route_map.py), or the ridge ornament."""
    base, overlay = SPITI / "book/img/route-map-base.webp", SPITI / "book/img/route-map-overlay.svg"
    if not (base.exists() and overlay.exists()):
        return RIDGE
    vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', overlay.read_text(encoding="utf-8"))
    ratio = f"{float(vb[1]):.1f} / {float(vb[2]):.1f}" if vb else "1"
    num = float(vb[1]) / float(vb[2]) if vb else 1
    return (f'<figure class="route-map" style="--map-ratio:{num:.4f}">'
            f'<div class="route-map-stack" style="aspect-ratio:{ratio}">'
            '<img src="img/route-map-base.webp" alt="" fetchpriority="high" decoding="async">'
            '<img class="overlay" src="img/route-map-overlay.svg" '
            'alt="Route map: Shimla, Sarahan, Chitkul, Kalpa, Nako, Tabo, Mud, Kaza, Losar, Kunzum La, Chandratal, Manali">'
            '</div><figcaption>The route, night by night. Map data © '
            '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>.'
            '</figcaption></figure>')


def write_service_worker():
    """spiti/sw.js precaches every file of the site; its VERSION is a hash of their contents,
    so any change to the site makes installed copies offer an update."""
    files = []
    for p in sorted(SPITI.rglob("*")):
        rel = p.relative_to(SPITI).as_posix()
        build_only = {"book/images.json", "book/maps.json", "book/figures.json", "book/search-aliases.json",
                      "book/vendor/README.txt"}
        if p.is_dir() or p.suffix in (".md", ".zip") or p.name == "sw.js" or rel in build_only \
                or any(part.startswith(".") for part in rel.split("/")):
            continue
        files.append(rel)
    digest = hashlib.sha256()
    for rel in files:
        digest.update(rel.encode())
        digest.update((SPITI / rel).read_bytes())
    version = digest.hexdigest()[:8]
    urls = [["./" if f == "index.html" else f.removesuffix("index.html") if f.endswith("/index.html") else f,
             (SPITI / f).stat().st_size, hashlib.sha256((SPITI / f).read_bytes()).hexdigest()[:12]]
            for f in files]
    sw = (SW_TEMPLATE.replace("%%VERSION%%", version)
          .replace("%%PRECACHE%%", "[\n" + ",\n".join(json.dumps(u) for u in urls) + "\n]")
          .replace("%%EXTERNAL%%", json.dumps(EXTERNAL, indent=1))
          .replace("%%RUNTIME_HOSTS%%", json.dumps(RUNTIME_HOSTS)))
    (SPITI / "sw.js").write_text(sw, encoding="utf-8")
    size = sum((SPITI / f).stat().st_size for f in files) / 1e6
    print(f"wrote spiti/sw.js (version {version}, {len(urls)} files, {size:.1f} MB)")


SW_TEMPLATE = r"""// Generated by scripts/build_spiti_book.py — do not edit by hand.
// Caches the whole spiti/ site for offline use. Each build gets a new VERSION; installed
// copies then download the new files in the background and pages offer "Update" (pwa.js).
const VERSION = "%%VERSION%%";
const CACHE = `spiti-${VERSION}`;
const RUNTIME = "spiti-runtime";
const PRECACHE = %%PRECACHE%%;
const EXTERNAL = %%EXTERNAL%%;
const RUNTIME_HOSTS = %%RUNTIME_HOSTS%%;   // third-party hosts worth keeping offline; map tiles are not
const keepable = url => RUNTIME_HOSTS.includes(new URL(url).hostname);

const fill = (cache, url) =>
  cache.match(url, { ignoreVary: true })
    .then(hit => hit || fetch(url, { mode: "cors" }).then(res => res.ok && cache.put(url, res)))
    .catch(() => {});

const TOTAL_BYTES = PRECACHE.reduce((n, [, size]) => n + size, 0);
const tell = async msg => {
  for (const c of await self.clients.matchAll({ includeUncontrolled: true, type: "window" })) c.postMessage(msg);
};

// PRECACHE is [url, bytes, content hash]. Files whose hash matches the previous version are copied from
// the old cache instead of downloaded again, so an update only fetches what actually changed.
self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    const old = [];
    for (const key of await caches.keys())
      if (key.startsWith("spiti-") && key !== CACHE && key !== RUNTIME) old.push(await caches.open(key));
    const queue = PRECACHE.slice();
    let done = 0, bytes = 0, last = 0, reused = 0;
    const progress = async force => {
      if (!force && Date.now() - last < 250) return;
      last = Date.now();
      await tell({ type: "progress", version: VERSION, done, total: PRECACHE.length, bytes, totalBytes: TOTAL_BYTES });
    };
    const one = async ([url, size, hash]) => {
      for (const c of old) {
        const hit = await c.match(url);
        if (hit && hit.headers.get("x-spiti-hash") === hash) {
          await cache.put(url, hit);
          reused++;
          return;
        }
      }
      const res = await fetch(new Request(url, { cache: "reload" }));
      if (!res.ok) throw new Error(`${url} (${res.status})`);
      const headers = new Headers(res.headers);
      headers.set("x-spiti-hash", hash);
      await cache.put(url, new Response(await res.blob(), { status: res.status, statusText: res.statusText, headers }));
    };
    const worker = async () => {
      while (queue.length) {
        const item = queue.shift();
        await one(item);
        done++;
        bytes += item[1];
        progress(false);
      }
    };
    try {
      await Promise.all(Array.from({ length: 6 }, worker));
    } catch (err) {
      await tell({ type: "install-failed", version: VERSION, error: String(err.message || err) });
      throw err;
    }
    await progress(true);
    const runtime = await caches.open(RUNTIME);
    await Promise.all(EXTERNAL.map(url => fill(runtime, url)));
    await tell({ type: "installed", version: VERSION, files: PRECACHE.length, bytes: TOTAL_BYTES, reused });
  })());
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys())
      if (key.startsWith("spiti-") && key !== CACHE && key !== RUNTIME) await caches.delete(key);
    await self.clients.claim();
  })());
});

self.addEventListener("message", event => {
  const data = event.data || {};
  if (data.type === "skip-waiting") self.skipWaiting();
  if (data.type === "version" && event.source) event.source.postMessage({ type: "version", version: VERSION });
  if (data.type === "status" && event.source)
    event.waitUntil(caches.open(CACHE).then(c => c.keys()).then(keys => event.source.postMessage({
      type: "status", version: VERSION, files: PRECACHE.length, have: keys.length, bytes: TOTAL_BYTES,
      complete: keys.length >= PRECACHE.length })));
  if (data.type === "cache" && Array.isArray(data.urls))
    event.waitUntil(caches.open(RUNTIME).then(runtime => Promise.all(
      data.urls.filter(keepable).map(url => fill(runtime, url)))));
});

self.addEventListener("fetch", event => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (url.origin === location.origin) {
    if (!url.pathname.startsWith(new URL(self.registration.scope).pathname)) return;
    // the site itself: cache first; new content arrives through a service-worker update
    event.respondWith((async () => {
      const cache = await caches.open(CACHE);
      const hit = await cache.match(request, { ignoreSearch: true });
      if (hit) return hit;
      try {
        return await fetch(request);
      } catch (err) {
        if (request.mode === "navigate")
          return (await cache.match(url.pathname.replace(/[^/]*$/, ""))) || (await cache.match("./"));
        throw err;
      }
    })());
    return;
  }

  // fonts and scripts from other sites: cache first, filled on first use.
  // Anything else (map tiles) goes straight to the network so it cannot fill the phone's storage.
  if (!keepable(request.url)) return;
  event.respondWith((async () => {
    const runtime = await caches.open(RUNTIME);
    const hit = await runtime.match(request, { ignoreVary: true });
    if (hit) return hit;
    const res = await fetch(request);
    if (res.ok || res.type === "opaque") runtime.put(request, res.clone());
    return res;
  })());
});
"""


DARK_TOKENS = """
  --bg:#161513; --surface:#211f1c; --surface-2:#2a2723; --text:#e8e2d7; --muted:#a29a8f;
  --accent:#d6a35a; --accent-strong:#e6bb78;
  --rock:#9d9891; --people:#8fa3b5;
  --divider:color-mix(in srgb,#e8e2d7 13%,transparent);
  --shadow:0 12px 32px rgba(0,0,0,.5);
  --practical:#6FA8C7; --caution:#D9A441; --respect:#7FA86F; --route:#5d9bd6; --route-alt:#8A8A85;
  --practical-ink:#9ccbe4; --caution-ink:#ecc16f; --respect-ink:#a9cf99;
  --map-land:#23211e; --map-water:#2f5068; --map-water-label:#8fb8d4; --map-road:#57524a; --map-boundary:#7a7268;
  --map-label:#e8e2d7; --map-muted:#a29a8f; --map-halo:#161513;
  color-scheme:dark;
"""

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Long Read · Spiti Circuit</title>
<meta name="description" content="History, geology, myth and old travel writing for the Shimla – Kinnaur – Spiti – Chandratal – Manali road, chapter by chapter.">
<meta name="theme-color" content="#201f1d">
<link rel="manifest" href="../manifest.webmanifest">
<link rel="apple-touch-icon" href="../icons/apple-touch-icon.png">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Spiti">
<script src="../pwa.js" defer></script>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📖</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=Lora:ital,wght@0,400;0,600;1,400&display=swap">
<script>try{var t=localStorage.getItem("spiti-theme");if(t)document.documentElement.dataset.theme=t}catch(e){}</script>
<!-- generated by scripts/build_spiti_book.py from spiti-circuit-the-long-read.md; edit the markdown, not this file -->
<style>
:root{
  --bg:#f3f2f2; --surface:#eae7e3; --surface-2:#e2ded8; --text:#201f1d; --muted:#6b6661;
  --accent:#a06f24; --accent-strong:#7d5411;
  --rock:#7d7979; --people:#5d7285;
  --divider:color-mix(in srgb,#201f1d 14%,transparent);
  --shadow:0 12px 32px color-mix(in srgb,#2d2b2b 22%,transparent);
  /* actionable boxes are cool, interpretive boxes warm (todo: colour system) */
  --practical:#6FA8C7; --caution:#D9A441; --respect:#7FA86F; --route:#3F7FBF; --route-alt:#8A8A85;
  --practical-ink:#2d6385; --caution-ink:#8a5c12; --respect-ink:#3f6b31;
  --map-land:#ece8e1; --map-water:#a9c9de; --map-water-label:#3b6e8f; --map-road:#c4bdb1; --map-boundary:#a39a8e;
  --map-label:#201f1d; --map-muted:#6b6661; --map-halo:#f3f2f2;
  --display:"Cormorant Garamond",Georgia,serif;
  --serif:"Lora",Georgia,serif;
  --top:52px; --side:310px;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){%%DARK%%}}
:root[data-theme="dark"]{%%DARK%%}
/* T6.5: a dimmer, warmer night mode for reading in a tent, and three text sizes */
:root[data-theme="night"]{%%DARK%%
  --bg:#0b0a09; --surface:#15130f; --surface-2:#1c1915; --text:#b9a487; --muted:#8c7c66;
  --accent:#9d7443; --accent-strong:#b98a50; --rock:#7d766c; --people:#7c8b96;
  --practical:#5c8199; --caution:#a8823c; --respect:#6c8a60; --route:#7d8fa3;
  --practical-ink:#8fb0c4; --caution-ink:#c9a462; --respect-ink:#9bb38f;
  --map-land:#12100d; --map-water:#243644; --map-water-label:#7d97a8; --map-road:#3d3831; --map-label:#b9a487;
  --map-muted:#8c7c66; --map-halo:#0b0a09; --divider:color-mix(in srgb,#b9a487 12%,transparent);}
:root[data-theme="night"] img{filter:brightness(.6) sepia(.25)}
:root[data-size="s"] body{font-size:16px}
:root[data-size="l"] body{font-size:20.5px}

*,*::before,*::after{box-sizing:border-box}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition:none!important}}
body{margin:0;background:var(--bg);color:var(--text);font:400 18px/1.75 var(--serif);overflow-x:hidden}
a{color:var(--accent-strong);text-underline-offset:3px;text-decoration-thickness:1px}
::selection{background:color-mix(in srgb,var(--accent) 30%,transparent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* ---- top bar ---- */
.topbar{position:fixed;inset:0 0 auto 0;height:var(--top);z-index:40;display:flex;align-items:center;gap:4px;padding:0 8px;
  background:color-mix(in srgb,var(--bg) 90%,transparent);-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);
  border-bottom:1px solid var(--divider)}
.progress{position:absolute;left:0;right:0;bottom:-1px;height:2px;background:var(--accent);transform-origin:0 50%;transform:scaleX(0)}
.icon-btn{flex:none;appearance:none;border:0;background:none;color:inherit;width:44px;height:44px;display:grid;place-items:center;border-radius:8px;cursor:pointer;text-decoration:none}
.icon-btn:hover{background:var(--surface)}
.icon-btn svg{width:20px;height:20px}
.brand{flex:none;width:calc(var(--side) - 16px);padding-left:12px;font:600 20px/1 var(--display);color:inherit;text-decoration:none;letter-spacing:.01em}
.here{flex:1;min-width:0;appearance:none;border:0;background:none;color:inherit;text-align:left;cursor:pointer;padding:6px 8px;border-radius:8px;
  font:500 17px/1.2 var(--display);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.here:hover{background:var(--surface)}

/* ---- sidebar / drawer ---- */
.sidebar{position:fixed;top:var(--top);bottom:0;left:0;width:var(--side);z-index:35;overflow-y:auto;overscroll-behavior:contain;
  background:var(--bg);border-right:1px solid var(--divider);padding:12px 10px 48px;scrollbar-width:thin}
.toc-group{font:600 11.5px/1.2 var(--display);letter-spacing:.16em;text-transform:uppercase;color:var(--muted);padding:22px 12px 8px}
.toc-list,.sub{list-style:none;margin:0;padding:0}
.sec{display:flex;gap:10px;padding:7px 12px;border-radius:8px;color:inherit;text-decoration:none;line-height:1.25}
.sec:hover{background:var(--surface)}
.sec .n{flex:none;width:22px;text-align:right;font:500 16px/1.3 var(--display);color:var(--muted);font-variant-numeric:tabular-nums}
.sec .t{font:500 17px/1.25 var(--display)}
.sec small{display:block;font:12px/1.35 var(--serif);color:var(--muted);margin-top:2px}
.k-interlude > .sec .t{font-style:italic}
.k-interlude > .sec .n{color:var(--accent);font-size:13.5px;letter-spacing:.02em}
.k-sidebar > .sec .t{font-size:15.5px}
.toc-list>li.active>.sec{background:var(--surface-2)}
.toc-list>li.active>.sec .n,.toc-list>li.active>.sec .t{color:var(--accent-strong)}
.sub{display:none;margin:4px 0 8px 44px;border-left:1px solid var(--divider)}
.toc-list>li.active>.sub{display:block}
.sub a{display:block;padding:4px 10px;margin-left:-1px;border-left:2px solid transparent;font-size:13.5px;line-height:1.35;color:var(--muted);text-decoration:none}
.sub a:hover{color:var(--text)}
.sub a.current{color:var(--text);border-left-color:var(--accent)}
.sidebar-foot{margin:28px 12px 0;padding-top:16px;border-top:1px solid var(--divider);display:grid;gap:6px;font-size:13.5px}
.sidebar-foot a{color:var(--muted);text-decoration:none}
.sidebar-foot a:hover{color:var(--accent-strong)}
.backdrop{position:fixed;inset:0;z-index:34;background:rgba(0,0,0,.35);opacity:0;pointer-events:none;transition:opacity .25s}

/* ---- page ---- */
main{margin-left:var(--side);padding:calc(var(--top) + 8px) 40px 120px}
.page{max-width:37rem;margin:0 auto}
.cover{min-height:calc(100svh - var(--top) - 8px);display:flex;flex-direction:column;justify-content:center;padding:48px 0 64px;text-align:center}
.cover .kicker{margin-bottom:22px}
.cover:has(.route-map){padding-top:24px}
.route-map{margin:0 auto 34px;width:100%;max-width:calc(76svh * var(--map-ratio, 1))}
.route-map-stack{position:relative;overflow:hidden;border-radius:10px;background:var(--surface);box-shadow:var(--shadow)}
.route-map-stack img{display:block;width:100%;height:100%;object-fit:cover}
.route-map-stack .overlay{position:absolute;inset:0}
.route-map figcaption{margin-top:9px;font-size:12.5px;line-height:1.4;color:var(--muted)}
.route-map figcaption a{color:inherit}.ridge{display:block;width:150px;margin:0 auto 26px;color:var(--accent)}
.cover-title{font:400 clamp(58px,11vw,96px)/.95 var(--display);letter-spacing:-.025em;margin:0}
.cover-route{font:500 clamp(19px,3.4vw,24px)/1.35 var(--display);margin:22px 0 6px}
.cover-tag{font-style:italic;color:var(--muted);margin:0}
.actions{display:flex;flex-wrap:wrap;justify-content:center;gap:10px;margin-top:36px}
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 20px;border-radius:999px;border:1px solid var(--divider);
  font:600 17px/1.2 var(--display);letter-spacing:.02em;color:inherit;text-decoration:none;background:var(--surface)}
.btn:hover{border-color:var(--accent)}
.btn.primary{background:var(--text);color:var(--bg);border-color:var(--text)}
.btn.primary:hover{background:var(--accent-strong);border-color:var(--accent-strong)}
.btn[hidden]{display:none}
.offline{margin:26px auto 0;max-width:26rem;font-size:13px;line-height:1.5;color:var(--muted)}

.kicker{font:600 12.5px/1 var(--display);letter-spacing:.2em;text-transform:uppercase;color:var(--accent-strong)}
.chapter{padding-top:72px;scroll-margin-top:var(--top)}
.chapter + .chapter{margin-top:72px;border-top:1px solid var(--divider)}
.chapter-head{text-align:center;margin-bottom:44px}
.chapter-head h1{font:400 clamp(40px,7vw,56px)/1.02 var(--display);letter-spacing:-.02em;margin:14px 0 16px;text-wrap:balance}
.meta{margin:0;font-size:14px;line-height:1.6;color:var(--muted);font-variant-numeric:tabular-nums;letter-spacing:.01em}
.meta.note{font-style:italic;font-size:15.5px;max-width:30rem;margin:0 auto;text-wrap:balance}
.chapter-head::after{content:"";display:block;width:7px;height:7px;margin:26px auto 0;background:var(--accent);transform:rotate(45deg)}
.k-interlude .chapter-head .kicker,.k-sidebar .chapter-head .kicker{color:var(--muted)}
.k-sidebar .chapter-head h1{font-size:clamp(34px,6vw,44px)}

.chapter-body h2{font:600 30px/1.15 var(--display);letter-spacing:-.01em;margin:2.1em 0 .55em;scroll-margin-top:calc(var(--top) + 20px);text-wrap:balance}
.chapter-body h3{font:600 23px/1.2 var(--display);margin:1.9em 0 .45em;scroll-margin-top:calc(var(--top) + 20px)}
.chapter-body > h2:first-child,.chapter-body > h3:first-child{margin-top:0}
.chapter-body p{margin:0 0 1.05em}
.chapter-body ul,.chapter-body ol{padding-left:1.25em;margin:0 0 1.2em}
.chapter-body li{margin:.4em 0;padding-left:.2em}
.chapter-body li::marker{color:var(--accent)}
.chapter-body strong{font-weight:600}
:is(.k-chapter,.k-interlude,.k-sidebar,.k-coda) .chapter-body > p:first-of-type::first-letter{float:left;font:500 4.1em/.78 var(--display);padding:.08em .1em 0 0;color:var(--accent-strong)}

.box{margin:2.2em 0;padding:20px 22px 6px;background:var(--surface);border-left:3px solid var(--accent);border-radius:0 10px 10px 0}
.box h2,.box h3{margin:.1em 0 .5em;font-size:24px}
.box-label{font:600 12px/1 var(--display);letter-spacing:.18em;text-transform:uppercase;color:var(--accent-strong)}
.box-rock{border-left-color:var(--rock)} .box-rock .box-label{color:var(--rock)}
.box-people{border-left-color:var(--people)} .box-people .box-label{color:var(--people)}
.box-practical{border-left-color:var(--practical);background:color-mix(in srgb,var(--practical) 8%,var(--bg))}
.box-practical .box-label{color:var(--practical-ink)}
.box-caution{border-left-color:var(--caution);background:color-mix(in srgb,var(--caution) 8%,var(--bg))}
.box-caution .box-label{color:var(--caution-ink)}
.box-respect{border-left-color:var(--respect);background:color-mix(in srgb,var(--respect) 8%,var(--bg))}
.box-respect .box-label{color:var(--respect-ink)}
.box-field{border-left:3px dashed var(--muted);background:transparent;border-radius:0;padding-left:18px}
.box-field .box-label{color:var(--muted)}
.box-field p{font-style:italic}
.box p.checked,.chapter-body p.checked{font-size:12.5px;line-height:1.45;color:var(--muted);border-top:1px solid var(--divider);padding-top:7px;margin-top:10px}
.todo-verify{display:inline-block;padding:0 7px;border-radius:999px;font:600 11px/1.7 var(--serif);letter-spacing:.02em;white-space:nowrap;
  vertical-align:.08em;color:var(--caution-ink);background:color-mix(in srgb,var(--caution) 20%,transparent)}
/* glossary words (T2.7) */
.gloss{appearance:none;border:0;background:none;padding:0;margin:0;font:inherit;color:inherit;cursor:help;
  text-decoration:underline dotted;text-decoration-color:color-mix(in srgb,var(--text) 55%,transparent);text-underline-offset:3px}
.gloss-pop{position:absolute;z-index:60;padding:10px 12px;border-radius:8px;background:var(--text);color:var(--bg);
  font:14px/1.45 var(--serif);box-shadow:var(--shadow)}
.gloss-pop a{color:inherit}
/* A–Z index (T2.8) */
.ix-letters{display:flex;flex-wrap:wrap;gap:4px;margin:0 0 18px}
.ix-letters a{min-width:34px;min-height:34px;display:grid;place-items:center;border:1px solid var(--divider);border-radius:6px;
  text-decoration:none;color:var(--text);font:600 16px/1 var(--display)}
.ix-letter{font:600 26px/1 var(--display);margin:1.4em 0 .3em;scroll-margin-top:calc(var(--top) + 12px)}
.chapter-body ul.ix{list-style:none;padding:0}
.chapter-body ul.ix li{font-size:15px;line-height:1.5;margin:.35em 0}
.ix-term{font-weight:600}
/* today (T2.9) */
.today{margin:6px 12px 2px;padding:10px 12px;border-radius:8px;background:color-mix(in srgb,var(--practical) 12%,var(--bg));
  font-size:14px;line-height:1.45}
.today a{color:var(--text)}
.today-k{display:block;font:600 12px/1.2 var(--display);letter-spacing:.14em;text-transform:uppercase;color:var(--practical-ink);margin-bottom:3px}
.cover .today{margin:18px auto 0;max-width:30rem;text-align:left}
.today[hidden]{display:none}
/* search (T2.3) */
.search{position:fixed;inset:0;z-index:70;background:rgba(0,0,0,.45);display:flex;align-items:flex-start;justify-content:center;padding:calc(var(--top) + 8px) 12px 12px}
.search[hidden]{display:none}
.search-panel{width:min(640px,100%);max-height:calc(100dvh - var(--top) - 24px);display:flex;flex-direction:column;
  background:var(--bg);border-radius:12px;box-shadow:var(--shadow);overflow:hidden}
.search-box{display:flex;align-items:center;gap:6px;padding:8px 8px 8px 14px;border-bottom:1px solid var(--divider)}
.search-box input{flex:1;min-width:0;min-height:44px;border:0;background:none;color:var(--text);font:17px/1.3 var(--serif);outline:none}
.search-body{overflow-y:auto;padding:6px}
.search-hit{display:block;padding:10px 12px;border-radius:8px;text-decoration:none;color:var(--text)}
.search-hit:hover,.search-hit.on{background:var(--surface-2)}
.search-hit .crumb{display:block;font:600 12px/1.3 var(--serif);color:var(--practical-ink)}
.search-hit .stitle{display:block;font:600 18px/1.25 var(--display);margin:1px 0 2px}
.search-hit .snip{display:block;font-size:14px;line-height:1.45;color:var(--muted)}
.search-hit mark{background:color-mix(in srgb,var(--caution) 38%,transparent);color:var(--text);border-radius:2px;padding:0 1px}
.search-empty h2{font:600 12px/1 var(--display);letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin:10px 8px 8px}
.search-empty ul{list-style:none;margin:0;padding:0 4px 8px;display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:6px}
.search-empty a{display:block;padding:11px 12px;border-radius:8px;background:var(--surface);color:var(--text);text-decoration:none;font:600 16px/1.2 var(--display)}
.search-none{padding:12px;margin:0;color:var(--muted)}
body.search-open{overflow:hidden}
@keyframes flash{0%,40%{background:color-mix(in srgb,var(--caution) 32%,transparent)}100%{background:transparent}}
.flash{animation:flash 1.8s ease-out;border-radius:4px}
.box p:last-child,.box ul:last-child{margin-bottom:14px}

.table-wrap{overflow-x:auto;margin:1.2em 0 1.6em}
table{width:100%;border-collapse:collapse;font-size:15px;line-height:1.45;font-variant-numeric:tabular-nums}
th{font:600 12px/1 var(--display);letter-spacing:.14em;text-transform:uppercase;color:var(--muted);text-align:left;padding:0 10px 10px;white-space:nowrap}
td{padding:9px 10px;border-top:1px solid var(--divider);vertical-align:top}
td:first-child{white-space:nowrap;color:var(--muted)}
/* contents tables */
#contents .chapter-body p > strong:first-child{font:600 12.5px/1 var(--display);letter-spacing:.18em;text-transform:uppercase;color:var(--accent-strong)}
#contents .chapter-body p:has(> strong:first-child){margin:2.2em 0 .2em}
#contents .chapter-body p:has(> strong:first-child) a{color:inherit}
#contents .table-wrap{margin-top:.4em}
#contents table{table-layout:fixed}
#contents td:first-child{width:2.8em;text-align:right;font:500 17px/1.3 var(--display)}
#contents td:nth-child(2){width:58%}
#contents td:last-child{color:var(--muted);font-size:13.5px}
#contents td a{color:inherit;text-decoration:none;font:500 18px/1.25 var(--display)}
#contents td a:hover{color:var(--accent-strong);text-decoration:underline}
#contents td a strong{font-weight:600}

.h-label{margin:2.6em 0 0;font:600 12px/1 var(--display);letter-spacing:.18em;text-transform:uppercase;color:var(--people)}
.h-label::before{content:"";display:inline-block;width:18px;height:1px;margin-right:8px;vertical-align:middle;background:currentColor}
.chapter-body .h-label + h2,.chapter-body .h-label + h3{margin-top:.4em;scroll-margin-top:calc(var(--top) + 48px)}

/* figures */
.fig{margin:1.9em 0 2.1em}
.fig img{display:block;width:auto;height:auto;max-width:100%;max-height:min(78vh,680px);margin:0 auto;border-radius:6px;background:var(--surface)}
.fig figcaption{margin-top:9px;font-size:13.5px;line-height:1.45;color:var(--muted);text-align:center;text-wrap:balance}
.fig .credit{display:block;margin-top:2px;font-size:11.5px;opacity:.85}
.fig .credit a{color:inherit}
.fig.hero{margin:-8px 0 44px}
.box .fig{margin:1.2em 0 1.4em}
@media (min-width:1280px){.fig.hero{margin-left:-3.5rem;margin-right:-3.5rem}.fig.hero figcaption{padding:0 3.5rem}}
.map-fig{margin:1.8em 0 2.1em;clear:both}
.map-fig svg{display:block;width:100%;height:auto;max-height:82vh;border-radius:8px;border:1px solid var(--divider)}
.map-fig figcaption{margin-top:9px;font-size:13.5px;line-height:1.45;color:var(--muted)}
.map-fig .credit{display:block;margin-top:2px;font-size:11.5px;opacity:.85}
.map-places{margin-top:6px;font-size:13.5px;color:var(--muted)}
.map-places summary{cursor:pointer;font-weight:600;color:var(--text)}
.map-places ul{columns:2 12rem;column-gap:22px;margin:.5em 0 0;padding-left:1.1em}
.map-places li{margin:.2em 0;break-inside:avoid}
.map-places li span{font-size:12px}
.fig.hero + .map-fig{margin-top:-18px}
.map-fig.diagram img{display:block;width:100%;height:auto;max-width:640px;margin:0 auto}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:16px 12px;margin:1.2em 0 1.9em}
.gallery .gfig{margin:0}
.gallery img{display:block;width:100%;height:auto;aspect-ratio:1;object-fit:cover;object-position:50% 35%;border-radius:5px;background:var(--surface)}
.gallery figcaption{margin-top:6px;font-size:12.5px;line-height:1.35;color:var(--muted)}
.gallery .credit{display:block;margin-top:2px;font-size:10.5px;opacity:.8}
.gallery .credit a{color:inherit}
.with-float{display:flow-root}
.gfig.float{float:right;width:min(36%,190px);margin:.35em 0 1.1em 1.1em}
.gfig.float img{display:block;width:100%;height:auto;aspect-ratio:1;object-fit:cover;object-position:50% 35%;border-radius:5px;background:var(--surface)}
.gfig.float figcaption{margin-top:5px;font-size:12px;line-height:1.3;color:var(--muted)}
.gfig.float .credit{display:block;margin-top:1px;font-size:10px;opacity:.8}
.gfig.float .credit a{color:inherit}
.chapter-body :is(h2,h3,.h-label,.gallery,.box,.fig,.table-wrap){clear:both}
.chapter-body :is(ul,ol){display:flow-root}
.credits{padding-left:1.4em;font-size:14px;line-height:1.5}
.credits li{margin:.45em 0}
.credits a:first-child{color:inherit}

.colophon{margin:88px 0 0;padding-top:28px;border-top:1px solid var(--divider);text-align:center;font-size:14px;color:var(--muted)}
.colophon nav{margin-top:18px;display:flex;flex-wrap:wrap;justify-content:center;gap:6px 18px;font:600 16px/1.3 var(--display)}

/* ---- narrow screens: sidebar becomes a drawer ---- */
@media (min-width:1024px){ #menu-btn{display:none} }
@media (max-width:1023px){
  .brand{display:none}
  .sidebar{width:min(88vw,340px);transform:translateX(-102%);transition:transform .25s ease;border-right:0}
  body.nav-open{overflow:hidden}
  body.nav-open .sidebar{transform:none;box-shadow:var(--shadow)}
  body.nav-open .backdrop{opacity:1;pointer-events:auto}
  main{margin-left:0;padding:calc(var(--top) + 4px) 16px 96px}
}
@media (max-width:600px){
  body{font-size:17px;line-height:1.7}
  .chapter{padding-top:56px}
  .chapter + .chapter{margin-top:56px}
  .chapter-body h2{font-size:27px}
  .box{padding:16px 16px 4px;margin-left:-4px;margin-right:-4px}
  td{padding:8px 6px} th{padding:0 6px 8px}
  #contents td:first-child{width:2.4em}
  #contents td:nth-child(2){width:55%}
  #contents td a{font-size:17px}
}
@media print{
  .topbar,.sidebar,.backdrop,.actions,.offline{display:none!important}
  main{margin:0;padding:0} .chapter{break-before:page;border:0!important;margin:0!important}
}
</style>
</head>
<body>

<header class="topbar">
  <button class="icon-btn" id="menu-btn" aria-label="Contents" aria-controls="sidebar" aria-expanded="false">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h10"/></svg>
  </button>
  <a class="brand" href="#top">%%BOOK_TITLE%%</a>
  <button class="here" id="here" title="Contents">%%BOOK_TITLE%%</button>
  <button class="icon-btn" id="search-btn" aria-label="Search the book" title="Search (/ or Ctrl+K)">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></svg>
  </button>
  <button class="icon-btn" id="size-btn" aria-label="Text size" title="Text size">
    <span style="font:600 16px/1 var(--display)" aria-hidden="true">Aa</span>
  </button>
  <button class="icon-btn" id="theme-btn" aria-label="Light, dark or night mode" title="Light / dark / night">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor"/></svg>
  </button>
  <a class="icon-btn" href="../" aria-label="Spiti Circuit home" title="Spiti Circuit home">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"><path d="M2 19 9 8l4 6 3-4 6 9Z"/></svg>
  </a>
  <div class="progress" id="progress"></div>
</header>

<aside class="sidebar" id="sidebar" aria-label="Contents">
  <div class="today" data-today hidden></div>
  <nav>%%NAV%%</nav>
  <div class="sidebar-foot">
    <a href="../practical/">Practical: fuel, cash, emergency</a>
    <a href="../preparation/">Preparation: weather, roads, packing</a>
    <a href="../map/">Route map</a>
    <a href="%%MAP_URL%%" target="_blank" rel="noopener">Google My Maps ↗</a>
    <a href="../">Spiti Circuit home</a>
    <a href="#" data-pwa-install>Install on this phone</a>
    <a href="#" data-pwa-update>Check for updates</a>
  </div>
</aside>
<div class="backdrop" id="backdrop"></div>
<div class="search" id="search" role="dialog" aria-modal="true" aria-label="Search the book" hidden>
  <div class="search-panel">
    <div class="search-box">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></svg>
      <input id="search-input" type="search" placeholder="Search: chutagi, fuel, black ice…" autocomplete="off" spellcheck="false" aria-controls="search-results" aria-label="Search the book">
      <button class="icon-btn" id="search-close" aria-label="Close search">✕</button>
    </div>
    <div class="search-body">
      <div class="search-empty" id="search-empty">
        <h2>Most looked-up</h2>
        <ul>
          <li><a href="#sidebar-manners">Manners</a></li>
          <li><a href="#sidebar-your-body-on-this-road">Altitude and your body</a></li>
          <li><a href="#interlude-3">Food</a></li>
          <li><a href="#interlude-1-language-the-least-you-can-carry">Phrases</a></li>
          <li><a href="../practical/#emergency">Emergency</a></li>
          <li><a href="../practical/#fuel">Fuel and distances</a></li>
          <li><a href="../preparation/#s4">Packing list</a></li>
          <li><a href="../practical/#hours">What's open</a></li>
        </ul>
      </div>
      <div id="search-results" role="listbox" hidden></div>
    </div>
  </div>
</div>
%%EXTRA_DATA%%

<main>
<div class="page">
  <header class="cover" id="top" data-section data-here="%%BOOK_TITLE%%">
    %%ROUTE_MAP%%
    <div class="kicker">Spiti Circuit · September 2026</div>
    <h1 class="cover-title">%%BOOK_TITLE%%</h1>
    <p class="cover-route">%%SUBTITLE%%</p>
    <p class="cover-tag">%%TAGLINE%%</p>
    <div class="actions">
      <a class="btn primary" href="#how-to-use">Begin reading</a>
      <a class="btn" id="resume" href="#" hidden>Continue · <span></span></a>
      <a class="btn" href="#" data-pwa-install>Install on phone</a>
    </div>
    <div class="today" data-today hidden></div>
    <p class="offline">Open this once while you have signal and the whole site, pictures included, keeps working offline, which you will want past Reckong Peo.</p>
  </header>

%%SECTIONS%%

  <footer class="colophon">
    <p>%%COLOPHON%%</p>
    <nav><a href="../">Spiti Circuit</a><a href="../preparation/">Preparation</a><a href="../map/">Route map</a><a href="%%MAP_URL%%" target="_blank" rel="noopener">Google My Maps ↗</a></nav>
  </footer>
</div>
</main>

<script>
(() => {
  const root = document.documentElement, body = document.body;
  const $ = id => document.getElementById(id);
  const sidebar = $("sidebar"), menuBtn = $("menu-btn"), here = $("here"), bar = $("progress"), resume = $("resume");
  const wide = matchMedia("(min-width: 1024px)");
  const store = { get: k => { try { return localStorage.getItem(k); } catch { return null; } },
                  set: (k, v) => { try { localStorage.setItem(k, v); } catch {} } };

  // theme
  const THEMES = ["light", "dark", "night"];
  $("theme-btn").addEventListener("click", () => {
    const now = root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    root.dataset.theme = THEMES[(THEMES.indexOf(now) + 1) % THEMES.length];
    store.set("spiti-theme", root.dataset.theme);
    $("theme-btn").title = `Mode: ${root.dataset.theme} (tap for ${THEMES[(THEMES.indexOf(root.dataset.theme) + 1) % 3]})`;
  });
  const SIZES = ["m", "l", "s"];
  if (store.get("spiti-size")) root.dataset.size = store.get("spiti-size");
  $("size-btn").addEventListener("click", () => {
    root.dataset.size = SIZES[(SIZES.indexOf(root.dataset.size || "m") + 1) % SIZES.length];
    store.set("spiti-size", root.dataset.size);
    onScroll();
  });

  // drawer
  const setNav = open => {
    body.classList.toggle("nav-open", open);
    menuBtn.setAttribute("aria-expanded", open);
    sidebar.inert = !open && !wide.matches;
    if (open) reveal();
  };
  menuBtn.addEventListener("click", () => setNav(!body.classList.contains("nav-open")));
  here.addEventListener("click", () => wide.matches ? curSec && curSec.scrollIntoView() : setNav(true));
  $("backdrop").addEventListener("click", () => setNav(false));
  document.addEventListener("keydown", e => { if (e.key === "Escape") setNav(false); });
  sidebar.addEventListener("click", e => { if (e.target.closest("a") && !wide.matches) setNav(false); });
  wide.addEventListener("change", () => setNav(false));
  setNav(false);

  // scroll tracking
  const sections = [...document.querySelectorAll("[data-section]")];
  const links = new Map([...sidebar.querySelectorAll('a[href^="#"]')].map(a => [a.hash.slice(1), a]));
  const heads = [...sidebar.querySelectorAll(".sub a")].map(a => $(a.hash.slice(1))).filter(Boolean);
  const lastAbove = list => { let hit = null; for (const el of list) { if (el.getBoundingClientRect().top <= 110) hit = el; else break; } return hit; };
  let curSec = null, curHead = null, ticking = false, saveTimer;

  function reveal() {
    const a = curSec && links.get(curSec.id);
    if (!a) return;
    const s = sidebar.getBoundingClientRect(), r = a.getBoundingClientRect();
    if (r.top < s.top + 40 || r.bottom > s.bottom - 80) sidebar.scrollTop += r.top - s.top - s.height / 4;
  }

  function update() {
    ticking = false;
    const sec = lastAbove(sections) || sections[0];
    // T2.10: the bar shows progress through the current chapter
    const secTop = sec.getBoundingClientRect().top + scrollY, span = sec.offsetHeight - innerHeight * 0.6;
    bar.style.transform = `scaleX(${span > 0 ? Math.max(0, Math.min(1, (scrollY - secTop + 110) / span)) : 1})`;
    let head = lastAbove(heads);
    if (head && !sec.contains(head)) head = null;
    if (sec !== curSec) {
      if (curSec) links.get(curSec.id)?.parentElement.classList.remove("active");
      links.get(sec.id)?.parentElement.classList.add("active");
      curSec = sec;
      here.textContent = sec.dataset.here;
      reveal();
    }
    if (head !== curHead) {
      if (curHead) links.get(curHead.id)?.classList.remove("current");
      if (head) links.get(head.id)?.classList.add("current");
      curHead = head;
    }
    clearTimeout(saveTimer);
    if (sec.id !== "top") saveTimer = setTimeout(() => store.set("spiti-book-pos", (head || sec).id), 400);
  }
  const onScroll = () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } };
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", onScroll);

  // resume where you left off
  const saved = store.get("spiti-book-pos"), savedEl = saved && document.getElementById(saved);
  if (savedEl) {
    const sec = savedEl.closest("[data-section]");
    resume.hash = saved;
    resume.querySelector("span").textContent = sec.dataset.here;
    if (savedEl !== sec) resume.title = savedEl.textContent;
    resume.hidden = false;
  }
  update();
  // lazy images change the page height as they load; keep the progress bar honest
  document.addEventListener("load", e => { if (e.target.tagName === "IMG") onScroll(); }, true);

  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const flash = el => { el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); };

  // ---- today (T2.9): on trip dates, what to read; ?today=2026-09-19 previews a date ----
  try {
    const plan = JSON.parse($("today-data").textContent);
    const d = new Date(), pad = n => String(n).padStart(2, "0");
    const key = new URLSearchParams(location.search).get("today") || `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const t = plan[key];
    if (t && t.links.length) {
      const html = `<span class="today-k">Today · ${esc(t.label)}</span>` + t.links.map(l => `<a href="#${l.id}">${esc(l.text)}</a>`).join(" · ");
      document.querySelectorAll("[data-today]").forEach(el => { el.innerHTML = html; el.hidden = false; });
    }
  } catch {}

  // ---- glossary popovers (T2.7) ----
  const glossary = JSON.parse($("glossary-data").textContent), pop = $("gloss-pop");
  document.addEventListener("click", e => {
    const g = e.target.closest(".gloss");
    if (!g) { if (!e.target.closest("#gloss-pop")) pop.hidden = true; return; }
    const [term, def] = glossary[+g.dataset.g];
    pop.innerHTML = `<strong>${esc(term)}</strong> — ${def}. <a href="#appendix-d">Words</a>`;
    pop.hidden = false;
    const r = g.getBoundingClientRect(), w = Math.min(320, innerWidth - 24);
    pop.style.width = w + "px";
    pop.style.left = Math.max(12, Math.min(r.left + scrollX, scrollX + innerWidth - w - 12)) + "px";
    pop.style.top = (r.bottom + scrollY + 6) + "px";
  });
  addEventListener("keydown", e => { if (e.key === "Escape") pop.hidden = true; });

  // ---- search (T2.1–T2.6): MiniSearch and the index are local files, cached for offline use ----
  const sBox = $("search"), sIn = $("search-input"), sOut = $("search-results"), sEmpty = $("search-empty");
  const norm = s => s.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "");
  let mini = null, docs = [], aliases = [], active = -1, lastFocus = null, timer = 0, loading = null;
  const loadScript = src => new Promise((ok, bad) => {
    const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = bad; document.head.appendChild(s);
  });
  function ensureIndex() {
    return loading || (loading = Promise.all([
      window.MiniSearch ? null : loadScript("vendor/minisearch-7.2.0.min.js"),
      fetch("search-index.json").then(r => r.json())
    ]).then(([, data]) => {
      docs = data.docs; aliases = data.aliases;
      mini = new MiniSearch({ fields: ["t", "b", "c"], idField: "id", processTerm: t => norm(t),
                              searchOptions: { boost: { t: 4, c: 1.5 }, prefix: term => term.length > 2,
                                               fuzzy: term => (term.length > 5 ? 0.2 : false) } });
      mini.addAll(docs);
    }));
  }
  // The query becomes a tree: every word (or alias phrase such as "kunzum la") is an OR over its known
  // spellings from search-aliases.json, and those groups are ANDed. "key monastery" = (ki|key|…) AND (gompa|monastery|…).
  function parse(q) {
    let nq = " " + norm(q).replace(/[^a-z0-9]+/g, " ").trim() + " ";
    const parts = [];
    for (const g of aliases) {
      const phrase = g.filter(v => v.includes(" ")).sort((a, b) => b.length - a.length).find(v => nq.includes(` ${v} `));
      if (phrase) { parts.push(g); nq = nq.replace(` ${phrase} `, " "); }
    }
    for (const w of nq.trim().split(/\s+/).filter(Boolean)) parts.push(aliases.find(g => g.includes(w)) || [w]);
    return parts;
  }
  const tree = parts => ({ combineWith: "AND", queries: parts.map(g => ({ combineWith: "OR",
    queries: g.map(v => (v.includes(" ") ? { combineWith: "AND", queries: [v] } : v)) })) });
  function run(q) {
    const parts = parse(q), hits = new Map();
    const add = (res, w) => res.forEach(r => {
      const h = hits.get(r.id) || { id: r.id, score: 0, terms: new Set() };
      h.score = Math.max(h.score, r.score * w); r.terms.forEach(t => h.terms.add(t)); hits.set(r.id, h);
    });
    add(mini.search(tree(parts)), 1);
    if (hits.size < 8 && parts.length > 1) add(mini.search({ combineWith: "OR", queries: parts.flat() }), 0.2);
    return { parts, res: [...hits.values()].sort((a, b) => b.score - a.score).slice(0, 40) };
  }
  function snippet(text, words) {
    const low = norm(text);
    let at = -1;
    for (const w of words) { const i = low.indexOf(w); if (i >= 0 && (at < 0 || i < at)) at = i; }
    const start = Math.max(0, at - 50), piece = text.slice(start, start + 150);
    let out = esc((start > 0 ? "…" : "") + piece + (start + 150 < text.length ? "…" : ""));
    const ws = [...new Set(words)].filter(w => w.length > 1).sort((a, b) => b.length - a.length)
      .map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    return ws.length ? out.replace(new RegExp(`(${ws.join("|")})`, "gi"), "<mark>$1</mark>") : out;
  }
  function render(q) {
    active = -1;
    sIn.removeAttribute("aria-activedescendant");
    if (norm(q).trim().length < 2) { sOut.hidden = true; sEmpty.hidden = false; return; }
    sEmpty.hidden = true; sOut.hidden = false;
    const { parts, res } = run(q);
    // highlight the words and alias spellings (phrases stay whole), plus index terms that are clearly the same word
    const words = [...new Set(parts.flat())].filter(w => w.length > 1);
    const near = terms => [...terms].filter(t => t.length > 2 && words.some(w => !w.includes(" ") && t.startsWith(w.slice(0, 3))));
    if (!res.length) {
      sOut.innerHTML = `<p class="search-none">Nothing for “${esc(q)}”. Try <a href="#appendix-d">the glossary</a> or <a href="#contents">the contents</a>.</p>`;
      return;
    }
    sOut.innerHTML = res.map((r, i) => {
      const d = docs[r.id];
      return `<a class="search-hit" role="option" id="hit-${i}" href="#${d.a}"><span class="crumb">${esc(d.c)}</span>` +
             `<span class="stitle">${esc(d.t)}</span><span class="snip">${snippet(d.b || d.t, [...words, ...near(r.terms)])}</span></a>`;
    }).join("");
  }
  function openSearch() {
    if (!sBox.hidden) return;
    lastFocus = document.activeElement;
    setNav(false);
    sBox.hidden = false;
    body.classList.add("search-open");
    sIn.focus();
    sIn.select();
    ensureIndex().then(() => render(sIn.value)).catch(() => {
      sEmpty.hidden = true; sOut.hidden = false;
      sOut.innerHTML = '<p class="search-none">Search could not load. Open the book once with signal so it is saved.</p>';
    });
  }
  function closeSearch() {
    sBox.hidden = true;
    body.classList.remove("search-open");
    if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
  }
  $("search-btn").addEventListener("click", openSearch);
  $("search-close").addEventListener("click", closeSearch);
  sIn.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => mini && render(sIn.value), 120); });
  sIn.addEventListener("keydown", e => {
    const hits = [...sOut.querySelectorAll(".search-hit")];
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!hits.length) return;
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + hits.length) % hits.length;
      hits.forEach((h, i) => h.classList.toggle("on", i === active));
      hits[active].scrollIntoView({ block: "nearest" });
      sIn.setAttribute("aria-activedescendant", hits[active].id);
    } else if (e.key === "Enter") {
      const h = hits[Math.max(active, 0)];
      if (h) { e.preventDefault(); h.click(); }
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeSearch();
    }
  });
  sBox.addEventListener("click", e => {
    if (e.target === sBox) return closeSearch();
    const a = e.target.closest("a[href]");
    if (!a) return;
    const href = a.getAttribute("href");
    closeSearch();
    if (!href.startsWith("#")) return;
    e.preventDefault();
    const el = document.getElementById(href.slice(1));
    if (!el) return;
    history.pushState(null, "", href);
    el.scrollIntoView({ block: "start" });
    flash(el.matches("section") ? (el.querySelector("h1") || el) : el);
  });
  document.addEventListener("keydown", e => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if ((e.key === "/" && !typing) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k")) {
      e.preventDefault();
      openSearch();
    }
  });
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check-only":
        sys.exit(main(sys.argv[2], write=False))
    sys.exit(main())
