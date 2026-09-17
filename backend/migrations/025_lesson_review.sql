-- An independent review for every course lesson, 2026-09-14.
--
-- The inference course's own review found commands that did not run,
-- benchmark numbers that did not reproduce and stale links. A lesson is now
-- checked by the reviewer agent before it counts as done: the lab is run in a
-- sandbox, the lesson is checked against its spec and study note, and the
-- verdict lands here. Topic lessons keep 'pending'; nothing reviews them yet.

ALTER TABLE hq.lessons
  ADD COLUMN IF NOT EXISTS review_status text NOT NULL DEFAULT 'pending'
    CHECK (review_status IN ('pending','passed','revise','failed')),
  ADD COLUMN IF NOT EXISTS review_score int,
  ADD COLUMN IF NOT EXISTS review_notes text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS review_round int NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS reviewed_at timestamptz;
