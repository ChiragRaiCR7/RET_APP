import { reactive } from "vue";

import { ApiError } from "@/api/client";

export type Toast = { id: number; kind: "ok" | "bad" | "info"; text: string };
export const toasts = reactive<Toast[]>([]);
let seq = 0;
const MAX_VISIBLE = 3;

export function notify(text: string, kind: Toast["kind"] = "ok", ms = 4500): void {
  const id = ++seq;
  toasts.push({ id, kind, text });
  if (toasts.length > MAX_VISIBLE) toasts.splice(0, toasts.length - MAX_VISIBLE);
  setTimeout(() => dismiss(id), kind === "bad" ? ms * 2 : ms);
}

export function dismiss(id: number): void {
  const i = toasts.findIndex((t) => t.id === id);
  if (i >= 0) toasts.splice(i, 1);
}

/** Show any thrown error as a toast and return its message (for inline display too). */
export function fail(e: unknown, prefix?: string): string {
  const msg = e instanceof ApiError || e instanceof Error ? e.message : String(e);
  if (!(e instanceof ApiError && e.status === 401)) notify(prefix ? `${prefix}: ${msg}` : msg, "bad");
  return msg;
}
