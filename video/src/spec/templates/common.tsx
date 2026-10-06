import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { continueRender, delayRender, getInputProps, useCurrentFrame } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadCaveat } from "@remotion/google-fonts/Caveat";
import { loadFont as loadJBMono } from "@remotion/google-fonts/JetBrainsMono";
import { Appear, C, SketchRect, font, hand, prog, theme, type BeatT } from "../../kit-sketch/visuals";
import type { Panel, Tone, TimingBeat } from "../types";

// Shared pieces for the spec templates: tones, timing lookups, the fit box, inline highlighter.

export const RED = "#E03131";
export const AMBER = "#E8890C";

export const TONE: Record<Tone, string> = {
  ink: theme.ink,
  ok: C.ok,
  bad: RED,
  warn: AMBER,
  info: C.router,
  accent: C.cascade,
};

const PASTEL: Record<Tone, string> = {
  ink: "#F1F3F5",
  ok: "#D3F9D8",
  bad: "#FFE3E3",
  warn: "#FFF3BF",
  info: "#D0EBFF",
  accent: "#FFE8CC",
};

export const toneColor = (t?: Tone) => TONE[t ?? "ink"];
export const tonePastel = (t?: Tone) => PASTEL[t ?? "ink"];

/** Frames between `at` and the moment the voice starts the line: elements keyed to a line land in this window. */
export const LEAD = 0;

/**
 * Resolves when the kit's three web fonts have loaded (same families, weights and subsets as
 * kit-sketch/visuals.tsx, so these calls reuse its downloads). FitBox measures only after this.
 */
const fontsReady = Promise.all([
  loadInter("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).waitUntilDone(),
  loadCaveat("normal", { weights: ["500", "600", "700"], subsets: ["latin"] }).waitUntilDone(),
  loadJBMono("normal", { weights: ["400", "500", "700"], subsets: ["latin"] }).waitUntilDone(),
]).then(() => document.fonts.ready);

// ---------------------------------------------------------------- timing

/** The kit's beat shape (captions) from a timing-file beat (cues). */
export const toBeatT = (b: TimingBeat): BeatT => ({
  id: b.id,
  start: b.start,
  end: b.end,
  steps: b.steps.map((s) => ({ key: s.key, at: s.at })),
  captions: b.cues,
});

export type K = (key: string) => number;

/** Local frame of a line key in a beat. Unknown keys throw: check-spec.mjs rejects them before a render. */
export const keyFrame = (b: TimingBeat): K => (key: string) => {
  const s = b.steps.find((x) => x.key === key);
  if (!s) throw new Error(`Narration key "${key}" is missing in beat "${b.id}"`);
  return s.at;
};

/** Text of every narration line whose key starts with `letter` followed by a digit, in order. */
export const linesOf = (b: TimingBeat, letter: string) =>
  b.steps.filter((s) => new RegExp(`^${letter}[0-9]`).test(s.key));

/** First frame of the lines with this letter, or null when the beat has none. */
export const firstOf = (b: TimingBeat, letter: string): number | null => {
  const l = linesOf(b, letter);
  return l.length ? l[0].at : null;
};

/** Every `at` key a panel uses, in document order. */
export const panelKeys = (p: Panel): string[] => {
  switch (p.kind) {
    case "chips": return p.items.map((x) => x.at);
    case "flow": return p.nodes.map((x) => x.at);
    case "stats": return p.items.map((x) => x.at);
    case "bars": return p.items.map((x) => x.at);
    case "table": return p.rows.map((x) => x.at);
    case "equation": return p.lines.map((x) => x.at);
    case "compare": return [p.at_left, p.at_right];
    case "prompt": return p.lines.map((x) => x.at);
  }
};

/** The frame of a panel's first element: the panel's border, caption and note all appear with it. */
export const panelStart = (p: Panel, k: K) => Math.min(...panelKeys(p).map(k));

// ---------------------------------------------------------------- fit box

/**
 * Debug only: with `debugFit: true` in the input props, every FitBox logs one line per render,
 * "FIT {...}": its scale, its box, the visible content rectangle, whether it overflows, and the
 * smallest on-screen font size of each text kind marked with `data-ty` (body, sec, note).
 */
const DEBUG_FIT = (() => {
  try { return Boolean((getInputProps() as { debugFit?: boolean }).debugFit); } catch { return false; }
})();

/**
 * Lays its children out and scales them to fit `w` x `h`: down until they fit, and up to `grow` when
 * they are small. The templates pick their sizes from the box and the longest text; the scale is the
 * safety net for long text and the way short content fills its box.
 * - `reflow`: the content wraps to the scaled width (w / scale), so only the height limits the scale.
 *   Use it for text that may wrap anywhere (lists, recap); never for nowrap text.
 * - `hug`: the box is as tall as the scaled content instead of `h`, so a parent can place or group it.
 * - `valign: "center"`: the content sits in the middle of the box height.
 * - `fill`: growing stops when the content is this share of `h` tall (shrinking still uses all of `h`).
 * Measures after the fonts load, so the scale is the same in every render tab. Content must keep the
 * same size on every frame (animate opacity, not presence), or the scale changes while it plays.
 */
export const FitBox: React.FC<{
  w: number; h: number; children: React.ReactNode; align?: "left" | "center"; valign?: "top" | "center"; style?: React.CSSProperties;
  grow?: number; // largest scale up for small content; 1 = never scale up
  reflow?: boolean;
  hug?: boolean;
  fill?: number;
}> = ({ w, h, children, align = "left", valign = "top", style, grow = 1, reflow = false, hug = false, fill = 1 }) => {
  const ref = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState({ scale: 1, height: h });
  const cur = useRef(fit);
  cur.current = fit;
  const last = useRef("");
  const [handle] = useState(() => delayRender("FitBox: wait for the fonts, then measure"));
  const measure = () => {
    const el = ref.current;
    if (!el) return;
    // Width comes from the [data-fit-body] element when there is one (captions and notes rewrap instead),
    // so a narrow drawing can grow even when its note spans the box.
    const body = el.querySelector("[data-fit-body]") as HTMLElement | null;
    // Lay the content out at scale s (reflow width and --fit) and return its unscaled size.
    const at = (s: number) => {
      const width = `${w / s}px`;
      if (reflow && el.style.width !== width) el.style.width = width;
      if (el.style.getPropertyValue("--fit") !== String(s)) el.style.setProperty("--fit", String(s));
      const bw = Math.max(body ? body.scrollWidth : 0, body && !reflow ? 0 : el.scrollWidth);
      // the layout height, so an element still sliding in (translateY) does not change the scale
      return { bw, bh: el.offsetHeight };
    };
    const fits = (s: number) => {
      const m = at(s);
      // Hand-drawn borders overhang their box by 5 px (SketchRect), which is allowed. With reflow the
      // layout width is w / s by construction, so only wider content (nowrap text) fails.
      const bw = m.bw - 6;
      const okW = reflow ? bw <= w / s + 1 : bw * s <= w + 1;
      return okW && m.bh * s <= (s > 1 ? fill * h : h) + 1;
    };
    // Skip the search when the content has the size it had after the last search (most frames).
    const now = at(cur.current.scale);
    const key = `${now.bw}x${now.bh}`;
    if (key === last.current) return;
    // The fitted height shrinks as s shrinks, so the largest s that fits is found by bisection.
    let s = grow;
    if (!fits(s)) {
      let lo = 0.05, hi = grow;
      for (let i = 0; i < 14; i++) { const mid = (lo + hi) / 2; if (fits(mid)) lo = mid; else hi = mid; }
      s = lo;
    }
    s = Math.floor(s * 200) / 200; // steps of 0.005
    const m = at(s);
    last.current = `${m.bw}x${m.bh}`;
    const height = Math.min(h, Math.ceil(m.bh * s));
    if (s !== cur.current.scale || height !== cur.current.height) setFit({ scale: s, height });
  };
  useLayoutEffect(measure);
  useLayoutEffect(() => {
    let live = true;
    // The text reflows when the web fonts arrive; measure again then, and on any later size change.
    const ro = new ResizeObserver(() => measure());
    if (ref.current) ro.observe(ref.current);
    fontsReady.then(() => {
      if (!live) return;
      last.current = "";
      measure();
      requestAnimationFrame(() => requestAnimationFrame(() => continueRender(handle)));
    });
    return () => { live = false; ro.disconnect(); continueRender(handle); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (DEBUG_FIT) logFit(ref.current, fit.scale);
  });
  const { scale } = fit;
  const boxH = hug ? fit.height : h;
  const inner: React.CSSProperties = reflow
    ? { width: w / scale, flex: "none" }
    : { width: grow > 1 ? "max-content" : w, maxWidth: w, flex: "none" };
  return (
    <div style={{ width: w, height: boxH, position: "relative", display: "flex", justifyContent: align === "center" ? "center" : "flex-start", alignItems: valign === "center" ? "center" : "flex-start", ...style }}>
      <div style={{
        width: w, flex: "none", display: "flex", justifyContent: align === "center" ? "center" : "flex-start",
        transform: `scale(${scale})`, transformOrigin: `${align === "center" ? "50%" : "0"} ${valign === "center" ? "50%" : "0"}`,
      }}>
        <div ref={ref} style={{
          ...inner, display: "flex", flexDirection: "column", alignItems: align === "center" ? "center" : "flex-start",
          ["--fit" as string]: scale,
        }}>
          {children}
        </div>
      </div>
    </div>
  );
};

function logFit(el: HTMLDivElement | null, scale: number) {
  if (!el) return;
  const box = (el.parentElement?.parentElement as HTMLElement).getBoundingClientRect();
  const vis = el.getBoundingClientRect();
  const min: Record<string, number> = {};
  el.querySelectorAll<HTMLElement>("[data-ty]").forEach((n) => {
    if (!n.offsetHeight) return;
    const k = n.getBoundingClientRect().height / n.offsetHeight;
    const fs = Math.round(parseFloat(getComputedStyle(n).fontSize) * k * 10) / 10;
    const t = n.dataset.ty as string;
    min[t] = Math.min(min[t] ?? 1e9, fs);
  });
  const R = Math.round;
  console.log("FIT " + JSON.stringify({
    id: (el.textContent ?? "").replace(/\s+/g, " ").slice(0, 36), scale,
    nat: [el.scrollWidth, (el.querySelector("[data-fit-body]") as HTMLElement | null)?.scrollWidth ?? null, el.offsetHeight],
    box: [R(box.left), R(box.top), R(box.right), R(box.bottom)], vis: [R(vis.left), R(vis.top), R(vis.right), R(vis.bottom)],
    over: vis.right > box.right + 2 || vis.bottom > box.bottom + 2 || vis.top < box.top - 2 || vis.left < box.left - 2, min,
  }));
}

/**
 * Keeps layout space for content that is not drawn yet: the hidden `ghost` and the real `children`
 * share one grid cell, so the box has its final size on every frame (the kit's Handwrite and KeyPoint
 * render nothing before their frame, which would move a centred block and change its fit scale).
 */
export const Reserve: React.FC<{ ghost: React.ReactNode; children: React.ReactNode; style?: React.CSSProperties }> = ({ ghost, children, style }) => (
  <div style={{ display: "grid", justifyItems: "start", alignItems: "start", ...style }}>
    <div aria-hidden style={{ gridArea: "1 / 1", visibility: "hidden" }}>{ghost}</div>
    <div style={{ gridArea: "1 / 1", minWidth: 0 }}>{children}</div>
  </div>
);

/**
 * The kit's Handwrite with its final size reserved from the first frame. The reserved box also holds the
 * pen, which hangs up to 66 px past the end of the text, so the width is the same on every frame.
 */
export const HandwriteBox: React.FC<{ text: string; size: number; children: React.ReactNode }> = ({ text, size, children }) => (
  <Reserve ghost={<div style={{ paddingRight: 68 }}><HandGhost text={text} size={size} /></div>}>
    {children}
  </Reserve>
);

/** The layout box of the kit's Handwrite (same font, size, line height, nowrap and padding), for a Reserve ghost. */
export const HandGhost: React.FC<{ text: string; size: number }> = ({ text, size }) => (
  <div style={{ display: "inline-block", fontFamily: hand, fontSize: size, fontWeight: 700, lineHeight: 1.1, whiteSpace: "nowrap" }}>
    <span style={{ display: "inline-block", paddingRight: "0.2em" }}>{text}</span>
  </div>
);

/**
 * A number and its unit never split across lines: "30 s", "2.72 %", "49 h" get a no-break space.
 * Only short unit words count, so "30 requests" can still wrap.
 */
const UNIT = /(\d)[ \t]+(%|‰|×|x(?![a-z])|(?:ms|µs|us|ns|s|sec|secs|min|mins|h|hr|hrs|d|ms\/tok|tok\/s|req\/s|rps|qps|tps|KB|MB|GB|TB|kB|Kb|Mb|Gb|K|M|B|k|px|pp|W|kW|GHz|MHz|USD|GPUs?|x)(?![A-Za-z]))/g;
export const keepUnits = (s: string) => s.replace(UNIT, "$1\u00A0$2");

// ---------------------------------------------------------------- text helpers

/**
 * Yellow highlighter behind part of a text that may wrap. Unlike the kit's Marker (inline-block, one
 * line only) this is a background on an inline span, so it follows the text across line breaks.
 */
export const MarkText: React.FC<{ text: string; mark?: string; at: number }> = ({ text, mark, at: a }) => {
  const f = useCurrentFrame();
  const i = mark ? text.indexOf(mark) : -1;
  if (!mark || i < 0) return <>{text}</>;
  const p = prog(f, a, 14);
  return (
    <>
      {text.slice(0, i)}
      <span style={{
        backgroundImage: `linear-gradient(${C.marker}, ${C.marker})`, backgroundRepeat: "no-repeat",
        backgroundPosition: "0 88%", backgroundSize: `${p * 100}% 42%`, WebkitBoxDecorationBreak: "clone", boxDecorationBreak: "clone",
        padding: "0 6px", margin: "0 -6px",
      }}>{mark}</span>
      {text.slice(i + mark.length)}
    </>
  );
};

/** A chip that wraps inside its box instead of running out of it (the kit's Chip never wraps). */
export const WrapChip: React.FC<{ tone?: Tone; size?: number; children: React.ReactNode; solid?: boolean }> = ({ tone, size = 32, children, solid }) => {
  const c = toneColor(tone);
  const filled = solid ?? (tone != null && tone !== "ink");
  return (
    <span style={{
      position: "relative", zIndex: 0, display: "inline-block", maxWidth: "100%", boxSizing: "border-box", fontFamily: font, fontSize: size,
      fontWeight: 600, lineHeight: 1.25, color: theme.ink, padding: "10px 26px",
    }}>
      <SketchRect color={c} fill={filled ? tonePastel(tone) : "#FFFFFF"} radius={24} sw={2.5} />
      <span data-ty="body">{children}</span>
    </span>
  );
};

/** Text width inside a growing FitBox: the box width divided by the scale, so the scaled text still fits. */
export const fitWidth = (w: number) => `calc(${w}px / var(--fit, 1))`;

/**
 * A font size that stays between `lo` and `hi` pixels on screen whatever the FitBox scale: inside a
 * box scaled by --fit, the layout size is the on-screen size divided by the scale.
 */
export const screenSize = (size: number, lo: number, hi: number) =>
  `calc(clamp(${lo}px, ${size}px * var(--fit, 1), ${hi}px) / var(--fit, 1))`;

/** Small grey line under a panel: a note or a source. 24 px, and 20 to 30 px on screen. */
export const GreyNote: React.FC<{ at: number; children: React.ReactNode; w: number }> = ({ at: a, children, w }) => (
  <Appear at={a} style={{ marginTop: 20, maxWidth: fitWidth(w), width: "max-content" }}>
    <div data-ty="note" style={{ fontFamily: font, fontSize: screenSize(24, 20, 30), color: theme.mut, lineHeight: 1.35 }}>{children}</div>
  </Appear>
);

/** One handwritten line above a panel. 40 px, and 34 to 50 px on screen. */
export const PanelCaption: React.FC<{ at: number; children: React.ReactNode; w: number }> = ({ at: a, children, w }) => (
  <Appear at={a} style={{ fontFamily: hand, fontSize: screenSize(40, 34, 50), fontWeight: 700, color: C.cascade, lineHeight: 1.12, marginBottom: 20, maxWidth: fitWidth(w), width: "max-content" }}>
    {children}
  </Appear>
);

/** Strips the spoken frame around a question: "Here is the question." and "Let's think it through." */
export const cleanQuestion = (s: string) =>
  s.replace(/^Here is the question\.\s*/i, "").replace(/\s*Let['’]s think it through\.?\s*$/i, "").trim();

/** Strips "Remember:", "The trap:", "Try this:" and capitalises what is left. */
export const stripLead = (s: string) => {
  const t = s.replace(/^(Remember|The trap|Try this)\s*[:.]\s*/i, "");
  return t.charAt(0).toUpperCase() + t.slice(1);
};
