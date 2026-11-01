import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

import { loadSession, session } from "@/state/session";

declare module "vue-router" {
  interface RouteMeta {
    public?: boolean;
    admin?: boolean;
    title?: string;
  }
}

const routes: RouteRecordRaw[] = [
  { path: "/login", name: "login", component: () => import("@/views/LoginView.vue"),
    meta: { public: true, title: "Sign in" } },
  { path: "/", name: "home", component: () => import("@/views/HomeView.vue"),
    meta: { title: "Workspaces" } },
  {
    path: "/w/:id",
    component: () => import("@/views/WorkspaceView.vue"),
    props: true,
    children: [
      { path: "", redirect: (to) => ({ name: "files", params: to.params }) },
      { path: "files", name: "files", component: () => import("@/views/ws/FilesTab.vue") },
      { path: "data", name: "data", component: () => import("@/views/ws/DataTab.vue") },
      { path: "structure", name: "structure", component: () => import("@/views/ws/StructureTab.vue") },
      { path: "ask", name: "ask", component: () => import("@/views/ws/AskTab.vue") },
    ],
  },
  { path: "/compare", name: "compare", component: () => import("@/views/CompareView.vue"),
    meta: { title: "Compare" } },
  { path: "/compare/:id", name: "comparison", component: () => import("@/views/ComparisonView.vue"),
    props: true, meta: { title: "Comparison" } },
  { path: "/admin", name: "admin", component: () => import("@/views/AdminView.vue"),
    meta: { admin: true, title: "Administration" } },
  { path: "/account", name: "account", component: () => import("@/views/AccountView.vue"),
    meta: { title: "Account" } },
  { path: "/:rest(.*)*", name: "missing", component: () => import("@/views/NotFoundView.vue"),
    meta: { title: "Not found" } },
];

export const router = createRouter({ history: createWebHistory(), routes });

router.beforeEach(async (to) => {
  if (!session.checked) await loadSession();
  if (to.meta.public) return session.user && to.name === "login" ? { name: "home" } : true;
  if (!session.user) return { name: "login", query: { next: to.fullPath } };
  if (to.meta.admin && session.user.role !== "admin") return { name: "home" };
  return true;
});

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · RET` : "RET";
});
