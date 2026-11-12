// The app: the library, the settings, a dataset's gallery, a set a worker showed or the loupe
// (the workers beside them), by the URL hash (lib/route.ts).
import { useEffect } from "react";
import type { Progress, StageName } from "@/api/types";
import { Toaster } from "sonner";
import { t, useLang } from "@/i18n";
import { stageNow } from "@/lib/home";
import { type PlanRef, useRoute } from "@/lib/route";
import { useApi } from "@/lib/useApi";
import { applyTheme, useTheme } from "@/lib/theme";
import { applyTextSize, useTextSize } from "@/lib/textSize";
import { useWorkWatch } from "@/lib/workWatch";
import { IN_APP_WINDOW } from "@/lib/appWindow";
import { ObjectsScreen } from "./screens/ObjectsScreen";
import { Gallery } from "@/screens/Gallery";
import type { About } from "@/lib/talk";
import { PlanInterview } from "@/screens/PlanInterview";
import { Library } from "@/screens/Library";
import { Loupe } from "@/screens/Loupe";
import { Settings } from "@/screens/Settings";
import { Stopped } from "@/components/Stopped";

/** A dataset's right: the plan's interview, or the gallery of carrying it out (the stage in the
 * link, else the dataset's stage now; definition 35.3). */
function DatasetScreen({
  datasetId,
  stage: chosen,
  recordId,
  step,
  plan,
  about,
}: {
  datasetId: string;
  stage: StageName | null;
  recordId: string | null;
  step: string | null;
  /** The plan its images are judged by (definition 36.1). */
  plan: PlanRef | null;
  /** The plan's screen: what it shows above the plan (definition 37.4). */
  about: About | null;
}) {
  const progress = useApi<Progress>(chosen ? null : `/v1/datasets/${datasetId}/progress`);
  const stage = chosen ?? (progress.data ? stageNow(progress.data) : null);
  if (stage === null) return null;
  return stage === "instruction" ? (
    <PlanInterview datasetId={datasetId} plan={plan} about={about} recordId={recordId} />
  ) : (
    <Gallery datasetId={datasetId} recordId={recordId} step={step} plan={plan} />
  );
}

export function App() {
  const route = useRoute();
  const lang = useLang();
  const theme = useTheme();
  useEffect(() => applyTheme(theme), [theme]);
  const textSize = useTextSize();
  useEffect(() => applyTextSize(textSize), [textSize]);
  const stopped = useWorkWatch();
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  return (
    <>
      {/* The app stopped (quit from its small window, or ended): said over every screen. */}
      {stopped && !IN_APP_WINDOW && <Stopped title={t("quit.stopped")} />}
      {route.screen === "library" && <Library />}
      {route.screen === "settings" && <Settings />}
      {route.screen === "gallery" && (
        <DatasetScreen
          key={route.datasetId}
          datasetId={route.datasetId}
          stage={route.stage}
          recordId={route.recordId}
          step={route.step ?? null}
          plan={route.plan ?? null}
          about={route.about ?? null}
        />
      )}
      {route.screen === "objects" && (
        <ObjectsScreen
          key={`${route.datasetId}-${route.type}`}
          datasetId={route.datasetId}
          type={route.type}
          where={route.where}
          id={route.id}
          title={route.title}
        />
      )}
      {route.screen === "loupe" && (
        <Loupe
          datasetId={route.datasetId}
          imageId={route.imageId}
          stage={route.stage ?? "production"}
          recordId={route.recordId}
          objectId={route.objectId ?? null}
          plan={route.plan ?? null}
        />
      )}
      <Toaster position="bottom-right" richColors closeButton theme={theme} />
    </>
  );
}
