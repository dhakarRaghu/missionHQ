-- One row per eval run: an agent scored against one golden dataset.
-- details holds one entry per case (checks, judge score, reason).
CREATE TABLE hq.eval_runs (
  id bigserial PRIMARY KEY,
  ts timestamptz NOT NULL DEFAULT now(),
  agent text NOT NULL,
  dataset text NOT NULL,
  job_hash text NOT NULL DEFAULT '',
  cases int NOT NULL,
  passed int NOT NULL,
  score numeric(5,3) NOT NULL,
  details jsonb NOT NULL DEFAULT '[]'::jsonb,
  cost_usd numeric(12,6) NOT NULL DEFAULT 0
);
CREATE INDEX ix_eval_runs_agent_ts ON hq.eval_runs (agent, ts);
