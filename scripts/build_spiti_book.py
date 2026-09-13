#!/usr/bin/env python3
"""Render spiti/book/spiti-circuit-the-long-read.md into a single-page web book.

Output: spiti/book/index.html (one scrollable page, with an always-available
contents sidebar / drawer, scroll tracking, resume, dark mode).
"""
import html
import re
import unicodedata
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "spiti" / "book" / "spiti-circuit-the-long-read.md"
OUT = ROOT / "spiti" / "book" / "index.html"
MAP_URL = ("https://www.google.com/maps/d/viewer?hl=en&mid=1u-k6Xo2r8bb7X1d2uw0fOrKS4oj_jdU"
           "&ll=31.598923869659814%2C77.71116500000001&z=8")

BOXES = {"In the rock": "rock", "The other story": "myth", "Who came through here": "people"}

_used_ids = set()


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
    out = markdown.markdown("\n".join(lines), extensions=["tables", "smarty", "sane_lists"])
    return out.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")


def inline(text):
    return re.sub(r"^<p>|</p>$", "", md([text]))


def render_body(lines, prefix):
    """Render a section body; wrap the recurring boxes in <aside>. Returns (html, h2 toc)."""
    out, toc, buf = [], [], []
    box_level = None

    def flush():
        if any(l.strip() for l in buf):
            out.append(md(buf))
        buf.clear()

    for line in lines:
        m = re.match(r"^(#{2,4}) (.+)$", line)
        if not m:
            buf.append(line)
            continue
        flush()
        level, text = len(m.group(1)), m.group(2).strip()
        if box_level is not None and level <= box_level:
            out.append("</aside>")
            box_level = None
        hid = slug(text, prefix)
        label, sep, rest = text.partition(":")
        kind = BOXES.get(label.strip()) if sep else None
        if kind and box_level is None:
            out.append(f'<aside class="box box-{kind}"><div class="box-label">{html.escape(label.strip())}</div>')
            rest = rest.strip()
            out.append(f'<h{level} id="{hid}">{inline(rest[:1].upper() + rest[1:])}</h{level}>')
            box_level = level
        else:
            out.append(f'<h{level} id="{hid}">{inline(text)}</h{level}>')
        if level == 2:
            toc.append((hid, plain(text)))
    flush()
    if box_level is not None:
        out.append("</aside>")
    return "\n".join(out), toc


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


def main():
    lines = SRC.read_text(encoding="utf-8").splitlines()
    blocks = [b for b in split_on(lines, r"^# (.+)$") if b[0]]

    # ---- cover + front matter (first H1 block) ----
    book_title, front = blocks[0]
    rule = front.index("---")
    cover_lines = [l for l in front[:rule] if l.strip()]
    subtitle = next((l.lstrip("# ").strip() for l in cover_lines if l.startswith("###")), "")
    tagline = next((l.strip("* ") for l in cover_lines if l.startswith("*")), "")

    when = {}
    sections = []  # dicts: id, kind, n, label, title, here, meta, body, toc, when

    for title, body in split_on(front[rule:], r"^## (.+)$"):
        if not title:
            continue
        sid = {"How to use this": "how-to-use", "Contents": "contents"}.get(title) or slug(title)
        _used_ids.add(sid)
        if sid == "contents":
            def link_row(m):
                num, name, w = m.group(1), m.group(2), m.group(3)
                target = "coda" if num == "—" else f"ch-{num}"
                when[target] = w
                return f"| {num} | [{name}](#{target}) | {w} |"
            body = [re.sub(r"^\|\s*(\d+|—)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", link_row, l) for l in body]
        body_html, toc = render_body([l for l in body if l.strip() != "---"], sid)
        sections.append(dict(id=sid, kind="front", n="", label="Before you start", title=title,
                             here=title, meta=[], body=body_html, toc=toc))

    # ---- chapters ----
    colophon = ""
    for title, body in blocks[1:]:
        m = re.match(r"^(Chapter (\d+)|Coda)\s*·\s*(.+)$", title)
        if m and m.group(2) is not None:
            sid, n, label, name = f"ch-{m.group(2)}", m.group(2), m.group(1), m.group(3)
        elif m:
            sid, n, label, name = "coda", "", "Coda", m.group(3)
        else:
            sid, n, label, name = slug(title.replace("The ", "")), "", "", title
        _used_ids.add(sid)

        # meta lines (**Day 1 · …**) directly under the chapter title
        i, meta = 0, []
        while i < len(body) and (not body[i].strip() or re.match(r"^\*\*[^*].*\*\*$", body[i].strip())):
            if body[i].strip():
                meta.append(body[i].strip().strip("*"))
            i += 1
        body = body[i:]

        # anything after a final horizontal rule is a colophon
        if "---" in body:
            last = len(body) - 1 - body[::-1].index("---")
            tail = [l for l in body[last + 1:] if l.strip()]
            if tail:
                colophon = inline(" ".join(tail))
                body = body[:last]
        body = [l for l in body if l.strip() != "---"]

        body_html, toc = render_body(body, sid)
        here = f"{label} · {name}" if label else name
        sections.append(dict(id=sid, kind="chapter" if n else "back", n=n, label=label, title=name,
                             here=here, meta=meta, body=body_html, toc=toc))

    # ---- sidebar ----
    def nav_item(s):
        sub = "".join(f'<li><a href="#{hid}">{html.escape(t)}</a></li>' for hid, t in s["toc"])
        w = when.get(s["id"])
        return (f'<li><a class="sec" href="#{s["id"]}"><span class="n">{s["n"]}</span>'
                f'<span class="t">{html.escape(s["title"])}'
                f'{f"<small>{html.escape(w)}</small>" if w else ""}</span></a>'
                f'{f"<ol class=sub>{sub}</ol>" if sub else ""}</li>')

    groups = [("Before you start", "front"), ("The road", "chapter"), ("After", "back")]
    nav = "".join(
        f'<div class="toc-group">{g}</div><ol class="toc-list">'
        + "".join(nav_item(s) for s in sections if s["kind"] == k) + "</ol>"
        for g, k in groups)

    # ---- sections ----
    def section_html(s):
        kicker = s["label"] or "Further reading"
        meta = "".join(f'<p class="meta">{html.escape(x)}</p>' for x in s["meta"])
        return (f'<section class="chapter" id="{s["id"]}" data-section data-here="{html.escape(s["here"])}">'
                f'<header class="chapter-head"><div class="kicker">{html.escape(kicker)}</div>'
                f'<h1>{html.escape(s["title"])}</h1>{meta}</header>'
                f'<div class="chapter-body">{s["body"]}</div></section>')

    page = (TEMPLATE
            .replace("%%DARK%%", DARK_TOKENS)
            .replace("%%BOOK_TITLE%%", html.escape(book_title))
            .replace("%%SUBTITLE%%", html.escape(subtitle))
            .replace("%%TAGLINE%%", html.escape(tagline))
            .replace("%%NAV%%", nav)
            .replace("%%SECTIONS%%", "\n".join(section_html(s) for s in sections))
            .replace("%%COLOPHON%%", colophon)
            .replace("%%MAP_URL%%", html.escape(MAP_URL)))
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(sections)} sections)")


DARK_TOKENS = """
  --bg:#161513; --surface:#211f1c; --surface-2:#2a2723; --text:#e8e2d7; --muted:#a29a8f;
  --accent:#d6a35a; --accent-strong:#e6bb78;
  --rock:#9d9891; --people:#8fa3b5;
  --divider:color-mix(in srgb,#e8e2d7 13%,transparent);
  --shadow:0 12px 32px rgba(0,0,0,.5);
  color-scheme:dark;
"""

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Long Read · Spiti Circuit</title>
<meta name="description" content="History, geology, myth and old travel writing for the Shimla – Kinnaur – Spiti – Chandratal – Manali road, chapter by chapter.">
<meta name="theme-color" content="#f3f2f2">
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
  --display:"Cormorant Garamond",Georgia,serif;
  --serif:"Lora",Georgia,serif;
  --top:52px; --side:310px;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){%%DARK%%}}
:root[data-theme="dark"]{%%DARK%%}

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
.icon-btn{flex:none;appearance:none;border:0;background:none;color:inherit;width:40px;height:40px;display:grid;place-items:center;border-radius:8px;cursor:pointer;text-decoration:none}
.icon-btn:hover{background:var(--surface)}
.icon-btn svg{width:20px;height:20px}
.brand{flex:none;width:calc(var(--side) - 16px);padding-left:12px;font:600 20px/1 var(--display);color:inherit;text-decoration:none;letter-spacing:.01em}
.here{flex:1;min-width:0;appearance:none;border:0;background:none;color:inherit;text-align:left;cursor:pointer;padding:6px 8px;border-radius:8px;
  font:500 17px/1.2 var(--display);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.here:hover{background:var(--surface)}

/* ---- sidebar / drawer ---- */
.sidebar{position:fixed;top:var(--top);bottom:0;left:0;width:var(--side);z-index:35;overflow-y:auto;overscroll-behavior:contain;
  background:var(--bg);border-right:1px solid var(--divider);padding:12px 10px 48px;scrollbar-width:thin}
.toc-group{font:600 11.5px/1 var(--display);letter-spacing:.16em;text-transform:uppercase;color:var(--muted);padding:22px 12px 8px}
.toc-list,.sub{list-style:none;margin:0;padding:0}
.sec{display:flex;gap:10px;padding:7px 12px;border-radius:8px;color:inherit;text-decoration:none;line-height:1.25}
.sec:hover{background:var(--surface)}
.sec .n{flex:none;width:18px;text-align:right;font:500 16px/1.3 var(--display);color:var(--muted);font-variant-numeric:tabular-nums}
.sec .t{font:500 17px/1.25 var(--display)}
.sec small{display:block;font:12px/1.35 var(--serif);color:var(--muted);margin-top:2px}
.toc-list>li.active>.sec{background:var(--surface-2)}
.toc-list>li.active>.sec .n,.toc-list>li.active>.sec .t{color:var(--accent-strong)}
.sub{display:none;margin:4px 0 8px 40px;border-left:1px solid var(--divider)}
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
.ridge{display:block;width:150px;margin:0 auto 26px;color:var(--accent)}
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
.chapter-head::after{content:"";display:block;width:7px;height:7px;margin:26px auto 0;background:var(--accent);transform:rotate(45deg)}

.chapter-body h2{font:600 30px/1.15 var(--display);letter-spacing:-.01em;margin:2.1em 0 .55em;scroll-margin-top:calc(var(--top) + 20px);text-wrap:balance}
.chapter-body h3{font:600 23px/1.2 var(--display);margin:1.9em 0 .45em;scroll-margin-top:calc(var(--top) + 20px)}
.chapter-body > h2:first-child{margin-top:0}
.chapter-body p{margin:0 0 1.05em}
.chapter-body ul,.chapter-body ol{padding-left:1.25em;margin:0 0 1.2em}
.chapter-body li{margin:.4em 0;padding-left:.2em}
.chapter-body li::marker{color:var(--accent)}
.chapter-body strong{font-weight:600}
.chapter-body > p:first-of-type::first-letter{float:left;font:500 4.1em/.78 var(--display);padding:.08em .1em 0 0;color:var(--accent-strong)}

.box{margin:2.2em 0;padding:20px 22px 6px;background:var(--surface);border-left:3px solid var(--accent);border-radius:0 10px 10px 0}
.box h2,.box h3{margin:.1em 0 .5em;font-size:24px}
.box-label{font:600 12px/1 var(--display);letter-spacing:.18em;text-transform:uppercase;color:var(--accent-strong)}
.box-rock{border-left-color:var(--rock)} .box-rock .box-label{color:var(--rock)}
.box-people{border-left-color:var(--people)} .box-people .box-label{color:var(--people)}
.box p:last-child,.box ul:last-child{margin-bottom:14px}

.table-wrap{overflow-x:auto;margin:1.4em 0 1.6em}
table{width:100%;border-collapse:collapse;font-size:15px;line-height:1.4;font-variant-numeric:tabular-nums}
th{font:600 12px/1 var(--display);letter-spacing:.14em;text-transform:uppercase;color:var(--muted);text-align:left;padding:0 10px 10px;white-space:nowrap}
td{padding:9px 10px;border-top:1px solid var(--divider);vertical-align:top}
td:first-child{color:var(--muted);text-align:right;width:2.2em;font-family:var(--display);font-size:17px}
td:last-child{color:var(--muted);font-size:13.5px}
td a{color:inherit;text-decoration:none;font:500 18px/1.25 var(--display)}
td a:hover{color:var(--accent-strong);text-decoration:underline}

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
  <button class="icon-btn" id="theme-btn" aria-label="Toggle dark mode" title="Light / dark">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor"/></svg>
  </button>
  <a class="icon-btn" href="../" aria-label="Spiti Circuit home" title="Spiti Circuit home">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"><path d="M2 19 9 8l4 6 3-4 6 9Z"/></svg>
  </a>
  <div class="progress" id="progress"></div>
</header>

<aside class="sidebar" id="sidebar" aria-label="Contents">
  <nav>%%NAV%%</nav>
  <div class="sidebar-foot">
    <a href="../preparation/">Preparation: weather, roads, packing</a>
    <a href="%%MAP_URL%%" target="_blank" rel="noopener">Trip map ↗</a>
    <a href="../">Spiti Circuit home</a>
  </div>
</aside>
<div class="backdrop" id="backdrop"></div>

<main>
<div class="page">
  <header class="cover" id="top" data-section data-here="%%BOOK_TITLE%%">
    <svg class="ridge" viewBox="0 0 150 34" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true"><path d="M1 33 24 14l10 8 22-21 16 15 9-6 20 17 11-9 18 15"/><path d="M50 7l6-6 6 6-3-1-3 3-3-3Z" fill="currentColor" stroke-width="1"/></svg>
    <div class="kicker">Spiti Circuit · September 2026</div>
    <h1 class="cover-title">%%BOOK_TITLE%%</h1>
    <p class="cover-route">%%SUBTITLE%%</p>
    <p class="cover-tag">%%TAGLINE%%</p>
    <div class="actions">
      <a class="btn primary" href="#how-to-use">Begin reading</a>
      <a class="btn" id="resume" href="#" hidden>Continue · <span></span></a>
    </div>
    <p class="offline">Open this page once while you have signal. After that it keeps working offline, which you will want past Reckong Peo.</p>
  </header>

%%SECTIONS%%

  <footer class="colophon">
    <p>%%COLOPHON%%</p>
    <nav><a href="../">Spiti Circuit</a><a href="../preparation/">Preparation</a><a href="%%MAP_URL%%" target="_blank" rel="noopener">Trip map ↗</a></nav>
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
  $("theme-btn").addEventListener("click", () => {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    store.set("spiti-theme", root.dataset.theme);
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
  const heads = [...document.querySelectorAll(".chapter-body h2[id]")];
  const links = new Map([...sidebar.querySelectorAll('a[href^="#"]')].map(a => [a.hash.slice(1), a]));
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
    const max = root.scrollHeight - innerHeight;
    bar.style.transform = `scaleX(${max > 0 ? Math.min(1, scrollY / max) : 0})`;
    const sec = lastAbove(sections) || sections[0];
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
    const sub = savedEl.tagName === "H2" ? savedEl.textContent : "";
    resume.hash = saved;
    resume.querySelector("span").textContent = sec.dataset.here;
    if (sub) resume.title = sub;
    resume.hidden = false;
  }
  update();

  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost"))
    navigator.serviceWorker.register("sw.js").catch(() => {});
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
