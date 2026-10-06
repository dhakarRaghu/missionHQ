# Remotion API notes for screen demos

Verified against `remotion@4.0.526`. Fetch any doc page as raw markdown by appending `.md`
(e.g. `https://www.remotion.dev/docs/spring.md`).

## Which video tag

| | `<Video>` from `@remotion/media` | `<OffthreadVideo>` from `remotion` | `<Html5Video>` |
|---|---|---|---|
| Engine | Mediabunny + WebCodecs | Rust + FFmpeg | HTML5 video |
| Frame-perfect | yes | yes | **no** |
| Partial download | **yes** | no, downloads the whole file | with `muted` |
| Loopable | yes | no | yes |
| `playbackRate` audio | pitch shifts | pitch preserved | pitch preserved |

**Default to `<Video>` from `@remotion/media`** for screen recordings: H.264 MP4 is supported and
partial download matters on a long capture. It falls back to `<OffthreadVideo>` automatically when
it cannot decode. Use `<OffthreadVideo>` deliberately for H.265/AV1 sources, or when a sped-up
section must keep its audio pitch. `@remotion/effects` works on `<Video>`, not on `<OffthreadVideo>`.

The old `<Video>` from `remotion` is now `<Html5Video>`. Do not use it for demos.

## Trimming and speed

- `trimBefore` and `trimAfter` are **frame counts in the source**, not seconds. Derive them from
  `useVideoConfig().fps`, never a hardcoded 30. The official `remotion-markup/embedding-videos.md`
  says "values are in seconds" — that sentence is wrong; its own example uses frames.
- `startFrom` / `endAt` are the deprecated names. Do not mix old and new.
- `playbackRate` compresses the source but does **not** shrink `durationInFrames`. Compute the slot
  yourself: `outputFrames = Math.ceil(sourceFrames / rate)`.
- Reverse playback is not supported.

## Freezing a shot

A slot longer than its footage will run on into whatever came next in the recording. Split it:

```tsx
<Sequence durationInFrames={play} layout="none">{clip}</Sequence>
<Sequence from={play} layout="none"><Freeze frame={play - 1}>{clip}</Freeze></Sequence>
```
`<Crop playFrames={n}>` in the kit does exactly this. Overlays must live outside the `<Freeze>`, or
they stop animating.

## Timing

- `useCurrentFrame()` is **relative to the enclosing `<Sequence>`**.
- `<Sequence>` props worth knowing: `from`, `durationInFrames`, `layout="none"`, `premountFor`
  (4.0.140), `postmountFor`, `freeze`, `trimBefore` (advances the child's clock without moving the
  mount), `cropLeft/Right/Top/Bottom` (4.0.500, ratios 0–1, animatable).
- `premountFor` does not work on `layout="none"` sequences, nor on a whole `<Series>`.
- `interpolate()` almost always needs `extrapolateLeft: "clamp"` and `extrapolateRight: "clamp"`.
- `output: "perceptual-scale"` (4.0.490) on a scale interpolation makes the **visible area** change
  linearly. Without it a 1.0 → 1.4 push feels like it decelerates.
- Animate `scale` / `translate` as individual CSS properties rather than a `transform` string, so
  the values stay editable in Studio.
- `spring({frame, fps, config, durationInFrames})`; `measureSpring()` returns its settle length.
- House easing for a natural push: `Easing.bezier(0.16, 1, 0.3, 1)`.

## Transitions

```tsx
<TransitionSeries>
  <TransitionSeries.Sequence durationInFrames={60}><A /></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 12 })} />
  <TransitionSeries.Sequence durationInFrames={90}><B /></TransitionSeries.Sequence>
</TransitionSeries>
```

- A transition **subtracts** its frames from the total: 40 + 60 with a 30-frame transition is 70.
  Get the number with `springTiming({...}).getDurationInFrames({ fps })` and use it in
  `calculateMetadata` instead of maintaining it by hand.
- A transition may not be longer than either neighbour, and two transitions cannot be adjacent.
- `layout="none"` is deprecated here and throws in v5.
- `<TransitionSeries.Overlay>` (4.0.415) puts something over a cut **without** shortening the timeline:
  the right tool for a flash.
- Presentations: `fade`, `slide`, `wipe`, `flip`, `clockWipe`, `iris`, `none`, `dissolve`, `pushCut`,
  `crossZoom`, `zoomInOut` and more, imported from `@remotion/transitions/<slug>`. For demos, `fade`
  and `none` carry almost everything; keep `slide`/`wipe` for chapter boundaries.
- `springTiming` docs recommend `durationRestThreshold: 0.001`, otherwise the move visibly cuts short.

## Cursor

`@remotion/mac-cursors` (4.0.513) ships 39 real macOS cursors with hotspot correction, so `left`/`top`
is the pointer tip:

```tsx
<MacOSCursor cursor="pointer" style={{ left: 200, top: 300, scale: 2 }} />
```
Nothing tracks the cursor automatically. Supply keyframes and interpolate, as the kit's `Cursor.tsx`
does. Use the kit's drawn arrow when you want a brand-neutral pointer, and `MacOSCursor` when the
demo should look like the real desktop.

## Effects and redaction

`@remotion/effects` applies GPU shaders through the `effects` prop of `<Video>`: `blur`, `glow`,
`vignette`, `brightness`, `pixelate`, `scale`, `zoomBlur`, `regionBlur`, `cornerPin` and more.
Requires WebGL2, so render with `--gl=angle`.

**Do not use `regionBlur` to redact.** Blur and pixelation are reversible in principle. Crop the
region away, or cover it with a solid element.

## Captions and text

- `@remotion/captions`: `Caption` is `{text, startMs, endMs, timestampMs, confidence}`.
  `createTikTokStyleCaptions({captions, combineTokensWithinMilliseconds})` builds pages. The `text`
  field is **whitespace sensitive**: keep the leading space on each word and set `white-space: pre`,
  or every page merges into one.
- `@remotion/layout-utils` exports `fitText`, `fitTextOnNLines`, `fillTextBox`, `measureText`.
  There is no `<TextFit>` component. Load fonts first and pass `validateFontIsLoaded: true`, or you
  measure the fallback font. Cap the result: `Math.min(80, fitText({...}).fontSize)`.
- `@remotion/google-fonts`: always pass `weights` and `subsets`. Calling `loadFont()` bare loads
  every weight and subset and will time out.

## Rendering and QA

```bash
npx remotion still src/index.ts Demo out/f215.png --frame=215
npx remotion render src/index.ts Demo out/beats/ --frames=0,90,240,410   # stills in one pass (4.0.502)
npx remotion render src/index.ts Demo out/qa.mp4 --frames=300-419        # a range
npx remotion render src/index.ts Demo out.mp4 --codec=h264 --crf=18 --pixel-format=yuv420p
```

| Flag | Note |
|---|---|
| `--crf` | h264 default 18; cannot be combined with `--video-bitrate` or hardware acceleration |
| `--jpeg-quality` | default 80; irrelevant with `--image-format=png` |
| `--scale` | supersample, for crisp text on 4K delivery |
| `--concurrency` | parallel tabs; benchmark rather than guess |
| `--gl=angle` | needed for `@remotion/effects`; known memory leaks on long renders |
| `--media-cache-size-in-bytes` | tune in CI, where the 50%-of-RAM default is too big |
| `--props=./file.json` | use a file, not inline JSON: Windows shells strip the quotes |

Transparent output: WebM needs `--image-format=png --pixel-format=yuva420p --codec=vp8`; ProRes needs
`--codec=prores --prores-profile=4444 --pixel-format=yuva444p10le --image-format=png`.

`remotion.config.ts` only affects CLI commands, and CLI flags beat it. `calculateMetadata` returns
sit between the two.

## Determinism

Frames render in parallel tabs, out of order. A component must be a pure function of the frame.
No `Math.random()` (use `random(seed)` from `remotion`), no `Date.now()`, no `performance.now()`,
no `requestAnimationFrame`, no CSS `transition` or `animation`. `--concurrency=1` hides the symptom
and does not fix it.

For anything async, use `useDelayRender()` and hold the handle in `useState(() => delayRender("label"))`.
Never call `delayRender()` at module top level. Default timeout 30 s.

## Performance on long recordings

- `@remotion/media` keeps one decode cache per render, shared across clips; it grows to 50% of RAM.
  Out-of-order frame rendering on a sparse-keyframe recording is the biggest cost, and the cache is
  what absorbs it.
- `premountFor={fps}` on every clip avoids a cold decode when the shot appears.
- Beyond about two minutes of source per shot, pre-cut with ffmpeg after all.
- `getVideoMetadata` is deprecated and can return `Infinity` for screen recordings. Use Mediabunny
  (`@remotion/media`'s underlying library) if you need durations.
