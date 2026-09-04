import { getJson } from "@/lib/api/request";

// Client for GET /api/evals/latest: one row per agent, its most recent eval.

export interface EvalScore {
  agent: string;
  /** passed / cases, 0..1. Always a number; the backend may send a string. */
  score: number;
  cases: number;
  passed: number;
  ts: string;
  dataset: string;
  job_hash: string;
  cost_usd: number;
}

type RawEvalScore = Omit<EvalScore, "score" | "cost_usd"> & {
  score: string | number;
  cost_usd: string | number;
};

export const evalKeys = {
  latest: ["evals", "latest"] as const,
};

export const evalsApi = {
  latest: async (): Promise<EvalScore[]> => {
    const rows = await getJson<RawEvalScore[]>("/evals/latest");
    return rows.map((row) => ({
      ...row,
      score: Number(row.score),
      cost_usd: Number(row.cost_usd),
    }));
  },
};
