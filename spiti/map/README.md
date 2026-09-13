# Spiti circuit route map

An interactive route map for the Shimla – Kinnaur – Kaza – Chandratal – Manali circuit,
16–24 September 2026. Leaflet over OpenStreetMap-derived tiles, no build step, no API key.

## Files

| File | What it is |
| --- | --- |
| `index.html` | The whole map. Self-contained apart from two CDN scripts. Open it directly in a browser to check it. |
| `route.geojson` | The same route and stops as GeoJSON. Not loaded by the page — it is there so you can open the route in QGIS, Google Earth, Gaia, or feed it to something else. |
| `route-data.json` | The source data the page was generated from. Same content, shaped for editing rather than for GIS. |

## Putting it on the site

Drop the folder in the repo, say at `spiti/map/`, and it works as a standalone page at
`/spiti/map/`. To put it inside the preparation page instead:

```html
<iframe src="/spiti/map/" title="Spiti circuit route map"
        style="width:100%;aspect-ratio:4/3;border:1px solid #43403a;border-radius:3px"
        loading="lazy"></iframe>
```

On narrow screens `aspect-ratio:3/4` reads better than `4/3`. The page has no fixed height of
its own, so the iframe decides how tall the map is.

## How to read it

- The eight coloured discs are night halts, numbered in order. Disc colour runs from bone at
  2,165 m to deep slate at 4,337 m, so the trip visibly gets colder as it goes anticlockwise.
- The two small white discs are Shimla and Manali.
- Small yellow dots are the high-altitude day stops. Their labels appear from zoom 10 in, to
  keep the overview readable.
- The dashed loop above Kaza is the Langza–Hikkim–Komic day trip. Kibber and Chicham sit on
  the main line, because Day 7 genuinely drives through them.
- The strip in the panel is the altitude profile. Every point is clickable, as is every disc
  on the map. Escape, or "Show whole route", zooms back out.

## Things you will probably want to change

**The base map.** Three are wired up in the `BASES` object near the top of the script:
OpenStreetMap (default), OpenTopoMap, and Esri World Imagery. (CARTO Voyager was the original
default, but its tiles now show an "API key required" watermark without a key.) Each carries the attribution its
licence requires — if you swap a provider, move its attribution string across too. All three
are free for a personal site at this traffic level; none is suitable for heavy commercial use.

**The colours and type.** Everything is in the `:root` block at the top of the stylesheet.
`--route` is the yellow of the line, `--warm` and `--cold` are the two ends of the altitude
ramp, `--ink` matches the theme colour already on the site. Swap `--font` and `--font-map` to
your own faces and delete the Google Fonts `<link>` if you would rather not load them.

**Label placement.** `LABEL_DIR` maps each stop to `left`, `right`, `top` or `bottom`. If two
names collide at your default zoom, change one of these.

**The line itself.** Read this bit before you publish.

## The route line is drawn by hand, not traced

The polyline follows the real road alignment through a few hundred waypoints, which is
accurate enough at the zoom the map opens at. Zoom in past about 12 and you will see it cut
corners on switchbacks — the Narkanda descent and the Kinnaur gorge especially. It is a
schematic of the route, not a GPS trace.

To replace it with a real one:

1. Get a trace. Export the leg from Google Maps, or record it on the drive, or pull the road
   geometry from OpenStreetMap.
2. Convert to GeoJSON if it is GPX (`gpsbabel`, or <https://mapstogeojson.com>).
3. In `index.html`, find the `legs` array inside `const DATA = {…}` and replace the `coords`
   array for that day. Coordinates are `[latitude, longitude]` — note that GeoJSON stores them
   the other way round, so you will need to flip each pair.
4. Each leg must start exactly where the previous one ended, or the line will show a gap.

Everything else — markers, profile, panel — reads from the `stops` array and is unaffected.

## Credits

Map data © OpenStreetMap contributors, ODbL. Tile styles © OpenTopoMap (CC-BY-SA)
and © Esri. Leaflet 1.9.4, BSD-2-Clause.

Altitudes and night temperatures are the figures from the preparation page, which lean
deliberately towards the cold end.
