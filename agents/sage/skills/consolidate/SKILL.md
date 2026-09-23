# Consolidate memory

Nightly. Keep `memory/user.md` and `memory/active_projects.md` short, current
and true. Every agent reads them on every run, so a stale line misleads all
of them. `memory/decisions.md` and `memory/rules.md` are his; never write them.

## Gather

1. `vault_read` both blocks.
2. `vault_list` with `since_days=1` and read what changed today.
3. `read_board` for which tasks are open and which are done.

## Judge each line

Keep a line only if an agent starting fresh tomorrow would act differently
for knowing it. Then:

- A line naming a task, a run or a pending state is true only while that
  thing is open. Drop it when the board says it is done, failed or archived.
- Drop history ("on 09-08, X happened"). Keep what is true now.
- Merge duplicates; keep the newer wording.
- Confidence follows the source: his own account data and his own words are
  first-party; an agent's reading is "(unconfirmed)".
- Nothing comes from `quarantine/` unless he acted on it, except reads of his
  own accounts.

## Write

Rewrite a block with `vault_write` only when something changed. A block
stays under its cap (4,000 characters); detail that no longer fits goes to
`memory/archive/`. Facts that should outlive the block go in with
`record_fact`, with the source path; `retire_fact` a fact that turned out
wrong.

Reply in three lines: what you changed, what you dropped, and anything you
were unsure about.
