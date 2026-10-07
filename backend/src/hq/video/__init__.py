"""Narrated teaching videos, made from a finished lesson, with no approval step.

A written course phase or article starts its video by itself
(engine._start_lesson_video). Two tasks, both run by tutor as code, not as
an agent loop:

1. SCRIPT (`script.py`): gather the lesson and its study note, plan the
   video, write the narration one beat at a time, then two independent
   reviews by a model that did not write it: the teaching editor and the
   fact checker against the material. Findings send the named beats back,
   and code checks every line (`checks.py`). Then the scenes are written as
   data against `video/SPEC.md` and checked by `video/scripts/check-spec.mjs`.
   A clean script starts the build; one that still states a wrong fact stops
   with its reasons.
2. BUILD (`build.py`): the voice (Kokoro), stills of every scene step, a
   frame review of each still by the teacher model (with redraws), the
   render, and the video checks as code (`video/scripts/verify.mjs`: frames,
   audio sync, keyframes, loudness, black frames). A video that passes is
   registered in `learning/videos/index.json` and shown on the Courses page.

Why data and not code for the scenes: a model that writes React can break a
render or overflow a box. Templates are tested once, at every text limit, so
a spec that passes the checks draws correctly; the frame review then checks
what was drawn against what the voice says.
"""

from __future__ import annotations

SCRIPT_STAGE = "video_script"
BUILD_STAGE = "video_build"
STAGES = frozenset({SCRIPT_STAGE, BUILD_STAGE})
# Course phases and Learn articles. YouTube episodes are cut from these by
# hand, in a Claude session with the video-remotion skill, not here.
MODES = ("course", "article")
