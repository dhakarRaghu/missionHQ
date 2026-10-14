import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Appear, C, Kicker, Numbered, Panel, font, hand, theme } from "../../kit-sketch/visuals";
import type { Beat, Panel as PanelT, TimingBeat, VideoSpec } from "../types";
import { FitBox, MarkText, WrapChip, keepUnits, keyFrame, linesOf } from "./common";
import { PanelSeq, panelsOf } from "./concept";

// Templates for the beats that are not concepts: cold open, title, payoff, recap and end card.

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const allPanels = (beat: Beat): PanelT[] =>
  (beat.steps ?? []).flatMap((s) => ("panel" in s || "panels" in s ? panelsOf(s as { panel?: PanelT; panels?: PanelT[] }) : []));

/** Cold open: its panel steps one after another, with no heading on screen, centred above the captions. */
export const ColdBeat: React.FC<{ beat: Beat; t: TimingBeat }> = ({ beat, t }) => (
  <AbsoluteFill>
    <PanelSeq panels={allPanels(beat)} k={keyFrame(t)} from={0} to={1e9} box={{ left: 120, top: 116, w: 1680, h: 812 }} />
  </AbsoluteFill>
);

/** Payoff: like the cold open, under the beat's handwritten heading. */
export const PayoffBeat: React.FC<{ beat: Beat; t: TimingBeat }> = ({ beat, t }) => (
  <AbsoluteFill>
    <PanelSeq panels={allPanels(beat)} k={keyFrame(t)} from={0} to={1e9} box={{ left: 120, top: 140, w: 1680, h: 788 }} />
  </AbsoluteFill>
);

/** Title card: the series, the title with its highlighter words, and the concept questions as they are named. */
export const TitleBeat: React.FC<{ spec: VideoSpec; beat: Beat; t: TimingBeat; hold: number }> = ({ spec, beat, t, hold }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, 10, hold - 8, hold], [0, 1, 1, 0], clamp);
  const heads = spec.beats.filter((b) => b.kind === "concept").map((b) => b.heading ?? "");
  const lines = linesOf(t, "t");
  const intro = lines[1] ?? lines[0];
  const start = intro?.at ?? 0;
  const span = intro ? Math.max(20, (intro.end - intro.start) * 0.8) : 0;
  const two = heads.length > 5;
  return (
    <AbsoluteFill style={{ opacity: o }}>
      <div style={{ position: "absolute", left: 120, top: 110 }}>
        <FitBox w={1680} h={840} align="center" valign="center">
          <div style={{ fontFamily: hand, fontSize: 46, fontWeight: 700, color: theme.acc, textAlign: "center" }}>{spec.series.toUpperCase()}</div>
          <div style={{ fontFamily: hand, fontSize: 124, fontWeight: 700, lineHeight: 1.06, marginTop: 10, textAlign: "center", maxWidth: 1680 }}>
            <MarkText text={spec.title} mark={beat.mark} at={16} />
          </div>
          <div style={{
            display: "grid", gridTemplateColumns: two ? "820px 820px" : "auto", gap: two ? "14px 40px" : 16, marginTop: 46,
            justifyItems: two ? "start" : "center",
          }}>
            {heads.map((h, i) => (
              <Appear key={i} at={start + 10 + Math.round((span * i) / Math.max(1, heads.length))}>
                <WrapChip tone="info" solid={false} size={two ? 26 : 30}>{i + 1}. {h}</WrapChip>
              </Appear>
            ))}
          </div>
        </FitBox>
      </div>
    </AbsoluteFill>
  );
};

/** Recap: the first line as a kicker, then one numbered line per remaining `r` line, centred under the heading. */
export const RecapBeat: React.FC<{ t: TimingBeat }> = ({ t }) => {
  const r = linesOf(t, "r");
  const [head, ...items] = r.length > 1 ? r : [null, ...r];
  const many = items.length > 5;
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 160, top: 140 }}>
        <FitBox w={1600} h={788} valign="center" reflow grow={many ? 36 / 32 : 46 / 40}>
          {head ? <Appear at={head.at}><Kicker style={{ fontSize: 44 }}>{keepUnits(head.text)}</Kicker></Appear> : null}
          <div style={{ marginTop: many ? 24 : 44, width: "100%" }}>
            <Numbered size={many ? 32 : 40} gap={many ? 20 : 40} items={items.map((l) => ({ text: <span data-ty="body">{keepUnits(l!.text)}</span>, at: l!.at }))} />
          </div>
        </FitBox>
      </div>
    </AbsoluteFill>
  );
};

/**
 * End card, centred: the video's title, "In this video" with the concept headings as a numbered list
 * (two columns from seven concepts on), the next lesson when the spec names one, and where the written
 * lesson is. Everything comes from fields the spec already has.
 */
export const EndBeat: React.FC<{ spec: VideoSpec; t: TimingBeat }> = ({ spec, t }) => {
  const x = linesOf(t, "x");
  const a = x[0]?.at ?? 0;
  const yt = spec.mode === "youtube";
  const next = spec.next;
  const nextText = next && (next.title || next.number != null)
    ? [next.number != null ? `#${next.number}` : null, next.title ?? "coming soon"].filter(Boolean).join(" · ")
    : null;
  const heads = spec.beats.filter((b) => b.kind === "concept").map((b) => b.heading ?? "");
  const two = heads.length > 6;
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 120, top: 110 }}>
        <FitBox w={1680} h={818} align="center" valign="center" reflow grow={1.3} fill={0.85}>
          <Appear at={a}>
            <div style={{ fontFamily: hand, fontSize: 80, fontWeight: 700, lineHeight: 1.08, textAlign: "center" }}>{keepUnits(spec.title)}</div>
          </Appear>
          {heads.length ? (
            <Appear at={a + 12} style={{ marginTop: 40 }}>
              <Kicker style={{ fontSize: 42 }}>{yt ? "In this episode" : "In this video"}</Kicker>
              <div style={{ display: "grid", gridTemplateColumns: two ? "1fr 1fr" : "auto", columnGap: 56, rowGap: 12, marginTop: 14 }}>
                {heads.map((h, i) => (
                  <div key={i} style={{ display: "flex", gap: 14, fontFamily: font, fontSize: two ? 30 : 34, fontWeight: 600, lineHeight: 1.3 }}>
                    <span style={{ fontFamily: hand, fontWeight: 700, color: theme.acc, flex: "none", minWidth: "1.1em" }}>{i + 1}.</span>
                    <span data-ty="body">{keepUnits(h)}</span>
                  </div>
                ))}
              </div>
            </Appear>
          ) : null}
          {nextText ? (
            <Appear at={a + 30} style={{ marginTop: 40 }}>
              <Panel drawAt={a + 30} hotAt={a + 50} hot={C.router} style={{ padding: "20px 40px", textAlign: "center" }}>
                <Kicker color={C.router}>{next?.label ?? (yt ? "Next episode" : "Next lesson")}</Kicker>
                <div style={{ fontFamily: hand, fontSize: 60, fontWeight: 700, lineHeight: 1.05, color: C.router, marginTop: 4 }}>{nextText}</div>
              </Panel>
            </Appear>
          ) : null}
          {spec.site ? (
            <Appear at={a + 44} style={{ marginTop: 36 }}>
              <div data-ty="body" style={{ fontFamily: font, fontSize: 34, color: theme.mut, textAlign: "center", lineHeight: 1.3 }}>
                {yt ? "Link in the description" : "The written lesson"}: <span style={{ color: theme.ink, fontWeight: 600 }}>{spec.site}</span>
              </div>
            </Appear>
          ) : null}
        </FitBox>
      </div>
    </AbsoluteFill>
  );
};
