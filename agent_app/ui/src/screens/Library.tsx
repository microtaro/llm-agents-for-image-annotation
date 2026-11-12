// The library: every dataset as a card with its purpose, where its images came from and the
// overall map's three stages (step 21; five in the step 6 design, the mockup's 1-1). Its screens
// are chosen at the top as a dataset's (definition 60.2): taking in, deleting, writing out.
import { QuitButton } from "@/components/QuitButton";
import { SettingsButton } from "@/components/SettingsButton";
import { ThemeToggle } from "@/components/ThemeToggle";
import type { DatasetSummary } from "@/api/types";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { formatBytes } from "@/lib/bytes";
import { useApi } from "@/lib/useApi";
import { arrange, calledName, type Order } from "@/lib/library";
import { errorText } from "@/lib/errorText";
import {
  type LibraryScreen,
  toggled,
  useLastDataset,
  useLibraryFind,
  useLibraryPicks,
  useLibraryScreen,
} from "@/lib/viewState";
import { DatasetCard } from "./LibraryCard";
import { LibrarySelectionBar } from "./LibraryDecisions";
import { LibraryShell } from "./LibraryShell";
import { ListHead, OrderChoice } from "./ListHead";
import { JobsButton } from "./WorkJobs";
import { LibraryEye } from "@/components/LooksMenu";
import { LIBRARY_COMPACT, useDisplay } from "@/lib/display";

export function Library() {
  const list = useApi<{ datasets: DatasetSummary[]; stored: { images: number; bytes: number } }>(
    "/v1/datasets",
  );
  const datasets = list.data?.datasets ?? [];
  const display = useDisplay();
  // The screen, and the datasets chosen on it (user 2026-10-15, definition 60.2).
  const [screen, setScreen] = useLibraryScreen();
  const [picks, setPicks] = useLibraryPicks(screen);
  const chosen = datasets.filter((d) => picks.includes(d.id));
  // Any number in both: making from several datasets' images, tidying several.
  const choose = (id: string, on: boolean) => setPicks(toggled(picks, id, on));
  const [found, setFound] = useLibraryFind();
  const query = found.query;
  const order = found.order as Order;
  const setQuery = (next: string) => setFound({ query: next, order });
  const setOrder = (next: Order) => setFound({ query, order: next });
  const shown = arrange(datasets, query, order);
  // The dataset now: the one on the right last, whose workers the left has (types design 16.3).
  const [now] = useLastDataset();
  // While a run goes, each card's progress ("running 7/13") is read again, and once more when
  // it ends, by the one watch of the line of work (lib/workWatch; user 2026-10-12: the last card
  // stayed at "running 1/2" after the run had ended).

  return (
    <LibraryShell>
      <div className="min-h-screen">
        {/* The same top row as inside a dataset (agent app 4.1): the place, then what goes on,
          the operations, the settings and the theme at the right end. */}
        <header className="flex flex-wrap items-center gap-x-3.5 gap-y-2 border-b border-line bg-sheet px-5 py-2.5">
          {/* The place and its screen, as a dataset's top row (definition 60.2). */}
          <h1 className="m-0 text-title">{t("library.title")}</h1>
          <span aria-hidden className="text-title text-muted-foreground">
            {t("gallery.path.separator")}
          </span>
          <select
            aria-label={t("apply.screen")}
            className="rounded-md border border-line bg-surface px-2 py-0.5 text-title font-semibold"
            value={screen}
            onChange={(e) => setScreen(e.target.value as LibraryScreen)}
          >
            <option value="import">{t("library.screen.import")}</option>
            <option value="delete">{t("library.screen.delete")}</option>
            <option value="export">{t("library.screen.export")}</option>
          </select>
          <span className="flex-1" />
          <JobsButton datasetId={null} />
          <SettingsButton />
          <ThemeToggle />
          <QuitButton />
        </header>

        <main className="mx-auto flex max-w-[1360px] flex-col gap-4 px-7 pb-10 pt-6">
          {list.error && <p className="text-failed">{errorText(list.error)}</p>}
          {list.data && datasets.length === 0 && (
            <p className="text-muted-foreground">{t("library.empty")}</p>
          )}
          {/* Nothing found: say so, and how to go back (Astra 2026-10-06: a blank area). */}
          {datasets.length > 0 && shown.length === 0 && (
            <p className="flex items-center gap-2 text-muted-foreground">
              {t("common.noneFound")}
              <Button size="small" onClick={() => setQuery("")}>
                {t("common.clearFind")}
              </Button>
            </p>
          )}
          <LibrarySelectionBar
            screen={screen}
            chosen={chosen}
            onClear={() => setPicks([])}
            shown={shown.map((d) => d.id)}
            found={Boolean(query)}
            onChosen={setPicks}
          />
          {/* The list's head, right over the cards, as every list's (user 2026-10-28): how many,
              how much is kept in all, once each (user 2026-10-15), finding and the order. */}
          <ListHead
            title={
              query
                ? t("library.found", { count: shown.length, total: datasets.length })
                : t("library.count", { count: datasets.length })
            }
            note={
              list.data
                ? t("library.stored", {
                    count: list.data.stored.images,
                    size: formatBytes(list.data.stored.bytes),
                  })
                : undefined
            }
          >
            {/* Finding beside the order (user 2026-10-28: alone on its row it floated): what
                and how many on the left, how they are shown on the right. */}
            <input
              aria-label={t("library.search")}
              placeholder={t("library.search")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-64 max-w-full rounded-md border border-line bg-surface px-2 py-0.5 text-body"
            />
            <OrderChoice<Order>
              value={order}
              options={(["new", "old", "name", "worked"] as const).map((o) => ({
                value: o,
                label: t(`library.order.${o}`),
              }))}
              onChange={setOrder}
            />
            <LibraryEye />
          </ListHead>
          <div
            className="grid gap-4"
            style={{
              gridTemplateColumns: `repeat(auto-fill, minmax(min(${display.libraryCardSize}px, 100%), 1fr))`,
            }}
          >
            {shown.map((dataset) => (
              <DatasetCard
                key={dataset.id}
                dataset={dataset}
                chosen={dataset.id === now}
                ring={{
                  chosen: picks.includes(dataset.id),
                  label: t("lib.choose", { name: calledName(dataset) }),
                  onChoose: (on) => choose(dataset.id, on),
                }}
                tidying={screen === "delete"}
                compact={display.libraryCardSize < LIBRARY_COMPACT}
              />
            ))}
          </div>
        </main>
      </div>
    </LibraryShell>
  );
}
