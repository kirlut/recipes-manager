import type { ProblemDetail } from "./types";

export const TOKEN_KEY = "auth_token";
export const UNAUTHORIZED_EVENT = "recipes-manager:unauthorized";

export class ApiError extends Error {
  problem: ProblemDetail;
  status: number;

  constructor(problem: ProblemDetail) {
    super(problem.title || `HTTP ${problem.status}`);
    this.problem = problem;
    this.status = problem.status;
  }
}

export function getToken(): string | null {
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

interface RequestOpts {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  rawBody?: BodyInit;
}

async function parseProblem(res: Response): Promise<ProblemDetail> {
  try {
    const data = await res.json();
    return {
      type: data?.type ?? "about:blank",
      title: data?.title ?? `HTTP ${res.status}`,
      status: data?.status ?? res.status,
      detail: data?.detail,
      instance: data?.instance,
      extensions: data?.extensions,
    };
  } catch {
    return {
      type: "about:blank",
      title: res.statusText || `HTTP ${res.status}`,
      status: res.status,
    };
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  opts: RequestOpts = {},
): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  const token = getToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let body: BodyInit | undefined = opts.rawBody;
  if (body === undefined && opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  const res = await fetch(`/api${path}`, {
    method: opts.method ?? "GET",
    headers,
    body,
  });

  if (res.status === 401) {
    clearToken();
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
    throw new ApiError(await parseProblem(res));
  }

  if (!res.ok) {
    throw new ApiError(await parseProblem(res));
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const ct = res.headers.get("Content-Type") ?? "";
  if (ct.includes("application/json")) {
    return (await res.json()) as T;
  }
  return undefined as T;
}
