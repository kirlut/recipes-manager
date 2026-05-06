import { apiFetch } from "./client";
import type { NutritionFactType } from "./types";

export function listNutritionFactTypes(): Promise<{ items: NutritionFactType[] }> {
  return apiFetch<{ items: NutritionFactType[] }>("/nutrition-fact-types");
}
