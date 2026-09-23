// Shapes returned by the backend. Field names follow the FastAPI responses
// one to one; operation ids are noted on the client methods in client.ts.

/** Task states. The order is the display order on the board. */
export const TASK_STATUSES = [
  "needs_approval",
  "running",
  "blocked",
  "backlog",
  "done",
  "failed",
] as const;

export type TaskStatus = (typeof TASK_STATUSES)[number];

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
  /** Latest run of this task, if any (LEFT JOIN in GET /api/tasks). */
  run_id: string | null;
}

/** Body of POST /api/tasks. */
export interface NewTask {
  agent: string;
  title: string;
  brief: string;
}

export interface TaskEvent {
  seq: number;
  ts: string;
  actor: string;
  event_type: string;
  data: Record<string, unknown>;
}

export type RunOutcome = "done" | "blocked" | "failed";

export interface Run {
  id: string;
  task_id: string | null;
  agent: string;
  model: string;
  job_hash: string;
  started_at: string;
  ended_at: string | null;
  outcome: RunOutcome | null;
  input_tokens: number;
  output_tokens: number;
  /** Always a number. The client coerces the backend's decimal string. */
  cost_usd: number;
  error: string | null;
}

/** One hq.events row for a run, as returned by GET /api/runs/{id}. */
export interface RunEvent {
  id: number;
  ts: string;
  task_id: string | null;
  agent: string | null;
  kind: string;
  payload: Record<string, unknown>;
}

/** Payload of a "tool.called" event (written by the @hq_tool wrapper). */
export interface ToolCalledPayload {
  tool: string;
  args: Record<string, unknown>;
  duration_ms: number;
  ok: boolean;
  error?: string;
  /** First 400 chars of the tool's return value (JSON for dicts and lists). */
  result?: string;
}

/** Payload of a "ledger" event (progress-ledger verdict after a tool round). */
export interface LedgerPayload {
  satisfied: boolean;
  progress: boolean;
  looping: boolean;
  reason: string;
  next_instruction: string;
  stall: number;
}

export interface RunDetailRun extends Run {
  wf_id: string | null;
  stall_count: number;
  /** Set when the run belongs to a task. */
  task_title: string | null;
  task_brief: string | null;
}

export interface RunDetail {
  run: RunDetailRun;
  /** All events for the run, ordered by id. */
  events: RunEvent[];
  /** Approval tickets opened during the run. */
  tickets: Ticket[];
  /** Chat runs only: the user/assistant turns of the round this run answered.
   * null when not derivable; transcript_reason says why. */
  transcript: ChatMessage[] | null;
  transcript_reason: string | null;
}

/** One row of GET /api/costs/daily: spend per calendar day (CRON_TZ) and agent. */
export interface DailyCost {
  date: string;
  agent: string;
  usd: number;
  runs: number;
}

/** Verdict sent to POST /api/tickets/{id}/resolve. */
export type Verdict = "approved" | "denied";

export interface Ticket {
  id: string;
  task_id: string | null;
  run_id: string | null;
  /** Agent of the run that asked (LEFT JOIN hq.runs); null for orphan tickets. */
  agent: string | null;
  tool_name: string;
  tool_args: Record<string, unknown>;
  action_class: string;
  status: "pending" | Verdict | "expired";
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
  caps: { cost_per_run_usd: number; tool_calls: number; daily_usd: number };
  /** Scopes granted through vault_write:<scope> tool entries ("**" = whole vault). */
  vault_write_scopes: string[];
}

/** One row of GET /api/agents/drafts: a folder whose job.md says status: draft. */
export interface AgentDraft {
  name: string;
  description: string;
  model: string;
  tools: string[];
  cron: { schedule: string; prompt: string }[];
  caps: Partial<AgentInfo["caps"]>;
}

/** POST /api/agents/{name}/activate. The backend restarts after replying. */
export interface ActivateResult {
  activated: string;
  restarting: boolean;
  message: string;
}

export interface Costs {
  today_usd: number;
  daily_cap_usd: number;
  week_by_agent: { agent: string; usd: number; runs: number }[];
}

export interface Health {
  ok: boolean;
  halted: boolean;
}

/** A web chat session (hq.sessions row with channel = 'web'). */
export interface ChatSession {
  id: string;
  agent: string;
  last_active: string;
  /** First user message of the stored transcript, if any. */
  preview: string | null;
}

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  text: string;
  ts: string | null;
  /** Which agent produced this turn. A delegated result is not from the agent
   * you are talking to, and labelling it as such hides the handover. */
  agent?: string | null;
  /** True when Mission HQ posted this in, rather than the agent replying. */
  delivered?: boolean;
  /** Assistant turns only, when the backend matched the run: else null. */
  run_id?: string | null;
  cost_usd?: number | null;
  tools?: string[] | null;
}

/** Body of POST /api/chat/sessions/{id}/messages. */
export interface SendChatBody {
  text: string;
  /** Client-generated UUID. The backend derives the workflow id from it, so a
   * retried request cannot start a second run. */
  client_id: string;
}

/** "pending" means the run is still going (usually waiting for an approval
 * ticket). The reply arrives in the transcript after an SSE invalidation. */
export type SendChatResult =
  | {
      status: "done";
      reply: string;
      run_id: string | null;
      cost_usd: number | null;
      tools: string[] | null;
    }
  | { status: "pending" }
  | {
      /** the turn ran but ended in "failed: …" / "blocked: …" */
      status: "failed";
      reply: string;
      run_id: string | null;
      cost_usd: number | null;
      tools: string[] | null;
    };

/** Named SSE frame types on GET /api/events. Each is registered as a listener. */
export const HQ_EVENT_TYPES = [
  "task.created",
  "task.updated",
  "run.started",
  "run.finished",
  "run.failed",
  "run.no_artifact",
  "chat.updated",
  "tool.called",
  "ledger",
  "ticket.created",
  "ticket.resolved",
  "approval_resolved",
  "guardrail.denied",
  "notify",
  "notify_digested",
  "digest",
  "cron.caught_up",
  "cron.missed",
  "vault.reindexed",
  "fact.recorded",
  "fact.retired",
  "policy.added",
  "injection_detected",
  "owner.action",
  "job.recorded",
  "job.updated",
  "announce",
] as const;

export type HqEventType = (typeof HQ_EVENT_TYPES)[number];

/** Envelope pushed on the /api/events SSE stream. */
export interface HqEvent {
  seq: number;
  ts: string;
  type: HqEventType;
  task_id: string | null;
  run_id: string | null;
  agent: string | null;
  payload: Record<string, unknown>;
}

/** State of the single console-wide EventSource. */
export type SseStatus = "connecting" | "connected" | "reconnecting";

/** One approval blocking work this chat started. */
export interface ChatTicket {
  id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  action_class: string;
  agent: string | null;
  created_at: string;
}

/** Work this chat handed to another agent, still in flight. */
export interface ChatTask {
  id: string;
  agent: string;
  title: string;
  status: TaskStatus;
  updated_at: string;
}

/** One role in the job ledger. Hunter records it; the owner moves it along. */
/** One person the owner could ask for a referral, found by operator on the
 * company's own people page. Ranked by degree: a 1st-degree connection
 * already knows him and is worth every other lead put together. */
export const REFERRAL_STATUSES = ["found", "asked", "replied", "dismissed"] as const;

export type ReferralStatus = (typeof REFERRAL_STATUSES)[number];

export interface Referral {
  id: string;
  job_id: string;
  company: string;
  name: string;
  headline: string;
  profile_url: string;
  degree: "1st" | "2nd" | "3rd" | "none" | "persona" | "unknown";
  shared_ground: string;
  why_them: string;
  mutuals: string;
  source: string;
  status: ReferralStatus;
  created_at: string;
  updated_at: string;
  /** Joined from the role this person is for. */
  job_role: string;
  job_url: string;
  fit_score: number;
  job_status: JobStatus;
}

export const JOB_STATUSES = [
  "seen",
  "shortlisted",
  "referral",
  "applied",
  "interviewing",
  "offer",
  "rejected",
  "closed",
] as const;

export type JobStatus = (typeof JOB_STATUSES)[number];

export interface JobFitPart {
  points: number;
  note?: string;
  lane?: string;
  reason?: string;
}

export interface Job {
  id: string;
  company: string;
  role: string;
  url: string;
  source: string;
  provider: string;
  external_id: string;
  location: string;
  remote_policy: string;
  experience_band: string;
  compensation: string;
  stack: string;
  /** 0-10, computed by record_job from the row's fields; `fit_parts` holds
   * each part that moved it, and why_fit is hunter's sentence on the role. */
  fit_score: number;
  fit_parts?: Record<string, JobFitPart | number | string | null>;
  /** Upper bound of the package, in lakhs per annum; null when none is named. */
  pay_lakh?: number | null;
  /** The candidate profile's lane: software, forward_deployed, applied_ai or "". */
  lane?: string;
  fit_bucket: "strong" | "decent" | "stretch";
  status: JobStatus;
  why_fit: string;
  next_step: string;
  notes: string;
  referral: string;
  /** Hunter's company dig, done only for roles scoring 6+. `researched_at` is
   * null when the dig has not happened, which is different from a dig that
   * found nothing to say. */
  company_brief: string;
  pay_signal: string;
  role_brief: string;
  researched_at: string | null;
  /** The LinkedIn job post the owner applies from. When present it is the
   * card's link; the company's own portal is not needed. Empty for a role
   * hunter found on an ATS board rather than on LinkedIn. */
  linkedin_url: string;
  seen_count: number;
  first_seen: string;
  last_seen: string;
}
