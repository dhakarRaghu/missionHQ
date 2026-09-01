"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bot,
  Inbox,
  LayoutList,
  ListChecks,
} from "lucide-react";

import { useHqEvents } from "@/hooks/use-hq-events";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/inbox", label: "Inbox", icon: Inbox },
  { href: "/board", label: "Board", icon: LayoutList },
  { href: "/runs", label: "Runs", icon: ListChecks },
  { href: "/feed", label: "Live feed", icon: Activity },
  { href: "/agents", label: "Agents", icon: Bot },
];

export function ConsoleShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { connected } = useHqEvents();

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-56 shrink-0 flex-col gap-1 border-r bg-sidebar p-4 md:flex">
        <div className="mb-6 px-2">
          <p className="text-sm font-semibold">Mission HQ</p>
          <p className="text-muted-foreground text-xs">personal agent console</p>
        </div>

        <nav className="flex flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-sidebar-accent/60",
                )}
              >
                <Icon className="size-4" aria-hidden />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto flex items-center gap-2 px-3 pt-4 text-xs">
          <span
            className={cn(
              "size-2 rounded-full",
              connected ? "bg-emerald-500" : "bg-muted-foreground/50",
            )}
            aria-hidden
          />
          <span className="text-muted-foreground">
            {connected ? "live" : "reconnecting"}
          </span>
        </div>
      </aside>

      <main className="min-w-0 flex-1 p-6 lg:p-8">{children}</main>
    </div>
  );
}
