// Typed API client. Shapes come from the backend's OpenAPI schema (npm run gen:api).
import type { components } from "./schema";

type S = components["schemas"];
export type User = S["UserOut"];
export type Workspace = S["WorkspaceOut"];
export type WorkspaceDetail = S["WorkspaceDetail"];
export type SourceFile = S["SourceFileOut"];
export type Dataset = S["DatasetOut"];
export type DatasetPage = S["DatasetPage"];
export type ColumnInfo = S["ColumnInfo"];
export type GroupSummary = S["GroupSummary"];
export type Job = S["JobOut"];
export type EditIn = S["EditIn"];
export type Structure = S["StructureOut"];
export type StructureNode = S["StructureNode"];
export type Comparison = S["ComparisonOut"];
export type ComparisonDetail = S["ComparisonDetail"];
export type ComparisonItem = S["ComparisonItemOut"];
export type Diff = S["DiffOut"];
export type DiffRow = S["DiffRow"];
export type AIStatus = S["AIStatus"];
export type Citation = S["Citation"];
export type ChatMessage = S["ChatMessageOut"];
export type AdminStats = S["AdminStats"];
export type AuditEvent = S["AuditEventOut"];
export type ResetRequest = S["ResetRequestOut"];
export type ResetToken = S["ResetTokenOut"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Called on any 401 except the session probe, so the app can return to sign-in. */
let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn;
}

async function errorFrom(res: Response): Promise<ApiError> {
  let detail = res.statusText || `Request failed (${res.status})`;
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    /* non-JSON error body: keep the status text */
  }
  return new ApiError(res.status, detail);
}

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  opts: { probe?: boolean; signal?: AbortSignal } = {},
): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: opts.signal,
  });
  if (!res.ok) {
    if (res.status === 401 && !opts.probe) onUnauthorized();
    throw await errorFrom(res);
  }
  return (await res.json()) as T;
}

export const get = <T>(path: string, signal?: AbortSignal) =>
  request<T>("GET", path, undefined, { signal });
export const post = <T>(path: string, body: unknown = {}) => request<T>("POST", path, body);
export const patch = <T>(path: string, body: unknown) => request<T>("PATCH", path, body);
export const del = <T>(path: string) => request<T>("DELETE", path);

export function query(params: Record<string, string | number | boolean | undefined | null>) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** Upload a file as the raw request body. XHR (not fetch) because it reports upload progress. */
export function uploadWorkspace(
  file: File,
  onProgress: (fraction: number) => void,
): { promise: Promise<WorkspaceDetail>; abort: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<WorkspaceDetail>((resolve, reject) => {
    xhr.open("POST", `/api/workspaces${query({ filename: file.name })}`);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let detail = `Upload failed (${xhr.status})`;
      try {
        const body = JSON.parse(xhr.responseText) as { detail?: string };
        if (xhr.status >= 200 && xhr.status < 300) return resolve(body as WorkspaceDetail);
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        /* keep generic message */
      }
      if (xhr.status === 401) onUnauthorized();
      reject(new ApiError(xhr.status, detail));
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload."));
    xhr.onabort = () => reject(new ApiError(0, "Upload cancelled."));
    xhr.send(file);
  });
  return { promise, abort: () => xhr.abort() };
}

/** Poll a job until it leaves queued/running. Calls onUpdate on every poll. */
export async function waitForJob(
  jobId: string,
  onUpdate: (job: Job) => void,
  signal?: AbortSignal,
): Promise<Job> {
  let delay = 400;
  for (;;) {
    const job = await get<Job>(`/jobs/${jobId}`, signal);
    onUpdate(job);
    if (job.status === "succeeded" || job.status === "failed") return job;
    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(delay * 1.5, 2500);
  }
}

export type ChatEvent =
  | { event: "citations"; data: Citation[] }
  | { event: "token"; data: string }
  | { event: "done"; data: { id: number; mode: string } }
  | { event: "error"; data: { message: string } };

/** POST a question and yield server-sent events as they arrive. */
export async function* chatStream(
  workspaceId: string,
  question: string,
  signal: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`/api/workspaces/${workspaceId}/ai/chat`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!res.ok || !res.body) {
    if (res.status === 401) onUnauthorized();
    throw await errorFrom(res);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      let event = "message";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      yield { event, data: JSON.parse(data) } as ChatEvent;
    }
  }
}
