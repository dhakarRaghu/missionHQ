-- One row per model attempt, 2026-09-23.
--
-- hq.runs held one cost per run, priced at the model the manifest names.
-- That hid three things: a run answered by a fallback spare was billed at the
-- primary's price, a failed or abandoned run recorded $0 although it had
-- spent, and nothing showed which attempt of which model hung. A row is
-- written for every attempt, including the ones that failed, so a run's cost
-- is the sum of its rows and the daily cap sees spend while a run is still
-- going. `usage_source` is 'reported' when the gateway sent a usage chunk and
-- 'estimated' when it did not.

CREATE TABLE hq.model_calls (
  id bigserial PRIMARY KEY,
  run_id uuid REFERENCES hq.runs(id) ON DELETE SET NULL,
  task_id uuid,
  agent text,
  model text NOT NULL,          -- registry name (kimi_k3), or 'codex'
  model_id text NOT NULL,       -- what the provider was asked for (kimi-k3)
  started_at timestamptz NOT NULL DEFAULT now(),
  ms int NOT NULL DEFAULT 0,
  input_tokens int NOT NULL DEFAULT 0,
  output_tokens int NOT NULL DEFAULT 0,
  cache_read_tokens int NOT NULL DEFAULT 0,
  cost_usd numeric(12,6) NOT NULL DEFAULT 0,
  error_class text,             -- NULL when the attempt answered
  usage_source text NOT NULL DEFAULT 'reported'
);

CREATE INDEX model_calls_run ON hq.model_calls (run_id);
CREATE INDEX model_calls_started ON hq.model_calls (started_at);
