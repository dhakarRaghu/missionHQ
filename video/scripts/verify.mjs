#!/usr/bin/env node
/**
 * verify.mjs: checks a rendered video in code and prints one JSON object on stdout.
 *
 *   node scripts/verify.mjs <mp4> <timing.json> [--spec=<spec.json>] [--out=<dir>]
 *
 * --spec defaults to <timing dir>/<name>.spec.json when <timing> is <name>.timing.json; --out defaults to the
 * MP4's folder. Writes <out>/contact.jpg (6 frames of the MP4 tiled 3x2, for a reviewer; render.mjs --stills
 * writes the per-step <out>/sheet.jpg) and <out>/verify-frames/<beat>__<step>.jpg (the frames it checked).
 * Exit code 0 when "ok" is true, 1 otherwise, 2 for a usage error.
 *
 * JSON keys:
 *   ok                     every check below passed
 *   file, size_bytes
 *   video   { width, height, codec, pix_fmt, color_space, color_range, fps, nb_frames, duration_s }
 *   audio   { codec, sample_rate, channels, bit_rate, duration_s }
 *   frames_ok_count        nb_frames == timing totalFrames
 *   keyframes { at_s, times, max_gap_s, ok }    keyframe spacing over 4 s at the midpoint, pass <= 0.5 s
 *   loudness  { integrated_lufs, true_peak_dbtp, ok }   pass -16 <= I <= -13
 *   black     { runs, ok }                       blackdetect runs (d=0.5 s, pix_th 0.10), pass 0
 *   sync_ok, sync_max_drift_ms, sync_matched, sync_lines, sync_worst [5 x {beat, key, expected_s, onset_s, drift_ms}],
 *   sync_unmatched [{beat, key, expected_s, first_line_of_beat}], audio_video_diff_ms, total_diff_ms,
 *   sync_beat_max_drift_ms, sync_beats [{beat, expected_s, onset_s, drift_ms}]: each beat's first speech in the
 *   render against the same point in <timing dir>/audio/<beat>.mp3 (--audio=<dir> overrides; skipped when absent)
 *   frames_ok, frames { checked, thresholds, failing [{beat, step, frame, reason, value, still, frame_file}] }
 *   sheet                  path of the 6-frame contact sheet
 */
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { scenes } from "./lib/scenes.mjs";

const args = process.argv.slice(2);
const flags = Object.fromEntries(args.filter((a) => a.startsWith("--")).map((a) => { const [k, ...v] = a.slice(2).split("="); return [k, v.join("=")]; }));
const [mp4Arg, timingArg] = args.filter((a) => !a.startsWith("--"));
if (!mp4Arg || !timingArg) { console.error("usage: verify.mjs <mp4> <timing.json> [--spec=<spec.json>] [--out=<dir>]"); process.exit(2); }
const mp4 = resolve(mp4Arg);
const timing = JSON.parse(readFileSync(resolve(timingArg), "utf8"));
const specPath = flags.spec ? resolve(flags.spec) : resolve(timingArg).replace(/\.timing\.json$/, ".spec.json");
const spec = existsSync(specPath) ? JSON.parse(readFileSync(specPath, "utf8")) : null;
const outDir = resolve(flags.out || dirname(mp4));
const fps = timing.fps;

// Thresholds, calibrated on the ep12 port (README "verify thresholds").
const T = {
  syncDriftMs: 250,         // a line's measured speech onset may differ this much from its timing-file start
  syncEarlyS: 0.3,          // an onset up to this much before a line start can be that line's onset
  syncLateS: 0.6,           // and up to this much after it. Earlier onsets are pauses inside the line before.
  totalDiffMs: 100,         // audio vs video vs timing totalFrames
  inkMin: 0.004,            // share of content-area pixels darker than INK_LUMA; below = near-empty frame
  inkLuma: 200,             // paper is ~250 and the grid ~236; text and borders are darker than 200
  sameMax: 0.6,             // mean absolute grey difference (0-255) between consecutive concept scenes; below = identical
  blackMean: 20,            // mean luma below this = black frame
  blankStd: 1.5,            // luma std-dev below this over the whole frame = blank (one flat colour)
};

const sh = (cmd, a) => execFileSync(cmd, a, { maxBuffer: 1 << 28 }).toString();
const ffErr = (a) => spawnSync("ffmpeg", a, { maxBuffer: 1 << 28 }).stderr.toString();
const result = { ok: false, file: mp4, size_bytes: statSync(mp4).size };

// --sync-only: audio and timing checks only, for an audio-only render (remotion render --codec=aac) of a long video.
if (flags["sync-only"] !== undefined) {
  const pr = JSON.parse(sh("ffprobe", ["-v", "error", "-show_streams", "-show_format", "-of", "json", mp4]));
  const au = pr.streams.find((s) => s.codec_type === "audio");
  const audioS = Number(au?.duration ?? pr.format.duration);
  const slog = ffErr(["-hide_banner", "-nostats", "-i", mp4, "-af", "silencedetect=noise=-38dB:d=0.05", "-f", "null", "-"]);
  Object.assign(result, syncCheck(slog, audioS, timing.totalFrames));
  result.ok = result.sync_ok;
  console.log(JSON.stringify(result, null, 1));
  process.exit(result.ok ? 0 : 1);
}

// ---------------------------------------------------------------- streams
const probe = JSON.parse(sh("ffprobe", ["-v", "error", "-show_streams", "-show_format", "-of", "json", mp4]));
const v = probe.streams.find((s) => s.codec_type === "video");
const a = probe.streams.find((s) => s.codec_type === "audio");
const [fn, fd] = (v?.r_frame_rate ?? "0/1").split("/").map(Number);
result.video = v ? {
  width: v.width, height: v.height, codec: v.codec_name, pix_fmt: v.pix_fmt, color_space: v.color_space ?? null,
  color_range: v.color_range ?? null, fps: fn / fd, nb_frames: Number(v.nb_frames), duration_s: Number(v.duration),
} : null;
result.audio = a ? {
  codec: a.codec_name, sample_rate: Number(a.sample_rate), channels: a.channels, bit_rate: Number(a.bit_rate), duration_s: Number(a.duration),
} : null;
result.frames_ok_count = !!v && Number(v.nb_frames) === timing.totalFrames;
const expectS = timing.totalFrames / fps;

// ---------------------------------------------------------------- keyframes at the midpoint
const mid = Math.floor((Number(v?.duration ?? expectS)) / 2);
const kf = sh("ffprobe", ["-v", "error", "-select_streams", "v", "-skip_frame", "nokey", "-show_entries", "frame=pts_time", "-of", "csv=p=0",
  "-read_intervals", `${mid}%+4`, mp4]).trim().split("\n").map((l) => parseFloat(l)).filter((x) => Number.isFinite(x));
const gaps = kf.slice(1).map((t, i) => t - kf[i]);
const maxGap = gaps.length ? Math.max(...gaps) : null;
result.keyframes = { at_s: mid, times: kf.map((t) => Number(t.toFixed(3))), max_gap_s: maxGap == null ? null : Number(maxGap.toFixed(3)), ok: maxGap != null && maxGap <= 0.5 + 1e-3 && kf.length >= 4 };

// ---------------------------------------------------------------- loudness, black runs, speech onsets: one decode pass
const log = ffErr(["-hide_banner", "-nostats", "-i", mp4, "-filter_complex",
  "[0:v]blackdetect=d=0.5:pix_th=0.10[vo];[0:a]asplit[a1][a2];[a1]ebur128=peak=true[ao];[a2]silencedetect=noise=-38dB:d=0.05[so]",
  "-map", "[vo]", "-f", "null", "-", "-map", "[ao]", "-f", "null", "-", "-map", "[so]", "-f", "null", "-"]);
const sumIdx = log.lastIndexOf("Summary:");
const summary = sumIdx >= 0 ? log.slice(sumIdx) : "";
const I = Number(/I:\s+(-?[\d.]+) LUFS/.exec(summary)?.[1]);
const TP = Number(/Peak:\s+(-?[\d.]+) dBFS/.exec(summary)?.[1]);
result.loudness = { integrated_lufs: Number.isFinite(I) ? I : null, true_peak_dbtp: Number.isFinite(TP) ? TP : null, ok: I >= -16 && I <= -13 };
const blackRuns = [...log.matchAll(/black_start:([\d.]+) black_end:([\d.]+)/g)].map((m) => ({ start_s: Number(m[1]), end_s: Number(m[2]) }));
result.black = { runs: blackRuns, ok: blackRuns.length === 0 };

// ---------------------------------------------------------------- audio and video sync
Object.assign(result, syncCheck(log, a ? Number(a.duration) : null, v ? Number(v.nb_frames) : null));

// ---------------------------------------------------------------- frame checks, one frame per scene step
const W = 192, H = 108;
const grab = (frame, file) => {
  const t = (frame + 0.5) / fps;
  const raw = execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-ss", t.toFixed(3), "-i", mp4, "-frames:v", "1",
    "-vf", `scale=${W}:${H}:flags=area,format=gray`, "-f", "rawvideo", "-"], { maxBuffer: 1 << 24 });
  if (file) execFileSync("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", "-ss", t.toFixed(3), "-i", mp4, "-frames:v", "1", "-vf", "scale=960:-1", "-q:v", "4", file]);
  return raw;
};
// content area: below the heading and the step rail (y > 160 of 1080), above the captions (y < 930)
const y0 = Math.round((160 / 1080) * H), y1 = Math.round((930 / 1080) * H);
const stats = (px) => {
  let n = 0, sum = 0, sq = 0, ink = 0, cN = 0;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const g = px[y * W + x];
    n++; sum += g; sq += g * g;
    if (y >= y0 && y < y1) { cN++; if (g < T.inkLuma) ink++; }
  }
  const mean = sum / n;
  return { mean, std: Math.sqrt(Math.max(0, sq / n - mean * mean)), ink: ink / cN };
};
const diff = (p, q) => {
  let s = 0, n = 0;
  for (let y = y0; y < y1; y++) for (let x = 0; x < W; x++) { s += Math.abs(p[y * W + x] - q[y * W + x]); n++; }
  return s / n;
};
const frameRes = { checked: 0, thresholds: { ink_min: T.inkMin, ink_luma: T.inkLuma, same_max: T.sameMax, black_mean: T.blackMean, blank_std: T.blankStd }, failing: [], ink_min_seen: null, same_min_seen: null };
if (spec) {
  const fdir = join(outDir, "verify-frames");
  mkdirSync(fdir, { recursive: true });
  const stillIndex = existsSync(join(outDir, "stills/index.json")) ? JSON.parse(readFileSync(join(outDir, "stills/index.json"), "utf8")) : [];
  let prev = null;
  for (const s of scenes(spec, timing)) {
    const name = `${s.beat}__${s.name.replace(/\./g, "-")}.jpg`;
    const file = join(fdir, name);
    const px = grab(s.still, file);
    const st = stats(px);
    frameRes.checked++;
    const still = stillIndex.find((e) => e.file === name) ? join(outDir, "stills", name) : null;
    const fail = (reason, value) => frameRes.failing.push({ beat: s.beat, step: s.name, frame: s.still, reason, value: Number(value.toFixed(4)), still, frame_file: file });
    if (st.mean < T.blackMean) fail("black", st.mean);
    else if (st.std < T.blankStd) fail("blank", st.std);
    // the title and end cards are centred cards; every other scene must have content under the heading
    if (st.ink < T.inkMin) fail("near-empty", st.ink);
    frameRes.ink_min_seen = frameRes.ink_min_seen == null ? st.ink : Math.min(frameRes.ink_min_seen, st.ink);
    if (prev && prev.beat === s.beat && s.kind === "concept") {
      const d = diff(prev.px, px);
      frameRes.same_min_seen = frameRes.same_min_seen == null ? d : Math.min(frameRes.same_min_seen, d);
      if (d < T.sameMax) fail(`same as ${prev.name}`, d);
    }
    prev = { beat: s.beat, name: s.name, px };
  }
  frameRes.ink_min_seen = frameRes.ink_min_seen == null ? null : Number(frameRes.ink_min_seen.toFixed(4));
  frameRes.same_min_seen = frameRes.same_min_seen == null ? null : Number(frameRes.same_min_seen.toFixed(3));
}
result.frames_ok = !!spec && frameRes.failing.length === 0;
result.frames = spec ? frameRes : { skipped: `no spec at ${specPath}` };

// ---------------------------------------------------------------- 6-frame contact sheet
const sheet = join(outDir, "contact.jpg");
const dur = Number(v?.duration ?? expectS);
const times = [1, 2, 3, 4, 5, 6].map((i) => (dur * i) / 7);
const inputs = times.flatMap((t) => ["-ss", t.toFixed(2), "-i", mp4]);
const filt = times.map((_, i) => `[${i}:v]scale=640:-1,setsar=1[v${i}]`).join(";") + ";" +
  times.map((_, i) => `[v${i}]`).join("") + "xstack=inputs=6:layout=0_0|646_0|1292_0|0_366|646_366|1292_366:fill=white[o]";
execFileSync("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", ...inputs, "-filter_complex", filt, "-map", "[o]", "-frames:v", "1", "-q:v", "7", sheet]);
result.sheet = sheet;

const vOk = !!result.video && result.video.pix_fmt === "yuv420p" && result.video.color_space === "bt709" && !!result.audio;
result.ok = vOk && result.frames_ok_count && result.keyframes.ok && result.loudness.ok && result.black.ok && result.sync_ok && result.frames_ok;
console.log(JSON.stringify(result, null, 1));
process.exit(result.ok ? 0 : 1);

/**
 * Speech onsets (silencedetect's silence_end, d = 0.05 s) against the timing file's line starts. Lines inside a
 * beat are joined with only ~0.15 s of near-silence, so a line counts as matched when an onset lies between
 * syncEarlyS before and syncLateS after its expected start; an earlier onset is a pause inside the line before.
 * Every beat's first line follows a silent gap and must match.
 * `videoFrames` null = audio-only file: the audio duration is compared with totalFrames instead.
 */
function syncCheck(slog, audioS, videoFrames) {
  const onsets = [0, ...[...slog.matchAll(/silence_end:\s*([\d.]+)/g)].map((m) => Number(m[1]))].sort((x, y) => x - y);
  const firstSilence = /silence_start:\s*([\d.]+)/.exec(slog);
  if (firstSilence && Number(firstSilence[1]) < 0.05) onsets.shift(); // the file starts silent: 0 is not an onset
  const lines = [];
  for (const id of timing.order) {
    const b = timing.beats[id];
    b.steps.forEach((l, i) => lines.push({ beat: id, key: l.key, expected_s: (b.start + l.start) / fps, first: i === 0 }));
  }
  const drifts = [];
  const unmatched = [];
  for (const l of lines) {
    let best = null;
    for (const o of onsets) {
      if (o - l.expected_s < -T.syncEarlyS || o - l.expected_s > T.syncLateS) continue;
      if (best == null || Math.abs(o - l.expected_s) < Math.abs(best - l.expected_s)) best = o;
    }
    if (best != null && best - l.expected_s >= -T.syncEarlyS && best - l.expected_s <= T.syncLateS) {
      drifts.push({ beat: l.beat, key: l.key, expected_s: Number(l.expected_s.toFixed(3)), onset_s: Number(best.toFixed(3)), drift_ms: Math.round((best - l.expected_s) * 1000) });
    } else unmatched.push({ beat: l.beat, key: l.key, expected_s: Number(l.expected_s.toFixed(3)), first_line_of_beat: l.first });
  }
  drifts.sort((x, y) => Math.abs(y.drift_ms) - Math.abs(x.drift_ms));
  const maxDrift = drifts.length ? Math.abs(drifts[0].drift_ms) : null;
  const firstMissing = unmatched.filter((u) => u.first_line_of_beat);
  const expect = timing.totalFrames / fps;
  const vidS = videoFrames != null ? videoFrames / fps : null;
  const avDiff = audioS != null ? Math.round(Math.abs(audioS - (vidS ?? expect)) * 1000) : null;
  const totDiff = Math.round(Math.abs((vidS ?? audioS ?? 0) - expect) * 1000);
  // Beat anchoring: where each beat's first speech lands in the render, against the same point in its own
  // MP3 (narrate.mjs output, <timing dir>/audio). This isolates the renderer's placement from the voice.
  const audioDir = flags.audio ? resolve(flags.audio) : join(dirname(resolve(timingArg)), "audio");
  const beatDrift = [];
  if (existsSync(audioDir)) {
    for (const id of timing.order) {
      const f = join(audioDir, `${id}.mp3`);
      if (!existsSync(f)) continue;
      const blog = ffErr(["-hide_banner", "-nostats", "-i", f, "-af", "silencedetect=noise=-38dB:d=0.05", "-f", "null", "-"]);
      const s0 = /silence_start:\s*([\d.]+)/.exec(blog);
      const e0 = /silence_end:\s*([\d.]+)/.exec(blog);
      const lead = s0 && Number(s0[1]) < 0.02 && e0 ? Number(e0[1]) : 0;
      const b = timing.beats[id];
      const exp = (b.start + (b.cues[0]?.start ?? 0)) / fps + lead;
      let best = null;
      for (const o of onsets) if (best == null || Math.abs(o - exp) < Math.abs(best - exp)) best = o;
      if (best != null) beatDrift.push({ beat: id, expected_s: Number(exp.toFixed(3)), onset_s: Number(best.toFixed(3)), drift_ms: Math.round((best - exp) * 1000) });
    }
  }
  const beatMax = beatDrift.length ? Math.max(...beatDrift.map((x) => Math.abs(x.drift_ms))) : null;
  return {
    sync_ok: maxDrift != null && maxDrift <= T.syncDriftMs && firstMissing.length === 0 && avDiff != null && avDiff <= T.totalDiffMs && totDiff <= T.totalDiffMs &&
      (beatMax == null || beatMax <= T.syncDriftMs),
    sync_beat_max_drift_ms: beatMax,
    sync_beats: beatDrift,
    sync_max_drift_ms: maxDrift,
    sync_lines: lines.length,
    sync_matched: drifts.length,
    sync_worst: drifts.slice(0, 5),
    sync_unmatched: unmatched,
    audio_video_diff_ms: avDiff,
    total_diff_ms: totDiff,
  };
}
