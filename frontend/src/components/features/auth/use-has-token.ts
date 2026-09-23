"use client";

import { useSyncExternalStore } from "react";

import { getToken, subscribeToken } from "@/lib/auth";

const getSnapshot = () => getToken() !== null;
// localStorage does not exist on the server: prerender as signed out.
const getServerSnapshot = () => false;

/** True while a token is stored in this browser. Hydration-safe. */
export function useHasToken(): boolean {
  return useSyncExternalStore(subscribeToken, getSnapshot, getServerSnapshot);
}
