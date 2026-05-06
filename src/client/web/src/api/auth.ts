import { apiFetch } from "./client";
import type { LoginResponse, User } from "./types";

export interface RegisterBody {
  username: string;
  password: string;
  full_name?: string | null;
}

export function register(body: RegisterBody): Promise<User> {
  return apiFetch<User>("/auth/register", { method: "POST", body });
}

export function login(username: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>("/auth/login", {
    method: "POST",
    body: { username, password },
  });
}

export function getMe(): Promise<User> {
  return apiFetch<User>("/auth/me");
}
