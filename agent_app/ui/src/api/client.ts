// A thin wrapper over fetch for the app's /v1 API. Errors arrive as {error: {code, message}}.
import { currentLang } from "@/i18n";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  init: { method?: string; body?: unknown; actor?: "ui"; signal?: AbortSignal } = {},
): Promise<T> {
  // The screen's language, not the browser's: a worker answers the person in it.
  const headers: Record<string, string> = {
    "X-Actor": init.actor ?? "ui",
    "Accept-Language": currentLang(),
  };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method: init.method ?? (init.body === undefined ? "GET" : "POST"),
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    signal: init.signal,
  });
  if (!response.ok) {
    let error = { code: "http_" + response.status, message: response.statusText, details: {} };
    try {
      const body = await response.json();
      if (body?.error) error = body.error;
    } catch {
      // Not JSON: keep the HTTP status as the error.
    }
    throw new ApiError(response.status, error.code, error.message, error.details);
  }
  return (await response.json()) as T;
}

export function thumbnailUrl(imageId: string, maxSide = 320): string {
  return `/v1/images/${imageId}/thumbnail?max_side=${maxSide}`;
}

export function imageUrl(imageId: string): string {
  return `/v1/images/${imageId}/file`;
}
