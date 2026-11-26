import type { BrowseResult, CollisionPolicy, Health, JobResult, JobStatus, Plan, PreviewRequest, SourceInfo } from "./types";

// The browser talks only to the loopback API; data never leaves the PC.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765";

const TOKEN_KEY = "pqcsv.sessionToken";

/** Start.bat opens the site with #token=... (a fragment is never sent to the web server). */
export function captureTokenFromHash(): void {
  if (typeof window === "undefined") return;
  const match = window.location.hash.match(/(?:^#|&)token=([^&]+)/);
  if (!match) return;
  window.localStorage.setItem(TOKEN_KEY, decodeURIComponent(match[1]));
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
}

export function getToken(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token.trim());
}

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      "backend_unreachable",
      "Cannot reach the converter on this PC. Double-click Start.bat and keep its window open.",
      0,
    );
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    if (res.status === 405 || (res.status === 404 && !detail?.code)) {
      // The endpoint does not exist: an older converter is still running.
      throw new ApiError(
        "converter_outdated",
        "The converter running on this PC is an older version. Close the converter window, then double-click Start.bat again.",
        res.status,
      );
    }
    throw new ApiError(
      detail?.code ?? "http_error",
      detail?.message ?? `The converter returned an error (HTTP ${res.status}).`,
      res.status,
    );
  }
  return data as T;
}

export const api = {
  health: () => request<Health>("GET", "/health"),
  /** Opens the native Windows dialog on this PC; resolves to null if the user cancels. */
  browse: (kind: "file" | "folder", initial_path?: string) =>
    request<BrowseResult>("POST", "/browse", { kind, initial_path: initial_path || null }),
  inspect: (source_path: string) => request<SourceInfo>("POST", "/inspect", { source_path }),
  preview: (req: PreviewRequest) => request<Plan>("POST", "/preview", req),
  createJob: (body: {
    preview_id: string;
    destination_dir: string;
    collision_policy: CollisionPolicy;
    acknowledge_oversize: boolean;
  }) => request<{ job_id: string; destination: string; warnings: string[] }>("POST", "/jobs", body),
  jobStatus: (id: string) => request<JobStatus>("GET", `/jobs/${encodeURIComponent(id)}`),
  cancelJob: (id: string) => request<JobStatus>("POST", `/jobs/${encodeURIComponent(id)}/cancel`),
  /** Opens a finished job's destination folder (Explorer) or _catalog.csv (default app) on this PC. */
  openOutput: (job_id: string, target: "folder" | "catalog") =>
    request<{ opened: string }>("POST", "/open", { job_id, target }),
  jobResult: (id: string) => request<JobResult>("GET", `/jobs/${encodeURIComponent(id)}/result`),
};
