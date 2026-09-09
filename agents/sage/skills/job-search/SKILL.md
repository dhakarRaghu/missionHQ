# Job search

Use when the owner asks about roles, companies, or people to reach. Output
lives in `projects/jobs/`, and this is your work: you write it, because the
agents that read the web may only write to `quarantine/`.

## The four questions this answers

1. **Which roles** are worth his time.
2. **Which companies** are worth approaching.
3. **Which people** to reach at each one, and why that person.
4. **What to say** to them, ready to send.

## How to gather

For a broad request such as "find SDE-1 jobs", call `start_job_search` once.
The owner does not need to name a company or platform. It creates this durable
pipeline:

1. Operator uses the signed-in browser to discover current roles across
   LinkedIn, Google Jobs, Wellfound, YC Work at a Startup and company sites.
2. Mission HQ automatically passes those leads to Hunter.
3. Hunter verifies original postings, detects the ATS, scores against the
   injected candidate profile, deduplicates, records the role, and adds a
   referral person or target persona.

Never create separate Operator and Hunter tasks for the same broad search;
that loses the ordering between discovery and verification.

For a narrow follow-up about a known company, ask with `create_subtask`:

- **hunter** first, for the open web, which is most of it: a company's
  engineering blog, a public careers page, the job posting, a funding
  announcement, a person's GitHub, their own site or conference talk. Job
  search is hunter's main work, so give it the four questions directly.
- **operator for LinkedIn and X**, and for anything private to the owner: his
  own analytics, his own profile as he sees it, a page only his session can
  open. Ask one precise question per task; it reads pages, it does not walk
  lists.

Operator's browser does not work on every machine. When it answers that no
browser is available, do not retry and do not fill the gap from memory. Note
the question as still open and carry on with what hunter found.

Their findings land in `quarantine/` with sources. Read those, then write.
Never write a name, title or claim that is not in one of those notes.

## The files you keep

`projects/jobs/targets.md` — the companies. For each: what they build, why it
fits what he is learning, and the evidence with its source URL.

`projects/jobs/people.md` — the people. For each: name, role, company, why
this person rather than another, and the shared ground you actually found —
a post, a repo, a talk, a mutual interest. A referral ask with no shared
ground is a cold ask with extra steps.

`projects/jobs/outreach/<date>-<person>.md` — one draft message per person,
in his voice: short, specific, naming the shared ground, asking one thing.

## The rules that matter here

- **You draft; he sends.** No agent can message anyone. End with which draft
  to send first and why.
- **Never invent a person, a role or a mutual connection.** A wrong name in an
  outreach message costs him the contact. If the research did not find it,
  say the gap out loud.
- **No bulk collection.** Reading a profile the owner opens is his browsing;
  walking a hundred is not, and it risks his account. Ask operator for a
  handful of named targets, never a scrape.
- Keep it small. Five good targets he actually contacts beat fifty he does not.
