-- The idea radar, step one: what people report as hard, collected by code.
--
-- He asked where project ideas come from when nobody hands him one, and said
-- what he will not build: something small that a coding assistant finishes in
-- a session. An idea worth two weeks starts from a problem someone really has,
-- so the radar collects evidence first and proposes nothing yet: issues and
-- design proposals in the projects he studies, discussion threads, papers in
-- the systems categories, the posts of the roster's feeds, incident titles.
--
-- One row per thing found, keyed by its url, so a second collection changes
-- nothing. No model reads a row here. Step two reads `excerpt`, which is text
-- written by strangers: it is data, never instruction, and stays bounded.

CREATE TABLE hq.radar_items (
  id bigserial PRIMARY KEY,
  source text NOT NULL,             -- the source's name: a repo, a feed, a query
  kind text NOT NULL CHECK (kind IN
    ('issue', 'thread', 'launch', 'paper', 'post', 'incident')),
  area text NOT NULL DEFAULT '',    -- inference | agents | evals | ... as the source declares it
  domain text NOT NULL,             -- who said it: github.com/vllm-project/vllm, brooker.co.za
  url text NOT NULL UNIQUE,
  title text NOT NULL,
  excerpt text NOT NULL DEFAULT '',
  published_at timestamptz,
  meta jsonb NOT NULL DEFAULT '{}'::jsonb,   -- comments, reactions, labels, points
  fetched_at timestamptz NOT NULL DEFAULT now(),
  extracted_at timestamptz,         -- set when step two has read it
  verdict text NOT NULL DEFAULT ''  -- '' until read; then problem | none | refused
);

CREATE INDEX radar_items_unread ON hq.radar_items (fetched_at) WHERE extracted_at IS NULL;
CREATE INDEX radar_items_source ON hq.radar_items (source, published_at DESC);
CREATE INDEX radar_items_domain ON hq.radar_items (domain, published_at DESC);
