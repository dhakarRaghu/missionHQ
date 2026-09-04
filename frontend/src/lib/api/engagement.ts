// Value-week engagement client. Kept apart from client.ts so the shared
// client and its query keys stay owned by one place; requests go through the
// shared helpers in request.ts (auth header, 401 redirect, {detail} errors).

import { getJson, sendJson } from "@/lib/api/request";

export interface ValueWeekDay {
  date: string;
  sent: number;
  acted: number;
}

export type ValueWeekVerdict = "on track" | "at risk";

/** Shape of GET /api/engagement and POST /api/engagement/start. */
export interface ValueWeekStatus {
  /** ISO date in CRON_TZ, or null when the week has not been started. */
  start: string | null;
  /** True from day 1 to day 7 inclusive. */
  active: boolean;
  /** 1..7 while running, 0 when not started. */
  day: number;
  days_left: number;
  /** Outbox rows delivered since the start (digest rows excluded). */
  sent: number;
  /** owner.action events since the start. */
  acted: number;
  tickets_pending_over_24h: number;
  /** vault reads by agents (memory_search / recall_facts / vault_read) since start */
  recall_queries: number;
  /** chat turns the owner started since start */
  owner_questions: number;
  /** acted / sent, 0 when nothing was sent. */
  response_rate: number;
  verdict: ValueWeekVerdict;
  per_day: ValueWeekDay[];
}

export const engagementKeys = {
  status: ["engagement"] as const,
};

export const engagementApi = {
  /** operation_id getEngagement */
  status: () => getJson<ValueWeekStatus>("/engagement"),
  /** operation_id startValueWeek; a no-op when the week already started. */
  start: () => sendJson<ValueWeekStatus>("POST", "/engagement/start"),
};
