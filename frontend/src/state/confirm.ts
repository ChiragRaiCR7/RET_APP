import { reactive } from "vue";

export type ConfirmRequest = {
  title: string;
  body: string;
  action: string;
  danger?: boolean;
  resolve: (ok: boolean) => void;
};

export const confirmState = reactive<{ current: ConfirmRequest | null }>({ current: null });

/** Ask for confirmation with the app's native <dialog>. Resolves false on cancel or Esc. */
export function confirm(opts: Omit<ConfirmRequest, "resolve">): Promise<boolean> {
  return new Promise((resolve) => {
    confirmState.current = { ...opts, resolve };
  });
}
