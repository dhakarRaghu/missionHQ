"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  Briefcase,
  GraduationCap,
  House,
  LayoutList,
  Lightbulb,
  ListChecks,
  LogOut,
  MessageSquare,
  NotebookText,
  Settings,
  Wrench,
} from "lucide-react";

import { ThemeToggle } from "@/components/theme-toggle";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useSseStatus } from "@/hooks/use-hq-events";
import { useHasToken } from "@/components/features/auth/use-has-token";
import { api, qk } from "@/lib/api/client";
import { clearToken, loginUrl } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/home", label: "Home", icon: House },
  { href: "/board", label: "Board", icon: LayoutList },
  { href: "/jobs", label: "Jobs", icon: Briefcase },
  { href: "/ideas", label: "Ideas", icon: Lightbulb },
  { href: "/learn", label: "Learn", icon: GraduationCap },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/vault", label: "Memory", icon: NotebookText },
  { href: "/runs", label: "Runs", icon: ListChecks },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/tools", label: "Tools", icon: Wrench },
  { href: "/settings", label: "Settings", icon: Settings },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

/** Label of the section the user is in. Drives the header title. */
function currentLabel(pathname: string): string {
  return (
    NAV.find((item) => isActive(pathname, item.href))?.label ?? "Mission HQ"
  );
}

/**
 * Live/reconnecting indicator for the event stream. It sits in the header
 * because a dropped stream means the page has stopped updating itself, which
 * the user needs to see without scrolling to a corner.
 */
function ConnectionDot() {
  const status = useSseStatus();
  const connected = status === "connected";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="text-muted-foreground flex items-center gap-1.5 text-xs">
          <span
            className={cn(
              "size-1.5 rounded-full transition-colors",
              connected
                ? "bg-status-success"
                : "bg-status-blocked motion-safe:animate-pulse",
            )}
            aria-hidden
          />
          <span className="hidden sm:inline">
            {connected ? "live" : status}
          </span>
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {connected
          ? "Connected to the event stream. This page updates itself."
          : "The event stream is not connected. Pages may be out of date."}
      </TooltipContent>
    </Tooltip>
  );
}

/** Bottom nav entry. Rendered only when a token is stored in this browser. */
function SignOutItem() {
  const router = useRouter();
  const signedIn = useHasToken();
  if (!signedIn) return null;

  const signOut = () => {
    clearToken();
    router.push(loginUrl());
  };
  return (
    <SidebarMenuItem>
      <SidebarMenuButton onClick={signOut} size="sm">
        <LogOut aria-hidden />
        <span>Sign out</span>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

/**
 * The roster, with what each agent is doing right now.
 *
 * A list of agent names is not worth the space; a list that says which of them
 * is working, idle or paused is the fastest answer to "is my system alive".
 * Running state is derived from the tasks the board already loads, so this
 * costs no extra request.
 */
function AgentRoster({ pathname }: { pathname: string }) {
  const agents = useQuery({ queryKey: qk.agents, queryFn: api.agents });
  const tasks = useQuery({ queryKey: qk.tasks(), queryFn: () => api.tasks() });

  const running = new Set(
    (tasks.data ?? [])
      .filter((task) => task.status === "running")
      .map((task) => task.agent),
  );
  const rows = agents.data ?? [];
  if (!rows.length) return null;
  const workingCount = rows.filter(
    (agent) => !agent.paused && running.has(agent.name),
  ).length;

  return (
    <SidebarGroup>
      <SidebarGroupLabel className="flex justify-between">
        <span>Your agents {rows.length}</span>
        <span>{workingCount ? `${workingCount} working` : "all idle"}</span>
      </SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {rows.map((agent) => {
            const href = `/agents/${encodeURIComponent(agent.name)}`;
            const state = agent.paused
              ? "paused"
              : running.has(agent.name)
                ? "working"
                : "idle";
            return (
              <SidebarMenuItem key={agent.name}>
                <SidebarMenuButton
                  asChild
                  size="sm"
                  isActive={pathname === href}
                  tooltip={agent.description}
                >
                  <Link href={href}>
                    <span
                      aria-hidden
                      className={cn(
                        "size-1.5 shrink-0 rounded-full",
                        state === "working" &&
                          "bg-status-success motion-safe:animate-pulse",
                        state === "paused" && "bg-status-blocked",
                        state === "idle" && "bg-status-muted",
                      )}
                    />
                    <span className="truncate">{agent.name}</span>
                    <span className="text-muted-foreground ml-auto text-xs">
                      {state === "idle" ? "" : state}
                    </span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            );
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

/** Shown when the backend kill switch is on. Polled; SSE may be down too. */
function HaltedBanner() {
  const { data } = useQuery({
    queryKey: qk.health,
    queryFn: api.health,
    refetchInterval: 30_000,
  });
  if (!data?.halted) return null;
  return (
    <div
      role="alert"
      className="bg-status-danger/15 text-status-danger shrink-0 border-b px-4 py-2 text-sm font-medium"
    >
      Halted: the kill switch is on. No agent will start a run until it is
      cleared on the backend.
    </div>
  );
}

/**
 * Sidebar, header and scrolling content area.
 *
 * The shell owns the only page-level scrollbar: the frame is exactly one
 * viewport tall and the content area scrolls. Views that need to fill the
 * height (chat, vault) use `flex-1 min-h-0` and scroll their own panes.
 */
/** Views that fill the viewport and scroll their own panes. */
const FULL_HEIGHT = ["/chat", "/vault", "/learn"];

export function ConsoleShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const fillsHeight = FULL_HEIGHT.some((href) => pathname.startsWith(href));
  // Pending approvals are the only count that means "you are the blocker",
  // so the Inbox entry carries it and nothing else does.
  const tickets = useQuery({
    queryKey: qk.tickets("pending"),
    queryFn: () => api.tickets("pending"),
  });
  const pending = tickets.data?.length ?? 0;

  return (
    <SidebarProvider>
      <Sidebar collapsible="offcanvas">
        <SidebarHeader className="p-3">
          <div className="bg-sidebar-accent/60 rounded-lg border px-3 py-2">
            <p className="text-sm font-semibold">Mission HQ</p>
            <p className="text-muted-foreground text-xs">
              personal agent console
            </p>
          </div>
        </SidebarHeader>

        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <nav aria-label="Console">
                <SidebarMenu>
                  {NAV.map(({ href, label, icon: Icon }) => {
                    const active = isActive(pathname, href);
                    return (
                      <SidebarMenuItem key={href}>
                        <SidebarMenuButton asChild isActive={active}>
                          <Link
                            href={href}
                            aria-current={active ? "page" : undefined}
                          >
                            <Icon aria-hidden />
                            <span>{label}</span>
                          </Link>
                        </SidebarMenuButton>
                        {href === "/home" && pending > 0 ? (
                          <SidebarMenuBadge className="text-status-approval">
                            {pending}
                          </SidebarMenuBadge>
                        ) : null}
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </nav>
            </SidebarGroupContent>
          </SidebarGroup>

          <AgentRoster pathname={pathname} />
        </SidebarContent>

        <SidebarFooter className="pb-3">
          <SidebarMenu>
            <SignOutItem />
          </SidebarMenu>
        </SidebarFooter>
      </Sidebar>

      <SidebarInset className="flex h-svh min-h-0 flex-col overflow-hidden">
        <header className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
          <SidebarTrigger aria-label="Toggle navigation" />
          <span className="text-sm font-medium">{currentLabel(pathname)}</span>
          <div className="ml-auto flex items-center gap-3">
            <ConnectionDot />
            <ThemeToggle />
          </div>
        </header>
        <HaltedBanner />
        {/* Two shapes, chosen by the route.
            A normal page grows with its content: the wrapper is min-h-full so
            its bottom padding still sits under the last row, and this
            container scrolls.
            A full-height view (chat, memory) must instead give its panes a
            definite height to scroll inside. That needs h-full, not
            min-h-full: with a minimum the flex basis stays indefinite, the
            panes grow to their content, and the page header is pushed off
            screen. This container then never scrolls. */}
        <div
          className={cn(
            "min-h-0 flex-1",
            fillsHeight ? "overflow-hidden" : "overflow-y-auto",
          )}
        >
          {/* A full-height view scrolls inside its own panes, so generous page
              padding only shrinks the pane. On a 13-inch screen the header bar,
              this padding and the old page title together cost about an eighth
              of the usable height, which is why chat felt cramped. */}
          <div
            className={cn(
              "mx-auto flex w-full max-w-7xl min-w-0 flex-col",
              fillsHeight ? "h-full p-3 lg:p-4" : "min-h-full p-5 lg:p-7",
            )}
          >
            {children}
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
