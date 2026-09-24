# Daily note

Write today's note to `daily/<YYYY-MM-DD>.md` with `vault_write`. Under 300
words. It goes to his phone at the top of the evening digest, twenty minutes
after you write it, as plain text: headings and bold are stripped.

## The one thing he did not know

Lead with one thing he did not know this morning, taken from what actually
landed today, with its source:

1. `vault_list` with `since_days=1`, and `list_lessons` for today's lesson.
2. Pick the single most useful fact, finding or result: a lesson's claim, a
   lead worth his time, a number from his own account. Say it in two or
   three sentences and name the file it came from.
3. If nothing new landed, say "Nothing new landed today" and move on. Never
   restate what memory already holds. The Continuity block in your brief
   names what last night's note led with: lead with something else.

## Then, short

- **Needs you:** only decisions only he can make, each one line. The
  Continuity block gives last nights' lines with their status now: a line
  marked `[closed]` is not repeated, a decision past seven days gets a
  proposed default, and the counters there are the only numbers you state.
  A memory proposal in `memory/proposals/` that he has not acted on counts:
  name the file once.
- **Today:** what was written or found, one line each, with the path.
- **What failed:** one line per failed or blocked run from `read_activity`
  with `since_hours=24`, and what it needs. Machine health is a footnote.

## What he has done

Anything about what he read, applied to, moved or posted comes from the
"What he has done (from the ledger)" block in your brief. No line there,
no claim.

## End with one action

One concrete thing to do tomorrow, and why that one first. Not a question.

## Inbox

Anything in `inbox/` is his: file it where it belongs with `vault_write`
and say where it went. Never delete it.
