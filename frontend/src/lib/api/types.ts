// Shapes returned by the backend. Phase 2 replaces this file with a client
// generated from FastAPI's OpenAPI schema (@hey-api/openapi-ts); the component
// code keeps the same names either way.

export type TaskStatus =
  | "backlog"
  | "running"
  | "blocked"
  | "needs_approval"
  | "done"
  | "failed";

export interface Task {
  id: string;
  title: string;
  brief: string;
  agent: string;
  status: TaskStatus;
  source: string;
  parent_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskEvent {
  seq: number;
  ts: string;
  actor: string;
  event_type: string;
  data: Record<string, unknown>;
}

export interface Run {
  id: string;
  task_id: string | null;
  agent: string;
  model: string;
  job_hash: string;
  started_at: string;
  ended_at: string | null;
  outcome: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string | number;
  error: string | null;
}

export interface Ticket {
  id: string;
  task_id: string | null;
  tool_name: string;
  tool_args: Record<string, unknown>;
  action_class: string;
  status: "pending" | "approved" | "denied" | "expired";
  created_at: string;
  resolved_at: string | null;
  resolved_via: string | null;
}

export interface AgentInfo {
  name: string;
  description: string;
  model: string;
  tools: string[];
  cron: { schedule: string; prompt: string }[];
  paused: boolean;
  spend_today_usd: number;
  daily_cap_usd: number;
}

export interface Costs {
  today_usd: number;
  daily_cap_usd: number;
  week_by_agent: { agent: string; usd: string | number; runs: number }[];
}

export interface Health {
  ok: boolean;
  halted: boolean;
}

/** Envelope pushed on the /api/events SSE stream. */
export interface HqEvent {
  seq: number;
  ts: string;
  type: string;
  task_id: string | null;
  run_id: string | null;
  agent: string | null;
  payload: Record<string, unknown>;
}
