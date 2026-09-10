-- What the company actually is, and whether the role pays.
--
-- The ledger recorded a title, a location and a fit score, which answers
-- "does this match my lane" and nothing about "is this worth leaving a job
-- for". The owner is an employed SDE-1: every lead is a switch, so the
-- company matters as much as the role. A 7/10 title at a company that is
-- twelve people and pre-revenue is a different decision from the same title
-- at a funded team, and neither was visible on the board.
--
-- Filled by hunter AFTER a role passes the gates and scores well enough to be
-- worth the reading, not for every row: researching every listing is how a
-- sweep spends 285k tokens.

ALTER TABLE hq.jobs ADD COLUMN IF NOT EXISTS company_brief text NOT NULL DEFAULT '';
ALTER TABLE hq.jobs ADD COLUMN IF NOT EXISTS pay_signal text NOT NULL DEFAULT '';
ALTER TABLE hq.jobs ADD COLUMN IF NOT EXISTS role_brief text NOT NULL DEFAULT '';
-- 'researched' means hunter did the company dig; the owner can then trust the
-- three columns above rather than wondering whether they are simply empty.
ALTER TABLE hq.jobs ADD COLUMN IF NOT EXISTS researched_at timestamptz;

CREATE INDEX IF NOT EXISTS jobs_researched_idx ON hq.jobs (researched_at)
    WHERE researched_at IS NOT NULL;
