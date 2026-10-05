import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  build: {
    // 三维地图与图表库体积较大，拆分为独立 chunk 以利用浏览器缓存、缩短首屏时间
    rollupOptions: {
      output: {
        manualChunks: {
          three: ["three", "gsap", "d3-geo"],
          echarts: ["echarts"],
          vue: ["vue"]
        }
      }
    }
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true
      }
    }
  }
});
