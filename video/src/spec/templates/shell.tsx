import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Captions, Marker, hand, theme, type BeatT } from "../../kit-sketch/visuals";
import { FitBox } from "./common";

// The kit's BeatShell, copied so the kit stays unchanged: the only difference is the audio path, which
// may be the public dir itself (audioDir ""), because scripts/render.mjs points the public dir at out/<id>/audio.

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const audioPath = (audioDir: string, id: string) => staticFile(audioDir ? `${audioDir.replace(/\/+$/, "")}/${id}.mp3` : `${id}.mp3`);

export const SpecBeatShell: React.FC<{
  beat: BeatT;
  until: number; // absolute frame where the next beat starts; the visual holds until then
  audioDir: string;
  heading?: string; // handwritten heading, top left
  headingW?: number; // room left of the corner label; a longer heading is scaled down to fit
  noCaptions?: boolean;
  drift?: boolean;
  children: React.ReactNode;
}> = ({ beat, until, audioDir, heading, headingW = 1100, noCaptions, drift = false, children }) => {
  const len = Math.max(1, until - beat.start);
  return (
    <Sequence from={beat.start} durationInFrames={len} name={beat.id}>
      <FadeBlock hold={len} drift={drift}>{children}</FadeBlock>
      {heading ? <Heading text={heading} hold={len} w={headingW} /> : null}
      <Sequence from={beat.captions[0]?.start ?? 0} layout="none">
        <Audio src={audioPath(audioDir, beat.id)} />
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

const Heading: React.FC<{ text: string; hold: number; w: number }> = ({ text, hold, w }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, 10, hold - 10, hold], [0, 1, 1, 0], clamp);
  return (
    <div style={{ position: "absolute", left: 96, top: 22, opacity: o }}>
      <FitBox w={w} h={84}>
        <div style={{ fontFamily: hand, fontSize: 62, fontWeight: 700, color: theme.ink, whiteSpace: "nowrap", lineHeight: 1.2 }}>
          <Marker at={6}>{text}</Marker>
        </div>
      </FitBox>
    </div>
  );
};
