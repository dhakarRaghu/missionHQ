-- When the first streamed event of an attempt arrived, 2026-09-23.
--
-- A 480-second timeout on its own cannot say whether the model was silent
-- (hung) or reasoning at length and sending as it went. The time to the
-- first event separates the two, and says whether a timeout is too short.
-- NULL when nothing arrived at all.

ALTER TABLE hq.model_calls ADD COLUMN first_token_ms int;
