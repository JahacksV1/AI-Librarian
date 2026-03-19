import { defineConfig } from "vite";

export default defineConfig({
  envPrefix: "VITE_",
  server: {
    host: "0.0.0.0",
    port: 3000,
    proxy: {
      // Same-origin `/api/*` → FastAPI on 8000 (strip `/api`). See docs/FE_BE_INTEGRATION.md
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, "") || "/",
      },
    },
  },
});
