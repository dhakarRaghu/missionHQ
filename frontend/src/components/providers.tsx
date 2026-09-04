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
  const onLogin = pathname.startsWith(LOGIN_PATH);

  useEffect(() => {
    // No stream on the login page: there is no token to send yet.
    if (onLogin) return;
    return startSse(client);
  }, [client, onLogin]);

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
  const hasToken = useHasToken();
  // Set only from the probe callback. "unreachable" also counts as open so
  // the console renders its own error states with Retry.
  const [anonymousOpen, setAnonymousOpen] = useState(false);

  useEffect(() => {
    if (onLogin || hasToken) return;
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
  }, [onLogin, hasToken, pathname, router]);

  // Dev mode (relative /api) renders at once, as before. A remote API waits
  // for a token or the probe so no request fires with a missing token.
  const ready = !hasRemoteApi() || onLogin || hasToken || anonymousOpen;
  return ready ? children : null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(makeQueryClient);
  return (
    // Light is the designed default; the header toggle offers dark and system,
    // and next-themes remembers the choice per browser.
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem>
      <QueryClientProvider client={client}>
        <TooltipProvider delayDuration={200}>
          <SseBridge client={client} />
          <AuthGuard>{children}</AuthGuard>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
