import { existsSync, readFileSync } from "node:fs";
import { defineConfig, type Plugin, type PreviewServer, type ViteDevServer } from "vite";
import path from "node:path";

import { buildV197PerformanceBootstrap } from "./src/bridge/v197PerformanceProfile";

const omegaResearchFlag = process.env.VITE_NUR_ENABLE_OMEGA_RESEARCH ?? process.env.NUR_ENABLE_OMEGA_RESEARCH ?? "";
const rootDirectory = __dirname;
const publicV197Directory = path.resolve(rootDirectory, "public/v197");
const canonicalV197Filename = "NUR_V197_CHECKBOX_TICK_RESTORED.html";
const nativeV197Routes = new Set([
  "/",
  "/auth",
  "/onboarding",
  "/today",
  "/talk",
  "/journal",
  "/plan",
  "/systems",
  "/universe",
  "/universe/map",
  "/universe/orbits",
  "/universe/timeline",
  "/universe/insights",
  "/universe/research",
  "/universe/community",
  "/universe/web-signals",
  "/settings",
  "/memory",
  "/teach-nur",
  "/billing",
  "/capsules",
  "/universe/omega",
  "/universe/omega/review",
]);

function pathname(rawUrl: string | undefined): string {
  return new URL(rawUrl ?? "/", "http://nur.local").pathname;
}

function isNativeV197Route(value: string): boolean {
  return nativeV197Routes.has(value)
    || value.startsWith("/talk/")
    || value.startsWith("/journal/")
    || value.startsWith("/plan/")
    || value.startsWith("/systems/")
    || value === "/universe/life"
    || value.startsWith("/capsule/")
    || value === "/consultations"
    || value.startsWith("/consultations/")
    || value === "/community"
    || value.startsWith("/community/")
    || value === "/projects"
    || value.startsWith("/projects/")
    || value === "/glow"
    || value === "/notifications"
    || value.startsWith("/universe/omega/why-changed/");
}

function composedV197Document(sourcePath: string): string {
  const source = readFileSync(sourcePath, "utf8");
  const bridge = '<script type="module" src="/assets/v197-bridge.js"></script>';
  const pwa = '<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#000000">';
  const performanceProfile = buildV197PerformanceBootstrap();
  if (!source.includes("</body>")) throw new Error("Canonical V197 source is missing its closing body tag.");
  // Preserve the canonical file byte-for-byte on disk and at /v197/. Native
  // product routes add only a deterministic runtime quality profile, PWA
  // metadata, and the nonvisual bridge. The profile runs before V197 assigns
  // either srcdoc and falls back to canonical bytes if a signature drifts.
  return source
    .replace("</head>", `${pwa}${performanceProfile}</head>`)
    .replace("</body>", `${bridge}</body>`);
}

function v197DirectHost(): Plugin {
  const attach = (server: ViteDevServer | PreviewServer, preview: boolean) => {
    server.middlewares.use((request, response, next) => {
      const route = pathname(request.url);
      if (route === "/assets/v197-bridge.js" && !preview) {
        response.statusCode = 200;
        response.setHeader("content-type", "application/javascript; charset=utf-8");
        response.setHeader("cache-control", "no-store");
        response.end('import "/src/main.ts";');
        return;
      }
      if (!isNativeV197Route(route)) return next();

      const builtCanonical = path.resolve(rootDirectory, `dist/v197/${canonicalV197Filename}`);
      const canonicalPath = preview && existsSync(builtCanonical)
        ? builtCanonical
        : path.resolve(publicV197Directory, canonicalV197Filename);
      response.statusCode = 200;
      response.setHeader("content-type", "text/html; charset=utf-8");
      response.setHeader("cache-control", "no-store");
      response.end(composedV197Document(canonicalPath));
    });
  };

  return {
    name: "nur-v197-direct-host",
    configureServer(server) {
      attach(server, false);
    },
    configurePreviewServer(server) {
      attach(server, true);
    },
  };
}

export default defineConfig({
  plugins: [v197DirectHost()],
  define: {
    "import.meta.env.VITE_NUR_ENABLE_OMEGA_RESEARCH": JSON.stringify(omegaResearchFlag),
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/healthz": { target: "http://localhost:8000", changeOrigin: true },
      "/readyz": { target: "http://localhost:8000", changeOrigin: true },
      "/metrics": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  preview: {
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/healthz": { target: "http://localhost:8000", changeOrigin: true },
      "/readyz": { target: "http://localhost:8000", changeOrigin: true },
      "/metrics": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      input: path.resolve(rootDirectory, "src/main.ts"),
      output: {
        entryFileNames: "assets/v197-bridge.js",
        chunkFileNames: "assets/v197-[name]-[hash].js",
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    css: false,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
