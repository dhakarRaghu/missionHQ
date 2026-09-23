-- The reading list has an order, and the order is the point.
--
-- The first curriculum was mine: eight generic modules, "go find articles
-- about retrieval". The owner replaced it with something far better — he read
-- all 111 essays on arpitbhayani.me, kept 24, ordered them into four phases
-- and paired each phase with a build. His verdict on mine was short: "I don't
-- like the path you have said".
--
-- So a reading can now hold its position on that list. Position beats score:
-- when the next essay on the path is unread, that is what gets read today,
-- and the open-web scan does not run at all.
ALTER TABLE hq.readings ADD COLUMN IF NOT EXISTS path_order int NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS readings_path_idx ON hq.readings (path_order)
    WHERE path_order > 0 AND status = 'found';
