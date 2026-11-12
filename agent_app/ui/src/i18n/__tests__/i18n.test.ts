/// <reference types="node" />
// Every word lives in both dictionaries, and no screen file writes Japanese directly
// (AGENTS.md: the screen's words are only in ja.json and en.json).
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vite-plus/test";
import en from "../en.json";
import { fill, startLang } from "../index";
import ja from "../ja.json";

const SRC = path.resolve(import.meta.dirname, "../..");
const JAPANESE = /[぀-ヿ㐀-鿿！-｠]/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return name === "__tests__" ? [] : files(full);
    return /\.(ts|tsx)$/.test(name) ? [full] : [];
  });
}

describe("screen words", () => {
  it("has the same keys in Japanese and English", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(ja).sort());
  });

  it("starts in the browser's language until one is chosen (2026-11-09: always Japanese)", () => {
    expect(startLang(null, "en-US")).toBe("en");
    expect(startLang(null, "ja-JP")).toBe("ja");
    expect(startLang("ja", "en-US")).toBe("ja");
  });

  it('says one thing for a count of one in English (2026-10-30: "1 images")', () => {
    const plural =
      /\b1(?:\/1)? (?:[A-Za-z]+ )?(?:images|datasets|objects|records|annotations|labels|characters|items|times|rows|turns|questions|lines|masks|sheets|files|samples|ways|versions)\b/;
    const found = Object.entries(en)
      .filter(([, words]) => {
        const ones = Object.fromEntries([...words.matchAll(/\{(\w+)/g)].map((m) => [m[1], 1]));
        return plural.test(fill(words, ones, "en"));
      })
      .map(([key]) => key);
    expect(found).toEqual([]);
  });

  it("has no Japanese written in the code", () => {
    const found = files(SRC).filter((file) => JAPANESE.test(readFileSync(file, "utf8")));
    expect(found).toEqual([]);
  });

  it("has words for every refusal a person can meet (issue #3 U-16)", () => {
    // The server's codes from its source; those only a worker or the line of work meets are
    // never on the screen, and invalid input and a plan's definition have their own words.
    const server = path.resolve(SRC, "../../agent_app");
    const codes = new Set(
      readdirSync(server)
        .filter((name) => name.endsWith(".py"))
        .flatMap((name) => [
          ...readFileSync(path.join(server, name), "utf8").matchAll(
            /ApiError\(\s*\d+,\s*"([a-z_]+)"/g,
          ),
        ])
        .map((m) => m[1]),
    );
    const notOnScreen = new Set([
      "agent_scope",
      "library_decision",
      "run_scope",
      "run_call_busy",
      "run_inactive",
      "tool_call_limit",
      "idempotency_conflict",
      "revision_not_found",
      "not_one",
      "payload_too_large",
      "unsupported_image",
      "view_image_mismatch",
      "view_not_found",
      "proposal_not_applying",
      "invalid_input",
      "invalid_definition",
    ]);
    const missing = [...codes].filter((code) => !notOnScreen.has(code) && !(`error.${code}` in ja));
    expect(missing).toEqual([]);
  });

  it("says none of the words the screen gave up (issue #3 U-09, U-17)", () => {
    // Definition 16.3, 20.1 and the workers' rules: 決定待ち, not 提案; 学習に使う, not 採用;
    // AI でアノテーションする, not 流す; アノテーションの記録, not 依頼; 計画書, not 実施案.
    const given = /提案|採用|流す|流し|依頼|実施案/;
    const found = Object.entries(ja)
      .filter(([, words]) => given.test(words))
      .map(([key]) => key);
    expect(found).toEqual([]);
  });

  it("has the server's types of things, no more and no fewer (issue #4 F-05)", () => {
    const server = readFileSync(path.resolve(SRC, "../../agent_app/object_types.py"), "utf8");
    const listed = server.split("\nTYPES = {")[1].split("\n}")[0];
    const types = [...listed.matchAll(/^ {4}"([a-z]+)":/gm)].map((m) => m[1]).sort();
    const screen = readFileSync(path.resolve(SRC, "api/types.ts"), "utf8")
      .split("export type ObjectType =")[1]
      .split(";")[0];
    expect([...screen.matchAll(/"([a-z]+)"/g)].map((m) => m[1]).sort()).toEqual(types);
  });

  it("names every decision of the server, and tags a dataset's on its images (review 10-28)", () => {
    // Keys made from a decision's tool (t(`work.tool.${tool}`)) are not found by the check of
    // the keys the code asks for: pick and taking images out showed as raw keys.
    const server = readFileSync(path.resolve(SRC, "../../agent_app/actions.py"), "utf8");
    const listed = server.split("\nDECISIONS = {")[1].split("\n}")[0];
    const decisions = [
      ...listed.matchAll(/^ {4}"([a-z_]+)": Decision\(\s*"[a-z]+",\s*"([a-z]+)"/gm),
    ];
    expect(decisions.length).toBeGreaterThan(10);
    const missing = decisions.flatMap(([, tool, place]) => [
      ...(`work.tool.${tool}` in ja ? [] : [`work.tool.${tool}`]),
      ...(place === "dataset" && !(`band.tag.${tool}` in ja) ? [`band.tag.${tool}`] : []),
    ]);
    expect(missing).toEqual([]);
  });

  it("names every group of the settings and every setting in them (2026-10-29)", () => {
    // The settings screen shows the server's groups (t(`settings.group.${group}`) and
    // t(`settings.${key}`)), which the check of the keys the code asks for does not find.
    const server = readFileSync(path.resolve(SRC, "../../agent_app/settings.py"), "utf8");
    const listed = server.split("\nGROUPS = [")[1].split("\n]")[0];
    const names = [...listed.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
    expect(names.length).toBeGreaterThan(10);
    const groups = [...listed.matchAll(/^ {4}\[\s*"([a-z]+)"/gm)].map((m) => m[1]);
    const keys = names.map((name) =>
      groups.includes(name) ? `settings.group.${name}` : `settings.${name}`,
    );
    expect(keys.filter((key) => !(key in ja) || !(key in en))).toEqual([]);
  });

  it("has every key the code asks for", () => {
    const asked = files(SRC).flatMap((file) =>
      [...readFileSync(file, "utf8").matchAll(/\bt\(\s*"([^"]+)"/g)].map((m) => m[1]),
    );
    const missing = asked.filter((key) => !(key in ja));
    expect(missing).toEqual([]);
  });
});
