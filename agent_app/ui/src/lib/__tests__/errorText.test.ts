import { describe, expect, it } from "vite-plus/test";
import { ApiError } from "@/api/client";
import { errorText, fieldName } from "../errorText";

describe("error words", () => {
  it("says which field is wrong and how, in the screen's language (found 2026-10-05)", () => {
    expect(fieldName("body.label_definitions.0.attributes.1.name")).toBe(
      "ラベルの定義 1 · 属性 2 · 名前",
    );
    const refused = new ApiError(422, "invalid_input", "The request is not valid", {
      problems: [{ at: "body.max_mcp_calls", message: "x", type: "int_from_float", limit: null }],
    });
    expect(errorText(refused)).toContain("整数");
    expect(errorText(new ApiError(409, "run_active", "Another run is active"))).not.toContain(
      "Another",
    );
    // Sol 2026-10-17: the refusal while a worker answered came in English.
    for (const code of ["workers_answering", "plan_rewritten", "box_fixed"])
      expect(errorText(new ApiError(409, code, "English words"))).not.toContain("English");
  });
});
