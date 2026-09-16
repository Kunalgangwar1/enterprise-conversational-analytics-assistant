import { apiRequest } from "./client";
import type { AuthPrincipal } from "./types";

export const getCurrentPrincipal = (signal?: AbortSignal): Promise<AuthPrincipal> =>
  apiRequest("/api/auth/me", {}, signal);
