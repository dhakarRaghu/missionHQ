-- The fit score is computed, and its reasons are kept.
--
-- The score used to be a number the model chose from a rubric in its card,
-- so the same posting could score 6 one night and 8 the next, and nothing on
-- the row said why. record_job now computes it from the fields (lane from the
-- title, the years floor, the package, stack, domain, geography) and writes
-- each part here, with the model's own number beside them for comparison.
--
-- pay_lakh is the upper bound parsed from compensation or pay_signal, in lakhs
-- per annum; NULL when neither names a figure. lane is the candidate profile's
-- lane the title falls in: software, forward_deployed, applied_ai, or ''.

ALTER TABLE hq.jobs ADD COLUMN IF NOT EXISTS fit_parts jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE hq.jobs ADD COLUMN IF NOT EXISTS pay_lakh numeric;
ALTER TABLE hq.jobs ADD COLUMN IF NOT EXISTS lane text NOT NULL DEFAULT '';
