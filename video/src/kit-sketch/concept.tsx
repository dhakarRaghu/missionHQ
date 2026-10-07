import React from "react";
import { AbsoluteFill } from "remotion";
import { Appear, C, Kicker, Numbered, Panel, Phase, at, font, hand, theme, type BeatT } from "./visuals";
import { ConceptRail, Handwrite, KeyPoint } from "./teach";

// One concept taught in the Mission HQ tutor order (references/teaching-method.md in the skill).
// Generalised from the Phase 2 build. The caller supplies the scenes; this file fixes the order,
// the step rail and the think-it-through and key-point layouts.
//
// Narration keys the beat must have, in this order:
//   claim line (any key) · s0 situation · p0 picture · q0 givens · q1 question · t1 first thought
//   t2 what it misses · t3 real question · <step keys> mechanism · n0 the number · r0 r1 r2 key points
//   h0 what is still open · h1 the next concept's question

export const STAGES = ["Situation", "Picture", "Think it through", "Mechanism", "The number", "Key points", "Next"];

export type Think = {
  givens?: React.ReactNode;   // shown from q0
  question: React.ReactNode;  // shown from q1
  first: string;              // handwritten from t1, struck through at t2
  misses: string;             // handwritten in orange from t2
  real: React.ReactNode;      // boxed from t3
  size?: number;
};

export const Concept: React.FC<{
  B: BeatT;
  n: number;                        // this concept's number
  of: number;                       // concepts in the video
  claim: React.ReactNode;
  situation: React.ReactNode;
  picture: React.ReactNode;
  think: Think;
  steps: { text: React.ReactNode; key: string }[];
  mech: React.ReactNode;            // right side of the mechanism, positioned by the caller
  stepsW?: number;
  stepSize?: number;
  number: React.ReactNode;
  remember: React.ReactNode;
  trap: React.ReactNode;
  tryThis: React.ReactNode;
  done: string;                     // one sentence: what this concept did not explain
  next: { label: string; q: string };
}> = ({ B, n, of, claim, situation, picture, think, steps, mech, stepsW = 760, stepSize = 32, number, remember, trap, tryThis, done, next }) => {
  const k = (key: string) => at(B, key);
  const starts = [k("s0"), k("p0"), k("q0"), k(steps[0].key), k("n0"), k("r0"), k("h0")];
  return (
    <AbsoluteFill>
      <ConceptRail stages={STAGES} starts={starts} from={k("s0")} />

      <Phase from={0} to={k("s0")}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", textAlign: "center", padding: "0 170px" }}>
          <Kicker style={{ fontSize: 50 }}>Concept {n} of {of}</Kicker>
          <div style={{ fontFamily: hand, fontSize: 80, fontWeight: 700, lineHeight: 1.14, marginTop: 18 }}>{claim}</div>
        </AbsoluteFill>
      </Phase>

      <Phase from={k("s0")} to={k("p0")}>{situation}</Phase>
      <Phase from={k("p0")} to={k("q0")}>{picture}</Phase>

      <Phase from={k("q0")} to={k(steps[0].key)}>
        <div style={{ position: "absolute", left: 140, right: 140, top: 180 }}>
          {think.givens ? <Appear at={k("q0")} style={{ marginBottom: 22 }}>{think.givens}</Appear> : null}
          <Appear at={k("q1")}>
            <div style={{ fontFamily: hand, fontSize: 60, fontWeight: 700, lineHeight: 1.12 }}>{think.question}</div>
          </Appear>
          <Appear at={k("t1")} style={{ marginTop: 30 }}>
            <Kicker color={theme.mut}>First thought</Kicker>
            <Handwrite text={think.first} at={k("t1") + 10} size={think.size ?? 50} color={theme.mut} strikeAt={k("t2")} />
          </Appear>
          <Appear at={k("t2")} style={{ marginTop: 24 }}>
            <Kicker>What it misses</Kicker>
            <Handwrite text={think.misses} at={k("t2") + 10} size={think.size ?? 50} color={C.cascade} />
          </Appear>
          <Appear at={k("t3")} style={{ marginTop: 32 }}>
            <Panel hotAt={k("t3")} style={{ padding: "16px 30px", display: "inline-block" }}>
              <span style={{ fontFamily: font, fontSize: 36, fontWeight: 600 }}>{think.real}</span>
            </Panel>
          </Appear>
        </div>
      </Phase>

      <Phase from={k(steps[0].key)} to={k("n0")}>
        <div style={{ position: "absolute", left: 110, top: 200, width: stepsW }}>
          <Numbered size={stepSize} gap={30} items={steps.map((s) => ({ text: s.text, at: k(s.key) }))} />
        </div>
        {mech}
      </Phase>

      <Phase from={k("n0")} to={k("r0")}>{number}</Phase>

      <Phase from={k("r0")} to={k("h0")}>
        <div style={{ position: "absolute", left: 160, right: 160, top: 190, display: "flex", flexDirection: "column", gap: 26 }}>
          <KeyPoint kind="remember" at={k("r0")}>{remember}</KeyPoint>
          <KeyPoint kind="trap" at={k("r1")}>{trap}</KeyPoint>
          <KeyPoint kind="try" at={k("r2")}>{tryThis}</KeyPoint>
        </div>
      </Phase>

      <Phase from={k("h0")}>
        <div style={{ position: "absolute", left: 160, right: 160, top: 300 }}>
          <Appear at={k("h0")}>
            <div style={{ fontFamily: font, fontSize: 36, color: theme.mut }}>{done}</div>
          </Appear>
          <Appear at={k("h1")} style={{ marginTop: 30 }}>
            <Panel hotAt={k("h1")} hot={C.router} style={{ padding: "30px 40px" }}>
              <Kicker color={C.router}>{next.label}</Kicker>
              <div style={{ fontFamily: hand, fontSize: 76, fontWeight: 700, marginTop: 6 }}>{next.q}</div>
            </Panel>
          </Appear>
        </div>
      </Phase>
    </AbsoluteFill>
  );
};
