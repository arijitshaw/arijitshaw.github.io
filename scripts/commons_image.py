#!/usr/bin/env python3
"""Add Wikimedia Commons images to the Spiti long read.

    python3 scripts/commons_image.py picks.json
    python3 scripts/commons_image.py "Tabo" "File:Tabo Gompa.jpg" "Tabo from the terrace"

picks.json is a list of {"anchor", "title", "caption", "alt"}:
  anchor   a chapter title or a ## / ### heading, exactly as written in the markdown
           (without the #s or *s); chapter titles get a full-width image under the title,
           headings get the image after their first paragraph
  title    the Commons file name, e.g. "File:Key Monastery.jpg"

Each image is shrunk to a web-sized WebP in spiti/book/img/, and its author, licence and
source page go into spiti/book/images.json, which `make spiti-book` reads.
Remove an image by deleting its entry from images.json (and the file from img/).
"""
import io
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
BOOK = ROOT / "spiti" / "book"
IMG, DB = BOOK / "img", BOOK / "images.json"
# English Wikipedia's API serves Commons files too, and is far less aggressively rate-limited.
API = "https://en.wikipedia.org/w/api.php"
MAX_W, QUALITY = 1200, 72

S = requests.Session()
S.headers["User-Agent"] = "SpitiLongReadBuilder/1.0 (static travel site; python-requests)"


def get(url, **kw):
    for attempt in range(6):
        r = S.get(url, timeout=60, **kw)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(3 + 4 * attempt)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()


def strip(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h or "")).strip()


def slug(text):
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60].strip("-")


def add(pick, db):
    r = get(API, params=dict(action="query", format="json", titles=pick["title"], prop="imageinfo",
                             iiprop="url|size|extmetadata", iiurlwidth=1280,
                             iiextmetadatafilter="LicenseShortName|Artist|Credit"))
    page = next(iter(r.json()["query"]["pages"].values()))
    if "imageinfo" not in page:
        print(f"skip {pick['title']}: not found on Commons")
        return
    ii, meta = page["imageinfo"][0], page["imageinfo"][0].get("extmetadata", {})
    licence = strip(meta.get("LicenseShortName", {}).get("value")) or "licence unchecked"
    author = strip(meta.get("Artist", {}).get("value")) or strip(meta.get("Credit", {}).get("value")) or "Unknown author"

    name = slug(page["title"].removeprefix("File:").rsplit(".", 1)[0]) + ".webp"
    out = IMG / name
    if not out.exists():
        raw = get(ii.get("thumburl") or ii["url"]).content
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
        if im.width > MAX_W:
            im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
        im.save(out, "WEBP", quality=QUALITY, method=6)
    w, h = Image.open(out).size

    entry = dict(anchor=pick["anchor"], file=name, w=w, h=h, caption=pick.get("caption", ""),
                 alt=pick.get("alt") or pick.get("caption", ""), credit=author[:120], license=licence,
                 source=ii["descriptionurl"])
    for i, old in enumerate(db):
        if old["source"] == entry["source"] and old["anchor"] == entry["anchor"]:
            db[i] = entry
            break
    else:
        db.append(entry)
    print(f"{name:62} {w}x{h} {out.stat().st_size // 1024:4} KB  {licence:14} {author[:40]}")


def main():
    if len(sys.argv) == 2:
        picks = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    elif len(sys.argv) in (3, 4):
        picks = [dict(anchor=sys.argv[1], title=sys.argv[2], caption=sys.argv[3] if len(sys.argv) == 4 else "")]
    else:
        sys.exit(__doc__)
    IMG.mkdir(parents=True, exist_ok=True)
    db = json.loads(DB.read_text(encoding="utf-8")) if DB.exists() else []
    try:
        for pick in picks:
            add(pick, db)
    finally:
        DB.write_text(json.dumps(db, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
