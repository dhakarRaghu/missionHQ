/**
 * Remotion CLI config. The Node APIs (scripts/render.mjs stills) do not read this file;
 * they pass the same options directly.
 */
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);

// YouTube uploads (YT=1): keyframe every 0.5 s at 30 fps and the moov atom first (fast start).
// Needs --disallow-parallel-encoding, or Remotion can skip the stitcher step where this runs.
if (process.env.YT === "1") {
  Config.overrideFfmpegCommand(({ type, args }) => {
    if (type !== "stitcher") return args;
    const out = args[args.length - 1];
    return [...args.slice(0, -1), "-g", "15", "-movflags", "+faststart", out];
  });
}
