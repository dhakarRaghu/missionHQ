import { getBlob, getJson, queryString, sendJson } from "@/lib/api/request";
import { API_BASE } from "@/lib/auth";

// Client, types and query keys for the course videos (GET /api/media/*).
// The manifest is in git (learning/videos/index.json); the files are not, and
// the backend serves them from its media folder. See docs/videos.md.

/** "course" is the long video of one phase; "youtube" is one short episode
 * of the YouTube playlist; "article" is the video of one Learn article, shown
 * above the article and in the library. */
export type VideoKind = "course" | "youtube" | "article";

export interface VideoChapter {
  /** Start, in seconds from the beginning of the video. */
  t: number;
  title: string;
}

export interface Video {
  id: string;
  kind: VideoKind;
  /** The course key, as `hq.course_phases.course` names it. */
  course: string;
  /** The phase the video belongs to. */
  phase_slug: string;
  /** Every phase it covers. The Phase 2 video covers 2A and 2B. */
  phase_slugs: string[];
  /** The episode number in the YouTube playlist; null for a course video. */
  number: number | null;
  title: string;
  duration_s: number | null;
  chapters: VideoChapter[];
  /**
   * Set when he has uploaded the video to YouTube as a private video. The
   * player then plays the YouTube embed; otherwise it plays the local file.
   */
  youtube_id: string | null;
  /** The lesson file the video was made from. */
  source_lesson?: string | null;
  /** False when this machine does not have the file the manifest names. */
  available: boolean;
  /**
   * Signed URLs, relative to the API base. A `<video>` cannot send the
   * Authorization header, so each URL carries a signature for that one file,
   * valid for about a day. Use `mediaUrl` to make them absolute.
   */
  urls: {
    video: string | null;
    captions: string | null;
  };
}

export interface VideoFilter {
  course?: string;
  /** A phase slug; matches any of a video's `phase_slugs`. */
  phase?: string;
  kind?: string;
}

export const mediaKeys = {
  all: ["media"] as const,
  /** Every video job, newest first (GET /api/videos/jobs). */
  jobs: ["media", "jobs"] as const,
  /** One job with its plan, narration and reviews. */
  job: (id: string) => ["media", "jobs", id] as const,
  /** The contact sheet of one job, as a blob. */
  jobSheet: (id: string, updated: string) =>
    ["media", "jobs", id, "sheet", updated] as const,
  videos: (filter: VideoFilter = {}) =>
    [
      "media",
      "videos",
      filter.course ?? "",
      filter.phase ?? "",
      filter.kind ?? "",
    ] as const,
};

export const mediaApi = {
  videos: (filter: VideoFilter = {}) =>
    getJson<Video[]>(`/media/videos${queryString({ ...filter })}`),
  /** Accepts a full YouTube URL or an id; null clears it. The backend
   * reduces a URL to the id and writes it into the manifest. */
  setYoutubeId: (id: string, youtubeId: string | null) =>
    sendJson<Video>("PATCH", `/media/videos/${encodeURIComponent(id)}`, {
      youtube_id: youtubeId,
    }),
  jobs: () => getJson<VideoJobRow[]>("/videos/jobs"),
  job: (id: string) =>
    getJson<VideoJobDetail>(`/videos/jobs/${encodeURIComponent(id)}`),
  jobSheet: (id: string) =>
    getBlob(`/videos/jobs/${encodeURIComponent(id)}/sheet`),
  /**
   * "Generate video" for a lesson (`lesson_md` is a learning/lessons/*.md path).
   * A stopped job whose script passed its checks is built again from it;
   * `fresh` writes a new script instead.
   */
  makeVideo: (
    lessonMd: string,
    mode: "course" | "article" = "course",
    fresh = false,
  ) =>
    sendJson<VideoStart>("POST", "/videos/make", {
      lesson_md: lessonMd,
      mode,
      fresh,
    }),
};

// --- video jobs (GET/POST /api/videos/*) ------------------------------------
// A job is one video on its way: the script, the two reviews, then the voice
// and the render, with no approval step. It starts only when he presses
// "Generate video"; Courses → Videos shows how far it got. See backend/src/hq/api/videos.py.

export type VideoJobState =
  /** A new task for a stopped or finished job, waiting to start. */
  | "queued"
  | "writing"
  | "script_ready"
  | "approved"
  | "building"
  | "built"
  | "failed";

/** The states in which a task is working on the job, so the list polls. */
export const ACTIVE_JOB_STATES: readonly VideoJobState[] = [
  "queued",
  "writing",
  "approved",
  "building",
];

/** One row of GET /api/videos/jobs. */
export interface VideoJobRow {
  id: string;
  mode: VideoKind;
  title: string;
  state: VideoJobState;
  lesson_md: string;
  course: string;
  /** Zero until the video is built. */
  duration_s: number;
  updated: string;
  /** Script length, once the script is written. */
  minutes?: number;
  /** Stopped with a checked script: "Generate" builds it again, no new script. */
  can_rebuild: boolean;
}

/** The answer of make. */
export interface VideoStart {
  started: boolean;
  video_id?: string;
  task_id: string;
  /** "build" when a checked script is built again, "script" when it is written. */
  stage?: "script" | "build" | "";
  /** Why nothing started, such as a task already running for it. */
  reason?: string;
}

/** The job record on disk (`data/video-work/<id>/job.json`). */
export interface VideoJob extends VideoJobRow {
  phase_slugs: string[];
  script_task_id: string;
  build_task_id: string;
  /** Notes from the script writer and the build, one per line. */
  report: string[];
  /** Where the lesson contradicts its own numbers or sources. */
  mismatches: string[];
  /** The render checks, once built: key → passed, plus details. */
  verify: Record<string, unknown>;
}

export interface PlannedConcept {
  id: string;
  heading: string;
  question: string;
}

export interface VideoPlan {
  title: string;
  question: string;
  running_case: string;
  concepts: PlannedConcept[];
  payoff: string;
  left_out: string[];
  mismatches: string[];
}

export interface NarrationLine {
  key: string;
  /** What the screen shows as the caption. */
  text: string;
  /** What the voice says, when it differs (numbers spelled out and such). */
  say?: string;
}

export interface Narration {
  /** In speaking order: cold, title, c1…cN, payoff, recap, end. */
  beats: Record<string, { chapter?: string; lines: NarrationLine[] }>;
}

/** The seven things the teaching editor scores, 1 to 5, per beat. */
export const EDITOR_CRITERIA = [
  "answers_question",
  "connected",
  "thinks_aloud",
  "defined",
  "spoken",
  "numbers",
  "transfer",
] as const;
export type EditorCriterion = (typeof EDITOR_CRITERIA)[number];

/** A criterion under this sends a beat back to the writer (EDITOR_BAR). */
export const EDITOR_BAR = 4;

export type BeatScore = { beat: string } & Record<EditorCriterion, number>;

export interface EditorFinding {
  beat: string;
  criterion: string;
  quote: string;
  problem: string;
  instruction: string;
}

export type FactVerdict = "supported" | "contradicted" | "unsupported" | "example";

export interface FactRow {
  beat: string;
  key: string;
  verdict: FactVerdict;
  material_quote: string;
  arithmetic: string;
  correction: string;
}

export interface VideoReview {
  editor: {
    scores: BeatScore[];
    findings: EditorFinding[];
    whole_video: string[];
  };
  facts: FactRow[];
  /** The code checks still failing after the rewrites. */
  remaining: string[];
  minutes: number;
  think_questions: string[];
}

/** GET /api/videos/jobs/{id}. Each file is null until its step has run. */
export interface VideoJobDetail {
  job: VideoJob;
  can_rebuild: boolean;
  plan: VideoPlan | null;
  narration: Narration | null;
  review: VideoReview | null;
  has_sheet: boolean;
}

/** A signed URL from the API, as the browser must request it. */
export function mediaUrl(path: string | null): string | undefined {
  return path ? `${API_BASE}${path}` : undefined;
}

/** "27 min" for a course video, "7:05" for an episode. */
export function formatDuration(seconds: number | null): string {
  if (seconds == null) return "";
  if (seconds >= 15 * 60) return `${Math.round(seconds / 60)} min`;
  return formatTime(seconds);
}

/** "4:07", or "1:02:09" past an hour. */
export function formatTime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

/** Course videos first, then the YouTube episodes by number. */
export function sortVideos(videos: Video[]): Video[] {
  const rank: Record<VideoKind, number> = { course: 0, youtube: 1, article: 2 };
  return [...videos].sort(
    (a, b) =>
      rank[a.kind] - rank[b.kind] ||
      (a.number ?? 0) - (b.number ?? 0) ||
      (a.phase_slug ?? "").localeCompare(b.phase_slug ?? ""),
  );
}
