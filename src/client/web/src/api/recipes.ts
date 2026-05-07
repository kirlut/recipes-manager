import { apiFetch } from "./client";
import type {
  ListScope,
  Page,
  Recipe,
  RecipeListItem,
  RecipeWrite,
} from "./types";

export interface RecipeListParams {
  scope: ListScope;
  q?: string;
  cursor?: string;
  limit?: number;
}

export function listRecipes(
  params: RecipeListParams,
): Promise<Page<RecipeListItem>> {
  const qs = new URLSearchParams();
  qs.set("scope", params.scope);
  if (params.q) qs.set("q", params.q);
  if (params.cursor) qs.set("cursor", params.cursor);
  if (params.limit) qs.set("limit", String(params.limit));
  return apiFetch<Page<RecipeListItem>>(`/recipes?${qs.toString()}`);
}

export function getRecipe(id: number): Promise<Recipe> {
  return apiFetch<Recipe>(`/recipes/${id}`);
}

export function createRecipe(body: RecipeWrite): Promise<Recipe> {
  return apiFetch<Recipe>("/recipes", { method: "POST", body });
}

export function updateRecipe(id: number, body: RecipeWrite): Promise<Recipe> {
  return apiFetch<Recipe>(`/recipes/${id}`, { method: "PUT", body });
}

export function deleteRecipe(id: number): Promise<void> {
  return apiFetch<void>(`/recipes/${id}`, { method: "DELETE" });
}

export function copyRecipe(id: number): Promise<Recipe> {
  return apiFetch<Recipe>(`/recipes/${id}/copy`, { method: "POST", body: {} });
}

export function starRecipe(id: number): Promise<void> {
  return apiFetch<void>(`/recipes/${id}/star`, { method: "PUT" });
}

export function unstarRecipe(id: number): Promise<void> {
  return apiFetch<void>(`/recipes/${id}/star`, { method: "DELETE" });
}
