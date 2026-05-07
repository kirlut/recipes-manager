import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { listRecipes } from "../../api/recipes";
import { computeShoppingList } from "../../api/shoppingList";
import type {
  RecipeListItem,
  ShoppingListResponse,
} from "../../api/types";
import { ErrorBanner } from "../../components/ErrorBanner";

interface Selection {
  recipe: RecipeListItem;
  servings: string;
}

export function ShoppingListPage() {
  const [selections, setSelections] = useState<Selection[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [result, setResult] = useState<ShoppingListResponse | null>(null);

  const mineQuery = useQuery({
    queryKey: ["recipes", "list", "mine", ""],
    queryFn: () => listRecipes({ scope: "mine", limit: 100 }),
    enabled: pickerOpen,
  });
  const starredQuery = useQuery({
    queryKey: ["recipes", "list", "starred", ""],
    queryFn: () => listRecipes({ scope: "starred", limit: 100 }),
    enabled: pickerOpen,
  });

  const compute = useMutation({
    mutationFn: () =>
      computeShoppingList(
        selections.map((s) => ({
          recipe_id: s.recipe.id,
          servings: Number(s.servings),
        })),
      ),
    onSuccess: (res) => setResult(res),
  });

  function addRecipe(recipe: RecipeListItem) {
    setSelections((prev) => [...prev, { recipe, servings: "1" }]);
    setPickerOpen(false);
  }

  function setServings(idx: number, value: string) {
    setSelections((prev) =>
      prev.map((s, i) => (i === idx ? { ...s, servings: value } : s)),
    );
  }

  function removeSelection(idx: number) {
    setSelections((prev) => prev.filter((_, i) => i !== idx));
  }

  const recipeOptions: RecipeListItem[] = (() => {
    const seen = new Set<number>();
    const out: RecipeListItem[] = [];
    for (const r of mineQuery.data?.items ?? []) {
      if (!seen.has(r.id)) {
        seen.add(r.id);
        out.push(r);
      }
    }
    for (const r of starredQuery.data?.items ?? []) {
      if (!seen.has(r.id)) {
        seen.add(r.id);
        out.push(r);
      }
    }
    out.sort((a, b) => a.id - b.id);
    return out;
  })();
  const alreadyChosen = new Set(selections.map((s) => s.recipe.id));
  const recipesLoading =
    (mineQuery.isFetching && !mineQuery.data) ||
    (starredQuery.isFetching && !starredQuery.data);
  const recipesError = mineQuery.error ?? starredQuery.error;

  return (
    <div className="space-y-4 max-w-3xl">
      <h1 className="text-2xl font-bold">Shopping List</h1>

      <ErrorBanner error={compute.error} />

      <section className="space-y-2">
        <h2 className="font-semibold">Selected recipes</h2>
        {selections.length === 0 && (
          <div className="opacity-70 italic">No recipes selected.</div>
        )}
        <ul className="space-y-2">
          {selections.map((s, idx) => (
            <li
              key={s.recipe.id}
              className="flex items-center gap-3 flex-wrap border border-base-300 rounded p-2"
            >
              <span className="font-medium flex-1 min-w-0 truncate">
                {s.recipe.name}
              </span>
              <label className="form-control">
                <span className="label-text mb-1">Servings</span>
                <input
                  type="number"
                  step="any"
                  min="0.1"
                  className="input input-bordered input-sm w-24"
                  value={s.servings}
                  onChange={(e) => setServings(idx, e.target.value)}
                />
              </label>
              <button
                type="button"
                className="btn btn-xs btn-ghost"
                onClick={() => removeSelection(idx)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>

        <button
          type="button"
          className="btn btn-sm btn-outline"
          onClick={() => setPickerOpen((v) => !v)}
        >
          Add recipe
        </button>

        {pickerOpen && (
          <div className="border border-base-300 rounded p-3 bg-base-100 space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">Pick a recipe</h3>
              <button
                type="button"
                className="btn btn-xs btn-ghost"
                onClick={() => setPickerOpen(false)}
              >
                Close
              </button>
            </div>
            <ErrorBanner error={recipesError} />
            {recipesLoading && (
              <div className="text-sm opacity-70">Loading…</div>
            )}
            {recipeOptions.length === 0 && !recipesLoading && (
              <div className="text-sm opacity-70">No recipes available.</div>
            )}
            <ul className="divide-y divide-base-300 max-h-64 overflow-auto">
              {recipeOptions
                .filter((r) => !alreadyChosen.has(r.id))
                .map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      className="w-full text-left px-2 py-1 hover:bg-base-200"
                      onClick={() => addRecipe(r)}
                    >
                      {r.name}
                    </button>
                  </li>
                ))}
            </ul>
          </div>
        )}
      </section>

      <div>
        <button
          type="button"
          className="btn btn-primary"
          disabled={selections.length === 0 || compute.isPending}
          onClick={() => compute.mutate()}
        >
          Compute
        </button>
      </div>

      {result && (
        <section>
          <h2 className="font-semibold mb-2">Shopping list</h2>
          {result.items.length === 0 ? (
            <div className="opacity-70 italic">Nothing to buy.</div>
          ) : (
            <table className="table table-sm">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Type</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((it) => (
                  <tr key={`${it.product_id}-${it.quantity_type}`}>
                    <td>{it.product_name}</td>
                    <td>{it.quantity_type}</td>
                    <td>
                      {it.total_amount} {it.unit}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
}
