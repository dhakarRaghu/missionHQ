# Mission HQ. How /study courses reach the reader

Read this before starting or continuing any course from the Mission HQ repo.
It wins over the defaults in `SKILL.md` where the two differ.

## The flow

```
┌────────────────────┐  publish   ┌──────────────────┐  sync    ┌─────────────────────┐
│ /study, with Claude├───────────►│ study platform   ├─────────►│ Mission HQ          │
│ one phase per turn │            │ /api/study       │          │ adds updates,       │
│ reviewed + audited │            │ /api/courses     │          │ incidents, deeper   │
└────────────────────┘            └──────────────────┘          │ material. He reads  │
                                                                 │ it on /courses      │
                                                                 └─────────────────────┘
```

1. The owner and Claude write each phase with this skill. The phase is the
   course. It must be complete on its own.
2. The phase is published to the study platform with `push_dashboard.py`.
3. `uv run python -m hq.cli sync-courses` (in `backend/`) pulls it in. The
   planned row for that phase disappears and the published phase replaces it.
4. Mission HQ's hunter researches past the phase. Tutor adds, under the
   section each belongs to: updates, corrections, production incidents,
   deeper material, practice. It never rewrites the published text.
5. He reads the phase on the Courses page, with the additions in place, and
   marks it read. The next phase is not started while one is unread.

Mission HQ never writes a planned phase itself. A phase that is not
published stays "planned" on the Courses page.

## Settings for this repo

| Setting | Value |
|---|---|
| Base directory | `learning/study-material/` in the Mission HQ repo |
| Dashboard URL | `https://raghu-monitoring.vercel.app`, stored in `_index.json` → `dashboardUrl` |
| Exercise language | the spec's `language:` line |
| Python tooling | `uv` |

## The path courses start from a spec

The eight path courses are specified in `learning/courses/NN-<name>/course.md`.
Read `learning/courses/README.md` for the format. For these courses the spec
is the approved outline. Do not design a new one.

If the course directory holds a `sources.md`, read it before researching
anything. It pins the fetch-verified sources, dated incidents and hard numbers
per phase, so generation does not repeat research that is already done.
Re-check version numbers before publishing. Do not re-check the dated incidents.
If it holds a `notes.md`, read that too: it lists facts that are commonly
published wrongly, and topics deliberately left out of the course.

`/study <slug>`, for example `/study elite-performance`:

1. Read the spec. `slug:` is the topic. Use it exactly.
2. Build `course.json` from it:
   - one outline entry per `## Phase N`, with the phase title and the spec's
     `question:` as the subtitle
   - `buildsOn`: every course named on an `assumes:` line, with the sections,
     such as `inference-internals 3A`
3. Show the outline and wait for approval, as `SKILL.md` says.

For each phase, the spec block is the contract:

| Spec field | What the phase must do with it |
|---|---|
| `question:` | the phase answers it, and the header says so |
| `### Sections` | every `N.x` appears, in order, as `## N.x — …` |
| `assumes:` | used without re-teaching. Link to the named section |
| `introduces:` | defined at first use |
| `leaves-for-later:` | never taught here. One line pointing forward is allowed |
| `### Why you're here` | the opening situation |
| `### Lab` / `### Demonstrate` | the hands-on lab and its measured result |
| `### Test out` | three checkpoint questions: explain, predict, demonstrate |

The spec's `minutes:` is reading time. The phase's own size targets still
come from `quality-bar.md`.

## File names. Code depends on them

- Phase file and slug: `<slug>-phase-NN-<name>.md`, where `NN` is the spec's
  phase number with two digits. A split phase uses `NNa` and `NNb`.
- `category` on the dashboard: the course slug.

Mission HQ reads the course from the part before `-phase-` and the phase
number from `NN`. A different pattern makes the phase appear as a new course
and leaves the planned row in place.

## Overlap. Never teach it twice

- The owner has already read **inference-internals** (11 phases: 0, 1, 2, 3A,
  3B, 4A, 4B, 5A, 5B, 6A, 6B). Its text is at
  `https://raghu-monitoring.vercel.app/api/study?slug=<slug>`. Before a
  phase, read the sections its `assumes:` line names, and link to them.
- Mission HQ writes weekday articles that orbit the active phase. They are
  separate reading. Do not copy their incidents into the phase.

## Anchors

The specs name Mission HQ as the laboratory. At course start, ask once
whether Mission HQ is the confirmed anchor for this course. If yes:

- read every file before citing it, and give `file:line`
- the lab may read and measure Mission HQ, and runs against a local copy.
  It never changes the owner's running system
- never use the repo's `.env` credentials for live calls unless he says so

If no, use learning-only mode from `SKILL.md`.

## Rules that are specific to him

- English is his second language. `writing-style.md` applies with no
  exceptions.
- Never name his current or former employer, anywhere.
- He is not a beginner. Shipping a system proves exposure, not mastery, so
  every phase teaches the failure modes.

## After publishing

1. `push_dashboard.py --course learning/study-material/<slug> --files …`
   and report the "N of N live and identical" line.
2. `cd backend && uv run python -m hq.cli sync-courses`.
3. Tell him: the phase is on the Courses page, and Mission HQ adds its
   updates on the next evening run, or at once with "Add updates now".
