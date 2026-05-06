import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  copyProduct,
  deleteProduct,
  getProduct,
  starProduct,
  unstarProduct,
} from "../../api/products";
import type { Product, ProductNutritionFact } from "../../api/types";
import { useAuth } from "../../auth/useAuth";
import { ErrorBanner } from "../../components/ErrorBanner";

export function ProductDetail() {
  const { id: idParam } = useParams();
  const id = Number(idParam);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const query = useQuery<Product>({
    queryKey: ["products", "detail", id],
    queryFn: () => getProduct(id),
    enabled: Number.isFinite(id),
  });

  const star = useMutation({
    mutationFn: () => {
      const isStarred = query.data?.starred_by_me ?? false;
      return isStarred ? unstarProduct(id) : starProduct(id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });

  const copy = useMutation({
    mutationFn: () => copyProduct(id),
    onSuccess: (newProduct) => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      navigate(`/products/${newProduct.id}`);
    },
  });

  const remove = useMutation({
    mutationFn: () => deleteProduct(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      navigate("/products");
    },
  });

  if (query.isLoading) return <div>Loading…</div>;
  if (query.error) return <ErrorBanner error={query.error} />;
  if (!query.data) return null;

  const product = query.data;
  const isOwner = user && product.created_by?.id === user.id;
  const weightFacts = product.nutrition_facts.filter(
    (f) => f.quantity_type === "weight",
  );
  const volumeFacts = product.nutrition_facts.filter(
    (f) => f.quantity_type === "volume",
  );

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex items-start gap-4 flex-wrap">
        {product.image_filename && (
          <img
            src={`/uploads/${product.image_filename}`}
            alt=""
            className="w-32 h-32 object-cover rounded border"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        )}
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold">{product.name}</h1>
          {product.created_by && (
            <div className="text-sm opacity-70">
              Created by {product.created_by.username}
            </div>
          )}
        </div>
      </div>

      <ErrorBanner error={copy.error || remove.error || star.error} />

      <div className="flex gap-2 flex-wrap">
        <button
          type="button"
          className={
            "btn btn-sm " +
            (product.starred_by_me ? "btn-warning" : "btn-outline")
          }
          onClick={() => star.mutate()}
          disabled={star.isPending}
        >
          {product.starred_by_me ? "Unstar" : "Star"}
        </button>
        {isOwner ? (
          <>
            <Link
              to={`/products/${product.id}/edit`}
              className="btn btn-sm btn-primary"
            >
              Edit
            </Link>
            <button
              type="button"
              className="btn btn-sm btn-error"
              onClick={() => {
                if (window.confirm("Delete this product?")) remove.mutate();
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

      <FactsSection title="Per 100 g" facts={weightFacts} />
      <FactsSection title="Per 100 ml" facts={volumeFacts} />
    </div>
  );
}

function FactsSection({
  title,
  facts,
}: {
  title: string;
  facts: ProductNutritionFact[];
}) {
  if (facts.length === 0) return null;
  return (
    <section>
      <h2 className="font-semibold mb-2">{title}</h2>
      <table className="table table-sm">
        <tbody>
          {facts.map((f) => (
            <tr key={`${f.nutrition_fact_id}-${f.quantity_type}`}>
              <td>{f.nutrition_fact_name}</td>
              <td className="text-right">
                {f.amount} {f.unit}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
