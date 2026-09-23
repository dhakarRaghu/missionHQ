"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApplyDialog } from "@/components/features/agents/agent-editor/apply-dialog";
import { CronEditor } from "@/components/features/agents/agent-editor/cron-editor";
import { ToolsEditor } from "@/components/features/agents/agent-editor/tools-editor";
import { ValidationResult } from "@/components/features/agents/agent-editor/validation-result";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  AGENT_STATUSES,
  type AgentConfig,
  type AgentConfigBody,
  type AgentStatus,
  type CronEntry,
  MODEL_PRESETS,
  type ValidationResult as ValidationResultData,
  agentAdminApi,
  agentAdminKeys,
} from "@/lib/api/agents-admin";

const CUSTOM_MODEL = "__custom__";

/** Form state. Caps stay strings while typing; toBody converts them. */
interface JobDraft {
  description: string;
  model: string;
  status: AgentStatus;
  tools: string[];
  caps: { cost_per_run_usd: string; tool_calls: string; daily_usd: string };
  cron: CronEntry[];
  role_prompt: string;
}

function fromConfig(config: AgentConfig): JobDraft {
  const status = AGENT_STATUSES.includes(config.status as AgentStatus)
    ? (config.status as AgentStatus)
    : "active";
  return {
    description: config.description,
    model: config.model,
    status,
    tools: [...config.tools],
    caps: {
      cost_per_run_usd: String(config.caps.cost_per_run_usd),
      tool_calls: String(config.caps.tool_calls),
      daily_usd: String(config.caps.daily_usd),
    },
    cron: config.cron.map((c) => ({ ...c })),
    role_prompt: config.role_prompt,
  };
}

/** Request body, or the reason the form cannot be sent yet. */
function toBody(draft: JobDraft): AgentConfigBody | string {
  const cost = Number(draft.caps.cost_per_run_usd);
  const calls = Number(draft.caps.tool_calls);
  const daily = Number(draft.caps.daily_usd);
  if (![cost, calls, daily].every(Number.isFinite)) {
    return "Caps must be numbers.";
  }
  if (!Number.isInteger(calls))
    return "caps.tool_calls must be a whole number.";
  return {
    description: draft.description,
    model: draft.model.trim(),
    status: draft.status,
    tools: draft.tools.map((t) => t.trim()).filter(Boolean),
    caps: { cost_per_run_usd: cost, tool_calls: calls, daily_usd: daily },
    cron: draft.cron,
    role_prompt: draft.role_prompt,
  };
}

function isPresetModel(model: string): model is (typeof MODEL_PRESETS)[number] {
  return (MODEL_PRESETS as readonly string[]).includes(model);
}

/**
 * The "Job" tab: every editable field of job.md, Validate / Save /
 * Apply & restart. The parent remounts it (key) when the saved file changes,
 * so the validation result lives in the parent and survives the remount.
 */
export function JobForm({
  name,
  config,
  result,
  onResult,
  restartPending,
  onRestartPending,
}: {
  name: string;
  config: AgentConfig;
  result: ValidationResultData | null;
  onResult: (result: ValidationResultData | null) => void;
  restartPending: boolean;
  onRestartPending: (pending: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<JobDraft>(() => fromConfig(config));
  const [customModel, setCustomModel] = useState(!isPresetModel(config.model));

  const patch = (change: Partial<JobDraft>) =>
    setDraft((d) => ({ ...d, ...change }));
  const patchCaps = (change: Partial<JobDraft["caps"]>) =>
    setDraft((d) => ({ ...d, caps: { ...d.caps, ...change } }));

  const validate = useMutation({
    mutationFn: (body: AgentConfigBody) => agentAdminApi.validate(name, body),
    onSuccess: (data) => {
      onResult(data);
      toast(data.ok ? "Validation passed" : "Validation failed");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const save = useMutation({
    mutationFn: async (body: AgentConfigBody) => {
      // Validate first so the owner sees every reason, not just the first.
      const checked = await agentAdminApi.validate(name, body);
      onResult(checked);
      if (!checked.ok) throw new Error("Fix the validation errors first.");
      return agentAdminApi.update(name, body);
    },
    onSuccess: (saved) => {
      onResult({
        ok: true,
        errors: [],
        warnings: saved.warnings,
        diff: saved.diff,
      });
      if (saved.restart_required) {
        onRestartPending(true);
        toast("Saved job.md. Apply & restart to load it.");
      } else {
        toast("Saved. job.md did not change; no restart needed.");
      }
      queryClient.invalidateQueries({ queryKey: agentAdminKeys.config(name) });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const busy = validate.isPending || save.isPending;
  // Cheap structural comparison; the draft is small, plain data.
  const dirty = JSON.stringify(draft) !== JSON.stringify(fromConfig(config));

  const submit = (action: "validate" | "save") => {
    const body = toBody(draft);
    if (typeof body === "string") {
      toast.error(body);
      return;
    }
    if (action === "validate") validate.mutate(body);
    else save.mutate(body);
  };

  const globalCap = config.daily_spend_cap_usd;
  const dailyNum = Number(draft.caps.daily_usd);
  const dailyPct =
    globalCap > 0 && Number.isFinite(dailyNum)
      ? Math.max(0, Math.min(100, (dailyNum / globalCap) * 100))
      : 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-2 md:col-span-2">
          <Label htmlFor="agent-description">Description</Label>
          <Input
            id="agent-description"
            value={draft.description}
            onChange={(e) => patch({ description: e.target.value })}
          />
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="agent-model">Model</Label>
          <div className="flex items-center gap-2">
            <Select
              value={customModel ? CUSTOM_MODEL : draft.model}
              onValueChange={(value) => {
                if (value === CUSTOM_MODEL) {
                  setCustomModel(true);
                } else {
                  setCustomModel(false);
                  patch({ model: value });
                }
              }}
            >
              <SelectTrigger id="agent-model" aria-label="Model role">
                <SelectValue placeholder="model" />
              </SelectTrigger>
              <SelectContent>
                {MODEL_PRESETS.map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
                <SelectItem value={CUSTOM_MODEL}>registry name…</SelectItem>
              </SelectContent>
            </Select>
            {customModel ? (
              <Input
                value={draft.model}
                placeholder="name from models.yaml"
                aria-label="Model registry name"
                className="font-mono"
                onChange={(e) => patch({ model: e.target.value })}
              />
            ) : null}
          </div>
          <p className="text-muted-foreground text-xs">
            A role (cheap, default, deep) or a registry name from models.yaml.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="agent-status">Status</Label>
          <Select
            value={draft.status}
            onValueChange={(value) => patch({ status: value as AgentStatus })}
          >
            <SelectTrigger id="agent-status" aria-label="Status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {AGENT_STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-muted-foreground text-xs">
            draft agents are skipped at startup.
          </p>
        </div>
      </div>

      <ToolsEditor tools={draft.tools} onChange={(tools) => patch({ tools })} />

      <div className="flex flex-col gap-2">
        <Label>Caps</Label>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="cap-run" className="text-muted-foreground text-xs">
              Cost per run <code className="font-mono">cost_per_run_usd</code>
            </Label>
            <Input
              id="cap-run"
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              value={draft.caps.cost_per_run_usd}
              onChange={(e) => patchCaps({ cost_per_run_usd: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label
              htmlFor="cap-calls"
              className="text-muted-foreground text-xs"
            >
              Tool calls per run <code className="font-mono">tool_calls</code>
            </Label>
            <Input
              id="cap-calls"
              type="number"
              min="1"
              step="1"
              inputMode="numeric"
              value={draft.caps.tool_calls}
              onChange={(e) => patchCaps({ tool_calls: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label
              htmlFor="cap-daily"
              className="text-muted-foreground text-xs"
            >
              Spend per day <code className="font-mono">daily_usd</code>
            </Label>
            <Input
              id="cap-daily"
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              value={draft.caps.daily_usd}
              onChange={(e) => patchCaps({ daily_usd: e.target.value })}
            />
          </div>
        </div>
        <Progress
          value={dailyPct}
          aria-label="daily_usd against the global daily cap"
        />
        <p className="text-muted-foreground text-xs tabular-nums">
          daily_usd against the global cap: {draft.caps.daily_usd || "0"} / $
          {globalCap.toFixed(2)}. All three must be above 0.
        </p>
      </div>

      <CronEditor cron={draft.cron} onChange={(cron) => patch({ cron })} />

      <div className="flex flex-col gap-2">
        <Label htmlFor="agent-role-prompt">Role prompt</Label>
        <p className="text-muted-foreground text-xs">
          The body of job.md. Who the agent is, what it does, where it writes,
          what it must not do.
        </p>
        <Textarea
          id="agent-role-prompt"
          value={draft.role_prompt}
          className="min-h-80 font-mono text-xs"
          onChange={(e) => patch({ role_prompt: e.target.value })}
        />
      </div>

      {result ? <ValidationResult result={result} /> : null}

      {/* The form is taller than the viewport, so the actions follow it down
          rather than sitting below an 80-row role prompt. */}
      <div className="bg-background sticky bottom-0 -mx-1 flex flex-wrap items-center gap-2 border-t px-1 py-3">
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={() => submit("validate")}
        >
          {validate.isPending ? "Validating…" : "Validate"}
        </Button>
        <Button type="button" disabled={busy} onClick={() => submit("save")}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
        <ApplyDialog
          name={name}
          enabled={restartPending && !busy}
          onApplied={() => onRestartPending(false)}
        />
        {dirty ? (
          <span className="text-status-blocked text-xs">Unsaved changes</span>
        ) : null}
        <p className="text-muted-foreground ml-auto max-w-md text-xs">
          Save writes job.md. Apply and restart loads it, and is enabled after a
          save that changed the file.
        </p>
      </div>
    </div>
  );
}
