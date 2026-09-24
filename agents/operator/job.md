---
name: operator
description: "Everything the Codex CLI can reach: the browser you are signed into, the shell, files and dashboards. Reads only. A run needs your approval unless you approved one like it in the last twelve hours, or the guard finds it read-only and bounded."
status: active
runtime: codex
model: default
tools: []
caps:
  cost_per_run_usd: 5.00
  # Codex cannot be held to a call count; codex_timeout_s is what bounds a run.
  tool_calls: 90
  daily_usd: 15.00
cron: []
---
Operator's whole contract is AGENTS.md in this folder. Mission HQ copies it into
Codex's working directory before every run, and the browse guard judges the run against the same text.
