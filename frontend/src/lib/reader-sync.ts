/**
 * The phone reader's way back: "mark read" and each concept tap, sent to the
 * backend when the phone can reach it, kept on the phone until it can.
 *
 * The reader is a static deployment and holds no credential, and nothing here
 * adds one. `NEXT_PUBLIC_READER_SYNC_URL` is the backend's tailnet origin
 * (e.g. `https://mac.tail1234.ts.net`): public, compiled into the bundle, and
 * useless off his tailnet. The request goes with `credentials: "omit"` and no
 * token; Tailscale Serve adds his identity header on the way in, and the
 * backend's `require_auth` accepts that (`backend/src/hq/api/reader.py`).
 *
 * Every event goes into an outbox in this page's storage first and leaves it
 * only once the backend has answered. So a phone off the tailnet, a Mac
 * asleep, or no sync URL at all loses nothing: the outbox is sent again on the
 * next page load and whenever the browser says it is back online. An event
 * the backend refuses outright (a page it has no lesson for, a malformed
 * body) is dropped, because sending it again cannot change the answer.
 *
 * Storage can be missing or refuse (private mode, a full quota), so every
 * access is guarded, with an in-memory outbox for this visit as the fallback.
 */

import {
  CONCEPT_RE,
  isConceptVerdict,
  type ConceptVerdict,
} from "@/lib/concept-taps";

export const READER_SYNC_URL = (
  process.env.NEXT_PUBLIC_READER_SYNC_URL ?? ""
).replace(/\/+$/u, "");

export type SyncEvent =
  | { id: string; kind: "read"; file: string; at: string }
  | {
      id: string;
      kind: "signal";
      file: string;
      concept: string;
      verdict: ConceptVerdict;
      at: string;
    };

/**
 * What a caller shows: stored by the backend, waiting in the outbox, or
 * refused by it (a page it has no lesson for), which no retry would change.
 */
export type SyncStatus = "saved" | "will sync" | "refused";

const OUTBOX_KEY = "hq:outbox";
const READ_PREFIX = "hq:read:";
const OUTBOX_MAX = 500;
const FILE_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,199}\.html$/u;

let memoryOutbox: SyncEvent[] = [];
const refusedIds = new Set<string>();

function newId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}

function isEvent(value: unknown): value is SyncEvent {
  if (typeof value !== "object" || value === null) return false;
  const e = value as Record<string, unknown>;
  if (typeof e.id !== "string" || typeof e.at !== "string") return false;
  if (typeof e.file !== "string" || !FILE_RE.test(e.file)) return false;
  if (e.kind === "read") return true;
  return (
    e.kind === "signal" &&
    typeof e.concept === "string" &&
    CONCEPT_RE.test(e.concept) &&
    isConceptVerdict(e.verdict)
  );
}

function loadOutbox(): SyncEvent[] {
  try {
    const raw = window.localStorage.getItem(OUTBOX_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter(isEvent) : [];
  } catch {
    return memoryOutbox;
  }
}

function saveOutbox(events: SyncEvent[]) {
  const kept = events.slice(-OUTBOX_MAX);
  memoryOutbox = kept;
  try {
    if (kept.length) window.localStorage.setItem(OUTBOX_KEY, JSON.stringify(kept));
    else window.localStorage.removeItem(OUTBOX_KEY);
  } catch {
    // Kept in memory for this visit only.
  }
}

/** One event per thing: a later tap on a concept replaces the earlier one. */
function sameThing(a: SyncEvent, b: SyncEvent): boolean {
  if (a.kind !== b.kind || a.file !== b.file) return false;
  return a.kind === "read" || (b.kind === "signal" && a.concept === b.concept);
}

function enqueue(event: SyncEvent) {
  saveOutbox([...loadOutbox().filter((e) => !sameThing(e, event)), event]);
}

function remove(id: string) {
  saveOutbox(loadOutbox().filter((e) => e.id !== id));
}

type Outcome = "sent" | "refused" | "unreachable";

async function post(event: SyncEvent): Promise<Outcome> {
  if (!READER_SYNC_URL) return "unreachable";
  const body =
    event.kind === "read"
      ? { file: event.file }
      : { file: event.file, concept: event.concept, verdict: event.verdict };
  try {
    const response = await fetch(`${READER_SYNC_URL}/api/reader/${event.kind}`, {
      method: "POST",
      credentials: "omit",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (response.ok) return "sent";
    // Not signed in (not on the tailnet as him), or the backend is busy or
    // broken: worth trying again later. Any other 4xx will say the same.
    if ([401, 403, 408, 429].includes(response.status) || response.status >= 500) {
      return "unreachable";
    }
    return "refused";
  } catch {
    return "unreachable"; // off the tailnet, asleep, or blocked by CORS
  }
}

let flushing: Promise<number> = Promise.resolve(0);

/**
 * Send the outbox, oldest first, stopping at the first event that cannot get
 * through. Resolves to how many are still waiting. Calls are queued one after
 * another, so two tabs of work never send the same event twice at once.
 */
export function flushOutbox(): Promise<number> {
  flushing = flushing.then(async () => {
    for (;;) {
      const next = loadOutbox()[0];
      if (!next) return 0;
      const outcome = await post(next);
      if (outcome === "unreachable") return loadOutbox().length;
      if (outcome === "refused") refusedIds.add(next.id);
      remove(next.id);
    }
  });
  return flushing;
}

async function send(event: SyncEvent): Promise<SyncStatus> {
  enqueue(event);
  await flushOutbox();
  if (loadOutbox().some((e) => e.id === event.id)) return "will sync";
  return refusedIds.has(event.id) ? "refused" : "saved";
}

export function sendRead(file: string): Promise<SyncStatus> {
  markedReadHere(file, true);
  return send({ id: newId(), kind: "read", file, at: new Date().toISOString() });
}

export function sendTap(
  file: string,
  concept: string,
  verdict: ConceptVerdict,
): Promise<SyncStatus> {
  return send({
    id: newId(),
    kind: "signal",
    file,
    concept,
    verdict,
    at: new Date().toISOString(),
  });
}

/** Did he mark this page read on this phone? Also records it when `set`. */
export function markedReadHere(file: string, set = false): boolean {
  try {
    if (set) window.localStorage.setItem(`${READ_PREFIX}${file}`, new Date().toISOString());
    return window.localStorage.getItem(`${READ_PREFIX}${file}`) !== null;
  } catch {
    return set;
  }
}
