-- Job search tracking: one row per role ever verified.
--
-- The reference project this borrows from keeps two CSVs, seen-jobs and
-- job-tracker, and its own notes say the split exists so discovery memory
-- survives even for roles not worth applying to. That split is right; two
-- files is not. One table with a status column does the same job, dedupes in
-- the database rather than by hand, and can be read by a dashboard.
--
-- `seen` is the discovery ledger: verified, recorded, not acted on.
-- Everything past `shortlisted` is the pipeline.

CREATE TABLE IF NOT EXISTS hq.jobs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company         text NOT NULL,
    role            text NOT NULL,
    url             text NOT NULL,
    -- Where it came from: a board name, 'search', 'operator', 'owner'.
    source          text NOT NULL DEFAULT '',
    location        text NOT NULL DEFAULT '',
    remote_policy   text NOT NULL DEFAULT '',
    experience_band text NOT NULL DEFAULT '',
    compensation    text NOT NULL DEFAULT '',
    stack           text NOT NULL DEFAULT '',
    -- 0-10, from the rubric in hunter's job.md. Not a vibe: a number the
    -- agent has to justify in why_fit.
    fit_score       integer NOT NULL DEFAULT 5
                    CHECK (fit_score BETWEEN 0 AND 10),
    fit_bucket      text NOT NULL DEFAULT 'decent'
                    CHECK (fit_bucket IN ('strong', 'decent', 'stretch')),
    status          text NOT NULL DEFAULT 'seen'
                    CHECK (status IN ('seen', 'shortlisted', 'applied',
                                      'interviewing', 'offer', 'rejected',
                                      'closed')),
    why_fit         text NOT NULL DEFAULT '',
    next_step       text NOT NULL DEFAULT '',
    notes           text NOT NULL DEFAULT '',
    -- Referral path, filled by operator from the owner's own network.
    referral        text NOT NULL DEFAULT '',
    first_seen      timestamptz NOT NULL DEFAULT now(),
    last_seen       timestamptz NOT NULL DEFAULT now(),
    seen_count      integer NOT NULL DEFAULT 1,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- The duplicate key. The reference project uses company + role + link and
-- warns that a changed link must update the row rather than add one, so the
-- link is deliberately not part of the key.
CREATE UNIQUE INDEX IF NOT EXISTS jobs_company_role_idx
    ON hq.jobs (lower(company), lower(role));

CREATE INDEX IF NOT EXISTS jobs_status_score_idx
    ON hq.jobs (status, fit_score DESC);
