-- Vault full-text search: one row per markdown chunk, indexed with a GIN tsvector.
-- The 'A'-weighted part is the path with separators replaced by spaces, so
-- "quarantine/2026-09-02-dbos.md" matches "quarantine", "dbos" and "2026".
CREATE TABLE hq.memory_chunks (
  id bigserial PRIMARY KEY,
  path text NOT NULL,
  chunk_no int NOT NULL,
  heading text NOT NULL DEFAULT '',
  body text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  tsv tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', translate(coalesce(path, ''), '/-_.', '    ')), 'A')
    || setweight(to_tsvector('english', coalesce(heading, '')), 'B')
    || to_tsvector('english', coalesce(body, ''))
  ) STORED,
  UNIQUE (path, chunk_no)
);
CREATE INDEX ix_memory_chunks_tsv ON hq.memory_chunks USING GIN (tsv);
