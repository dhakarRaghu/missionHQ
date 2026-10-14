#!/usr/bin/env node
/**
 * narrate.mjs: voices a narration file and writes the timing file the renderer reads.
 *
 *   node scripts/narrate.mjs <narration.json> <audioDir> <timing.json>
 *
 *   <audioDir>/<beatId>.mp3   one file per beat, every line normalised to -14 LUFS, 44.1 kHz mono
 *   <timing.json>             { version, fps, totalFrames, order, beats: { <id>: { id, chapter, start, end,
 *                               audioFrames, cues: [{text,start,end}], steps: [{key,at,start,end,text}] } } }
 *
 * Frames: `start`/`end` of a beat are absolute; cues and steps are local to the beat. A step's `start` is the
 * frame where the voice starts that line, and `at` is `start` minus the beat's cueLeadS (default 0.25 s, at
 * most 0.5 s): the frame where the line's visuals appear.
 *
 * Engine "kokoro" (default for the course) runs every line in one Python process, so the model loads once.
 * KOKORO_DIR points at a folder with .venv/, models/ and kokoro_batch.py (default: <repo>/tools/tts).
 * KOKORO_THREADS caps onnxruntime threads (kokoro_batch.py reads it; default 3). Engine "say" is macOS `say`,
 * for timing drafts only. NARRATE_DRY=1 writes silent audio with estimated line lengths, for layout checks.
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const [, , cfgPath, outDirArg, timingOut] = process.argv;
if (!cfgPath || !outDirArg || !timingOut) {
  console.error("usage: narrate.mjs <narration.json> <audioDir> <timing.json>");
  process.exit(2);
}
const cfg = JSON.parse(readFileSync(resolve(cfgPath), "utf8"));
const outDir = resolve(outDirArg);
mkdirSync(outDir, { recursive: true });
mkdirSync(dirname(resolve(timingOut)), { recursive: true });

const FPS = 30;
// This file is <repo>/video/scripts/narrate.mjs, so the repo root is two folders up.
const REPO_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const KOKORO_DIR = process.env.KOKORO_DIR ?? join(REPO_DIR, "tools", "tts");
// NARRATE_DRY=1: no voice. Each line is silence as long as the voice would roughly take (14.5 characters a
// second), so layouts and timing can be checked before the voice runs. Never ship a dry timing file.
const DRY = process.env.NARRATE_DRY === "1";
const engine = DRY ? "dry" : cfg.engine ?? "kokoro";
const voice = cfg.voice ?? (engine === "kokoro" ? "af_heart" : "Samantha");
const tmp = mkdtempSync(join(tmpdir(), "narrate-"));
const spokenOf = (line) => line.say ?? line.text;
const beatOrder = Object.keys(cfg.beats);

const run = (cmd, args) => execFileSync(cmd, args, { stdio: ["ignore", "pipe", "inherit"] });
const dur = (file) =>
  Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file]).toString().trim());

// ---------------------------------------------------------------- voice every line

const raw = new Map(); // `${beatId}-${i}` -> wav/aiff path
if (engine === "dry") {
  for (const beatId of beatOrder) {
    cfg.beats[beatId].lines.forEach((line, i) => {
      const out = join(tmp, `${beatId}-${i}.wav`);
      const sec = Math.max(1.2, spokenOf(line).length / 14.5).toFixed(2);
      run("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", sec, out]);
      raw.set(`${beatId}-${i}`, out);
    });
  }
} else if (engine === "kokoro") {
  for (const f of ["kokoro_batch.py", ".venv/bin/python", "models"]) {
    if (!existsSync(join(KOKORO_DIR, f))) {
      console.error(`KOKORO_DIR=${KOKORO_DIR} has no ${f}. Set KOKORO_DIR to a folder with .venv/, models/ and kokoro_batch.py.`);
      process.exit(2);
    }
  }
  const jobs = [];
  for (const beatId of beatOrder) {
    cfg.beats[beatId].lines.forEach((line, i) => {
      const out = join(tmp, `${beatId}-${i}.wav`);
      raw.set(`${beatId}-${i}`, out);
      jobs.push({ text: spokenOf(line), out, voice: line.voice || cfg.beats[beatId].voice || undefined });
    });
  }
  const jobFile = join(tmp, "kokoro-jobs.json");
  writeFileSync(jobFile, JSON.stringify({ voice, speed: cfg.speed ?? 0.94, lang: cfg.lang ?? "en-us", jobs }));
  console.log(`kokoro: ${jobs.length} lines`);
  execFileSync(join(KOKORO_DIR, ".venv/bin/python"), [join(KOKORO_DIR, "kokoro_batch.py"), jobFile], { stdio: ["ignore", "ignore", "inherit"] });
} else {
  for (const beatId of beatOrder) {
    cfg.beats[beatId].lines.forEach((line, i) => {
      const out = join(tmp, `${beatId}-${i}.aiff`);
      run("say", ["-v", voice, "-r", String(cfg.rate ?? 168), "-o", out, spokenOf(line)]);
      raw.set(`${beatId}-${i}`, out);
    });
  }
}

// Every line to one format, so lines concat cleanly. The lines stay PCM until the whole beat is joined: an MP3
// per line carries its own encoder padding (about 35 ms), which the joined beat drops, so line starts summed
// from per-line MP3s ran ahead of the voice by that much per line, about a second by a beat's last line.
const toWav = (src, out) =>
  run("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", "-i", src, "-af", "loudnorm=I=-14:TP=-1:LRA=11",
    "-ar", "44100", "-ac", "1", "-codec:a", "pcm_s16le", out]);

// ---------------------------------------------------------------- captions

const MAX = 48;
/** Splits one line into caption cues (3–9 words, max about 48 characters), timed by the line's real audio. */
const captionCues = (line, startS, durS) => {
  const clean = line.replace(/\s+/g, " ").trim();
  if (!clean || durS <= 0) return [];
  const wrapWords = (text) => {
    const width = Math.min(MAX, Math.ceil(text.length / Math.ceil(text.length / MAX)) + 4);
    const out = [];
    let cur = "";
    for (const w of text.split(" ")) {
      if (cur && (cur + " " + w).length > width) { out.push(cur); cur = w; } else cur = cur ? `${cur} ${w}` : w;
    }
    if (cur) out.push(cur);
    return out;
  };
  // split at sentence ends only when whitespace follows, so decimals like 0.35 stay whole
  const sentences = clean.split(/(?<=[.!?])\s+/).filter(Boolean);
  const rawCues = [];
  let cur = "";
  for (const snt of sentences) {
    if (snt.length > 52) {
      if (cur) { rawCues.push(cur); cur = ""; }
      for (const p of snt.split(/(?<=,)\s+/)) {
        if (cur && (cur + " " + p).length <= MAX) { cur = `${cur} ${p}`; continue; }
        if (cur) rawCues.push(cur);
        cur = "";
        if (p.length <= MAX) cur = p;
        else { const w = wrapWords(p); rawCues.push(...w.slice(0, -1)); cur = w[w.length - 1]; }
      }
      if (cur) { rawCues.push(cur); cur = ""; }
    } else if (cur && (cur + " " + snt).length <= MAX) cur = `${cur} ${snt}`;
    else { if (cur) rawCues.push(cur); cur = snt; }
  }
  if (cur) rawCues.push(cur);
  // a one-word cue flashes by too fast to read: join it to a neighbour when the result stays short
  const merged = [];
  for (const c of rawCues) {
    const prev = merged[merged.length - 1];
    if (prev && (c.split(" ").length === 1 || prev.split(" ").length === 1) && (prev + " " + c).length <= 56) merged[merged.length - 1] = `${prev} ${c}`;
    else merged.push(c);
  }
  const cues = merged.map((c) => c.replace(/,$/, ""));
  const total = cues.reduce((a, c) => a + c.length, 0) || 1;
  let cursor = startS;
  return cues.map((text, i) => {
    const min = Math.max(0.85, text.length / 17); // reading budget
    const d = i === cues.length - 1 ? startS + durS - cursor : Math.max(min, (durS * text.length) / total);
    const end = Math.min(startS + durS, cursor + d);
    const out = { text, start: cursor, end };
    cursor = end;
    return out;
  });
};

// ---------------------------------------------------------------- beats

const beats = {};
let cursor = 0; // seconds
for (const beatId of beatOrder) {
  const beat = cfg.beats[beatId];
  cursor += beat.leadinS ?? cfg.leadinS ?? 0.8;
  // The beat starts on a whole frame and every later time is counted from that frame, so rounding never
  // accumulates over a long video: each beat re-anchors on its own frame.
  const beatStart = Math.round(cursor * FPS);
  const beatStartS = beatStart / FPS;

  const chunks = [];
  const lineDur = [];
  beat.lines.forEach((line, i) => {
    const m = join(tmp, `${beatId}-${i}.norm.wav`);
    toWav(raw.get(`${beatId}-${i}`), m);
    chunks.push(m);
    lineDur.push(dur(m));
  });

  // concat the lines, fade only the last fadeTailS of the beat
  const beatMp3 = join(outDir, `${beatId}.mp3`);
  const list = join(tmp, `${beatId}.txt`);
  writeFileSync(list, chunks.map((p) => `file '${p}'`).join("\n"));
  const fadeS = cfg.fadeTailS ?? 0.4;
  const sumS = lineDur.reduce((a, b) => a + b, 0);
  run("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list,
    "-af", `afade=t=out:st=${Math.max(0, sumS - fadeS).toFixed(3)}:d=${fadeS}`, "-codec:a", "libmp3lame", "-q:a", "4", beatMp3]);

  const preDelayS = beat.preDelayS ?? 0.5;
  const leadS = Math.min(0.5, beat.cueLeadS ?? 0.25);
  const gapS = beat.gapS ?? cfg.gapS ?? 3;
  const holdS = beat.holdS ?? cfg.holdS ?? 2;
  const audioS = dur(beatMp3);
  // The audio starts on a whole frame (the renderer starts it at the first cue's frame).
  const audioStart = Math.round(preDelayS * FPS);
  const beatFrames = audioStart + Math.round((audioS + holdS) * FPS);

  // Line starts come from the summed durations of the lines before it, measured on the PCM chunks, which
  // the beat's MP3 joins exactly. The MP3 only pads its end (a few tens of ms, once per beat); the
  // difference between sumS and audioS is printed below so a drift would show.
  const steps = [];
  const cues = [];
  let s = audioStart / FPS;
  beat.lines.forEach((line, i) => {
    const start = Math.round(s * FPS);
    const end = Math.round((s + lineDur[i]) * FPS);
    steps.push({ key: line.key, at: Math.max(0, start - Math.round(leadS * FPS)), start, end, text: line.text });
    for (const c of captionCues(line.text, s, lineDur[i])) cues.push({ text: c.text, start: Math.round(c.start * FPS), end: Math.round(c.end * FPS) });
    s += lineDur[i];
  });

  beats[beatId] = {
    id: beatId,
    chapter: beat.chapter ?? null,
    start: beatStart,
    end: beatStart + beatFrames,
    audioFrames: Math.round(audioS * FPS),
    concatDiffMs: Math.round((audioS - sumS) * 1000),
    cues,
    steps,
  };
  cursor = beatStartS + beatFrames / FPS + gapS;
}

const last = beats[beatOrder[beatOrder.length - 1]];
const totalFrames = last.end + FPS; // one second of paper after the end card's hold
// version 2: line starts measured on PCM (see toWav). build.py voices a job again when its timing is older.
const timing = { version: 2, fps: FPS, totalFrames, order: beatOrder, beats };
const tmpOut = `${resolve(timingOut)}.tmp`;
writeFileSync(tmpOut, JSON.stringify(timing, null, 1) + "\n");
renameSync(tmpOut, resolve(timingOut));

console.log(`Wrote ${timingOut}: ${totalFrames} frames = ${(totalFrames / FPS).toFixed(1)} s`);
for (const id of beatOrder) {
  const b = beats[id];
  console.log(`  ${id}: frames ${b.start}..${b.end} (${((b.end - b.start) / FPS).toFixed(1)} s), audio ${(b.audioFrames / FPS).toFixed(2)} s, concat diff ${b.concatDiffMs} ms`);
}
