import type { QueryClient } from "@tanstack/react-query";

import { qk } from "@/lib/api/client";
import { HQ_EVENT_TYPES, type HqEvent, type SseStatus } from "@/lib/api/types";
import {
  API_BASE as BASE,
  getToken,
  onUnauthorized,
  probeHealth,
  withToken,
} from "@/lib/auth";

/**
 * One EventSource for the whole console, started once from <Providers>.
 *
 * Events are written into the TanStack Query cache under qk.feed and
 * qk.sseStatus; components read them with useQuery. Each event type also
 * invalidates the query keys it affects, so the server stays the source of
 * truth. The browser reconnects on its own and sends Last-Event-ID, so no
 * manual retry timer is needed while the connection is alive. Only when the
 * browser gives up (readyState CLOSED, e.g. the backend was down) a fresh
 * connection is opened with since=<last seq>.
 *
 * Auth: EventSource cannot send headers, so the token goes in `?token=`.
 * EventSource also cannot report an HTTP status, so a `GET /health` probe
 * with the same token runs before every open. A 401 there sends the browser
 * to /login instead of opening a stream that would fail forever.
 */

const FEED_MAX = 200;
const RESTART_DELAY_MS = 5_000;

let source: EventSource | null = null;
let client: QueryClient | null = null;
let restartTimer: ReturnType<typeof setTimeout> | null = null;
/** Bumped on every open/stop so a stale probe result cannot open a stream. */
let openGeneration = 0;
let lastSeq = 0;
let everOpened = false;
let status: SseStatus = "connecting";

export function getSseStatus(): SseStatus {
  return status;
}

function setStatus(next: SseStatus) {
  status = next;
  client?.setQueryData<SseStatus>(qk.sseStatus, next);
}

function invalidateFor(queryClient: QueryClient, event: HqEvent) {
  const { type } = event;
  const inv = (queryKey: readonly unknown[]) =>
    queryClient.invalidateQueries({ queryKey });
  // The run detail page (timeline, tickets, transcript). Ticket events carry
  // no run_id, so those refresh every open detail page.
  const invRunDetail = () =>
    inv(event.run_id ? qk.runDetail(event.run_id) : ["run-detail"]);

  switch (type) {
    case "task.created":
    case "task.updated":
      inv(["tasks"]);
      inv(["task-events"]);
      break;
    case "run.started":
    case "run.finished":
    case "run.failed":
    case "run.no_artifact":
      inv(["runs"]);
      invRunDetail();
      inv(qk.costs);
      inv(qk.agents);
      inv(["tasks"]);
      if (type === "run.failed") inv(qk.health);
      if (type !== "run.started") {
        // A chat turn that outlived the HTTP wait lands in the transcript.
        inv(["chat-messages"]);
        inv(qk.chatSessions);
      }
      break;
    case "ticket.created":
    case "ticket.resolved":
    case "approval_resolved":
      inv(["tickets"]);
      inv(["tasks"]);
      invRunDetail();
      if (type === "ticket.resolved") {
        inv(["chat-messages"]);
        inv(qk.chatSessions);
      }
      break;
    case "tool.called":
    case "ledger":
    case "guardrail.denied":
    case "fact.recorded":
    case "fact.retired":
    case "policy.added":
      // Steps of a run in progress.
      invRunDetail();
      break;
    case "cron.caught_up":
      // A task was dispatched for a slot the machine slept through.
      inv(["tasks"]);
      break;
    case "vault.reindexed":
      inv(["vault"]);
      break;
    case "owner.action":
      // Value-week counters on the Inbox page.
      inv(["engagement"]);
      break;
    case "notify":
    case "notify_digested":
    case "digest":
    case "cron.missed":
    case "injection_detected":
    case "announce":
      // Feed-only events.
      break;
  }
}

function url(token: string | null) {
  const base =
    lastSeq > 0
      ? `${BASE}/events?since=${encodeURIComponent(String(lastSeq))}`
      : `${BASE}/events`;
  return withToken(base, token);
}

/** Probes auth, then connects. Does nothing if the stream was stopped or
 * another open won the race while the probe was in flight. */
function open(queryClient: QueryClient) {
  const generation = ++openGeneration;
  const token = getToken();
  void probeHealth(token).then((result) => {
    if (generation !== openGeneration) return; // stopped or restarted
    if (client !== queryClient || source !== null) return;
    if (result === "unauthorized") {
      setStatus("reconnecting");
      onUnauthorized();
      return;
    }
    // "unreachable": connect anyway; the CLOSED handler below retries.
    connect(queryClient, token);
  });
}

function connect(queryClient: QueryClient, token: string | null) {
  const es = new EventSource(url(token));
  source = es;

  const onEvent = (raw: MessageEvent<string>) => {
    let event: HqEvent;
    try {
      event = JSON.parse(raw.data) as HqEvent;
    } catch {
      return; // malformed frame
    }
    lastSeq = Math.max(lastSeq, event.seq);
    queryClient.setQueryData<HqEvent[]>(qk.feed, (prev) =>
      [event, ...(prev ?? [])].slice(0, FEED_MAX),
    );
    invalidateFor(queryClient, event);
  };

  for (const type of HQ_EVENT_TYPES) {
    es.addEventListener(type, onEvent);
  }

  es.onopen = () => {
    const reopened = everOpened;
    everOpened = true;
    setStatus("connected");
    // A reconnect can miss events the replay ring dropped: resync all reads.
    if (reopened) queryClient.invalidateQueries();
  };

  es.onerror = () => {
    if (source !== es) return; // stale handler after restart
    setStatus("reconnecting");
    if (es.readyState === EventSource.CLOSED) {
      // The browser will not retry a closed stream; open a new one later.
      es.close();
      source = null;
      restartTimer = setTimeout(() => {
        restartTimer = null;
        if (client === queryClient && source === null) open(queryClient);
      }, RESTART_DELAY_MS);
    }
  };
}

/** Cache-only query defaults. Must run when the QueryClient is created, before
 * any component renders, or the first render of useSseStatus/useFeed sees no
 * queryFn and TanStack logs a warning. */
export function installSseDefaults(queryClient: QueryClient): void {
  const cacheOnly = {
    staleTime: Infinity,
    gcTime: Infinity,
    refetchInterval: false as const,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  };
  queryClient.setQueryDefaults(qk.feed, {
    ...cacheOnly,
    queryFn: () => queryClient.getQueryData<HqEvent[]>(qk.feed) ?? [],
  });
  queryClient.setQueryDefaults(qk.sseStatus, {
    ...cacheOnly,
    queryFn: () => queryClient.getQueryData<SseStatus>(qk.sseStatus) ?? status,
  });
}

/** Starts the stream. Returns a stop function for the effect cleanup. */
export function startSse(queryClient: QueryClient): () => void {
  client = queryClient;
  setStatus(everOpened ? "reconnecting" : "connecting");
  if (!source) open(queryClient);

  return () => {
    openGeneration++; // cancel a probe still in flight
    if (restartTimer) clearTimeout(restartTimer);
    restartTimer = null;
    source?.close();
    source = null;
    client = null;
  };
}

/** Closes the current stream and opens a new one from the last seen seq. */
export function restartSse() {
  const queryClient = client;
  if (!queryClient) return;
  if (restartTimer) clearTimeout(restartTimer);
  restartTimer = null;
  source?.close();
  source = null;
  setStatus(everOpened ? "reconnecting" : "connecting");
  open(queryClient);
}
