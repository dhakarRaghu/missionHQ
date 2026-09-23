import { getJson, sendJson } from "@/lib/api/request";

// Client, types and query keys for the agent configuration editor
// (GET/PUT /api/agents/{name}/config, /policy, /apply, /tools-catalog).

export type AgentStatus = "active" | "paused" | "draft";

export interface CronEntry {
  schedule: string;
  prompt: string;
}

export interface AgentCaps {
  cost_per_run_usd: number;
  tool_calls: number;
  daily_usd: number;
}

export interface AgentCommit {
  hash: string;
  ts: string;
  message: string;
}

/** GET /api/agents/{name}/config. */
export interface AgentConfig {
  name: string;
  status: AgentStatus | string;
  description: string;
  model: string;
  tools: string[];
  caps: AgentCaps;
  cron: CronEntry[];
  /** Body of job.md (below the frontmatter). */
  role_prompt: string;
  /** policy.md, trimmed. */
  policy: string;
  job_md_raw: string;
  policy_md_raw: string;
  /** Newest first, at most 5. Empty when the folder has no commits. */
  git: AgentCommit[];
  /** True when the running backend has this agent registered. */
  loaded: boolean;
  /** vault_write scopes granted in job.md. */
  memory_refs: string[];
  /** Global DAILY_SPEND_CAP_USD; caps.daily_usd may not exceed it. */
  daily_spend_cap_usd: number;
  /** Set when the on-disk job.md no longer parses. */
  parse_error: string | null;
}

/** Body of POST validate and PUT config. `name` is never sent. */
export interface AgentConfigBody {
  description: string;
  model: string;
  tools: string[];
  caps: AgentCaps;
  cron: CronEntry[];
  role_prompt: string;
  status: AgentStatus;
  /** PUT config only: also write policy.md. Omit to leave it untouched. */
  policy?: string;
}

export interface ValidationResult {
  ok: boolean;
  errors: string[];
  warnings: string[];
  /** Unified diff against the current job.md (and policy.md when sent). */
  diff: string;
}

export interface SaveResult {
  saved: boolean;
  /** False when job.md did not change (for example a policy-only save). */
  restart_required: boolean;
  diff: string;
  warnings: string[];
}

export interface PolicySaveResult {
  saved: boolean;
  restart_required: false;
  message: string;
}

export interface ApplyResult {
  restarting: boolean;
  delay_s: number;
  message: string;
}

/** One row of GET /api/agents/tools-catalog. */
export interface ToolCatalogEntry {
  name: string;
  action: string;
  trust: string;
  /** "no" for tools that act outward or spend. */
  grantable: "yes" | "no";
  description: string;
}

export const MODEL_PRESETS = ["cheap", "default", "deep"] as const;
export const AGENT_STATUSES: AgentStatus[] = ["active", "paused", "draft"];

/** Prefixed by qk.agents (["agents"]) so an agents invalidation refreshes these too. */
export const agentAdminKeys = {
  config: (name: string) => ["agents", "config", name] as const,
  toolsCatalog: ["agents", "tools-catalog"] as const,
};

const seg = encodeURIComponent;

export const agentAdminApi = {
  config: (name: string) => getJson<AgentConfig>(`/agents/${seg(name)}/config`),
  toolsCatalog: () => getJson<ToolCatalogEntry[]>("/agents/tools-catalog"),
  validate: (name: string, body: AgentConfigBody) =>
    sendJson<ValidationResult>(
      "POST",
      `/agents/${seg(name)}/config/validate`,
      body,
    ),
  update: (name: string, body: AgentConfigBody) =>
    sendJson<SaveResult>("PUT", `/agents/${seg(name)}/config`, body),
  updatePolicy: (name: string, policy: string) =>
    sendJson<PolicySaveResult>("PUT", `/agents/${seg(name)}/policy`, {
      policy,
    }),
  apply: (name: string) =>
    sendJson<ApplyResult>("POST", `/agents/${seg(name)}/apply`),
};
