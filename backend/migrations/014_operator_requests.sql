-- A web-reading agent asking for a look behind a login, without dispatching it.
--
-- Hunter cannot hold create_subtask: the loader refuses any manifest that
-- combines web-read tools with it, because one poisoned page would otherwise
-- become work for another agent. But hunter is the agent that discovers a
-- fact is missing — "this role is only on LinkedIn" — and until now it could
-- only write that in prose at the end of a quarantine note, where nothing
-- read it.
--
-- So the request becomes a row. Hunter writes it; it dispatches nothing. Sage
-- reads the queue, judges each one, and dispatches operator itself with its
-- own create_subtask. The boundary holds: the agent that read the web still
-- cannot start work, and a privileged agent decides.
--
-- Deliberately bounded columns, not a free-text instruction: a request is
-- data for sage to read, not a prompt to run. Everything here is web-derived
-- and untrusted until sage vouches for it.

CREATE TABLE IF NOT EXISTS hq.operator_requests (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    requested_by  text NOT NULL,
    run_id        uuid REFERENCES hq.runs(id),
    task_id       uuid REFERENCES hq.tasks(id),
    -- What it is about. Company and role make the request checkable against
    -- the ledger; question is the ONE fact that is missing.
    company       text NOT NULL DEFAULT '',
    role          text NOT NULL DEFAULT '',
    question      text NOT NULL,
    -- The page hunter believes holds the answer, when it saw a link to one.
    url_hint      text NOT NULL DEFAULT '',
    why           text NOT NULL DEFAULT '',
    status        text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'dispatched', 'declined', 'expired')),
    -- Set when sage routes it: the operator task that answers it.
    dispatched_task_id uuid REFERENCES hq.tasks(id),
    decided_by    text NOT NULL DEFAULT '',
    decided_note  text NOT NULL DEFAULT '',
    created_at    timestamptz NOT NULL DEFAULT now(),
    decided_at    timestamptz
);

-- One pending request per company+role+question, so a nightly sweep that
-- keeps hitting the same wall does not queue the same look seven times.
CREATE UNIQUE INDEX IF NOT EXISTS operator_requests_pending_idx
    ON hq.operator_requests (lower(company), lower(role), lower(question))
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS operator_requests_status_idx
    ON hq.operator_requests (status, created_at);
