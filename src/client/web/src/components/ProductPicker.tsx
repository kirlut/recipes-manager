import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getProduct, listProducts } from "../api/products";
import type { Product, ProductListItem } from "../api/types";
import { ErrorBanner } from "./ErrorBanner";

interface ProductPickerProps {
  onSelect: (product: Product) => void;
}

export function ProductPicker({ onSelect }: ProductPickerProps) {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [picking, setPicking] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(search), 300);
    return () => window.clearTimeout(t);
  }, [search]);

  const trimmed = debounced.trim();
  const enabled = trimmed.length > 0;

  const results = useQuery({
    queryKey: ["products", "picker-search", trimmed],
    queryFn: () => listProducts({ scope: "search", q: trimmed, limit: 20 }),
    enabled,
  });

  async function handlePick(item: ProductListItem) {
    setPicking(true);
    try {
      const full = await getProduct(item.id);
      onSelect(full);
    } finally {
      setPicking(false);
    }
  }

  const items = results.data?.items ?? [];

  return (
    <div className="space-y-2">
      <input
        type="search"
        className="input input-bordered w-full"
        placeholder="Search products by name…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        aria-label="Product search"
      />
      <ErrorBanner error={results.error} />
      {enabled && results.isFetching && !results.data && (
        <div className="text-sm opacity-70">Searching…</div>
      )}
      {enabled && !results.isFetching && items.length === 0 && (
        <div className="text-sm opacity-70">No matches.</div>
      )}
      {items.length > 0 && (
        <ul className="border border-base-300 rounded divide-y divide-base-300 max-h-64 overflow-auto">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className="w-full text-left px-3 py-2 hover:bg-base-200 disabled:opacity-50"
                onClick={() => handlePick(item)}
                disabled={picking}
              >
                {item.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
