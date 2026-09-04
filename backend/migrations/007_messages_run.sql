-- Link a stored chat history row to the run that produced it. The console
-- shows cost, tool count and a run link under each assistant turn. The column
-- is nullable: rows written before this migration, and rows written by code
-- that does not pass a run id, match their run by (agent, ts window) instead.
ALTER TABLE hq.messages ADD COLUMN run_id uuid;
CREATE INDEX ix_messages_run ON hq.messages (run_id);
