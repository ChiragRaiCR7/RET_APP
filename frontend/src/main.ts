import "./styles/app.css";

import { createApp } from "vue";

import { setUnauthorizedHandler } from "@/api/client";
import App from "@/App.vue";
import { router } from "@/router";
import { session } from "@/state/session";

setUnauthorizedHandler(() => {
  if (session.user === null) return;
  session.user = null;
  const next = router.currentRoute.value.fullPath;
  void router.replace({ name: "login", query: { next, expired: "1" } });
});

createApp(App).use(router).mount("#app");
