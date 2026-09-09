# Daily note

Use at 22:30, or when the owner asks what happened today. Write to
`daily/<YYYY-MM-DD>.md`. Under 300 words.

## What this note is for, and what it was doing wrong

The owner said he would keep Mission HQ **if it teaches him something**, and
drop it if it does not. He is here to become a better engineer and to have
something worth writing about.

Earlier daily notes were build logs of Mission HQ itself: which run failed,
which gateway timed out, which agent was blocked. Two consecutive notes came
out 96% identical, and sixteen of them are orphans that nothing links to. They
told him his own machine was broken. They taught him nothing.

So the note leads with something he did not know. System status is a footnote,
not the body.

## The one thing (this is the note)

Open with **one thing worth knowing**, in three to five lines, in this shape:

- What it is, in plain words.
- Why it matters to him specifically: payments and backend engineering,
  building AI agents, or the developer career. Name which.
- The source: the vault path, and the URL inside that note.

Where to find it, in order:

1. `vault_list` with `since_days=1` — what actually landed today. A hunter
   quarantine note is the usual source.
2. If today produced nothing, `memory_search` over the last week for something
   filed but never used. An unread finding from Tuesday is still new to him.
3. If the vault has nothing either, say so in one line and skip the section.
   **Do not invent one, and do not pad it with something he already knows.**
   An honest "nothing new landed today" is a useful signal: it means the
   research side produced nothing, and he should see that.

Never restate a fact he already has in `memory/`. Check before you write.

Do not repeat the same subject two days running. Read yesterday's note first.

## Then, briefly

**Needs you** — only what is genuinely waiting on him: a blocked task, a
pending approval, a decision. Skip the section entirely when nothing is.

**Today** — at most three lines, and only work that produced something. Name
the artifact and its path.

Failures go in one line, and only when they changed what he gets: "scout's
scan did not run, so no new ideas today". Never list them. A run that failed
and retried successfully is not news. He has `hq.cli health` for the machine's
condition, and that is where the failure rate belongs.

## End with one action

One concrete thing he can do tomorrow, in a line. Not a question about the
system's own plumbing. Something that moves his engineering, his writing, or
his job search forward.

## Inbox

If `inbox/` has items, append each into the right note and remove it from
`inbox/` by moving the content, not by deleting it. Mention it in one line.
