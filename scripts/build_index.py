import os, re, json, pathlib
NOTES_DIR = 'notes'
BUILD_DIR = 'build/notes'
os.makedirs('build', exist_ok=True)

def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r'[^a-z0-9\-]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s or 'untitled'

def extract_title(tex_path: str) -> str | None:
    try:
        with open(tex_path, 'r', encoding='utf-8') as f:
            data = f.read(4096)  # read a chunk; good enough for title
        m = re.search(r'\\title\{([^}]*)\}', data, flags=re.S)
        if m:
            title = re.sub(r'\s+', ' ', m.group(1)).strip()
            return title
    except Exception:
        pass
    return None

items = []
for fn in sorted(os.listdir(NOTES_DIR)):
    if not fn.endswith('.tex'): continue
    base = fn[:-4]
    slug = slugify(base)
    title = extract_title(os.path.join(NOTES_DIR, fn)) or base
    items.append({'slug': slug, 'title': title, 'filename': fn})

with open('build/index.json', 'w', encoding='utf-8') as f:
    json.dump(items, f, ensure_ascii=False, indent=2)

print(f"Wrote build/index.json with {len(items)} items.")
