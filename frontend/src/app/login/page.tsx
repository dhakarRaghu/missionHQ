import { Suspense } from "react";
import type { Metadata } from "next";

import { LoginForm } from "@/components/features/auth/login-form";

export const metadata: Metadata = { title: "Sign in · Mission HQ" };

// Outside the (console) group: no sidebar, no SSE stream, no data queries.
// The form reads ?next= with useSearchParams, so it needs a Suspense boundary
// for the static prerender.
export default function LoginPage() {
  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
