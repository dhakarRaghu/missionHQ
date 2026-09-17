-- Locally authored courses, 2026-09-14.
--
-- The seven courses in learning/courses/ are specs written in this repo, not
-- phases on his study platform. They use the same course_phases rows, so the
-- teach pipeline, the read gate and the Courses page do not need a second
-- path — the rows just carry where the spec came from and what it says.

ALTER TABLE hq.course_phases
    ADD COLUMN IF NOT EXISTS source    text  NOT NULL DEFAULT 'platform'
        CHECK (source IN ('platform', 'local')),
    ADD COLUMN IF NOT EXISTS question  text  NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS sections  jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS lab       text  NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS test_out  text  NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS spec_path text  NOT NULL DEFAULT '';

-- Course-level facts the phase rows cannot carry: the order he works through
-- them, the description shown on the page, and where the material lives.
CREATE TABLE IF NOT EXISTS hq.courses (
    course       text PRIMARY KEY,           -- matches course_phases.course
    title        text NOT NULL DEFAULT '',
    description  text NOT NULL DEFAULT '',
    source       text NOT NULL DEFAULT 'platform' CHECK (source IN ('platform', 'local')),
    course_order int  NOT NULL DEFAULT 999,  -- local courses 1..7; platform ones after
    spec_path    text NOT NULL DEFAULT '',
    synced_at    timestamptz NOT NULL DEFAULT now()
);

-- He asked on 2026-09-14 to remove these from Mission HQ. They stay on his
-- platform; sync_courses no longer imports them (see hq/courses.py).
DELETE FROM hq.course_phases
 WHERE course IN ('haskell', 'next-js-16-app-router-server-vs-client-components', 'go-mastery');
