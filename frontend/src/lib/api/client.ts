import type {
  AgentInfo,
  Costs,
  Health,
  Run,
  Task,
  TaskEvent,
  Ticket,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

/** Query keys live in one place so SSE handlers can invalidate precisely. */
export const qk = {
  health: ["health"] as const,
  tasks: (status?: string) => ["tasks", status ?? "all"] as const,
  taskEvents: (id: string) => ["task-events", id] as const,
  runs: ["runs"] as const,
  tickets: (status: string) => ["tickets", status] as const,
  agents: ["agents"] as const,
  costs: ["costs"] as const,
};

export const api = {
  health: () => request<Health>("/health"),
  tasks: (status?: string) =>
    request<Task[]>(`/tasks${status ? `?status=${status}` : ""}`),
  taskEvents: (id: string) => request<TaskEvent[]>(`/tasks/${id}/events`),
  runs: (limit = 50) => request<Run[]>(`/runs?limit=${limit}`),
  tickets: (status = "pending") => request<Ticket[]>(`/tickets?status=${status}`),
  resolveTicket: (id: string, verdict: "approved" | "denied") =>
    request<{ resolved: boolean; reason?: string }>(`/tickets/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify({ verdict }),
    }),
  agents: () => request<AgentInfo[]>("/agents"),
  setAgentPaused: (name: string, paused: boolean) =>
    request<{ agent: string; paused: boolean }>(`/agents/${name}/pause`, {
      method: "POST",
      body: JSON.stringify({ paused }),
    }),
  costs: () => request<Costs>("/costs"),
};
