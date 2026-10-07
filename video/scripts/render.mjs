#!/usr/bin/env node
/**
 * render.mjs: renders a spec video, or stills of it.
 *
 *   node scripts/render.mjs <outDir> <id> [--scale=1|2] [--stills=auto|<beatId>|<frame,frame,...>] [--audio-only]
 *                           [--spec=<spec.json>] [--timing=<timing.json>] [--audio=<audioDir>]
 *
 * Inputs (defaults): <outDir>/<id>.spec.json, <outDir>/<id>.timing.json, <outDir>/audio/<beat>.mp3.
 *
 * Full video (no --stills):
 *   <outDir>/<id>.mp4 (scale 1, 1920x1080) or <outDir>/<id>-4K.mp4 (scale 2, 3840x2160), H.264 CRF 18,
 *   x264 slow, yuv420p, BT.709, AAC 384 kbps 48 kHz, keyframe every 0.5 s, faststart (YT=1 override in
 *   remotion.config.ts, which needs --disallow-parallel-encoding). Also writes <outDir>/props.json.
 *
 * Audio only (--audio-only): <outDir>/<id>-audio.wav, the soundtrack without drawing frames, for
 *   verify.mjs --sync-only on a long video.
 *
 * Stills (JPEG quality 85, at --scale):
 *   --stills=auto       one still per scene step, 0.5 s before the next step starts:
 *                       <outDir>/stills/<beat>__<step>.jpg, <outDir>/stills/index.json
 *                       ([{file, beat, step, frame, keys}]), and the tiled <outDir>/sheet.jpg
 *   --stills=<beatId>   the same for one beat only; index.json and sheet.jpg are updated for that beat
 *   --stills=10,200     those absolute frames: <outDir>/stills/frame-<n>.jpg
 * Never run two renders at once on one machine: one render keeps every core busy.
 */
import { spawnSync, execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { scenes } from "./lib/scenes.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const flags = Object.fromEntries(args.filter((a) => a.startsWith("--")).map((a) => {
  const [k, ...v] = a.slice(2).split("=");
  return [k, v.join("=") || "true"];
}));
const [outDirArg, id] = args.filter((a) => !a.startsWith("--"));
if (!outDirArg || !id) {
  console.error("usage: render.mjs <outDir> <id> [--scale=1|2] [--stills=auto|<beatId>|<frames>] [--spec=] [--timing=] [--audio=]");
  process.exit(2);
}
const outDir = resolve(outDirArg);
const scale = Number(flags.scale ?? 1);
if (![1, 2].includes(scale)) { console.error("--scale must be 1 or 2"); process.exit(2); }
const specPath = resolve(flags.spec ?? join(outDir, `${id}.spec.json`));
const timingPath = resolve(flags.timing ?? join(outDir, `${id}.timing.json`));
const audioDir = resolve(flags.audio ?? join(outDir, "audio"));
for (const p of [specPath, timingPath]) if (!existsSync(p)) { console.error(`missing ${p}`); process.exit(2); }
const spec = JSON.parse(readFileSync(specPath, "utf8"));
const timing = JSON.parse(readFileSync(timingPath, "utf8"));
// The public dir is the audio folder itself, so the bundle copies only the beat MP3s.
const props = { spec, timing, audioDir: "" };
mkdirSync(outDir, { recursive: true });
const propsPath = join(outDir, "props.json");
writeFileSync(propsPath, JSON.stringify(props));

if (flags.stills) await stills(flags.stills);
else if (flags["audio-only"]) audioOnly();
else video();

/** The soundtrack alone as WAV (no frames are drawn), for verify.mjs --sync-only on a long video. */
function audioOnly() {
  const out = join(outDir, `${id}-audio.wav`);
  const cli = join(root, "node_modules/.bin/remotion");
  const cmd = ["render", "src/index.ts", "SpecVideo", out, `--props=${propsPath}`, `--public-dir=${audioDir}`, "--codec=wav", "--sample-rate=48000", "--log=warn"];
  const t0 = Date.now();
  const r = spawnSync(cli, cmd, { cwd: root, stdio: "inherit" });
  if (r.status !== 0) process.exit(r.status ?? 1);
  console.log(`Wrote ${out} in ${((Date.now() - t0) / 1000).toFixed(0)} s`);
}

function video() {
  const out = join(outDir, scale === 2 ? `${id}-4K.mp4` : `${id}.mp4`);
  const cli = join(root, "node_modules/.bin/remotion");
  const cmd = [
    "render", "src/index.ts", "SpecVideo", out, `--props=${propsPath}`, `--public-dir=${audioDir}`,
    `--scale=${scale}`, "--codec=h264", "--crf=18", "--x264-preset=slow", "--pixel-format=yuv420p", "--color-space=bt709",
    "--audio-bitrate=384k", "--sample-rate=48000", "--disallow-parallel-encoding", "--log=info",
  ];
  console.log(`remotion ${cmd.join(" ")}`);
  const t0 = Date.now();
  const r = spawnSync(cli, cmd, { cwd: root, stdio: "inherit", env: { ...process.env, YT: "1" } });
  if (r.status !== 0) process.exit(r.status ?? 1);
  console.log(`Wrote ${out} in ${((Date.now() - t0) / 1000).toFixed(0)} s`);
}

async function stills(what) {
  const { bundle } = await import("@remotion/bundler");
  const { renderStill, selectComposition } = await import("@remotion/renderer");
  const dir = join(outDir, "stills");
  mkdirSync(dir, { recursive: true });
  const all = scenes(spec, timing);
  let jobs;
  const numeric = /^[0-9,\s]+$/.test(what);
  if (numeric) {
    jobs = what.split(",").filter(Boolean).map((f) => ({ file: `frame-${Number(f)}.jpg`, frame: Number(f) }));
  } else {
    const pick = what === "auto" || what === "steps" ? all : all.filter((s) => s.beat === what);
    if (!pick.length) { console.error(`no scenes for "${what}"; beats: ${spec.beats.map((b) => b.id).join(", ")}`); process.exit(2); }
    jobs = pick.map((s) => {
      const tb = timing.beats[s.beat];
      const keys = tb.steps.filter((l) => tb.start + l.start >= s.from && tb.start + l.start < s.to).map((l) => l.key);
      return { file: `${s.beat}__${s.name.replace(/\./g, "-")}.jpg`, beat: s.beat, step: s.name, frame: s.still, keys };
    });
  }
  const t0 = Date.now();
  const serveUrl = await bundle({ entryPoint: join(root, "src/index.ts"), publicDir: audioDir });
  const composition = await selectComposition({ serveUrl, id: "SpecVideo", inputProps: props });
  for (const j of jobs) {
    await renderStill({ serveUrl, composition, frame: j.frame, output: join(dir, j.file), imageFormat: "jpeg", jpegQuality: 85, scale, inputProps: props });
    console.log(join(dir, j.file));
  }
  if (!numeric) {
    // merge with an existing index so --stills=<beat> updates one beat only, then keep video order
    const indexPath = join(dir, "index.json");
    const old = existsSync(indexPath) && what !== "auto" && what !== "steps" ? JSON.parse(readFileSync(indexPath, "utf8")) : [];
    const byFile = new Map(old.map((e) => [e.file, e]));
    for (const j of jobs) byFile.set(j.file, { file: j.file, beat: j.beat, step: j.step, frame: j.frame, keys: j.keys });
    const index = [...byFile.values()].sort((a, b) => a.frame - b.frame);
    writeFileSync(indexPath, JSON.stringify(index, null, 1) + "\n");
    sheet(index.map((e) => join(dir, e.file)), join(outDir, "sheet.jpg"));
    console.log(`Wrote ${index.length} entries to ${indexPath} and ${join(outDir, "sheet.jpg")}`);
  }
  console.log(`${jobs.length} stills in ${((Date.now() - t0) / 1000).toFixed(0)} s`);
}

/** Tiles stills 6 across at 320 px each, in index order. */
function sheet(files, out) {
  const cols = 6;
  const inputs = files.flatMap((f) => ["-i", f]);
  const n = files.length;
  const filt = files.map((_, i) => `[${i}:v]scale=320:-1,setsar=1[v${i}]`).join(";") +
    ";" + files.map((_, i) => `[v${i}]`).join("") + `xstack=inputs=${n}:layout=${files.map((_, i) => `${(i % cols) * 326}_${Math.floor(i / cols) * 186}`).join("|")}:fill=white[out]`;
  if (n === 1) {
    execFileSync("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", "-i", files[0], "-vf", "scale=320:-1", "-q:v", "5", out]);
    return;
  }
  execFileSync("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", ...inputs, "-filter_complex", filt, "-map", "[out]", "-q:v", "5", out]);
}
