# Story, pacing, captions, audio

## Length

| Format | Target | Source |
|---|---|---|
| Feature demo | **60–90 s** (45–75 s of actual demo) | demo-guide consensus |
| Anything instructional | **≤ 6 min**; best engagement 1–3 min | edX study of 6.9 M sessions |
| Vertical short | 15–45 s | demoday `demo-shorts` |
| Engagement cliff | under 1 min holds ~52%; past 5 min drops 50% → 38% | Wistia |

## Shape

| Part | Length | Job |
|---|---|---|
| Hook | 0–8 s (short form: 0–3 s) | The problem, on a real screen. Not the product name. |
| Title card | 2–3 s wide, ≤0.6 s in a short | Name it, one line of what it does |
| Chapter card | 1.8–2 s | Resets attention, absorbs a context jump |
| Beats | see below | One idea each |
| Payoff | 2–3 s held | The result, still, with the contrast stated |
| Close | 3–4 s | What it is, one next step |

## Beat length

| Style | Cut every | Source |
|---|---|---|
| Walkthrough / tutorial | **1.5–2.5 s** | demoday `demo-shorts:157` |
| Vertical short | 0.9–1.6 s | demoday `demo-shorts:63,117` |
| Calm wide demo | one framing per step | demoday `demo-script:86` |
| Hard cap for any non-closing shot | **2.5 s** | demoday `demo-shorts:85` |
| Hold a result before cutting | **2–3 s** | demoday; shortzly |

Measure it after the edit: total duration ÷ shot count. If a walkthrough averages 4 s per shot, it
is slow, whatever it felt like while cutting.

## Beat rules

- **One idea per beat.** If the caption needs "and", split it.
- **Cause then effect**, in that order.
- **Show the path, not just the destination**: scroll to the control, open the menu, pick the item.
- **Show absence positively**: keep the framing and point at the empty space.
- **Hold the result.** The most common thing missing from a rough cut.
- **End on the contrast.** Never cut back to the setup afterwards.

## Trim list

Loading spinners, page reloads, repeated typing, mouse hunting, dead frames before the first
action, the second half of an animation the viewer already understood, and every frame after the
point is made. Speed up (via `data-playback-rate`) anything the viewer does not need to read.

## Captions

A caption labels the beat; it does not narrate it. On-screen text that duplicates narration hurts
comprehension (Mayer's redundancy principle), so keep phrases short.

| Rule | Value | Source |
|---|---|---|
| Words per caption | 3–9 | practice |
| Characters per line | **30–37**, max **2 lines** | legibility.info; BBC; Netflix |
| Reading budget | **13–17 characters per second** | legibility.info 13; Netflix 20; demo viewers also watch the UI |
| Minimum on screen | **0.85 s**, and ~0.3 s per word | Netflix 5/6 s; BBC |
| Maximum on screen | 7 s | Netflix |
| Caption text height | **5–8% of frame height** (≥ 44 px at 1080p) | Rev |
| Body text for phone viewing | 40–60 px at 1920x1080 | legibility.info |
| Motionless time for kinetic text | **1 s per 13 characters** | legibility.info |

- Start the caption 0.1–0.3 s **after** the shot begins.
- One caption at a time. Bottom-left is the safe home in 16:9.
- Never rely on the footage for contrast: put text on a solid or ~85% opaque slab. WCAG AA is
  **4.5:1** normal, **3:1** for large text (≥24 px, or ≥19 px bold).
- Pre-size a word-by-word caption box to the full phrase, so the layout does not reflow.

## Safe areas

| Frame | Keep text inside | Source |
|---|---|---|
| 16:9 broadcast | 93% action safe, **88% title safe** (EBU R95) | tech.ebu.ch/publications/r095 |
| 1920x1080 practical | **96 px** from every edge | 90% convention |
| Instagram Reels / TikTok | avoid top 14%, **bottom 35%**, 6% each side | Meta ads guide |

The bottom 35% on vertical platforms is the one most people get wrong: a normal lower-third sits
under the platform UI.

## Type scale at 1920x1080

| Role | Size | Weight |
|---|---|---|
| Title headline | 88–96 px | 800 |
| Chapter title | 60–68 px | 800 |
| Side-note heading | 56–62 px | 800 |
| Caption | 36–40 px | 600 |
| Body / sub | 30–36 px | 400–500 |
| Label, tag | 22–26 px | 700 |

Humanist sans (Inter, Roboto, Atkinson Hyperlegible), medium to bold. Break headlines by hand so no
line holds a single word. One accent colour, used for the ring, the ripple and one key word.

## Audio

Most internal demos need no audio. Silence beats bad music.

| Rule | Value | Source |
|---|---|---|
| Music under speech | **at least 20 dB below**, i.e. voice −17 dB → music −37 dB | W3C WCAG 1.4.7 + technique G56 |
| Music peak under speech | −30 to −35 dB | Epidemic Sound |
| Dialogue peak | −12 to −6 dBFS, average ≈ −16 LUFS | Descript |
| Master loudness | **−14 LUFS** for web, −16 LUFS if it also ships as a podcast | Spotify −14; Apple −16 LKFS |
| True peak ceiling | **−1 dBTP** | EBU R128 |
| Noise floor | below **−60 dB RMS** | ACX |
| Ducking | −14 to −18 dB, ~800 ms fades | Premiere Essential Sound defaults |
| Dialogue compression | no more than 6 dB gain reduction | iZotope |
| SFX level | −12 to −18 dB with voice present | Epidemic Sound |
| SFX density warning | more than ~1 cue per second | demoday QA |

−14 LUFS is widely quoted as "the YouTube target" but YouTube publishes no LUFS figure; it is a
third-party measurement. Where SFX help most: full-screen text moments, which otherwise play in
silence and read as a stall. Normalise in two passes; single-pass `loudnorm` pumps on narration.
