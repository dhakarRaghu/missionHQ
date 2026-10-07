import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, type CalculateMetadataFunction } from "remotion";
import { Lesson, font, theme } from "./kit-sketch/visuals";
import type { SpecVideoProps, TimingBeat } from "./spec/types";
import { toBeatT } from "./spec/templates/common";
import { SpecBeatShell } from "./spec/templates/shell";
import { ConceptBeat } from "./spec/templates/concept";
import { ColdBeat, EndBeat, PayoffBeat, RecapBeat, TitleBeat } from "./spec/templates/beats";

// The whole video from { spec, timing, audioDir }. Every beat is a Sequence that starts at the frame the
// timing file gives it, with its own audio file, so a long video cannot drift: each beat re-anchors.

export const calculateSpecMetadata: CalculateMetadataFunction<SpecVideoProps> = ({ props }) => ({
  durationInFrames: props.timing?.totalFrames ?? 150,
  fps: props.timing?.fps ?? 30,
});

export const SpecVideo: React.FC<SpecVideoProps> = ({ spec, timing, audioDir }) => {
  const f = useCurrentFrame();
  if (!timing) {
    return (
      <AbsoluteFill style={{ background: theme.bg, alignItems: "center", justifyContent: "center", fontFamily: font, fontSize: 40, color: theme.mut }}>
        No timing file. Run scripts/narrate.mjs, then pass its output as the timing prop.
      </AbsoluteFill>
    );
  }
  const total = timing.totalFrames;
  const outro = interpolate(f, [total - 24, total], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  // the heading must end before the corner label (Caveat 34 px, about 17 px a character)
  const headingW = Math.min(1500, 1920 - 96 - 64 - spec.label.length * 17 - 48);
  const order = spec.beats.map((b) => b.id);
  const until = (i: number) => {
    const nextId = order[i + 1];
    return nextId ? timing.beats[nextId].start : total;
  };
  return (
    <Lesson label={spec.label}>
      {spec.beats.map((beat, i) => {
        const t: TimingBeat | undefined = timing.beats[beat.id];
        if (!t) throw new Error(`Beat "${beat.id}" is missing in the timing file`);
        const B = toBeatT(t);
        const shell = { key: beat.id, beat: B, until: until(i), audioDir };
        switch (beat.kind) {
          case "cold":
            return <SpecBeatShell {...shell}><ColdBeat beat={beat} t={t} /></SpecBeatShell>;
          case "title":
            return <SpecBeatShell {...shell} noCaptions><TitleBeat spec={spec} beat={beat} t={t} hold={until(i) - t.start} /></SpecBeatShell>;
          case "concept":
            return <SpecBeatShell {...shell} heading={beat.heading} headingW={headingW}><ConceptBeat beat={beat} t={t} /></SpecBeatShell>;
          case "payoff":
            return <SpecBeatShell {...shell} heading={beat.heading} headingW={headingW}><PayoffBeat beat={beat} t={t} /></SpecBeatShell>;
          case "recap":
            return <SpecBeatShell {...shell} heading={beat.heading ?? "Recap"} headingW={headingW} drift><RecapBeat t={t} /></SpecBeatShell>;
          case "end":
            return <SpecBeatShell {...shell}><EndBeat spec={spec} t={t} /></SpecBeatShell>;
        }
      })}
      <AbsoluteFill style={{ background: theme.bg, opacity: outro, pointerEvents: "none" }} />
    </Lesson>
  );
};

