-- The prompt version each run used, 2026-09-23.
--
-- A short hash of the agent's assembled instructions (charter, card,
-- policy, memory blocks, skills index; the clock line excluded). A run, a
-- regression result and an incident can then name the exact prompt that
-- produced them, and a change of behaviour can be traced to a change of text.

ALTER TABLE hq.runs ADD COLUMN bundle_sha text NOT NULL DEFAULT '';
