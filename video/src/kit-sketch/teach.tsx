import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, SketchRect, font, hand, pastel, prog, theme } from "./visuals";

// Teaching pieces for the Sketchbook look, used by the concept method (concept.tsx): the step rail,
// writing by hand, marking an answer, and the three key points. Built 2026-10-03.
// Removed after the user rejected them: pause-and-countdown cards and the tutor/student dialogue format.

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** A pen, drawn as a marker held at an angle. Its tip is at (0, 0). */
const Pen: React.FC<{ color?: string }> = ({ color = theme.ink }) => (
  <svg width={70} height={70} viewBox="0 0 70 70" style={{ position: "absolute", left: -4, top: -62, overflow: "visible" }}>
    <g transform="rotate(35 4 62)">
      <rect x={-2} y={0} width={14} height={50} rx={4} fill={color} />
      <rect x={-2} y={0} width={14} height={12} rx={3} fill="#ADB5BD" />
      <path d="M -2 50 L 12 50 L 5 64 Z" fill={color} />
    </g>
  </svg>
);

/**
 * Text written by hand: characters appear left to right at `cps` characters per second, with a pen at
 * the writing edge. `strikeAt` crosses the text out in red (the "first thought" in the concept method).
 */
export const Handwrite: React.FC<{
  text: string; at: number; size?: number; color?: string; cps?: number; style?: React.CSSProperties; strikeAt?: number;
}> = ({ text, at: a, size = 64, color = theme.ink, cps = 14, style, strikeAt }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const dur = Math.max(8, (text.length / cps) * fps);
  const p = interpolate(f, [a, a + dur], [0, 1], clamp);
  const penOn = interpolate(f, [a - 4, a, a + dur, a + dur + 8], [0, 1, 1, 0], clamp);
  const strike = strikeAt != null ? prog(f, strikeAt, 10) : 0;
  if (f < a - 4) return null;
  return (
    <div style={{ position: "relative", display: "inline-block", fontFamily: hand, fontSize: size, fontWeight: 700, color, lineHeight: 1.1, whiteSpace: "nowrap", ...style }}>
      {/* Caveat's last glyph overhangs its advance width; the right padding keeps it inside the clip box. */}
      <span style={{ clipPath: `inset(-20% ${(1 - p) * 100}% -20% 0)`, display: "inline-block", paddingRight: "0.2em" }}>{text}</span>
      <div style={{ position: "absolute", left: `${p * 100}%`, top: "78%", opacity: penOn }}><Pen color={color} /></div>
      {strikeAt != null ? (
        <svg style={{ position: "absolute", left: -6, top: "48%", width: "calc(100% + 12px)", height: 20, overflow: "visible" }}>
          <line x1={0} y1={8} x2="100%" y2={4} stroke="#E03131" strokeWidth={6} strokeLinecap="round" pathLength={1}
            strokeDasharray="1 1" strokeDashoffset={1 - strike} filter="url(#rough)" opacity={strike > 0 ? 1 : 0} />
        </svg>
      ) : null}
    </div>
  );
};

/** A hand-drawn tick that draws itself in. */
export const Tick: React.FC<{ at: number; size?: number; color?: string }> = ({ at: a, size = 80, color = C.ok }) => {
  const f = useCurrentFrame();
  const p = prog(f, a, 12);
  return (
    <svg width={size} height={size} viewBox="0 0 80 80" style={{ overflow: "visible", opacity: p > 0 ? 1 : 0 }}>
      <path d="M 8 44 L 30 66 L 74 12" fill="none" stroke={color} strokeWidth={9} strokeLinecap="round" strokeLinejoin="round"
        pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - p} filter="url(#rough)" />
    </svg>
  );
};

/** Circles its own children with a hand-drawn ellipse, so the mark always fits the text it marks. */
export const Circled: React.FC<{ at: number; color?: string; pad?: number; children: React.ReactNode }> = ({
  at: a, color = C.cascade, pad = 26, children,
}) => {
  const f = useCurrentFrame();
  const p = prog(f, a, 16);
  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      {children}
      <svg style={{ position: "absolute", left: -pad, top: -pad * 0.5, width: `calc(100% + ${2 * pad}px)`, height: `calc(100% + ${pad}px)`, overflow: "visible", opacity: p > 0 ? 1 : 0 }}>
        <ellipse cx="50%" cy="50%" rx="49%" ry="47%" fill="none" stroke={color} strokeWidth={5} pathLength={1}
          strokeDasharray="1 1" strokeDashoffset={1 - p} filter="url(#rough)" />
      </svg>
    </div>
  );
};

/**
 * The concept method as a rail under the heading: which step of the concept the viewer is in.
 * `stages` are the step names; `starts` their local start frames. Done steps get a tick, the current one is orange.
 */
export const ConceptRail: React.FC<{ stages: string[]; starts: number[]; from?: number; top?: number }> = ({ stages, starts, from = 0, top = 108 }) => {
  const f = useCurrentFrame();
  if (f < from) return null;
  const o = prog(f, from, 10);
  let cur = -1;
  starts.forEach((s, i) => { if (f >= s) cur = i; });
  return (
    <div style={{ position: "absolute", left: 96, top, display: "flex", alignItems: "center", gap: 8, opacity: o, fontFamily: font }}>
      {stages.map((name, i) => {
        const done = i < cur;
        const now = i === cur;
        return (
          <React.Fragment key={name}>
            {i > 0 ? <span style={{ width: 22, height: 3, background: done || now ? C.cascade : "#CED4DA", borderRadius: 2 }} /> : null}
            <span style={{
              position: "relative", zIndex: 0, padding: "5px 14px", fontSize: 22, fontWeight: now ? 700 : 600,
              color: now ? theme.ink : done ? theme.mut : "#ADB5BD", whiteSpace: "nowrap",
            }}>
              <SketchRect color={now ? C.cascade : done ? theme.mut : "#CED4DA"} fill={now ? pastel(C.cascade) : "#FFFFFF"} sw={2} radius={16} />
              {done ? "✓ " : ""}{name}
            </span>
          </React.Fragment>
        );
      })}
    </div>
  );
};

const KP = {
  remember: { title: "Remember", color: C.ok, mark: "✓" },
  trap: { title: "The trap", color: "#E03131", mark: "!" },
  try: { title: "Try this", color: C.router, mark: "✎" },
};

/** The three key points that close every concept: remember, the trap, try this. */
export const KeyPoint: React.FC<{ kind: keyof typeof KP; at: number; children: React.ReactNode; style?: React.CSSProperties }> = ({ kind, at: a, children, style }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const k = KP[kind];
  const p = spring({ frame: f - a, fps, config: { damping: 16, mass: 0.6 } });
  if (f < a) return null;
  return (
    <div style={{ position: "relative", zIndex: 0, display: "flex", gap: 22, alignItems: "flex-start", padding: "22px 28px", opacity: Math.min(1, p * 1.4), transform: `translateY(${(1 - p) * 18}px)`, ...style }}>
      <SketchRect color={k.color} fill={k.color === "#E03131" ? "#FFE3E3" : pastel(k.color)} sw={3} radius={16} drawAt={a} />
      <div style={{
        flex: "none", width: 56, height: 56, borderRadius: 28, background: k.color, color: "#fff", display: "flex",
        alignItems: "center", justifyContent: "center", fontFamily: hand, fontSize: 40, fontWeight: 700,
      }}>{k.mark}</div>
      <div>
        <div style={{ fontFamily: hand, fontSize: 40, fontWeight: 700, color: k.color, lineHeight: 1 }}>{k.title}</div>
        <div style={{ fontFamily: font, fontSize: 32, fontWeight: 500, color: theme.ink, marginTop: 8, lineHeight: 1.35 }}>{children}</div>
      </div>
    </div>
  );
};
