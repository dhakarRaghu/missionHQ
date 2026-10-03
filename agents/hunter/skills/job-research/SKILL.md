# Job research

What a lead is worth depends on four answers: is the role real and open, is
it level one and paid at least 25 LPA, who could refer him, and what do they
share with him.

## The order of work

1. **Check the ledger.** `list_jobs` first. A company or role already there
   is not researched again.
2. **The board.** `detect_job_board` on the company's careers or posting
   url, then `job_board` with the provider and slug it names. A board is
   read, not searched: the listing it returns is the record, with its id.
   Titles hide roles, so search the variants together in `query`.
3. **Score and record.** `record_job` computes the fit from the role's
   fields and files gated titles closed. Always pass the experience band,
   the compensation or pay signal, and the LinkedIn url when there is one.
   Record weak fits too.
4. **Dig only for a fit of 6 or more.** The company brief (what it builds,
   stage, team size), the pay signal (stated, or an estimate with its basis,
   or "no public signal"), and the role brief. Four to six calls each.
5. **The person.** A real person on the team, found on a page you opened,
   and the concrete ground they share with him (a school, a stack, a public
   project, a talk or post). No shared ground is a finding: say so. A
   role-based persona ("the backend lead for payments infra") is fine when
   no real person is visible. Never invent a name.

## When a page will not answer

- A board that returns nothing: say so, and record the role from the
  listing you have if it is complete.
- A JavaScript page: `browser_read`, never on an applicant-tracking page a
  board already read.
- LinkedIn only: one `request_operator` naming the exact fact you need.

## Sources that work

Roles: `job_feed` with `yc` first. It reads the postings of Y Combinator
companies that are hiring in India or remote, from each company's YC page:
the experience floor, the salary (most state one), the age, and `people`,
the founders with LinkedIn and X. A yc row is the company's own posting:
record it from the row, with its url, `source` "yc" and its `external_id`.
Pass its experience as `experience_band` and its salary as `compensation`.
Put one founder in `referral`, with the shared ground if you find any.

Then `hn_hiring` (this month's Hacker News "Who is hiring?" thread) and the
remote boards `himalayas`, `remotive` and `remoteok`, newest first. Their
rows are leads: verify each on the company's own board before
`record_job`. Pass `since_days` to `job_board` to see only new roles.

Companies: `discover_companies` lists hiring YC companies, newest first,
25 at a time; pass `page` for the next 25 instead of reading the same ones
again.

Research: company careers pages and their boards, engineering blogs, founder
posts, funding announcements, Glassdoor-style salary pages for a pay signal
(as signal, not fact), and the company's own team page.
