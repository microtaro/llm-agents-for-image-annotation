// A set of one type on the right, as a worker showed it (types design 3): the type decides how
// it is shown, the worker only says which set (type and conditions). Images are the gallery's
// cards; the others are tables whose rows open the thing where it lives
// (the loupe, the run, the band). The ways of showing each type are made richer in step 4 of
// types design 17.
import type {
  AgentKey,
  Dataset,
  GalleryItem,
  ObjectSet,
  ObjectType,
  Proposal,
  RecordKind,
  Run,
  Shown,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { has, t, when } from "@/i18n";
import { go, PLAN_FIELDS, planOf, resultLoupe, whereQuery } from "@/lib/route";
import { modelLabel, spentText, versionOf, wayText, useModelName } from "@/lib/runChoice";
import { screenName } from "@/lib/stages";
import { stepOfBox } from "@/lib/stageSteps";
import { planChangeText } from "@/lib/decisions";
import { screenOfBox } from "@/lib/talk";
import { invalidate, useApi } from "@/lib/useApi";
import { BackButton } from "@/components/BackButton";
import { type Action, actionPath, runActions, type TypeActions } from "@/lib/actions";
import { api } from "@/api/client";
import { toast } from "sonner";
import { enterToTalk, useDraftView, useRememberDataset } from "@/lib/viewState";
import { errorText } from "@/lib/errorText";
import { runState } from "@/lib/work";
import { AgentShell } from "./AgentShell";
import { useShowBox } from "./DecisionBand";
import { GalleryHeader } from "./GalleryHeader";
import { PlanBasis } from "./PlanBasis";
import { PlanScreen } from "./PlanScreen";
import { DraftView } from "./DraftView";
import { APP_TYPES, FIELD_VALUES } from "@/lib/objectTypes";
import { ImageSet } from "./ImageSet";
import { type SettingRow, SettingsRead } from "./SettingsRead";
import { textOf } from "@/lib/values";

type Row = Record<string, unknown>;
const CELL = "px-2.5 py-1.5 align-middle";
export function ObjectsScreen({
  datasetId,
  type,
  where,
  id,
  title,
}: {
  datasetId: string;
  type: ObjectType;
  where: Shown["where"];
  id: string | null;
  title: string;
}) {
  const base = `/v1/datasets/${datasetId}`;
  useRememberDataset(datasetId);
  const dataset = useApi<Dataset>(base);
  // The images and records named in the conditions by their names, not their ids.
  const runs = useApi<{ runs: Run[] }>(`${base}/runs`);
  const names = new Map([
    ...(dataset.data?.images ?? []).map((i): [string, string] => [i.image_id, i.name]),
    ...(runs.data?.runs ?? []).flatMap((r): [string, string][] =>
      r.number == null ? [] : [[r.id, t("run.number", { number: r.number })]],
    ),
  ]);
  const query = new URLSearchParams(whereQuery(where)).toString();
  const found = useApi<ObjectSet>(
    id ? `${base}/objects/${type}?${query}` : `${base}/objects/${type}${query ? `?${query}` : ""}`,
  );
  const items = (found.data?.items ?? []).filter((item) => !id || idOf(type, item as Row) === id);
  const heading = title || t(`object.${type}`);
  return (
    <AgentShell datasetId={datasetId} looking={{ showing: { type, where, title: heading } }}>
      <div className="flex min-h-screen flex-col">
        {/* The dataset's top row, as on its screens, with the set in the screen's place: any
            screen is chosen from here too (user 2026-10-23: only "back" led out). */}
        <GalleryHeader
          datasetId={datasetId}
          dataset={dataset.data}
          stage="production"
          plan={planOf(where)}
          here={heading}
        />
        <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1.5 border-b-2 border-action bg-surface px-5 py-2">
          <BackButton
            fallback={() => go({ screen: "gallery", datasetId, stage: null, recordId: null })}
          />
          <b className="text-heading">{heading}</b>
          {!APP_TYPES.includes(type) && <PlanBasis datasetId={datasetId} plan={planOf(where)} />}
          <span className="text-muted-foreground">
            {t("objects.count", { count: items.length })}
          </span>
          {/* The type and the conditions, each when it says more than the heading (2026-10-27:
              with none, "Annotation records 3 Annotation records ·"). */}
          <span className="text-muted-foreground">
            {[
              heading !== t(`object.${type}`) ? t(`object.${type}`) : "",
              conditions(where, (id) => names.get(id) ?? id),
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>
        <main className="px-5 py-3">
          {found.error ? (
            <p className="m-0 text-failed">{errorText(found.error)}</p>
          ) : !found.data ? (
            <p className="m-0 text-muted-foreground">…</p>
          ) : items.length === 0 ? (
            <p className="m-0 text-muted-foreground">{t("objects.none")}</p>
          ) : type === "version" && id ? (
            // One version: how it was asked for, then its plan as a document (types design 4).
            <>
              <VersionAsks datasetId={datasetId} revision={id} />
              <PlanScreen
                datasetId={datasetId}
                version={id}
                images={
                  new Map(
                    (dataset.data?.images ?? []).map((i) => [
                      i.image_id,
                      {
                        id: i.image_id,
                        name: i.name,
                        width: i.width,
                        height: i.height,
                        origin: "real" as const,
                        source_path: i.source_path,
                        excluded: i.excluded,
                      },
                    ]),
                  )
                }
                colors={{}}
              />
            </>
          ) : (
            <Shown
              datasetId={datasetId}
              type={type}
              items={items as Row[]}
              where={where}
              one={Boolean(id)}
            />
          )}
        </main>
      </div>
    </AgentShell>
  );
}

function idOf(type: ObjectType, item: Row): string {
  if (type === "image") return textOf((item.image as Row)?.id);
  if (type === "result") return textOf(item.result_id);
  if (type === "version") return textOf(item.revision);
  if (type === "snapshot") return textOf(item.number);
  return textOf(item.id);
}

/** The conditions in words ("Annotation: failed · Image: C005.png"); a yes/no field is
 * its words alone, a known value its own word (types design 4: object.where.*), the things
 * named by their ids said by their names (nameOf; user 2026-10-28: the ids were shown; 2026-11-05:
 * a record's still was, and it is never shown while its name is not known). The plan the set is
 * judged by is said beside them (PlanBasis), not here. */
export function conditions(where: Shown["where"], nameOf: (id: string) => string): string {
  return Object.entries(where)
    .filter(([key]) => !PLAN_FIELDS.includes(key))
    .map(([key, value]) => {
      const own = FIELD_VALUES[key];
      if (own) return own(String(value));
      if (value === true || value === "true") return t(`object.where.${key}`);
      if (value === false || value === "false")
        return t("object.where.not", { what: t(`object.where.${key}`) });
      const parts = Array.isArray(value) ? value.map(String) : String(value).split(",");
      if (key === "run") {
        const name = nameOf(parts[0]);
        return name === parts[0] ? t("object.where.run") : name;
      }
      const text = (key === "ids" || key === "image" ? parts.map(nameOf) : parts).join(
        t("text.list"),
      );
      const word = `object.value.${key}.${text}`;
      return `${t(`object.where.${key}`)}: ${has(word) ? t(word) : text}`;
    })
    .join(" · ");
}

function Shown({
  datasetId,
  type,
  items,
  where,
  one = false,
}: {
  datasetId: string;
  type: ObjectType;
  items: Row[];
  /** The set's conditions (the plan its images are judged by, 36.1). */
  where: Shown["where"];
  /** One thing asked by its id. */
  one?: boolean;
}) {
  const modelName = useModelName();
  const dataset = useApi<Dataset>(`/v1/datasets/${datasetId}`);
  const colors = useApi<{ colors: Record<string, string> }>(
    `/v1/datasets/${datasetId}/label-colors`,
  );
  const showBox = useShowBox(datasetId);
  const actions = useApi<TypeActions>("/v1/object-types");
  const [, setDraftView] = useDraftView(datasetId);
  const names = new Map((dataset.data?.images ?? []).map((i) => [i.image_id, i.name]));
  // The app's settings, read only (definition 71).
  if (type === "settings") return <SettingsRead items={items as unknown as SettingRow[]} />;
  // Images by the plan their conditions name, as every set of images is drawn (36.2).
  if (type === "image")
    return (
      <ImageSet
        datasetId={datasetId}
        items={items as unknown as GalleryItem[]}
        view="adoption"
        colors={colors.data?.colors ?? {}}
        plan={planOf(where)}
      />
    );
  if (type === "draft")
    // The draft's whole text here (Sol 2026-10-13: a nearly empty screen and one more press).
    return (
      <DraftView datasetId={datasetId} view="current" onView={(v) => v ?? setDraftView(null)} />
    );
  const table = (
    head: string[],
    rows: [string, string[], (() => void) | null][],
    extra?: (key: string) => React.ReactNode,
  ) => (
    <div className="max-w-full overflow-x-auto">
      <table className="w-full border-collapse text-body">
        <thead>
          <tr className="border-b border-line text-left text-muted-foreground">
            {head.map((h) => (
              <th key={h} className={`${CELL} font-normal`}>
                {t(h)}
              </th>
            ))}
            <th className={CELL} />
          </tr>
        </thead>
        <tbody>
          {rows.map(([key, cells, open]) => (
            <tr key={key} className="border-b border-line">
              {cells.map((cell, i) => (
                <td key={i} className={`${CELL} ${i === 0 ? "font-semibold" : ""}`}>
                  {cell}
                </td>
              ))}
              <td className={`${CELL} text-right whitespace-nowrap`}>
                {extra?.(key)}
                {/* Nothing to open (an image a fixed version did not hold): no button. */}
                {open && (
                  <Button size="small" onClick={open}>
                    {t("objects.open")}
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  if (type === "result")
    return table(
      [
        "objects.col.image",
        "objects.col.when",
        "objects.col.model",
        "objects.col.state",
        "objects.col.objects",
      ],
      items.map((r) => [
        textOf(r.result_id),
        [
          names.get(textOf(r.image_id)) ?? textOf(r.image_id),
          when(textOf(r.record_at)),
          `${modelLabel(r.model ? textOf(r.model) : null, textOf(r.record_kind) as RecordKind, modelName)} · ${versionOf(Number(r.instruction_revision))}`,
          t(`badge.${textOf(r.status)}`),
          t("common.objects", { count: Number(r.annotation_count ?? 0) }),
        ],
        () =>
          go({
            screen: "loupe",
            datasetId,
            ...resultLoupe({
              image_id: textOf(r.image_id),
              record_id: textOf(r.record_id),
              trial: Boolean(r.trial),
              revision: Number(r.instruction_revision),
            }),
          }),
      ]),
    );
  if (type === "run") {
    // The run's buttons come from the types' list of actions (types design 8).
    const runs = new Map((items as unknown as Run[]).map((r) => [r.id, r]));
    const press = async (action: Action, id: string) => {
      try {
        const done = await api<{ images?: number }>(actionPath(action, datasetId, id), {
          body: {},
        });
        // How many changed (definition 19.5).
        toast.success(t(`action.run.${action.name}.done`, { count: done.images ?? 0 }));
        invalidate(datasetId);
      } catch (reason) {
        toast.error(errorText(reason));
      }
    };
    // Records compared (definition 54, user 2026-10-27): the way each ran (version, model,
    // effort) against what came of it (images that succeeded, time, cost).
    return table(
      [
        "objects.col.record",
        "objects.col.when",
        "objects.col.way",
        "objects.col.state",
        "objects.col.succeeded",
        "objects.col.time",
        "objects.col.cost",
      ],
      (items as unknown as Run[]).map((r) => [
        r.id,
        [
          // By number, and a try said so (Sol 2026-10-14: neither was in the list).
          `${t("run.number", { number: r.number ?? "" })}${r.trial ? ` · ${t("run.trial")}` : ""}`,
          when(r.started_at),
          wayText(r, modelName),
          t(`run.status.${runState(r.status, r.error_code)}`),
          `${r.succeeded}/${r.total}`,
          spentText(r.elapsed_ms, null) || "—",
          spentText(null, r.cost?.usd) || "—",
        ],
        () =>
          go({
            screen: "gallery",
            datasetId,
            stage: r.of_version ? "production" : "instruction",
            recordId: r.id,
          }),
      ]),
      (id) => {
        const run = runs.get(id);
        return run
          ? runActions(actions.data ?? {}, run).map((action) => (
              <Button
                key={action.name}
                size="small"
                className="mr-1.5"
                onClick={() => void press(action, id)}
              >
                {t(`action.run.${action.name}`)}
              </Button>
            ))
          : null;
      },
    );
  }
  if (type === "proposal")
    return table(
      [
        "decision.list.col.title",
        "decision.list.col.stage",
        "objects.col.state",
        "decision.list.col.made",
      ],
      (items as unknown as Proposal[]).map((p) => [
        p.id,
        [
          p.title,
          p.stage ? screenName(p.stage, screenOfBox(p)) : "—",
          t(`work.box.state.${p.state}`),
          when(p.created_at),
        ],
        () => {
          showBox(p);
          go({
            screen: "gallery",
            datasetId,
            stage: p.stage ?? null,
            recordId: null,
            step: p.stage ? stepOfBox(p.stage, p.step) : null,
          });
        },
      ]),
    );
  if (type === "version") {
    // How each came about (user 2026-10-13): what changed from the one before, and the talk it
    // was saved from, to read how it was asked for.
    const story = (v: Row) => {
      if (Number(v.revision) === 1) return t("objects.version.first");
      const from = (v.from_previous ?? null) as Record<string, unknown> | null;
      return planChangeText(from, modelName) || t("objects.version.same");
    };
    const talkOf = (key: string) => {
      const v = items.find((x) => textOf(x.revision) === key);
      const talk = v?.talk as Talk | null | undefined;
      return talk ? (
        <Button
          size="small"
          variant="link"
          onClick={() => {
            enterToTalk(datasetId, talk.chat_id, talk.line ?? undefined);
            go({ screen: "gallery", datasetId, stage: "instruction", recordId: null });
          }}
        >
          {t("objects.version.talk")}
        </Button>
      ) : null;
    };
    return table(
      ["objects.col.version", "objects.col.when", "objects.col.fromPrevious"],
      items.map((v) => [
        textOf(v.revision),
        [versionOf(Number(v.revision)), when(textOf(v.created_at)), story(v)],
        () =>
          go({
            screen: "objects",
            datasetId,
            type: "version",
            where: {},
            id: textOf(v.revision),
            title: t("plan.version.title", { revision: textOf(v.revision) }),
          }),
      ]),
      talkOf,
    );
  }
  if (type === "snapshot" && one && items[0]) {
    // One fixed version: each image and the result it holds, as it was fixed (Sol 2026-10-13:
    // its [Open] showed what training gets now).
    type Held = {
      image_id: string;
      result: {
        record_id: string;
        record_at: string;
        model: string | null;
        record_kind: RecordKind;
      } | null;
    };
    const held = (items[0].items ?? []) as Held[];
    return table(
      ["objects.col.image", "objects.col.held"],
      held.map((h) => [
        h.image_id,
        [
          names.get(h.image_id) ?? h.image_id,
          h.result
            ? `${modelLabel(h.result.model, h.result.record_kind, modelName)} · ${when(h.result.record_at)}`
            : t("objects.held.none"),
        ],
        // As it was fixed: the held record's result; an image it did not hold has nothing to
        // open (Sol 2026-10-13: opened, it showed what training uses now).
        h.result
          ? () =>
              go({
                screen: "loupe",
                datasetId,
                imageId: h.image_id,
                stage: "production",
                recordId: h.result?.record_id ?? null,
              })
          : null,
      ]),
    );
  }
  if (type === "snapshot")
    return table(
      ["objects.col.version", "objects.col.when", "objects.col.images"],
      items.map((s) => [
        textOf(s.number),
        [
          t("objects.snapshot", { number: textOf(s.number) }),
          when(textOf(s.created_at)),
          t("common.images", { count: Number(s.used ?? 0) }),
        ],
        () =>
          go({
            screen: "objects",
            datasetId,
            type: "snapshot",
            where: {},
            id: textOf(s.number),
            title: t("objects.snapshot", { number: textOf(s.number) }),
          }),
      ]),
    );
  return table(
    ["objects.col.name"],
    items.map((d) => [
      textOf(d.id),
      [textOf(d.name)],
      () => go({ screen: "gallery", datasetId, stage: null, recordId: null }),
    ]),
  );
}

interface Talk {
  agent: AgentKey;
  chat_id: number;
  line: number | null;
}

/** The person's words that led to a version, and its talk a press away (user 2026-10-14: to
 * reuse it, how it was asked for is wanted). What the AI gets is the plan below as it is. */
function VersionAsks({ datasetId, revision }: { datasetId: string; revision: string }) {
  const found = useApi<{ items: { asks?: { id: number; text: string }[]; talk?: Talk | null }[] }>(
    `/v1/datasets/${datasetId}/objects/version?revision=${revision}`,
  );
  const story = found.data?.items[0];
  if (!story) return null;
  const asks = story.asks ?? [];
  const talk = story.talk;
  return (
    <section className="mb-3 flex flex-col gap-1.5 rounded-md border border-line bg-surface px-3 py-2 text-lead">
      <b>{t("version.asks.title", { revision })}</b>
      {asks.length ? (
        <ol className="m-0 flex flex-col gap-1 pl-5">
          {asks.map((a) => (
            <li key={a.id}>{a.text}</li>
          ))}
        </ol>
      ) : (
        <span className="text-muted-foreground">{t("version.asks.none")}</span>
      )}
      <span className="text-body text-muted-foreground">{t("version.asks.ai")}</span>
      {talk && (
        <Button
          size="small"
          variant="link"
          className="self-start"
          onClick={() => {
            enterToTalk(datasetId, talk.chat_id, talk.line ?? undefined);
            go({ screen: "gallery", datasetId, stage: "instruction", recordId: null });
          }}
        >
          {t("objects.version.talk")}
        </Button>
      )}
    </section>
  );
}
