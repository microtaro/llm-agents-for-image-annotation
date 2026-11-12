// A worker's mark wherever the right side points at a worker (user 2026-10-15: "ask Plan" read as
// asking the plan, a thing, and the library card's round mark was not the left's): the same
// rounded square as the worker's button at the top left, small, beside the words.
import type { AgentKey } from "@/api/types";
import { t } from "@/i18n";

export function AgentMark({ agent }: { agent: AgentKey }) {
  return (
    <span
      role="img"
      aria-label={t(`agent.${agent}`)}
      title={t(`agent.${agent}`)}
      className="inline-grid size-5 shrink-0 place-items-center rounded-[5px] border border-line bg-surface text-note font-semibold text-action no-underline"
    >
      {t(`agent.${agent}.icon`)}
    </span>
  );
}
