-- The idea radar, steps two to four: problems, ideas, and the project he builds.
--
-- Step one stored what people wrote (hq.radar_items). Here a model reads each
-- row and names the problem in it, with a quote. Code checks that the quote is
-- in the stored text, and a problem the quote does not stand behind is not
-- stored. Problems that say the same thing are one row, so a problem can be
-- counted by how many different sites reported it. Two steps make that so: a
-- statement joins the problem its embedding is nearest to when the two say
-- the same, and problems that are near are shown to a model as pairs, which
-- says whether one project would study both. `compared` holds the pairs it
-- said no to, so a pair is asked once.
--
-- An idea is proposed from a problem, every two weeks. He said what he will
-- not build: something a coding assistant finishes in a session. So each idea
-- carries why it needs him, and an idea that does not is stored as dropped
-- with the reason, never shown as a proposal.
--
-- One project is built at a time. What he found while building it goes back
-- in as problems of his own, and those need no second site.

CREATE TABLE hq.problems (
  id bigserial PRIMARY KEY,
  statement text NOT NULL,
  area text NOT NULL DEFAULT '',
  embedding vector(768),
  origin text NOT NULL DEFAULT 'radar' CHECK (origin IN ('radar', 'owner')),
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'used', 'dismissed')),
  compared jsonb NOT NULL DEFAULT '[]'::jsonb,   -- ids of near problems judged different
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX problems_open ON hq.problems (last_seen DESC) WHERE status = 'open';

CREATE TABLE hq.problem_evidence (
  id bigserial PRIMARY KEY,
  problem_id bigint NOT NULL REFERENCES hq.problems (id) ON DELETE CASCADE,
  item_id bigint NOT NULL UNIQUE REFERENCES hq.radar_items (id) ON DELETE CASCADE,
  statement text NOT NULL,          -- the problem as this one item states it
  quote text NOT NULL,              -- words found in the item's stored text
  kind text NOT NULL CHECK (kind IN
    ('pain', 'request', 'measurement', 'design', 'incident')),
  domain text NOT NULL,             -- copied from the item: the count is by domain
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX problem_evidence_problem ON hq.problem_evidence (problem_id);

CREATE TABLE hq.ideas (
  id bigserial PRIMARY KEY,
  problem_id bigint NOT NULL REFERENCES hq.problems (id) ON DELETE CASCADE,
  brief date NOT NULL,              -- the brief it was proposed in
  title text NOT NULL,
  question text NOT NULL,           -- what the project answers
  build text NOT NULL,
  measure text NOT NULL,
  baseline text NOT NULL DEFAULT '',
  workload text NOT NULL DEFAULT '',
  rig text NOT NULL DEFAULT '',     -- laptop | rented GPU, and for how long
  learn text NOT NULL DEFAULT '',
  hard_because text NOT NULL DEFAULT '',
  first_step text NOT NULL DEFAULT '',
  scores jsonb NOT NULL DEFAULT '{}'::jsonb,   -- the judge's numbers and reasons
  score numeric NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'proposed' CHECK (status IN
    ('proposed', 'chosen', 'declined', 'dropped')),
  reason text NOT NULL DEFAULT '',  -- why dropped (the gate) or declined (him)
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ideas_brief ON hq.ideas (brief DESC, score DESC);

CREATE TABLE hq.projects (
  id bigserial PRIMARY KEY,
  idea_id bigint NOT NULL REFERENCES hq.ideas (id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'building' CHECK (status IN
    ('building', 'built', 'shared', 'stopped')),
  started_at timestamptz NOT NULL DEFAULT now(),
  due_at timestamptz NOT NULL,
  finished_at timestamptz,
  result text NOT NULL DEFAULT '',     -- the number he measured
  surprise text NOT NULL DEFAULT '',   -- what he did not expect
  share_url text NOT NULL DEFAULT ''
);

-- One project at a time.
CREATE UNIQUE INDEX projects_one_building ON hq.projects ((true)) WHERE status = 'building';
