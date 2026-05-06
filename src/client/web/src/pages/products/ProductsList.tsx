import { useEffect, useMemo, useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  listProducts,
  starProduct,
  unstarProduct,
} from "../../api/products";
import type {
  ListScope,
  Page,
  ProductListItem,
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

export function ProductsList() {
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

  const query = useInfiniteQuery<Page<ProductListItem>>({
    queryKey: ["products", "list", tab, tab === "search" ? debouncedSearch : ""],
    queryFn: async ({ pageParam }) =>
      listProducts({
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
        <h1 className="text-2xl font-bold">Products</h1>
        <Link to="/products/new" className="btn btn-primary">
          New Product
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
          placeholder="Search products by name…"
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
        keyOf={(p) => p.id}
        empty={
          <div className="opacity-70 italic">
            {tab === "search" && debouncedSearch.trim().length === 0
              ? "Type to search…"
              : "No products."}
          </div>
        }
        renderItem={(p) => <ProductCard product={p} />}
      />
    </div>
  );
}

function ProductCard({ product }: { product: ProductListItem }) {
  const queryClient = useQueryClient();
  const starred = product.starred_by_me;

  const star = useMutation({
    mutationFn: () =>
      starred ? unstarProduct(product.id) : starProduct(product.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });

  return (
    <div className="card bg-base-100 shadow border border-base-300 h-full">
      {product.image_filename && (
        <figure className="h-32 overflow-hidden bg-base-200">
          <img
            src={`/uploads/${product.image_filename}`}
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
          to={`/products/${product.id}`}
          className="card-title text-base hover:underline"
        >
          {product.name}
        </Link>
        {product.created_by && (
          <div className="text-xs opacity-70">
            by {product.created_by.username}
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
