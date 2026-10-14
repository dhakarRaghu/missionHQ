"""Voice a whole narration's lines in one process, so the model loads once.

    .venv/bin/python kokoro_batch.py jobs.json

jobs.json: {"voice": "af_heart", "speed": 0.94, "lang": "en-us",
            "jobs": [{"text": "...", "out": "/abs/line.wav", "voice": null}]}

Every job writes its own 24 kHz mono WAV. KOKORO_THREADS caps onnxruntime's
threads (default 3), so a render running at the same time keeps its cores.
"""

import json
import os
import sys
from pathlib import Path

import soundfile as sf

MODELS = Path(__file__).parent / "models"

threads = os.environ.get("KOKORO_THREADS", "3").strip()
if threads.isdigit():
    os.environ.setdefault("OMP_NUM_THREADS", threads)
    os.environ.setdefault("ORT_NUM_THREADS", threads)

from kokoro_onnx import Kokoro  # noqa: E402  (after the thread env)


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text())
    voice = cfg.get("voice") or "af_heart"
    speed = float(cfg.get("speed") or 0.94)
    lang = cfg.get("lang") or "en-us"
    jobs = cfg["jobs"]

    kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    if threads.isdigit() and hasattr(kokoro, "sess"):
        kokoro.sess._sess_options.intra_op_num_threads = int(threads)

    for i, job in enumerate(jobs):
        out = Path(job["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        samples, rate = kokoro.create(job["text"], voice=job.get("voice") or voice,
                                      speed=speed, lang=lang)
        sf.write(str(out), samples, rate)
        print(f"[{i + 1}/{len(jobs)}] {out.name}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
