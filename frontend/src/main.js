import { createApp } from "vue";

import App from "./App.vue";
import router from "./router";
import "./styles/tokens.css";
import "./styles.css";
import "./theme/bigscreen.js";

createApp(App).use(router).mount("#app");
