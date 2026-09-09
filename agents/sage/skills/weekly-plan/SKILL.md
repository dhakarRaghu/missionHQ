# Weekly plan

Use **only when the owner asks** what to work on. Write one page to
`projects/planner/<YYYY>-W<NN>.md`.

This was a Monday cron once. It was removed because it answered a question
nothing had asked: the board already shows what is in flight, and the Sunday
review already says what happened and what it means. A third weekly file, on
a schedule, produced a summary of Mission HQ's own runs and one more thing
for the owner not to read. It earns its place when he wants it, not weekly.

This was a separate agent once. It is a skill because it needs nothing an
agent needs: no permissions you lack, no memory of its own, and no schedule
that is not already yours. It reads what you can already read and writes where
you can already write.

## What this plan is about

The owner's own growth: becoming a better engineer, building his skills,
shipping Mission HQ and his content. **Not his employer's work.** If the board
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
   it, against the three pillars in memory.
3. **Mission HQ and side projects** — the next feature worth building, not a
   list of bugs already fixed.
4. **Anything blocked on him**, with the one thing that unblocks it.

Five priorities at most. A plan he cannot finish is not a plan.

End with a `Sources:` line naming what you actually read, and mark any
unconfirmed cause as unconfirmed. A guess written as a fact becomes next
week's plan.
