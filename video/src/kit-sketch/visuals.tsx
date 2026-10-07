import React from "react";
import { AbsoluteFill, Audio, Easing, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadCaveat } from "@remotion/google-fonts/Caveat";
import { loadFont as loadJBMono } from "@remotion/google-fonts/JetBrainsMono";

// Sketchbook look for the Phase 3B lesson videos (chosen 2026-10-03): graph paper, hand-drawn boxes
// that draw themselves, a highlighter for key numbers, sticky notes for sources, word-by-word captions.
// Shared by every lesson video in this style; lesson-specific pieces live next to each lesson file.

export const font = loadInter("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).fontFamily;
export const hand = loadCaveat("normal", { weights: ["500", "600", "700"], subsets: ["latin"] }).fontFamily;
export const mono = loadJBMono("normal", { weights: ["400", "500", "700"], subsets: ["latin"] }).fontFamily;

export const theme = {
  acc: "#E8590C",
  ink: "#1E1E1E",
  mut: "#5C5F66",
  bg: "#FBFAF6",
  card: "#FFFFFF",
  line: "#1E1E1E",
  ok: "#2F9E44",
  safe: 96,
};

export const C = {
  cascade: "#E8590C",   // cascade, the thing under test, the alarm
  router: "#1971C2",    // router, the alternative, sources
  ok: "#2F9E44",
  warn: "#6741D9",
  grey: "#868E96",
  soft: "#DEE2E6",
  marker: "#FFE066",
};

const PASTEL: Record<string, string> = {
  [C.cascade]: "#FFE8CC", [C.router]: "#D0EBFF", [C.ok]: "#D3F9D8", [C.warn]: "#E5DBFF", [C.grey]: "#F1F3F5", [theme.ink]: "#F1F3F5",
};
export const pastel = (c: string) => PASTEL[c] ?? "#FFF9DB";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.bezier(0.16, 1, 0.3, 1);

export const prog = (frame: number, at: number, d = 12) =>
  interpolate(frame, [at, at + d], [0, 1], { ...clamp, easing: ease });

// ---------- narration timing ----------

export type Cue = { text: string; start: number; end: number; who?: string };
export type BeatT = { id: string; start: number; end: number; steps?: { key: string; at: number }[]; captions: Cue[] };

/** Local frame where a keyed narration line starts (minus the generator's cue lead). */
export const at = (b: BeatT, key: string): number => {
  const st = b.steps?.find((x) => x.key === key);
  if (!st) throw new Error(`Missing narration key "${key}" in beat "${b.id}"`);
  return st.at;
};

/** Local frame where the caption that starts with `prefix` begins, minus a small lead. */
export const cue = (b: BeatT, prefix: string, lead = 6): number => {
  const c = b.captions.find((x) => x.text.startsWith(prefix));
  if (!c) throw new Error(`No caption starting "${prefix}" in beat "${b.id}"`);
  return Math.max(0, c.start - lead);
};

/** Deterministic pseudo-random in [0, 1). Never Math.random in a render. */
export const hash = (n: number) => {
  const s = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return s - Math.floor(s);
};

// ---------- paper, filters, shell ----------

/** Hand-drawn wobble filters. Fixed user-space region, so straight lines (zero-height boxes) still render. */
export const RoughDefs: React.FC = () => (
  <svg width={0} height={0} style={{ position: "absolute" }}>
    <defs>
      <filter id="rough" filterUnits="userSpaceOnUse" x={-200} y={-200} width={4400} height={2600}>
        <feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves={2} seed={7} />
        <feDisplacementMap in="SourceGraphic" scale={4.5} />
      </filter>
      <filter id="rough2" filterUnits="userSpaceOnUse" x={-200} y={-200} width={4400} height={2600}>
        <feTurbulence type="fractalNoise" baseFrequency="0.022" numOctaves={2} seed={31} />
        <feDisplacementMap in="SourceGraphic" scale={6} />
      </filter>
    </defs>
  </svg>
);

const Paper: React.FC = () => (
  <AbsoluteFill style={{
    background: theme.bg,
    backgroundImage: "linear-gradient(#EEECE5 1.5px, transparent 1.5px), linear-gradient(90deg, #EEECE5 1.5px, transparent 1.5px)",
    backgroundSize: "48px 48px",
  }} />
);

export const Lesson: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  return (
    <AbsoluteFill style={{ fontFamily: font, color: theme.ink }}>
      <Paper />
      <RoughDefs />
      {children}
      <div style={{ position: "absolute", right: 64, top: 36, fontFamily: hand, fontSize: 34, fontWeight: 600, color: theme.mut }}>{label}</div>
      <div style={{ position: "absolute", left: 0, bottom: 0, height: 7, width: `${(f / durationInFrames) * 100}%`, background: theme.acc }} />
    </AbsoluteFill>
  );
};

// ---------- sketch primitives ----------

/** A hand-drawn rectangle behind its parent's content. The parent must have position: relative and zIndex: 0. */
export const SketchRect: React.FC<{ drawAt?: number; color?: string; fill?: string; sw?: number; radius?: number }> = ({
  drawAt, color = theme.ink, fill = "#FFFFFF", sw = 3, radius = 12,
}) => {
  const f = useCurrentFrame();
  const p = drawAt == null ? 1 : prog(f, drawAt, 18);
  const fo = drawAt == null ? 1 : prog(f, drawAt + 6, 14);
  const rect = (filter: string, o: number, w: number) => (
    <rect x={5} y={5} rx={radius} style={{ width: "calc(100% - 10px)", height: "calc(100% - 10px)" }} fill="none" stroke={color}
      strokeWidth={w} pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - p}
      filter={`url(#${filter})`} opacity={o} strokeLinecap="round" />
  );
  return (
    <svg style={{ position: "absolute", left: -5, top: -5, width: "calc(100% + 10px)", height: "calc(100% + 10px)", overflow: "visible", zIndex: -1 }}>
      <rect x={8} y={8} rx={radius} style={{ width: "calc(100% - 16px)", height: "calc(100% - 16px)" }} fill={fill} opacity={fo} />
      {rect("rough", 1, sw)}
      {rect("rough2", 0.28 * p, sw * 0.8)}
    </svg>
  );
};

/** Yellow highlighter band that wipes in behind inline text. */
export const Marker: React.FC<{ at: number; children: React.ReactNode; color?: string }> = ({ at: a, children, color = C.marker }) => {
  const f = useCurrentFrame();
  const p = prog(f, a, 14);
  return (
    <span style={{ position: "relative", display: "inline-block", zIndex: 0 }}>
      <span style={{
        position: "absolute", left: -8, right: -8, bottom: "8%", height: "42%", background: color, opacity: 0.85, zIndex: -1,
        transformOrigin: "left", transform: `scaleX(${p}) rotate(-0.8deg)`, borderRadius: 6,
      }} />
      {children}
    </span>
  );
};

// ---------- beat shell ----------

export const BeatShell: React.FC<{
  beat: BeatT;
  until: number;           // absolute frame where the next beat starts; the visual holds until then
  audioDir: string;
  chapter?: string;        // handwritten heading, top left
  noCaptions?: boolean;    // a title card already shows the words
  drift?: boolean;         // slow push-in over the beat
  children: React.ReactNode;
}> = ({ beat, until, audioDir, chapter, noCaptions, drift = true, children }) => {
  const len = until - beat.start;
  return (
    <Sequence from={beat.start} durationInFrames={len}>
      <FadeBlock hold={len} drift={drift}>{children}</FadeBlock>
      {chapter ? <ChapterHead text={chapter} hold={len} /> : null}
      <Sequence from={beat.captions[0]?.start ?? 0} layout="none">
        <Audio src={staticFile(`${audioDir}/${beat.id}.mp3`)} />
      </Sequence>
      {noCaptions ? null : <Captions cues={beat.captions} />}
    </Sequence>
  );
};

const FadeBlock: React.FC<{ hold: number; drift: boolean; children: React.ReactNode }> = ({ hold, drift, children }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, 10, hold - 10, hold], [0, 1, 1, 0], clamp);
  const s = drift ? interpolate(f, [0, hold], [1, 1.022], clamp) : 1;
  return <AbsoluteFill style={{ opacity: o, transform: `scale(${s})`, transformOrigin: "50% 45%" }}>{children}</AbsoluteFill>;
};

const ChapterHead: React.FC<{ text: string; hold: number }> = ({ text, hold }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, 10, hold - 10, hold], [0, 1, 1, 0], clamp);
  return (
    <div style={{ position: "absolute", left: 96, top: 22, opacity: o, fontFamily: hand, fontSize: 62, fontWeight: 700, color: theme.ink }}>
      <Marker at={6}>{text}</Marker>
    </div>
  );
};

/** Word-by-word captions: the phrase stays, each word darkens as it is spoken. */
export const Captions: React.FC<{ cues: Cue[] }> = ({ cues }) => {
  const f = useCurrentFrame();
  const c = cues.find((x) => f >= x.start && f < x.end);
  if (!c) return null;
  const words = c.text.split(" ");
  const total = words.reduce((a, w) => a + w.length + 1, 0);
  let acc = 0;
  const o = interpolate(f, [c.start, c.start + 5], [0, 1], clamp);
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 52, display: "flex", justifyContent: "center", opacity: o }}>
      <div style={{ position: "relative", zIndex: 0, padding: "14px 30px", display: "flex", gap: 12, fontFamily: font, fontSize: 40, fontWeight: 600 }}>
        <SketchRect fill="#FFFFFF" sw={2.5} radius={14} />
        {words.map((w, i) => {
          const s0 = c.start + ((c.end - c.start) * acc) / total;
          acc += w.length + 1;
          return <span key={i} style={{ color: f >= s0 ? theme.ink : "#ADB5BD" }}>{w}</span>;
        })}
      </div>
    </div>
  );
};

/** Shows children from local frame `from` to `to`, with short fades. */
export const Phase: React.FC<{ from: number; to?: number; children: React.ReactNode }> = ({ from, to, children }) => {
  const f = useCurrentFrame();
  const end = to ?? 1e9;
  // A phase shorter than its two fades still needs a range that only goes
  // forward, or Remotion throws and the whole render stops.
  if (end - from < 2 || f < from || f > end) return null;
  const fade = Math.min(10, (end - from) / 3);
  const o = interpolate(f, [from, from + fade, end - fade * 0.8, end], [0, 1, 1, 0], clamp);
  return <AbsoluteFill style={{ opacity: o }}>{children}</AbsoluteFill>;
};

// ---------- building blocks ----------

export const Appear: React.FC<{ at: number; dy?: number; style?: React.CSSProperties; children: React.ReactNode }> = ({
  at: a, dy = 16, style, children,
}) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f - a, fps, config: { damping: 18, mass: 0.6, stiffness: 140 } });
  return <div style={{ opacity: Math.min(1, p * 1.4), transform: `translateY(${(1 - p) * dy}px)`, ...style }}>{children}</div>;
};

/** Card with a hand-drawn border. `hotAt` re-inks it in a colour with a pastel fill. */
export const Panel: React.FC<{
  children: React.ReactNode; style?: React.CSSProperties; hotAt?: number; hot?: string; dimAt?: number; drawAt?: number; fill?: string;
}> = ({ children, style, hotAt, hot = theme.acc, dimAt, drawAt, fill }) => {
  const f = useCurrentFrame();
  const h = hotAt != null ? prog(f, hotAt, 8) : 0;
  const d = dimAt != null ? prog(f, dimAt, 10) : 0;
  return (
    <div style={{
      position: "relative", zIndex: 0, padding: "22px 28px", fontFamily: font, color: theme.ink, opacity: 1 - 0.55 * d, ...style,
    }}>
      <SketchRect drawAt={drawAt} color={h > 0.5 ? hot : theme.ink} fill={h > 0.5 ? pastel(hot) : fill ?? "#FFFFFF"} sw={h > 0.5 ? 3.5 : 3} />
      {children}
    </div>
  );
};

export const Kicker: React.FC<{ children: React.ReactNode; color?: string; style?: React.CSSProperties }> = ({
  children, color = theme.acc, style,
}) => (
  <div style={{ color, fontFamily: hand, fontSize: 38, fontWeight: 700, lineHeight: 1.1, ...style }}>{children}</div>
);

export const Chip: React.FC<{ children: React.ReactNode; color?: string; solid?: boolean; size?: number; style?: React.CSSProperties }> = ({
  children, color = theme.acc, solid, size = 30, style,
}) => (
  <span style={{
    position: "relative", zIndex: 0, display: "inline-flex", alignItems: "center", gap: 12, fontFamily: font, fontSize: size, fontWeight: 600,
    color: theme.ink, padding: "10px 24px", whiteSpace: "nowrap", ...style,
  }}>
    <SketchRect color={color} fill={solid ? pastel(color) : "#FFFFFF"} radius={24} sw={2.5} />
    {children}
  </span>
);

/** A big handwritten number with a highlighter stroke under it. */
export const Big: React.FC<{ value: string; label?: string; color?: string; size?: number; at?: number; align?: "center" | "left" }> = ({
  value, label, color = theme.ink, size = 120, at: a = 0, align = "center",
}) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f - a, fps, config: { damping: 14, mass: 0.6, stiffness: 150 } });
  return (
    <div style={{ textAlign: align, opacity: Math.min(1, p * 1.5), transform: `scale(${0.9 + 0.1 * p})`, transformOrigin: align === "center" ? "center" : "left" }}>
      <div style={{ color, fontFamily: hand, fontSize: size * 1.12, fontWeight: 700, lineHeight: 1 }}>
        <Marker at={a + 10}>{value}</Marker>
      </div>
      {label ? <div style={{ color: theme.mut, fontFamily: font, fontSize: 28, marginTop: 12 }}>{label}</div> : null}
    </div>
  );
};

/** Mono lines that each appear at their own frame. `hlAt` adds a highlighter behind a line. */
export const MonoLines: React.FC<{
  lines: { text: string; at: number; color?: string; hlAt?: number }[]; size?: number; title?: string; style?: React.CSSProperties; drawAt?: number;
}> = ({ lines, size = 34, title, style, drawAt }) => {
  const f = useCurrentFrame();
  return (
    <Panel drawAt={drawAt} style={{ padding: "26px 32px", ...style }}>
      {title ? <div style={{ fontFamily: hand, fontSize: 34, fontWeight: 600, color: theme.mut, marginBottom: 10 }}>{title}</div> : null}
      <div style={{ fontFamily: mono, fontSize: size, lineHeight: 1.6 }}>
        {lines.map((l, i) => {
          const p = prog(f, l.at, 8);
          const line = <span style={{ whiteSpace: "pre", color: l.color ?? theme.ink }}>{l.text === "" ? " " : l.text}</span>;
          return (
            <div key={i} style={{ opacity: p }}>
              {l.hlAt != null ? <Marker at={l.hlAt}>{line}</Marker> : line}
            </div>
          );
        })}
      </div>
    </Panel>
  );
};

/** Numbered list; each item lands at its own frame. The current number is circled in orange. */
export const Numbered: React.FC<{ items: { text: React.ReactNode; at: number }[]; size?: number; gap?: number }> = ({
  items, size = 40, gap = 30,
}) => {
  const f = useCurrentFrame();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap, fontFamily: font }}>
      {items.map((it, i) => {
        const p = prog(f, it.at);
        const next = items[i + 1]?.at ?? 1e9;
        const cur = f >= it.at && f < next;
        const d = size * 1.45;
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", opacity: p, transform: `translateX(${(1 - p) * -18}px)` }}>
            <div style={{ position: "relative", width: d, height: d, flex: "none", marginRight: 26 }}>
              <svg width={d} height={d} style={{ position: "absolute", overflow: "visible" }}>
                <ellipse cx={d / 2} cy={d / 2} rx={d / 2 - 3} ry={d / 2 - 4} fill={cur ? pastel(C.cascade) : "#FFFFFF"}
                  stroke={cur ? C.cascade : theme.ink} strokeWidth={3} filter="url(#rough)" />
              </svg>
              <div style={{
                position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
                fontFamily: hand, fontSize: size * 0.95, fontWeight: 700, color: cur ? C.cascade : theme.ink,
              }}>{i + 1}</div>
            </div>
            <div style={{ color: theme.ink, fontSize: size, lineHeight: 1.3, fontWeight: cur ? 600 : 500 }}>{it.text}</div>
          </div>
        );
      })}
    </div>
  );
};

/** Sticky note for an external source. Use for every external number. */
export const Evidence: React.FC<{ at: number; source: string; children: React.ReactNode; style?: React.CSSProperties }> = ({
  at: a, source, children, style,
}) => (
  <Appear at={a} style={style}>
    <div style={{
      position: "relative", background: "#FFF3BF", padding: "26px 32px 22px", fontFamily: font, transform: "rotate(-0.6deg)",
      boxShadow: "0 1px 1px rgba(0,0,0,.06), 0 10px 22px rgba(60,50,0,.12)", borderRadius: 3,
    }}>
      <div style={{
        position: "absolute", left: "50%", top: -14, width: 150, height: 30, marginLeft: -75, transform: "rotate(-3deg)",
        background: "rgba(255,255,255,.55)", border: "1px solid rgba(0,0,0,.06)",
      }} />
      <div style={{ color: "#8F6B00", fontFamily: hand, fontSize: 34, fontWeight: 700 }}>source says…</div>
      <div style={{ color: theme.ink, fontSize: 31, lineHeight: 1.38, marginTop: 4 }}>{children}</div>
      <div style={{ color: "#7A6A3A", fontSize: 22, marginTop: 10 }}>{source}</div>
    </div>
  </Appear>
);

/** Box with a title and a sub line, used in flow diagrams. Its border draws itself in at `at`. */
export const Node: React.FC<{
  title: string; sub?: string; at?: number; hotAt?: number; color?: string; w?: number; dimAt?: number; style?: React.CSSProperties;
}> = ({ title, sub, at: a = 0, hotAt, color = theme.acc, w = 300, dimAt, style }) => {
  const f = useCurrentFrame();
  const p = prog(f, a, 8);
  return (
    <div style={{ opacity: p, width: w, flex: "none", ...style }}>
      <Panel hotAt={hotAt} hot={color} dimAt={dimAt} drawAt={a} style={{ padding: "18px 22px" }}>
        <div style={{ fontSize: 31, fontWeight: 700, lineHeight: 1.15 }}>{title}</div>
        {sub ? <div style={{ fontSize: 23, color: theme.mut, marginTop: 6, lineHeight: 1.3 }}>{sub}</div> : null}
      </Panel>
    </div>
  );
};

/** Hand-drawn arrow that draws itself in. */
export const Arrow: React.FC<{ at?: number; label?: string; w?: number; color?: string }> = ({ at: a = 0, label, w = 70, color = theme.ink }) => {
  const f = useCurrentFrame();
  const p = prog(f, a, 12);
  const h = prog(f, a + 8, 6);
  return (
    <div style={{ width: w, flex: "none", display: "flex", flexDirection: "column", alignItems: "center" }}>
      <svg width={w} height={30} viewBox={`0 0 ${w} 30`} style={{ overflow: "visible" }}>
        <path d={`M 4 17 Q ${w / 2} 9 ${w - 8} 15`} fill="none" stroke={color} strokeWidth={3.5} strokeLinecap="round"
          pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - p} filter="url(#rough)" />
        <path d={`M ${w - 22} 6 L ${w - 7} 15 L ${w - 21} 24`} fill="none" stroke={color} strokeWidth={3.5} strokeLinecap="round"
          strokeLinejoin="round" opacity={h} filter="url(#rough)" />
      </svg>
      {label ? <div style={{ color, fontFamily: hand, fontSize: 28, fontWeight: 700, whiteSpace: "nowrap", opacity: p }}>{label}</div> : null}
    </div>
  );
};

// ---------- chart ----------

type Pt = [number, number];
export type Series = { pts: Pt[]; color: string; at: number; dur?: number; dashed?: boolean; width?: number; step?: boolean };
export type HLine = { y: number; label?: string; color: string; at: number; dashed?: boolean };
export type VLine = { x: number; label?: string; color: string; at: number };
export type Dot = { x: number; y: number; label?: string; color: string; at: number; dx?: number; dy?: number; anchor?: "start" | "middle" | "end" };

export const Chart: React.FC<{
  id: string; w: number; h: number; x: [number, number]; y: [number, number];
  xTicks?: number[]; yTicks?: number[]; xFmt?: (v: number) => string; yFmt?: (v: number) => string;
  xLabel?: string; yLabel?: string; series?: Series[]; hlines?: HLine[]; vlines?: VLine[]; dots?: Dot[];
  pad?: { l: number; r: number; t: number; b: number };
}> = ({ w, h, x, y, xTicks = [], yTicks = [], xFmt = String, yFmt = String, xLabel, yLabel, series = [], hlines = [], vlines = [], dots = [], pad = { l: 100, r: 30, t: 24, b: 76 } }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pw = w - pad.l - pad.r;
  const ph = h - pad.t - pad.b;
  const sx = (v: number) => pad.l + ((v - x[0]) / (x[1] - x[0])) * pw;
  const sy = (v: number) => pad.t + ph - ((v - y[0]) / (y[1] - y[0])) * ph;
  const path = (s: Series) => {
    const pts = s.step ? s.pts.flatMap((p, i) => (i === 0 ? [p] : [[p[0], s.pts[i - 1][1]] as Pt, p])) : s.pts;
    return pts.map((p, i) => `${i ? "L" : "M"} ${sx(p[0]).toFixed(1)} ${sy(p[1]).toFixed(1)}`).join(" ");
  };
  const txt = { fontFamily: hand, fill: theme.mut, fontSize: 30, fontWeight: 600 } as const;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ overflow: "visible" }}>
      {yTicks.map((v) => (
        <g key={`y${v}`}>
          <line x1={pad.l} x2={pad.l + pw} y1={sy(v)} y2={sy(v)} stroke="#DEE2E6" strokeWidth={2} strokeDasharray="2 8" strokeLinecap="round" />
          <text x={pad.l - 14} y={sy(v) + 9} textAnchor="end" {...txt}>{yFmt(v)}</text>
        </g>
      ))}
      {xTicks.map((v) => (
        <text key={`x${v}`} x={sx(v)} y={pad.t + ph + 38} textAnchor="middle" {...txt}>{xFmt(v)}</text>
      ))}
      <line x1={pad.l} x2={pad.l + pw} y1={pad.t + ph} y2={pad.t + ph} stroke={theme.ink} strokeWidth={3} filter="url(#rough)" strokeLinecap="round" />
      <line x1={pad.l} x2={pad.l} y1={pad.t} y2={pad.t + ph} stroke={theme.ink} strokeWidth={3} filter="url(#rough)" strokeLinecap="round" />
      {xLabel ? <text x={pad.l + pw / 2} y={h - 2} textAnchor="middle" {...txt}>{xLabel}</text> : null}
      {yLabel ? <text x={14} y={pad.t + ph / 2} textAnchor="middle" {...txt} transform={`rotate(-90 14 ${pad.t + ph / 2})`}>{yLabel}</text> : null}
      {hlines.map((l, i) => {
        const p = prog(f, l.at, 16);
        return (
          <g key={`h${i}`} opacity={p > 0 ? 1 : 0}>
            <line x1={pad.l} x2={pad.l + pw * p} y1={sy(l.y)} y2={sy(l.y)} stroke={l.color} strokeWidth={3.5} strokeLinecap="round"
              strokeDasharray={l.dashed === false ? undefined : "12 10"} filter="url(#rough)" />
            {l.label ? <text x={pad.l + pw - 6} y={sy(l.y) - 12} textAnchor="end" fontFamily={hand} fontSize={32} fontWeight={700} fill={l.color} opacity={p}>{l.label}</text> : null}
          </g>
        );
      })}
      {vlines.map((l, i) => {
        const p = prog(f, l.at, 16);
        return (
          <g key={`v${i}`} opacity={p > 0 ? 1 : 0}>
            <line x1={sx(l.x)} x2={sx(l.x)} y1={pad.t + ph} y2={pad.t + ph - ph * p} stroke={l.color} strokeWidth={3} strokeDasharray="10 10" strokeLinecap="round" filter="url(#rough)" />
            {l.label ? <text x={sx(l.x) + 12} y={pad.t + 28} fontFamily={hand} fontSize={32} fontWeight={700} fill={l.color} opacity={p}>{l.label}</text> : null}
          </g>
        );
      })}
      {series.map((s, i) => {
        const p = prog(f, s.at, s.dur ?? 30);
        return (
          <path key={i} d={path(s)} fill="none" stroke={s.color} strokeWidth={s.width ?? 5.5} strokeLinejoin="round" strokeLinecap="round"
            pathLength={s.dashed ? undefined : 1} strokeDasharray={s.dashed ? "12 10" : "1 1"} strokeDashoffset={s.dashed ? undefined : 1 - p}
            filter="url(#rough)" opacity={f >= s.at ? (s.dashed ? p : 1) : 0} />
        );
      })}
      {dots.map((d, i) => {
        const p = spring({ frame: f - d.at, fps, config: { damping: 11, mass: 0.5 } });
        return (
          <g key={`d${i}`} opacity={Math.min(1, p * 1.5)}>
            <circle cx={sx(d.x)} cy={sy(d.y)} r={12 * p} fill={d.color} stroke="#FFFFFF" strokeWidth={3} />
            {d.label ? (
              <text x={sx(d.x) + (d.dx ?? 18)} y={sy(d.y) + (d.dy ?? -16)} textAnchor={d.anchor ?? "start"} fontFamily={hand} fontSize={40} fontWeight={700} fill={d.color}>
                {d.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
};

// ---------- table ----------

export type Row = { cells: React.ReactNode[]; at: number; hotAt?: number; hot?: string; color?: string };

/** Rows land one at a time, each in its own hand-drawn box; a row can light up later. */
export const Table: React.FC<{
  cols: { title: string; w: number }[]; rows: Row[]; headAt?: number; size?: number; style?: React.CSSProperties;
}> = ({ cols, rows, headAt = 0, size = 30, style }) => {
  const f = useCurrentFrame();
  const cell = (w: number): React.CSSProperties => ({ width: w, flex: "none", padding: "14px 20px" });
  return (
    <div style={{ fontFamily: font, ...style }}>
      <div style={{ display: "flex", opacity: prog(f, headAt), color: theme.mut, fontFamily: hand, fontSize: 32, fontWeight: 700 }}>
        {cols.map((c, i) => <div key={i} style={{ ...cell(c.w), paddingBottom: 4 }}>{c.title}</div>)}
      </div>
      {rows.map((r, i) => {
        const p = prog(f, r.at);
        const h = r.hotAt != null ? prog(f, r.hotAt, 8) : 0;
        const hot = r.hot ?? theme.acc;
        return (
          <div key={i} style={{
            position: "relative", zIndex: 0, display: "flex", alignItems: "center", opacity: p, transform: `translateY(${(1 - p) * 12}px)`,
            marginTop: 12, fontSize: size, color: r.color ?? theme.ink,
          }}>
            <SketchRect drawAt={r.at} color={h > 0.5 ? hot : theme.ink} fill={h > 0.5 ? pastel(hot) : "#FFFFFF"} sw={h > 0.5 ? 3.5 : 2.5} />
            {r.cells.map((c, j) => (
              <div key={j} style={{ ...cell(cols[j].w), fontWeight: j === 0 ? 700 : 500, lineHeight: 1.25 }}>{c}</div>
            ))}
          </div>
        );
      })}
    </div>
  );
};

// ---------- cards ----------

/** Title card in the sketch style. */
export const Card: React.FC<{ hold: number; kicker?: string; title: string; sub?: string }> = ({ hold, kicker, title, sub }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const o = interpolate(f, [0, 10, hold - 8, hold], [0, 1, 1, 0], clamp);
  const p = spring({ frame: f - 4, fps, config: { damping: 16, mass: 0.7 } });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", textAlign: "center", opacity: o }}>
      {kicker ? <div style={{ fontFamily: hand, fontSize: 46, fontWeight: 700, color: theme.acc }}>{kicker}</div> : null}
      <div style={{ fontFamily: hand, fontSize: 150, fontWeight: 700, lineHeight: 1.0, marginTop: 10, transform: `scale(${0.92 + 0.08 * p})`, opacity: Math.min(1, p * 1.4) }}>
        <Marker at={16}>{title}</Marker>
      </div>
      {sub ? <div style={{ fontFamily: font, fontSize: 38, color: theme.mut, marginTop: 26 }}>{sub}</div> : null}
    </AbsoluteFill>
  );
};
