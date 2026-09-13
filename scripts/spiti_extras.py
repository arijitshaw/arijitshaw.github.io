"""Build-time extras for the Spiti long read, called from build_spiti_book.py.

search_records               T2.1  one search record per section and heading, deep-linkable
parse_glossary/link_glossary T2.7  first use of each Appendix D word per chapter gets a definition popover
index_section                T2.8  curated A–Z index from content/index-terms.yml
today_links                  T2.9  date → chapters, from content/today.json
build_practical              T3.2  spiti/practical/ from spiti/practical/practical.md
write_unverified             T4.3  content/unverified.md from TODO(verify) markers, map notes, content/volatile.yml
write_shot_list              T5.1  content/shot-list.md
"""
import datetime
import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


def _text(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _ascii(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def short_label(s):
    label = s.get("label") or ""
    if label.startswith("Chapter"):
        return "Ch " + label.split()[-1]
    if label.startswith("Interlude"):
        return "Interlude " + (s.get("n") or label.split()[-1])
    return label or s["title"]


# ----------------------------------------------------------------------------------------- search

SKIP_SEARCH = {"image-credits", "index"}


def search_records(sections):
    """One record per section intro and per h2/h3, so a result can jump straight to its heading."""
    docs = []
    for s in sections:
        if s["id"] in SKIP_SEARCH:
            continue
        body = re.sub(r"<figure\b.*?</figure>", " ", s["body"], flags=re.S)
        body = re.sub(r'<div class="(?:box|h)-label">(.*?)</div>\s*(<h[23] id="[^"]+"[^>]*>)', r"\2\1: ", body, flags=re.S)
        crumb = " · ".join(x for x in (s.get("label"), s["title"]) if x)
        short = short_label(s)
        anchor, title, buf = s["id"], s["title"], []

        def flush():
            raw = " ".join(buf)
            text = _text(raw)
            if text or anchor == s["id"]:
                strong = " | ".join(_text(x) for x in re.findall(r"<strong>(.*?)</strong>", raw, flags=re.S))
                docs.append({"id": len(docs), "a": anchor, "k": s["id"], "c": crumb, "s": short, "t": title, "b": text,
                             "st": strong})

        for part in re.split(r'(<h[23] id="[^"]+"[^>]*>.*?</h[23]>)', body, flags=re.S):
            m = re.match(r'<h[23] id="([^"]+)"[^>]*>(.*?)</h[23]>', part, flags=re.S)
            if m:
                flush()
                anchor, title, buf = m.group(1), _text(m.group(2)), []
            else:
                buf.append(part)
        flush()
    return docs


def load_aliases(path):
    if not path.exists():
        return []
    groups = json.loads(path.read_text(encoding="utf-8")).get("groups", [])
    return [[_ascii(v).lower().strip() for v in g if v.strip()] for g in groups if len(g) > 1]


# ----------------------------------------------------------------------------------------- glossary

GLOSS_SKIP = {"la", "lha", "tso", "taal", "khar", "dhang", "nala", "kul", "losar", "negi", "gur", "rath", "mani",
              "boti", "dham", "ri", "cham", "chuba"}
GLOSS_NO_SECTIONS = {"appendix-d", "image-credits", "index"}
_BLOCKING = {"a", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "figure", "strong", "b", "button", "svg",
             "summary", "th", "script", "style", "title", "desc", "text", "em"}
_VOID = {"br", "img", "hr", "input", "source", "wbr", "meta", "link"}


def parse_glossary(md_text):
    m = re.search(r"^# Appendix [A-Z] · Words\s*$(.*?)(?=^# |\Z)", md_text, flags=re.S | re.M)
    entries = []
    if not m:
        return entries
    for line in m.group(1).splitlines():
        if not line.lstrip().startswith("- "):
            continue
        for tm in re.finditer(r"\*\*([^*]+)\*\*\s*—\s*(.*?)(?=\s*\*\*[^*]+\*\*\s*—|$)", line):
            names = [n.strip() for n in tm.group(1).split("/") if n.strip()]
            entries.append((names, tm.group(2).strip().rstrip(".")))
    return entries


def link_glossary(sections, entries):
    """First use of each glossary word in each section becomes a button that shows the definition.
    Skips headings, captions, links, bold (where words are usually being defined) and the glossary itself."""
    data, compiled = [], []
    for names, definition in entries:
        variants = [n for n in names if n.lower() not in GLOSS_SKIP and len(n) >= 3]
        if not variants:
            continue
        compiled.append((len(data), re.compile(
            r"(?<![\w’'-])(" + "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True)) + r")(?![\w’'-])",
            re.I)))
        data.append([" / ".join(names), html.escape(re.sub(r"\*([^*]+)\*", r"\1", definition))])
    for s in sections:
        if s["id"] in GLOSS_NO_SECTIONS or s.get("kind") == "front":
            continue
        used, out, stack = set(), [], []
        for part in re.split(r"(<[^>]+>)", s["body"]):
            if part.startswith("<"):
                m = re.match(r"<(/?)\s*([a-zA-Z0-9]+)", part)
                if m:
                    name = m.group(2).lower()
                    if m.group(1):
                        if name in stack:
                            while stack and stack.pop() != name:
                                pass
                    elif name not in _VOID and not part.endswith("/>"):
                        stack.append(name)
                out.append(part)
                continue
            if not part.strip() or any(t in _BLOCKING for t in stack):
                out.append(part)
                continue
            spans = []
            for idx, pat in compiled:
                if idx in used:
                    continue
                for m in pat.finditer(part):
                    if all(m.end() <= a or m.start() >= b for a, b, _ in spans):
                        spans.append((m.start(), m.end(), idx))
                        used.add(idx)
                        break
            if spans:
                spans.sort()
                pos, buf = 0, []
                for a, b, idx in spans:
                    buf += [part[pos:a], f'<button type="button" class="gloss" data-g="{idx}">{part[a:b]}</button>']
                    pos = b
                buf.append(part[pos:])
                part = "".join(buf)
            out.append(part)
        s["body"] = "".join(out)
    return data


# ----------------------------------------------------------------------------------------- A–Z index

def _parse_terms(path):
    terms, group = [], None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith((" ", "-")) and raw.rstrip().endswith(":"):
            group = raw.strip()[:-1]
            continue
        m = re.match(r"\s*-\s+(.*)$", raw)
        if m:
            names = [n.strip() for n in m.group(1).split("|") if n.strip()]
            if names:
                terms.append((group, names))
    return terms


def _sort_key(name):
    return re.sub(r"^(the|a|an)\s+", "", _ascii(name).lower())


def index_section(sections, terms_path, warnings):
    """Curated A–Z index: each term links to every section where it is substantively discussed
    (named in the heading, set in bold where it is introduced, or used at least twice in that part)."""
    if not terms_path.exists():
        return None
    docs = [d for d in search_records(sections) if d["k"] not in ("contents", "how-to-use", "one-thing-to-notice-each-day")]
    entries = []
    for _group, names in _parse_terms(terms_path):
        pats = [re.compile(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", re.I) for n in names]
        hits = [d for d in docs if any(p.search(d["t"]) or p.search(d["st"]) for p in pats)
                or sum(len(p.findall(d["b"])) for p in pats) >= 2]
        if not hits:
            warnings.append(f"index term {names[0]!r} has no substantive mention in the book (content/index-terms.yml)")
            continue
        entries.append((names[0], hits[:8]))
    entries.sort(key=lambda e: _sort_key(e[0]))
    by_letter = defaultdict(list)
    for name, hits in entries:
        by_letter[_sort_key(name)[:1].upper()].append((name, hits))
    letters = sorted(by_letter)
    nav = "".join(f'<a href="#index-{l.lower()}">{l}</a>' for l in letters)
    parts = [f'<nav class="ix-letters" aria-label="Index letters">{nav}</nav>']
    for letter in letters:
        items = []
        for name, hits in by_letter[letter]:
            links = "; ".join(
                f'<a href="#{d["a"]}" title="{html.escape(d["c"])}">{html.escape(d["s"])}'
                f'{": " + html.escape(d["t"]) if d["a"] != d["k"] else ""}</a>' for d in hits)
            items.append(f'<li><span class="ix-term">{html.escape(name)}</span> {links}</li>')
        parts.append(f'<p class="ix-letter" id="index-{letter.lower()}">{letter}</p><ul class="ix">{"".join(items)}</ul>')
    return dict(id="index", n="", kind="back", label="", title="Index", here="Index",
                meta=[("People, places, food and ideas, and where each is actually discussed.", True)],
                body="".join(parts), toc=[], hero="")


# ----------------------------------------------------------------------------------------- today

def today_links(path, sections, errors):
    if not path.exists():
        return {}
    by_id = {s["id"]: s for s in sections}
    out = {}
    for date, ids in json.loads(path.read_text(encoding="utf-8")).items():
        if date.startswith("_"):
            continue
        d = datetime.date.fromisoformat(date)
        links = []
        for i in ids:
            if i not in by_id:
                errors.append(f"content/today.json: {date} points at unknown section {i!r}")
                continue
            s = by_id[i]
            links.append({"id": i, "text": f"{short_label(s)} ({s['title']})" if s.get("label") else s["title"]})
        out[date] = {"label": f"{d.day} {d.strftime('%b')}", "links": links}
    return out


def data_scripts(gloss, today):
    j = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (f'<script type="application/json" id="glossary-data">{j(gloss)}</script>'
            f'<script type="application/json" id="today-data">{j(today)}</script>'
            '<div class="gloss-pop" id="gloss-pop" role="status" aria-live="polite" hidden></div>')


# ----------------------------------------------------------------------------------------- practical page

PRACTICAL_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Practical · Spiti Circuit</title>
<meta name="description" content="Fuel, cash, signal, emergency numbers, permits, opening hours, responsible travel and phrases for the Spiti circuit, 16–24 September 2026.">
<meta name="theme-color" content="#201f1d">
<link rel="manifest" href="../manifest.webmanifest">
<link rel="apple-touch-icon" href="../icons/apple-touch-icon.png">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Spiti">
<script src="../pwa.js" defer></script>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🧭</text></svg>">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=Lora:ital,wght@0,400;0,600;1,400&display=swap">
<script>try{var t=localStorage.getItem("spiti-theme");if(t)document.documentElement.dataset.theme=t;var z=localStorage.getItem("spiti-size");if(z)document.documentElement.dataset.size=z}catch(e){}</script>
<!-- generated by scripts/build_spiti_book.py from spiti/practical/practical.md; edit the markdown, not this file -->
<style>%%CSS%%
main.prac{margin-left:0;padding:calc(var(--top) + 8px) 16px 96px}
.prac .page{max-width:46rem}
.prac-toc{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin:0 0 20px}
.prac-toc a{padding:7px 13px;border:1px solid var(--divider);border-radius:999px;text-decoration:none;color:var(--text);font:600 15px/1.2 var(--display);background:var(--surface)}
.prac-sec{padding-top:28px;scroll-margin-top:var(--top)}
.prac-sec > h2{font:600 32px/1.1 var(--display);margin:0 0 .5em;padding-top:22px;border-top:1px solid var(--divider)}
.toplinks{display:flex;gap:14px;margin-left:auto;padding-right:10px;font:600 16px/1 var(--display)}
.toplinks a{color:inherit;text-decoration:none}
.prac .table-wrap table{font-size:14px}
.prac td:first-child{white-space:normal}
</style>
</head>
<body>
<header class="topbar">
  <a class="icon-btn" href="../" aria-label="Spiti Circuit home" title="Spiti Circuit home">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"><path d="M2 19 9 8l4 6 3-4 6 9Z"/></svg>
  </a>
  <span class="here" style="cursor:default">%%TITLE%%</span>
  <nav class="toplinks"><a href="../book/">Book</a><a href="../preparation/">Packing</a><a href="../map/">Map</a></nav>
</header>
<main class="prac"><div class="page">
  <header class="chapter-head"><div class="kicker">Spiti Circuit · 16–24 September 2026</div><h1>%%TITLE%%</h1><p class="meta note">%%INTRO%%</p></header>
  <nav class="prac-toc" aria-label="Sections">%%CHIPS%%</nav>
  <div class="chapter-body">%%BODY%%</div>
</div></main>
</body>
</html>
"""


def build_practical(src, out, render_body, inline, template, dark_tokens, errors):
    if not src.exists():
        return
    lines = src.read_text(encoding="utf-8").splitlines()
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), "Practical")
    intro = next((l.strip() for l in lines if l.strip().startswith("*") and not l.strip().startswith("**")), "")
    secs, cur = [], None
    for line in lines:
        m = re.match(r"^## (.+?)\s*\{#([a-z0-9-]+)\}\s*$", line)
        if m:
            cur = {"title": m.group(1), "id": m.group(2), "lines": []}
            secs.append(cur)
        elif cur is not None and not line.startswith("# "):
            cur["lines"].append(line)
    body = []
    for s in secs:
        rendered, _ = render_body([l for l in s["lines"] if l.strip() != "---"], f"p-{s['id']}")
        body.append(f'<section class="prac-sec" id="{s["id"]}"><h2>{html.escape(s["title"])}</h2>{rendered}</section>')
    css = re.search(r"<style>(.*?)</style>", template, re.S).group(1).replace("%%DARK%%", dark_tokens)
    page = (PRACTICAL_TEMPLATE.replace("%%CSS%%", css).replace("%%TITLE%%", html.escape(title))
            .replace("%%INTRO%%", inline(intro.strip("*")) if intro else "")
            .replace("%%CHIPS%%", "".join(f'<a href="#{s["id"]}">{html.escape(s["title"])}</a>' for s in secs))
            .replace("%%BODY%%", "".join(body)))
    ids = set(re.findall(r'\sid="([^"]+)"', page))
    for h in sorted(set(re.findall(r'href="#([^"]+)"', page))):
        if h not in ids:
            errors.append(f"practical page: link to #{h} points at nothing")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out.relative_to(out.parents[2])} ({len(secs)} sections)")


# ----------------------------------------------------------------------------------------- unverified / volatile

def _parse_volatile(path):
    items, cur = [], None
    if not path.exists():
        return items
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = re.match(r"^-\s+(\w+):\s*(.*)$", raw)
        if m:
            cur = {m.group(1): m.group(2).strip()}
            items.append(cur)
            continue
        m = re.match(r"^\s+(\w+):\s*(.*)$", raw)
        if m and cur is not None:
            cur[m.group(1)] = m.group(2).strip()
    return items


def write_unverified(root, warnings, today=None):
    """content/unverified.md: every TODO(verify) marker, every approximate map feature, and every volatile
    claim that has never been checked. Expired volatile claims are also build warnings."""
    today = today or datetime.date.today()
    out = ["# Unverified claims", "",
           "Generated by `scripts/build_spiti_book.py`. Work through this list before (or during) the trip; "
           "remove a `TODO(verify)` from the markdown once a claim is checked, and record the check in "
           "`content/volatile.yml`.", ""]
    total = 0
    for rel in ("spiti/book/spiti-circuit-the-long-read.md", "spiti/practical/practical.md"):
        p = root / rel
        if not p.exists():
            continue
        rows, heading, sub = [], "", ""
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("# "):
                heading, sub = line[2:].strip(), ""
            elif line.startswith("#"):
                sub = line.lstrip("#").strip()
            if "TODO(verify)" in line:
                ctx = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
                ctx = re.sub(r"\*\*?|`", "", ctx).strip(" -|")
                rows.append(f"- [ ] **{heading}{' › ' + sub if sub else ''}** (line {n}): {ctx}")
        if rows:
            out += [f"## `{rel}` ({len(rows)})", ""] + rows + [""]
            total += len(rows)
    maps = root / "content" / "unverified-maps.json"
    if maps.exists():
        rows = [f"- [ ] **{m['map']}**{' › ' + m['place'] if m['place'] else ''}: {m['why']}"
                for m in json.loads(maps.read_text(encoding="utf-8"))]
        if rows:
            out += [f"## Maps ({len(rows)})", ""] + rows + [""]
            total += len(rows)
    vol = _parse_volatile(root / "content" / "volatile.yml")
    never = [v for v in vol if v.get("verified", "never") == "never"]
    expired = [v for v in vol if v.get("expires") and datetime.date.fromisoformat(v["expires"]) < today]
    if never:
        out += [f"## Volatile claims never checked ({len(never)})", ""]
        out += [f"- [ ] {v.get('claim')} — *{v.get('where', '')}*, source: {v.get('source', '?')}" for v in never] + [""]
        total += len(never)
    if expired:
        out += [f"## Volatile claims past their expiry ({len(expired)})", ""]
        out += [f"- [ ] {v.get('claim')} — expired {v['expires']}, last checked {v.get('verified')}" for v in expired] + [""]
        for v in expired:
            warnings.append(f"volatile claim past expiry ({v['expires']}): {v.get('claim')}")
    out.insert(3, f"**{total} items.**\n")
    (root / "content" / "unverified.md").write_text("\n".join(out), encoding="utf-8")
    print(f"wrote content/unverified.md ({total} items)")


# ----------------------------------------------------------------------------------------- shot list

def write_shot_list(root, images, sections):
    where = {}
    for s in sections:
        where[s["title"]] = s["here"]
        for h in re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", s["body"], flags=re.S):
            where.setdefault(_text(h), s["here"])
    by_section = defaultdict(list)
    for img in images:
        by_section[where.get(img["anchor"], "(unplaced)")].append(img)
    counts = Counter(re.sub(r"^(This Photo was taken by)\s*", "", img.get("credit", "")).split(".")[0] for img in images)
    heavy = {c: n for c, n in counts.items() if n >= 5 and c}
    lines = ["# Shot list", "",
             "Generated by `scripts/build_spiti_book.py` from `spiti/book/images.json`. For each chapter: the "
             "photographs the book uses now, and what to shoot to replace them on the trip.", ""]
    if heavy:
        lines += ["**Over-represented photographers** (the book leans on one set): "
                  + ", ".join(f"{c} ({n})" for c, n in sorted(heavy.items(), key=lambda x: -x[1])), ""]
    order = [s["here"] for s in sections] + ["(unplaced)"]
    for here in order:
        imgs = by_section.get(here)
        if not imgs:
            continue
        lines += [f"## {here}", ""]
        for img in imgs:
            subject = img.get("caption") or img.get("after") or img["anchor"]
            lines.append(f"- [ ] `{img['file']}` — {subject} — {img.get('credit', '?')} ({img.get('license', '?')})  ")
            lines.append(f"  Shoot: {img.get('after') or img['anchor']}, in the same framing, on the trip.")
        lines.append("")
    (root / "content" / "shot-list.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote content/shot-list.md ({len(images)} images)")
