import { describe, expect, it } from "vite-plus/test";
import { formatRoute, parseRoute, planOf, planQuery, type Route, viewOf } from "../route";

describe("route", () => {
  it("reads back what it writes", () => {
    const routes: Route[] = [
      { screen: "library" },
      { screen: "gallery", datasetId: "d1", stage: null, recordId: null },
      { screen: "gallery", datasetId: "d1", stage: "production", recordId: null },
      { screen: "gallery", datasetId: "d1", stage: "production", recordId: "r1" },
      { screen: "gallery", datasetId: "d1", stage: "production", recordId: null, step: "exclude" },
      { screen: "loupe", datasetId: "d1", imageId: "img-1", stage: "production", recordId: null },
    ];
    for (const route of routes) expect(parseRoute(formatRoute(route))).toEqual(route);
  });

  it("names a blank plan, the loupe keeping it (definition 49.2: no plan not begun could be named, so the plan now's results showed)", () => {
    expect(planOf({ blank: "true", revision: 4 })).toEqual({ blank: true });
    expect(planQuery({ blank: true })).toBe("blank=true");
    const loupe: Route = {
      screen: "loupe",
      datasetId: "d1",
      imageId: "img-1",
      stage: "production",
      recordId: null,
      plan: { blank: true },
    };
    expect(parseRoute(formatRoute(loupe))).toEqual(loupe);
  });

  it("leaves out an unknown stage, so the map's present stage opens", () => {
    expect(parseRoute("#/d/d1?stage=nonsense")).toEqual({
      screen: "gallery",
      datasetId: "d1",
      stage: null,
      recordId: null,
    });
  });

  it("opens a link of the stages before in the stage its work is in now (types design 17.1)", () => {
    const stageOfLink = (name: string) => {
      const route = parseRoute(`#/d/d1?stage=${name}`);
      return route.screen === "gallery" ? route.stage : null;
    };
    expect(["inspection", "master", "check", "run", "adoption"].map(stageOfLink)).toEqual([
      "production",
      "production",
      "production",
      "production",
      "production",
    ]);
    expect([viewOf("instruction"), viewOf("production")]).toEqual(["images", "run"]);
  });
});
