"""The shapes the model returns, and the job record kept on disk."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["course", "article"]


# --- the plan -----------------------------------------------------------------

class PlannedConcept(BaseModel):
    id: str = Field(description="c1, c2, ... in teaching order")
    heading: str = Field(description="the concept as the question it answers, max 60 characters")
    claim: str = Field(description="one sentence the viewer could be wrong about, with its reason")
    situation: str = Field(description="where the running case meets this concept, with its number")
    picture: str = Field(description="what the thing is, does and why it exists; the terms defined here")
    question: str = Field(description="the think-it-through question; ends with ?")
    first_thought: str = Field(description="a reasonable engineer's first answer")
    why_reasonable: str
    what_it_misses: str
    real_question: str
    steps: list[str] = Field(description="the mechanism, 2 to 6 steps, each with its reason")
    number: str = Field(description="the one number or failure, with its conditions")
    evidence_quote: str = Field(description="copied exactly from the material")
    trap: str
    try_this: str
    bridge: str = Field(description="what happens next in the running case, leading to the next question")
    new_here: str = Field(default="", description=(
        "what this concept teaches that no earlier concept in the plan did, in one"
        " sentence; if it is nothing new, merge it into the concept it repeats"))


class VideoPlan(BaseModel):
    title: str = Field(description="the video title, the problem in the viewer's words")
    question: str = Field(description="the cold open's one question; ends with ?")
    running_case: str = Field(description="the one situation the video follows, owned by the viewer")
    cold_open: list[str] = Field(description="the facts and numbers the cold open tells, in order")
    concepts: list[PlannedConcept]
    payoff: str = Field(description="how the question is answered with this video's numbers")
    left_out: list[str] = Field(default_factory=list,
                                description="taught in the lesson but not here, and where it lives")
    mismatches: list[str] = Field(default_factory=list,
                                  description="where the material contradicts its own numbers or sources")


# --- narration ------------------------------------------------------------------

class Line(BaseModel):
    key: str
    text: str
    say: str = ""


class BeatLines(BaseModel):
    lines: list[Line]


# --- reviews ----------------------------------------------------------------------

class EditorFinding(BaseModel):
    beat: str
    criterion: str
    quote: str = Field(description="the line, copied exactly")
    problem: str
    instruction: str


class BeatScore(BaseModel):
    beat: str
    answers_question: int = Field(ge=1, le=5)
    connected: int = Field(ge=1, le=5)
    thinks_aloud: int = Field(ge=1, le=5)
    defined: int = Field(ge=1, le=5)
    spoken: int = Field(ge=1, le=5)
    numbers: int = Field(ge=1, le=5)
    transfer: int = Field(ge=1, le=5)

    def low(self, bar: int) -> list[str]:
        return [c for c in ("answers_question", "connected", "thinks_aloud", "defined",
                            "spoken", "numbers", "transfer") if getattr(self, c) < bar]

    def mean(self) -> float:
        vals = [self.answers_question, self.connected, self.thinks_aloud, self.defined,
                self.spoken, self.numbers, self.transfer]
        return sum(vals) / len(vals)


class EditorVerdict(BaseModel):
    scores: list[BeatScore]
    findings: list[EditorFinding] = Field(default_factory=list)
    whole_video: list[str] = Field(default_factory=list,
                                   description="problems of the whole video, each with a quote")


class FactItem(BaseModel):
    key: str
    verdict: Literal["supported", "contradicted", "unsupported", "example"]
    material_quote: str = ""
    arithmetic: str = ""
    correction: str = Field(default="", description="the correct statement, for contradicted or unsupported")


class FactVerdict(BaseModel):
    items: list[FactItem]


class FrameItem(BaseModel):
    file: str
    ok: bool
    problems: list[str] = Field(default_factory=list)
    instruction: str = ""


class FrameVerdict(BaseModel):
    items: list[FrameItem]


# --- the job --------------------------------------------------------------------

# script_ready: written and checked, build not started (only a by-hand script run stops there).
JobState = Literal["writing", "script_ready", "approved", "building", "built", "failed"]


class VideoJob(BaseModel):
    """`data/video-work/<id>/job.json`: what the console shows and the build reads."""

    id: str
    mode: Mode
    lesson_md: str
    course: str = ""
    phase_slugs: list[str] = Field(default_factory=list)
    title: str = ""
    state: JobState = "writing"
    script_task_id: str = ""
    build_task_id: str = ""
    report: list[str] = Field(default_factory=list)
    mismatches: list[str] = Field(default_factory=list)
    review: dict[str, object] = Field(default_factory=dict)
    duration_s: float = 0.0
    verify: dict[str, object] = Field(default_factory=dict)
    updated: str = ""
