# Class Notes Website (LaTeXML-based)

This template lets you keep notes as LaTeX files and view them on a simple website. The left sidebar lists your classes; clicking one loads the corresponding HTML (converted from LaTeX via LaTeXML).

## Quick start
1. **Install LaTeXML** (one of the following):
   - Ubuntu/Debian: `sudo apt-get install latexml`
   - Perl CPAN: `cpanm LaTeXML` (after installing cpanminus)
2. Put your `.tex` files into `notes/`.
3. Build:
   ```bash
   make
   ```
4. Serve locally (browsers block `fetch()` on `file://`):
   ```bash
   make serve
   # then open http://localhost:8000
   ```

## Notes
- Generated HTML goes to `build/notes/`.
- Sidebar entries are created from `build/index.json` (auto-made by `scripts/build_index.py`).
- The title shown in the sidebar comes from `\title{...}` in each LaTeX file; if missing, the filename is used.
- You can deploy this folder to any static host (e.g., GitHub Pages). Include the `build/` directory in your commits or set up CI to run `make` on push.

## Clean
```
make clean
```
