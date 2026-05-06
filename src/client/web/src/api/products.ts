import { apiFetch } from "./client";
import type {
  ListScope,
  Page,
  Product,
  ProductListItem,
  ProductWrite,
} from "./types";

export interface ProductListParams {
  scope: ListScope;
  q?: string;
  cursor?: string;
  limit?: number;
}

export function listProducts(
  params: ProductListParams,
): Promise<Page<ProductListItem>> {
  const qs = new URLSearchParams();
  qs.set("scope", params.scope);
  if (params.q) qs.set("q", params.q);
  if (params.cursor) qs.set("cursor", params.cursor);
  if (params.limit) qs.set("limit", String(params.limit));
  return apiFetch<Page<ProductListItem>>(`/products?${qs.toString()}`);
}

export function getProduct(id: number): Promise<Product> {
  return apiFetch<Product>(`/products/${id}`);
}

export function createProduct(body: ProductWrite): Promise<Product> {
  return apiFetch<Product>("/products", { method: "POST", body });
}

export function updateProduct(id: number, body: ProductWrite): Promise<Product> {
  return apiFetch<Product>(`/products/${id}`, { method: "PUT", body });
}

export function deleteProduct(id: number): Promise<void> {
  return apiFetch<void>(`/products/${id}`, { method: "DELETE" });
}

export function copyProduct(id: number): Promise<Product> {
  return apiFetch<Product>(`/products/${id}/copy`, { method: "POST", body: {} });
}

export function starProduct(id: number): Promise<void> {
  return apiFetch<void>(`/products/${id}/star`, { method: "PUT" });
}

export function unstarProduct(id: number): Promise<void> {
  return apiFetch<void>(`/products/${id}/star`, { method: "DELETE" });
}
