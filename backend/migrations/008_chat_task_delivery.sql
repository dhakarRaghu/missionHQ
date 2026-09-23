-- Keep delegated work tied to the chat that requested it without putting
-- browser-derived text back into a privileged agent's model history.
ALTER TABLE hq.tasks
  ADD COLUMN origin_session_id uuid REFERENCES hq.sessions(id) ON DELETE SET NULL;

CREATE INDEX ix_tasks_origin_session ON hq.tasks (origin_session_id)
  WHERE origin_session_id IS NOT NULL;

CREATE TABLE hq.chat_deliveries (
  id bigserial PRIMARY KEY,
  session_id uuid NOT NULL REFERENCES hq.sessions(id) ON DELETE CASCADE,
  task_id uuid NOT NULL UNIQUE REFERENCES hq.tasks(id) ON DELETE CASCADE,
  run_id uuid REFERENCES hq.runs(id) ON DELETE SET NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  text text NOT NULL
);

CREATE INDEX ix_chat_deliveries_session
  ON hq.chat_deliveries (session_id, ts, id);
