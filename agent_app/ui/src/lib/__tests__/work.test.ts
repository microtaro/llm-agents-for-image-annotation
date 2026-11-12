import { describe, expect, it } from "vite-plus/test";
import { changedText, noteText, runState } from "../work";

describe("what a person changed when applying", () => {
  it("says the changed values in words", () => {
    expect(changedText({ count: [5, 2] }, (model) => model ?? "")).toContain("5→2");
  });
});

describe("how a run ended", () => {
  it("says a run stopped at its cost limit apart from one a person stopped (definition 50.3: both said 'stopped')", () => {
    expect(runState("stopped", "budget_reached")).toBe("budget_reached");
    expect(runState("stopped", "stopped")).toBe("stopped");
    expect(runState("succeeded", null)).toBe("succeeded");
    expect(runState("failed", "memory_short")).toBe("memory_short");
  });
});

describe("a run that ended with images not done", () => {
  it("names them as not done (the 50 images' test 10-29: the first ten read as failed)", () => {
    const data = { note: "run_ended", status: "failed", succeeded: 38, total: 47 };
    const said = noteText(
      { text: "run_ended", data: { ...data, images: ["B011.png"], not_done: true } },
      () => "",
    );
    expect(said).toContain("済んでいない画像: B011.png");
  });
});

describe("the parts of a worker's answer not used", () => {
  it("names each part in the screen's words (definition 68.2)", () => {
    const parts = [{ part: "show" }, { part: "option", label: "位置" }];
    const said = noteText(
      { text: "answer_unused", data: { note: "answer_unused", parts } },
      () => "",
    );
    expect(said).toContain("右に表示");
    expect(said).toContain("「位置」");
  });
});

describe("a dataset made without some files", () => {
  it("says which reasons, as the taking in does (definition 76)", () => {
    const outcome = {
      id: "d",
      name: "外れ値",
      skipped: [{ name: "b.png", reason: "same_content", as: "a.png" }],
    };
    const said = noteText(
      { text: "box_applied", data: { note: "box_applied", title: "作る", outcome } },
      () => "",
    );
    expect(said).toContain("取り込めなかった物 1");
    expect(said).toContain("中身が同じ画像");
  });
});
