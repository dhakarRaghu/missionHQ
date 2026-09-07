import type {
  ActivateResult,
  AgentDraft,
  AgentInfo,
  ChatMessage,
  ChatTicket,
  ChatSession,
  Costs,
  DailyCost,
  Health,
  NewTask,
  Run,
  RunDetail,
  SendChatBody,
  SendChatResult,
  Task,
  TaskEvent,
  Ticket,
  Verdict,
} from "./types";
import { API_BASE as BASE, authHeaders, onUnauthorized } from "@/lib/auth";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function isJson(res: Response) {
  return (res.headers.get("content-type") ?? "").includes("application/json");
}

/** FastAPI reports errors as {detail}. Never surface an HTML error page. */
async function errorMessage(res: Response): Promise<string> {
  if (isJson(res)) {
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") return body.detail;
      if (body.detail !== undefined) {
        return JSON.stringify(body.detail).slice(0, 200);
      }
    } catch {
      // fall through to the status text
    }
  }
  if (res.status >= 500) {
    return "Connection to Mission HQ dropped before it confirmed the result. Refresh or retry safely.";
  }
  return res.statusText || `HTTP ${res.status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  for (const [name, value] of Object.entries(authHeaders())) {
    headers.set(name, value);
  }

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(
      0,
      "Cannot reach Mission HQ. The turn may still be running; refresh or retry safely.",
    );
  }
  if (!res.ok) {
    // Token missing or rejected: drop it and send the browser to /login.
    if (res.status === 401) onUnauthorized();
    throw new ApiError(res.status, await errorMessage(res));
  }
  // 204 and non-JSON bodies resolve to undefined instead of a parse error.
  if (res.status === 204 || !isJson(res)) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

function query(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

const seg = encodeURIComponent;

/** Query keys live in one place so SSE handlers can invalidate precisely. */
export const qk = {
  health: ["health"] as const,
  tasks: (status?: string) => ["tasks", status ?? "all"] as const,
  taskEvents: (id: string) => ["task-events", id] as const,
  runs: (limit?: number) => ["runs", limit ?? 50] as const,
  runDetail: (id: string) => ["run-detail", id] as const,
  tickets: (status: string) => ["tickets", status] as const,
  agents: ["agents"] as const,
  /** Prefixed by qk.agents so an agents invalidation refreshes it too. */
  agentDrafts: ["agents", "drafts"] as const,
  costs: ["costs"] as const,
  /** Prefixed by qk.costs so a costs invalidation refreshes it too. */
  dailyCosts: (days: number) => ["costs", "daily", days] as const,
  chatSessions: ["chat-sessions"] as const,
  chatTickets: (id: string) => ["chat-tickets", id] as const,
  chatMessages: (sessionId: string) => ["chat-messages", sessionId] as const,
  /** Written by src/lib/sse.ts, never fetched. */
  feed: ["sse", "feed"] as const,
  sseStatus: ["sse", "status"] as const,
};

/** Backend may serialise Decimal columns as strings. */
type RawRun = Omit<Run, "cost_usd"> & { cost_usd: string | number };
type RawRunDetail = Omit<RunDetail, "run"> & {
  run: Omit<RunDetail["run"], "cost_usd"> & { cost_usd: string | number };
};
type RawDailyCost = Omit<DailyCost, "usd"> & { usd: string | number };
type RawCosts = {
  today_usd: string | number;
  daily_cap_usd: string | number;
  week_by_agent: { agent: string; usd: string | number; runs: number }[];
};

export const api = {
  health: () => request<Health>("/health"),

  tasks: (status?: string, limit?: number) =>
    request<Task[]>(`/tasks${query({ status, limit })}`),
  createTask: (body: NewTask) =>
    request<Task>("/tasks", { method: "POST", body: JSON.stringify(body) }),
  taskEvents: (id: string) =>
    request<TaskEvent[]>(`/tasks/${seg(id)}/events`),

  runs: async (limit = 50): Promise<Run[]> => {
    const rows = await request<RawRun[]>(`/runs${query({ limit })}`);
    return rows.map((run) => ({ ...run, cost_usd: Number(run.cost_usd) }));
  },

  runDetail: async (id: string): Promise<RunDetail> => {
    const raw = await request<RawRunDetail>(`/runs/${seg(id)}`);
    return { ...raw, run: { ...raw.run, cost_usd: Number(raw.run.cost_usd) } };
  },

  /** `status` may list several states: "approved,denied". */
  tickets: (status = "pending", limit?: number) =>
    request<Ticket[]>(`/tickets${query({ status, limit })}`),
  resolveTicket: (id: string, verdict: Verdict) =>
    request<{ resolved: boolean; reason?: string }>(
      `/tickets/${seg(id)}/resolve`,
      { method: "POST", body: JSON.stringify({ verdict }) },
    ),

  agents: () => request<AgentInfo[]>("/agents"),
  agentDrafts: () => request<AgentDraft[]>("/agents/drafts"),
  activateAgent: (name: string) =>
    request<ActivateResult>(`/agents/${seg(name)}/activate`, {
      method: "POST",
    }),
  setAgentPaused: (name: string, paused: boolean) =>
    request<{ agent: string; paused: boolean }>(`/agents/${seg(name)}/pause`, {
      method: "POST",
      body: JSON.stringify({ paused }),
    }),

  chatSessions: () => request<ChatSession[]>("/chat/sessions"),
  createChatSession: (agent: string) =>
    request<{ session_id: string; agent: string; created: boolean }>(
      "/chat/sessions",
      { method: "POST", body: JSON.stringify({ agent }) },
    ),
  deleteChatSession: (sessionId: string) =>
    request<{ session_id: string; deleted: boolean }>(
      `/chat/sessions/${seg(sessionId)}`,
      { method: "DELETE" },
    ),
  setChatSessionAgent: (sessionId: string, agent: string) =>
    request<{ session_id: string; agent: string }>(
      `/chat/sessions/${seg(sessionId)}/agent`,
      { method: "POST", body: JSON.stringify({ agent }) },
    ),
  chatTickets: (sessionId: string) =>
    request<ChatTicket[]>(`/chat/sessions/${seg(sessionId)}/tickets`),
  chatMessages: (sessionId: string) =>
    request<ChatMessage[]>(`/chat/sessions/${seg(sessionId)}/messages`),
  sendChatMessage: (sessionId: string, body: SendChatBody) =>
    request<SendChatResult>(`/chat/sessions/${seg(sessionId)}/messages`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  dailyCosts: async (days = 14): Promise<DailyCost[]> => {
    const rows = await request<RawDailyCost[]>(`/costs/daily${query({ days })}`);
    return rows.map((row) => ({ ...row, usd: Number(row.usd) }));
  },

  costs: async (): Promise<Costs> => {
    const raw = await request<RawCosts>("/costs");
    return {
      today_usd: Number(raw.today_usd),
      daily_cap_usd: Number(raw.daily_cap_usd),
      week_by_agent: raw.week_by_agent.map((row) => ({
        ...row,
        usd: Number(row.usd),
      })),
    };
  },
};
