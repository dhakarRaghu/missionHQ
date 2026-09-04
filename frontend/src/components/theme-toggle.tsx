"use client";

import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { Monitor, Moon, Sun } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ACCENTS, type Accent, useAccent } from "@/lib/accent";
import { cn } from "@/lib/utils";

const MODES = [
  { value: "system", label: "System theme", Icon: Monitor },
  { value: "light", label: "Light theme", Icon: Sun },
  { value: "dark", label: "Dark theme", Icon: Moon },
] as const;

// Both settings live in this browser, not on the server, so the control
// renders a placeholder until the client takes over. Reading "am I on the
// client yet" from an external store keeps it out of an effect.
const subscribeNever = () => () => {};
const onClient = () => true;
const onServer = () => false;

/** Light / dark / system, plus an accent colour. */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [accent, setAccent] = useAccent();
  const mounted = useSyncExternalStore(subscribeNever, onClient, onServer);

  if (!mounted) return <div className="h-7 w-[7.5rem]" aria-hidden />;

  return (
    <div className="flex items-center gap-2">
      <div
        role="group"
        aria-label="Colour theme"
        className="bg-muted/60 flex items-center gap-0.5 rounded-lg p-0.5"
      >
        {ACCENTS.map((option) => (
          <Tooltip key={option.value}>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={option.label}
                aria-pressed={accent === option.value}
                onClick={() => setAccent(option.value as Accent)}
                data-accent-swatch={option.value}
                className={cn(
                  "size-4 rounded-full border transition-transform",
                  accent === option.value
                    ? "border-foreground scale-110"
                    : "border-transparent hover:scale-110",
                )}
              />
            </TooltipTrigger>
            <TooltipContent>{option.label}</TooltipContent>
          </Tooltip>
        ))}
      </div>

      <div
        role="group"
        aria-label="Light or dark"
        className="bg-muted/60 flex items-center rounded-lg p-0.5"
      >
        {MODES.map(({ value, label, Icon }) => {
          const active = (theme ?? "system") === value;
          return (
            <Tooltip key={value}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label={label}
                  aria-pressed={active}
                  onClick={() => setTheme(value)}
                  className={cn(
                    "rounded-md p-1 transition-colors",
                    active
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <Icon className="size-3.5" aria-hidden />
                </button>
              </TooltipTrigger>
              <TooltipContent>{label}</TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}
