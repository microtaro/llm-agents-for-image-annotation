import { afterEach, describe, expect, it, vi } from "vite-plus/test";
import { readApi } from "../useApi";
import { ApiError } from "@/api/client";
import { every, notAnswering, turned } from "../workWatch";

describe("watching the line of work", () => {
  it("reads again when work starts or ends (user 2026-10-15: a run started elsewhere)", () => {
    expect(turned(false, true)).toBe(true);
    expect(turned(true, false)).toBe(true);
    expect(turned(true, true)).toBe(false);
    expect(turned(null, true)).toBe(false);
  });

  it("says the app stopped when it does not answer (2026-10-30: quit from its small window, the page stayed)", () => {
    expect(notAnswering(new TypeError("Failed to fetch"))).toBe(true);
    expect(notAnswering(new DOMException("timed out", "TimeoutError"))).toBe(true);
    expect(notAnswering(new ApiError(502, "http_502", "Bad Gateway"))).toBe(true);
    expect(notAnswering(new ApiError(409, "draft_conflict", "changed"))).toBe(false);
  });

  it("reads often only while something goes", () => {
    expect(every({ running: 1, queued: 0, jobs: [] } as never)).toBeLessThan(every(undefined));
  });
});

describe("a read of the cache", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("is stopped with its request when the cache drops it (2026-10-29: reads piled up until the browser refused them all)", async () => {
    let sent: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      (_path: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          sent = init.signal ?? undefined;
          init.signal?.addEventListener("abort", () => reject(init.signal?.reason));
        }),
    );
    const cache = new AbortController();
    const reading = readApi("/v1/jobs", cache.signal);
    cache.abort();
    await expect(reading).rejects.toBeDefined();
    expect(sent?.aborted).toBe(true);
  });
});
