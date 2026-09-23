# Job shortlist: five roles from the ledger, each with the next action

Use weekly, and whenever the owner asks which roles to act on. Output is one
page, `projects/jobs/shortlist-<YYYY>-W<NN>.md` (ISO week).

## Read

1. `list_jobs` with status `seen`, then `shortlisted`, then `referral`. The
   ledger is the source: hunter verified every row and code computed
   its score. Closed rows are out; do not revive one.
2. Fewer than five open roles: say so and list what there is. Never fill the
   page from memory or from a search.

## Pick five

Highest fit first, then the ones a single action moves furthest. Skip a role
he has already applied to. Give each one next action:

- **Apply**: pay is known and at or above 25 LPA, the band fits, the link
  works. Name the link (the LinkedIn post when there is one).
- **Ask for a referral**: a strong fit with a person named in `referral`.
  Name the person and the shared ground as the row states them. A row that
  names only a persona gets "shortlist it on the board", which sends
  operator to find the person.
- **Verify pay**: `pay_lakh` is empty or the figure is an estimate. Say what
  would settle it: the posting, or a salary page for that level and city.

## Write

One line per role:

`Company, Role, score/10, pay, band. Next: <action>. Why: <one clause from why_fit>.`

Then one line: the single role to act on first, and why that one. Then a
"Not picked" line naming any strong role left out and the reason.

## Rules

- You shortlist; he acts. Never apply, message, connect or post, and never
  write as if he has.
- Never write a name, title, figure or relationship that is not on the row.
  An empty field means the action is to fill it, not to guess it.
- Five is the size. A page he acts on beats a page he reads.
- Do not change a job's status. Moving a role is his, on the Jobs board.
