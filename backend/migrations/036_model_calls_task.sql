-- The hang watchdog reads a task's latest model call as a sign of life,
-- 2026-09-23: the staged lesson writer calls models with no tool events.
CREATE INDEX IF NOT EXISTS model_calls_task ON hq.model_calls (task_id, started_at);
