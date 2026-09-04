"use client";

import { useSyncExternalStore } from "react";

/**
 * Accent colour, kept separate from light/dark.
 *
 * next-themes owns light/dark through a class on <html>. The accent is a
 * second, independent axis written as data-accent on the same element, so the
 * two combine: any accent works in either mode. The value lives in
 * localStorage because it is a per-browser preference, not server state.
 */
export const ACCENTS = [
  { value: "neutral", label: "Neutral accent" },
  { value: "blue", label: "Blue accent" },
  { value: "green", label: "Green accent" },
  { value: "amber", label: "Amber accent" },
] as const;

export type Accent = (typeof ACCENTS)[number]["value"];

const STORAGE_KEY = "hq.accent";
const DEFAULT: Accent = "neutral";

function isAccent(value: string | null): value is Accent {
  return ACCENTS.some((option) => option.value === value);
}

/** Reads the stored accent. Returns the default when storage is unavailable. */
function readStored(): Accent {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return isAccent(value) ? value : DEFAULT;
  } catch {
    return DEFAULT;
  }
}

export function applyAccent(accent: Accent) {
  document.documentElement.dataset.accent = accent;
}

// The accent is external state (a DOM attribute plus localStorage), so it is
// read with useSyncExternalStore rather than mirrored into an effect. The
// inline script in layout.tsx has already applied it before hydration.
let current: Accent | null = null;
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): Accent {
  if (current === null) current = readStored();
  return current;
}

/** The server cannot know this browser's choice, so it renders the default. */
function getServerSnapshot(): Accent {
  return DEFAULT;
}

function setAccentValue(next: Accent) {
  current = next;
  applyAccent(next);
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // A browser with site data blocked still gets the accent for this page.
  }
  for (const listener of listeners) listener();
}

/** Current accent and a setter that persists and applies it at once. */
export function useAccent(): [Accent, (next: Accent) => void] {
  const accent = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return [accent, setAccentValue];
}
