"""Synthesize many lines with Kokoro in one process (the model loads once).

usage: .venv/bin/python kokoro_batch.py jobs.json
jobs.json: {"voice": "af_heart", "speed": 1.0, "lang": "en-us", "jobs": [{"text": "...", "out": "/abs/path.wav"}]}
A voice may be a blend such as "af_heart:60,af_bella:40". A job may carry its own "voice".
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import soundfile as sf
from kokoro_onnx import Kokoro

HERE = Path(__file__).resolve().parent


def load_voice(k: Kokoro, spec: str):
    if ":" not in spec:
        return spec
    parts = [p.split(":") for p in spec.split(",")]
    total = sum(float(w) for _, w in parts)
    return sum(k.get_voice_style(name) * (float(w) / total) for name, w in parts)


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text())
    # Several narrations may run at once (parallel episode builds). onnxruntime's default thread pool
    # takes every core and spin-waits, so five processes drove the load average past 200 and each
    # job slowed from minutes to hours. Cap the threads and turn spinning off. KOKORO_THREADS overrides.
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = int(os.environ.get("KOKORO_THREADS", "3"))
    opts.inter_op_num_threads = 1
    opts.add_session_config_entry("session.intra_op.allow_spinning", "0")
    session = ort.InferenceSession(str(HERE / "models/kokoro-v1.0.onnx"), sess_options=opts, providers=["CPUExecutionProvider"])
    k = Kokoro.from_session(session, str(HERE / "models/voices-v1.0.bin"))
    voices = {}  # a job may name its own voice (dialogue); styles are loaded once each
    for job in cfg["jobs"]:
        spec = job.get("voice") or cfg.get("voice", "af_heart")
        if spec not in voices:
            voices[spec] = load_voice(k, spec)
        samples, rate = k.create(job["text"], voice=voices[spec], speed=cfg.get("speed", 1.0), lang=cfg.get("lang", "en-us"))
        # trim leading and trailing near-silence so line timings are tight
        idx = np.where(np.abs(samples) > 0.01)[0]
        if len(idx):
            samples = samples[max(0, idx[0] - int(0.03 * rate)) : idx[-1] + int(0.12 * rate)]
        sf.write(job["out"], samples, rate)
        print(job["out"], flush=True)


if __name__ == "__main__":
    main()
