import React from "react";
import { AbsoluteFill, Freeze } from "remotion";
import { Appear, C, Kicker, Numbered, Panel, Phase, font, hand, theme } from "../../kit-sketch/visuals";
import { ConceptRail, Handwrite, KeyPoint } from "../../kit-sketch/teach";
import type {
  Beat, BridgeStep, MechanismStep, NumberStep, Panel as PanelT, PictureStep, SituationStep, Step, ThinkStep, TimingBeat,
} from "../types";
import { FitBox, HandwriteBox, MarkText, Reserve, cleanQuestion, firstOf, keepUnits, keyFrame, linesOf, panelStart, stripLead, type K } from "./common";
import { PanelView } from "./panels";

// One concept beat in the Mission HQ tutor order, drawn from the spec: one template per step
// (claim, situation, picture, think, mechanism, number, keypoints, bridge). Copied in shape from
// course-videos InfEp12.kit.tsx StoryConcept: "1 of 3" claim card, the step rail, and the story bridge
// from the first `h` line, during which the rail hides.

export const STAGES = ["Situation", "Picture", "Think it through", "Mechanism", "The number", "Key points"];

/**
 * The content box: from under the step rail (it ends near y = 150) to above the caption bar (it starts
 * near y = 950). Every step centres its content in this height.
 */
export const BOX = { left: 120, top: 172, w: 1680, h: 756 };

type Visual = { panel?: PanelT; panels?: PanelT[] };
export const panelsOf = (s: Visual): PanelT[] => (s.panels ? s.panels : s.panel ? [s.panel] : []);

/**
 * Panels shown one after another: each holds from its first element (the first from `from`) until the
 * next panel's first element, so the screen changes when the voice reaches the next visual.
 */
export const PanelSeq: React.FC<{
  panels: PanelT[]; k: K; from: number; to: number; box?: { left: number; top: number; w: number; h: number }; source?: string;
}> = ({ panels, k, from, to, box = BOX, source }) => {
  const starts = panels.map((p, i) => (i === 0 ? from : panelStart(p, k)));
  return (
    <>
      {panels.map((p, i) => (
        <Phase key={i} from={starts[i]} to={i + 1 < panels.length ? starts[i + 1] : to}>
          <div style={{ position: "absolute", left: box.left, top: box.top }}>
            <PanelView p={p} k={k} w={box.w} h={box.h} source={source} valign="center" />
          </div>
        </Phase>
      ))}
    </>
  );
};

// ---------------------------------------------------------------- step templates

export const ClaimCard: React.FC<{ count?: string; claim: string; mark?: string; markAt: number }> = ({ count, claim, mark, markAt }) => (
  <div style={{ position: "absolute", left: 170, top: 130, width: 1580, height: 780 }}>
    <FitBox w={1580} h={780} align="center" valign="center">
      {count ? <Kicker style={{ fontSize: 50 }}>{count}</Kicker> : null}
      <div style={{ fontFamily: hand, fontSize: 80, fontWeight: 700, lineHeight: 1.14, marginTop: 18, textAlign: "center" }}>
        <MarkText text={claim} mark={mark} at={markAt} />
      </div>
    </FitBox>
  </div>
);

export const ThinkView: React.FC<{ s: ThinkStep; b: TimingBeat; k: K }> = ({ s, b }) => {
  const q = linesOf(b, "q");
  const t = linesOf(b, "t");
  const question = q.length ? q[q.length - 1] : null;
  const givens = q.length > 1 ? q.slice(0, -1) : [];
  return (
    <div style={{ position: "absolute", left: 140, top: BOX.top }}>
      {/* The whole block scales (reflow: the printed lines rewrap at the scaled width; the handwritten lines
          never wrap and limit the scale), so pen and strike-through stay on their text. */}
      <FitBox w={1640} h={BOX.h} valign="center" reflow grow={1.4} fill={0.7}>
        {givens.map((g) => (
          <Appear key={g.key} at={g.at} style={{ marginBottom: 18 }}>
            <div style={{ fontFamily: font, fontSize: 32, color: theme.mut, lineHeight: 1.3 }}>{keepUnits(cleanQuestion(g.text))}</div>
          </Appear>
        ))}
        {question ? (
          <Appear at={question.at}>
            <div style={{ fontFamily: hand, fontSize: 60, fontWeight: 700, lineHeight: 1.12 }}>{keepUnits(cleanQuestion(question.text))}</div>
          </Appear>
        ) : null}
        {t[0] ? (
          <Appear at={t[0].at} style={{ marginTop: 30 }}>
            <Kicker color={theme.mut}>First thought</Kicker>
            <HandwriteBox text={keepUnits(s.first)} size={50}>
              <Handwrite text={keepUnits(s.first)} at={t[0].at + 10} size={50} color={theme.mut} strikeAt={t[1]?.at} />
            </HandwriteBox>
          </Appear>
        ) : null}
        {t[1] ? (
          <Appear at={t[1].at} style={{ marginTop: 24 }}>
            <Kicker>What it misses</Kicker>
            <HandwriteBox text={keepUnits(s.misses)} size={50}>
              <Handwrite text={keepUnits(s.misses)} at={t[1].at + 10} size={50} color={C.cascade} />
            </HandwriteBox>
          </Appear>
        ) : null}
        {t[2] ? (
          <Appear at={t[2].at} style={{ marginTop: 32 }}>
            <Panel hotAt={t[2].at} drawAt={t[2].at} style={{ padding: "16px 30px", display: "inline-block" }}>
              <span style={{ fontFamily: font, fontSize: 36, fontWeight: 600 }}>{keepUnits(s.real)}</span>
            </Panel>
          </Appear>
        ) : null}
      </FitBox>
    </div>
  );
};

/**
 * The numbered steps on the left and the optional side panel on the right, tops aligned, the pair centred
 * in the content height. Each box is as tall as its content (hug), so the flex row can centre them.
 */
export const MechanismView: React.FC<{ s: MechanismStep; k: K; from: number; to: number }> = ({ s, k }) => {
  const listW = s.side ? 700 : 1600;
  const size = s.side ? 36 : 42;
  return (
    <div style={{ position: "absolute", left: 110, top: BOX.top, width: 1700, height: BOX.h, display: "flex", alignItems: "center" }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 50 }}>
        <FitBox w={listW} h={BOX.h} grow={(s.side ? 39 : 48) / size} reflow hug>
          <Numbered size={size} gap={s.side ? 26 : 30} items={s.items.map((it) => ({
            // balanced lines: a wrapped item splits in two even halves instead of leaving one word alone
            text: <span data-ty="body" style={{ display: "block", textWrap: "balance" } as React.CSSProperties}>{keepUnits(it.text)}</span>, at: k(it.at),
          }))} />
        </FitBox>
        {s.side ? <PanelView p={s.side} k={k} w={950} h={BOX.h} valign="top" hug /> : null}
      </div>
    </div>
  );
};

/**
 * The three key points, centred in the content height. Each one keeps its space from the start (a frozen,
 * hidden copy), because the kit's KeyPoint draws nothing before its line and the block would move.
 */
export const KeypointsView: React.FC<{ b: TimingBeat }> = ({ b }) => {
  const r = linesOf(b, "r").slice(0, 3);
  const kinds = ["remember", "trap", "try"] as const;
  const kindOf = (text: string, i: number) =>
    /^remember/i.test(text) ? "remember" : /^the trap/i.test(text) ? "trap" : /^try this/i.test(text) ? "try" : kinds[i];
  return (
    <div style={{ position: "absolute", left: 160, top: BOX.top }}>
      <FitBox w={1600} h={BOX.h} valign="center" grow={1.2} reflow>
        <div style={{ display: "flex", flexDirection: "column", gap: 26, width: "100%" }}>
          {r.map((l, i) => {
            const kp = (key: string) => <KeyPoint key={key} kind={kindOf(l.text, i)} at={l.at}>{keepUnits(stripLead(l.text))}</KeyPoint>;
            return (
              <Reserve key={l.key} style={{ justifyItems: "stretch" }} ghost={<Freeze frame={l.at + 90}>{kp("ghost")}</Freeze>}>
                {kp("real")}
              </Reserve>
            );
          })}
        </div>
      </FitBox>
    </div>
  );
};

// ---------------------------------------------------------------- the concept beat

const find = <S extends Step["step"]>(steps: Step[], name: S) => steps.find((s) => s.step === name) as Extract<Step, { step: S }> | undefined;

export const ConceptBeat: React.FC<{ beat: Beat; t: TimingBeat }> = ({ beat, t }) => {
  const k = keyFrame(t);
  const steps = beat.steps ?? [];
  const end = 1e9;
  const s0 = firstOf(t, "s") ?? end;
  const p0 = firstOf(t, "p") ?? s0;
  const q0 = firstOf(t, "q") ?? firstOf(t, "t") ?? p0;
  const m0 = firstOf(t, "m") ?? q0;
  const n0 = firstOf(t, "n") ?? m0;
  const r0 = firstOf(t, "r") ?? n0;
  const bridge = find(steps, "bridge") as BridgeStep | undefined;
  const h0 = bridge ? firstOf(t, "h") ?? end : end;
  const claim = linesOf(t, "k").map((l) => l.text).join(" ");
  const situation = find(steps, "situation") as SituationStep | undefined;
  const picture = find(steps, "picture") as PictureStep | undefined;
  const think = find(steps, "think") as ThinkStep | undefined;
  const mech = find(steps, "mechanism") as MechanismStep | undefined;
  const num = find(steps, "number") as NumberStep | undefined;
  return (
    <AbsoluteFill>
      <Phase from={s0} to={h0}><ConceptRail stages={STAGES} starts={[s0, p0, q0, m0, n0, r0]} from={s0} /></Phase>

      <Phase from={0} to={s0}>
        <ClaimCard count={beat.count} claim={keepUnits(claim)} mark={beat.mark ? keepUnits(beat.mark) : undefined} markAt={40} />
      </Phase>

      {situation ? <PanelSeq panels={panelsOf(situation)} k={k} from={s0} to={p0} /> : null}
      {picture ? <PanelSeq panels={panelsOf(picture)} k={k} from={p0} to={q0} /> : null}
      {think ? <Phase from={q0} to={m0}><ThinkView s={think} b={t} k={k} /></Phase> : null}
      {mech ? <Phase from={m0} to={n0}><MechanismView s={mech} k={k} from={m0} to={n0} /></Phase> : null}
      {num ? <PanelSeq panels={panelsOf(num)} k={k} from={n0} to={r0} source={num.source?.text} /> : null}
      <Phase from={r0} to={h0}><KeypointsView b={t} /></Phase>

      {bridge ? (
        <>
          {bridge.label ? (
            <Phase from={h0}>
              <Appear at={h0} style={{ position: "absolute", left: 100, top: 118 }}>
                <Kicker color={C.router} style={{ fontSize: 34 }}>{bridge.label}</Kicker>
              </Appear>
            </Phase>
          ) : null}
          <PanelSeq panels={panelsOf(bridge)} k={k} from={h0} to={end} />
        </>
      ) : null}
    </AbsoluteFill>
  );
};
