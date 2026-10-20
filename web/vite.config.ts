import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "prompt",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "List Companion",
        short_name: "Listas",
        display: "standalone",
        background_color: "#0F1115",
        theme_color: "#0F1115",
        lang: "pt-BR",
        icons: [{ src: "favicon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,woff,woff2}"],
        runtimeCaching: [{ urlPattern: ({ url }) => url.pathname.startsWith("/api/"), handler: "NetworkOnly" }],
      },
    }),
  ],
  server: { proxy: { "/api": process.env.API_TARGET || "http://127.0.0.1:18001" } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
