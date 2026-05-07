import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  copyRecipe,
  deleteRecipe,
  getRecipe,
  starRecipe,
  unstarRecipe,
} from "../../api/recipes";
import type { Recipe } from "../../api/types";
import { useAuth } from "../../auth/useAuth";
import { ErrorBanner } from "../../components/ErrorBanner";
import { NutritionTotalsTable } from "./NutritionTotalsTable";

export function RecipeDetail() {
  const { id: idParam } = useParams();
  const id = Number(idParam);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const query = useQuery<Recipe>({
    queryKey: ["recipes", "detail", id],
    queryFn: () => getRecipe(id),
    enabled: Number.isFinite(id),
  });

  const star = useMutation({
    mutationFn: () => {
      const isStarred = query.data?.starred_by_me ?? false;
      return isStarred ? unstarRecipe(id) : starRecipe(id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recipes"] });
    },
  });

  const copy = useMutation({
    mutationFn: () => copyRecipe(id),
    onSuccess: (newRecipe) => {
      queryClient.invalidateQueries({ queryKey: ["recipes"] });
      navigate(`/recipes/${newRecipe.id}`);
    },
  });

  const remove = useMutation({
    mutationFn: () => deleteRecipe(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recipes"] });
      navigate("/recipes");
    },
  });

  if (query.isLoading) return <div>Loading…</div>;
  if (query.error) return <ErrorBanner error={query.error} />;
  if (!query.data) return null;

  const recipe = query.data;
  const isOwner = Boolean(user && recipe.created_by?.id === user.id);

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex items-start gap-4 flex-wrap">
        {recipe.image_filename && (
          <img
            src={`/uploads/${recipe.image_filename}`}
            alt=""
            className="w-32 h-32 object-cover rounded border"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        )}
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold">{recipe.name}</h1>
          {recipe.created_by && (
            <div className="text-sm opacity-70">
              Created by {recipe.created_by.username}
            </div>
          )}
        </div>
      </div>

      {recipe.description && (
        <p className="whitespace-pre-wrap">{recipe.description}</p>
      )}

      <ErrorBanner error={copy.error || remove.error || star.error} />

      <div className="flex gap-2 flex-wrap">
        <button
          type="button"
          className={
            "btn btn-sm " +
            (recipe.starred_by_me ? "btn-warning" : "btn-outline")
          }
          onClick={() => star.mutate()}
          disabled={star.isPending}
        >
          {recipe.starred_by_me ? "Unstar" : "Star"}
        </button>
        {isOwner ? (
          <>
            <Link
              to={`/recipes/${recipe.id}/edit`}
              className="btn btn-sm btn-primary"
            >
              Edit
            </Link>
            <button
              type="button"
              className="btn btn-sm btn-error"
              onClick={() => {
                if (window.confirm("Delete this recipe?")) remove.mutate();
              }}
              disabled={remove.isPending}
            >
              Delete
            </button>
          </>
        ) : (
          <button
            type="button"
            className="btn btn-sm btn-primary"
            onClick={() => copy.mutate()}
            disabled={copy.isPending}
          >
            Copy
          </button>
        )}
      </div>

      <section>
        <h2 className="font-semibold mb-2">Products</h2>
        {recipe.products.length === 0 ? (
          <div className="opacity-70 italic">No products.</div>
        ) : (
          <ul className="list-disc pl-6 space-y-1">
            {recipe.products.map((p) => (
              <li key={`${p.product_id}-${p.quantity_type}`}>
                <Link
                  to={`/products/${p.product_id}`}
                  className="hover:underline"
                >
                  {p.product_name}
                </Link>
                {" — "}
                {p.quantity_type}
                {" — "}
                {p.amount} {p.quantity_type === "weight" ? "g" : "ml"}
              </li>
            ))}
          </ul>
        )}
      </section>

      <NutritionTotalsTable totals={recipe.nutrition_totals_per_serving} />
    </div>
  );
}
