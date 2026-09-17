-- Courses are written with Claude and the /study skill, 2026-09-17.
--
-- The owner and Claude generate each phase and publish it to his study
-- platform. Mission HQ syncs it, adds to it (updates, corrections, incidents,
-- deeper material) and he reads it here. So:
--
-- * A phase can be read before, or without, anything Mission HQ adds. Reading
--   is recorded on the phase itself, not only on a lesson row.
-- * Additions to a published phase are not a rewrite and do not go through
--   the 130-point lesson review; their sources are checked when they are
--   written. 'none' says no review applies.

ALTER TABLE hq.course_phases
  ADD COLUMN IF NOT EXISTS read_at timestamptz;

ALTER TABLE hq.lessons DROP CONSTRAINT IF EXISTS lessons_review_status_check;
ALTER TABLE hq.lessons
  ADD CONSTRAINT lessons_review_status_check
    CHECK (review_status IN ('pending','passed','revise','failed','none'));
