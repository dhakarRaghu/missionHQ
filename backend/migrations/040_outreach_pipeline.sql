-- The job pipeline past "found": where a role came from, and the follow-up
-- clock on what he applied to.
--
-- On 2026-10-04 the ledger held 138 roles ever found (54 live, 84 archived)
-- and none had reached applied, interviewing or offer, because nothing past
-- "found" was tracked. He finds people and writes to them himself; the
-- pipeline finds roles and keeps the clock:
--
-- * jobs.channel: where a role was found, from a fixed list (outreach.CHANNELS).
--   `source` was free text ("Board", "HN", "lever/meesho", "Y", empty), so
--   no source's yield could be counted.
-- * jobs.applied_at, followup_due, touches and the status 'ghosted': applied
--   plus 7 silent days is a follow-up; a second 7 days with no reply is
--   ghosted. Two touches at most.

ALTER TABLE hq.jobs
    ADD COLUMN IF NOT EXISTS channel      text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS applied_at   timestamptz,
    ADD COLUMN IF NOT EXISTS followup_due date,
    ADD COLUMN IF NOT EXISTS touches      integer NOT NULL DEFAULT 0;

ALTER TABLE hq.jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
ALTER TABLE hq.jobs ADD CONSTRAINT jobs_status_check
    CHECK (status = ANY (ARRAY[
        'seen', 'shortlisted', 'referral', 'applied',
        'interviewing', 'offer', 'rejected', 'ghosted', 'closed'
    ]));

CREATE INDEX IF NOT EXISTS jobs_followup_due_idx ON hq.jobs (followup_due)
    WHERE followup_due IS NOT NULL;
