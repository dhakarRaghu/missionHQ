# Job shortlist: five roles from the ledger, each with the next action

Weekly, and whenever he asks which roles to act on. The page is
`projects/jobs/shortlist-<YYYY>-W<NN>.md` (ISO week), written by
`file_shortlist`, never by `vault_write`.

## Read

1. `list_jobs` with status `seen`, then `shortlisted`, then `referral`. The
   ledger is the source: hunter verified every row and code computed its
   score. Each row carries the `job_id` you file.
2. The Continuity block in your brief lists the candidate rows with status,
   score, pay (stated, estimated or none) and last live check. Read pay from
   there, never from memory.
3. Closed rows are out; `file_shortlist` refuses one. Fewer than five open
   roles: file what there is and say so. Never fill the page from memory or
   from a search.

## Pick five

Highest fit first, then the ones a single action moves furthest. Skip a role
he has already applied to. Give each one `action`:

- `apply`: the posting itself states pay at or above the target. Code
  refuses `apply` for estimated or missing pay.
- `referral`: a strong fit with a person named in `referral`. Name the
  person and the shared ground as the row states them.
- `shortlist`: the row names only a persona; operator then finds the person.
- `verify_pay`: pay empty or an estimate. Say what would settle it: the
  posting, or a salary page for that level and city.

## Write

Call `file_shortlist` once with the picks (`job_id`, `action`, `next_step`)
and a title. Code writes company, role, score, pay, status and last live
check from the row and stamps the date; your `next_step` is one sentence he
can act on. A refused pick: change it and call again.

Reply in three lines: the role to act on first and why, any strong role
left out and the reason, and the page's path.

## Rules

- You shortlist; he acts. Never write as if he has applied.
- Never write a name, title, figure or relationship that is not on the row.
- Five is the size. Do not change a job's status; moving a role is his.
