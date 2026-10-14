"""The shapes the model returns, and the job record kept on disk."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["course", "article"]


# --- the plan -----------------------------------------------------------------

class PlannedConcept(BaseModel):
    """One concept in the story order: the question before the answer, the claim said once at the end."""

    id: str = Field(description="c1, c2, ... in teaching order")
    heading: str = Field(description="the concept as the question it answers, max 60 characters")
    situation: str = Field(description=(
        "where the running case reaches this concept, with the number that makes it matter"))
    question: str = Field(description="the question this concept answers, in the viewer's words; ends with ?")
    first_thought: str = Field(description="the answer a reasonable engineer gives first")
    why_reasonable: str = Field(description="why that answer is reasonable, from what he has built")
    what_it_misses: str = Field(description="what that answer does not account for, concretely")
    picture: str = Field(default="", description=(
        "the parts and terms the mechanism needs, each defined; empty when it needs none"))
    steps: list[str] = Field(description="the mechanism, 2 to 6 steps, each with its reason")
    number: str = Field(description="the one number or failure that proves it, with its conditions")
    evidence_quote: str = Field(description="copied exactly from the material")
    takeaway: str = Field(description=(
        "the concept's claim, said once, at the end, as he would tell a colleague"))
    bridge: str = Field(default="", description=(
        "what happens next in the running case, leading to the next concept's question;"
        " empty on the last concept"))
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
    try_this: str = Field(default="", description=(
        "one action on his own system, said once in the end beat of the last part"))
    left_out: list[str] = Field(default_factory=list,
                                description="taught in the lesson but not here, and where it lives")
    mismatches: list[str] = Field(default_factory=list,
                                  description="where the material contradicts its own numbers or sources")


# --- the series ---------------------------------------------------------------
# A lesson longer than one sitting is told as parts of about ten minutes:
# each part is its own video with its own question, answered inside it, and
# ends on the question the next part answers.

class PartPlan(BaseModel):
    title: str = Field(description="this part's title, the problem in the viewer's words, max 70")
    question: str = Field(description="the one question this part answers; ends with ?")
    concepts: list[str] = Field(description=(
        "the concepts this part teaches, each as the question it answers, in teaching order"))
    answer: str = Field(description="how this part answers its question, with the lesson's numbers")
    leads_to: str = Field(default="", description=(
        "the open question this part ends on, which the next part answers; ends with ?;"
        " empty on the last part"))


class SeriesPlan(BaseModel):
    title: str = Field(description="the lesson's problem in the viewer's words, max 70")
    running_case: str = Field(description="the one situation every part follows, owned by the viewer")
    parts: list[PartPlan]
    left_out: list[str] = Field(default_factory=list,
                                description="taught in the lesson but in no part, and where it lives")
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
    stakes: int = Field(ge=1, le=5)

    def low(self, bar: int) -> list[str]:
        return [c for c in ("answers_question", "connected", "thinks_aloud", "defined",
                            "spoken", "numbers", "stakes") if getattr(self, c) < bar]

    def mean(self) -> float:
        vals = [self.answers_question, self.connected, self.thinks_aloud, self.defined,
                self.spoken, self.numbers, self.stakes]
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
    # A part of a series (data/video-work/<series_id>/series.json): part 1 of
    # parts. Empty for a video made before series existed.
    series_id: str = ""
    part: int = 0
    parts: int = 0
    title: str = ""
    state: JobState = "writing"
    script_task_id: str = ""
    build_task_id: str = ""
    # The script stages script_task_id finished (plan, beats, whole, editor,
    # facts, whole2), so that task resumes there when it is queued again.
    stages: list[str] = Field(default_factory=list)
    report: list[str] = Field(default_factory=list)
    mismatches: list[str] = Field(default_factory=list)
    review: dict[str, object] = Field(default_factory=dict)
    duration_s: float = 0.0
    verify: dict[str, object] = Field(default_factory=dict)
    updated: str = ""
