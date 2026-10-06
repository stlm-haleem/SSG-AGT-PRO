import type { ApiErrorBody } from "@/types/api";

const API = "/api";

function authHeaders(token: string | null, extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

function detailOf(body: ApiErrorBody): string {
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) return "Invalid request";
  return "";
}

async function parseError(res: Response, fallback: string): Promise<Error> {
  const body: ApiErrorBody = await res.json().catch(() => ({}));
  return new Error(detailOf(body) || res.statusText || fallback);
}

export async function apiFetch<T>(path: string, token: string | null, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(API + path, { ...opts, headers: authHeaders(token, opts.headers) });
  if (res.status === 401) {
    localStorage.removeItem("ssg_token");
    window.location.reload();
    throw new Error("Session expired");
  }
  if (!res.ok) throw await parseError(res, "Request failed");
  return res.json() as Promise<T>;
}

/** JSON body helper: apiSend("/x", token, "POST", {a: 1}) */
export function apiSend<T>(path: string, token: string | null, method: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, token, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export async function apiUpload<T>(path: string, token: string | null, file: File): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(API + path, { method: "POST", headers: authHeaders(token), body: fd });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(detailOf(body as ApiErrorBody) || "Import failed");
  return body as T;
}

export async function apiForm<T>(path: string, token: string | null, fd: FormData): Promise<T> {
  const res = await fetch(API + path, { method: "POST", headers: authHeaders(token), body: fd });
  if (res.status === 401) {
    localStorage.removeItem("ssg_token");
    window.location.reload();
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(detailOf(body as ApiErrorBody) || "Request failed");
  return body as T;
}

/** Download a server-generated file (xlsx exports / templates) with the auth header attached. */
export async function apiDownload(path: string, token: string | null, fallbackName = "export.xlsx"): Promise<void> {
  const res = await fetch(API + path, { headers: authHeaders(token) });
  if (!res.ok) throw await parseError(res, "Download failed");
  const cd = res.headers.get("content-disposition") || "";
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = m ? decodeURIComponent(m[1]) : fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Build "?a=1&b=x&b=y" from a params object; arrays repeat the key, empties are skipped. */
export function qs(params: Record<string, string | number | boolean | string[] | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    if (Array.isArray(v)) v.filter(Boolean).forEach((x) => sp.append(k, x));
    else sp.append(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}
