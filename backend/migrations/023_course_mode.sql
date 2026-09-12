-- Tutor's second job: work through his own course material, one phase a day.
--
-- He built a study platform (raghu-monitoring.vercel.app) holding 68 phases
-- across 13 courses — Kafka, Kubernetes, Redis, NoSQL, Elasticsearch, Docker,
-- SQL, Haskell, AWS Lambda, inference internals. Each phase is a full module:
-- mental model, numbered subsections, hands-on labs, production anchors, a
-- checkpoint and a cheatsheet. `/api/study` serves the catalogue publicly.
--
-- The daily topic lesson stays. This is the other half: take the next phase,
-- read it properly, research deeper than it goes, and teach it.

-- Two lessons a day now, so the date alone can no longer identify one.
ALTER TABLE hq.lessons DROP CONSTRAINT IF EXISTS lessons_lesson_date_key;
ALTER TABLE hq.lessons ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'topic'
    CHECK (kind IN ('topic', 'course'));
ALTER TABLE hq.lessons ADD COLUMN IF NOT EXISTS course_slug text NOT NULL DEFAULT '';
-- The gate he asked for: "if I have read that last article then generate the
-- next, otherwise articles will pile up".
ALTER TABLE hq.lessons ADD COLUMN IF NOT EXISTS read_at timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS lessons_day_kind_idx ON hq.lessons (lesson_date, kind);

CREATE TABLE IF NOT EXISTS hq.course_phases (
    slug         text PRIMARY KEY,
    course       text NOT NULL,
    phase_order  int  NOT NULL DEFAULT 0,
    title        text NOT NULL,
    summary      text NOT NULL DEFAULT '',
    category     text NOT NULL DEFAULT '',
    difficulty   text NOT NULL DEFAULT '',
    minutes      int  NOT NULL DEFAULT 0,
    url          text NOT NULL,
    -- 'pending' until tutor has taught it; 'skipped' when he drops it.
    status       text NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'taught', 'skipped')),
    lesson_id    uuid REFERENCES hq.lessons(id) ON DELETE SET NULL,
    synced_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS course_phases_next_idx
    ON hq.course_phases (course, phase_order) WHERE status = 'pending';
