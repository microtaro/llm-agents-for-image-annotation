import { describe, expect, it } from "vite-plus/test";
import type { Progress } from "@/api/types";
import { overallText, stageText } from "../stages";

const facts = (extra: Partial<Progress["facts"]>) =>
  ({ images: 5, revision: 2, ...extra }) as Progress["facts"];

describe("the map's words (step 18)", () => {
  it("says ①'s next step and ② by what training gets", () => {
    expect(
      stageText(
        "instruction",
        "now",
        facts({ instruction: { items: [], next: "leave_out", draft: true } }),
      ),
    ).toBe("第2版 · 次: アノテーションしない物");
    expect(stageText("production", "done", facts({ adopted: 7, images: 20 }))).toBe(
      "学習に使う 7/20枚",
    );
  });
});

describe("the dataset's line while a draft is made", () => {
  it("names the draft's next step, as ① does", () => {
    const progress = {
      stages: [],
      facts: facts({ instruction: { items: [], next: "leave_out", draft: true } }),
      overall: { kind: "next", stage: "instruction" },
    } as Progress;
    expect(overallText(progress).text).toBe(
      "今すること: 計画書の下書きを進める（次: アノテーションしない物）",
    );
  });
});
