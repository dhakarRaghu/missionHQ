-- The LinkedIn post is the link the owner applies from.
--
-- `url` held the original company or ATS posting, because hunter wanted it to
-- detect the board. For a big company that portal is a wall — Workday,
-- Eightfold, a JavaScript-only site — and chasing it is what lost American
-- Express "Software Engineer I, 1-2 years" on 2026-09-12, a lead that arrived
-- with everything needed to record it. The owner applies from LinkedIn and
-- said so: "just directly add these LinkedIn job posts, don't need the
-- company apply page". So the post gets its own column and the card links it.
ALTER TABLE hq.jobs ADD COLUMN IF NOT EXISTS linkedin_url text NOT NULL DEFAULT '';

-- A request whose answer has been handed back to hunter to record. Before this
-- the loop stopped at 'dispatched': operator answered into quarantine and
-- nothing turned the answer into a job row. Cisco was found open and
-- early-career on two consecutive nights and never reached the board.
ALTER TABLE hq.operator_requests DROP CONSTRAINT IF EXISTS operator_requests_status_check;
ALTER TABLE hq.operator_requests ADD CONSTRAINT operator_requests_status_check
    CHECK (status IN ('pending', 'dispatched', 'answered', 'declined', 'expired'));
