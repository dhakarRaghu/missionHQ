# Dashboard API. Publishing and verifying

Use this only when a dashboard URL is configured, through `STUDY_DASHBOARD_URL` or `_index.json` → `dashboardUrl`. Without one, skip publishing and say so.

`scripts/push_dashboard.py` implements everything here.

## Endpoints, as verified on the first dashboard

| Call | Body | Result |
|---|---|---|
| `POST /api/courses` | `{topic, title, totalPhases, currentPhase, outline, config}` | 201. First phase of a new course |
| `PATCH /api/courses` | `{topic, currentPhase, outline}` | 200. Every later update |
| `GET /api/courses` | none | the course list |
| `POST /api/study` | see below | 201. Returns 500 if the slug exists |
| `PATCH /api/study` | ONLY `{slug, progress, status}` | any other field returns 500 |
| `DELETE /api/study?slug=<slug>` | none | 200, `{"deleted":1}` |
| `GET /api/study?slug=<slug>` | none | the document |

A different dashboard may differ. Test each call once with a throwaway slug before trusting this table.

## Document body for `POST /api/study`

```json
{
  "title": "Inference Internals — Phase 6A: Sizing the Fleet and Sharing It",
  "slug": "inference-internals-phase-06a-capacity-tenants",
  "category": "inference-internals",
  "difficulty": "advanced",
  "estimatedMinutes": 150,
  "tags": ["llm", "capacity-planning", "queueing"],
  "summary": "Two or three plain sentences. Name the exercise count.",
  "content": "<the full .md text>",
  "sections": [{"title": "6.1 — Capacity planning", "anchor": "61-capacity-planning-how-many-replicas-from-your-own-numbers"}],
  "source": "study-skill",
  "filePath": "study-material/<topic>/<file>.md"
}
```

- The slug is the file name without `.md`.
- `sections` is a list of objects, never a list of strings. A list of strings produced an empty table of contents.
- Build `sections` from `## ` headings **outside code fences**. A decision-record example inside a fence once added four false entries.
- The anchor is the heading lowercased, with punctuation removed and spaces replaced by hyphens.

## Updating a document

1. `DELETE /api/study?slug=<slug>`
2. `POST /api/study` with the full body.
3. `GET /api/study?slug=<slug>`.
4. Compare the SHA-256 of the live `content` with the local file. Report MATCH or DIFF.

To change metadata only, GET the current record first and reuse its fields in the new POST.

## Known limits of the first dashboard

- It has no order field. Part B documents may appear before part A. Re-posting in order did not change this.
- Pace requests about 1.5 seconds apart.

## Final check

After every publish, verify every document of the course, not only the new ones:

```
inference-internals-phase-00-frame          14,285 chars  MATCH  8 sections
...
11/11 live and byte-identical
```

Report that line to the user.
