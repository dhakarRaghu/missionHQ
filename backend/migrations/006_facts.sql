-- Facts with validity (memory layer v2, tools/facts_tools.py).
-- One row per statement about a subject. A newer fact about the same subject
-- SUPERSEDES the old row: invalid_at is set and superseded_by points at the
-- new id. Rows are never deleted, so history and provenance stay auditable.
-- provenance: 'owner' (stated by the owner), 'agent' (an agent's own
-- conclusion), 'web' (the run had read web content; excluded from recall by
-- default). embedding = llm.embed(subject + ": " + fact), 768 dims as in 005.
CREATE TABLE hq.facts (
  id bigserial PRIMARY KEY,
  subject text NOT NULL,
  fact text NOT NULL,
  source_path text,
  provenance text NOT NULL CHECK (provenance IN ('owner', 'agent', 'web')),
  agent text NOT NULL,
  confidence text NOT NULL DEFAULT 'medium',
  valid_at timestamptz NOT NULL DEFAULT now(),
  invalid_at timestamptz,
  superseded_by bigint REFERENCES hq.facts(id),
  embedding vector(768),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_facts_subject ON hq.facts (subject);
CREATE INDEX ix_facts_valid ON hq.facts (subject, valid_at DESC) WHERE invalid_at IS NULL;
CREATE INDEX ix_facts_embedding ON hq.facts USING hnsw (embedding vector_cosine_ops);
