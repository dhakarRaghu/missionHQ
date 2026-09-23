-- "Got it" / "Lost me" per concept, 2026-09-23.
--
-- Every lesson page opens with its concepts (c1..cN) and now carries two
-- buttons under each. The page cannot store the answer (no network, no
-- storage in the sandboxed frame), so it tells the page around it; the
-- console writes it here. One row per tap, never updated: the latest row for
-- a (lesson, concept) is his current answer, and the history shows a concept
-- that lost him and later landed. The next phase's outline reads the
-- "lost me" answers from earlier phases of the same course.
--
-- 034 is taken by a parallel change.

CREATE TABLE hq.concept_signals (
  id bigserial PRIMARY KEY,
  lesson_id uuid NOT NULL REFERENCES hq.lessons(id) ON DELETE CASCADE,
  concept text NOT NULL CHECK (concept ~ '^c[0-9]{1,2}$'),
  verdict text NOT NULL CHECK (verdict IN ('got_it', 'lost_me')),
  at timestamptz NOT NULL DEFAULT now(),
  via text NOT NULL DEFAULT 'console'   -- console | phone
);

CREATE INDEX concept_signals_lesson ON hq.concept_signals (lesson_id, concept, at DESC);
CREATE INDEX concept_signals_at ON hq.concept_signals (at);
