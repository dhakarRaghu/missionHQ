-- The daily learning journey: what to read, what was read, what was taught.
--
-- The owner said the system should teach him something or he would drop it.
-- Recommending links is not teaching: he already has more links than
-- mornings. So the pipeline reads the articles in full and writes him one
-- lesson a day, and these two tables are what stop it repeating itself.
--
-- `readings` is the ledger of candidates, the same idea as the jobs dedupe:
-- a URL is seen once, scored once, read once, taught once. Without it the
-- same three famous posts win the scoring every morning and by week two the
-- lesson is something he read on Monday.

CREATE TABLE IF NOT EXISTS hq.lessons (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- One lesson a day, so the date is the natural key. A second run on the
    -- same day updates that day's lesson rather than adding a rival to it.
    lesson_date  date NOT NULL UNIQUE,
    title        text NOT NULL,
    -- What he reads on his phone at breakfast, before deciding to open it.
    one_liner    text NOT NULL DEFAULT '',
    topic        text NOT NULL DEFAULT '',
    md_path      text NOT NULL DEFAULT '',
    -- The self-contained page with the diagram. Rendered in a sandboxed
    -- frame, never in the console's own origin: tutor writes this HTML from
    -- web-derived digests, so it is treated as untrusted markup.
    html_path    text NOT NULL DEFAULT '',
    score        int  NOT NULL DEFAULT 0,
    -- The urls it was built from, so a claim can be traced to its source.
    sources      jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hq.readings (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    url          text NOT NULL UNIQUE,
    title        text NOT NULL DEFAULT '',
    author       text NOT NULL DEFAULT '',
    -- Where it was found: blog, newsletter, paper, hn, x, linkedin.
    source       text NOT NULL DEFAULT '',
    topic        text NOT NULL DEFAULT '',
    posted_date  text NOT NULL DEFAULT '',
    -- One line on what he would learn, written by whoever put it forward.
    why          text NOT NULL DEFAULT '',
    -- 0-10, how much it would teach HIM. Code sorts on this, which is why it
    -- is a column and not a sentence: picking the day's reading is the
    -- cheapest step and does not need a second model round trip.
    score        int  NOT NULL DEFAULT 0,
    status       text NOT NULL DEFAULT 'found'
                 CHECK (status IN ('found', 'queued', 'digested', 'taught', 'skipped')),
    -- The quarantine note holding the full study digest, once one exists.
    digest_path  text NOT NULL DEFAULT '',
    lesson_id    uuid REFERENCES hq.lessons(id) ON DELETE SET NULL,
    first_seen   timestamptz NOT NULL DEFAULT now(),
    last_seen    timestamptz NOT NULL DEFAULT now()
);

-- The morning's two questions: what is still unread, and what did it teach.
CREATE INDEX IF NOT EXISTS readings_pending_idx ON hq.readings (status, score DESC, first_seen DESC);
CREATE INDEX IF NOT EXISTS readings_lesson_idx ON hq.readings (lesson_id) WHERE lesson_id IS NOT NULL;
