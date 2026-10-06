import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Builds to dist/ with the default /assets/... hashed filenames, which the
// FastAPI backend serves directly (see backend/app.py) — no separate Node
// server needed at runtime, just `npm run build` once.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      // so `npm run dev` also works against the FastAPI backend directly
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
