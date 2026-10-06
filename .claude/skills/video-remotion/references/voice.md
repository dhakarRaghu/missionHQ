# Voice

Narration quality decides whether a lesson video feels modern. A robotic voice reads as old even
when the visuals are good.

## Options, best first

| Option | Quality | Cost | Needs |
|---|---|---|---|
| The user's own recording | best | free | a microphone; transcribe for captions |
| ElevenLabs or OpenAI TTS | very good | paid per minute | the user's API key |
| **Kokoro** (local, `kokoro-onnx`) | good, natural | free | `setup-kokoro.sh`, ~350 MB once |
| macOS `say` | robotic | free | nothing; use for timing drafts only |

The macOS voices (Samantha and the rest) were rejected by a user as "not modern" on 2026-10-03.
Premium macOS voices are not installed by default and cannot be installed from a script.

## Kokoro

`bash <skill>/assets/lesson/setup-kokoro.sh <project>` installs it into `<project>/tools/tts`; Mission HQ reads it from `KOKORO_DIR` (default `course-videos/tools/tts`).
`narrate.mjs` uses it when the narration JSON has `"engine": "kokoro"`. It renders every line in one
Python process, so the model loads once.

| Voice | Character |
|---|---|
| `af_heart` | American female, warm. Highest-rated Kokoro voice. **Chosen by the user for the course.** |
| `af_bella` | American female, more energy |
| `am_michael` | American male, calm |
| `am_fenrir` | American male, deeper |
| `bf_emma` | British female |
| `bm_george` | British male |

- `speed: 0.92` gives about 160 words per minute. At `1.0` the measured rate was 177 wpm, which is
  fast for viewers whose first language is not English.
- A blend is allowed: `"voice": "af_heart:60,af_bella:40"`.
- `kokoro_batch.py` trims leading and trailing silence on each line, so line timings stay tight.
- `kokoro_batch.py` caps onnxruntime at 3 threads with spin-waiting off (`KOKORO_THREADS` overrides).
  Without the cap, several narrations at once take every core and none of them finishes.

To let the user choose, render the same two or three sentences in four to six voices, loudness
normalised (`loudnorm=I=-14:TP=-1`), named `voice-1-af_heart.mp3` and so on.

## Pronunciation: write it in `say`

Captions show `text`; the voice reads `say`. Write `say` whenever the spoken form differs.

| On screen (`text`) | Spoken (`say`) |
|---|---|
| `TTFT`, `KV cache`, `GPU` | `T T F T`, `K V cache`, `G P U` |
| `0.35`, `0.1875` | `point three five`, `point one eight seven five` |
| `$4.20`, `$0.0074` | `four dollars and twenty cents`, `point seven four cents` |
| `5.4×`, `5x` | `five point four times`, `five times` |
| `1 + 5e = 5` | `one plus five e equals five` |
| `max_tokens` | `max tokens` |
| `METR`, `LiteLLM` | `Meter`, `Lite L L M` |
| `Phase 3B` | `Phase three B` |
| `503` | `five oh three` |

Read the generated captions once (`grep 'text:' <id>.script.ts`) before writing scenes. The captions
come from `text`, so they keep the symbols.

## Levels

`narrate.mjs` normalises each line to −14 LUFS and fades the tail of each beat. A finished render
measured −14.3 to −14.9 LUFS integrated with no further mastering.
