"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  clearToken,
  probeAnonymousAccess,
  probeHealth,
  safeNext,
  setToken,
} from "@/lib/auth";

type Anonymous = "checking" | "open" | "closed";

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));

  const [token, setTokenInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [anonymous, setAnonymous] = useState<Anonymous>("checking");

  // Dev mode: the backend has no token configured and answers /health as is.
  useEffect(() => {
    let active = true;
    void probeAnonymousAccess().then((result) => {
      if (active) setAnonymous(result === "ok" ? "open" : "closed");
    });
    return () => {
      active = false;
    };
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = token.trim();
    if (!value) return;
    setBusy(true);
    setError(null);
    setToken(value);
    const result = await probeHealth(value);
    if (result === "ok") {
      router.push(next);
      return;
    }
    clearToken();
    setBusy(false);
    setError(
      result === "unauthorized"
        ? "Token rejected"
        : "Backend unreachable. Check NEXT_PUBLIC_API_BASE and try again.",
    );
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>Sign in to Mission HQ</CardTitle>
        <CardDescription>
          Enter the API token from <code>backend/.env</code> (
          <code>API_BEARER_TOKEN</code>). It is stored in this browser only.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <div className="flex flex-col gap-2">
            <Label htmlFor="api-token">API token</Label>
            <Input
              id="api-token"
              type="password"
              autoComplete="current-password"
              autoFocus
              value={token}
              onChange={(event) => setTokenInput(event.target.value)}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "api-token-error" : undefined}
              disabled={busy}
            />
            {error ? (
              <p
                id="api-token-error"
                role="alert"
                className="text-destructive text-sm"
              >
                {error}
              </p>
            ) : null}
          </div>
          <Button type="submit" disabled={busy || token.trim() === ""}>
            {busy ? "Checking…" : "Sign in"}
          </Button>
        </form>

        {anonymous === "open" ? (
          <div className="flex flex-col gap-2 border-t pt-4">
            <p className="text-muted-foreground text-sm">
              This backend accepts requests without a token (no
              <code> API_BEARER_TOKEN</code> configured).
            </p>
            <Button
              type="button"
              variant="outline"
              onClick={() => router.push(next)}
            >
              Continue without a token
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
