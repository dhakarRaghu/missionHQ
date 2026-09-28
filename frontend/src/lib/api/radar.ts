// Client and types for the Radar page (GET/POST /api/radar/*). One read
// returns the whole page, and every action answers with the page again, so
// the cache is written from the answer and nothing is fetched twice.

import { getJson, sendJson } from "@/lib/api/request";

export interface RadarKind {
  kind: string;
  items: number;
  sites: number;
  unread: number;
}

export interface RadarCollection {
  kinds: RadarKind[];
  items: number;
  sites: number;
  newest: string | null;
  problems: number;
  none: number;
  refused: number;
  unread: number;
}

export interface RadarProblem {
  id: number;
  statement: string;
  area: string;
  origin: "radar" | "owner";
  evidence: number;
  domains: number;
  /** One of its reports is loud: many people joined it. */
  strong?: boolean;
  /** An idea can be written for it. */
  enough?: boolean;
  status?: string;
  last_seen?: string;
}

export interface RadarEvidence {
  quote: string;
  kind: string;
  domain: string;
  statement: string;
  url: string;
  title: string;
  item_kind: string;
  published_at: string | null;
}

/** The judge's marks, as stored. Empty when the judge gave none. */
export interface RadarMarks {
  one_session?: boolean;
  needs_you?: number[];
  learning?: number;
  fits_rig?: number;
  measurable?: number;
  why?: string;
}

export interface RadarIdea {
  id: number;
  problem_id: number;
  brief: string;
  title: string;
  question: string;
  build: string;
  measure: string;
  baseline: string;
  workload: string;
  rig: string;
  learn: string;
  hard_because: string;
  first_step: string;
  scores: RadarMarks;
  score: number;
  status: "proposed" | "chosen" | "declined" | "dropped";
  reason: string;
  problem: RadarProblem | null;
  evidence: RadarEvidence[];
}

export interface RadarLeftOut {
  id: number;
  title: string;
  question: string;
  reason: string;
  score: number;
}

export type ProjectStatus = "building" | "built" | "shared" | "stopped";

export interface RadarProject extends Omit<RadarIdea, "problem" | "evidence"> {
  project_id: number;
  project_status: ProjectStatus;
  started_at: string;
  due_at: string;
  finished_at: string | null;
  result: string;
  surprise: string;
  share_url: string;
  problem?: RadarProblem | null;
  evidence?: RadarEvidence[];
}

export interface RadarRules {
  every_days: number;
  ideas: number;
  min_domains: number;
  strong: { comments: number; reactions: number; points: number };
  project_days: number;
  needs_you_min: number;
  needs_you: string[];
  one_session: string[];
  rig: Record<string, string>;
}

export interface Radar {
  collection: RadarCollection;
  /** `shown` is cut at thirty; the two counts are of all open problems. */
  problems: { open: number; enough: number; shown: RadarProblem[] };
  ideas: {
    brief: string | null;
    /** Ideas written in the newest brief, whatever became of them. */
    written: number;
    proposed: RadarIdea[];
    /** The gate said no: too easy, no sound measurement, or no machine for it. */
    dropped: RadarLeftOut[];
    /** Passed the gate; the brief was full. */
    ranked_out: RadarLeftOut[];
    declined: RadarLeftOut[];
  };
  projects: { running: RadarProject | null; past: RadarProject[] };
  rules: RadarRules;
}

export interface FinishBody {
  status: Exclude<ProjectStatus, "building">;
  result: string;
  surprise: string;
  share_url: string;
  problems: string[];
}

export const radarKeys = {
  page: ["radar"] as const,
  problem: (id: number) => ["radar", "problem", id] as const,
};

export const radarApi = {
  page: () => getJson<Radar>("/radar"),
  problem: (id: number) =>
    getJson<RadarProblem & { evidence: RadarEvidence[] }>(`/radar/problems/${id}`),
  choose: (id: number) => sendJson<Radar>("POST", `/radar/ideas/${id}/choose`),
  decline: (id: number, reason: string) =>
    sendJson<Radar>("POST", `/radar/ideas/${id}/decline`, { reason }),
  finish: (id: number, body: FinishBody) =>
    sendJson<Radar>("POST", `/radar/projects/${id}/finish`, body),
  addProblem: (statement: string) =>
    sendJson<Radar>("POST", "/radar/problems", { statement }),
  dismiss: (id: number) =>
    sendJson<Radar>("POST", `/radar/problems/${id}/dismiss`),
};
