import type { NutritionTotal } from "../../api/types";

interface NutritionTotalsTableProps {
  totals: NutritionTotal[];
}

export function NutritionTotalsTable({ totals }: NutritionTotalsTableProps) {
  if (totals.length === 0) return null;
  return (
    <section>
      <h2 className="font-semibold mb-2">Per serving</h2>
      <table className="table table-sm">
        <thead>
          <tr>
            <th>Nutrition</th>
            <th>Amount</th>
          </tr>
        </thead>
        <tbody>
          {totals.map((t) => (
            <tr key={t.nutrition_fact_id}>
              <td>{t.nutrition_fact_name}</td>
              <td>
                {t.amount} {t.unit}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
