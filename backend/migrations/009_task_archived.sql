-- Finished tasks stay on the board forever, so the Done column grows without
-- limit and the columns that need attention get harder to find. The
-- maintenance tick now retires a task that finished more than
-- BOARD_ARCHIVE_DAYS ago by setting this status. Nothing is deleted: the row,
-- its runs and its events all stay, and the task list still returns it when
-- asked for status=archived by name.

ALTER TABLE hq.tasks DROP CONSTRAINT IF EXISTS tasks_status_check;

ALTER TABLE hq.tasks ADD CONSTRAINT tasks_status_check
    CHECK (status = ANY (ARRAY[
        'backlog', 'running', 'blocked', 'needs_approval',
        'done', 'failed', 'archived'
    ]));

-- The archiver scans finished tasks by age on every tick.
CREATE INDEX IF NOT EXISTS tasks_status_updated_idx
    ON hq.tasks (status, updated_at);
