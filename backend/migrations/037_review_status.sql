-- One set of lesson review statuses, 2026-09-23.
--
-- The staged writer checks its own sentences against the study note. A clean
-- page is 'passed'; a page with sentences it could not map is 'flagged', with
-- them listed in review_notes. Nothing revises a lesson after it is written,
-- so the old 'revise' only ever stopped the course. 'failed' is his own call.
UPDATE hq.lessons SET review_status = 'flagged' WHERE review_status = 'revise';
ALTER TABLE hq.lessons DROP CONSTRAINT IF EXISTS lessons_review_status_check;
ALTER TABLE hq.lessons
  ADD CONSTRAINT lessons_review_status_check
    CHECK (review_status IN ('pending', 'passed', 'flagged', 'failed', 'none'));
