CREATE SCHEMA IF NOT EXISTS hq;

    CREATE TABLE hq.tasks (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      title text NOT NULL,
      brief text NOT NULL DEFAULT '',
      agent text NOT NULL,
      status text NOT NULL DEFAULT 'backlog'
        CHECK (status IN ('backlog','running','blocked','needs_approval','done','failed')),
      priority int NOT NULL DEFAULT 0,
      parent_id uuid REFERENCES hq.tasks(id),
      source text NOT NULL,
      payload jsonb NOT NULL DEFAULT '{}'::jsonb,
      dedup_key text UNIQUE,
      not_before timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE hq.task_events (
      id bigserial PRIMARY KEY,
      task_id uuid NOT NULL REFERENCES hq.tasks(id),
      seq int NOT NULL,
      ts timestamptz NOT NULL DEFAULT now(),
      actor text NOT NULL,
      event_type text NOT NULL,
      data jsonb NOT NULL DEFAULT '{}'::jsonb,
      UNIQUE (task_id, seq)
    );

    CREATE TABLE hq.tickets (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      task_id uuid REFERENCES hq.tasks(id),
      run_id uuid,
      wf_id text NOT NULL,
      tool_name text NOT NULL,
      tool_args jsonb NOT NULL DEFAULT '{}'::jsonb,
      tool_call_id text NOT NULL DEFAULT '',
      action_class text NOT NULL,
      status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','denied','expired')),
      created_at timestamptz NOT NULL DEFAULT now(),
      resolved_at timestamptz,
      resolved_via text
    );

    CREATE TABLE hq.runs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      task_id uuid REFERENCES hq.tasks(id),
      wf_id text,
      agent text NOT NULL,
      model text NOT NULL DEFAULT '',
      job_hash text NOT NULL DEFAULT '',
      started_at timestamptz NOT NULL DEFAULT now(),
      ended_at timestamptz,
      outcome text,
      input_tokens int NOT NULL DEFAULT 0,
      output_tokens int NOT NULL DEFAULT 0,
      cost_usd numeric(12,6) NOT NULL DEFAULT 0,
      stall_count int NOT NULL DEFAULT 0,
      error text
    );

    CREATE TABLE hq.events (
      id bigserial PRIMARY KEY,
      ts timestamptz NOT NULL DEFAULT now(),
      run_id uuid,
      task_id uuid,
      agent text,
      kind text NOT NULL,
      payload jsonb NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE INDEX ix_events_kind_ts ON hq.events (kind, ts);
    CREATE INDEX ix_events_run ON hq.events (run_id);

    CREATE TABLE hq.sessions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      channel text NOT NULL,
      channel_user_id text NOT NULL,
      thread_id text NOT NULL DEFAULT '',
      conversation_id uuid NOT NULL DEFAULT gen_random_uuid(),
      agent text NOT NULL DEFAULT 'sage',
      last_active timestamptz NOT NULL DEFAULT now(),
      UNIQUE (channel, channel_user_id, thread_id)
    );

    CREATE TABLE hq.messages (
      id bigserial PRIMARY KEY,
      conversation_id uuid NOT NULL,
      ts timestamptz NOT NULL DEFAULT now(),
      agent text NOT NULL DEFAULT '',
      history jsonb NOT NULL
    );
    CREATE INDEX ix_messages_conv ON hq.messages (conversation_id, id);

    CREATE TABLE hq.outbox (
      id bigserial PRIMARY KEY,
      created_at timestamptz NOT NULL DEFAULT now(),
      channel text NOT NULL DEFAULT 'telegram',
      chat_ref text NOT NULL DEFAULT '',
      intent jsonb NOT NULL,
      idempotency_key text UNIQUE,
      sent_at timestamptz,
      attempts int NOT NULL DEFAULT 0,
      last_error text
    );

    CREATE TABLE hq.control (
      key text PRIMARY KEY,
      value jsonb NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now()
    );
