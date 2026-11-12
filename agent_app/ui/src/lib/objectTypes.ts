// What the screen says of a type besides its rows, in one place (definition 72: it was written
// into the shared set screen): the types of the app rather than of a dataset, which no plan
// judges, and the condition fields whose values are said by words of their own.
import type { ObjectType } from "@/api/types";
import { t } from "@/i18n";

/** The app's types, of no dataset: their screen says no plan (definition 71). */
export const APP_TYPES: readonly ObjectType[] = ["settings"];

/** A condition's value in words, for the fields that have words of their own: a settings group
 * by its heading on the settings screen. */
export const FIELD_VALUES: Readonly<Record<string, (value: string) => string>> = {
  group: (value) => t(`settings.group.${value}`),
};
