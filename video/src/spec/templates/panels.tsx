import React from "react";
import { useCurrentFrame } from "remotion";
import { Appear, Arrow, Big, C, Kicker, MonoLines, Panel, SketchRect, font, hand, prog, theme } from "../../kit-sketch/visuals";
import { Handwrite } from "../../kit-sketch/teach";
import type {
  BarsPanel, ChipsPanel, ComparePanel, EquationPanel, FlowPanel, Panel as PanelT, PromptPanel, StatsPanel, TablePanel,
} from "../types";
import { FitBox, GreyNote, HandwriteBox, PanelCaption, WrapChip, keepUnits, panelStart, toneColor, tonePastel, type K } from "./common";

// One template per panel kind (SPEC.md "Panel"). Each one draws inside a w x h box and must hold at every
// text limit: sizes are picked from the box width, the item count and the longest text, and FitBox scales
// down what is still too big. A panel that is small for its box grows until its largest text reaches the
// on-screen maximum in MAX (capOf). Every element lands at its `at` line; a border draws in with the first
// element it holds. Every element is laid out on every frame (only its opacity changes), so the fit scale
// does not change while the panel plays.
//
// Sizes at 1080p (layout px; FitBox may scale them): body text 30 to 46, secondary text (flow sub, compare
// items, prompt lines) 24 to 40, notes and sources 24 (20 to 30 on screen, see GreyNote).

type P<T> = { p: T; k: K; w: number };

/** Inter 600 is about 0.56 em per character, Caveat 700 about 0.5, JetBrains Mono 0.6. */
const W_INTER = 0.56;
const W_HAND = 0.5;
const W_MONO = 0.6;
const clampN = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** A box at least this wide is a full-width box; narrower is a mechanism's side panel (950 px). */
const WIDE = 1300;

/** On-screen maxima: a small panel grows only until its text reaches these sizes. */
const MAX = { body: 54, sec: 42, compare: 50, mono: 42, handLine: 78, value: 230, title: 58 };

// ---------------------------------------------------------------- chips

const chipsSize = (w: number) => (w >= WIDE ? 36 : 32);

export const ChipsView: React.FC<P<ChipsPanel>> = ({ p, k, w }) => {
  const size = chipsSize(w);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 18, maxWidth: w }}>
      {p.items.map((it, i) => (
        <Appear key={i} at={k(it.at)} style={{ maxWidth: w }}>
          <WrapChip tone={it.tone} size={size}>{keepUnits(it.text)}</WrapChip>
        </Appear>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------- flow

const ARROW_W = 70;

const longestWord = (texts: (string | undefined)[]) =>
  Math.max(4, ...texts.flatMap((t) => (t ?? "").split(/\s+/)).map((x) => x.length));

/** Two-row flows: the arrow column between nodes and the height of the turn between the rows. */
const ROWS_ARROW_W = 90;
const TURN_H = 96;

/**
 * Layout and sizes. Wide box, 2 or 3 nodes: one row, each node (w - arrows) / n wide. Wide box, 4 or 5
 * nodes: two rows, the first ceil(n / 2) nodes left to right, a turn arrow down and back to the left,
 * then the rest left to right, so each node is wider and the text larger. The text is as large as the
 * node width allows (labels may take two or three lines), but never so large that one word is wider
 * than the node. Narrow box (a mechanism's side panel): nodes top to bottom.
 */
const flowSizes = (p: FlowPanel, w: number) => {
  const n = p.nodes.length;
  if (w < WIDE) return { layout: "column" as const, label: 34, sub: 27, pad: "14px 22px", nw: Math.min(w, 700), perRow: 1 };
  const rows = n >= 4;
  const perRow = rows ? Math.ceil(n / 2) : n;
  const aw = rows ? ROWS_ARROW_W : ARROW_W;
  const nw = Math.min(rows ? 640 : 520, (w - 8 - (perRow - 1) * aw) / perRow);
  const t: Record<number, [number, number]> = { 2: [50, 38], 3: [48, 36], 4: [52, 40], 5: [48, 36] };
  const [L, S] = t[n] ?? t[5];
  const padX = rows ? 32 : 28;
  const inner = nw - 2 * padX;
  const label = Math.floor(clampN(inner / (longestWord(p.nodes.map((x) => x.label)) * 0.64), 30, L));
  const sub = Math.floor(clampN(inner / (longestWord(p.nodes.map((x) => x.sub)) * 0.56), 24, S));
  return { layout: rows ? ("rows" as const) : ("row" as const), label, sub, pad: `${rows ? 28 : 26}px ${padX}px`, nw, perRow, aw };
};

/**
 * The turn between the two rows: from the bottom of the first row's last node down, left along the gap,
 * and down into the second row's first node. It draws in with that node, like the arrows in a row.
 */
const TurnArrow: React.FC<{ at: number; x1: number; x2: number; w: number }> = ({ at: a, x1, x2, w }) => {
  const f = useCurrentFrame();
  const p = prog(f, a, 16);
  const head = prog(f, a + 12, 6);
  const mid = TURN_H / 2;
  const end = TURN_H - 10;
  return (
    <svg width={w} height={TURN_H} style={{ overflow: "visible", display: "block" }}>
      <path d={`M ${x1} 8 L ${x1} ${mid} L ${x2} ${mid} L ${x2} ${end}`} fill="none" stroke={theme.ink} strokeWidth={3.5}
        strokeLinecap="round" strokeLinejoin="round" pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - p} filter="url(#rough)" />
      <path d={`M ${x2 - 11} ${end - 14} L ${x2} ${end} L ${x2 + 11} ${end - 14}`} fill="none" stroke={theme.ink} strokeWidth={3.5}
        strokeLinecap="round" strokeLinejoin="round" opacity={head} filter="url(#rough)" />
    </svg>
  );
};

const FlowNode: React.FC<{ n: FlowPanel["nodes"][number]; at: number; w: number; label: number; sub: number; pad: string }> = ({ n, at: a, w, label, sub, pad }) => {
  const f = useCurrentFrame();
  const tone = n.tone ?? "ink";
  // In a row every node is as tall as the tallest one (the row stretches them); the text sits in the middle.
  return (
    <div style={{ width: w, flex: "none", opacity: prog(f, a, 8), display: "flex" }}>
      <div style={{ position: "relative", zIndex: 0, padding: pad, flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <SketchRect drawAt={a} color={toneColor(tone)} fill={tone === "ink" ? "#FFFFFF" : tonePastel(tone)} sw={3} />
        <div data-ty="body" style={{ fontSize: label, fontWeight: 700, lineHeight: 1.15, overflowWrap: "break-word" }}>{keepUnits(n.label)}</div>
        {n.sub ? <div data-ty="sec" style={{ fontSize: sub, color: theme.mut, marginTop: 8, lineHeight: 1.28, overflowWrap: "break-word" }}>{keepUnits(n.sub)}</div> : null}
      </div>
    </div>
  );
};

export const FlowView: React.FC<P<FlowPanel>> = ({ p, k, w }) => {
  const s = flowSizes(p, w);
  const nw = s.nw;
  if (s.layout === "rows") {
    // a grid: node and arrow columns; rows = first row, the turn, second row (both node rows equally tall)
    const aw = s.aw ?? ROWS_ARROW_W;
    const cols = Array.from({ length: 2 * s.perRow - 1 }, (_, c) => (c % 2 === 0 ? `${nw}px` : `${aw}px`)).join(" ");
    const gridW = s.perRow * nw + (s.perRow - 1) * aw;
    const x1 = (s.perRow - 1) * (nw + aw) + nw / 2;
    const x2 = nw / 2;
    return (
      <div style={{ display: "grid", gridTemplateColumns: cols, gridTemplateRows: `1fr ${TURN_H}px 1fr`, width: gridW }}>
        {p.nodes.map((node, i) => {
          const second = i >= s.perRow;
          const j = second ? i - s.perRow : i;
          const row = second ? 3 : 1;
          return (
            <React.Fragment key={i}>
              {j > 0 ? (
                <div style={{ gridRow: row, gridColumn: 2 * j, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <Arrow at={k(node.at)} w={aw - 16} />
                </div>
              ) : null}
              <div style={{ gridRow: row, gridColumn: 2 * j + 1, display: "flex" }}>
                <FlowNode n={node} at={k(node.at)} w={nw} label={s.label} sub={s.sub} pad={s.pad} />
              </div>
            </React.Fragment>
          );
        })}
        <div style={{ gridRow: 2, gridColumn: "1 / -1" }}>
          <TurnArrow at={k(p.nodes[s.perRow].at)} x1={x1} x2={x2} w={gridW} />
        </div>
      </div>
    );
  }
  if (s.layout === "row") {
    return (
      <div style={{ display: "flex", alignItems: "stretch", width: "max-content", maxWidth: w }}>
        {p.nodes.map((node, i) => (
          <React.Fragment key={i}>
            {i > 0 ? <div style={{ display: "flex", alignItems: "center" }}><Arrow at={k(node.at)} w={ARROW_W} /></div> : null}
            <FlowNode n={node} at={k(node.at)} w={nw} label={s.label} sub={s.sub} pad={s.pad} />
          </React.Fragment>
        ))}
      </div>
    );
  }
  // narrow box: top to bottom
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", width: nw }}>
      {p.nodes.map((node, i) => (
        <React.Fragment key={i}>
          {i > 0 ? (
            <div style={{ width: nw, display: "flex", justifyContent: "center", height: 46 }}>
              <div style={{ transform: "rotate(90deg)", marginTop: 8 }}><Arrow at={k(node.at)} w={40} /></div>
            </div>
          ) : null}
          <FlowNode n={node} at={k(node.at)} w={nw} label={s.label} sub={s.sub} pad={s.pad} />
        </React.Fragment>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------- stats

const statsSizes = (p: StatsPanel, w: number) => {
  const n = p.items.length;
  const gap = 70;
  const maxLen = Math.max(...p.items.map((x) => x.value.length), 3);
  const top = n === 1 ? 210 : n === 2 ? 180 : 150;
  const fit = (width: number) => clampN(width / (maxLen * W_HAND * 1.12) - 4, 56, top);
  const colW = (w - gap * (n - 1)) / n;
  const sizeRow = fit(colW);
  const sizeCol = Math.min(fit(w), w >= WIDE ? 110 : 96);
  const row = n === 1 || sizeRow >= 0.8 * sizeCol;
  return { n, gap, colW, row, size: row ? sizeRow : sizeCol, label: w >= WIDE ? 34 : 30 };
};

export const StatsView: React.FC<P<StatsPanel>> = ({ p, k, w }) => {
  const f = useCurrentFrame();
  const s = statsSizes(p, w);
  return (
    <div style={{ display: "flex", flexDirection: s.row ? "row" : "column", gap: s.row ? s.gap : 30, width: w }}>
      {p.items.map((it, i) => (
        <div key={i} style={{ width: s.row ? s.colW : w, flex: "none" }}>
          <Big value={keepUnits(it.value)} color={toneColor(it.tone)} at={k(it.at)} size={s.size} align="left" />
          {it.label ? (
            <div data-ty="body" style={{ color: theme.mut, fontFamily: font, fontSize: s.label, lineHeight: 1.3, marginTop: 14, opacity: prog(f, k(it.at), 10) }}>
              {keepUnits(it.label)}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------- bars

const barsSizes = (p: BarsPanel, w: number) => {
  const n = p.items.length;
  const wide = w >= WIDE;
  const z = wide ? (n <= 2 ? 1.2 : n === 3 ? 1.12 : n === 4 ? 1.05 : 1) : 1; // fewer bars, larger bars
  const label = (wide ? 34 : 30) * z;
  const disp = (wide ? 54 : 46) * z;
  const longLabel = Math.max(...p.items.map((x) => x.label.length));
  const longDisp = Math.max(...p.items.map((x) => x.display.length));
  const lw = clampN(longLabel * 0.58 * label + 24, 200, wide ? 560 : 320);
  const dw = clampN(longDisp * W_HAND * disp + 40, 150, wide ? 420 : 280);
  return { label, disp, lw, dw, barH: 64 * z, rowH: 72 * z, gap: 22 * z, barMax: w - lw - dw - 24 };
};

export const BarsView: React.FC<P<BarsPanel>> = ({ p, k, w }) => {
  const f = useCurrentFrame();
  const s = barsSizes(p, w);
  const max = Math.max(...p.items.map((x) => x.value));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: s.gap, maxWidth: w, fontFamily: font }}>
      {p.items.map((it, i) => {
        const a = k(it.at);
        const c = it.tone && it.tone !== "ink" ? toneColor(it.tone) : C.grey;
        const grow = prog(f, a, 20);
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", minHeight: s.rowH, opacity: prog(f, a, 6) }}>
            <div data-ty="body" style={{ width: s.lw, flex: "none", fontSize: s.label, fontWeight: 700, lineHeight: 1.2, paddingRight: 20, boxSizing: "border-box" }}>{keepUnits(it.label)}</div>
            {/* the track has the bar's final width from the start, so the row width (and the fit) never changes */}
            <div style={{ flex: "none", width: Math.max(10, (s.barMax * it.value) / max) }}>
              <div style={{
                height: s.barH, width: `${grow * 100}%`, minWidth: 10 * Math.min(1, grow * 4), background: tonePastel(it.tone ?? "ink"),
                border: `3px solid ${c}`, borderRadius: 10, boxSizing: "border-box", filter: "url(#rough)",
              }} />
            </div>
            <div style={{
              marginLeft: 20, fontFamily: hand, fontSize: s.disp, fontWeight: 700, color: it.tone ? toneColor(it.tone) : theme.ink,
              whiteSpace: "nowrap", opacity: prog(f, a + 14, 8),
            }}>{it.display}</div>
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------- table

/** Width of a text in em of Inter: capitals and digits are wider than lower case. Bold adds about 6 %. */
const textEm = (t: string, bold: boolean) => {
  let e = 0;
  for (const ch of t) e += /[A-Z]/.test(ch) ? 0.68 : /[0-9$%]/.test(ch) ? 0.6 : /[a-z]/.test(ch) ? 0.53 : /\s/.test(ch) ? 0.27 : 0.4;
  return e * (bold ? 1.06 : 1);
};

/** The first column is bold (Inter 700), the others Inter 500; each column is as wide as its longest cell. */
const tableSizes = (p: TablePanel, w: number) => {
  const wide = w >= WIDE;
  const ncol = p.columns.length;
  // longest cell of each column in em, with 4 % slack; the heading is handwritten (narrower)
  const longest = p.columns.map((c, j) => 1.04 * Math.max(c.length * 0.45, ...p.rows.map((r) => textEm(r.cells[j] ?? "", j === 0))));
  const padX = wide ? 18 : 12;
  const sum = longest.reduce((a, b) => a + b, 0);
  const size = clampN((w - 2 * padX * ncol - 8) / sum, wide ? 30 : 28, wide ? 44 : 38);
  const natural = longest.map((l) => Math.max(140, l * size + 2 * padX + 4));
  const total = natural.reduce((a, b) => a + b, 0);
  const widths = total > w ? natural.map((x) => (x * w) / total) : natural;
  return { size, ncol, widths, total, padX };
};

export const TableView: React.FC<P<TablePanel>> = ({ p, k, w }) => {
  const f = useCurrentFrame();
  const { size, ncol, widths, total, padX } = tableSizes(p, w);
  const head = Math.min(...p.rows.map((r) => k(r.at)));
  const pad = `${size >= 36 ? 15 : 12}px ${padX}px`;
  const cell = (cw: number): React.CSSProperties => ({ width: cw, flex: "none", padding: pad, boxSizing: "border-box", overflowWrap: "break-word" });
  return (
    <div style={{ fontFamily: font, width: Math.min(w, total) }}>
      <div style={{ display: "flex", opacity: prog(f, head), color: theme.mut, fontFamily: hand, fontSize: size + 4, fontWeight: 700, lineHeight: 1.1 }}>
        {p.columns.map((c, j) => <div key={j} style={{ ...cell(widths[j]), paddingBottom: 4 }}>{c}</div>)}
      </div>
      {p.rows.map((r, i) => {
        const a = k(r.at);
        const pr = prog(f, a);
        const tone = r.tone ?? "ink";
        return (
          <div key={i} style={{
            position: "relative", zIndex: 0, display: "flex", alignItems: "center", opacity: pr, transform: `translateY(${(1 - pr) * 12}px)`,
            marginTop: 10, fontSize: size, color: theme.ink,
          }}>
            <SketchRect drawAt={a} color={toneColor(tone)} fill={tone === "ink" ? "#FFFFFF" : tonePastel(tone)} sw={tone === "ink" ? 2.5 : 3.5} />
            {Array.from({ length: ncol }, (_, j) => (
              <div key={j} data-ty="body" style={{ ...cell(widths[j]), fontWeight: j === 0 ? 700 : 500, lineHeight: 1.25, color: j > 0 && tone !== "ink" ? toneColor(tone) : theme.ink }}>
                {keepUnits(r.cells[j] ?? "")}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------- equation

const equationSize = (p: EquationPanel, w: number) => {
  const maxLen = Math.max(...p.lines.map((l) => l.text.length), 8);
  return clampN((w - 40) / (maxLen * 0.47), w >= WIDE ? 40 : 34, p.lines.length <= 3 ? 72 : 62);
};

export const EquationView: React.FC<P<EquationPanel>> = ({ p, k, w }) => {
  const f = useCurrentFrame();
  const size = equationSize(p, w);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 26, maxWidth: w }}>
      {p.lines.map((l, i) => {
        const a = k(l.at);
        const text = keepUnits(l.text);
        return (
          <div key={i} style={{ minHeight: size * 1.15, opacity: f >= a - 4 ? 1 : 0 }}>
            <HandwriteBox text={text} size={size}>
              <Handwrite text={text} at={a + 6} size={size} color={toneColor(l.tone)} />
            </HandwriteBox>
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------- compare

const compareSizes = (p: ComparePanel, w: number) => {
  const wide = w >= WIDE;
  const gap = wide ? 50 : 36;
  const cw = (w - gap) / 2;
  const maxLen = Math.max(...[...p.left.items, ...p.right.items].map((t) => t.length), 12);
  // wide: one line per item when it fits; narrow: two lines per item
  const item = wide ? clampN((cw - 100) / (maxLen * W_INTER), 32, 42) : clampN((2 * (cw - 90)) / (maxLen * W_INTER), 26, 34);
  return { gap, item, title: wide ? 46 : 38 };
};

export const CompareView: React.FC<P<ComparePanel>> = ({ p, k, w }) => {
  const s = compareSizes(p, w);
  const side = (x: ComparePanel["left"], a: number, color: string) => (
    <Appear at={a} style={{ minWidth: 0 }}>
      <SideBox at={a}>
        <Kicker color={color} style={{ fontSize: s.title }}>{keepUnits(x.title)}</Kicker>
        {x.items.map((t, i) => (
          <div key={i} style={{ fontSize: s.item, fontWeight: 600, marginTop: 14, lineHeight: 1.3, display: "flex", gap: 12 }}>
            <span style={{ flex: "none" }}>·</span><span data-ty="sec">{keepUnits(t)}</span>
          </div>
        ))}
      </SideBox>
    </Appear>
  );
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: s.gap, alignItems: "start", width: "max-content", maxWidth: w }}>
      {side(p.left, k(p.at_left), C.router)}
      {side(p.right, k(p.at_right), C.cascade)}
    </div>
  );
};

const SideBox: React.FC<{ at: number; children: React.ReactNode }> = ({ at: a, children }) => (
  <Panel drawAt={a} style={{ padding: "26px 34px" }}>{children}</Panel>
);

// ---------------------------------------------------------------- prompt

const promptSize = (p: PromptPanel, w: number) => {
  const maxLen = Math.max(...p.lines.map((l) => l.text.length), p.title ? p.title.length * 0.5 : 0, 10);
  return clampN((w - 90) / (maxLen * W_MONO), 24, w >= WIDE ? 40 : 34);
};

export const PromptView: React.FC<P<PromptPanel>> = ({ p, k, w }) => {
  const size = promptSize(p, w);
  const first = Math.min(...p.lines.map((l) => k(l.at)));
  return (
    <Appear at={first} dy={0} style={{ display: "inline-block", maxWidth: w }}>
      {/* data-ty carries the line size for the debug probe; MonoLines sets its own fonts */}
      <div data-ty="sec" style={{ fontSize: size }}>
        <MonoLines
          drawAt={first}
          size={size}
          title={p.title}
          lines={p.lines.map((l) => ({ text: l.text, at: k(l.at), color: l.tone && l.tone !== "ink" ? toneColor(l.tone) : undefined }))}
        />
      </div>
    </Appear>
  );
};

// ---------------------------------------------------------------- one panel in its box

const Body: React.FC<P<PanelT>> = ({ p, k, w }) => {
  switch (p.kind) {
    case "chips": return <ChipsView p={p} k={k} w={w} />;
    case "flow": return <FlowView p={p} k={k} w={w} />;
    case "stats": return <StatsView p={p} k={k} w={w} />;
    case "bars": return <BarsView p={p} k={k} w={w} />;
    case "table": return <TableView p={p} k={k} w={w} />;
    case "equation": return <EquationView p={p} k={k} w={w} />;
    case "compare": return <CompareView p={p} k={k} w={w} />;
    case "prompt": return <PromptView p={p} k={k} w={w} />;
  }
};

/** How far a panel may grow: until its largest text reaches the on-screen maximum. */
export const capOf = (p: PanelT, w: number): number => {
  switch (p.kind) {
    case "chips": return MAX.body / chipsSize(w);
    case "flow": { const s = flowSizes(p, w); return Math.min(MAX.body / s.label, MAX.sec / s.sub); }
    case "stats": { const s = statsSizes(p, w); return Math.min(MAX.value / (s.size * 1.12), MAX.body / s.label); }
    case "bars": { const s = barsSizes(p, w); return Math.min(MAX.body / s.label, 1.3); }
    case "table": return 48 / tableSizes(p, w).size;
    case "equation": return MAX.handLine / equationSize(p, w);
    case "compare": { const s = compareSizes(p, w); return Math.min(MAX.compare / s.item, MAX.title / s.title); }
    case "prompt": return MAX.mono / promptSize(p, w);
  }
};

/**
 * A panel with its caption above and its note (and a step's source) under it, fitted to w x h and
 * centred in the box height. `hug` makes the box as tall as the panel (the mechanism's side panel).
 */
export const PanelView: React.FC<{
  p: PanelT; k: K; w: number; h: number; source?: string; grow?: number; valign?: "top" | "center"; hug?: boolean;
}> = ({ p, k, w, h, source, grow, valign = "center", hug = false }) => {
  const a = panelStart(p, k);
  return (
    <FitBox w={w} h={h} grow={grow ?? Math.max(1, capOf(p, w))} valign={valign} hug={hug}>
      {p.caption ? <PanelCaption at={a} w={w}>{keepUnits(p.caption)}</PanelCaption> : null}
      <div data-fit-body="" style={{ width: "max-content", maxWidth: w }}><Body p={p} k={k} w={w} /></div>
      {p.note ? <GreyNote at={a + 20} w={w}>{keepUnits(p.note)}</GreyNote> : null}
      {source ? <GreyNote at={a + 20} w={w}>Source: {keepUnits(source)}</GreyNote> : null}
    </FitBox>
  );
};
