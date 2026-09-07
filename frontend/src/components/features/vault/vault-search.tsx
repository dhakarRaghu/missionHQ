"use client";

import { Fragment, useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { SEARCH_LIMIT, vaultApi, vaultKeys } from "@/lib/api/vault";

const DEBOUNCE_MS = 300;

/** Search box with debounced hybrid search. Picking a hit opens the note. */
export function VaultSearch({ onSelect }: { onSelect: (path: string) => void }) {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setQuery(text.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text]);

  const active = query.length > 0;
  const results = useQuery({
    queryKey: vaultKeys.search(query, SEARCH_LIMIT),
    queryFn: () => vaultApi.search(query, SEARCH_LIMIT),
    enabled: active,
    // Keep the old list on screen while the next query loads.
    placeholderData: keepPreviousData,
  });

  return (
    <section aria-label="Search vault" className="flex flex-col gap-2">
      <div className="relative">
        <Search
          className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
          aria-hidden
        />
        <Input
          type="search"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") setText("");
          }}
          placeholder="Search notes by words or meaning"
          aria-label="Search notes"
          className="h-9 pr-9 pl-9"
        />
        {text ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Clear search"
            onClick={() => setText("")}
            className="absolute top-1/2 right-0.5 size-8 -translate-y-1/2"
          >
            <X aria-hidden />
          </Button>
        ) : null}
      </div>

      {!active ? null : results.isLoading ? (
        <div role="status" aria-busy="true" aria-label="Searching">
          <Skeleton className="h-16 w-full" />
        </div>
      ) : results.isError ? (
        <ErrorState
          message={results.error.message}
          onRetry={() => results.refetch()}
          retrying={results.isFetching}
        />
      ) : !results.data?.length ? (
        <EmptyState>No notes match “{query}”.</EmptyState>
      ) : (
        <>
          <p className="text-muted-foreground px-1 text-xs">
            {results.data.length} note{results.data.length === 1 ? "" : "s"}{" "}
            match “{query}”. Press Escape to clear.
          </p>
          <ul
            aria-label="Search results"
            className="max-h-64 divide-y overflow-y-auto rounded-lg border"
          >
          {results.data.map((hit) => (
            <li key={hit.path}>
              <button
                type="button"
                onClick={() => onSelect(hit.path)}
                className="hover:bg-muted flex w-full flex-col gap-0.5 px-3 py-2 text-left"
              >
                <span className="flex flex-wrap items-baseline gap-x-2 text-sm">
                  <span className="font-medium break-all">{hit.path}</span>
                  {hit.heading ? (
                    <span className="text-muted-foreground text-xs">
                      {hit.heading}
                    </span>
                  ) : null}
                </span>
                <span className="text-muted-foreground line-clamp-2 text-xs">
                  <Snippet text={hit.snippet} />
                </span>
              </button>
            </li>
          ))}
          </ul>
        </>
      )}
    </section>
  );
}

/** ts_headline wraps matches in `**`; render those spans as bold. */
function Snippet({ text }: { text: string }) {
  const parts = text.split("**");
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <strong key={i} className="text-foreground font-semibold">
            {part}
          </strong>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}
