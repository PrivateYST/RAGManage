import { createApp } from "vue";
import { createPinia } from "pinia";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import EnvironmentPage from "./pages/EnvironmentPage.vue";
import "./style.css";

const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: "/", component: EnvironmentPage }],
});
createApp(App).use(createPinia()).use(router).mount("#app");
