# Build a new agent

Use when the owner describes an agent he wants. This was a separate agent
once; it is a skill because building an agent is a thing you do occasionally,
not a role someone holds.

## Before you draft anything

Ask yourself whether it should be an agent at all. Most requests are better as
a skill, and a skill costs nothing to maintain:

- **A skill** when it is a procedure you follow on request. No schedule of its
  own, no separate memory, no new tools. Write a SKILL.md under your own
  skills/ folder and stop.
- **An agent** only when at least one is true: it needs a schedule of its own,
  or it needs a tool that would be unsafe on you, or its write scope must be
  narrower than yours.

The second reason is the real one. An agent that reads the open web can never
also write trusted memory or hand work to others, so reading the web is why
hunter exists rather than being part of you. Separation for its own sake just
adds a folder nobody maintains.

Say which of these it is, and why, before writing anything.

## Drafting

1. `list_agent_drafts` first: it may already exist.
2. `draft_agent` with the smallest tool list that can do the job. Every tool
   is a permanent grant, and a tool nobody uses is a tool nobody notices being
   misused.
3. Never include a tool that acts on the world. The loader refuses any agent
   holding one, so such a draft would not load.
4. `validate_agent_draft` before telling the owner it is ready. A draft that
   fails to load is worse than no draft: it looks finished.

## Handing it over

Tell the owner the name, what it does, the tools you gave it and why each one,
and its schedule. Then say it is a draft and he activates it on the Agents
page, which restarts the backend. Do not activate it yourself.
