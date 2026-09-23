-- One row per course lesson, keyed by its phase, 2026-09-14.
--
-- Lessons were unique on (lesson_date, kind). That held while there was one
-- lesson of each kind a day, and broke both ways once course phases gained a
-- review loop: a revision landing the next day inserted a SECOND row for the
-- same phase (the old one stayed unread and held the read gate shut), and two
-- course lessons recorded on one day overwrote each other. A topic article is
-- still one a day; a course lesson is one per phase.

DROP INDEX IF EXISTS hq.lessons_day_kind_idx;

CREATE UNIQUE INDEX IF NOT EXISTS lessons_topic_day_idx
    ON hq.lessons (lesson_date) WHERE kind = 'topic';

CREATE UNIQUE INDEX IF NOT EXISTS lessons_course_phase_idx
    ON hq.lessons (course_slug) WHERE kind = 'course' AND course_slug <> '';
