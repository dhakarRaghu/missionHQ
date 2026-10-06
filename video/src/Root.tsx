import React from "react";
import { Composition } from "remotion";
import { SpecVideo, calculateSpecMetadata } from "./SpecVideo";
import type { SpecVideoProps, VideoSpec } from "./spec/types";
import ep12 from "../examples/ep12/ep12.spec.json";

// One composition. It takes { spec, timing, audioDir } as input props (scripts/render.mjs writes them).
// The default props show the ep12 example without timing, so Studio opens; a real render passes --props.
const defaults: SpecVideoProps = { spec: ep12 as unknown as VideoSpec, timing: null, audioDir: "" };

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="SpecVideo" component={SpecVideo} width={1920} height={1080} fps={30} durationInFrames={150}
      defaultProps={defaults} calculateMetadata={calculateSpecMetadata} />
  </>
);
