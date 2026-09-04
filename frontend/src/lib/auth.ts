// API token handling for the console.
//
// Two deployment modes:
// - Dev: NEXT_PUBLIC_API_BASE is unset (relative "/api"), next.config.ts
//   rewrites it to the backend, and the backend usually has no token set.
// - Remote (Vercel): NEXT_PUBLIC_API_BASE is an absolute URL and the backend
//   requires `Authorization: Bearer <token>` (or `?token=` for EventSource).
//
// The token lives in localStorage under `hq.token`. Every helper is safe to
// call during SSR: without `window` there is no token.

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

const STORAGE_KEY = "hq.token";
const LOGIN_PATH = "/login";
const DEFAULT_NEXT = "/inbox";

/** True when the browser talks to a different origin (Vercel mode). */
export function hasRemoteApi(): boolean {
  return /^https?:\/\//i.test(API_BASE);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value && value.length > 0 ? value : null;
  } catch {
    return null;
  }
}

const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

/**
 * Subscribe to token changes in this tab (setToken/clearToken) and in other
 * tabs (the `storage` event). Shaped for React's useSyncExternalStore.
 */
export function subscribeToken(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === STORAGE_KEY) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, token);
  } catch {
    // Storage blocked (private mode, quota). The session simply stays signed out.
  }
  notify();
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
  notify();
}

/** `Authorization` header for fetch, or an empty object without a token. */
export function authHeaders(token: string | null = getToken()): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Appends `token=<token>` to a URL. EventSource cannot send headers, so the
 * SSE stream is the only caller. Returns the URL unchanged without a token.
 */
export function withToken(url: string, token: string | null = getToken()): string {
  if (!token) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(token)}`;
}

/** Only same-site paths are valid `next` targets (no open redirect). */
export function safeNext(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return DEFAULT_NEXT;
  if (raw.startsWith(LOGIN_PATH)) return DEFAULT_NEXT;
  return raw;
}

export function loginUrl(next?: string): string {
  const target = safeNext(next);
  return target === DEFAULT_NEXT
    ? LOGIN_PATH
    : `${LOGIN_PATH}?next=${encodeURIComponent(target)}`;
}

let redirecting = false;

/**
 * Full navigation to /login, at most once per page load and never from the
 * login page itself. Used by the fetch helpers that run outside React.
 */
export function redirectToLogin(): void {
  if (typeof window === "undefined" || redirecting) return;
  const { pathname, search } = window.location;
  if (pathname.startsWith(LOGIN_PATH)) return;
  redirecting = true;
  window.location.assign(loginUrl(`${pathname}${search}`));
}

/** Shared 401 handling for client.ts, request.ts and sse.ts. */
export function onUnauthorized(): void {
  clearToken();
  redirectToLogin();
}

export type HealthProbe = "ok" | "unauthorized" | "unreachable";

/**
 * Lightweight `GET /health` with the given token. Distinguishes a rejected
 * token (401) from a backend that is down. Never throws.
 */
export async function probeHealth(
  token: string | null = getToken(),
): Promise<HealthProbe> {
  try {
    const res = await fetch(`${API_BASE}/health`, {
      headers: { Accept: "application/json", ...authHeaders(token) },
      cache: "no-store",
    });
    if (res.status === 401) return "unauthorized";
    return res.ok ? "ok" : "unreachable";
  } catch {
    return "unreachable";
  }
}

let anonymousProbe: Promise<HealthProbe> | null = null;

/**
 * Does the backend accept requests without a token? Probed once per browser
 * session. An unreachable backend is not cached so a later call retries.
 */
export function probeAnonymousAccess(): Promise<HealthProbe> {
  if (!anonymousProbe) {
    anonymousProbe = probeHealth(null).then((result) => {
      if (result === "unreachable") anonymousProbe = null;
      return result;
    });
  }
  return anonymousProbe;
}
