// The bar of annotating with AI (definition 40.2): the run being decided, whoever made it (the
// steward's waiting run, else the images the person ringed), choosing in one line and deciding
// with its one button in the next, its values on asking and its card in a window; above it the
// run going, with stop. It stays at the top while the cards scroll: the cards are its images,
// their rings its choice.
import { useState } from "react";
import { toast } from "sonner";
import type { AgentInfo, GalleryItem, Run, RunCard, RunModels } from "@/api/types";
import { ChooseLine, DecideLine } from "@/components/ChooseLine";
import { Button } from "@/components/ui/button";
import { Confirm, Dialog } from "@/components/ui/dialog";
import { t } from "@/i18n";
import { useModelName } from "@/lib/runChoice";
import { heldSaid, runCardView, runLine } from "@/lib/cardView";
import { decideLabel, type PlanTarget, planToOpen, workersAnswering } from "@/lib/decisions";
import { errorText } from "@/lib/errorText";
import {
  decideRun,
  heavyOf,
  letGo,
  runWho,
  useRunDecision,
  useRunPreview,
} from "@/lib/runDecision";
import { annotatedAfter, budgetWords, type Narrowing, runSplit } from "@/lib/selection";
import { invalidate, useApi } from "@/lib/useApi";
import { placeKey, useChatOf } from "@/lib/viewState";
import { AskSteward } from "./AskSteward";
import { RunBar } from "./RunBar";
import { RunCardView } from "./RunCardView";
import { textOf } from "@/lib/values";

const FIELD = "rounded-md border border-line bg-sheet px-1.5 py-0.5";
/** Annotating with AI before there is a plan (user 2026-10-28: rings, a button and "1/50
 * expected" read as runnable while the server refuses it with no plan): what is missing and where
 * it is made, the left, as a plan is made by asking the steward (the right shows the images only). */
export function NoPlanBand() {
  return (
    <div
      role="region"
      aria-label={t("select.label")}
      className="sticky top-(--gallery-head) z-20 flex flex-col gap-1.5 border-b-2 border-ink bg-sheet px-5 py-2 text-body"
    >
      <DecideLine>
        <span>{t("decide.noPlan")}</span>
        <AskSteward />
      </DecideLine>
    </div>
  );
}

export function RunDecisionBar({
  datasetId,
  items,
  shown,
  by,
  going,
  onTargets,
  onSeePlan,
}: {
  datasetId: string;
  items: GalleryItem[];
  /** The images the filter shows now: "choose the shown" chooses them. */
  shown: string[];
  /** What narrows what is shown, said on "choose the shown". */
  by: Narrowing;
  /** The run of the dataset waiting or going (none: none). */
  going: Run | null;
  /** The cards the decide button works on, marked while it is pointed at. */
  onTargets: (ids: string[]) => void;
  /** Open the plan it runs, as it holds it. */
  onSeePlan: (target: PlanTarget) => void;
}) {
  const decision = useRunDecision(datasetId);
  // The chat the left shows (none chosen: the steward's latest), told what came of it (81).
  const [chatOf] = useChatOf(placeKey(datasetId));
  const chat = chatOf.steward ?? null;
  const { box, images, changes, body } = decision;
  const preview = useRunPreview(datasetId, body);
  const models = useApi<RunModels>("/v1/run-models");
  const agents = useApi<{ agents: AgentInfo[] }>(`/v1/datasets/${datasetId}/agents`);
  const [changing, setChanging] = useState(false);
  const [details, setDetails] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const modelName = useModelName();
  const card = (preview.data?.preview.card ?? null) as RunCard | null;
  const view = card ? runCardView(card, images, modelName) : null;
  const names = new Map(items.map((i) => [i.image.id, i.image.name]));
  // While a worker answers, its answer may write the plan: no run is decided (11.10); nor while
  // another run holds some of its images (18.13).
  const held = heldSaid(card);
  const blocked = workersAnswering(agents.data?.agents ?? [])
    ? t("decide.writing")
    : held
      ? t(...held)
      : undefined;
  const args = { ...(preview.data?.args ?? body?.args) };
  const model = models.data?.models.find((m) => m.model === textOf(args.model));
  // What deciding does, in the words of the line on the left (lib/decisions).
  const label = t(
    ...decideLabel(
      box
        ? { ...box, args: { ...box.args, ...changes }, preview: preview.data?.preview }
        : { tool: "run_start", args: { image_ids: images }, preview: preview.data?.preview },
      (id) => names.get(id),
    ),
  );
  const split = runSplit(items, images);

  async function act(task: () => Promise<void>, done: string) {
    setBusy(true);
    try {
      await task();
      toast.success(done);
    } catch (reason) {
      toast.error(errorText(reason));
      invalidate(datasetId);
    } finally {
      setBusy(false);
    }
  }
  const start = () =>
    void act(async () => {
      setConfirming(false);
      if (!body) return;
      await decideRun(datasetId, box, body, preview.data, chat);
      if (!box) decision.setImages([]);
    }, t("band.decided"));

  return (
    <div
      role="region"
      aria-label={t("select.label")}
      className="sticky top-(--gallery-head) z-20 flex flex-col gap-1.5 border-b-2 border-ink bg-sheet px-5 py-2 text-body"
    >
      {going && <RunBar run={going} onChanged={() => invalidate(datasetId)} />}
      {/* Choosing (not recorded) and deciding (recorded), each its line (user 2026-10-27). */}
      <ChooseLine
        who={images.length || box ? runWho(box, changes, images.length) : t("select.none")}
        hint={!images.length && !box}
        by={by}
        shown={shown}
        chosen={images}
        onChosen={decision.setImages}
        // A box keeps waiting with none of its images; one's own choice goes with its values.
        onClear={() =>
          box
            ? decision.setImages([])
            : void letGo(datasetId, null, () => decision.setImages([]), chat)
        }
      >
        {images.some((id) => !shown.includes(id)) && (
          <span className="text-muted-foreground">
            {t("select.hidden", { count: images.filter((id) => !shown.includes(id)).length })}
          </span>
        )}
      </ChooseLine>
      <DecideLine>
        <Button
          size="small"
          variant="primary"
          disabled={!body || !preview.data || busy || Boolean(blocked)}
          title={!body ? t("select.run.why") : blocked}
          onMouseEnter={() => onTargets(images)}
          onMouseLeave={() => onTargets([])}
          onFocus={() => onTargets(images)}
          onBlur={() => onTargets([])}
          onClick={() => (heavyOf(preview.data?.preview) ? setConfirming(true) : start())}
        >
          {body ? label : t("select.run.none")}
          {body && heavyOf(preview.data?.preview) ? t("decide.bar.more") : ""}
        </Button>
        {box && (
          <Button
            size="small"
            disabled={busy}
            onClick={() =>
              void act(
                () => letGo(datasetId, box, () => decision.setImages([]), chat),
                t("band.declined"),
              )
            }
          >
            {t("band.decline")}
          </Button>
        )}
        {view && <span className="text-muted-foreground">{runLine(view)}</span>}
        {body && (
          <>
            <Button
              variant="link"
              size="small"
              aria-expanded={changing}
              onClick={() => setChanging(!changing)}
            >
              {t(changing ? "decide.bar.changed" : "decide.bar.change")}
            </Button>
            <Button variant="link" size="small" onClick={() => setDetails(true)}>
              {t("decide.bar.details")}
            </Button>
            {preview.data && (
              <Button
                variant="link"
                size="small"
                onClick={() =>
                  onSeePlan(
                    planToOpen({ args: preview.data!.args, preview: preview.data!.preview }),
                  )
                }
              >
                {t("record.plan.open")}
              </Button>
            )}
          </>
        )}
        {/* Why it cannot be decided now, beside it. */}
        {blocked && <span className="text-xs">{blocked}</span>}
        {/* Expected, shown even before anything is chosen (user 2026-10-16). */}
        <span className="text-muted-foreground">
          {t("select.run.after", { after: annotatedAfter(items, images), total: items.length })}
        </span>
        {split.again > 0 && (
          <span className="text-muted-foreground">
            {t("select.split", { fresh: split.fresh, again: split.again })}
          </span>
        )}
      </DecideLine>
      {body && changing && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <label className="flex items-center gap-1.5">
            <span className="text-muted-foreground">{t("box.key.model")}</span>
            <select
              className={FIELD}
              value={textOf(args.model)}
              onChange={(e) => {
                // Another model takes its own default effort (each model has its own).
                const chosen = models.data?.models.find((m) => m.model === e.target.value);
                decision.setValues({
                  model: e.target.value,
                  effort: chosen?.default_effort ?? undefined,
                });
              }}
            >
              {(models.data?.models ?? []).map((m) => (
                <option key={m.model} value={m.model}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </label>
          {model && (
            <label className="flex items-center gap-1.5">
              <span className="text-muted-foreground">{t("box.key.effort")}</span>
              <select
                className={FIELD}
                value={textOf(args.effort)}
                onChange={(e) => decision.setValues({ effort: e.target.value })}
              >
                {model.efforts.map((effort) => (
                  <option key={effort} value={effort}>
                    {effort}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="flex items-center gap-1.5">
            <span className="text-muted-foreground">{t("work.decision.budget")}</span>
            <input
              className={`${FIELD} w-20`}
              inputMode="decimal"
              value={textOf(args.budget_per_image_usd)}
              onChange={(e) => decision.setValues({ budget_per_image_usd: e.target.value })}
            />
            <span className="text-muted-foreground">
              {t(
                "work.decision.budgetTotal",
                budgetWords(args.budget_per_image_usd, card?.happens.images ?? 0),
              )}
            </span>
          </label>
        </div>
      )}
      <Confirm
        open={confirming}
        title={t("decide.irreversible")}
        // What starts: as the button and the line beside it say it.
        message={view ? `${label}${t("decide.bar.join")}${runLine(view)}` : label}
        confirm={t("decide.start")}
        cancel={t("reply.cancel")}
        onConfirm={start}
        onCancel={() => setConfirming(false)}
      />
      <Dialog open={details} onOpenChange={setDetails} title={label} wide>
        <div className="px-5 py-4">
          {view && <RunCardView view={view} nameOf={(id) => names.get(id) ?? id} />}
        </div>
      </Dialog>
    </div>
  );
}
