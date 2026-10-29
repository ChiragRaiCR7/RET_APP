import { inject, type InjectionKey, type Ref } from "vue";

import type { WorkspaceDetail } from "@/api/client";

export type WorkspaceCtx = {
  ws: Ref<WorkspaceDetail | null>;
  reload: () => Promise<void>;
  convert: (groups?: string[] | null) => Promise<void>;
  converting: Ref<{ progress: number; total: number } | null>;
};

export const WORKSPACE: InjectionKey<WorkspaceCtx> = Symbol("workspace");

export function useWorkspace(): WorkspaceCtx {
  const ctx = inject(WORKSPACE);
  if (!ctx) throw new Error("useWorkspace() outside WorkspaceView");
  return ctx;
}
