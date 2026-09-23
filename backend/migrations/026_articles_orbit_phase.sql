-- Articles orbit the active course phase, 2026-09-14.
--
-- The course is the spine; the daily article shows whether the course's model
-- transfers to real systems. Every candidate reading and every article now
-- carries the phase it serves and what it is for relative to that phase, so
-- selection can refuse an off-phase article however high it scored, and the
-- next scan can aim at the relationship the phase is still missing.

ALTER TABLE hq.readings
    ADD COLUMN IF NOT EXISTS phase_slug   text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS relationship text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS adds         text NOT NULL DEFAULT '',
    -- The shelf-life gate needs both of these at selection time, and selection
    -- reads the ledger, not the envelope. Before this column existed the gate
    -- only ever saw leads with no date and kept all of them.
    ADD COLUMN IF NOT EXISTS shelf_life   text NOT NULL DEFAULT '';

ALTER TABLE hq.lessons
    ADD COLUMN IF NOT EXISTS phase_slug   text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS relationship text NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS lessons_phase_slug_idx
    ON hq.lessons (phase_slug) WHERE phase_slug <> '';
