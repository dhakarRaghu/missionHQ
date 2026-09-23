# Weekly plan

Use **only when the owner asks** what to work on. Write one page to
`projects/planner/<YYYY>-W<NN>.md`.

A plan is written when he asks for one, never on a schedule.

## What this plan is about

The owner's own growth: becoming a better engineer, building his skills,
shipping Mission HQ and his content. Never his day job. If the board
or the notes contain office tasks, leave them out and say you did.

## Which file

Always the ISO week containing the next Monday from today. A run late on
Sunday plans the week that starts the next day, not the one ending. Say at the
top which Monday the plan is for, so the file and the content cannot disagree.

## Gather first

- `read_board` for what is open.
- `read_activity` with `since_hours=168` for what actually finished.
- The last seven daily notes with `vault_read`; list `daily/` if you need to.
- `recall_facts` for his goals.

If a tool fails outright, say so in the plan and carry on with what you did
read. "Could not read the board this run" is worth more than a plan that
quietly assumes it was empty.

## Structure

Four areas, in this order of priority:

1. **Learning** — what he set out to learn, and whether he moved. Name the
   evidence: a note, a run, a shipped thing. Movement, not intention.
2. **Content and audience** — what to publish next and what to research for
   it, from `projects/content/ideas.md` and what his own numbers say reached
   people.
3. **Mission HQ and side projects** — the next feature worth building, not a
   list of bugs already fixed.
4. **Anything blocked on him**, with the one thing that unblocks it.

Five priorities at most. A plan he cannot finish is not a plan.

End with a `Sources:` line naming what you actually read, and mark any
unconfirmed cause as unconfirmed. A guess written as a fact becomes next
week's plan.
