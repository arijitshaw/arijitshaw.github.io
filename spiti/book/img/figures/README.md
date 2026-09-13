# Eight diagrams for the Spiti book

Hand-drawn-looking SVGs, one per argument. No external fonts, no scripts, no network —
each file is self-contained and will render the same offline in ten years.

| File | Does the work of |
| --- | --- |
| `01-drainage.svg` | Chapter 0 and Chapter 13 — the Kunzum watershed |
| `02-pare-chu.svg` | Interlude V — the river that leaves India and comes back |
| `03-passes.svg` | Interlude XI — Spiti as a crossroads |
| `04-elevation.svg` | the Body sidebar and Chapter 12 — the acclimatisation sawtooth |
| `05-kailash.svg` | Interlude V — four rivers, four directions |
| `06-tabo-plan.svg` | Interlude VIII — navigating the Tsuglakhang |
| `07-kath-kuni.svg` | Interlude II — how the wall is built |
| `08-wheel-of-life.svg` | Interlude VIII — finding the pig, the snake and the bird |

## Dropping them in

Markdown, and therefore GitHub Pages:

```markdown
![One saddle, two rivers](figures/01-drainage.svg)
```

HTML, if you want to control the width:

```html
<img src="figures/01-drainage.svg" alt="One saddle, two rivers"
     style="width:100%;max-width:560px;height:auto">
```

Each file carries a `<title>` and a `<desc>`, so screen readers get a real description
rather than the filename. Keep the `alt` short; the `desc` does the heavy lifting.

## They follow the page into dark mode

Every file has a `prefers-color-scheme: dark` block inside it. On a printed page or a
white site the ink is near-black on nothing; on your dark site the ink flips to bone and
the blues and reds lighten to match. You do not have to ship two versions, and you do not
have to do anything to switch — the file reads the reader's setting.

This works when the SVG is used as `<img>`, as a CSS background, or inlined. It does *not*
work if something rasterises the file to PNG first.

## Changing them

Open any file in a text editor. The first thing inside is a `<style>` block with every
colour and the type stack in it. Change `#2f2b26` and you have changed the ink everywhere
in that figure.

The type is deliberately *not* a handwriting face. The linework is hand-drawn — every
stroke is a bezier nudged off true and drawn twice — but the labels are set in a plain old
serif, because handwriting fonts at 12px on a map go illegible fast and date badly. If you
want the labels in something else, change the `font-family` line in the `<style>` block. If
you want them in an actual handwriting face, `Caveat` and `Architects Daughter` both work
at these sizes; you would need to add a webfont link, which costs you the offline
guarantee.

## What these are not

None of them is to scale and none of them is navigable. `01` is a plumbing diagram with no
geography in it at all; `02` and `03` are schematic and the distances are wrong on purpose;
`06` is a sketch plan, not a survey. They are arguments with lines round them. Use the
offline Google Maps for actually finding things.

## Sources, figure by figure

**01 · drainage.** Kunzum La divides the Chandra catchment from the Spiti. Chandra + Bhaga
meet at Tandi and become the Chenab; the Spiti joins the Sutlej at Khab. The Beas rises
below Rohtang and joins the Sutlej at Harike. Chenab and Sutlej meet at Uch Sharif to form
the Panjnad, which joins the Indus at Mithankot. Kunzum's height is given as 4,590 m to
match your preparation page; the Lahaul–Spiti district site says 4,551 m and both figures
circulate.

**02 · Pare Chu.** Rises near Parang La (c. 5,580 m), runs north-east then east, crosses
into Tibet, is turned back by the Drongmar range, and re-enters India to join the Spiti at
Sumdo (c. 3,200 m). About 210 km end to end. The landslide dam formed in 2004 and the lake
burst on 26 June 2005, destroying stretches of NH-22 between Sumdo and Wangtu; about 5,000
people were evacuated along the Sutlej and nobody was killed. Sources: Survey of India
gazetteer material via Wikipedia, NASA Earth Observatory's ASTER imagery of the lake
(July 2004 and July 2005), and contemporary Indian press.

**03 · passes.** Parang La 5,578 m (Ladakh), Manirang 5,550 m (Ropa valley, Kinnaur),
Pin–Parvati 5,319 m (Kullu), Pin–Bhaba 4,890 m (Bhaba valley, Kinnaur), Kunzum La 4,590 m
(Lahaul), Shipki La 4,600 m (Tibet, reached down the Spiti and up the Sutlej). Elevations
from the Lahaul & Spiti district administration's list of passes and the usual references.
Note that the figure draws **six** passes; your Interlude XI text says five directions. See
the note below.

**04 · elevation.** Every sleeping altitude and date is from your preparation page. Daytime
maxima: Komic 4,587 m (Day 6), Chicham bridge 4,145 m (Day 7), Kunzum La 4,590 m (Day 8).
The 937 m figure is Komic minus Kaza; the 2,287 m is Chandratal minus Manali.

**05 · Kailash.** Indus north (Senge Khabab, the Lion's Mouth), Brahmaputra east (Tamchok,
the Horse's Mouth), Karnali south (Mapcha, the Peacock's Mouth), Sutlej west (Langchen, the
Elephant's Mouth). All four rise within roughly 100 km of the peak; the Himalayan Journal
puts it at 125 km. Sacred to Hinduism, Buddhism, Jainism and Bon.

**06 · Tabo.** Plan after Christian Luczanits' schematic of the Main Temple, which is the
standard reference. Three units from the foundation of 996: entry hall (Go-khang, with
Yeshe Ö and his sons Nagaraja and Devaraja on the south wall), assembly hall (Du-khang, 33
clay sculptures of the Vajradhatu mandala, four-fold Vairocana at the west end), and the
cella (Ti-tsang-khang, stucco Amitabha and two attendants) inside a three-sided ambulatory
(Kor-lam-khang). The porch in front is modern. Most of the painting dates from the 1042
renovation; the entry hall keeps more of the original.

**07 · kath-kuni.** From *kāshth* (wood) and *kona* (corner). Alternating courses of
dry-laid stone and paired deodar beams with rubble packed between; the two skins tied by
cross-braces or dovetails (*maanvi*) and pegged with wooden *kadil*; corners interlocked,
alternating direction each course; stone decreasing and wood increasing as the wall rises.
Sources: the CEPT/SID *Prathaa* study, and Kumar & Sarhosis' 2023 field survey in
*Proceedings of the ICE*, which identifies corner interlocking as a main contributor to the
seismic performance.

**08 · Wheel of Life.** A generic bhavachakra schematic, not a copy of any particular
painting — the one at Tabo is a fragment in the entry hall, so what you see on the wall will
not match this exactly. Standard arrangement: three animals at the hub, the pale and dark
band, six realms, twelve links round the rim, Yama holding the whole thing.

## One thing to reconcile

Interlude XI says Spiti had five ways out. The figure has six, because Pin–Parvati and
Pin–Bhaba are genuinely separate passes going to separate places (Kullu and Kinnaur) even
though both start up the Pin. If you meant five *directions* rather than five passes, the
figure supports that reading too — but the text and the picture should agree, so either the
line becomes "six ways out" or the caption should say "five directions, six passes".
