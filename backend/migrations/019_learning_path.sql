-- Where a lesson sits on the path.
--
-- The first week of lessons was a daily digest: four articles that happened to
-- be published, synthesized into one theme. The themes were real, but which
-- subjects appeared was decided by the feed, not by any plan — the owner put
-- it plainly: "don't you have any direction or any path, or just anything
-- random".
--
-- So lessons now carry the module they advance. That makes two things
-- possible: the scan can be told what to look for, and "am I getting
-- anywhere" becomes a query rather than a feeling.

ALTER TABLE hq.lessons ADD COLUMN IF NOT EXISTS path_step text NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS lessons_path_step_idx ON hq.lessons (path_step)
    WHERE path_step <> '';
