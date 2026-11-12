// What the worker AI reads besides the plan (definition 18.15, user 2026-10-17: scattered, they
// can contradict): the server's fixed rules (how to use the tools, the answer's form) and the
// shared notes of every dataset, seen and changed here (definition 55). The plan wins where it
// says otherwise. Shown under the plan.
import { t } from "@/i18n";
import { useApi } from "@/lib/useApi";
import { SharedNotes } from "./SharedNotes";

export function PlanGets() {
  const rules = useApi<{ text: string }>("/v1/worker-rules");
  return (
    <section aria-label={t("plan.gets.title")} className="flex flex-col gap-1.5">
      <h3 className="m-0 text-lead">{t("plan.gets.title")}</h3>
      <p className="m-0 text-xs text-muted-foreground">{t("plan.gets.note")}</p>
      <details className="rounded-md border border-line bg-surface px-2.5 py-1.5">
        <summary className="cursor-pointer">
          {t("plan.gets.rules")}{" "}
          <span className="text-xs text-action underline">{t("common.showAll")}</span>
        </summary>
        <pre className="m-0 mt-1.5 max-h-80 overflow-auto whitespace-pre-wrap text-xs">
          {rules.data?.text ?? "…"}
        </pre>
      </details>
      <SharedNotes />
    </section>
  );
}
