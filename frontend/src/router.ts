import { createRouter, createWebHistory } from "vue-router";

import DashboardView from "./views/DashboardView.vue";
import LogsView from "./views/LogsView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "dashboard", component: DashboardView },
    { path: "/logs", name: "logs", component: LogsView },
  ],
});
