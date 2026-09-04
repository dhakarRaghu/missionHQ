"use client";

import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { Moon, Sun } from "lucide-react";

import { cn } from "@/lib/utils";

// Two skins only: the warm light one the console is designed in, and a dark
// one stepped from the same hue. No "system" option, because the choice is
// part of the design rather than an OS preference to follow.
const MODES = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
] as const;

// The stored theme lives in this browser, so the control renders a placeholder
// until the client takes over. Reading "am I on the client yet" from an
// external store keeps it out of an effect.
const subscribeNever = () => () => {};
const onClient = () => true;
const onServer = () => false;

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(subscribeNever, onClient, onServer);

  if (!mounted) return <div className="h-7 w-[4.5rem]" aria-hidden />;

  return (
    <div
      role="group"
      aria-label="Theme"
      className="bg-muted/70 flex items-center rounded-lg p-0.5"
    >
      {MODES.map(({ value, label, Icon }) => {
        const active = (theme ?? "light") === value;
        return (
          <button
            key={value}
            type="button"
            aria-label={`${label} theme`}
            aria-pressed={active}
            onClick={() => setTheme(value)}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs transition-colors",
              active
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="size-3.5" aria-hidden />
            <span className="hidden sm:inline">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
