import { reactive } from "vue";

import { ApiError, post, request, type User } from "@/api/client";

// ponytail: a reactive module instead of a store library — the app has two pieces of global
// state (session, toasts). Reach for Pinia if shared state grows beyond that.
export const session = reactive<{ user: User | null; checked: boolean }>({
  user: null,
  checked: false,
});

export async function loadSession(): Promise<User | null> {
  try {
    session.user = await request<User>("GET", "/auth/me", undefined, { probe: true });
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 401)) throw e;
    session.user = null;
  }
  session.checked = true;
  return session.user;
}

export async function signIn(username: string, password: string): Promise<User> {
  session.user = await post<User>("/auth/login", { username, password });
  return session.user;
}

export async function signOut(): Promise<void> {
  try {
    await post("/auth/logout");
  } finally {
    session.user = null;
  }
}
