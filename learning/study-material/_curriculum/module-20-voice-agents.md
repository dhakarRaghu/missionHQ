# Module 20: Voice agents in production

Research date: 2026-09-25. Status: research dossier, not course material. Reviewed on 2026-09-25 by an independent reviewer. Section 10 lists every correction.

Module question: **Where does the one-second budget go, and what do you give up to stay inside it?**

This is the question in `_curriculum/README.md`, section "### Module 20".

## How this dossier was built

- **Inputs.** Two research reports written on 2026-09-25 in `scratchpad/reports/`: `research_voice-agents_budget.md` and `research_voice-agents_realtime.md`. Below they are the budget report and the realtime report.
- **Path short names.** `S/` is `/private/tmp/claude-502/-Users-raghvendra-dhakar-Desktop-project-code/2ba7cd59-bd20-4d0a-a9d5-98cef39f2fb7/scratchpad/`.
  - `BS/` is `S/research_voice-agents/budget/src/`. `BP/` is `S/research_voice-agents/budget/proto/`.
  - `RS/` is `S/research_voice-agents/realtime/`. `RP/` is `RS/proto/`.
  - `LK/` is `RS/src/livekit_agents-1.8.3/livekit/agents/`, the LiveKit Agents 1.8.3 sdist from PyPI.
  - `LKS/` is `RS/src/livekit_plugins_silero-1.8.3/livekit/plugins/silero/`.
  - `PC/` is `RS/src/pipecat_ai-1.11.0/src/pipecat/`, the Pipecat 1.11.0 sdist from PyPI.
  - `D20/` is `S/dossier_m20/`, the dossier author's notes.
- **Rules followed.** `S/briefs/BRIEF_merge.md`, `S/briefs/BRIEF_research.md`, `research-method.md` and `writing-style.md`. Structure modelled on `_curriculum/module-10-memory.md`.
- **Work done for this dossier.** No lab ran. No URL was fetched. The dossier author did five read-only things:
  1. Re-grepped **127 section-4 anchors** in their saved files. **127 of 127 match** their expected count. Script `D20/anchor_check.py`, output `D20/anchor_check.txt`. Per concept, found of checked:
     - 4.1 10 of 10. 4.2 14 of 14. 4.3 11 of 11. 4.4 12 of 12.
     - 4.5 11 of 11. 4.6 11 of 11. 4.7 20 of 20. 4.8 8 of 8.
     - 4.9 4 of 4. 4.10 9 of 9. 4.11 11 of 11. 4.12 6 of 6.

     Four anchors are absence checks with an expected count of 0. Two needles needed a fix before they matched. Neither changed a fact: one string appears twice in `LK/voice/turn.py`, once as the default and once in a docstring. One Pipecat quote spans two comment lines.
  2. Recomputed every arithmetic claim with an independent cost model. Script `D20/recompute.py`, output `D20/recompute.txt`. 0 mismatches against the reports. The same script adds the sensitivity rows in section 5.3. Those rows are arithmetic on stated assumptions, not measurements.
  3. Ran both prototype self-tests on 2026-09-25 on the learner's Mac with `python3` 3.9.6: `BP/budget.py --test` printed "self-test: 8 checks passed" in 0.13 s. `RP/voice_audio_lab.py --selftest` printed "selftest: all hand-worked cases pass".
  4. Read source files at their tags to settle three conflicts: LiveKit endpointing, Pipecat's stop strategy and the OpenAI VAD default. Section 7.
  5. Read the saved Artificial Analysis and Coval tables row by row to confirm each number belongs to its model.
- **Labels.** Every claim is **verified**, **verified by run**, **inferred** or **not checked**. A verified claim names its file and line, or its table. "Verified by run" means a research agent ran a script on 2026-09-25 on the learner's Apple arm64 Mac, and the output file is named. An inferred claim names its basis and the check that would confirm it. **Vendor claim** marks a number that a company published about its own product.
- **Terms used in the whole dossier.**
  - **Voice-to-voice latency**: time from the end of the user's speech to the first sound of the agent's reply, as the user hears it.
  - **Chained pipeline**: three services in a row. Speech-to-text, then a text LLM, then text-to-speech.
  - **STT**: speech-to-text. **TTS**: text-to-speech.
  - **S2S**: a speech-to-speech model. It takes audio in and gives audio out, with no separate STT or TTS.
  - **VAD**: voice activity detection. A small model that labels each audio frame as speech or silence.
  - **Endpointing**: the decision that the user has finished the turn. A VAD silence timeout is the simplest endpointer.
  - **End-of-speech wait**: the silence the system waits before it ends the user's turn.
  - **Turn model**: a classifier that predicts whether a turn is complete from audio or text. Smart Turn and the LiveKit turn detector are turn models.
  - **False cutoff**: the agent ends the user's turn while the user is still speaking.
  - **Barge-in**: the user starts speaking while the agent speaks. **False barge-in**: the system treats echo, noise or a short "mm-hm" as a barge-in.
  - **AEC**: acoustic echo cancellation. It removes the agent's own voice from the microphone signal.
  - **TTFT**: time to first token of an LLM. Module 1 defines it.
  - **TTFA**: time to first audio. Time from the request to the first audio byte or sample.
  - **STT final**: the transcript event that the STT service marks as no longer changing.
  - **Jitter buffer**: a receive buffer that holds audio packets so late packets can play in order.
  - **p50, p95**: the 50th and 95th percentile of a latency distribution.
  - **Sum of tails**: the sum of each stage's p95. It is not the p95 of the total.
  - **Playout clock**: the count of audio the listener has actually heard.
  - **PSTN**: the public telephone network. **G.711**: the 8 kHz, 64 kbit/s telephone codec. **PCMU** is G.711 μ-law.
  - **Full duplex**: both sides can speak at the same time, and the model decides when to talk.

---

## 1. Purpose and the module question

Module 1 teaches TTFT and streaming for text. This module owns the audio path and the real-time budget. It covers every stage between the user's last word and the agent's first sound, what each stage costs per minute, and what a phone line adds.

The short answer: **a default chained pipeline on public APIs spends about 1.6 s at p50 and 2.1 s at p95. The end-of-speech wait and the LLM TTFT take about 70% of it. To reach one second at p50, you give up complete turns, reasoning and region choice. No configuration in the sources fits one second at p95 on public APIs.**

| Part of the question | Short answer | Where |
|---|---|---|
| Where the budget goes, chained | Default settings: end-of-speech wait 500 ms, STT final 66 ms, LLM TTFT 597 ms, TTS 183 ms, network, jitter and device audio 203 ms. p50 1,586 ms. Every simulated turn is over 1,000 ms | 4.1, 4.2, 5.1 |
| Where the budget goes, S2S | Measured model TTFA is 0.81 s to 1.35 s. Whether that includes the VAD wait is a gap. With a 500 ms VAD, p50 is 1.2 s to 1.7 s | 4.6, 5.1 |
| Give up 1: complete turns | A 250 ms endpoint is fast. On LiveKit's benchmark, Smart Turn v3.2 cuts off 35.2% of turns at a 300 ms budget. The silence-only baseline cuts off 55.6% | 4.2, 4.3 |
| Give up 2: reasoning | Fast LLMs are non-reasoning. Reasoning settings move TTFT from 0.77 s to 130 s for one model. Faster S2S models score lower on reasoning | 4.5, 4.6 |
| Give up 3: region and vendor choice | Every independent number comes from one US region. From India, the primer gives about 350 ms of round-trip network time | 4.1, 4.4 |
| Give up 4: the p95 | The tuned chained case reaches p50 915 ms. Its p95 is still 1,313 ms, because the LLM tail remains | 4.5 |
| Give up 5: control, with S2S or full duplex | The model owns turn-taking and truncation. You lose the endpointing knob and the per-stage view | 4.6, 4.12 |
| What it costs per minute | On one set of stated assumptions: chained $0.0234, or $0.0263 at Deepgram's regular price, gpt-realtime-2.1 $0.0479, gpt-live-1 $0.05, Gemini 3.8 Live $0.0093 to $0.0492. The assumptions move the answer more than the list price | 4.7, 5.3 |
| How barge-in works and what it costs | Two separate gates. A longer start gate removes false barge-ins and delays every true one. Echo cancellation must work first. The context must be cut at the playout clock | 4.8, 4.9, 4.10 |
| What telephony adds | 8 kHz narrowband audio, a carrier path with its own delay and jitter buffer, and a TCP WebSocket. The G.711 coder adds 0.375 ms. The 20 ms packet adds 20 ms at the sender. The added milliseconds on a real call are not measured in any source | 4.11 |

Summary: the budget goes to waiting for the user to finish and waiting for the LLM to start. Cutting either one costs turn quality or answer quality.

---

## 2. Scope

### In scope

- The voice-to-voice budget, stage by stage, for a chained pipeline and for S2S models. p50 and p95.
- Endpointing: VAD timeouts, turn models, their defaults at release tags, and the false-cutoff trade.
- Vendor latency claims against independent measurements.
- Cost per minute for both paths, on one set of stated assumptions, and how the assumptions move it.
- Barge-in detection, echo cancellation, and cutting the model's context at the interruption point.
- Telephony: G.711, 8 kHz narrowband, carrier delay planning values, media-stream WebSockets, DTMF.
- How Pipecat, LiveKit Agents and OpenAI's realtime APIs place these functions.
- Versions and defaults on 2026-09-25.

### Out of scope, and the owner of each item

| Topic | Owner |
|---|---|
| What TTFT and TPOT are, and how prefill sets TTFT | Module 1, built sections 0.2 and 1.2 |
| Measuring TTFT from a stream, the `usage` object | Module 1, built section 1.6 |
| Stream deadlines and the three timeouts | Module 1, built section 5.1 |
| Token classes, modality multipliers, `audio_tokens` fields | Module 1, built section 3.1 |
| Prefix caching mechanics and cache prices | Module 1, built sections 3.2 and 3.3 |
| Percentiles in SLOs | Module 1, built section 5.4, subsection "Use several percentiles, not one" |
| Self-hosting models on GPUs for lower latency | Module 1, built section 4.6. Module 13, built, `serving-cluster-phase-01-breakeven.md` section "1.1 — The latency target sets break-even, not the GPU price" |
| Per-tenant budgets, gateways and bill decomposition | Module 14, built, `ai-finops/ai-finops-phase-01-metering.md` to `-phase-04-bill.md` |
| TTFT metric names in OpenTelemetry, naming per-stage metrics | Module 1, built section 5.5. Module 15, being written. `observability-ops-phase-01-names.md` sections "1.1 — GenAI names have no release, so pin a commit" and "1.2 — Name what the spec lacks under your own prefix" |
| Task success of a voice agent, simulated users, τ-Voice | Module 12, built. `agent-evals-phase-03-reliability.md` line 728 mentions the tau2-bench voice section only |
| Prompt injection through audio | Module 16, built, `security/security-phase-01-threat-model.md` to `-phase-05-supply-chain.md`. `grep -iE 'voice|audio|speech'` on them finds 0 hits |

### Overlap with built modules

Headings were read with `grep '^## '` on `study-material/*/*.md` on 2026-09-25. The reviewer re-ran the grep on the same day. Modules 1 to 12 are built. Module 13 `serving-cluster/`, Module 14 `ai-finops/` and Module 16 `security/` now also have built phase files. Module 15 `observability-ops/` has four phase files and is being written. The first draft said Modules 13 to 16 had dossiers only. That was wrong on the review date. The reviewer grepped all four folders for `voice|audio|speech|telephon|barge`. The only hits are the word "invoice" in Module 14 and one comment about audio routes in `ai-finops-phase-02-budgets.md` line 357. No built module has a section on voice, VAD, barge-in or telephony.

| Built heading | What it owns | What this module adds |
|---|---|---|
| Module 1, "0.2 — The three numbers that rule you" | TTFT, TPOT and cost per token | TTFT becomes one stage of eight. Link 0.2. Do not re-teach |
| Module 1, "1.2 — Prefill (your prompt meets the GPU; where TTFT comes from)" | Why prompt length sets TTFT | 4.5 notes that AA measures TTFT at about 10,000 input tokens, not at a voice-sized prompt. Link 1.2 |
| Module 1, "1.6 — Streaming and usage (how to measure like an engineer)" | TTFT measured from a text stream | Voice-to-voice measured from a waveform, and vendor TTFA that leaves out network and audio, 4.4. Link 1.6 |
| Module 1, "5.1 — Streaming and the three timeouts (your one timeout is the wrong one)" | Deadlines on a text stream | A barge-in cancels a stream on purpose, then the context must be cut, 4.10. Link 5.1 |
| Module 1, "2.4 — Chunked prefill (the trade between TTFT and TPOT)" | Server-side TTFT trade | Not repeated |
| Module 1, "3.1 — The five token classes, and two multipliers" | Modality multipliers and the `audio_tokens` field | 4.7 uses audio token prices and rates as inputs. Link 3.1 |
| Module 1, "3.2 — Implicit prefix caching" and "3.3 — Explicit caching with cache_control" | How a prefix cache works and what a hit costs | 4.7: the OpenAI realtime cost depends on best-effort caching. $0.048 against $0.294 per minute. Link 3.2 |
| Module 1, "5.4 — SLOs for a thing that can be up, fast, and wrong" | Several percentiles, not one | 4.5 adds that the sum of stage p95 values is not the p95 of the total. Link 5.4 |
| Module 1, "4.6 — The self-host decision (arithmetic, not preference)" | Self-host break-even | The primer's 500 ms voice-to-voice needs co-located self-hosted models, 4.1. Link 4.6 and Module 13 section 1.1 |
| Module 1, "6.1 — Capacity planning" | Replicas from your own numbers | Not repeated |
| Module 13, "1.1 — The latency target sets break-even, not the GPU price" and "2.1 — Splitting buys latency control, not throughput" | A TTFT limit decides the self-host fleet | A voice TTFT limit is one input to that decision. Link 1.1. Do not re-teach serving |
| Module 15, "1.2 — Name what the spec lacks under your own prefix" | Custom metric and span names | Per-stage voice timings, such as end-of-turn delay and TTFA, need names. Link 1.2. Do not re-teach telemetry |

Summary: Module 1 owns TTFT for text. This module treats TTFT as one input, and owns the audio stages around it.

---

## 3. Sources, with dates, tags and versions

Rank follows `research-method.md` Rule 2. Rank 1 is source code at a tag. Rank 2 is versioned docs. Rank 3 is a paper. Rank 5 is a vendor post with conditions. Rank 6 is a vendor post without conditions.

### 3.1 Code at release tags and package versions

All versions checked on PyPI JSON on 2026-09-25. Upload times are UTC.

| Package | Version | Upload | What was read | Rank |
|---|---|---|---|---|
| livekit-agents | 1.8.3 | 2026-09-23T19:04 | `LK/voice/turn.py`, `voice/audio_recognition.py`, `voice/agent_session.py`, `voice/agent_activity.py`, `inference/interruption.py`, `inference/eot/detector.py` | 1 |
| livekit-plugins-silero | 1.8.3 | 2026-09-23T19:06 | `LKS/vad.py` defaults | 1 |
| livekit-plugins-turn-detector | 1.8.3 | 2026-09-23 | README marks it deprecated. It holds the old text model | 1 |
| pipecat-ai | 1.11.0 | 2026-09-18T04:11 | `PC/audio/vad/vad_analyzer.py`, `turns/user_turn_strategies.py`, `audio/turn/smart_turn/base_smart_turn.py`, `services/tts_service.py`, `serializers/twilio.py`. Requires Python 3.11 or later | 1 |
| silero-vad | 6.2.3 | 2026-09-23T11:37 | `BS/silero_utils_vad_v6.2.3.py`, read at GitHub tag `v6.2.3`. Depends on torch | 1 |
| webrtcvad-wheels | 2.0.14 | 2024-09-05 | README only. The original `webrtcvad` 2.0.10 is from 2017 | 1 |
| twilio | 9.11.1 | 2026-09-10 | Not read. Version only | not applicable |
| telnyx | 4.181.0 | 2026-09-23 | Not read. Version only | not applicable |
| openai | 3.19.2 | 2026-09-24 | Not read. Version only | not applicable |

GitHub release API calls failed with a rate-limit error in both reports. The budget report confirmed tags by fetching files at the tag. The realtime report read the PyPI sdists.

### 3.2 Documentation and price pages, fetched 2026-09-25

| Source | Org | What to read | Notes |
|---|---|---|---|
| API pricing, `.md` form | OpenAI | "Realtime and audio generation models", "Transcription models", "GPT-Live sessions" | Rank 2. `BS/openai_pricing_md.html` |
| GPT-Live 1 model page | OpenAI | Pricing | `BS/openai_gpt_live_1.md`. No release date on the page |
| Voice latency and cost guide | OpenAI | Audio token rates, Realtime costs, GPT-Live costs | `BS/openai_voice_latency.md`, `BS/openai_realtime_costs.txt` |
| Realtime client events reference | OpenAI | `turn_detection` defaults, `conversation.item.truncate` | `RS/oai_rt_client_events.txt`. Rank 2 for defaults |
| Realtime VAD guide | OpenAI | `server_vad`, `semantic_vad` | `BS/openai_realtime_vad.md`. Shows 500 ms in an example |
| Realtime conversations guide | OpenAI | "Interruption and Truncation" | `RS/oai_rt_conversations.txt` |
| SIP guide, GPT-Live guides | OpenAI | SRTP, DTMF events, "remove manual audio commits" | `RS/oai_rt_sip.txt`, `RS/oai_live*.txt` |
| Gemini API pricing, `.md.txt` form | Google | "Gemini 3.8 Live" row, Transcribe Live, TTS, 2.5 Flash | `BS/gemini_pricing.md.txt`. The HTML page redirects to a sign-in for plain fetchers |
| Live API capabilities, session management | Google | "Impact of silenceDurationMs", 15-minute audio session limit | `BS/gemini_live_api_capabilities.md.txt`, `BS/gemini_live_session.md.txt` |
| Deepgram, AssemblyAI, ElevenLabs, Cartesia, xAI pricing | each vendor | STT, TTS and agent per-minute prices | Deepgram prices are in embedded JSON. Cartesia sells credits |
| Twilio Media Streams overview and WebSocket messages | Twilio | `mark`, `clear`, `dtmf`, format rules | `RS/twilio_media_streams*.txt` |
| Telnyx media streaming | Telnyx | Codecs, `clear`, `mark` | `RS/telnyx_media_streaming.txt` |
| LiveKit docs: turn detector, SIP codecs, HD voice, DTMF | LiveKit | Model selection, fallback, codec list | `RS/lk_*.txt`, `RS/lk_*.md` |
| Pipecat docs: interruptions, pipeline | Daily | "What ends up in the context" | `RS/pipecat_docs_*.md` |
| W3C Media Capture and Streams, editor's draft | W3C | `EchoCancellationModeEnum` | `RS/w3c_mediacapture.txt`. Not a Recommendation |
| WebRTC NetEq design doc | Google | GetAudio loop | Header says "reviewed: '2021-04-13'". May be stale |

Re-fetched by the reviewer on 2026-09-25 at about 00:00 UTC, all HTTP 200:
- `developers.openai.com/api/docs/pricing.md`. The realtime and GPT-Live rows are identical to `BS/openai_pricing_md.html`. gpt-realtime-2.1 audio is still $32.00, $0.40 and $64.00. gpt-live-1 is still $0.05 per minute.
- `developers.openai.com/api/docs/guides/realtime-vad.md`. It still shows `"silence_duration_ms": 500` inside an example.
- `docs.livekit.io/agents/logic/turns/turn-detector/`. The 0.25 s `min_silence_duration` rule and the v1 and v1-mini text match `RS/lk_turn_detector.txt`.
- `raw.githubusercontent.com/livekit/eot-bench/main/README.md`. Byte-identical to `RS/eot-bench_README.md`.

### 3.3 Standards and papers

| Source | Org | Year | Status | What to read |
|---|---|---|---|---|
| RFC 3551, 4733, 6716, 7587, 7874 | IETF | 2003 to 2016 | Standards Track | PCMU clock and packet, DTMF events, Opus bands, WebRTC codec rules |
| ITU-T G.114 (05/2003) | ITU-T | 2003 | Recommendation | One-way delay limits, Table A.1, Table I.1, de-jitter rule |
| Mantena et al., arXiv 1909.02667 | Apple | 2019 | Preprint. Venue not checked | Table 2, narrowband WER |
| arXiv 2606.09335, Indic ASR factors | academic | June 2026 | Preprint | Section 2.1.2 and Figure 2(b). Numbers are in the figure only |
| Stivers et al., PNAS | PNAS | 2009 | Peer reviewed | HTTP 403 to curl. Not read. Not used |

### 3.4 Benchmarks and practitioner sources

| Source | Org | Date and version | Vendor status | What to read |
|---|---|---|---|---|
| Voice AI and Voice Agents: An Illustrated Primer | Daily, the Pipecat maintainer | "This update was published in June 2026", `BS/voiceai_primer.txt` line 124 | Sells WebRTC infrastructure. Not peer reviewed | 5.1 latency table, 5.2 TTFT table, 5.8 turn detection, 11.2 cost |
| The World's Fastest Voice Bot | Daily | 2024 | Same | Older 800 ms target, for contrast |
| Artificial Analysis speech-to-speech leaderboard and methodology | Artificial Analysis | Fetched 2026-09-25 | Independent benchmark company | TTFA, Big Bench Audio, cost per hour of input audio |
| Artificial Analysis streaming STT leaderboard and methodology | Artificial Analysis | Fetched 2026-09-25 | Same | Time to final after a forced endpoint |
| Artificial Analysis LLM leaderboard and performance methodology | Artificial Analysis | Median over 72 hours, fetched 2026-09-25 | Same | `medianTimeToFirstTokenSeconds`, server `us-central1-a` |
| TTS benchmark by Coval, mirrored by Openbenchmarks | Coval | Pulled 2026-09-24 10:48 UTC, rolling 7 days, pinned dataset `286de7c17410` | Sells voice-agent evaluation. Does not sell TTS | TTFA median and p95 per model |
| coval-ai/benchmarks README | Coval | Read at `main`, no tag | Same | TTFA definition, `us-east-1` |
| eot-bench | LiveKit | 2026. Commit not recorded | Vendor ranks its own model first | Results table, policy sweep |
| Smart Turn README, v3 and v3.2 posts | Daily | v3 post dated "Sep 11, 2025", `RS/daily_smartturn_v3.txt` line 78. v3.2 post dated "Jan 7, 2026", `RS/daily_smartturn_v32.txt` line 79 | Vendor | Architecture, CPU timing table |
| turn-detection-benchmark | one individual, `txya900619` | 2026 | Personal repo. Not peer reviewed | SmartTurn v3.2 on FastTurn |
| Silero VAD wiki | Silero | Performance page edited 2024-06-27 | Vendor | ROC-AUC and speed tables |

### 3.5 What changed recently

| Date | Change | Source | Why it matters |
|---|---|---|---|
| 2026-04-14 | Pipecat 1.0.0. Turn logic moved to start and stop strategies. The default stop strategy is a turn model | Pipecat CHANGELOG, realtime report 3 | A Pipecat end-of-speech wait is no longer a VAD timeout |
| June 2026 | Primer update. The target moves to 1,500 ms voice-to-voice | `BS/voiceai_primer.txt` lines 124 and 212 | The 2024 post targeted "800ms median" |
| 2026, date not checked | OpenAI GPT-Live 1: full duplex, $0.05 per minute, backend billed separately | `BS/openai_gpt_live_1.md` line 23 | Silence and idle time are now billed. Turn-taking moves into the model |
| 2026, date not checked | OpenAI gpt-realtime-2 and 2.1, 2.1-mini, gpt-realtime-whisper, gpt-live-transcribe | `BS/openai_pricing_md.html` | Same audio prices as gpt-realtime |
| 2026 | Gemini 3.8 Live is stable. Docs state an 800 ms default VAD silence | `BS/gemini_live_api_capabilities.md.txt` line 1016 | The largest end-of-speech default in the sources |
| 2026, date not checked | LiveKit audio turn detector, `v1` in the cloud and `v1-mini` local, replaces the text detector | `RS/lk_turn_detector.txt` | The text model is "slated for removal in version 2.0" |
| 2026, date not checked | LiveKit "adaptive" interruption, a cloud classifier for barge-in against backchannel | `LK/inference/interruption.py` | Off by default outside LiveKit Cloud |
| livekit-agents 1.8.3, 2026-09-23 | `min_endpointing_delay` deprecated for `turn_handling=TurnHandlingOptions(...)` | `LK/voice/agent_session.py` lines 373 to 374 | Older examples use a parameter that will go |
| livekit-agents 1.8.3, 2026-09-23 | With no `turn_detection` argument, the session uses the audio turn detector, `inference.TurnDetector()`. Preemptive LLM generation is on by default | `LK/voice/agent_session.py` lines 562 to 566. `LK/voice/turn.py` lines 223 to 228 | The out-of-box wait is the 0.3 s turn-detector policy, not the 0.5 s VAD policy. See 4.2 |
| 2026 | Artificial Analysis publishes a streaming STT benchmark with forced endpointing | `BS/aa_methodology_speech_to_text.txt` | The first cross-vendor STT-final number found |
| 2026-12-31 | Gemini 3.8 Flash TTS price doubles on 2027-01-01, $9 to $18 per 1M audio tokens | `BS/gemini_pricing.md.txt` line 650 | A cost model built today is wrong in three months |
| Python 3.13, October 2024 | `audioop` removed from the standard library | Pipecat `pyproject.toml` | μ-law code needs `audioop-lts` |

---

## 4. Core concepts, with verified facts

Each heading is a claim a senior engineer could get wrong. Each concept gives one best piece of evidence first, with its conditions. Every anchor below was re-grepped by `D20/anchor_check.py`. 127 of 127 match.

Prototype conditions for every "verified by run" number from `BP/run_output.txt`: Monte Carlo with n = 60,000 turns, seed 7, each stage a lognormal fitted to its p50 and p95, stages independent. Browser client over WebRTC, agent in the same cloud region as the models. Python 3.9.6. Run time 6.4 s. p95 values marked "A" in section 5.1 are the budget researcher's assumptions.

### 4.1 A default chained pipeline does not fit in one second. The end-of-speech wait and the LLM TTFT take about 70% of it

- **Best evidence, verified.** The primer's "fairly typical" round trip totals 1,293 ms. It includes "transcription and endpointing 300" and "llm ttfb 650". `BS/voiceai_primer.txt` lines 158 to 195. Conditions: macOS microphone and speaker, Opus over WebRTC, no region, no sample count, no percentile. The dossier author re-added the 16 rows: 1,293. The primer's text says "the total is about 1,200 ms". The table is the number to use.
- **Verified by run.** Prototype, default settings: p50 1,586 ms, p95 2,129 ms. 100% of simulated turns exceed 1,000 ms. The end-of-speech wait is 500 ms and the LLM TTFT p50 is 597 ms. Together they are 1,097 of the 1,569 ms p50 sum, which is 69.9%. `BP/run_output.txt`.
- **Verified by run.** The tuned case reaches p50 915 ms and p95 1,313 ms. 31.6% of turns still exceed 1,000 ms. Its settings: a 250 ms endpoint, Soniox v5 STT, gemini-2.5-flash-lite TTFT 304 ms, Inworld TTS 63 ms.
- **Verified quote, vendor claim.** The primer's authors now aim for 1,500 ms: "People are happy talking to agents that respond within 1,500 ms." Line 212. Daily sells the infrastructure. They publish no data for it.
- **Verified quote, vendor claim.** 500 ms voice-to-voice needs self-hosting: "by hosting all models within the same GPU-enabled cluster". Line 196. Daily reports this about its own Pipecat demos. It gives no percentile, region or sample count. That is not a public-API result. Module 13 section 1.1 owns the self-host arithmetic.
- **Verified. Region.** "From Europe, round-trip network time to the US is ~250 ms; from India, ~350 ms." Line 312. The prototype assumes 24 ms of network for both directions. One cross-region round trip per external API call breaks the budget. The primer does not say how it measured this. Not checked.

### 4.2 The end-of-speech wait is a setting, not a model cost. Defaults run from 100 ms to 800 ms, and the setting that ends the turn is often not the one you see

- **Best evidence, verified.** Google's Live API docs: "The server's internal default is approximately 800ms." `BS/gemini_live_api_capabilities.md.txt` line 1016. The OpenAI Realtime reference for `server_vad`: "Defaults to 500ms". `RS/oai_rt_client_events.txt` lines 546 to 548. This settles a question the budget report left open. Section 7, conflict a.

| Tool, version | What ends the turn by default | Evidence and label |
|---|---|---|
| Gemini Live API, automatic VAD | About 800 ms of silence | Verified, line 1016 above |
| OpenAI Realtime `server_vad` | 500 ms of silence, `prefix_padding_ms` 300, `threshold` 0.5 | Verified, `RS/oai_rt_client_events.txt` lines 543 to 550 |
| OpenAI Realtime `semantic_vad` | A model decides. Maximum timeouts 8 s, 4 s and 2 s for eagerness low, medium and high. `auto` equals medium | Verified, same file line 560 |
| LiveKit Agents 1.8.3, VAD mode, Silero plugin. Only when the app sets `turn_detection` to VAD or STT mode | Silero `min_silence_duration` 0.55 s fires end of speech. The 0.5 s `min_delay` is counted from the back-dated speech end, so it adds nothing. The wait is about 0.55 s plus inference | Defaults verified: `LKS/vad.py` line 64, `LK/voice/turn.py` line 137. The timing is **inferred from the code, not run**: `LK/voice/audio_recognition.py` sets `speech_end_time = time.time() - ev.silence_duration - ev.inference_duration`, then `extra_sleep = endpointing_delay` plus `last_speaking_time - time.time()`, lines 1437 and 1716 to 1718. Section 7, conflict c |
| LiveKit Agents 1.8.3, out of the box, with the audio turn detector | This is the default. With no `turn_detection` argument, the session builds `inference.TurnDetector()`. `min_delay` 0.3 s, `max_delay` 2.5 s. If the model gives no prediction "within about a second", the agent commits the turn | Verified in code: `LK/voice/agent_session.py` lines 562 to 566, `LK/voice/turn.py` lines 142 to 147 and 307 to 311, `LK/inference/eot/detector.py` line 34. Verified in docs: `RS/lk_turn_detector.txt` lines 205 to 214. The resulting wait in ms is **not checked**. Section 7, conflict b |
| Pipecat 1.11.0 | VAD `stop_secs` 0.2 s starts a Smart Turn v3 check. The turn ends when the model says "complete". If it does not, a 3 s fallback ends it | Verified, `PC/audio/vad/vad_analyzer.py` line 27, `PC/turns/user_turn_strategies.py` line 53, `PC/audio/turn/smart_turn/base_smart_turn.py` line 27. Section 7, conflict d |
| Silero VAD 6.2.3 `get_speech_timestamps` | `min_silence_duration_ms` 100 | Verified, `BS/silero_utils_vad_v6.2.3.py` line 287. An offline segmenter, not an agent endpointer |

- **Verified. A short wait alone cuts users off.** Google: at 100 ms to 200 ms "The system ends speech turns during natural pauses". The model then gets fragments and gives "lower transcription and response quality". `BS/gemini_live_api_capabilities.md.txt` line 1017.
- **Verified by run, synthetic.** With VAD-only endpointing on the prototype's made-up pause distribution, clipped turns fall from 66.2% at 200 ms to 38.4% at 500 ms and 0.3% at 3,000 ms. `RP/run_output_py39.txt`, A1. The rates show the mechanism, not real rates.
- **Verified.** LiveKit's audio turn detector requires VAD `min_silence_duration` of at least 0.25 s. A lower value raises `ValueError`. `RS/lk_turn_detector.txt` line 215. Re-fetched 2026-09-25, unchanged.
- **Verified default, effect inferred. Preemptive generation hides part of the wait.** Preemptive generation starts the LLM on the transcript before the turn is confirmed. If the user keeps talking, the framework discards that reply. LiveKit Agents 1.8.3 turns it on by default for the LLM only: `"enabled": True`, `"preemptive_tts": False`, `"max_speech_duration": 10.0`, `"max_retries": 3`. `LK/voice/turn.py` lines 201 to 228.
  - **Inferred.** The LLM TTFT then overlaps the end-of-speech wait instead of following it. The serial sums in 4.1 and 5.1 overstate a LiveKit default pipeline by up to the smaller of the two stages. `BP/budget.py` does not model this. Check: run an `AgentSession` with and without `preemptive_generation`, and compare voice-to-voice on the waveform.
  - **Inferred.** The price is LLM tokens. Each discarded attempt is billed, up to 3 per turn. No source gives a discard rate.

### 4.3 A turn model moves the trade-off between fast replies and cut-off turns. It does not remove it

- **Best evidence, verified, vendor on vendor data.** LiveKit eot-bench, English. The silence-only VAD baseline needs 1,600 ms of dead air to keep false cutoffs at 5%. At a 300 ms budget it cuts off 55.6% of turns. `RS/eot-bench_README.md` lines 76 to 90. Conditions: LiveKit's dataset `livekit/eot-bench-data`, every pause of 100 ms or more annotated, a policy sweep over threshold, action delay and timeout. The latency is endpointing delay, not compute time. LiveKit's own model ranks first.

| Detector | False cutoffs at 300 ms | False cutoffs at 600 ms | Latency at 5% cutoffs | Latency at 10% cutoffs |
|---|---:|---:|---:|---:|
| LiveKit Turn Detector v1, cloud | 9.9% | 4.5% | 543 ms | 295 ms |
| Deepgram Flux | 12.9% | 9.9% | 1,151 ms | 548 ms |
| LiveKit Turn Detector v1-mini, local | 27.8% | 12.1% | 1,070 ms | 698 ms |
| SmartTurn v3.2 | 35.2% | 14.8% | 1,051 ms | 739 ms |
| OpenAI GPT Realtime 2 | no setting reached it | no setting reached it | 1,143 ms | 824 ms |
| VAD baseline | 55.6% | 21.7% | 1,600 ms | 1,000 ms |

- **This is the main price of a sub-second budget.** The tuned case in 4.1 uses the primer's "~250ms" turn decision, `BS/voiceai_primer.txt` line 582. That is a **vendor claim**: Daily describes its own Smart Turn and Pipecat, with no data, percentile or sample count. On eot-bench, SmartTurn v3.2 at a 300 ms budget cuts off 35.2% of turns. The primer's 250 ms is the time to a decision. The eot-bench figure is the cutoff rate at that delay. Both can be true. The prototype's latency model does not count cutoffs. Section 7, conflict e.
- **Verified, third party, not peer reviewed.** On the FastTurn subset at a fixed threshold of 0.5, SmartTurn v3.2 called 54.74% of incomplete turns complete. `RS/turn_bench_README.md` lines 368 to 385. A personal repo. The README calls the threshold "a production-default reference". The language mix of FastTurn is not checked.
- **Verified by run, synthetic.** Prototype A1b: a 200 ms gate plus a turn model with 0.993 and 0.870 accuracy clips 11.3% of turns. Those two inputs are LiveKit's English true positive and true negative rates for its **deprecated text** turn detector, a Qwen2.5-0.5B model. `RS/lk_turn_detector.txt` lines 440 to 481. They are vendor claims on vendor data. They are not Smart Turn rates and not the audio detector's rates. When hold accuracy on real pauses falls to 0.60, clips rise to 29.3%. `RP/run_output_py39.txt`. Model accuracy is an input, not evidence.
- **Where it does not hold.** No neutral benchmark was found. eot-bench, Daily's Smart Turn tests and the FastTurn repo use different data and scorers. Teach the mechanism and the VAD baseline, not a ranking.

### 4.4 Vendor latency numbers leave out network and audio. Independent numbers for the fastest-claimed TTS models are 2 to 4 times higher

- **Best evidence, verified.** ElevenLabs claims "Ultra-low latency (~75ms)" for Flash and Turbo. `BS/elevenlabs_api_pricing.txt` line 61. **Vendor claim.** Coval measures `eleven_flash_v2_5` at 183 ms median and 227 ms p95 TTFA over 3,257 samples. `BS/openbench_coval_tts.txt`. That is 2.4 times the claim at the median and 3.0 times at p95. Conditions: workers in AWS `us-east-1`, `BS/coval_benchmarks_README.md` line 115. TTFA counts to the first audible sample, "including front-loaded silence", README line 28. The Openbenchmarks mirror defines TTFA as the time "to the first byte of audio coming back", `BS/openbench_coval_tts.txt` line 279. The two definitions differ for a model that sends silence first. The README is the runner's own text, so use it. Rolling 7 days, pulled 2026-09-24 10:48 UTC, dataset `286de7c17410`.
- **Verified.** Cartesia claims "sub-90ms latency". `BS/cartesia_sonic.txt` line 17. **Vendor claim**, model not named. Coval measures `sonic-3.5` at 285 ms median and 361 ms p95, and `sonic-3.6` at 316 ms and 383 ms. That is 3.2 to 3.5 times at the median and 4.0 to 4.3 times at p95.
- **Verified. Why.** The primer: provider numbers measure inference time. That "does not account for audio processing, phrase endpointing delay, network transport, and operating system overhead". `BS/voiceai_primer.txt` line 153.
- **Where it does not hold. Verified.** ElevenLabs claims "Low latency (~280ms)" for v3 Conversational. Coval measures 318 ms median and 399 ms p95. That is 1.1 and 1.4 times. The 2 to 4 times range belongs to the two fastest claims only.
- **Verified. A tail can be larger than the budget.** Coval measures OpenAI `gpt-4o-mini-tts` at 558 ms median and 4,165 ms p95. The p95 is 7.5 times the median. OpenAI publishes no latency number for it or for gpt-realtime-2.1 and gpt-live-1. Absence checked by grep in the budget report.
- **Not checked.** Every independent TTS number comes from `us-east-1`. The learner's region may differ.

Vendor latency claims found, all labelled **vendor claim**. None states a region, a network path or, except AssemblyAI, a percentile.

| Vendor and model | Claim | Source |
|---|---|---|
| ElevenLabs Flash / Turbo | "Ultra-low latency (~75ms)" | `BS/elevenlabs_api_pricing.txt` line 61 |
| ElevenLabs v3 Conversational | "Low latency (~280ms)" | same, line 41 |
| ElevenLabs Scribe v2 Realtime, STT | "Low latency (~150ms)" | same, line 89 |
| Cartesia Sonic | "sub-90ms latency" | `BS/cartesia_sonic.txt` line 17 |
| AssemblyAI Universal-3.5 Pro, request and response | "~134 ms (p50)" | `BS/assemblyai_pricing.txt` line 317. Not the streaming endpoint |
| xAI Voice APIs | "sub-second latency" | `BS/xai_voice.txt` line 183 |
| Google Gemini 3.8 Live | "ultra-low latency", no number | `BS/gemini_38_live_model.md.txt` line 29 |

### 4.5 The p95 of the total is lower than the sum of stage p95 values, but the LLM tail still sets it. On public APIs, no configuration in the sources fits one second at p95

- **Best evidence, verified by run.** Default chained case: the sum of stage p95 values is 2,313 ms. The Monte Carlo p95 of the total is 2,129 ms. Removing the LLM stage lowers the total p95 by 1,045 ms. Flattening only the LLM tail to its median lowers it by 448 ms. No other stage saves more than 176 ms. `BP/run_output.txt`. Condition: independent stages.
- **Verified by run.** In the tuned case the LLM is still first to cut: 614 ms saved if removed, 310 ms if its tail is flattened.
- **Verified. The LLM tail is real.** The primer's TTFT table gives GPT-4.1 536 ms median and 1,771 ms P95, and Gemini 2.5 Flash 597 ms and 1,137 ms. `BS/voiceai_primer.txt` lines 200 to 232. "recently all providers have had worse P95 times from their public APIs than we would like to see." Not checked: region, prompt length and sample count for this table.
- **Verified. Reasoning settings decide TTFT.** Artificial Analysis lists gpt-5.4-mini at 130.2 s median TTFT with default reasoning and 0.774 s with reasoning off. `BS/aa_llm_ttft_extracted.tsv`. Conditions: median over 72 hours, server in Google Cloud `us-central1-a`, default workload about 10,000 input tokens, `BS/aa_methodology_llm.txt` lines 38 and 71. The primer's limit is "TTFT (first non-thinking token) faster than 700ms". Line 294.
- **Inferred.** A voice turn with a 2,000-token prompt would see a lower TTFT than AA's 10,000-token workload. Module 1 section 1.2 explains why. Check: time TTFT at 2,000 tokens in the learner's region.
- **Where it does not hold.** If stages are correlated, the p95 of the total moves toward the sum of tails. One congested network path can slow STT, LLM and TTS together. The prototype does not model this. Lab 6.2 B would show it.

### 4.6 Speech-to-speech is not faster by default. Measured time to first audio is 0.81 s to 1.35 s, and faster models score lower on reasoning

- **Best evidence, verified.** Artificial Analysis TTFA on Big Bench Audio: GPT-Realtime-2.1 Minimal 0.97 s, Gemini 3.8 Live 1.18 s, GPT-Realtime-2.1 High 1.21 s, GPT-Live-1 Sol low 1.24 s. `BS/aa_s2s.txt`. The dossier author read each row in the table order Provider, Model, Index, Speech Reasoning, Conversational Dynamics, Agentic Performance, Arena Elo, Task Success, TTFA, cost. Header at lines 186 to 197.
- **Verified.** AA defines TTFA as the "Average number of seconds required to generate the first token of audio output". `BS/aa_methodology_s2s.txt` line 191. It is an average over reasoning questions, not a percentile.
- **Gap, not a fact.** AA does not say where its TTFA timer starts. It does not say whether server VAD is on, or whether the VAD wait is inside the 0.97 s. It does not state the test region. The prototype shows both cases. If the VAD wait is outside, S2S p50 is 1,678 ms and p95 2,161 ms. If a 500 ms VAD wait is inside, p50 is 1,179 ms and p95 1,659 ms, with 86.5% of turns over one second. Even the second case does not fit one second at p50. Section 8, gap 1.

| Model | TTFA, s | Speech reasoning, Big Bench Audio |
|---|---:|---:|
| GPT-Realtime-1.5 | 0.81 | 81% |
| GPT Realtime Mini, Oct '25 | 0.81 | 64% |
| Gemini 3.1 Flash Live Minimal | 0.96 | 71% |
| GPT-Realtime-2.1 Minimal | 0.97 | 87% |
| Gemini 3.8 Live | 1.18 | 92% |
| GPT-Realtime-2.1 High | 1.21 | 96% |
| GPT-Live-1, Sol, low | 1.24 | 89% |
| Gemini 3.8 Live Extended Thinking, High | 1.35 | 98% |

- **Pattern, inferred from this table only.** Faster rows score lower on reasoning. The trade is the same one as 4.5. Eight rows is not a fit.
- **Verified.** The primer: speech-to-speech models "are also slower, more expensive, less configurable". `BS/voiceai_primer.txt` line 273.
- **Where S2S may win.** Turn-taking. The table's Conversational Dynamics column runs from 72.3% to 97.3% for these models. AA builds it on a subset of Full Duplex Bench v1 and v1.5, `BS/aa_methodology_s2s.txt` line 51. AA cites them as "Lin et al., 2025". Whether they are preprints or peer reviewed is not checked. It is not a latency measure.

### 4.7 Cost per minute depends on talk ratio, turns per minute and tokens per turn. On one stated set of assumptions, the chained path costs half as much as gpt-realtime-2.1, and TTS is the largest chained line

- **Best evidence, verified by run, prices fetched 2026-09-25.** The chained path, Deepgram Nova-3 plus Gemini 2.5 Flash plus ElevenLabs Flash, costs $0.0234 per minute. TTS is $0.0180 of that, STT $0.0048 and the LLM $0.0006. gpt-realtime-2.1 costs $0.0479 per minute. `BP/run_output.txt`. The dossier author's independent model gives the same numbers, `D20/recompute.txt`.
- **Verified. The STT price is a discount.** Deepgram's page shows Nova-3 streaming as "Current price $0.0048/min" and "Regular price $0.0077/min". `BS/deepgram_pricing.html`, the Nova-3 tooltip. The end date of the discount is not on the page. At the regular price the chained path costs $0.0263 per minute. The reviewer re-ran the `budget.py` cost functions with 0.0077: $0.02631.
- **The assumptions. Keep them with every number.** All are in `BP/budget.py`, dict `ASSUME`.

| Assumption | Value | Label |
|---|---|---|
| Conversation length | 5 minutes | assumption |
| Turns per minute | 4 exchanges. One exchange is one user turn and one agent turn | assumption |
| Talk ratio | User speaks 40% of wall-clock time, agent 40%, silence 20% | assumption |
| Speaking rate | 150 words per minute | assumption, not sourced |
| Tokens per turn | 19.5 text tokens each side: 15 words × 1.3 | 1.3 tokens per word verified, "one English word equals about 1.3 tokens", `BS/assemblyai_pricing.txt` line 793 |
| Audio per turn | 6 s user, 6 s agent | derived: 60 × 0.4 ÷ 4 |
| Characters per agent turn | 90: 15 words × 6 characters | 6 characters per word is an assumption |
| System prompt | 2,000 tokens, cached from turn 2 | size follows the primer, "This assumes a 2,000 token system prompt", line 257. Caching is an assumption |
| STT billing | Every streamed minute, including silence | inferred. Check a usage report after a test call |

- **Verified. The prices behind the S2S rows.** gpt-realtime-2.1 audio: $32.00 input, $0.40 cached, $64.00 output per 1M tokens. `BS/openai_pricing_md.html` line 288. "Audio tokens in user messages are 1 token per 100 ms of audio, while audio tokens in assistant messages are 1 token per 50ms". `BS/openai_voice_latency.md` line 219. "The entire conversation is sent to the model for each Response." Caching is "best-effort and not guaranteed". `BS/openai_realtime_costs.txt` lines 831 and 882. gpt-live-1: "Voice sessions cost $0.05 per minute, billed per second." `BS/openai_gpt_live_1.md` line 23.
- **Verified by arithmetic.** For gpt-realtime-2.1, output audio alone is 4 × 120 tokens × $64 ÷ 1M = $0.0307 per minute. That is 64% of the total.
- **Gap, not a fact. Gemini Live history billing.** The pricing row for Gemini 3.8 Live lists no cached rate. The docs read do not say whether earlier turns are billed again on each turn. If only new audio is billed, the cost is $0.0093 per minute. If the whole history is billed again each turn, it is $0.0492. That is a 5.3 times spread, and in the second case the cost per minute grows with length: $0.020 at 1 minute, $0.085 at 10 minutes and $0.121 at 15 minutes, `D20/recompute.txt`. Section 8, gap 3.
- **Inferred. Gemini's 25 tokens per second.** The Live row gives "$0.005/min" input and "$0.018/min" output. Both match 1,500 tokens per minute. The explicit "25 tokens per second" footnotes sit under the TTS models and Live Translate, not the Live row. `BS/gemini_pricing.md.txt` lines 271 to 272, 297 and 681. Section 7, conflict l.
- **Where it does not hold.** The assumptions move the cost more than the vendor choice. Section 5.3 changes one input at a time:
  - Talk ratio user 30% and agent 50% raises chained cost to $0.0280. User 50% and agent 30% lowers it to $0.0189. TTS is billed per character, so agent talk time drives it.
  - With no cache hits, gpt-realtime-2.1 costs $0.294 per minute, six times the cached figure.
  - If Gemini bills all streamed input audio, not only the user's 24 s per minute, mode A becomes $0.0120.
- **Verified. A unit trap.** The primer lists ElevenLabs Turbo at "$0.050" per minute. That is per minute of generated audio. At 150 words per minute and 6 characters per word, $0.05 per 1K characters is $0.045 per minute of speech. The prototype's $0.018 is per minute of conversation, where the agent speaks 40% of the time.
- **Verified. A second source disagrees.** The primer: "Costs range from $0.20 per minute or more if you are using a speech-to-speech API like the OpenAI Realtime API". Line 1059. No conditions. Section 7, conflict j.
- **Not included in any row.** Telephony, agent hosting, tool calls, retries, and input transcription on the S2S path.

### 4.8 Barge-in detection and end-of-turn detection are separate gates. A longer barge-in gate removes false barge-ins and delays every true one

- **Best evidence, verified.** LiveKit Agents 1.8.3 has a separate interruption gate: `min_duration` 0.5 s of speech, `min_words` 0, `false_interruption_timeout` 2.0 s, and the agent resumes after a false interruption. `LK/voice/turn.py` lines 187 to 197. The end-of-turn gate is `min_delay` and `max_delay`, lines 136 to 147.
- **Verified.** Pipecat 1.11.0 starts a user turn after `VAD_START_SECS = 0.2` of speech with confidence 0.7 and volume 0.6. `PC/audio/vad/vad_analyzer.py` lines 25 to 28. It can also require N words while the bot speaks: `min_words = self._min_words if self._bot_speaking else 1`. `PC/turns/user_start/min_words_user_turn_start_strategy.py` line 108.
- **Verified by run, synthetic.** Prototype A2: raising the minimum speech duration from 200 ms to 500 ms cut false barge-ins from 21.7% to 0.3% of agent turns. Every true barge-in then waits 500 ms before the agent stops. `RP/run_output_py39.txt`. The A2 table counts only the first trigger in each agent turn.
- **Verified.** LiveKit's "adaptive" interruption is an ML classifier on LiveKit's cloud gateway, with a 0.7 s remote timeout. `LK/inference/interruption.py` lines 51 to 57. It is "disabled by default in production mode" outside LiveKit Cloud. `LK/voice/agent_activity.py`. No accuracy numbers were found.
- **Inferred.** `min_words` needs STT words, so it adds STT delay on top of the gate. From the docstring "(STT only)" in `LK/voice/turn.py`. Not measured.

### 4.9 Echo cancellation is a precondition for barge-in, not a quality option

- **Best evidence, verified.** LiveKit 1.8.3 ignores interruptions for `aec_warmup_duration` after the agent starts speaking: `_DEFAULT_AEC_WARMUP_DURATION = 3.0`. `LK/voice/agent_session.py` line 117. It is `None` for outbound SIP calls, line 2105. The reason for the SIP case is not documented.
- **Verified by run, synthetic.** Prototype A3: without AEC, 2,972 of 3,000 agent turns interrupt themselves, 99.1%. With AEC on after a 3 s warm-up, 0. `RP/run_output_py39.txt`.
- **Verified.** The W3C draft: `echoCancellation: true` must "attempt to cancel at least as much as" `"remote-only"`, which covers `RTCPeerConnection` audio. `RS/w3c_mediacapture.txt` lines 1427 to 1461. It is an editor's draft. Which browsers ship the enum is not checked.
- **Inferred.** Agent audio played through a WebSocket and Web Audio, not an `RTCPeerConnection`, may not be cancelled. Check: play agent audio through Web Audio in Chrome and Safari and measure the echo left in the captured track.
- **Inferred.** On a phone call, the agent server has no echo canceller in the pipeline. The frameworks rely on the handset or the carrier. Basis: the LiveKit SIP branch above. Not checked.

### 4.10 After a barge-in, the model's context must be cut at the point the user stopped hearing. Only the component that owns the playout clock knows that point

- **Best evidence, verified.** OpenAI's `conversation.item.truncate`: "Truncating audio will delete the server-side text transcript to ensure there is not text in the context that hasn't been heard by the user." `RS/oai_rt_client_events.txt` lines 1409 to 1416. It takes `audio_end_ms`.
- **Verified. Transport decides who does it.** Over WebRTC and SIP, "The server will automatically truncate unplayed audio when there's a user interruption." Over WebSocket, the client stops playback and sends the truncate event. `RS/oai_rt_conversations.txt` lines 2088 to 2092.
- **Verified. Telephony gives you a playout signal.** Twilio returns a `mark` "When that media message's playback is complete". A `clear` message "empties all buffered audio". `RS/twilio_media_streams_ws.txt` lines 301 to 304 and 381 to 382. Telnyx has the same pair, `RS/telnyx_media_streaming.txt` lines 286 to 289.
- **Verified.** Pipecat writes only spoken text into the context. The TTS service sets `append_to_context = False` because "we do not want to add this text to the assistant context until it is spoken". `PC/services/tts_service.py` lines 1221 to 1225. Its Twilio serializer turns an interruption into `{"event": "clear"}`, `PC/serializers/twilio.py` lines 186 to 188.
- **Verified.** LiveKit sends `audio_end_ms=int(entry.out.playback_position * 1000)` to realtime models on interruption. `LK/voice/agent_activity.py` lines 4545 to 4551.
- **Verified by run, arithmetic on a made-up sentence.** Prototype part C: the user heard 6 of 18 words. If the server counts audio sent 1 s ahead, the context keeps 3 unheard words. If TTS streams three times faster than real time and all audio is sent, the context keeps all 12 unheard words. `RP/run_output_py39.txt`.
- **Narrowed, not settled.** The reference says truncate deletes "the server-side text transcript". The guide says it removes "the unplayed portion". The same guide, `RS/oai_rt_conversations.txt` line 2100, adds that truncate removes "the text transcript for the unplayed portion" and "doesn't provide a truncated transcript". Inferred reading: after a truncate, no text transcript of the heard part is kept. Section 7, conflict o.

### 4.11 Telephony adds narrowband audio and a carrier path with its own delay. The G.711 coder adds almost no delay, and the added milliseconds on a real call are not measured in any source

- **Best evidence, verified.** Twilio Media Streams deliver audio whose encoding "is always audio/x-mulaw" at a sample rate that "is always 8000". `RS/twilio_media_streams_ws.txt` lines 168 to 170. PCMU uses an 8,000 Hz clock, RFC 3551 Table 4, `RS/rfc3551.txt` line 1802. Its default packet is 20 ms, Table 1, line 646. At 8 kHz, nothing above 4 kHz survives. RFC 6716 Table 1.
- **Verified.** G.711 coder delay: mean one-way 0.375 ms. ITU-T G.114 (05/2003) Table I.1, `RS/itu_g114.txt` line 646. This is coder processing only.
- **Verified by arithmetic. Packetization adds more than the coder.** The sender must collect 20 ms of samples before it can send a 20 ms packet. So each direction adds at least 20 ms before transit. For WebRTC, the primer's "opus encoding 21" per direction covers this. For a phone leg, the carrier's packet time is not stated in any source.
- **Verified, 2003 planning values.** G.114 Table A.1 gives a mobile network, PLMS, 80 to 110 ms one-way, with an "objective" of 40 ms, `RS/itu_g114.txt` lines 423 to 425. A de-jitter buffer adds "one half of its peak delay to the mean network delay". Below 150 ms mouth to ear, most applications see "essentially transparent interactivity". `RS/itu_g114.txt` lines 311 to 323, 423 to 425 and 604 to 614. Whether VoLTE or 5G changes the PLMS figure is not checked.
- **Verified rule, inferred arithmetic. Jitter buffer.** G.114's example: a buffer for a 50 ms delay variation range adds 25 ms on average, line 614. By the same half-peak rule, the primer's 40 ms per direction matches a buffer with an 80 ms peak. A dynamic buffer also causes "transitional delay variations" when it resizes, lines 622 to 624. That adds to the p95, not the p50.
- **Verified.** The primer: "if your telephony provider adds a few hundred milliseconds, you're over budget". `BS/voiceai_primer.txt` line 158. No measurement is given.
- **Verified.** Twilio media runs over a secure WebSocket on TCP port 443. `RS/twilio_media_streams.txt` line 153. **Inferred:** TCP delivers in order, so one lost packet delays all audio behind it. RTP over UDP does not. Not measured.
- **Verified by run.** A 20 ms PCMU packet is 200 B on IP, 80 kbit/s. The same 20 ms as Twilio-style JSON is 305 B, 122 kbit/s before WebSocket, TLS and TCP headers. `RP/run_output_py39.txt` B2.
- **Verified. Narrowband cost to STT is poorly measured.** A June 2026 Hindi-only preprint says the simulated 3G narrowband condition stays close to 16 kHz accuracy, and GSM "consistently degrades performance". `RS/arxiv_2606.09335.txt` lines 67 and 109. The numbers are only in a figure. The Apple 2019 preprint shows 13.1% against 23.81% WER, but on different test sets. Treat the penalty for current English models as unmeasured.
- **Verified. Other telephony facts, from the realtime report, anchors not all re-grepped.** Telnyx bidirectional streams support PCMU, PCMA, G722, OPUS, AMR-WB and L16. LiveKit SIP supports PCMU, PCMA and G.722. AMR-WB "isn't enabled by default", `RS/lk_codecs-negotiation.md` lines 84 to 100. OpenAI GPT-Live over SIP requires SRTP for call audio, `RS/oai_rt_sip.txt` line 669. GPT-Live accepts raw G.711 μ-law and A-law at 8 kHz "over WebSocket", line 703. The first draft said "over SIP". That was wrong. DTMF over SIP reaches the app as `transport.dtmf.received` sideband events, line 696. RFC 4733 carries DTMF as named events. Twilio sends DTMF inbound only, `RS/twilio_media_streams.txt` line 137. The reviewer re-grepped these anchors on 2026-09-25.

### 4.12 A full-duplex model moves turn-taking and truncation into the vendor. The app loses those knobs

- **Best evidence, verified.** OpenAI's GPT-Live migration guide: "GPT-Live decides when to speak; remove manual audio commits and voice-turn triggers." `RS/oai_live-migration.txt` line 698.
- **Verified, absence.** The word "truncat" appears 0 times on the three GPT-Live guide pages read: `RS/oai_live.txt`, `RS/oai_live-migration.txt`, `RS/oai_live-conversations.txt`. How an app cuts context or enforces its own barge-in policy is undocumented on those pages. The API reference for GPT-Live events was not read.
- **Verified. Idle time costs money.** Creating a WebRTC session "bills 15 seconds of voice duration while the session initializes", credited once it runs. "Closing saves $0.05 per minute of idle voice time". `BS/openai_realtime_costs.txt` lines 696 and 792.
- **Where it may still win.** GPT-Live-1 scores 97.3% on AA's Conversational Dynamics, the highest in the table in 4.6. It does so at 1.24 s TTFA.

---

## 5. Numbers, with their conditions

### 5.1 The budget, stage by stage

From `BP/run_output.txt`. "V" means verified in the named source. "A" means the budget researcher's assumption, because the source gives only a mean or median. All values in ms.

| Stage | Chained, default | Chained, tuned | S2S, gpt-realtime-2.1 Minimal |
|---|---|---|---|
| End-of-speech wait | 500 fixed. V OpenAI `server_vad` default and LiveKit's VAD-mode `min_delay`. LiveKit 1.8.3 out of the box uses its turn detector, 0.3 s `min_delay`, not this. In VAD mode the code implies about 550, section 7 conflict c. Preemptive generation, not modelled, 4.2 | p50 250, p95 300 A. V primer "~250ms" | 500 fixed. V OpenAI `server_vad` default |
| STT final after endpoint | p50 66 V AA Nova-3 mean, p95 150 A | 54 V AA Soniox v5, 120 A | none |
| LLM TTFT | 597 / 1,137 V primer, Gemini 2.5 Flash | 304 V AA gemini-2.5-flash-lite, 700 A | model TTFA 970 V AA, 1,450 A |
| Sentence aggregation | 20 V primer | 20 | none |
| TTS TTFA | 183 / 227 V Coval ElevenLabs Flash | 63 / 97 V Coval Inworld Flash | inside model TTFA |
| Network, both directions | 24 V primer, 60 A | 24 / 60 A | 24 / 60 A |
| Jitter buffer, both directions | 80 V primer, 120 A | 80 / 120 A | 80 / 120 A |
| Device audio and Opus | 99 fixed V primer | 99 | 99 |
| **Sum of stage p50** | 1,569 | 894 | 1,673 |
| **Sum of stage p95** | 2,313 | 1,516 | 2,229 |
| **Monte Carlo p50 / p95** | 1,586 / 2,129 | 915 / 1,313 | 1,678 / 2,161 |
| **Turns over 1,000 ms** | 100% | 31.6% | 100% |
| **Cut first** | LLM, 1,045 p95 if removed | LLM, 614 | S2S model, 1,403 |
| **False cutoffs at this endpoint** | not modelled | not modelled. eot-bench gives 35.2% for SmartTurn v3.2 at 300 ms | not modelled |

Second S2S case, if AA's 0.97 s already includes 500 ms of server VAD: model part 470 ms, p50 1,179 ms, p95 1,659 ms, 86.5% over one second. Whether this case is true is gap 1.

What a sub-second p50 needs, from the tuned column: endpointing near 250 ms, a non-reasoning LLM near 300 ms TTFT, TTS near 60 ms, and user, agent and models in one region. At 1,000 ms p50, the fixed stages and the tuned LLM and TTS leave 410 ms for endpointing and STT. `D20/recompute.txt`.

### 5.2 Stage numbers from independent sources

| Stage | Number | Conditions | Label |
|---|---|---|---|
| STT time to final after a forced endpoint | Deepgram Flux 0.021 s, Soniox v5 0.054 s, Deepgram Nova-3 0.066 s, Cartesia Ink-2 external endpoints 0.067 s, ElevenLabs Scribe v2 0.141 s, AssemblyAI U3.5 Pro Min Latency 0.191 s, Gemini 3.5 Transcribe Live 0.395 s, Cartesia Ink-2 semantic endpoints 0.431 s, OpenAI GPT Realtime Whisper 0.688 s, GPT Live Transcribe 0.812 s, Google Chirp 3 1.276 s | AA streaming benchmark. Audio sent in real time in 20 ms chunks. SileroVAD finds the end, then AA forces an endpoint. Network included. Means, not percentiles. Region not stated. `BS/aa_stt_streaming_extracted.tsv`, `BS/aa_methodology_speech_to_text.txt` lines 139 to 160 | verified |
| TTS TTFA | 8 rows in 4.4 | Coval, `us-east-1`, rolling 7 days | verified |
| LLM TTFT, primer | GPT-4.1 536 / 1,771, Gemini 2.5 Flash 597 / 1,137, Claude 4.5 Haiku 637 / 1,615, GPT-5.1 739 / 1,492, Nemotron 3 Ultra self-hosted 541 / 712, median / P95 ms | No region, prompt size or sample count | verified quote, conditions not checked |
| LLM TTFT, AA | gemini-2.5-flash-lite 0.304 s, Gemini 2.5 Flash 0.464 s, Claude 4.5 Haiku 0.632 s, gpt-5.4-mini non-reasoning 0.774 s, gpt-4.1-mini 0.842 s, GPT-4.1 1.055 s | Median over 72 hours, `us-central1-a`, about 10,000 input tokens. No p95 | verified |
| End-of-turn delay at 5% false cutoffs | 543 ms to 1,600 ms | eot-bench, English, vendor data | verified, vendor |
| Smart Turn v3 inference | 12.6 ms on AWS c7a.2xlarge, 59.8 ms on c8g.medium, 94.8 ms on t3.medium, 3.3 ms on an L40S, including about 3 ms preprocessing | Daily blog dated Sep 11, 2025, v3 not v3.2. Vendor run. Sample count not stated | verified, **vendor claim**. Re-grepped by the reviewer, `RS/daily_smartturn_v3.txt` lines 116 to 148 |
| Silero v5 ONNX speed | 189 μs per 31.25 ms chunk, 165 times real time | 1 thread, AMD Threadripper 3960X, 16 kHz. No v6 row. No Apple row | verified, vendor. Not re-grepped |
| Human turn gap | "A response time of 500ms is typical" | The primer only. Stivers et al. not read | not checked against the paper |

### 5.3 Cost per minute, same assumptions for every path

Prices fetched 2026-09-25. Assumptions in 4.7. Telephony, hosting, tools and retries excluded. The first block is **verified by run** in `BP/run_output.txt` and matched by `D20/recompute.txt`.

| Path | $ per 5-minute conversation | $ per minute |
|---|---:|---:|
| Chained: Deepgram Nova-3 + Gemini 2.5 Flash + ElevenLabs Flash | 0.1171 | 0.0234 |
| of which STT, billed on all streamed minutes | 0.0240 | 0.0048 |
| of which LLM | 0.0031 | 0.0006 |
| of which TTS | 0.0900 | 0.0180 |
| Chained, same, at Deepgram's regular $0.0077 per minute. Reviewer run of the `budget.py` cost functions | 0.1316 | 0.0263 |
| S2S: OpenAI gpt-realtime-2.1 | 0.2397 | 0.0479 |
| S2S: OpenAI gpt-realtime-2.1-mini | 0.0749 | 0.0150 |
| S2S: Gemini 3.8 Live, only new audio billed, mode A | 0.0465 | 0.0093 |
| S2S: Gemini 3.8 Live, history billed again every turn, mode B | 0.2460 | 0.0492 |
| S2S: OpenAI gpt-live-1, voice only | 0.2500 | 0.0500 |
| S2S: gpt-live-1 plus a backend LLM call every turn | 0.2531 | 0.0506 |

Managed agent platforms bundle STT, LLM and TTS and sell per minute. Their **verified** prices, per minute:

- xAI Grok Voice agent $0.08. ElevenLabs Agents $0.08.
- Deepgram Voice Agent API $0.075, or $0.065 with your own TTS.
- AssemblyAI Voice Agent API $0.075. Cartesia Managed Agents $0.06.
- Amazon Nova Sonic was not extracted.

Sensitivities. **Dossier author arithmetic** in `D20/recompute.txt`. One input changes, all others stay at the 4.7 values. Not a measurement.

| Change | Chained $/min | gpt-realtime-2.1 $/min | Gemini mode B $/min |
|---|---:|---:|---:|
| Baseline, 5 minutes | 0.0234 | 0.0479 | 0.0492 |
| 1-minute conversation | 0.0238 | 0.0512 | 0.0204 |
| 10-minute conversation | 0.0234 | 0.0504 | 0.0852 |
| 15-minute conversation | 0.0234 | 0.0534 | 0.1212 |
| 2 exchanges per minute | 0.0233 | 0.0447 | not run |
| 6 exchanges per minute | 0.0236 | 0.0511 | not run |
| Talk user 30%, agent 50% | 0.0280 | 0.0545 | not run |
| Talk user 50%, agent 30% | 0.0189 | 0.0414 | not run |
| No cache hits on gpt-realtime-2.1 | not applicable | 0.2941 | not applicable |
| Gemini mode A, all streamed input billed | not applicable | not applicable | mode A becomes 0.0120 |

Reading the table:
- The chained cost barely moves with length, because only the small LLM line grows.
- gpt-realtime-2.1 is not monotonic in length. At 1 minute the uncached 2,000-token system prompt is a larger share. Under the caching assumption, it grows 11% from 5 to 15 minutes.
- Caching is the largest single lever for gpt-realtime-2.1. It is best-effort.

Per-minute unit conversions, verified by arithmetic: AssemblyAI Universal-Streaming $0.15 per hour is $0.0025 per minute. Universal-3.5 Pro Realtime $0.45 per hour is $0.0075. ElevenLabs Scribe v2 Realtime $0.39 per hour is $0.0065. Cartesia's Scale plan, $299 for about 10,667 minutes, is about $0.028 per minute of generated audio. That last figure is inferred from plan credits.

AA's cost column is a different unit. GPT-Realtime-2.1 Minimal costs $11.31 per hour of input audio on a 40-question Big Bench Audio subset. It "does not include cached-token discounts or tool-call costs". `BS/aa_s2s.txt` line 158. It is not a cost per conversation minute.

### 5.4 Audio and telephony numbers

| Number | Conditions | Source and label |
|---|---|---|
| PCMU 64 kbit/s payload, 80 kbit/s on IP at 20 ms packets | 160 B + RTP 12 + UDP 8 + IPv4 20 | `RP/run_output_py39.txt` B2, verified by run |
| Twilio JSON media, 122 kbit/s | 305 B per 20 ms, before WebSocket, TLS and TCP | same |
| μ-law SNR 35 to 38 dB from −3 to −40 dBFS. 8-bit linear falls from 46.7 to 11.1 dB | 1,013 Hz tone, 8 kHz, 1 s | B3, verified by run |
| 5 kHz tone removed. Without a low-pass filter it aliases to 3 kHz at 0 dB | 8 kHz resampling | B4, verified by run |
| In-band DTMF survives μ-law, 12 of 12 digits | Goertzel detector, 80 ms per digit | B5, verified by run |
| μ-law encoders disagree on 381 of 65,536 inputs, 0.58%, all negative, one code step | This prototype against CPython `audioop` on 3.9.6 | B6, verified by run. Which one matches G.711 exactly is not checked |
| Silero window 32 ms: 512 samples at 16 kHz, 256 at 8 kHz | Silero VAD supports only 8 and 16 kHz | Realtime report 2.1, verified |
| Smart Turn v3.2 CPU ONNX, 8,679,182 bytes | Bundled in the Pipecat 1.11.0 sdist | Realtime report 2.2, measured by the researcher |
| G.114: under 150 ms one-way is transparent, over 400 ms is unacceptable for planning | 2003 planning values | verified |

### 5.5 Arithmetic recomputed

`D20/recompute.py` compared 52 claimed values with an independent computation. 0 mismatches. It also printed the ratios and sensitivities used above. It covers:

- The primer's table sum and every prototype stage sum.
- Every cost row, and the hand-worked gpt-realtime-2.1 single turn of $0.018068.
- The Gemini per-minute rates and every vendor-to-Coval ratio.
- The telephony packet sizes and the Silero window arithmetic.

Two corrections come from the recompute, not from mismatches. Both are in section 7, conflict k.

---

## 6. Lab designs

The learner has an Apple Silicon Mac, 14 cores, 26 GB RAM, no Docker, no GPU except MPS, and no API keys by default.

### 6.1 Built and run

| Lab | Script | Where it runs | Cost | Run time | Self-test | Proves |
|---|---|---|---|---|---|---|
| Budget calculator: four latency scenarios, Monte Carlo, cut-first ranking, cost per minute for ten paths | `BP/budget.py` | Mac, offline, standard library, Python 3.9 or later | $0 | 6.4 s full run. 0.13 s for `--test`, re-run 2026-09-25 | 8 hand-worked checks, passing | 4.1, 4.5, 4.6, 4.7 |
| Audio lab: endpointing timeout, turn-model policy, barge-in gate, AEC, μ-law size and quality, band limit, DTMF, truncation error | `RP/voice_audio_lab.py` | Mac, offline, standard library | $0 | 2.02 s on Python 3.9.6 | Hand-worked μ-law cases, round trips, Goertzel, DTMF "5", a 700 ms pause clipped at 500 ms and not at 800 ms. Passing, re-run 2026-09-25 | 4.2, 4.3, 4.8, 4.9, 4.10, 4.11 |

Known noise in `budget.py`: the "tail flattened" column shows −7 ms to +10 ms for stages with small tails. Removing a stage shifts the random stream. Part A of the audio lab uses a synthetic scenario. It shows the mechanism, not real rates.

Break-its already in the reports:
- `budget.py`: set the end-of-speech wait to 800 ms, Gemini's default. Or swap ElevenLabs Flash for `gpt-4o-mini-tts`, 558 / 4,165 ms. The p95 moves by more than one second.
- `voice_audio_lab.py`: set `vad_echo_aec` to (0.45, 0.2) for a poor canceller. Remove the low-pass filter in B4. Set `p_long_pause` to 0.6 for a caller who pauses to think.

### 6.2 Designed, not built

| Lab | Where it runs | Cost | What it prints | Proves |
|---|---|---|---|---|
| A. Add the false-cutoff rate to `budget.py`. Take each endpoint setting's cutoff rate from eot-bench or from lab C | Mac, offline | $0 | p50, p95 and false cutoffs side by side per scenario | 4.3. Makes "what you give up" one table |
| B. Correlated tails. One shared congestion factor per turn multiplies every network-dependent stage | Mac, offline, seconds | $0 | p95 of the total moving from 2,129 toward 2,313 ms as correlation rises | 4.5 |
| C. Endpointing on the learner's own speech. Record a WAV with pauses. Sweep Silero `min_silence_duration` from 100 to 800 ms. Use the bare ONNX file with onnxruntime to avoid torch | Mac CPU | $0. Silero ONNX 2.3 MB. onnxruntime wheel size not measured | Utterances split mid-sentence and added delay per turn, per setting | 4.2, 4.3 on real speech |
| D. Smart Turn v3.2 timing on the Mac. `smart-turn-v3.2-cpu.onnx`, 8.68 MB, 100 inferences on 8 s windows | Mac CPU | $0 | ms per inference, compared with Daily's 12.6 ms on c7a.2xlarge | 4.3, the compute share of a turn decision |
| E. Cost sensitivity. Change talk ratio, turns per minute, length and cache hit rate in `budget.py` | Mac, offline | $0 | The section 5.3 table, for the learner's own traffic | 4.7 |
| F. Narrowband WER. About 100 LibriSpeech test-clean utterances, through the lab's 8 kHz μ-law codec, transcribed with a small local Whisper build. Paired test from the retrieval harness | Mac CPU or MPS | $0. Model download size not measured | Paired WER at 16 kHz against 8 kHz μ-law | 4.11, gap 10 |
| G. Optional, UNVERIFIED, hosted. Time one gpt-realtime-2.1 turn with `turn_detection: null` and a manual commit, from commit to first audio delta. Then repeat with `server_vad` | Mac plus OpenAI API key | About $0.05 per 1-minute session on the 4.7 assumptions. 10 sessions about $0.51 | Model TTFA without VAD, and the VAD share | Closes gap 1 |
| H. Optional, UNVERIFIED, hosted. A 10-turn Gemini 3.8 Live session. Log `usageMetadata.promptTokenCount` per turn | Mac plus Google API key | Under $0.25, the mode B cost of a 5-minute conversation | Whether prompt tokens grow with each turn | Closes gap 3 |
| I. Optional, UNVERIFIED, account needed. A Twilio or Telnyx number to a local WebSocket through a tunnel. Time `clear` to silence and `mark` spacing. Record a call and measure voice-to-voice on the waveform | Mac plus a telephony account and number | Not fetched. Not checked | Added ms on a real phone path | Closes gap 2 |

### 6.3 The module lab, proposed

"Spend one second." One script answers both halves of the module question on the learner's machine. Proposal, not built:

1. Start from `budget.py`. Add lab A, so every scenario prints p50, p95 and false cutoffs together.
2. Replace the endpoint assumption with lab C's measured split rate on the learner's own recording.
3. Replace the turn-model compute assumption with lab D's measured inference time on the Mac.
4. Add lab B's correlation knob.
5. Print the cost per minute for each scenario with the 4.7 assumptions shown next to it.
6. Break-its: an 800 ms VAD, a reasoning LLM, a cross-region round trip of 350 ms, TTS with a 4 s tail, cache hit rate 0.
7. Self-test: the 8 existing checks plus one hand-worked row that adds cutoffs.

Inferred: offline, no key, under one minute of run time after the ONNX downloads. Not measured. Labs G, H and I stay optional.

---

## 7. Conflicts resolved

| Conflict | Reports | Evidence used | Resolution |
|---|---|---|---|
| a. Is OpenAI's 500 ms `silence_duration_ms` the default or an example? | Budget report: example only, listed as not verified. Realtime report: default | `RS/oai_rt_client_events.txt` lines 546 to 548: "Defaults to 500ms." The VAD guide, `BS/openai_realtime_vad.md` line 52, shows it inside an example | The API reference settles it. 500 ms is the default. Budget report item 9.2 is closed |
| b. LiveKit endpointing: 0.5 s, or 0.3 s | Budget: 0.5 s, "0.3 s for streaming STT endpointing". Realtime: 0.3 s and 2.5 s "with a turn detector" | `LK/voice/turn.py` lines 136 to 147 and 307 to 311: the 0.3 and 2.5 defaults apply when `turn_detection` is a `_StreamingTurnDetector`. `LK/inference/eot/detector.py` line 34: `class TurnDetector(_BaseStreamingTurnDetector)` | Both numbers are defaults. 0.5 and 3.0 without a turn detector. 0.3 and 2.5 with LiveKit's audio turn detector. The budget report's "streaming STT" wording is wrong. It is a streaming turn detector. Reviewer: the docs state the same pair, "0.3 seconds" and "2.5 seconds" with the audio turn detector, `RS/lk_turn_detector.txt` lines 205 to 213. So this is verified, not only inferred. The reviewer also found that the audio turn detector is the default when the app passes no `turn_detection`, `LK/voice/agent_session.py` lines 562 to 566. So 0.3 and 2.5 are the out-of-box values. 0.5 and 3.0 apply only in VAD or STT mode |
| c. LiveKit's default wait in VAD mode: 500 ms | Budget report and prototype: 500 ms fixed | `LKS/vad.py` line 64: `min_silence_duration` 0.55. `LK/voice/audio_recognition.py` line 1437 back-dates the speech end by the silence already seen. Lines 1716 to 1718 subtract it from `endpointing_delay` | The end-of-speech event fires after 0.55 s of silence. The 0.5 s delay is then already spent. The wait is about 0.55 s plus VAD inference, not 0.5 s and not 1.05 s. Inferred from the code, not run. The prototype understates this stage by about 50 ms |
| d. Pipecat's end-of-speech default: 0.2 s | Budget report lists `VAD_STOP_SECS = 0.2` as the default wait. Realtime report: the default stop strategy is Smart Turn | `PC/turns/user_turn_strategies.py` line 53. `PC/audio/turn/smart_turn/base_smart_turn.py` line 27, `STOP_SECS = 3` | 0.2 s is the VAD gate that starts a Smart Turn check. The turn ends at 0.2 s plus inference only when the model says complete. Otherwise the fallback is 3 s. Teach it as a two-stage policy |
| e. Smart Turn latency: ~250 ms or ~1,050 ms | Primer line 582: "~250ms". eot-bench: SmartTurn v3.2 1,051 ms at 5% false cutoffs, 35.2% cutoffs at 300 ms | Both saved sources | Different measures. 250 ms is time to a decision. eot-bench gives the dead air needed for a cutoff rate. The tuned budget buys its 250 ms with a high cutoff rate on vendor data. Teach both, and add lab 6.2 A |
| f. Vendor against independent TTS: "2 to 4 times" | Budget report C3 | Coval rows and vendor claims, 4.4. Ratios in `D20/recompute.txt` | Holds for ElevenLabs Flash, 2.4 to 3.0 times, and Cartesia Sonic, 3.2 to 4.3 times. Does not hold for ElevenLabs v3 Conversational, 1.1 to 1.4 times. Keep the range with its scope |
| g. Primer round trip: 1,200 or 1,293 ms | Primer text against its table | `BS/voiceai_primer.txt` line 158 says "about 1,200 ms". The 16 rows sum to 1,293 | A source rounding. Use 1,293 |
| h. GPT-4.1 TTFT: 536 ms or 1.06 s | Primer against AA | Primer gives no conditions. AA: `us-central1-a`, about 10,000 input tokens, median over 72 hours | Not settled. Likely causes are region and prompt length. Inferred. Teach both with conditions |
| i. STT stage: 300 ms or 21 to 66 ms | Primer "transcription and endpointing 300" against AA time to final | AA starts its timer after a forced endpoint, `BS/aa_methodology_speech_to_text.txt` lines 139 to 160 | Different measures. The primer's 300 includes the endpointing wait. AA's excludes it, except for models with built-in semantic endpointing: Cartesia Ink-2 0.067 s external against 0.431 s semantic |
| j. S2S cost: $0.20 per minute or $0.048 | Primer line 1059 against the prototype | Recompute with no cache hits: $0.294 per minute | The primer's range matches a run where caching fails or sessions are long. The prototype assumes almost every input token after turn 1 is cached. Inferred. The primer states no conditions. Teach $0.048 as the cached lower bound and $0.294 as the uncached upper bound, on the same assumptions |
| k. Two claims in the budget report's labs | Budget report lab 4: gpt-realtime-2.1 cost "grows with conversation length". Optional lab: 10 one-minute calls "about $0.48" | `D20/recompute.txt`: $0.0512 at 1 minute, $0.0479 at 5, $0.0504 at 10, $0.0534 at 15. 10 one-minute sessions: $0.51 | Under the caching assumption, growth is small and not monotonic. The 1-minute cost is higher because the first turn is uncached. The $0.48 used the 5-minute rate. The 1-minute rate gives $0.51 |
| l. Gemini Live's 25 tokens per second: verified or inferred | Budget report cites lines 297 and 681 as verified | Line 297 is under Gemini 3.5 Live Translate. Line 681 is under Gemini 3.8 Flash TTS. The Live row, lines 271 to 272, gives per-minute prices only | Inferred for Gemini 3.8 Live. The per-minute prices match 25 tokens per second exactly for output and to rounding for input |
| m. Gemini mode A input basis | Not raised by either report | `BP/budget.py` `cost_gemini_live` bills only the user's 6 s per turn. `cost_chained` bills STT on all streamed minutes | The two paths use different billing bases for input audio. If Gemini bills all streamed input, mode A is $0.0120, not $0.0093. Not checked. Added to gap 7 |
| n. "Full Duplex Bench 72% to 97%" | Budget report section 4 | `BS/aa_s2s.txt` header: the column is "Conversational Dynamics". `BS/aa_methodology_s2s.txt` line 51: built on a subset of Full Duplex Bench v1 and v1.5 | Both are right. Use the column name and say what it is built on |
| o. What `truncate` removes | Realtime report 8.2 | Reference: "delete the server-side text transcript". Guide: "remove the unplayed portion". Reviewer: guide line 2100, "doesn't provide a truncated transcript" | Narrowed by the reviewer. The audio is cut at `audio_end_ms`. Inferred from line 2100: no text transcript of the heard part is kept. Still not tested. Teach that the context must be cut at the playout clock. Say that OpenAI's two pages differ on how much text goes |
| p. Pipecat 1.11.0 date: 2026-09-17 or 2026-09-18 | Realtime report 2.9 against its own section 7 | CHANGELOG date against PyPI upload `2026-09-18T04:11:07` UTC | Both are true. Cite the PyPI upload with UTC |
| q. Target: 800, 1,000 or 1,500 ms | Budget report 8.5 | Daily 2024 "800ms median". Primer 2026 "1,500 ms", with no data. README module question: one second | Not a factual conflict. Keep one second as the module's question. Teach the primer's 1,500 ms as a practitioner claim without data |

---

## 8. Gap list, ranked by what the module question needs

| Rank | Gap | Why the module question needs it | What was done, and the check |
|---|---|---|---|
| 1 | **Whether Artificial Analysis's S2S TTFA timer includes the VAD wait** | It decides whether S2S costs about 1.2 s or about 1.7 s at p50 in the budget | Not settled. The methodology says only "Average number of seconds required to generate the first token of audio output". Check: lab 6.2 G, or ask AA. A second source exists: Coval lists a speech-to-speech "Voice-to-voice latency" benchmark, `BS/coval_benchmarks_README.md` line 30. The saved `BS/openbench_coval_s2s.html` is a 404 page. Fetch Coval's S2S results and read its timer definition |
| 2 | What telephony adds in milliseconds on a real call today | "What telephony adds" has only 2003 planning values and the primer's "a few hundred milliseconds" | Not measured. Check: lab 6.2 I, with a waveform measurement |
| 3 | **Whether Gemini Live bills earlier turns again on each turn** | A 5.3 times spread in cost per minute, growing with length | Not settled. The Live row lists no cached rate, and the docs read do not say. Check: lab 6.2 H |
| 4 | False-cutoff rate at a sub-300 ms endpoint on independent data | It is the price of the tuned budget. The only number is vendor-run | Not found. eot-bench is LiveKit's data. Check: lab 6.2 C on the learner's speech, and an independent benchmark if one appears |
| 5 | p95 for STT final, network and jitter buffer | The prototype assumes them. They set part of the p95 | Not checked. AA reports means. Check: `chrome://webrtc-internals` jitter buffer delay, or a benchmark that reports STT p95 |
| 6 | Correlation between stage tails | Decides where the p95 sits between 2,129 and 2,313 ms | Not modelled. Check: lab 6.2 B, then real traces |
| 7 | Whether streaming STT and S2S APIs bill silence | Moves Gemini mode A from $0.0093 to $0.0120 and may change the STT line | Not checked. Check: usage reports after a test call per vendor |
| 8 | OpenAI realtime cache hit rate on real sessions | $0.048 against $0.294 per minute | Not checked. Check: `usage` cached token counts over a 5-minute session |
| 9 | LLM TTFT at a 2,000-token prompt in the learner's region | AA uses 10,000 tokens in `us-central1-a`. The primer gives no conditions | Not checked. Check: time it with the Module 1 section 1.6 meter |
| 10 | Narrowband WER penalty for current English STT | The size of the telephony quality cost | Not measured. Check: lab 6.2 F |
| 11 | Echo cancellation of Web Audio playback in browsers | A barge-in precondition for WebSocket clients | Not checked. Check: a browser echo test |
| 12 | How GPT-Live exposes truncation or playout position | Full duplex may remove the app's context control | Not checked. Check: the GPT-Live API reference events |
| 13 | Region of AA's STT and S2S tests | Every independent number may be one US region | Not stated on the pages read |
| 14 | Amazon Nova Sonic price and latency. Cartesia price per character | Two missing rows | Not extracted. The AWS page renders with JavaScript |
| 15 | Reviewer addition. How much preemptive generation saves, and what it costs | LiveKit 1.8.3 turns it on by default. It may overlap the LLM TTFT with the end-of-speech wait | Not measured. Check: an `AgentSession` run with it on and off, voice-to-voice on the waveform, and the count of discarded LLM calls |
| 16 | Reviewer addition. Tool-call latency inside a turn | The primer warns against letting latency "creep up above 1,500 ms as you add features like tool calling", `BS/voiceai_primer.txt` line 213. No source gives a number | Not checked. Check: time one tool round trip inside the lab 6.2 G session |
| 17 | Reviewer addition. When Deepgram's discount on Nova-3 streaming ends | $0.0048 against $0.0077 per minute | Not stated on the page. Check: re-fetch the pricing page before the lesson is written |
| 18 | Reviewer addition. Filler audio, such as a short "one moment" clip played while the LLM starts | A common way to hide TTFT | No saved source covers it. Not checked |

---

## 9. Things not verified

Each item names the check that would settle it. Items that the text depends on are also stated where they are used.

1. **Where AA starts the S2S TTFA timer, whether server VAD is on, and the test region.** Check: lab 6.2 G, or ask AA.
2. **Whether Gemini Live bills earlier turns again.** Check: lab 6.2 H.
3. **LiveKit's VAD-mode wait of about 0.55 s.** Inferred from `LK/voice/audio_recognition.py`, not run. Check: run an `AgentSession` with Silero VAD and read the `end_of_turn_delay` metric.
4. **LiveKit's 0.3 s and 2.5 s defaults apply to its audio turn detector.** Now verified in code and docs by the reviewer, section 7 conflict b. Still not run. The resulting wait in ms is not checked. Check: log the resolved `EndpointingOptions` and the `end_of_turn_delay` metric in a session with default settings.
5. **The primer's conditions**: region, prompt size and sample count for its TTFT table, and how it measured "~250 ms" turn decisions and the 250 ms and 350 ms round trips.
6. **p95 values for STT final, network and jitter buffer** in the prototype. All assumed.
7. **Stage independence** in the Monte Carlo. Assumed.
8. **STT billed on all streamed minutes, including silence.** Inferred. Check: a Deepgram usage report.
9. **Gemini 3.8 Live's audio token rate.** Inferred from per-minute prices. Check: `usageMetadata` token counts for 60 s of audio.
10. **Speaking rate of 150 words per minute and 6 characters per word.** Assumptions, not sourced.
11. **Cartesia cost per character.** $0.028 per minute is inferred from plan credits.
12. **Amazon Nova Sonic price and latency.** Not extracted.
13. **Release dates of gpt-live-1, gpt-realtime-2.1, Gemini 3.8 Live, and LiveKit's audio turn detector and adaptive interruption.** No dates on the pages read. Check: changelogs and release tags. Smart Turn v3 and v3.2 dates were on the saved pages. The reviewer added them to 3.4.
14. **Accuracy of LiveKit's adaptive interruption model.** No numbers found.
15. **Why LiveKit sets `aec_warmup_duration` to `None` for outbound SIP.** The code does it, the reason is not documented.
16. **Browser echo cancellation of Web Audio playback.** Check: a browser test.
17. **What `truncate` removes: the whole transcript or the unplayed part.** Check: send a truncate in a test session and read the item back.
18. **The GPT-Live API reference for truncation or playout events.** Not read.
19. **Real PSTN and mobile one-way delays today.** G.114's 80 to 110 ms is a 2003 planning value.
20. **TCP head-of-line delay on Twilio and Telnyx media WebSockets under loss.** Inferred, not measured.
21. **Numeric WER values in arXiv 2606.09335 Figure 2(b).** Image only. Venue of arXiv 1909.02667 not checked.
22. **Which μ-law encoder matches G.711 exactly** for the 381 disputed inputs. The G.711 PDF was not fetched.
23. **Coval runner and methodology at a fixed tag.** Read at `main`. The numbers are a rolling window and will change.
24. **eot-bench commit.** Not recorded. The table can change.
25. **The language mix of the FastTurn subset.**
26. **Which Silero version Pipecat bundles.** Same size as silero-vad 6.2.3's ONNX, different SHA-1.
27. **The prototype on Python 3.13 or later.** Not run. The `audioop` comparison is skipped there by design.
28. **Download sizes of onnxruntime and the Whisper models for labs C, D and F.** Not measured.
29. **Telephony per-minute prices.** Not fetched. Every cost row excludes telephony. Cartesia lists $0.014 per minute for calls on a Cartesia phone number.
30. **The Stivers et al. PNAS paper on human turn gaps.** HTTP 403. Not read. "500ms is typical" is the primer's statement only.
31. **Anchors in 5.2's Silero row** were verified by the realtime report, not re-grepped. The reviewer re-grepped 4.11's last bullet and the Smart Turn row.

---

## 10. Review log

Reviewer: independent reviewer, not the dossier author. Date: 2026-09-25. Scope: read-only checks of the saved sources, four fresh fetches, the two prototype self-tests, and the cost functions re-run with one changed price. No lab ran. No keyed API call. Scratch notes and fetched pages: `/private/tmp/claude-502/-Users-raghvendra-dhakar-Desktop-project-code/dabd56e3-78f3-4dbc-bddb-3316bb9bedda/scratchpad/m20review/`.

### 10.1 What was checked

| Check | Method | Result |
|---|---|---|
| Anchors | About 90 anchors re-read with `grep` and `sed -n` in their saved files, not with `D20/anchor_check.py`. Primer lines 151 to 312, 582 and 1059. G.114 lines 311 to 323, 423, 604 to 614 and 646. eot-bench table. Smart Turn v3 timing table. LiveKit `turn.py`, `vad.py`, `audio_recognition.py`, `agent_session.py`, `interruption.py`, `agent_activity.py`. OpenAI client events, conversations, SIP, pricing and costs pages. Pipecat 1.11.0 VAD, turn strategies, Smart Turn, TTS service, Twilio serializer, CHANGELOG. Twilio, Telnyx, LiveKit SIP pages. RFC 3551. Coval, AA S2S, AA STT and AA LLM rows | Every quoted number matches its file. Problems were a wrong default, a missing discount, a wrong transport, a wrong input source and stale overlap. Items R1 to R10 below |
| Fresh fetches, 2026-09-25 about 00:00 UTC | `curl -sL --max-time 60` of OpenAI `pricing.md`, OpenAI `realtime-vad.md`, the LiveKit turn-detector page and the eot-bench README | All HTTP 200. Realtime and GPT-Live price rows identical to the saved copy. eot-bench README byte-identical. LiveKit 0.25 s rule unchanged. VAD guide still shows 500 ms in an example. Listed in 3.2 |
| Self-tests | `BP/budget.py --test` and `RP/voice_audio_lab.py --selftest`, Python 3.9.6 | "self-test: 8 checks passed" in 0.13 s. "selftest: all hand-worked cases pass" in 0.03 s |
| Budget sums | By hand from `BP/run_output.txt` | Default 1,569 and 2,313. Tuned 894 and 1,516. S2S 1,673 and 2,229. Second S2S 1,173 and 1,729. 69.9% share. 410 ms left for endpointing and STT. Primer table 1,293. All match |
| Codec and bitrate | By hand | 160 + 12 + 8 + 20 = 200 B per 20 ms, 80 kbit/s. 305 B per 20 ms, 122 kbit/s. Match |
| Jitter buffer | G.114 half-peak rule against the primer | Primer 40 ms per direction is consistent with an 80 ms peak. Added to 4.11 as inferred arithmetic |
| Cost per minute | `budget.py` cost functions re-run, plus a hand model of Gemini mode B | $0.0234, $0.0479, $0.2941 uncached, $0.0492 mode B, $0.0120 mode A with all input billed, $0.018068 single turn, $0.0307 output audio. All match. Unit conversions for AssemblyAI, ElevenLabs Scribe and Cartesia match |
| Section 7 conflicts | Each resolution re-read against its evidence | a, c, d, e, f, g, i, j, k, l, m, n, p and q hold. b and o changed, R1 and R8 |
| Overlap | `grep '^## '` on `inference-internals`, `serving-cluster`, `observability-ops`, `agent-evals`, plus `ai-finops` and `security` | Module 1 owns TTFT and streaming. No module teaches voice. Section 2 was stale, R6 |

### 10.2 Corrections, by kind

| # | Kind | Where | What was wrong | Evidence | Fix in the text |
|---|---|---|---|---|---|
| R1 | Wrong default. Most serious | 4.2 table, 5.1 row 1, 3.5, 7 b, 9.4 | The dossier treated LiveKit's 0.5 s VAD-mode delay as the default. In 1.8.3, a session with no `turn_detection` builds the audio turn detector. So the out-of-box policy is 0.3 s and 2.5 s | `LK/voice/agent_session.py` lines 562 to 566, `turn_handling.get("turn_detection", inference.TurnDetector())`. Docs table, `RS/lk_turn_detector.txt` lines 205 to 213 | Rows relabelled. The 500 ms stage now rests on the OpenAI `server_vad` default. Conflict b upgraded from inferred to verified |
| R2 | Missing concept. Serious | 4.2, 3.5, 5.1, gap 15 | Preemptive generation is on by default in LiveKit 1.8.3. It can overlap the LLM TTFT with the end-of-speech wait. The serial budget does not show this, and discarded attempts cost tokens | `LK/voice/turn.py` lines 201 to 228 | New bullet. Effect labelled inferred. Check added |
| R3 | Missing price condition. Serious | 4.7, 5.3, section 1 table, gap 17 | Deepgram's $0.0048 is a "Current price". The "Regular price" is $0.0077 | `BS/deepgram_pricing.html`, Nova-3 tooltip | New bullet and row. Chained $0.0263 per minute at the regular price, recomputed |
| R4 | Wrong source for a model input | 4.3, prototype A1b | 0.993 and 0.870 were called the vendor's turn-model accuracy. They are LiveKit's English rates for its deprecated text detector | `RS/lk_turn_detector.txt` lines 440 to 481. `RP/voice_audio_lab.py` line 394 | Bullet rewritten and labelled as vendor claim |
| R5 | Wrong transport | 4.11 last bullet | "GPT-Live over SIP accepts raw G.711". The page says raw G.711 is supported "over WebSocket" | `RS/oai_rt_sip.txt` lines 669, 696 and 703 | Fixed. SRTP, DTMF sideband events and the LiveKit AMR-WB note added with lines |
| R6 | Stale overlap | Section 2 | Modules 13, 14 and 16 have built phases. Module 15 has four phase files. The dossier said dossiers only | `ls study-material/{serving-cluster,ai-finops,observability-ops,security}` and `grep '^## '` | Owner table and prose fixed. Links to Module 13 section 1.1 and Module 15 section 1.2 added |
| R7 | Missing labels | 4.1, 4.3, 5.2 | The primer's 1,500 ms, 500 ms self-hosted and "~250ms" turn decision are Daily's claims about its own products. Smart Turn timings are vendor runs. Full Duplex Bench venue unchecked | `BS/voiceai_primer.txt` lines 196, 212 and 582 | Each labelled **vendor claim** with its missing conditions. Full Duplex Bench labelled "not checked" |
| R8 | Conflict narrowed | 4.10, 7 o | The guide has a third sentence the dossier missed | `RS/oai_rt_conversations.txt` line 2100, "doesn't provide a truncated transcript" | Added. Reading labelled inferred. Test still needed |
| R9 | Missing condition | 4.11, section 1 table | "G.711 itself adds 0.375 ms" left out the 20 ms packet the sender must fill. PLMS "objective 40 ms" was missing. Dynamic jitter buffers were missing | RFC 3551 Table 1 line 646. G.114 lines 423 to 425, 614 and 622 to 624 | New bullets. Heading now says "the G.711 coder" |
| R10 | Wrong anchor or missing date | 4.11, 3.4, 4.4, 9.13 | RFC 3551 line 646 gives the clock as "var.". The 8,000 Hz clock is Table 4, line 1802. Smart Turn post dates were on the saved pages. The Coval mirror defines TTFA differently from the README | `RS/rfc3551.txt` line 1802. `RS/daily_smartturn_v3.txt` line 78, `RS/daily_smartturn_v32.txt` line 79. `BS/openbench_coval_tts.txt` line 279 | Anchor, dates and TTFA note added |

### 10.3 Concepts checked for the module question

- **Added with evidence.** Preemptive generation, R2. Packetization delay and the jitter-buffer rule, R9.
- **Listed as gaps, no evidence in the saved sources.** Tool-call latency inside a turn, gap 16. Filler audio to hide TTFT, gap 18. The end of Deepgram's discount, gap 17.
- **A missed independent source.** Coval runs a speech-to-speech voice-to-voice benchmark, README line 30. The saved page is a 404. It may close gap 1.

### 10.4 Left unchanged

- Conflict c holds for VAD mode. The reviewer read the same lines. It is still inferred, not run.
- The 500 ms end-of-speech stage in `BP/budget.py` is still a fair default, because OpenAI `server_vad` defaults to 500 ms. Its source string names LiveKit. A lab writer should change that string.
- The prototype's cost numbers are correct as arithmetic. Only the Deepgram input changed.

Summary: the arithmetic and the quoted numbers hold. The main fixes are LiveKit's real default, its default preemptive generation, and a discounted STT price.
