"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";

import { TooltipProvider } from "@/components/ui/tooltip";

import { useHasToken } from "@/components/features/auth/use-has-token";
import { useSseStatus } from "@/hooks/use-hq-events";
import { hasRemoteApi, loginUrl, probeAnonymousAccess } from "@/lib/auth";
import { getSseStatus, installSseDefaults, startSse } from "@/lib/sse";

const FALLBACK_POLL_MS = 60_000;
const LOGIN_PATH = "/login";
// The phone reader. It is the one route that is not the console: it reads
// static files under /reader that were committed with the deployment, so
// there is no backend to stream from and no token to hold. Guarding it would
// bounce him to a login page for a backend his phone cannot reach.
const READER_PATH = "/read";

function makeQueryClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        refetchOnWindowFocus: true,
        // SSE is the fast path. Poll only while the stream is not connected.
        // TanStack re-evaluates this function on every query state change.
        refetchInterval: () =>
          getSseStatus() === "connected" ? false : FALLBACK_POLL_MS,
      },
    },
  });
  installSseDefaults(client);
  return client;
}

/** Opens the single SSE stream and re-arms fallback polling on status change. */
function SseBridge({ client }: { client: QueryClient }) {
  const status = useSseStatus();
  const pathname = usePathname();
  const offline =
    pathname.startsWith(LOGIN_PATH) || pathname.startsWith(READER_PATH);

  useEffect(() => {
    // No stream on the login page: there is no token to send yet. None on the
    // reader either: it has no backend behind it.
    if (offline) return;
    return startSse(client);
  }, [client, offline]);

  useEffect(() => {
    // Marking queries invalid without a refetch makes every active observer
    // re-run the refetchInterval function above. No network request happens.
    client.invalidateQueries({ refetchType: "none" });
  }, [client, status]);

  return null;
}

/**
 * Route guard. Without a stored token, asks the backend once per session
 * whether it accepts anonymous requests (dev mode). If it answers 401 the
 * browser goes to /login. With a remote API the console stays hidden until
 * that check is done so no request fires with a missing token.
 */
function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const onLogin = pathname.startsWith(LOGIN_PATH);
  const onReader = pathname.startsWith(READER_PATH);
  const hasToken = useHasToken();
  // Set only from the probe callback. "unreachable" also counts as open so
  // the console renders its own error states with Retry.
  const [anonymousOpen, setAnonymousOpen] = useState(false);

  useEffect(() => {
    if (onLogin || onReader || hasToken) return;
    let active = true;
    void probeAnonymousAccess().then((result) => {
      if (!active) return;
      if (result === "unauthorized") {
        router.replace(loginUrl(`${pathname}${window.location.search}`));
        return;
      }
      setAnonymousOpen(true);
    });
    return () => {
      active = false;
    };
  }, [onLogin, onReader, hasToken, pathname, router]);

  // Dev mode (relative /api) renders at once, as before. A remote API waits
  // for a token or the probe so no request fires with a missing token.
  const ready =
    !hasRemoteApi() || onLogin || onReader || hasToken || anonymousOpen;
  return ready ? children : null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(makeQueryClient);
  return (
    // Two skins, no system option: light is the designed default and the
    // header toggle switches to dark. next-themes remembers the choice.
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <QueryClientProvider client={client}>
        <TooltipProvider delayDuration={200}>
          <SseBridge client={client} />
          <AuthGuard>{children}</AuthGuard>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
