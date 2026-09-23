import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * The gate in front of the deployment.
 *
 * He did not want Vercel's Deployment Protection: "let it authenticate, same
 * as API_BEARER_TOKEN, I will add the env variable in Vercel." So the app
 * carries its own gate, and `READER_PASSWORD` is its only credential.
 *
 * It runs here, in the proxy, rather than in a React component, and that is
 * the whole point. The lessons are static files: `/reader/index.json` and
 * `/reader/lessons/<slug>.html` are fetchable on their own, and a gate drawn
 * in the page would leave both wide open. This runs before any route or file
 * is served, with no matcher, so it covers the pages, the JSON, the lesson
 * HTML and the build output alike.
 *
 * The secret is read from `process.env` on the server. It must NOT be named
 * `NEXT_PUBLIC_*`: those are compiled into the JavaScript the browser
 * downloads, so a password in one is published, not checked.
 *
 * Unset means no gate, which is what his own machine wants: `next start` on
 * localhost behind the console, and `next dev`, both stay as they were.
 */

const REALM = 'Basic realm="Mission HQ", charset="UTF-8"';

/** Compare without leaking the answer through how long it took. */
function sameSecret(given: string, expected: string): boolean {
  if (given.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < given.length; i++) {
    diff |= given.charCodeAt(i) ^ expected.charCodeAt(i);
  }
  return diff === 0;
}

/** The password out of an `Authorization: Basic` header, or "". */
function passwordFrom(header: string | null): string {
  if (!header?.startsWith("Basic ")) return "";
  try {
    // Any user name is accepted; the password is the whole credential, so
    // there is nothing extra for him to remember on a phone keyboard.
    const decoded = atob(header.slice(6).trim());
    const colon = decoded.indexOf(":");
    return colon === -1 ? "" : decoded.slice(colon + 1);
  } catch {
    return "";
  }
}

/**
 * Is this a deployment that has no backend behind it?
 *
 * Vercel sets `VERCEL` on its own. A console there can still be real — that
 * is section 11 of the deploy guide, where `NEXT_PUBLIC_API_BASE` points at a
 * backend on a VPS. With no API base there is nothing for the console to
 * talk to, so every console view is a spinner that never resolves: he opened
 * `/courses` and got "HTTP 404", then `/learn` and got empty boxes, because
 * the `/api/*` rewrite lands on the function's own localhost.
 *
 * Nothing new to configure: his machine has no `VERCEL`, and a real console
 * on Vercel has the API base.
 */
const readerOnly =
  Boolean(process.env.VERCEL) && !process.env.NEXT_PUBLIC_API_BASE;

/** Paths that must answer for themselves on a reader-only deployment. */
function servesItself(path: string): boolean {
  return (
    path === "/read" ||
    path.startsWith("/read/") ||
    path.startsWith("/reader/") ||
    path.startsWith("/_next/") ||
    path === "/favicon.ico" ||
    path === "/robots.txt"
  );
}

export function proxy(request: NextRequest) {
  const expected = process.env.READER_PASSWORD ?? "";
  const path = request.nextUrl.pathname;

  if (expected) {
    const given = passwordFrom(request.headers.get("authorization"));
    if (!sameSecret(given, expected)) return askForPassword();
  }

  // Send the console's routes to the one view that works here, rather than
  // leaving him on a page that will never fill in.
  if (readerOnly && !servesItself(path)) {
    return NextResponse.redirect(new URL("/read", request.url));
  }

  return NextResponse.next();
}

function askForPassword() {
  return new NextResponse("Mission HQ — sign in to read.", {
    status: 401,
    headers: {
      "WWW-Authenticate": REALM,
      "Content-Type": "text/plain; charset=utf-8",
      // Nothing behind this gate should sit in a shared cache.
      "Cache-Control": "no-store",
    },
  });
}
