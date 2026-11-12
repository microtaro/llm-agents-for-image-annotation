// The app's settings a person can see and change, in the server's groups (models, cost, each
// image, at once, stopping and trying again; a run copies its settings when it starts), the
// language and text size of the screen (this browser only; changes at once, no Save), how big
// the data kept is and the software's version.
import { ThemeToggle } from "@/components/ThemeToggle";
import { useEffect, useState } from "react";
import { BackButton } from "@/components/BackButton";
import { go } from "@/lib/route";
import { toast } from "sonner";
import { api, type ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { has, setLang, t, useLang } from "@/i18n";
import { errorText } from "@/lib/errorText";
import { problemOf } from "@/lib/settingsForm";
import { useApi } from "@/lib/useApi";
import type { RunModels } from "@/api/types";
import { setTextSize, SIZES, STANDARD, useTextSize } from "@/lib/textSize";
import { formatBytes } from "@/lib/bytes";
import { StorageSection } from "./SettingsStorage";

interface AppSettings {
  target_timeout_seconds: number;
  max_mcp_calls: number;
  worker_view_max_side: number;
  mcp_tool_timeout_seconds: number;
  usd_to_jpy: number;
  run_budget_per_image_usd: number;
  /** The model of the workers' answers with tools (step 24; never Haiku 5.5). */
  agent_model: string;
  agent_effort: string;
  /** The model a run takes when none is chosen (user 2026-10-27; never Haiku 5.5). */
  run_model: string;
  run_effort: string;
  worker_prompt: string;
  /** The allowed range of each number, from the server. */
  ranges: Record<string, [number, number]>;
  /** The groups the settings are shown in, in order, from the server (user 2026-10-29). */
  groups: [string, string[]][];
  /** This machine's facts: the software's version and the memory free now, in MB. */
  machine: { version: string; free_memory_mb: number | null };
}

export function Settings() {
  const lang = useLang();
  const loaded = useApi<AppSettings>("/v1/settings");
  // Haiku 5.5 only judges quickly (user 2026-10-08: it cannot do the heavy answers).
  const models = useApi<RunModels>("/v1/run-models");
  const heavy = (models.data?.models ?? []).filter((m) => m.model !== "claude-haiku-5-5");
  const [form, setForm] = useState<AppSettings | null>(null);
  const textSize = useTextSize();
  // The numbers as typed, so an emptied field stays empty instead of becoming 0.
  const [typed, setTyped] = useState<Record<string, string>>({});
  useEffect(() => {
    setForm(loaded.data);
    if (loaded.data)
      setTyped(
        Object.fromEntries(
          Object.keys(loaded.data.ranges).map((k) => [
            k,
            String((loaded.data?.[k as keyof AppSettings] as number | undefined) ?? ""),
          ]),
        ),
      );
  }, [loaded.data]);
  const problems = Object.fromEntries(
    Object.entries(form?.ranges ?? {}).map(([k, range]) => [
      k,
      problemOf(k, typed[k] ?? "", range),
    ]),
  );
  const ready = Object.values(problems).every((p) => p === null);

  async function save() {
    if (!form) return;
    try {
      const { worker_prompt: _, ranges: __, groups: ___, machine: ____, ...rest } = form;
      const body = {
        ...rest,
        ...Object.fromEntries(Object.keys(form.ranges).map((k) => [k, Number(typed[k])])),
      };
      const saved = await api<AppSettings>("/v1/settings", { method: "PUT", body });
      setForm(saved);
      toast.success(t("settings.saved"));
    } catch (reason) {
      const error = reason as ApiError;
      const { key, minimum, maximum } = error.details as Record<string, number>;
      toast.error(
        error.code === "invalid_setting"
          ? t("settings.invalid", { name: t(`settings.${key}`), min: minimum, max: maximum })
          : errorText(error),
      );
    }
  }

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center gap-3.5 border-b border-line bg-sheet px-7 py-3.5">
        {/* Back to where settings were opened from; settings are the whole app's, not the
            library's (user 2026-10-14: "library › settings" put them under the library). */}
        <BackButton fallback={() => go({ screen: "library" })} />
        <h1 className="m-0 text-lg">{t("settings.title")}</h1>
        {/* Beside the title, where it is found without scrolling (user 2026-10-29). */}
        {form && (
          <span className="text-xs text-muted-foreground">
            {t("settings.version", { version: form.machine.version })}
          </span>
        )}
        {/* The memory free now: what the answers and runs wait for (2026-10-30: it was on no
            screen a person opens, and a 16 GB machine's answers waited for it). */}
        {form?.machine.free_memory_mb != null && (
          <span
            className="text-xs text-muted-foreground"
            title={t("objects.settings.free_memory_mb.tip")}
          >
            {t("settings.freeMemory", {
              size: formatBytes(form.machine.free_memory_mb * 1024 * 1024),
            })}
          </span>
        )}
        <span className="flex-1" />
        <ThemeToggle />
      </header>
      {form && (
        <main className="mx-auto flex max-w-[860px] flex-col gap-4 px-7 py-6">
          <section className="flex flex-col gap-2 rounded-md border border-line bg-sheet p-4">
            <h2 className="m-0 text-base">{t("settings.group.display")}</h2>
            <label className="flex items-center gap-3">
              {t("common.language")}
              <select
                className="rounded-md border border-line bg-surface px-2 py-1"
                value={lang}
                onChange={(event) => setLang(event.target.value as "ja" | "en")}
              >
                <option value="ja">{t("lang.ja")}</option>
                <option value="en">{t("lang.en")}</option>
              </select>
            </label>
            <p className="m-0 text-xs text-muted-foreground">{t("settings.language.note")}</p>
            {/* This browser's too, at once (user 2026-10-14). */}
            <label className="flex items-center gap-3">
              {t("settings.text_size")}
              <select
                className="rounded-md border border-line bg-surface px-2 py-1"
                value={textSize}
                onChange={(event) => setTextSize(Number(event.target.value))}
              >
                {SIZES.map((size) => (
                  <option key={size} value={size}>
                    {t(
                      size === STANDARD ? "settings.text_size.standard" : "settings.text_size.px",
                      {
                        size,
                      },
                    )}
                  </option>
                ))}
              </select>
            </label>
            <p className="m-0 text-xs text-muted-foreground">{t("settings.text_size.note")}</p>
          </section>
          {/* One grid for every group, so the fields line up from group to group. */}
          <div className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-3 rounded-md border border-line bg-sheet p-4">
            {form.groups.map(([group, keys], index) => (
              <div key={group} className="contents">
                <h2 className={`col-span-2 m-0 text-base ${index > 0 ? "mt-3" : ""}`}>
                  {t(`settings.group.${group}`)}
                </h2>
                {keys.map((key) =>
                  key === "agent_model" || key === "run_model" ? (
                    <ModelChoice
                      key={key}
                      name={t(`settings.${key}`)}
                      tip={t(`settings.${key}.tip`)}
                      note={t(`settings.${key}.note`)}
                      models={heavy}
                      model={form[key]}
                      effort={form[key === "agent_model" ? "agent_effort" : "run_effort"]}
                      onChange={(model, effort) =>
                        setForm({
                          ...form,
                          [key]: model,
                          [key === "agent_model" ? "agent_effort" : "run_effort"]: effort,
                        })
                      }
                    />
                  ) : (
                    <NumberField
                      key={key}
                      name={key}
                      range={form.ranges[key]}
                      typed={typed[key] ?? ""}
                      problem={problems[key]}
                      onChange={(value) => setTyped({ ...typed, [key]: value })}
                    />
                  ),
                )}
              </div>
            ))}
          </div>
          <div className="flex justify-end">
            <Button variant="primary" disabled={!ready} onClick={save}>
              {t("common.save")}
            </Button>
          </div>
          <StorageSection />
          <details className="rounded-md border border-line bg-sheet p-3">
            <summary className="cursor-pointer font-semibold">
              {t("settings.worker_prompt")}
            </summary>
            <pre className="m-0 mt-2 whitespace-pre-wrap font-mono text-xs">
              {form.worker_prompt}
            </pre>
          </details>
        </main>
      )}
    </div>
  );
}

/** A number setting: its name (what it is on the mouse, where the name alone reads two ways;
 * user 2026-10-28, the cost limit), its field and range, and what is wrong with what was typed. */
function NumberField({
  name,
  range: [min, max],
  typed,
  problem,
  onChange,
}: {
  name: string;
  range: [number, number];
  typed: string;
  problem: string | null;
  onChange: (value: string) => void;
}) {
  return (
    <label className="contents">
      <span title={has(`settings.${name}.tip`) ? t(`settings.${name}.tip`) : undefined}>
        {t(`settings.${name}`)}
      </span>
      <span className="flex items-center gap-2">
        <input
          type="number"
          min={min}
          max={max}
          value={typed}
          aria-invalid={problem !== null}
          onChange={(e) => onChange(e.target.value)}
          className="w-32 rounded-md border border-line bg-surface px-2 py-1"
        />
        <span className="text-xs text-muted-foreground">
          {t("settings.range", { min, max })}
          {/* Why the range is what it is, where it is not plain (the image size). */}
          {has(`settings.${name}.note`) && ` · ${t(`settings.${name}.note`)}`}
        </span>
        {problem && <span className="text-xs text-failed">{t(`settings.problem.${problem}`)}</span>}
      </span>
    </label>
  );
}

/** A model and its effort, the effort kept when the next model has it, else its own default. */
function ModelChoice({
  name,
  tip,
  note,
  models,
  model,
  effort,
  onChange,
}: {
  name: string;
  /** What it does (the dictionary's, the one place the workers read too; definition 72). */
  tip: string;
  note: string;
  models: RunModels["models"];
  model: string;
  effort: string;
  onChange: (model: string, effort: string) => void;
}) {
  const efforts = models.find((m) => m.model === model)?.efforts ?? [];
  return (
    <label className="contents">
      <span title={tip}>{name}</span>
      <span className="flex flex-wrap items-center gap-2">
        <select
          value={model}
          onChange={(e) => {
            const next = models.find((m) => m.model === e.target.value);
            onChange(
              e.target.value,
              next?.efforts.includes(effort) ? effort : (next?.default_effort ?? effort),
            );
          }}
          className="rounded-md border border-line bg-surface px-2 py-1"
        >
          {models.map((m) => (
            <option key={m.model} value={m.model}>
              {m.display_name}
            </option>
          ))}
        </select>
        <select
          value={effort}
          aria-label={t("settings.effort", { name })}
          onChange={(e) => onChange(model, e.target.value)}
          className="rounded-md border border-line bg-surface px-2 py-1"
        >
          {efforts.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <span className="text-xs text-muted-foreground">{note}</span>
      </span>
    </label>
  );
}
