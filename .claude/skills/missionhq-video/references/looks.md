# Looks

A look is the full visual system: page, type, cards, charts, captions and motion. Choose it before
the first full render, with samples, because changing it later means rebuilding every scene.

## How to choose

1. Pick one real scene from the lesson with a chart, a formula and a takeaway.
2. Render it for 30 seconds in two or three looks, with the same voice.
   The three samples the owner chose from are not kept here; the chosen look is Sketchbook.
3. Send the clips and let the user pick. Mixing is allowed, for example look B with the captions of A.

On 2026-10-03 a user rejected the dark magenta kit as "not modern" for YouTube and chose
**Sketchbook**. Treat Sketchbook as the default for lesson and course videos, and the dark kit as
the default for product demos of dark dashboards.

## The three looks

| | Editorial light | Midnight glass | **Sketchbook** |
|---|---|---|---|
| Page | warm off-white `#F5F2EA` | near-black `#05060A`, slow purple and cyan glows, dot grid | graph paper `#FBFAF6`, 48 px grid |
| Headline | Instrument Serif, italic accent word in blue | Geist 600, gradient text on key words | Caveat 700, yellow highlighter behind key words |
| Body | Inter | Geist | Inter |
| Formulas | JetBrains Mono | Geist Mono | JetBrains Mono |
| Cards | white, soft shadow, radius 20 | glass: 3.5% white, hairline border, blur | hand-drawn border that draws itself in, white fill |
| Accents | `#2B50FF` blue, `#FF5A1F` orange | `#A78BFA` violet, `#22D3EE` cyan | `#E8590C` orange, `#1971C2` blue, `#2F9E44` green, `#6741D9` violet |
| Feels like | Stripe or magazine explainer | Linear or Vercel launch | Excalidraw whiteboard |

All three use word-by-word captions: the phrase stays on screen and each word darkens as it is spoken.

## Sketchbook kit (`video/src/kit-sketch/visuals.tsx` in Mission HQ)

| Component | What it does |
|---|---|
| `Lesson` | paper, wobble filters, label top right, progress bar |
| `BeatShell` | one beat: visual, voice, captions, handwritten heading, slow push-in (scale 1 → 1.022) |
| `Phase` | a scene change inside a beat |
| `Panel`, `Node`, `Chip`, `Table` | hand-drawn boxes; `drawAt` draws the border in, `hotAt` re-inks it with a pastel fill |
| `Arrow` | curved hand-drawn arrow that draws itself in |
| `Big` | big handwritten number with a highlighter stroke |
| `Marker` | highlighter that wipes in behind inline text |
| `MonoLines` | formula lines that appear one by one, `hlAt` highlights one |
| `Numbered` | list with hand-drawn circles; the current item is orange |
| `Evidence` | yellow sticky note with tape, for every external source |
| `Chart` | axes, series that draw in, dashed thresholds, labelled dots, all with wobble |
| `Card` | title card |
| `at`, `cue`, `prog`, `hash` | timing helpers; `hash` replaces `Math.random` |

Rules that keep the look clean:

- **The wobble filter needs a fixed region.** `filterUnits="userSpaceOnUse"` with a large x/y/width/height.
  The default bounding-box region is zero high for a horizontal line, and the line disappears.
- **The parent of a `SketchRect` needs `position: relative` and `zIndex: 0`.** The rect sits at
  `zIndex: -1` so the fill paints under the text without covering it.
- Fonts load through `@remotion/google-fonts` at module level, with only the weights in use.
- One colour per category for the whole video: cascade orange, router blue, OK green, warning
  violet. Pastel fills come from `pastel(color)`.
- Use `filter: url(#rough)` on plain bars and blocks so they match the hand-drawn boxes.
