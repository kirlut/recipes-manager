import { apiFetch } from "./client";
import type {
  ShoppingListRequestItem,
  ShoppingListResponse,
} from "./types";

export function computeShoppingList(
  items: ShoppingListRequestItem[],
): Promise<ShoppingListResponse> {
  return apiFetch<ShoppingListResponse>("/shopping-list", {
    method: "POST",
    body: { items },
  });
}
