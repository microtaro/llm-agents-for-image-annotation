import { describe, expect, it } from "vite-plus/test";
import type { Progress } from "@/api/types";
import { homeOf, stageNow } from "../home";

describe("home", () => {
  it("talks with the reception at the library and with the steward in its dataset", () => {
    expect(homeOf("reception", "d1")).toEqual({ screen: "library" });
    // No stage: the dataset opens at its stage now (definition 35.3).
    expect(homeOf("steward", "d1")).toEqual({
      screen: "gallery",
      datasetId: "d1",
      stage: null,
      recordId: null,
    });
  });
});

describe("coming in to a dataset", () => {
  it("opens at the map's stage now, Apply once the plan is done (definition 35.3)", () => {
    const at = (state: "now" | "done") =>
      ({
        stages: [
          { stage: "instruction", state },
          { stage: "production", state: state === "now" ? "todo" : "now" },
        ],
        facts: { images: 3, revision: null },
      }) as Progress;
    expect(stageNow(at("now"))).toBe("instruction");
    expect(stageNow(at("done"))).toBe("production");
  });
});
