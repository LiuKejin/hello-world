import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies API calls to the FastAPI backend so the browser only
// ever talks to a single origin (no CORS juggling during development).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
