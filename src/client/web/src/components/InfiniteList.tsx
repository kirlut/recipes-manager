import { useEffect, useRef, type ReactNode } from "react";

interface InfiniteListProps<T> {
  items: T[];
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
  renderItem: (item: T) => ReactNode;
  empty?: ReactNode;
  keyOf: (item: T) => string | number;
}

export function InfiniteList<T>({
  items,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
  renderItem,
  empty,
  keyOf,
}: InfiniteListProps<T>) {
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && hasNextPage && !isFetchingNextPage) {
            fetchNextPage();
          }
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  if (items.length === 0 && !isFetchingNextPage && empty) {
    return <>{empty}</>;
  }

  return (
    <div>
      <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {items.map((item) => (
          <li key={keyOf(item)}>{renderItem(item)}</li>
        ))}
      </ul>
      <div ref={sentinelRef} className="h-8" />
      {isFetchingNextPage && <div className="text-center py-2">Loading…</div>}
    </div>
  );
}
