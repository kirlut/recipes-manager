import { useEffect, useMemo, useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  listRecipes,
  starRecipe,
  unstarRecipe,
} from "../../api/recipes";
import type {
  ListScope,
  Page,
  RecipeListItem,
} from "../../api/types";
import { ErrorBanner } from "../../components/ErrorBanner";
import { InfiniteList } from "../../components/InfiniteList";

const TABS: { id: ListScope; label: string }[] = [
  { id: "mine", label: "My" },
  { id: "starred", label: "Starred" },
  { id: "search", label: "Search" },
];

function extractCursor(next: string | undefined): string | undefined {
  if (!next) return undefined;
  try {
    const url = new URL(next, window.location.origin);
    return url.searchParams.get("cursor") ?? undefined;
  } catch {
    return undefined;
  }
}

export function RecipesList() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("tab") as ListScope | null;
  const tab: ListScope =
    rawTab === "starred" || rawTab === "search" ? rawTab : "mine";

  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(searchInput), 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  const enabled = tab !== "search" || debouncedSearch.trim().length > 0;

  const query = useInfiniteQuery<Page<RecipeListItem>>({
    queryKey: ["recipes", "list", tab, tab === "search" ? debouncedSearch : ""],
    queryFn: async ({ pageParam }) =>
      listRecipes({
        scope: tab,
        q: tab === "search" ? debouncedSearch : undefined,
        cursor: pageParam as string | undefined,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => extractCursor(last.next),
    enabled,
  });

  const items = useMemo(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data],
  );

  function setTab(next: ListScope) {
    setSearchParams((prev) => {
      const sp = new URLSearchParams(prev);
      sp.set("tab", next);
      return sp;
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h1 className="text-2xl font-bold">Recipes</h1>
        <Link to="/recipes/new" className="btn btn-primary">
          New Recipe
        </Link>
      </div>

      <div role="tablist" className="tabs tabs-bordered">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={"tab" + (tab === t.id ? " tab-active" : "")}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "search" && (
        <input
          type="search"
          className="input input-bordered w-full max-w-md"
          placeholder="Search recipes by name…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
      )}

      <ErrorBanner error={query.error} />

      <InfiniteList
        items={items}
        hasNextPage={Boolean(query.hasNextPage)}
        isFetchingNextPage={query.isFetchingNextPage || query.isFetching}
        fetchNextPage={() => query.fetchNextPage()}
        keyOf={(r) => r.id}
        empty={
          <div className="opacity-70 italic">
            {tab === "search" && debouncedSearch.trim().length === 0
              ? "Type to search…"
              : "No recipes."}
          </div>
        }
        renderItem={(r) => <RecipeCard recipe={r} />}
      />
    </div>
  );
}

function RecipeCard({ recipe }: { recipe: RecipeListItem }) {
  const queryClient = useQueryClient();
  const starred = recipe.starred_by_me;

  const star = useMutation({
    mutationFn: () =>
      starred ? unstarRecipe(recipe.id) : starRecipe(recipe.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recipes"] });
    },
  });

  return (
    <div className="card bg-base-100 shadow border border-base-300 h-full">
      {recipe.image_filename && (
        <figure className="h-32 overflow-hidden bg-base-200">
          <img
            src={`/uploads/${recipe.image_filename}`}
            alt=""
            className="w-full h-full object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        </figure>
      )}
      <div className="card-body p-4">
        <Link
          to={`/recipes/${recipe.id}`}
          className="card-title text-base hover:underline"
        >
          {recipe.name}
        </Link>
        {recipe.created_by && (
          <div className="text-xs opacity-70">
            by {recipe.created_by.username}
          </div>
        )}
        <div className="card-actions mt-2">
          <button
            type="button"
            className={"btn btn-sm " + (starred ? "btn-warning" : "btn-ghost")}
            onClick={() => star.mutate()}
            disabled={star.isPending}
          >
            {starred ? "Unstar" : "Star"}
          </button>
        </div>
      </div>
    </div>
  );
}
