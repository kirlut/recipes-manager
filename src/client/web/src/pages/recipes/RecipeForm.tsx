import { useEffect, useState, type FormEvent } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import {
  createRecipe,
  getRecipe,
  updateRecipe,
} from "../../api/recipes";
import type {
  Product,
  QuantityType,
  RecipeProductWrite,
} from "../../api/types";
import { ErrorBanner } from "../../components/ErrorBanner";
import { ImageUpload } from "../../components/ImageUpload";
import { ProductPicker } from "../../components/ProductPicker";

interface RowState {
  productId: number | null;
  productName: string | null;
  supportedQtyTypes: QuantityType[] | null;
  quantityType: QuantityType | null;
  amount: string;
}

function emptyRow(): RowState {
  return {
    productId: null,
    productName: null,
    supportedQtyTypes: null,
    quantityType: null,
    amount: "",
  };
}

function supportedTypesOf(product: Product): QuantityType[] {
  const set = new Set<QuantityType>();
  for (const f of product.nutrition_facts) set.add(f.quantity_type);
  return Array.from(set);
}

export function RecipeForm({ mode }: { mode: "create" | "edit" }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { id: idParam } = useParams();
  const id = mode === "edit" ? Number(idParam) : null;

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [imageFilename, setImageFilename] = useState<string | null>(null);
  const [rows, setRows] = useState<RowState[]>([]);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const existing = useQuery({
    queryKey: ["recipes", "detail", id],
    queryFn: () => getRecipe(id as number),
    enabled: mode === "edit" && Number.isFinite(id),
  });

  useEffect(() => {
    if (mode !== "edit" || !existing.data) return;
    const r = existing.data;
    setName(r.name);
    setDescription(r.description ?? "");
    setImageFilename(r.image_filename ?? null);
    const sorted = [...r.products].sort((a, b) =>
      a.product_name.localeCompare(b.product_name),
    );
    setRows(
      sorted.map((p) => ({
        productId: p.product_id,
        productName: p.product_name,
        supportedQtyTypes: null,
        quantityType: p.quantity_type,
        amount: String(p.amount),
      })),
    );
    setEditingIndex(null);
  }, [mode, existing.data]);

  const saveMutation = useMutation({
    mutationFn: async (body: {
      name: string;
      description: string | null;
      image_filename: string | null;
      products: RecipeProductWrite[];
    }) => {
      if (mode === "create") return createRecipe(body);
      return updateRecipe(id as number, body);
    },
    onSuccess: (recipe) => {
      queryClient.invalidateQueries({ queryKey: ["recipes"] });
      navigate(`/recipes/${recipe.id}`);
    },
    onError: (err) => setSubmitError(err),
  });

  function patchRow(i: number, patch: Partial<RowState>) {
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  function handleAddProduct() {
    setValidationError(null);
    setRows((rs) => {
      const next = [...rs, emptyRow()];
      setEditingIndex(next.length - 1);
      return next;
    });
  }

  function handlePickProduct(rowIndex: number, product: Product) {
    const supported = supportedTypesOf(product);
    patchRow(rowIndex, {
      productId: product.id,
      productName: product.name,
      supportedQtyTypes: supported,
      quantityType: supported.length === 1 ? supported[0] : null,
    });
  }

  function unitFor(qty: QuantityType): string {
    return qty === "weight" ? "g" : "ml";
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    setValidationError(null);

    const trimmedName = name.trim();
    if (!trimmedName) {
      setValidationError("Name is required.");
      return;
    }

    const products: RecipeProductWrite[] = [];
    const seen = new Set<number>();
    for (const r of rows) {
      if (
        r.productId === null ||
        r.quantityType === null ||
        r.amount === ""
      ) {
        continue;
      }
      const amountNum = Number(r.amount);
      if (!Number.isFinite(amountNum) || amountNum <= 0) {
        setValidationError("Each product amount must be a positive number.");
        return;
      }
      if (seen.has(r.productId)) {
        setValidationError(
          "The same product cannot appear twice in a recipe.",
        );
        return;
      }
      seen.add(r.productId);
      products.push({
        product_id: r.productId,
        quantity_type: r.quantityType,
        amount: amountNum,
      });
    }

    saveMutation.mutate({
      name: trimmedName,
      description: description.trim() ? description.trim() : null,
      image_filename: imageFilename,
      products,
    });
  }

  return (
    <form className="space-y-4 max-w-2xl" onSubmit={onSubmit}>
      <h1 className="text-2xl font-bold">
        {mode === "create" ? "New Recipe" : "Edit Recipe"}
      </h1>

      <ErrorBanner error={submitError} />
      {validationError && (
        <div role="alert" className="alert alert-warning">
          {validationError}
        </div>
      )}

      <label className="form-control">
        <span className="label-text mb-1">Name</span>
        <input
          type="text"
          className="input input-bordered"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </label>

      <label className="form-control">
        <span className="label-text mb-1">Description</span>
        <textarea
          className="textarea textarea-bordered"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
        />
      </label>

      <ImageUpload value={imageFilename} onChange={setImageFilename} />

      <section className="border border-base-300 rounded p-3 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Products</h2>
          <button
            type="button"
            className="btn btn-sm btn-outline"
            onClick={handleAddProduct}
          >
            Add product
          </button>
        </div>

        {rows.length === 0 && (
          <div className="text-sm opacity-70">No products added.</div>
        )}

        <ul className="space-y-3">
          {rows.map((row, i) => {
            const isEditing = i === editingIndex;
            if (!isEditing) {
              if (row.productId === null) return null;
              return (
                <li
                  key={i}
                  className="flex items-center justify-between gap-2 text-sm"
                >
                  <span>
                    {row.productName} — {row.quantityType} — {row.amount}{" "}
                    {row.quantityType ? unitFor(row.quantityType) : ""}
                  </span>
                  <button
                    type="button"
                    className="btn btn-xs btn-ghost"
                    onClick={() =>
                      setRows((rs) => rs.filter((_, idx) => idx !== i))
                    }
                  >
                    Remove
                  </button>
                </li>
              );
            }
            return (
              <li
                key={i}
                className="border border-base-200 rounded p-3 space-y-2 bg-base-100"
              >
                {row.productId === null ? (
                  <ProductPicker
                    onSelect={(product) => handlePickProduct(i, product)}
                  />
                ) : (
                  <>
                    <div className="font-medium">{row.productName}</div>
                    <fieldset className="space-y-1">
                      <legend className="text-sm opacity-70 mb-1">
                        Quantity type
                      </legend>
                      <div className="flex gap-4">
                        {(["weight", "volume"] as QuantityType[])
                          .filter(
                            (q) =>
                              row.supportedQtyTypes === null ||
                              row.supportedQtyTypes.includes(q),
                          )
                          .map((q) => (
                            <label
                              key={q}
                              className="flex items-center gap-2 cursor-pointer"
                            >
                              <input
                                type="radio"
                                name={`qty-${i}`}
                                aria-label={q}
                                className="radio radio-sm"
                                checked={row.quantityType === q}
                                onChange={() =>
                                  patchRow(i, { quantityType: q })
                                }
                              />
                              <span className="text-sm">
                                {q} ({unitFor(q)})
                              </span>
                            </label>
                          ))}
                      </div>
                    </fieldset>
                    <label className="form-control">
                      <span className="label-text mb-1">Amount</span>
                      <input
                        type="number"
                        step="any"
                        min="0"
                        className="input input-bordered"
                        value={row.amount}
                        onChange={(e) =>
                          patchRow(i, { amount: e.target.value })
                        }
                      />
                    </label>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="btn btn-xs btn-ghost"
                        onClick={() => {
                          setRows((rs) => rs.filter((_, idx) => idx !== i));
                          setEditingIndex(null);
                        }}
                      >
                        Remove
                      </button>
                    </div>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      <div className="flex gap-2 pt-2">
        <button
          type="submit"
          className="btn btn-primary"
          disabled={saveMutation.isPending}
        >
          Save
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => navigate(-1)}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
