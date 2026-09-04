# Mission HQ console: design rules

1. **Structure.** Routes live in `src/app/(console)/<view>/page.tsx`. Shared UI in `src/components/ui` (shadcn, do not hand-edit styles). Feature components in `src/components/features/<view>`. API client and types in `src/lib/api` (`client.ts`, `types.ts`). Hooks in `src/hooks`.
2. **No hard-coded CSS.** Colours, fonts and radii are CSS variables in `src/app/globals.css`, mapped in `@theme inline`. Components use Tailwind utilities and shadcn variants only. No palette classes such as `bg-amber-500`, no inline `style` for layout or colour.
3. **Rewrites, not CORS.** The browser calls the relative `/api/*` path. `next.config.ts` rewrites it to `BACKEND_ORIGIN` (server-only env var). `compress` is off so SSE frames pass through `next start`.
4. **TanStack Query plus one SSE stream.** Server data is read with `useQuery` and keys from `qk` in `client.ts`. One `EventSource` (`src/lib/sse.ts`, started from `providers.tsx`) writes the feed and connection status into the query cache and invalidates the keys each event affects. Polling is a fallback only while the stream is not connected.
5. **Seven views.** Inbox, Board, Runs, Live feed, Agents, Vault, Chat. Every list branches on loading, error (with Retry) and empty state, in that order.
6. **One page-level scrollbar.** `ConsoleShell` is exactly one viewport tall and its content area scrolls. Full-height views (Chat, Vault) use `flex min-h-0 flex-1 flex-col` and scroll their own panes with `.pane-scroll`.
7. **Layout primitives live in CSS.** Two-pane views use `.console-split` plus `.pane-narrow` or `.pane-wide` from `globals.css`, not arbitrary Tailwind grid templates. An arbitrary template such as `md:grid-cols-[18rem_minmax(0,1fr)]` silently failed to compile once and collapsed the Vault into one column.
8. **Time formatting.** Lists show relative time from `lib/time.ts` (`timeAgo`) with the exact value in a `title`. Detail views show the full timestamp.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
