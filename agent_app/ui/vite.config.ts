import { defineConfig } from "vite-plus";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const require = createRequire(import.meta.url);
const repo = path.resolve(import.meta.dirname, "../..");

// Where the screen's dev server listens and sends the API: this project's fixed ports, checked by
// its dev entry (scripts/); or, in a clone of the public repository, which has neither (the test
// of config.given on the server), Vite's own port and the port the running app wrote down, else
// the one it tries first (config.server_port).
function devServer(): { frontend: number; backend: number; headers: Record<string, string> } {
  if (existsSync(path.join(repo, ".claude/project.config.json"))) {
    const { fixedSettings, identityHeader } = require(
      path.join(repo, "scripts/lib/dev-server.cjs"),
    );
    const { ports, identity } = fixedSettings(repo, process.env);
    // Local development identity only; no host path is exposed.
    return { ...ports, headers: { [identityHeader]: identity } };
  }
  const written = path.join(repo, "agent_app/server.port");
  const backend = existsSync(written) ? Number(readFileSync(written, "utf8")) : 3900;
  return { frontend: 5173, backend, headers: {} };
}

const LICENCES = "third-party-licenses.md";

// The licences of the packages the CSS takes in (src/index.css's @import), in the same form as
// those Vite writes, which are the script's only (2026-11-11: tailwindcss and tw-animate-css were
// missing from them).
function cssLicences(): string {
  const css = readFileSync(path.join(import.meta.dirname, "src/index.css"), "utf8");
  const packages = [...css.matchAll(/^@import\s+"([^"./][^"]*)"/gm)].map((m) => m[1]);
  return packages
    .map((name) => {
      const folder = [repo, import.meta.dirname]
        .map((root) => path.join(root, "node_modules", name))
        .find((candidate) => existsSync(path.join(candidate, "package.json")));
      const file =
        folder &&
        ["LICENSE", "LICENSE.md", "LICENSE.txt"].find((f) => existsSync(path.join(folder, f)));
      if (!folder || !file)
        throw new Error(`No licence found for ${name}, which src/index.css takes in`);
      const { version, license } = JSON.parse(
        readFileSync(path.join(folder, "package.json"), "utf8"),
      );
      const text = readFileSync(path.join(folder, file), "utf8").trim();
      return `\n## ${name} - ${version} (${license})\n\n${text}\n`;
    })
    .join("");
}

// The screen of agent_app. In development it runs on its own port and passes the API to the app
// server; for daily use the app server serves the built files (dist/).
export default defineConfig(({ command }) => {
  const dev = command === "serve" ? devServer() : null;
  const backend = dev ? `http://127.0.0.1:${dev.backend}` : "";
  return {
    test: {
      // Vitest v4 compatibility: preserve mock call history.
      // Remove after tests no longer rely on calls from setup or earlier tests.
      // https://viteplus.dev/guide/vitest-v5#remove-unneeded-compatibility-settings
      // https://vitest.dev/guide/migration/#clearmocks-is-enabled-by-default
      clearMocks: false,
    },
    plugins: [
      react(),
      tailwindcss(),
      {
        name: "dev-identity",
        apply: "serve",
        configureServer(server) {
          server.middlewares.use((_req, res, next) => {
            for (const [name, value] of Object.entries(dev?.headers ?? {})) {
              res.setHeader(name, value);
            }
            next();
          });
        },
      },
      {
        name: "css-licences",
        apply: "build",
        // After the files are written, so the licences Vite writes are there to add to. Line
        // ends made LF, as the public repository keeps the file (tslib's licence has CRLF).
        writeBundle(options) {
          const file = path.join(options.dir ?? "dist", LICENCES);
          const text = readFileSync(file, "utf8") + cssLicences();
          writeFileSync(file, text.replace(/\r\n/g, "\n"));
        },
      },
    ],
    resolve: { alias: { "@": path.resolve(import.meta.dirname, "./src") } },
    // The libraries' licences, for the screen built into the zip (their notices are minified away).
    build: { license: { fileName: LICENCES } },
    server: dev
      ? {
          host: "127.0.0.1",
          port: dev.frontend,
          strictPort: true,
          proxy: { "/v1": backend, "/mcp": backend, "/health": backend },
        }
      : undefined,
  };
});
