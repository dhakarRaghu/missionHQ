import { ApiError } from "@/lib/api/client";
import { API_BASE as BASE, authHeaders, onUnauthorized } from "@/lib/auth";

// GET/POST helpers for feature clients that live in their own file (vault.ts,
// evals.ts, engagement.ts, agents-admin.ts). Same contract as client.ts: the
// Authorization header on every call, a 401 sends the browser to /login, and
// errors surface FastAPI's {detail} first, the status text as fallback, never
// an HTML error page.

async function errorMessage(res: Response): Promise<string> {
  const json = (res.headers.get("content-type") ?? "").includes(
    "application/json",
  );
  if (json) {
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
  return res.statusText || `HTTP ${res.status}`;
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Accept: "application/json", ...authHeaders() },
  });
  if (!res.ok) {
    // Token missing or rejected: drop it and send the browser to /login.
    if (res.status === 401) onUnauthorized();
    throw new ApiError(res.status, await errorMessage(res));
  }
  return (await res.json()) as T;
}

/** POST/PUT with an optional JSON body. Same auth and error contract as getJson. */
export async function sendJson<T>(
  method: "POST" | "PUT",
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    if (res.status === 401) onUnauthorized();
    throw new ApiError(res.status, await errorMessage(res));
  }
  return (await res.json()) as T;
}

export function queryString(
  params: Record<string, string | number | undefined>,
) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
