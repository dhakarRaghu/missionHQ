"use client";

import { useEffect, useRef, type RefObject } from "react";

import {
  isFrameReady,
  parseTap,
  tellFrame,
  type ConceptTap,
  type ConceptVerdict,
} from "@/lib/concept-taps";

/**
 * Listen for "Got it" / "Lost me" taps from one lesson frame, and keep that
 * frame's buttons showing `verdicts`.
 *
 * A message counts only when it comes from `frame`'s own window: any other
 * frame, tab or extension posting the same shape is ignored. `onTap` receives
 * validated taps only (see `parseTap`).
 */
export function useConceptTaps(
  frame: RefObject<HTMLIFrameElement | null>,
  verdicts: Record<string, ConceptVerdict>,
  onTap: (tap: ConceptTap) => void,
) {
  const onTapRef = useRef(onTap);
  const verdictsRef = useRef(verdicts);
  useEffect(() => {
    onTapRef.current = onTap;
    verdictsRef.current = verdicts;
  });

  useEffect(() => {
    function listen(event: MessageEvent) {
      const own = frame.current?.contentWindow;
      if (!own || event.source !== own) return;
      if (isFrameReady(event.data)) {
        tellFrame(own, verdictsRef.current);
        return;
      }
      const tap = parseTap(event.data);
      if (tap) onTapRef.current(tap);
    }
    window.addEventListener("message", listen);
    return () => window.removeEventListener("message", listen);
  }, [frame]);

  useEffect(() => {
    const own = frame.current?.contentWindow;
    if (own) tellFrame(own, verdicts);
  }, [frame, verdicts]);
}
