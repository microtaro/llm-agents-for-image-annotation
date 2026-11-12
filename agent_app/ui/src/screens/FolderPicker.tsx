// Choose where images come from: server-local folders or files, typed or chosen in the Windows
// window (definition 43), previewed before anything is imported, which of the found images to
// take (all at first), and whether they were photographed or generated (data-model 2).
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { PickedFolder, ScanResult, Written } from "@/api/types";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { errorText } from "@/lib/errorText";
import { leftOutBy } from "@/lib/pickNames";
import { useLastFolder } from "@/lib/viewState";
import { skipText } from "@/lib/skips";

export interface Picked {
  paths: string[];
  origin: { kind: "generated"; how: { note: string } } | null;
  count: number;
  /** A folder written out, as the scan told it (definition 60.3); null: images. */
  written: Written | null;
}

export function FolderPicker({ onChange }: { onChange: (picked: Picked) => void }) {
  const [paths, setPaths] = useState<string[]>([""]);
  const [generated, setGenerated] = useState(false);
  const [how, setHow] = useState("");
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The found files left out (unchecked); everything found is taken unless left out.
  const [left, setLeft] = useState<Set<string>>(new Set());
  const [names, setNames] = useState("");
  // The row whose Windows window is open (the request waits until it closes).
  const [choosing, setChoosing] = useState<number | null>(null);
  const [lastFolder, setLastFolder] = useLastFolder();
  const given = paths.map((p) => p.trim()).filter(Boolean);
  const key = given.join("\n");

  useEffect(() => {
    if (!key) {
      setScan(null);
      return;
    }
    const timer = window.setTimeout(() => {
      api<ScanResult>("/v1/local-images/scan", { body: { paths: key.split("\n") } })
        .then((result) => {
          setScan(result);
          setError(null);
        })
        .catch((reason: Error) => setError(errorText(reason)));
    }, 400);
    return () => window.clearTimeout(timer);
  }, [key]);

  // The folder chosen goes in the row; the images not chosen in it are left out.
  async function choose(index: number) {
    setChoosing(index);
    try {
      const picked = await api<PickedFolder>("/v1/local-images/select", {
        body: {
          directory: paths[index].trim() || lastFolder,
          title: t("picker.window.title"),
          whole_folder: t("picker.window.whole"),
        },
      });
      if (picked.cancelled) return;
      setLastFolder(picked.directory);
      setLeft(new Set([...left, ...picked.left_out]));
      setPaths(paths.map((p, i) => (i === index ? picked.directory : p)));
      setError(null);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setChoosing(null);
    }
  }

  const files = scan?.files ?? [];
  const taken = files.filter((f) => !left.has(f.path));
  useEffect(() => {
    onChange({
      // Some left out: the files one by one; otherwise the folders as given.
      paths: left.size && scan ? taken.map((f) => f.path) : key ? key.split("\n") : [],
      origin: generated ? { kind: "generated", how: { note: how } } : null,
      count: taken.length,
      written: scan?.written ?? null,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- taken follows scan and left
  }, [key, generated, how, scan, left, onChange]);

  return (
    <div className="flex flex-col gap-2.5">
      {paths.map((path, index) => (
        <div key={index} className="flex flex-wrap items-center gap-2">
          <label htmlFor={`folder-${index}`} className="flex-none">
            {t("picker.folder")}
          </label>
          <input
            id={`folder-${index}`}
            value={path}
            placeholder="/home/…/images"
            onChange={(event) =>
              setPaths(paths.map((p, i) => (i === index ? event.target.value : p)))
            }
            className="min-w-0 flex-[1_1_360px] rounded-md border border-line bg-surface px-2 py-1.5 font-mono text-body"
          />
          <Button disabled={choosing !== null} onClick={() => void choose(index)}>
            {t("picker.window.open")}
          </Button>
          {choosing === index && (
            <span className="text-body text-muted-foreground">{t("picker.window.waiting")}</span>
          )}
          {paths.length > 1 && (
            <Button variant="link" onClick={() => setPaths(paths.filter((_, i) => i !== index))}>
              {t("picker.remove")}
            </Button>
          )}
        </div>
      ))}
      <div>
        <Button onClick={() => setPaths([...paths, ""])}>{t("picker.addFolder")}</Button>
      </div>
      <div className="flex flex-col gap-1.5 text-body">
        {error && <span className="text-failed">{error}</span>}
        {/* A folder written out is said by the window that takes it in (what it holds). */}
        {scan && !scan.written && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <strong>{t("picker.taken", { count: taken.length, total: scan.count })}</strong>
              <Button size="small" disabled={!left.size} onClick={() => setLeft(new Set())}>
                {t("picker.all")}
              </Button>
              <Button
                size="small"
                disabled={left.size === files.length}
                onClick={() => setLeft(new Set(files.map((f) => f.path)))}
              >
                {t("picker.none")}
              </Button>
            </div>
            {files.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <textarea
                  rows={1}
                  aria-label={t("picker.names")}
                  placeholder={t("picker.names.example")}
                  value={names}
                  onChange={(e) => setNames(e.target.value)}
                  className="min-w-64 flex-1 resize-y rounded-md border border-line bg-surface px-2 py-1 font-mono text-xs"
                />
                <Button
                  size="small"
                  disabled={!names.trim()}
                  onClick={() => setLeft(leftOutBy(files, names) ?? left)}
                >
                  {t("picker.names.choose")}
                </Button>
              </div>
            )}
            {files.length > 0 && (
              <ul
                aria-label={t("picker.files")}
                className="m-0 grid max-h-44 list-none grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-x-3 overflow-auto rounded-md border border-line bg-surface p-2"
              >
                {files.map((f) => (
                  <li key={f.path}>
                    <label className="flex items-center gap-1.5 truncate" title={f.path}>
                      <input
                        type="checkbox"
                        checked={!left.has(f.path)}
                        onChange={(event) => {
                          const next = new Set(left);
                          if (event.target.checked) next.delete(f.path);
                          else next.add(f.path);
                          setLeft(next);
                        }}
                      />
                      <span className="truncate font-mono text-xs">{f.name}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            {scan.skipped.length > 0 && (
              // A problem, in the problems' red (Astra 2026-10-06: grey read as a note).
              <span className="text-failed">
                {t("picker.skipped", { count: scan.skipped.length })} {skipText(scan.skipped)}
              </span>
            )}
          </>
        )}
      </div>
      {/* This app's datasets keep their images' own origins; COCO's images are told here. */}
      {scan?.written?.kind !== "app" && (
        <fieldset className="m-0 flex flex-col gap-1.5 rounded-md border border-line bg-surface px-3 py-2">
          <legend className="px-1 font-semibold">{t("picker.origin")}</legend>
          <label className="flex items-center gap-2">
            <input type="radio" checked={!generated} onChange={() => setGenerated(false)} />
            {t("picker.origin.real")}
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={generated} onChange={() => setGenerated(true)} />
            {t("picker.origin.generated")}
          </label>
          {generated && (
            <input
              aria-label={t("picker.origin.how")}
              placeholder={t("picker.origin.how")}
              value={how}
              onChange={(event) => setHow(event.target.value)}
              className="rounded-md border border-line px-2 py-1.5"
            />
          )}
        </fieldset>
      )}
    </div>
  );
}

/** "not found 1 · not an image 2": how many files were refused for each reason. */
