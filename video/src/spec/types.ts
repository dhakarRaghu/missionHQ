// The VideoSpec contract (video/SPEC.md, versions 1 and 2) as TypeScript types.
// Version 2 changes only the concept beat: the question comes before the answer, and the claim is the
// takeaway at the end (situation, think, picture, mechanism, number, takeaway, bridge).
// video/spec/video-spec.schema.json is the same contract as JSON Schema, for Python and check-spec.mjs.
// Keep the two in step: every limit here is a maxLength or maxItems there.

export type Tone = "ink" | "ok" | "bad" | "warn" | "info" | "accent";

/** Key of the narration line on which an element appears. It must exist in the same beat. */
export type At = string;

type PanelBase = {
  caption?: string; // max 90: one handwritten line above the panel
  note?: string; // max 120: small grey text under it
};

export type ChipsPanel = PanelBase & {
  kind: "chips";
  items: { text: string; tone?: Tone; at: At }[]; // 1–6, text max 64
};

export type FlowPanel = PanelBase & {
  kind: "flow";
  nodes: { label: string; sub?: string; tone?: Tone; at: At }[]; // 2–5, label max 22, sub max 36
};

export type StatsPanel = PanelBase & {
  kind: "stats";
  items: { value: string; label?: string; tone?: Tone; at: At }[]; // 1–3, value max 14, label max 40
};

export type BarsPanel = PanelBase & {
  kind: "bars";
  items: { label: string; value: number; display: string; tone?: Tone; at: At }[]; // 2–6, label max 28, display max 16
};

export type TablePanel = PanelBase & {
  kind: "table";
  columns: string[]; // 2–4, max 18 each
  rows: { cells: string[]; tone?: Tone; at: At }[]; // 1–6, cell max 22, one cell per column
};

export type EquationPanel = PanelBase & {
  kind: "equation";
  lines: { text: string; tone?: Tone; at: At }[]; // 1–5, text max 48
};

export type CompareSide = { title: string; items: string[] }; // title max 28, 1–4 items max 40

export type ComparePanel = PanelBase & {
  kind: "compare";
  left: CompareSide;
  right: CompareSide;
  at_left: At;
  at_right: At;
};

export type PromptPanel = PanelBase & {
  kind: "prompt";
  title?: string; // max 40
  lines: { text: string; tone?: Tone; at: At }[]; // 1–8, text max 56
};

export type Panel = ChipsPanel | FlowPanel | StatsPanel | BarsPanel | TablePanel | EquationPanel | ComparePanel | PromptPanel;
export type PanelKind = Panel["kind"];

/** A step that shows visuals: one `panel`, or `panels` (2–3) shown one after another. */
type Visual = { panel: Panel; panels?: never } | { panels: Panel[]; panel?: never };

export type ClaimStep = { step: "claim" };
export type SituationStep = { step: "situation" } & Visual;
export type PictureStep = { step: "picture" } & Visual;
/**
 * v1: first, misses and real are required, one per `t` line. v2: first and misses are optional (both or
 * neither), `real` is not used, and `first_at` / `misses_at` name the `t` lines they appear on (default:
 * the first and the last `t` line); the first thought is struck through at `misses_at`.
 */
export type ThinkStep = { step: "think"; first?: string; misses?: string; real?: string; first_at?: At; misses_at?: At }; // 70, 70, 90
export type MechanismStep = {
  step: "mechanism";
  items: { text: string; at: At }[]; // 2–6, one per m line, text max 48
  side?: Panel;
};
export type NumberStep = { step: "number"; source?: { text: string } } & Visual; // source max 160
export type KeypointsStep = { step: "keypoints" };
export type TakeawayStep = { step: "takeaway" }; // v2: the claim card, drawn from the `k` lines and `count`
export type BridgeStep = { step: "bridge"; label?: string } & Visual; // label max 40
export type PanelStep = { step: "panel" } & Visual;

export type Step =
  | ClaimStep | SituationStep | PictureStep | ThinkStep | MechanismStep | NumberStep | KeypointsStep | TakeawayStep
  | BridgeStep | PanelStep;
export type StepName = Step["step"];

export type BeatKind = "cold" | "title" | "concept" | "payoff" | "recap" | "end";

export type Beat = {
  id: string; // cold | title | c1..c9 | payoff | recap | end
  kind: BeatKind;
  heading?: string; // max 60; required for concept and payoff
  count?: string; // max 12; concept only, "1 of 3"
  mark?: string; // max 40; highlighter words: a substring of the claim (concept) or the video title (title beat)
  steps?: Step[];
};

export type VideoSpec = {
  version: 1 | 2;
  id: string; // max 80
  mode: "course" | "youtube" | "article";
  series: string; // max 40
  number: number | null;
  title: string; // max 70
  label: string; // max 40
  next?: { number: number | null; title: string | null; label?: string }; // title max 60, label max 24 ("Next part")
  site?: string; // max 40
  beats: Beat[];
};

// ---------------------------------------------------------------- timing file (written by scripts/narrate.mjs)

export type TimingLine = {
  key: string;
  at: number; // local frame where elements keyed to this line appear (voice start minus a small lead)
  start: number; // local frame where the voice starts the line
  end: number; // local frame where the voice ends the line
  text: string; // caption text of the line
};

export type TimingCue = { text: string; start: number; end: number };

export type TimingBeat = {
  id: string;
  chapter: string | null;
  start: number; // absolute frame where the beat starts
  end: number; // absolute frame where its hold ends
  audioFrames: number;
  cues: TimingCue[]; // local frames
  steps: TimingLine[]; // one per narration line, local frames
};

export type Timing = {
  version: 1;
  fps: number;
  totalFrames: number;
  order: string[];
  beats: Record<string, TimingBeat>;
};

export type SpecVideoProps = {
  spec: VideoSpec;
  timing: Timing | null;
  audioDir: string; // folder of <beatId>.mp3 inside the public dir; "" = the public dir itself
};
