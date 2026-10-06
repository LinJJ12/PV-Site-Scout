/* 路由：大屏三个视图各自独立网址。
   大屏为纯展示项目、通常静态托管且无 SEO 需求，
   采用 hash 模式免服务器 fallback 配置（深链接刷新不 404）。 */

import { createRouter, createWebHashHistory } from "vue-router";

const APP_TITLE = "光伏电站智能选址数据可视化大屏";

const routes = [
  { path: "/", redirect: "/dashboard" },
  {
    path: "/dashboard",
    name: "dashboard",
    component: () => import("@/views/DashboardView.vue"),
    meta: { title: "选址态势" }
  },
  {
    path: "/resource",
    name: "resource",
    component: () => import("@/views/ResourceProfitView.vue"),
    meta: { title: "资源收益评估" }
  },
  {
    path: "/realtime",
    name: "realtime",
    component: () => import("@/views/RealtimeView.vue"),
    meta: { title: "实时选址" }
  },
  { path: "/:pathMatch(.*)*", redirect: "/dashboard" }
];

const router = createRouter({
  history: createWebHashHistory(),
  routes
});

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · ${APP_TITLE}` : APP_TITLE;
});

export default router;
