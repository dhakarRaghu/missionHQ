/**
 * "Got it" / "Lost me", per concept, from inside a lesson frame.
 *
 * The lesson page runs in a sandboxed frame with no same-origin, and its own
 * content policy blocks every request, so it cannot store or send a tap. It
 * posts `{hq: "concept", concept, verdict}` to the window around it instead
 * (`backend/src/hq/lesson_kit.py`, `KIT_TAPS_JS`). The page is model-written
 * markup, so the message is data: it is accepted only from the frame the page
 * rendered (`useConceptTaps`), and only when the concept is `c1`..`c99` and
 * the verdict one of two words. Anything else is dropped without a word.
 *
 * The reply goes the other way: once the frame says it is ready, and again
 * whenever the answers change, the outer page tells it what he chose so the
 * buttons show it.
 */

export type ConceptVerdict = "got_it" | "lost_me";

export type ConceptTap = { concept: string; verdict: ConceptVerdict };

export const VERDICT_LABEL: Record<ConceptVerdict, string> = {
  got_it: "Got it",
  lost_me: "Lost me",
};

export const CONCEPT_RE = /^c\d{1,2}$/u;

export function isConceptVerdict(value: unknown): value is ConceptVerdict {
  return value === "got_it" || value === "lost_me";
}

/** A tap out of a frame message, or null when it is not one. */
export function parseTap(data: unknown): ConceptTap | null {
  if (typeof data !== "object" || data === null) return null;
  const message = data as Record<string, unknown>;
  if (message.hq !== "concept") return null;
  const { concept, verdict } = message;
  if (typeof concept !== "string" || !CONCEPT_RE.test(concept)) return null;
  if (!isConceptVerdict(verdict)) return null;
  return { concept, verdict };
}

/** The frame's "my buttons exist, tell me what he chose". */
export function isFrameReady(data: unknown): boolean {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as Record<string, unknown>).hq === "concept-ready"
  );
}

export function tellFrame(
  frame: Window,
  verdicts: Record<string, ConceptVerdict>,
) {
  // The frame's origin is opaque, so "*" is the only target that reaches it.
  // What goes is his own answers, nothing else.
  frame.postMessage({ hq: "concept-state", verdicts }, "*");
}

/** Concepts in reading order: c2 before c10. */
export function byConcept(a: string, b: string): number {
  return Number(a.slice(1)) - Number(b.slice(1));
}
