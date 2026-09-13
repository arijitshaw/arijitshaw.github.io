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
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
WORDS = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve"]
LIST_ITEM = re.compile(r"^\s*([-*+]|\d+\.)\s")

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
    # Python-Markdown needs a blank line before a list that follows a paragraph line.
    fixed = []
    for line in lines:
        if LIST_ITEM.match(line) and fixed and fixed[-1].strip() and not LIST_ITEM.match(fixed[-1]):
            fixed.append("")
        fixed.append(line)
    out = markdown.markdown("\n".join(fixed), extensions=["tables", "smarty", "sane_lists"])
    out = re.sub(r"<thead>\s*<tr>\s*(<th[^>]*>\s*</th>\s*)+</tr>\s*</thead>\s*", "", out)  # empty header rows
    return out.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")


def inline(text):
    return re.sub(r"^<p>|</p>$", "", md([text]))


def render_body(lines, prefix):
    """Render a section body; wrap the recurring boxes in <aside>. Returns (html, toc)."""
    out, h2s, h3s, buf = [], [], [], []
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
            rest = rest.strip()
            out.append(f'<aside class="box box-{kind}"><div class="box-label">{html.escape(label.strip())}</div>')
            out.append(f'<h{level} id="{hid}">{inline(rest[:1].upper() + rest[1:])}</h{level}>')
            box_level = level
        else:
            out.append(f'<h{level} id="{hid}">{inline(text)}</h{level}>')
        (h2s if level == 2 else h3s if level == 3 else []).append((hid, plain(text)))
    flush()
    if box_level is not None:
        out.append("</aside>")
    return "\n".join(out), (h2s or h3s)


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


def main():
    lines = SRC.read_text(encoding="utf-8").splitlines()
    blocks = [b for b in split_on(lines, r"^# (.+)$") if b[0]]

    # ---- cover (first H1 block, up to its first rule) ----
    book_title, front = blocks[0]
    rule = front.index("---")
    cover_lines = [l for l in front[:rule] if l.strip()]
    subtitle = next((l.lstrip("# ").strip() for l in cover_lines if l.startswith("###")), "")
    tagline = next((l.strip("* ") for l in cover_lines if l.startswith("*")), "")

    # ---- chapters, interludes, sidebars, appendices ----
    sections, colophon = [], ""
    for bi, (title, body) in enumerate(blocks[1:], start=1):
        sid, n, kind, label, name = classify(title)
        _used_ids.add(sid)

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
        body = [l for l in body if l.strip() != "---"]

        body_html, toc = render_body(body, sid)
        sections.append(dict(id=sid, n=n, kind=kind, label=label, title=name,
                             here=f"{label} · {name}" if label else name,
                             meta=meta, body=body_html, toc=toc))

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
                    l = f"**{group}**" + re.sub(r"Appendix ([A-Z]): [^·]+?(?=\s*·|\s*$)", appendix, g[2])
                elif row and row[2] and not re.fullmatch(r"[-: ]+", row[2]):
                    target = row_target(row[1], row[2])
                    if target in ids:
                        group_of.setdefault(target, group)
                        if row[3]:
                            when[target] = plain(row[3])
                        l = f"| {row[1]} | [{row[2]}](#{target}) | {row[3]} |"
                linked.append(l)
            body = linked
        body_html, toc = render_body([l for l in body if l.strip() != "---"], sid)
        front_sections.append(dict(id=sid, n="", kind="front", label="Before you start", title=title,
                                   here=title, meta=[], body=body_html, toc=toc))
    sections = front_sections + sections

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
                f'<h1>{html.escape(s["title"])}</h1>{meta}</header>'
                f'<div class="chapter-body">{s["body"]}</div></section>')

    page = (TEMPLATE
            .replace("%%DARK%%", DARK_TOKENS)
            .replace("%%BOOK_TITLE%%", html.escape(book_title))
            .replace("%%SUBTITLE%%", html.escape(subtitle))
            .replace("%%TAGLINE%%", html.escape(tagline))
            .replace("%%NAV%%", "".join(nav))
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
    resume.hash = saved;
    resume.querySelector("span").textContent = sec.dataset.here;
    if (savedEl !== sec) resume.title = savedEl.textContent;
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
