// Thin API client. Cookies carry the session; the custom header satisfies the backend's CSRF check.

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api/v1";

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { "X-PivotPilot-Client": "web", ...(init.headers as Record<string, string>) };
  let body = init.body;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  let res: Response;
  try {
    res = await fetch(BASE + path, { ...init, body, headers, credentials: "include" });
  } catch {
    throw new ApiError(0, "NETWORK", "Cannot reach the PivotPilot server. Is the backend running?");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const d = data?.detail;
    if (d && typeof d === "object") throw new ApiError(res.status, d.code ?? "ERROR", d.message ?? "Request failed", d);
    throw new ApiError(res.status, "ERROR", typeof d === "string" ? d : `Request failed (${res.status})`);
  }
  return data as T;
}

export const post = <T,>(path: string, json?: unknown) => api<T>(path, { method: "POST", json: json ?? {} });
export const patch = <T,>(path: string, json: unknown) => api<T>(path, { method: "PATCH", json });
export const put = <T,>(path: string, json: unknown) => api<T>(path, { method: "PUT", json });
export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });

export function upload<T>(path: string, file: File): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  return api<T>(path, { method: "POST", body: fd });
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const errs = (e.details as { errors?: { field: string; message: string }[] })?.errors;
    if (errs?.length) return errs.map((x) => `${x.field ? x.field + ": " : ""}${x.message}`).join(" · ");
    const missing = (e.details as { missing?: string[] })?.missing;
    return missing?.length ? `${e.message} (${missing.join(", ")})` : e.message;
  }
  return e instanceof Error ? e.message : "Something went wrong.";
}
