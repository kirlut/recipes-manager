import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { listNutritionFactTypes } from "../../api/nutritionFactTypes";
import {
  createProduct,
  getProduct,
  updateProduct,
} from "../../api/products";
import type {
  NutritionFactType,
  ProductNutritionFactWrite,
  QuantityType,
} from "../../api/types";
import { ErrorBanner } from "../../components/ErrorBanner";
import { ImageUpload } from "../../components/ImageUpload";

interface FactRow {
  nutrition_fact_id: number | "";
  amount: string;
}

function emptyRow(): FactRow {
  return { nutrition_fact_id: "", amount: "" };
}

export function ProductForm({ mode }: { mode: "create" | "edit" }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { id: idParam } = useParams();
  const id = mode === "edit" ? Number(idParam) : null;

  const [name, setName] = useState("");
  const [imageFilename, setImageFilename] = useState<string | null>(null);
  const [weightFacts, setWeightFacts] = useState<FactRow[]>([]);
  const [volumeFacts, setVolumeFacts] = useState<FactRow[]>([]);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const factTypes = useQuery({
    queryKey: ["nutrition-fact-types"],
    queryFn: () => listNutritionFactTypes(),
  });

  const existing = useQuery({
    queryKey: ["products", "detail", id],
    queryFn: () => getProduct(id as number),
    enabled: mode === "edit" && Number.isFinite(id),
  });

  useEffect(() => {
    if (mode !== "edit" || !existing.data) return;
    setName(existing.data.name);
    setImageFilename(existing.data.image_filename ?? null);
    setWeightFacts(
      existing.data.nutrition_facts
        .filter((f) => f.quantity_type === "weight")
        .map((f) => ({
          nutrition_fact_id: f.nutrition_fact_id,
          amount: String(f.amount),
        })),
    );
    setVolumeFacts(
      existing.data.nutrition_facts
        .filter((f) => f.quantity_type === "volume")
        .map((f) => ({
          nutrition_fact_id: f.nutrition_fact_id,
          amount: String(f.amount),
        })),
    );
  }, [mode, existing.data]);

  const saveMutation = useMutation({
    mutationFn: async (body: {
      name: string;
      image_filename: string | null;
      nutrition_facts: ProductNutritionFactWrite[];
    }) => {
      if (mode === "create") return createProduct(body);
      return updateProduct(id as number, body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      navigate("/products");
    },
    onError: (err) => setSubmitError(err),
  });

  function rowsToFacts(
    rows: FactRow[],
    quantityType: QuantityType,
  ): ProductNutritionFactWrite[] {
    return rows
      .filter((r) => r.nutrition_fact_id !== "" && r.amount !== "")
      .map((r) => ({
        nutrition_fact_id: Number(r.nutrition_fact_id),
        quantity_type: quantityType,
        amount: Number(r.amount),
      }));
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    setValidationError(null);
    const facts = [
      ...rowsToFacts(weightFacts, "weight"),
      ...rowsToFacts(volumeFacts, "volume"),
    ];
    if (facts.length === 0) {
      setValidationError("Add at least one nutrition fact.");
      return;
    }
    if (facts.some((f) => f.amount < 0)) {
      setValidationError("Amounts must be non-negative.");
      return;
    }
    const seen = new Set<string>();
    for (const f of facts) {
      const key = `${f.nutrition_fact_id}|${f.quantity_type}`;
      if (seen.has(key)) {
        setValidationError(
          "The same nutrition fact cannot appear twice for the same quantity type.",
        );
        return;
      }
      seen.add(key);
    }
    saveMutation.mutate({
      name: name.trim(),
      image_filename: imageFilename,
      nutrition_facts: facts,
    });
  }

  const factTypesList: NutritionFactType[] =
    factTypes.data?.items ?? [];

  return (
    <form className="space-y-4 max-w-2xl" onSubmit={onSubmit}>
      <h1 className="text-2xl font-bold">
        {mode === "create" ? "New Product" : "Edit Product"}
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

      <ImageUpload value={imageFilename} onChange={setImageFilename} />

      <FactSection
        title="Per 100 g (weight)"
        addLabel="Add weight fact"
        rows={weightFacts}
        setRows={setWeightFacts}
        factTypes={factTypesList}
      />
      <FactSection
        title="Per 100 ml (volume)"
        addLabel="Add volume fact"
        rows={volumeFacts}
        setRows={setVolumeFacts}
        factTypes={factTypesList}
      />

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

interface FactSectionProps {
  title: string;
  addLabel: string;
  rows: FactRow[];
  setRows: React.Dispatch<React.SetStateAction<FactRow[]>>;
  factTypes: NutritionFactType[];
}

function FactSection({
  title,
  addLabel,
  rows,
  setRows,
  factTypes,
}: FactSectionProps) {
  const factById = useMemo(() => {
    const m = new Map<number, NutritionFactType>();
    for (const ft of factTypes) m.set(ft.id, ft);
    return m;
  }, [factTypes]);

  function update(i: number, patch: Partial<FactRow>) {
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  function remove(i: number) {
    setRows((rs) => rs.filter((_, idx) => idx !== i));
  }

  return (
    <section className="border border-base-300 rounded p-3 space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">{title}</h2>
        <button
          type="button"
          className="btn btn-sm btn-outline"
          onClick={() => setRows((rs) => [...rs, emptyRow()])}
        >
          {addLabel}
        </button>
      </div>
      {rows.length === 0 && (
        <div className="text-sm opacity-70">No facts added.</div>
      )}
      {rows.map((row, i) => {
        const ft =
          row.nutrition_fact_id !== ""
            ? factById.get(Number(row.nutrition_fact_id))
            : undefined;
        return (
          <div
            key={i}
            className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2 items-end"
          >
            <label className="form-control">
              <span className="label-text mb-1">Nutrition fact</span>
              <select
                className="select select-bordered"
                value={row.nutrition_fact_id}
                onChange={(e) =>
                  update(i, {
                    nutrition_fact_id:
                      e.target.value === "" ? "" : Number(e.target.value),
                  })
                }
                required
              >
                <option value="">—</option>
                {factTypes.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-control">
              <span className="label-text mb-1">
                Amount{ft ? ` (${ft.unit})` : ""}
              </span>
              <input
                type="number"
                step="any"
                min="0"
                className="input input-bordered"
                value={row.amount}
                onChange={(e) => update(i, { amount: e.target.value })}
                required
              />
            </label>
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => remove(i)}
            >
              Remove
            </button>
          </div>
        );
      })}
    </section>
  );
}
