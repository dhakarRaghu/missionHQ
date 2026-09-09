-- People to ask for a referral: one row per person, not one text blob per job.
--
-- The `jobs.referral` column held whatever the agent wrote, e.g. "Head of
-- Engineering at Bolna.ai; Aditya Kumar and 27 other mutual connections".
-- Everything the owner needs is in that sentence and none of it is usable: he
-- cannot see who is 1st-degree at a glance, cannot open the profile, and
-- cannot mark one as asked. A person is a record, so it gets a table.
--
-- jobs.referral stays as the agent's own summary line. This is the structured
-- form of the same finding, and the two are written from one operator run.

CREATE TABLE IF NOT EXISTS hq.referrals (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id        uuid NOT NULL REFERENCES hq.jobs(id) ON DELETE CASCADE,
    company       text NOT NULL DEFAULT '',
    name          text NOT NULL,
    -- Their title as the page showed it. The whole point of reading the
    -- company people page is that the headline is already there.
    headline      text NOT NULL DEFAULT '',
    profile_url   text NOT NULL DEFAULT '',
    -- How the owner is connected: '1st' is someone who already knows him and
    -- is worth every other lead put together. 'persona' means no verifiable
    -- person was found and this describes who to look for instead.
    degree        text NOT NULL DEFAULT 'unknown'
                  CHECK (degree IN ('1st', '2nd', '3rd', 'none', 'persona', 'unknown')),
    -- What he can open the conversation with. A referral ask with no shared
    -- ground is a cold ask with extra steps.
    shared_ground text NOT NULL DEFAULT '',
    why_them      text NOT NULL DEFAULT '',
    mutuals       text NOT NULL DEFAULT '',
    source        text NOT NULL DEFAULT '',
    status        text NOT NULL DEFAULT 'found'
                  CHECK (status IN ('found', 'asked', 'replied', 'dismissed')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

-- Re-running the hunt for a role refreshes the same person rather than
-- stacking duplicates.
CREATE UNIQUE INDEX IF NOT EXISTS referrals_job_person_idx
    ON hq.referrals (job_id, lower(name));

CREATE INDEX IF NOT EXISTS referrals_job_idx ON hq.referrals (job_id);
