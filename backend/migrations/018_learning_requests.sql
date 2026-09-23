-- What he wants to learn next, in his own words.
--
-- The roster says who publishes and interests.md says which subjects count,
-- but neither lets him say "go find me something on X this week". He asked
-- for exactly that: a box on the Learn page where he writes a thought and the
-- morning run goes looking for it.
--
-- A row here outranks the roster: a request is the one input that is not a
-- standing preference but a thing he wants today.

CREATE TABLE IF NOT EXISTS hq.learning_requests (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- His words, unedited. Injected into the scan brief as data, never as
    -- instruction — it is his text, but it still goes in a bounded field.
    text        text NOT NULL,
    status      text NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'served', 'dropped')),
    -- The lesson that answered it, when one does.
    lesson_id   uuid REFERENCES hq.lessons(id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    served_at   timestamptz
);

CREATE INDEX IF NOT EXISTS learning_requests_open_idx
    ON hq.learning_requests (created_at DESC) WHERE status = 'open';
