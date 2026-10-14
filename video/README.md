# Mission HQ video renderer

This folder turns a lesson into a narrated video. The model writes two JSON files: the narration
and the spec. Code checks them, a local voice reads the narration, and tested Remotion templates
draw the spec in the Sketchbook look. The model never writes React.

`SPEC.md` is the contract. Read it first.

## How the pieces fit

```
<id>.narration.json ─┐
                     ├─ check-spec.mjs ── narrate.mjs ── <id>.timing.json + audio/<beat>.mp3
<id>.spec.json ──────┘                                          │
                                   render.mjs --stills=auto ────┤── stills/, sheet.jpg  (review)
                                   render.mjs ──────────────────┴── <id>.mp4 ── verify.mjs (JSON)
                                   captions.mjs ── captions.srt, chapters.json
```

| Path | What it is |
|---|---|
| `SPEC.md` | the contract: narration, spec, panels, limits, checks, timing file |
| `spec/video-spec.schema.json`, `spec/narration.schema.json` | the same contract as JSON Schema (draft-07), for Python |
| `src/spec/types.ts` | the same contract as TypeScript types |
| `src/SpecVideo.tsx`, `src/Root.tsx`, `src/index.ts` | the `SpecVideo` composition (1920x1080, 30 fps) |
| `src/spec/templates/concept.tsx` | the concept beat and one template per step |
| `src/spec/templates/panels.tsx` | one template per panel kind |
| `src/spec/templates/beats.tsx` | cold open, title, payoff, recap, end card |
| `src/spec/templates/shell.tsx` | one beat: its Sequence, audio, captions, heading |
| `src/spec/templates/common.tsx` | tones, timing lookups, `FitBox` (fits any text into its box, centres it, grows small content), `keepUnits` |
| `src/kit-sketch/` | the Sketchbook kit, copied unchanged from `course-videos/src/kit-sketch` |
| `scripts/build-schema.mjs` | writes the two JSON Schemas; run after a contract change |
| `examples/ep12/` | Inference Internals #12 ported to the spec format (the proof) |
| `examples/stress/make-stress.py` | writes a spec with every text field at its limit and ten concepts |

## Setup

Remotion needs the arm64 Node. The x86 Node breaks the renderer. Make sure the `node` on your `PATH` is arm64 (the backend uses it, or the folder named in `VIDEO_NODE_BIN`):

```bash
node -p process.arch        # must print arm64
cd video && npm install
```

The voice is Kokoro (`af_heart`). `narrate.mjs` looks for it in `KOKORO_DIR`, which defaults to
`<repo>/tools/tts` (a folder with `.venv/`,
`models/` and `kokoro_batch.py`). Do not copy the models into this repo.

## Commands

Run every command from `video/`. `<out>` is the job folder, for example `out/ep12`, and `<id>` the
file stem, for example `ep12`.

| Step | Command | Writes |
|---|---|---|
| Check | `node scripts/check-spec.mjs <narration.json> <spec.json>` | stdout: one line per problem, `<file>:<JSON path>: <message>`, or `OK: …`. Exit 0 ok, 1 problems, 2 usage. Check 6 (narration rules) is the Python backend's job. |
| Voice | `node scripts/narrate.mjs <narration.json> <out>/audio <out>/<id>.timing.json` | `<out>/audio/<beat>.mp3`, `<out>/<id>.timing.json`. Env: `KOKORO_DIR`, `KOKORO_THREADS` (default 3), `NARRATE_DRY=1` (silent audio with estimated lengths, for layout checks only). |
| Stills | `node scripts/render.mjs <out> <id> --stills=auto` | `<out>/stills/<beat>__<step>.jpg` (1920x1080, JPEG 85; a step with `panels` gives `<step>-1`, `<step>-2`), `<out>/stills/index.json` = `[{file, beat, step, frame, keys}]`, `<out>/sheet.jpg` (all stills, 6 across) |
| One beat | `node scripts/render.mjs <out> <id> --stills=<beatId>` | that beat's stills; `index.json` and `sheet.jpg` updated |
| Frames | `node scripts/render.mjs <out> <id> --stills=120,4000` | `<out>/stills/frame-<n>.jpg` |
| Video | `node scripts/render.mjs <out> <id> [--scale=1\|2]` | `<out>/<id>.mp4` (scale 1, 1080p) or `<out>/<id>-4K.mp4` (scale 2), plus `<out>/props.json` |
| Soundtrack | `node scripts/render.mjs <out> <id> --audio-only` | `<out>/<id>-audio.wav`, for `verify.mjs --sync-only` on a long video |
| Verify | `node scripts/verify.mjs <out>/<id>.mp4 <out>/<id>.timing.json [--spec=<spec.json>] [--out=<dir>]` | stdout: one JSON object; `<out>/contact.jpg` (6 frames, 3x2); `<out>/verify-frames/<beat>__<step>.jpg`. Exit 0 when `ok`, else 1. |
| Sync only | `node scripts/verify.mjs <out>/<id>-audio.wav <out>/<id>.timing.json --sync-only` | stdout: the `sync_*` keys, `audio_video_diff_ms`, `total_diff_ms`, `ok` |
| Captions | `node scripts/captions.mjs <out>/<id>.timing.json <out>/<id>.spec.json <out>` | `<out>/captions.srt`, `<out>/chapters.json` = `[{t, title}]` (seconds) |

`render.mjs` reads `<out>/<id>.spec.json` and `<out>/<id>.timing.json` unless `--spec=`/`--timing=`
point elsewhere, and uses `<out>/audio` as Remotion's public dir (`--audio=` overrides). The video
uses the proven upload flags: H.264, CRF 18, x264 `slow`, yuv420p, BT.709, AAC 384 kbps 48 kHz,
`--disallow-parallel-encoding`, and `YT=1`, which makes `remotion.config.ts` add a keyframe every
0.5 s and `+faststart`. Never run two renders at once: one render keeps every core busy.

Long jobs: background shells stop after 30 minutes, so run narration and renders detached:

```bash
nohup bash -c 'node scripts/render.mjs out/ep12 ep12; echo $? > out/ep12/render.done' > out/ep12/render.log 2>&1 &
```

Layout debug: add `"debugFit": true` to the props (for example in `<out>/props.json`) and every `FitBox`
logs a `FIT {...}` line to the browser console: its scale, its box, the visible content and the smallest
on-screen font size of each text kind (`data-ty`: body, sec, note).

Studio: `npx remotion studio` opens `SpecVideo` with the ep12 spec and no timing (a placeholder
frame). Pass real props with `--props=<out>/props.json`.

## verify.mjs output

| Key | Meaning | Pass |
|---|---|---|
| `ok` | every check below passed | |
| `file`, `size_bytes` | the MP4 | |
| `video` | `{width, height, codec, pix_fmt, color_space, color_range, fps, nb_frames, duration_s}` | `pix_fmt` yuv420p, `color_space` bt709 |
| `audio` | `{codec, sample_rate, channels, bit_rate, duration_s}` | present |
| `frames_ok_count` | `nb_frames` equals the timing file's `totalFrames` | true |
| `keyframes` | `{at_s, times, max_gap_s, ok}`: keyframes over 4 s at the midpoint | gap ≤ 0.5 s |
| `loudness` | `{integrated_lufs, true_peak_dbtp, ok}` (ebur128) | −16 ≤ I ≤ −13 |
| `black` | `{runs, ok}` (blackdetect, d = 0.5 s, pix_th 0.10) | no runs |
| `sync_ok` | sync passed | |
| `sync_max_drift_ms` | largest gap between a line's timing-file start and the measured speech onset | ≤ 250 |
| `sync_worst` | the 5 worst lines: `{beat, key, expected_s, onset_s, drift_ms}` | |
| `sync_lines`, `sync_matched`, `sync_unmatched` | lines in the timing file, lines with an onset from 0.3 s before to 0.6 s after their start, and the rest (`{beat, key, expected_s, first_line_of_beat}`) | every beat's first line matched |
| `sync_beat_max_drift_ms`, `sync_beats` | each beat's first speech in the render against the same point in `<timing dir>/audio/<beat>.mp3` (`{beat, expected_s, onset_s, drift_ms}`); skipped without the audio folder | ≤ 250 |
| `audio_video_diff_ms`, `total_diff_ms` | audio vs video duration; video vs `totalFrames` | ≤ 100 each |
| `frames_ok` | the frame checks passed | |
| `frames` | `{checked, thresholds, failing: [{beat, step, frame, reason, value, still, frame_file}], ink_min_seen, same_min_seen}` | `failing` empty |
| `sheet` | path of `contact.jpg` | |

Onsets come from `silencedetect=noise=-38dB:d=0.05` on the MP4's audio. Lines inside a beat are
joined with only about 0.15 s of near-silence, so some lines have no detectable onset; they are
listed in `sync_unmatched`, and only a beat's first line must always match.

Frame checks run on one frame of the MP4 per scene step, 0.5 s before the next step starts
(the same frames as `--stills=auto`), scaled to 192x108 grey:

| Check | Measure | Threshold |
|---|---|---|
| near-empty | share of pixels darker than luma 200 between y = 160 and y = 930 | fail below 0.004 |
| identical steps | mean absolute grey difference between consecutive scenes of a concept, same area | fail below 0.6 |
| black | mean luma of the whole frame | fail below 20 |
| blank | luma standard deviation of the whole frame | fail below 1.5 |

The thresholds were calibrated on the ep12 port; the README's numbers are the values in
`scripts/verify.mjs` (`const T`).
