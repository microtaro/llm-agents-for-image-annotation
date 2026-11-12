import { defineConfig } from "vite-plus";

// Vite+ (2026-10-05). Never formatted or linted: recorded results, documents, data and test
// fixtures (rewriting them would change records). `npm run lint:agent` checks agent_app/ with
// `vp check agent_app vite.config.ts`.
const records = ["results/**", "docs/**", "data/**", "**/*.md", "scripts/__tests__/fixtures/**"];
// The built screen, which the public repository keeps (2026-11-11): written by the build, not by hand.
const built = ["agent_app/ui/dist/**"];

export default defineConfig({
  fmt: { ignorePatterns: [...records, ...built] },
  lint: {
    ignorePatterns: [...records, ...built],
    jsPlugins: [{ name: "vite-plus", specifier: "vite-plus/oxlint-plugin" }],
    rules: { "vite-plus/prefer-vite-plus-imports": "error" },
    options: { typeAware: true, typeCheck: true },
  },
});
