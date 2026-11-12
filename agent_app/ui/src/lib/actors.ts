// Who did a thing, as the server says it (definition 21.2): the person, a worker
// (agent:<worker>), the server by itself or the outside connection; named here once.
import { t } from "@/i18n";

export const PERSON = "person";

/** The name of who did a thing, for the screen. */
export function actorName(who: string | null | undefined): string {
  if (who?.startsWith("agent:")) return t(`agent.${who.slice(6)}`);
  return t(`actor.${who === PERSON || who === "server" ? who : "outside"}`);
}
