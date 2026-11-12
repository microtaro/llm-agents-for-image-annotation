// A reference is a result chosen as the plan's example (definition 38.1): chosen on a result (a
// sample's card, the loupe) and taken out in the plan's references, all through this one call.
import { api } from "@/api/client";
import { invalidate } from "./useApi";

/** The image's reference made the result (an earlier one replaced); none: taken out. */
export async function chooseReference(
  datasetId: string,
  imageId: string,
  resultId: string | null,
): Promise<void> {
  const path = `/v1/datasets/${datasetId}/images/${imageId}/reference`;
  await api(
    path,
    resultId ? { method: "PUT", body: { result_id: resultId, note: "" } } : { method: "DELETE" },
  );
  invalidate(datasetId);
}
