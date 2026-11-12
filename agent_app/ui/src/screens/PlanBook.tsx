// The plan as the interview made it (definition 26.7): what it is for, the requirement's tree
// (what changed since the latest version marked), what to leave out, the references (results
// chosen, definition 38.1), the words to the worker AI and the samples; each row says who decided
// it (a worker, a person) or that it is being asked now. Folded to one line while a question shows
// something else above it (one decision at a time). A person changes it here too: an attribute, a
// rule, a reference taken out.
import { toast } from "sonner";
import { api } from "@/api/client";
import type {
  AttributeDefinition,
  PlanInput,
  InstructionDraft,
  LabelDefinition,
  PlanItemName,
  PlanState,
  Run,
} from "@/api/types";
import type { FigureImage } from "@/components/PlanFigure";
import { FoldText, TEXT_LINES } from "@/components/FoldText";
import { RequirementTree } from "@/components/RequirementTree";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { errorText } from "@/lib/errorText";
import { withAttribute, withLeaveOut, withoutAttribute } from "@/lib/planEdits";
import { summaryLine } from "@/lib/planParts";
import { chooseReference } from "@/lib/reference";
import { versionOf } from "@/lib/runChoice";
import { schemaRows } from "@/lib/requirementTree";
import { invalidate, useApi } from "@/lib/useApi";
import { type FieldWriting, usePlanWriting } from "@/lib/viewState";
import { PlanGets } from "./PlanGets";
import { ReferenceFigure } from "./ReferenceFigure";
import { AskSteward } from "./AskSteward";

const FIELD = "rounded-md border border-line bg-surface px-2 py-0.5";

function PlanRow({
  name,
  tag,
  children,
}: {
  name: string;
  tag?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[11rem_minmax(0,1fr)_auto] items-baseline gap-3 border-b border-line px-4 py-2 last:border-b-0 max-[600px]:grid-cols-1">
      <span className="text-body text-muted-foreground">{name}</span>
      <div className="min-w-0 text-body">{children}</div>
      <span className="flex flex-wrap items-center justify-end gap-1.5">{tag}</span>
    </div>
  );
}

const NO_FIELD: FieldWriting = { name: "", type: "text", choices: "" };

function NewAttribute({
  value: { name, type, choices },
  onValue,
  onAdd,
}: {
  /** What is written (kept by the plan, so the right moving away loses none of it). */
  value: FieldWriting;
  onValue: (next: FieldWriting) => void;
  /** Written into the draft: true once it is (the words go then, not when refused). */
  onAdd: (a: Pick<AttributeDefinition, "name" | "type" | "choices">) => Promise<boolean>;
}) {
  const setName = (next: string) => onValue({ name: next, type, choices });
  const setType = (next: AttributeDefinition["type"]) => onValue({ name, type: next, choices });
  const setChoices = (next: string) => onValue({ name, type, choices: next });
  return (
    <form
      className="mt-1.5 flex flex-wrap items-center gap-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!name.trim()) return;
        void onAdd({
          name: name.trim(),
          type,
          choices:
            type === "choice"
              ? choices
                  .split(/[,/\u3001\uff0c\uff0f]/)
                  .map((c) => c.trim())
                  .filter(Boolean)
              : null,
        }).then((done) => done && onValue({ ...NO_FIELD, type }));
      }}
    >
      <input
        aria-label={t("book.attr.name")}
        placeholder={t("book.attr.name")}
        className={FIELD}
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <select
        aria-label={t("book.attr.type")}
        className={FIELD}
        value={type}
        onChange={(e) => setType(e.target.value as AttributeDefinition["type"])}
      >
        {(["text", "number", "choice"] as const).map((k) => (
          <option key={k} value={k}>
            {t(`book.attr.type.${k}`)}
          </option>
        ))}
      </select>
      {type === "choice" && (
        <input
          aria-label={t("book.attr.choices")}
          placeholder={t("book.attr.choices")}
          className={FIELD}
          value={choices}
          onChange={(e) => setChoices(e.target.value)}
        />
      )}
      <Button size="small" type="submit">
        {t("book.attr.add")}
      </Button>
    </form>
  );
}

export function PlanBook({
  datasetId,
  state,
  purpose,
  base,
  colors,
  images,
  folded,
  asking,
  trial,
}: {
  datasetId: string;
  state: PlanState;
  purpose: string;
  /** The latest version's labels while a draft is the plan (what changed since is marked). */
  base: LabelDefinition[] | null;
  colors: Record<string, string>;
  images: Map<string, FigureImage>;
  folded: boolean;
  /** The item a question asks about now. */
  asking: PlanItemName | null;
  /** The newest samples, whatever version made them (user 2026-10-27). */
  trial: Run | undefined;
}) {
  const path = `/v1/datasets/${datasetId}/drafts/instruction`;
  const draft = useApi<InstructionDraft>(path);
  const [writing, setWriting] = usePlanWriting(datasetId);
  const editing = writing.editing ?? null;
  const setEditing = (next: "requirement" | "leave_out" | null) =>
    setWriting({ ...writing, editing: next ?? undefined });
  const rule = writing.rule ?? "";
  const setRule = (next: string) => setWriting({ ...writing, rule: next });
  const plan = state.plan;
  if (!plan)
    // No plan yet (user 2026-10-28: the right showed the images only, nothing of a plan or of
    // where it is made): the book's place says so, and that it is made by asking the steward.
    return (
      <div className="flex flex-wrap items-baseline gap-3 rounded-md border border-line bg-surface px-4 py-2">
        <h2 className="m-0 shrink-0 text-large">{t("book.title")}</h2>
        <span className="text-body text-muted-foreground">{t("book.none")}</span>
        <AskSteward />
      </div>
    );
  const status = new Map(state.items.map((i) => [i.item, i.status]));
  // A change into the draft; refused (the worker wrote it since, 409), the draft is read again
  // and what was written stays to be pressed again.
  const write = (next: PlanInput) =>
    api(path, {
      method: "PUT",
      body: { ...next, ...(draft.data ? { if_updated_at: draft.data.updated_at } : {}) },
    })
      .then(() => true)
      .catch((reason) => {
        toast.error(errorText(reason));
        return false;
      })
      .finally(() => invalidate(datasetId));
  const tag = (item: PlanItemName, edit?: "requirement" | "leave_out") => (
    <>
      {asking === item ? (
        <span className="rounded-sm border border-processing bg-draft px-1.5 text-note font-semibold">
          {t("book.asking")}
        </span>
      ) : status.get(item) === "agent" ? (
        <span className="rounded-sm border border-line px-1.5 text-note text-muted-foreground">
          {t("book.byAgent")}
        </span>
      ) : status.get(item) === "person" ? (
        <span className="rounded-sm border border-ink px-1.5 text-note">{t("book.byPerson")}</span>
      ) : null}
      {edit && (
        <Button
          variant="link"
          size="small"
          aria-expanded={editing === edit}
          onClick={() => setEditing(editing === edit ? null : edit)}
        >
          {t(editing === edit ? "common.close" : "book.edit")}
        </Button>
      )}
    </>
  );
  // A reference is a result chosen (definition 38.1): taken out here, chosen on a result.
  const unset = (imageId: string) =>
    void chooseReference(datasetId, imageId, null).catch((reason) =>
      toast.error(errorText(reason)),
    );
  const book = (
    <div className="flex flex-col">
      <PlanRow name={t("book.what")}>{purpose}</PlanRow>
      <PlanRow name={t("plan.item.requirement")} tag={tag("requirement", "requirement")}>
        <RequirementTree
          rows={schemaRows(plan.label_definitions, base ? { base } : {})}
          root={t("tree.root.schema")}
          colors={colors}
          descriptions={Object.fromEntries(
            plan.label_definitions.map((d) => [d.name, d.description]),
          )}
        />
        {editing === "requirement" &&
          plan.label_definitions.map((d) => (
            <div key={d.name} className="mt-2 border-t border-line pt-1.5">
              <b>{d.name}</b>
              <span className="ml-2 inline-flex flex-wrap gap-1">
                {d.attributes.map((a) => (
                  <Button
                    key={a.name}
                    size="small"
                    aria-label={t("book.attr.remove", { name: a.name })}
                    onClick={() => void write(withoutAttribute(plan, d.name, a.name))}
                  >
                    {a.name} ×
                  </Button>
                ))}
              </span>
              <NewAttribute
                value={writing.fields?.[d.name] ?? NO_FIELD}
                onValue={(next) =>
                  setWriting({ ...writing, fields: { ...writing.fields, [d.name]: next } })
                }
                onAdd={(a) => write(withAttribute(plan, d.name, a))}
              />
            </div>
          ))}
      </PlanRow>
      <PlanRow name={t("plan.item.leave_out")} tag={tag("leave_out", "leave_out")}>
        {plan.leave_out.length > 0 && (
          <ul className="m-0 flex flex-col gap-0.5 p-0">
            {plan.leave_out.map((r) => (
              <li key={r}>
                {r}
                {editing === "leave_out" && (
                  <Button
                    variant="link"
                    size="small"
                    aria-label={t("book.rule.remove", { rule: r })}
                    onClick={() =>
                      void write(
                        withLeaveOut(
                          plan,
                          plan.leave_out.filter((x) => x !== r),
                        ),
                      )
                    }
                  >
                    ×
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
        {editing === "leave_out" && (
          <form
            className="mt-1.5 flex flex-wrap gap-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              if (!rule.trim()) return;
              void write(withLeaveOut(plan, [...plan.leave_out, rule])).then(
                (done) => done && setRule(""),
              );
            }}
          >
            <input
              aria-label={t("book.rule.new")}
              placeholder={t("book.rule.new")}
              className={`${FIELD} min-w-[16rem] flex-1`}
              value={rule}
              onChange={(e) => setRule(e.target.value)}
            />
            <Button size="small" type="submit">
              {t("book.rule.add")}
            </Button>
          </form>
        )}
      </PlanRow>
      <PlanRow name={t("plan.item.references")} tag={tag("references")}>
        {/* Seen as the worker AI sees them (user 2026-10-27: named, not shown). */}
        {plan.references.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {plan.references.map((r) => (
              <ReferenceFigure
                key={r.image_id}
                reference={r}
                image={images.get(r.image_id)}
                colors={colors}
                width={180}
              >
                <Button
                  variant="link"
                  size="small"
                  className="self-start"
                  onClick={() => unset(r.image_id)}
                >
                  {t("ref.unset")}
                </Button>
              </ReferenceFigure>
            ))}
          </div>
        )}
      </PlanRow>
      <PlanRow name={t("plan.item.text")} tag={tag("text")}>
        {plan.text && (
          <FoldText lines={TEXT_LINES}>
            <p className="m-0 whitespace-pre-wrap">{plan.text}</p>
          </FoldText>
        )}
      </PlanRow>
      <PlanRow name={t("plan.item.trial")} tag={tag("trial")}>
        {(() => {
          const tried = state.items.find((i) => i.item === "trial")?.summary as {
            revision: number;
            trials: number;
            runs: number;
          } | null;
          // The samples made, by their record and version (user 2026-10-27: "version 2, once"
          // counted a run that was not the samples, and the samples of version 1 were gone).
          if (trial)
            return t("trial.record", {
              run: trial.number ?? "",
              version: versionOf(trial.instruction_revision),
              count: trial.total,
            });
          return tried ? t("book.tried", { revision: tried.revision, runs: tried.runs }) : null;
        })()}
      </PlanRow>
    </div>
  );
  return (
    <details
      open={!folded || undefined}
      className="group rounded-md border border-line bg-surface"
      // Folded by the screen while a question shows something above; opened by the person.
      key={folded ? "folded" : "open"}
    >
      <summary className="flex cursor-pointer items-baseline gap-3 border-b border-line px-4 py-2 [&::-webkit-details-marker]:hidden">
        <h2 className="m-0 shrink-0 text-large">{t("book.title")}</h2>
        <span className="min-w-0 truncate text-body text-muted-foreground">
          {summaryLine(plan.label_definitions)}
        </span>
        <span className="ml-auto shrink-0 text-body text-action underline">
          <span className="group-open:hidden">{t("book.open")}</span>
          <span className="hidden group-open:inline">{t("book.close")}</span>
        </span>
      </summary>
      {book}
      {/* What the worker AI reads with the plan (definition 55): part of the book, open and
          folded with it (user 2026-10-27: shown under some plans and not others). */}
      <div className="border-t border-line px-4 py-3">
        <PlanGets />
      </div>
    </details>
  );
}
