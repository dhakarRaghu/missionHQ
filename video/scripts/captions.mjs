#!/usr/bin/env node
/**
 * captions.mjs: the captions file and the chapter list of a rendered spec video.
 *
 *   node scripts/captions.mjs <timing.json> <spec.json> <outDir>
 *
 *   <outDir>/captions.srt    every caption cue at its absolute time (the same cues the video burns in)
 *   <outDir>/chapters.json   [{ "t": seconds, "title": "..." }]: one chapter per beat with a heading; the first
 *                            chapter starts at 0. A beat without a heading (title, end) stays in the chapter
 *                            before it. Warns on stderr when a chapter is shorter than 10 s.
 * Adapted from course-videos scripts/youtube-meta.mjs; the YouTube description part was dropped.
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const [, , timingPath, specPath, outDir] = process.argv;
if (!timingPath || !specPath || !outDir) {
  console.error("usage: captions.mjs <timing.json> <spec.json> <outDir>");
  process.exit(2);
}
const timing = JSON.parse(readFileSync(timingPath, "utf8"));
const spec = JSON.parse(readFileSync(specPath, "utf8"));
mkdirSync(outDir, { recursive: true });
const fps = timing.fps;

const srtTime = (frames) => {
  const ms = Math.round((frames / fps) * 1000);
  const p = (n, w = 2) => String(n).padStart(w, "0");
  return `${p(Math.floor(ms / 3600000))}:${p(Math.floor((ms % 3600000) / 60000))}:${p(Math.floor((ms % 60000) / 1000))},${p(ms % 1000, 3)}`;
};

const cues = spec.beats.flatMap((b) => {
  const t = timing.beats[b.id];
  return t.cues.map((c) => ({ text: c.text, start: t.start + c.start, end: t.start + c.end }));
});
writeFileSync(join(outDir, "captions.srt"), cues.map((c, i) => `${i + 1}\n${srtTime(c.start)} --> ${srtTime(c.end)}\n${c.text}\n`).join("\n"));

const chapters = [];
for (const b of spec.beats) {
  const title = b.heading ?? (b.kind === "recap" ? "Recap" : null);
  if (!title) continue;
  chapters.push({ t: chapters.length === 0 ? 0 : Number((timing.beats[b.id].start / fps).toFixed(3)), title });
}
if (chapters.length === 0) chapters.push({ t: 0, title: spec.title });
const totalS = timing.totalFrames / fps;
chapters.forEach((c, i) => {
  const next = chapters[i + 1]?.t ?? totalS;
  if (next - c.t < 10) console.error(`warning: chapter "${c.title}" is ${(next - c.t).toFixed(1)} s, shorter than 10 s`);
});
writeFileSync(join(outDir, "chapters.json"), JSON.stringify(chapters, null, 1) + "\n");
const clock = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
console.log(`captions: ${cues.length} cues; chapters: ${chapters.length}`);
console.log(chapters.map((c) => `${clock(c.t)} ${c.title}`).join("\n"));
