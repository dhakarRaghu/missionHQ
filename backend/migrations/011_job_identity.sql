-- Stable ATS identity prevents two requisitions with the same title from
-- overwriting one another. The fallback includes location for sources that do
-- not expose a provider job id.

ALTER TABLE hq.jobs ADD COLUMN IF NOT EXISTS provider text NOT NULL DEFAULT '';
ALTER TABLE hq.jobs ADD COLUMN IF NOT EXISTS external_id text NOT NULL DEFAULT '';
ALTER TABLE hq.jobs ADD COLUMN IF NOT EXISTS dedupe_key text NOT NULL DEFAULT '';

UPDATE hq.jobs
SET dedupe_key = 'fallback:' || lower(btrim(company)) || '|' ||
                 lower(btrim(role)) || '|' || lower(btrim(location))
WHERE dedupe_key = '';

DROP INDEX IF EXISTS hq.jobs_company_role_idx;

CREATE UNIQUE INDEX IF NOT EXISTS jobs_dedupe_key_idx
    ON hq.jobs (dedupe_key);

CREATE INDEX IF NOT EXISTS jobs_provider_external_idx
    ON hq.jobs (provider, external_id)
    WHERE provider <> '' AND external_id <> '';
