import { apiFetch } from "./client";
import type { UploadResponse } from "./types";

export function uploadImage(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<UploadResponse>("/uploads/images", {
    method: "POST",
    rawBody: form,
  });
}
