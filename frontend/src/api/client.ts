import type { ApiErrorEnvelope } from "./types";

const TAB_ID_KEY = "eca_tab_id";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getTabId(): string {
  const existing = sessionStorage.getItem(TAB_ID_KEY);
  if (existing) return existing;
  const generated = globalThis.crypto?.randomUUID?.() ?? fallbackUuid();
  sessionStorage.setItem(TAB_ID_KEY, generated);
  return generated;
}

function fallbackUuid(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${__API_BASE_URL__}${path}`, {
      ...init,
      signal,
      credentials: "include",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Tab-Id": getTabId(),
        ...init.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Unable to reach the analytics service.", "network_error", 0);
  }
  if (!response.ok) {
    let envelope: ApiErrorEnvelope | null = null;
    try {
      envelope = (await response.json()) as ApiErrorEnvelope;
    } catch {
      // The safe generic message below handles non-JSON upstream failures.
    }
    throw new ApiError(
      envelope?.error?.message ?? "The analytics service could not complete the request.",
      envelope?.error?.code ?? "request_failed",
      response.status,
    );
  }
  return (await response.json()) as T;
}
