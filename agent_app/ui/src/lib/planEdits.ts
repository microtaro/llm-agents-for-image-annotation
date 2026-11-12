// What a person changes in the plan on the right (definition 26.4, 26.7): an attribute taken out
// of a label or added to it, a rule of what to leave out added or taken out. Each gives the plan
// written as the draft (its references are chosen by their own entries, definition 38.1).
import type { AttributeDefinition, PlanInput } from "@/api/types";

/** The plan as the draft is written: its text, labels and what it leaves out. */
export function contentOf(plan: PlanInput): PlanInput {
  return {
    text: plan.text,
    label_definitions: plan.label_definitions,
    leave_out: plan.leave_out,
  };
}

export function withoutAttribute(plan: PlanInput, label: string, name: string): PlanInput {
  return {
    ...contentOf(plan),
    label_definitions: plan.label_definitions.map((d) =>
      d.name === label ? { ...d, attributes: d.attributes.filter((a) => a.name !== name) } : d,
    ),
  };
}

export function withAttribute(
  plan: PlanInput,
  label: string,
  attribute: Pick<AttributeDefinition, "name" | "type" | "choices">,
): PlanInput {
  return {
    ...contentOf(plan),
    label_definitions: plan.label_definitions.map((d) =>
      d.name === label && !d.attributes.some((a) => a.name === attribute.name)
        ? {
            ...d,
            attributes: [
              ...d.attributes,
              {
                name: attribute.name,
                type: attribute.type,
                choices: attribute.type === "choice" ? attribute.choices : null,
                description: "",
              },
            ],
          }
        : d,
    ),
  };
}

export function withLeaveOut(plan: PlanInput, rules: string[]): PlanInput {
  const kept = rules.map((r) => r.trim()).filter(Boolean);
  return { ...contentOf(plan), leave_out: [...new Set(kept)] };
}
