"use client";

import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { agentAdminApi, agentAdminKeys } from "@/lib/api/agents-admin";

const DATALIST_ID = "agent-editor-tool-names";

/**
 * One Input per tool entry (`name` or `vault_write:<folder>/**`), plus the
 * registry catalog as helper text and as browser autocomplete.
 */
export function ToolsEditor({
  tools,
  onChange,
}: {
  tools: string[];
  onChange: (tools: string[]) => void;
}) {
  const catalog = useQuery({
    queryKey: agentAdminKeys.toolsCatalog,
    queryFn: agentAdminApi.toolsCatalog,
    staleTime: 5 * 60 * 1000,
  });

  const update = (i: number, value: string) =>
    onChange(tools.map((t, j) => (j === i ? value : t)));
  const remove = (i: number) => onChange(tools.filter((_, j) => j !== i));

  return (
    <div className="flex flex-col gap-2">
      <Label>Tools</Label>
      {tools.length === 0 ? (
        <p className="text-muted-foreground text-xs">
          No tools. The agent still gets load_skill for its own skills folder.
        </p>
      ) : null}
      {tools.map((tool, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input
            value={tool}
            list={DATALIST_ID}
            placeholder="tool name, or vault_write:<folder>/**"
            aria-label={`Tool ${i + 1}`}
            className="font-mono"
            onChange={(e) => update(i, e.target.value)}
          />
          <Button
            type="button"
            size="sm"
            variant="ghost"
            aria-label={`Remove tool ${i + 1}`}
            onClick={() => remove(i)}
          >
            Remove
          </Button>
        </div>
      ))}
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="self-start"
        onClick={() => onChange([...tools, ""])}
      >
        Add tool
      </Button>
      <datalist id={DATALIST_ID}>
        {(catalog.data ?? []).map((t) => (
          <option key={t.name} value={t.name} />
        ))}
      </datalist>
      <div className="text-muted-foreground text-xs">
        {catalog.isPending ? (
          <p>Loading tool catalog…</p>
        ) : catalog.isError ? (
          <p>Tool catalog unavailable: {catalog.error.message}</p>
        ) : (
          <>
            <p className="mb-1">
              Available tools. Click one to add it. Scope vault_write as
              vault_write:&lt;folder&gt;/**. An agent with a web-read tool may
              only hold vault_write:quarantine/** and no outward tool.
            </p>
            <ul className="grid gap-x-4 gap-y-0.5 md:grid-cols-2">
              {catalog.data.map((t) => {
                // vault_write is added scoped, so an exact match is the test
                // for a plain tool and a prefix match for a scoped one.
                const held = tools.some(
                  (tool) => tool === t.name || tool.startsWith(`${t.name}:`),
                );
                return (
                  <li key={t.name}>
                    <button
                      type="button"
                      disabled={held}
                      title={held ? "Already on this agent" : `Add ${t.name}`}
                      onClick={() => onChange([...tools, t.name])}
                      className="hover:bg-muted -mx-1 w-full rounded px-1 text-left disabled:opacity-60 disabled:hover:bg-transparent"
                    >
                      <span className="text-foreground font-mono">{t.name}</span>{" "}
                      <span>
                        ({t.action}, {t.trust})
                      </span>
                      {t.grantable === "no" ? (
                        <span> · approval per call</span>
                      ) : null}
                      {held ? <span> · added</span> : null}
                      {t.description ? <span> — {t.description}</span> : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
