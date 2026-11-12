// What a person reads when the API refuses: the code's own words from the dictionary, and for
// an invalid input which field and what is wrong (found 2026-10-05: "The request is not valid"
// in English on the Japanese screen). Falls back to the server's message.
import { ApiError } from "@/api/client";
import { has, t } from "@/i18n";

interface Problem {
  at: string;
  message: string;
  type?: string;
  limit?: number | null;
}

/** "label definitions 1 · attributes 1 · name" from "body.label_definitions.0.attributes.0.name". */
export function fieldName(at: string): string {
  const parts: string[] = [];
  for (const segment of at.split(".")) {
    if (segment === "body" || segment === "query" || segment === "path") continue;
    if (/^\d+$/.test(segment) && parts.length) parts[parts.length - 1] += ` ${Number(segment) + 1}`;
    else parts.push(has(`field.${segment}`) ? t(`field.${segment}`) : segment);
  }
  return parts.join(" · ");
}

export function problemText(problem: Problem): string {
  const key = `problem.${problem.type}`;
  return problem.type && has(key) ? t(key, { limit: problem.limit ?? "" }) : problem.message;
}

export function errorText(reason: unknown): string {
  if (!(reason instanceof ApiError)) return (reason as Error)?.message ?? String(reason);
  const problems = (reason.details?.problems ?? []) as Problem[];
  if (reason.code === "invalid_input" && problems.length) {
    return t("error.fields", {
      list: problems
        .slice(0, 3)
        .map((p) => `${fieldName(p.at)}: ${problemText(p)}`)
        .join(" / "),
    });
  }
  if (reason.code === "invalid_definition") {
    const vars = reason.details as Record<string, string>;
    const why = `error.definition.${vars.reason ?? ""}`;
    if (has(why)) return t(why, vars);
  }
  const key = `error.${reason.code}`;
  const vars = Object.fromEntries(
    Object.entries(reason.details ?? {}).filter(([, v]) => typeof v !== "object"),
  ) as Record<string, string | number>;
  return has(key) ? t(key, vars) : reason.message;
}
