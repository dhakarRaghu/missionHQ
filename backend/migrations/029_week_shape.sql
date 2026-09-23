-- The week, 2026-09-18.
--
-- Articles used to serve only the active course phase, so every article was
-- about the one subject that course taught. He said it: "how will I learn new
-- things ... what about extra". The week now has two streams. Three weekdays
-- serve a course phase (an incident, the paper behind a mechanism, the
-- missing evidence). Two are frontier: new ground next to his lanes, which
-- ends by saying whether it changes the path. Saturday and Sunday are for
-- building: a lab card for the phase he is on, and a week review.
--
-- `article_kind` says which stream a lesson came from. `kind` gains the two
-- weekend pieces, which are lessons he opens like any other.

ALTER TABLE hq.lessons
  ADD COLUMN IF NOT EXISTS article_kind text NOT NULL DEFAULT '';

ALTER TABLE hq.lessons DROP CONSTRAINT IF EXISTS lessons_kind_check;
ALTER TABLE hq.lessons
  ADD CONSTRAINT lessons_kind_check CHECK (kind IN ('topic', 'course', 'lab', 'review'));

-- One lab card per course phase, and one review per day.
CREATE UNIQUE INDEX IF NOT EXISTS lessons_lab_phase_idx
  ON hq.lessons (course_slug) WHERE kind = 'lab' AND course_slug <> '';
CREATE UNIQUE INDEX IF NOT EXISTS lessons_review_day_idx
  ON hq.lessons (lesson_date) WHERE kind = 'review';
