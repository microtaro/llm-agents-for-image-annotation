/// <reference types="node" />
// No two functions of the screen share a name (user 2026-10-30: "同じ名前で別な意味の関数とか
// ありえないだろ"); a value read the same way is read by one function (lib/values).
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vite-plus/test";

const SRC = path.resolve(import.meta.dirname, "../..");
// Each store's own subscribe: one role under one name on purpose.
const SAME_ROLE = new Set(["subscribe"]);
const DEFINED = /^(?:export )?(?:async )?(?:function (\w+)|const (\w+) = (?:async )?\()/gm;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return name === "__tests__" ? [] : files(full);
    return /\.(ts|tsx)$/.test(name) ? [full] : [];
  });
}

describe("function names", () => {
  it("are each one function's", () => {
    const where = new Map<string, string[]>();
    for (const file of files(SRC)) {
      for (const match of readFileSync(file, "utf8").matchAll(DEFINED)) {
        const name = match[1] ?? match[2];
        where.set(name, [...(where.get(name) ?? []), path.relative(SRC, file)]);
      }
    }
    const twice = [...where].filter(([name, at]) => at.length > 1 && !SAME_ROLE.has(name));
    expect(twice).toEqual([]);
  });
});
