# Video spec, versions 1 and 2

A video is **data, not code**. The model writes a `VideoSpec` (JSON). Code checks it
against this contract. A fixed set of tested Remotion templates draws it. The model never
writes React, so it cannot break a render, and every text slot has a length limit, so text
cannot overflow its box.

Two files describe one video:

| File | Written by | Holds |
|---|---|---|
| `<id>.narration.json` | the pipeline (model text, code checks) | every spoken line, per beat |
| `<id>.spec.json` | the pipeline (model scenes, code checks) | the scenes, which point at narration lines by key |

`video/scripts/narrate.mjs` turns the narration into audio and a timing file
(`<id>.timing.json`: the frame where every line and every caption starts). The renderer
reads the spec and the timing file. A scene element appears when its `at` line starts.

## Narration (`<id>.narration.json`)

The same format the course videos already use (`course-videos/scripts/*.narration.json`):

```json
{
  "engine": "kokoro", "voice": "af_heart", "speed": 0.94,
  "fadeTailS": 0.3, "leadinS": 0.4, "holdS": 1.8, "gapS": 0.8,
  "beats": {
    "cold":  { "chapter": "The $0.81 in the meeting", "lines": [ {"key": "co0", "text": "...", "say": "..."} ] },
    "title": { "lines": [ ... ] },
    "c1":    { "chapter": "What does a 4-bit checkpoint make faster?", "lines": [ ... ] }
  }
}
```

- `text` is what the captions show. `say` (optional) is what the voice reads: numbers,
  units, symbols and acronyms spelled out ("764 ms" → "seven hundred sixty-four milliseconds").
- Beat ids, in order: `cold`, `title`, `c1`…`c20` (numbered without gaps), then optional `payoff`, then `recap`, `end`.
  A course video teaches every concept of a lesson, so 20 to 40 minutes and ten or more concepts are normal.
- Line keys inside a concept beat start with the step letter, then a number:
  `k` claim, `s` situation, `p` picture, `q` question, `t` think it through, `m` mechanism
  (one line per "Step N."), `n` the number, `r` key points (remember, trap, try), `h` bridge.
  Inside a concept beat the lines come in that order (k s p q t m n r h). Each step needs its letter:
  at least one `k`, `s`, `p`, `q`, `m`, `n`; at least three `t` (first thought, what it misses, the real
  question); exactly three `r` (remember, the trap, try this). `h` lines are optional.
  Other beats: `co` cold open, `t` title, `y` payoff, `r` recap, `x` end. (The ep12 example keeps its
  original `a` keys in the payoff; code does not check the prefixes outside concept beats.)
- Each beat may set `cueLeadS` (default 0.25, at most 0.5): how long before the voice a line's visuals appear.
- **Version 2** (the pipeline writes only this since 2026-10-14) changes only the concept beat; see
  "Version 2: the story order" below.

## Spec (`<id>.spec.json`)

```json
{
  "version": 1,
  "id": "inference-internals-yt-12",  // max 80, lowercase letters, digits and "-"
  "mode": "course",               // "course" | "article" ("youtube" stays valid but is not used)
  "series": "Inference Internals", // max 40, shown in capitals on the title card
  "number": 12,                   // lesson number, or null
  "title": "Is Self-Hosting Your LLM Cheaper Than the API?",   // max 70
  "label": "Inference Internals #12",   // corner label on every frame, max 40: the course name, or "Learn" for an article
  "next": { "number": 13, "title": null },   // optional; end card "Next lesson"; title max 60, null = "coming soon"
  "site": "Mission HQ · Learn",         // optional; end card "The written lesson: <site>", max 40
  // The end card is drawn from these fields and the beats: the title, "In this
  // video" with every concept heading, the next lesson (when `next` is set),
  // and the written lesson. It needs no fields of its own.
  "beats": [ <Beat>, ... ]        // same ids and order as the narration
}
```

### Beat

```json
{ "id": "c1", "kind": "concept", "heading": "What does a 4-bit checkpoint make faster?",
  "count": "1 of 3", "mark": "a quiet server", "steps": [ <Step>, ... ] }
```

- `kind`: `cold` | `title` | `concept` | `payoff` | `recap` | `end`.
- `heading` (max 60): the handwritten question at the top. Required for `concept` and
  `payoff`; it is also the chapter title (`scripts/captions.mjs`). Optional on `cold` (the first
  chapter's title, not drawn) and `recap` (drawn; default "Recap").
- `count` (max 12): the claim card count, "1 of 3". Concept beats only.
- `mark` (max 40, optional): the words the yellow highlighter marks. On a concept beat it must be part of
  the claim (the `k` lines); on the title beat, part of `title`.
- `cold`, `payoff`: one or more `panel` steps. `title`, `recap`, `end`: no steps; the
  template builds them from the narration and the top-level fields.
- `concept`: the steps below, in this order: `claim`, `situation`, `picture`, `think`, `mechanism`,
  `number`, `keypoints`, then `bridge` exactly when the narration has `h` lines (eight steps with a
  bridge, seven without). `claim`, `think` and `keypoints` are filled from the narration by the
  template, so they carry no visual slots. `situation`, `picture`, `mechanism`, `number` and
  `bridge` carry the visuals.

### Step

Every step has `"step"` (its name) and the visual slots of its template. Every visual element
has an `"at"` field: the key of the narration line on which it appears. It must exist in the
same beat, and the `at` keys inside one step must not go backwards. In a concept beat each
step's `at` keys use that step's letter (`situation` → `s`, `picture` → `p`, `mechanism` → `m`,
`number` → `n`, `bridge` → `h`): a key from another step's lines would appear after its step
has left the screen.

A visual step carries `panel` (one Panel) or `panels` (2–3 Panels). With `panels`, the screen
shows them one after another: each panel replaces the one before when its first element's line
starts. The voice sets the pace, so a step needs no more than one screen at a time.

| step | template slots | limits |
|---|---|---|
| `claim` | none (uses `k` lines and `count`) | |
| `situation` | `panel` or `panels` | see Panel |
| `picture` | `panel` or `panels` | see Panel |
| `think` | `first` (max 70), `misses` (max 70), `real` (max 90): short paraphrases of the three `t` lines, shown handwritten; the question comes from the `q` lines | |
| `mechanism` | `items`: one per "Step N." line, `{ "text": max 48, "at": "m1" }`; optional `side`: a Panel shown to the right | 2–6 items |
| `number` | `panel` or `panels`, plus optional `source`: `{ "text": max 160 }`, a small grey note under each panel | |
| `keypoints` | none (uses the three `r` lines; "Remember:", "The trap:", "Try this:" are stripped) | |
| `bridge` | `panel` or `panels`, plus optional `label` (max 40), a small blue line top left; shown from the first `h` line, the step rail hides | |
| `panel` | for `cold` and `payoff` beats: `panel` or `panels` | |

`mechanism.items` has exactly one item per step: each `at` is the `m` line that starts "Step N.".
A step that continues on more `m` lines (`m1b`) keeps its item lit; those lines get no item. `side` (optional)
is drawn in a narrower box (950 px instead of 1680 px); every panel kind fits there.

### Panel (one visual)

A panel is exactly one of these. The `kind` decides the template.

| kind | fields | limits |
|---|---|---|
| `chips` | `items: [{ "text", "tone", "at" }]` | 1–6 items, text max 64 |
| `flow` | `nodes: [{ "label", "sub", "tone", "at" }]`, drawn left to right with arrows; 4–5 nodes in a wide box run in two rows joined by a turn arrow; a flow in a side panel runs top to bottom | 2–5 nodes, label max 22, sub max 36 |
| `stats` | `items: [{ "value", "label", "tone", "at" }]`, big handwritten numbers | 1–3 items, value max 14, label max 40 |
| `bars` | `items: [{ "label", "value", "display", "tone", "at" }]`, horizontal bars scaled to the largest `value` | 2–6 items, label max 28, display max 16 |
| `table` | `columns: [max 18 each]`, `rows: [{ "cells": [...], "tone", "at" }]` | 2–4 columns, 1–6 rows, cell max 22 |
| `equation` | `lines: [{ "text", "tone", "at" }]`, handwritten working, one line per step | 1–5 lines, text max 48 |
| `compare` | `left: { "title", "items": [text] }`, `right: {...}`, `at_left`, `at_right` | title max 28, 1–4 items max 40 |
| `prompt` | `title` (max 40), `lines: [{ "text", "tone", "at" }]`, a monospace box such as a prompt, log or JSON | 1–8 lines, text max 56 |

`tone` is one of `ink` (default), `ok` (green), `bad` (red), `warn` (amber), `info` (blue),
`accent` (orange). Use tone for meaning only: `bad` for the failure, `ok` for the fix.

Optional on every panel: `"caption"` (max 90), a one-line handwritten note above it, and
`"note"` (max 120), small grey text under it, for "illustration, not measured". Both appear
with the panel's first element, and the panel's border draws in with its first element too,
so an empty box never waits on screen.

Layout: every step centres its content in the height between the step rail (about y = 150) and
the caption bar (about y = 950). Every template is sized from its box, its item count and its
longest text, so the longest allowed text fits; anything still too big (a long narration line in a
claim, think or recap card) is scaled down to fit. A small panel is scaled up until its largest text
reaches an on-screen maximum (body text 54 px, compare items 50 px), so short panels fill more of
the screen. At 1080p body text in a panel is at least 30 px, secondary text (flow sub, compare items,
prompt lines) at least 24 px and notes and sources at least 20 px, except where a panel at the text
limits must shrink to fit (a full 4x6 table, or a mechanism side panel at every limit). A number and
its unit ("30 s", "2.72 %") never break across lines. Ten recap lines of 200 characters still fit,
but at a small size; keep recap lines under about 120 characters.

## Version 2: the story order

The version 1 concept opened with its claim and walked a fixed rail of steps with fixed phrases,
then said the claim twice more (Remember, the recap). Watched end to end, the answer came before the
question and the same pattern repeated in every concept (2026-10-14). Version 2 asks first and
answers once. Set `"version": 2`; everything outside concept beats is unchanged.

Narration keys inside a concept beat, in this order (s q t p m n k h):

| Key | Step | Lines |
|---|---|---|
| `s` | situation: where the running case reaches this concept, with the number that makes it matter | 1 or more |
| `q` | the question, in the viewer's words; the last `q` line ends with "?" | 1 or more |
| `t` | thinking it through: a first answer, why it is reasonable, what it misses | 2 to 4 |
| `p` | picture: the parts and terms the mechanism needs | optional |
| `m` | mechanism: how it works, each step with its reason; no "Step N." phrase | 1 or more |
| `n` | the number that proves it, with its conditions | optional |
| `k` | the takeaway: the concept's claim, said once, now earned | 1 or 2 |
| `h` | bridge: what happened next, leading to the next concept's question | optional (not on the last concept) |

Steps of a concept beat, in this order: `situation`, `think`, `picture` (exactly when there are `p`
lines), `mechanism`, `number` (exactly when there are `n` lines), `takeaway`, then `bridge` (exactly when
there are `h` lines). There is no step rail.

| step | slots |
|---|---|
| `situation`, `picture`, `number`, `bridge` | as in version 1 |
| `think` | optional `first` (max 70) and `misses` (max 70), together or not at all; optional `first_at` and `misses_at`, `t` keys, `misses_at` later (default: the first and the last `t` line). The question comes from the `q` lines; the first answer is struck through at `misses_at`. No `real`. |
| `mechanism` | `items` (2–6, text max 48), each `at` an `m` line, each on its own later line; at most one item per `m` line; optional `side` |
| `takeaway` | none: the claim card, drawn from the `k` lines with `count` ("2 of 3") and `mark` (part of the `k` lines) |

`next` may carry `label` (max 24), the kicker of the end card's next panel: "Next part" for a series.

## What code checks before anything is rendered

`node scripts/check-spec.mjs <narration.json> <spec.json>` runs checks 1–5. It prints every
problem as `<file>:<JSON path>: <message>` and exits 1 when there is any. JSON Schemas of the same
contract, for Python: `spec/video-spec.schema.json`, `spec/narration.schema.json` (draft-07,
generated by `scripts/build-schema.mjs`).

1. Both files parse and match this contract (unknown fields are errors).
2. Beat ids and order match between narration and spec, and follow cold, title, c1…, payoff, recap, end.
3. Every `at` key exists in its beat, `at` keys inside a step never go backwards, and each panel
   starts no earlier than the panel before it.
4. Every text field is within its limit.
5. Concept beats have their steps in order (with `bridge` exactly when there are `h` lines), the
   narration has every step's letter in step order, `at` keys use their step's letter, and
   `mechanism` has one item per "Step N." line. `mark` is part of the claim or the title.
6. Narration rules (see `agents/tutor/video/rules.md`): sentence length, banned words,
   no part names, terms defined at first use, numbers in `text` spelled in `say`.

## Rendering

`video/` is a Remotion project (`video/README.md` has every command). The composition
`SpecVideo` (1920x1080, 30 fps) takes `{ spec, timing, audioDir }` as input props and sets its own
duration from the timing file. Every beat is a Sequence that starts at the frame the timing file
gives it, with its own audio file, so audio cannot drift across a long video.

```bash
node scripts/check-spec.mjs out/<id>/<id>.narration.json out/<id>/<id>.spec.json
node scripts/narrate.mjs out/<id>/<id>.narration.json out/<id>/audio out/<id>/<id>.timing.json
node scripts/render.mjs out/<id> <id> --stills=auto        # stills/<beat>__<step>.jpg, stills/index.json, sheet.jpg
node scripts/render.mjs out/<id> <id> --scale=1            # out/<id>/<id>.mp4 (--scale=2: <id>-4K.mp4)
node scripts/verify.mjs out/<id>/<id>.mp4 out/<id>/<id>.timing.json   # JSON report, exit 1 on a failure
node scripts/captions.mjs out/<id>/<id>.timing.json out/<id>/<id>.spec.json out/<id>   # captions.srt, chapters.json
```

### Timing file (`<id>.timing.json`, written by `narrate.mjs`)

```json
{ "version": 1, "fps": 30, "totalFrames": 23453, "order": ["cold", "title", "..."],
  "beats": { "c1": { "id": "c1", "chapter": "...", "start": 2030, "end": 7891, "audioFrames": 5798,
    "cues":  [ { "text": "caption words", "start": 9, "end": 120 } ],
    "steps": [ { "key": "k0", "at": 2, "start": 9, "end": 160, "text": "..." } ] } } }
```

`start`/`end` of a beat are absolute frames; cues and steps are frames inside the beat. A line's
`start` is where the voice starts it; `at` is `start` minus the beat's `cueLeadS`.
