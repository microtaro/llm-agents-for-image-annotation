// The run going, watched (out of Gallery.tsx, types design 17.6): each change is waited for and
// everything of the dataset read again; a wait that ends with nothing changed (20 s) waits again
// without reading everything (review 2026-10-07). Its images waiting or being worked on are
// given, to mark on the cards (user 2026-10-06: a trial pressed from ① showed nothing on its
// images).
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { Run } from "@/api/types";
import { useApi } from "./useApi";

/** The run of the dataset waiting or going, the one the bar of annotating with AI shows with
 * its stop (definition 40.2): waiting in the line is stopped too, before it starts. */
export function runGoing(runs: Run[]): Run | null {
  return runs.find((r) => r.going) ?? null;
}

export function useRunWatch(runs: Run[], reloadAll: () => void) {
  // Started (not waiting in the line): its results change.
  const active = runs.find((r) => r.going && r.status !== "queued");
  const [waits, setWaits] = useState(0);
  useEffect(() => {
    if (!active) return;
    let live = true;
    api<Run>(`/v1/runs/${active.id}/wait?after_version=${active.version}&timeout=20`)
      .then((now) => {
        if (!live) return;
        const same =
          now.status === active.status &&
          now.processed === active.processed &&
          now.succeeded === active.succeeded;
        if (same) setWaits((n) => n + 1);
        else reloadAll();
      })
      .catch(() => live && window.setTimeout(reloadAll, 3000));
    return () => {
      live = false;
    };
  }, [active, reloadAll, waits]);
  const results = useApi<{ results: { image_id: string; status: string; waiting: boolean }[] }>(
    active ? `/v1/runs/${active.id}/results` : null,
  );
  const { reload } = results;
  useEffect(() => reload(), [reload, active?.version]);
  const going = new Map(
    (results.data?.results ?? []).filter((r) => r.waiting).map((r) => [r.image_id, r.status]),
  );
  return { active, going };
}
