-- Take the reference list back out of the ledger.
--
-- His curated essays were seeded as readings with a fixed position, then
-- demoted to beatable candidates, and both were wrong for the same reason:
-- a row in hq.readings is a thing the system intends to read. Those essays
-- are a description of good taste, not a queue and not a shortlist.
--
-- What stays: the one that was genuinely read and taught on 2026-09-12
-- (G-Eval), because that is real history — the lesson row points at it, and
-- removing it would let tomorrow read it again.
DELETE FROM hq.readings WHERE path_order > 0 AND status = 'found';

-- The column goes with them. Nothing in the code reads it any more: the
-- reading order comes from the quality bar and the current subject, both of
-- which live in learning/path.md where he can change them.
DROP INDEX IF EXISTS hq.readings_path_idx;
ALTER TABLE hq.readings DROP COLUMN IF EXISTS path_order;
