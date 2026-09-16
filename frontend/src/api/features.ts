import { apiRequest } from "./client";
import type { ToolFeatureFlags, UiFeatureFlags } from "./types";

export const getUiFeatureFlags = (signal?: AbortSignal): Promise<UiFeatureFlags> =>
  apiRequest("/api/ui-feature-flags", {}, signal);

export const getToolFeatureFlags = (signal?: AbortSignal): Promise<ToolFeatureFlags> =>
  apiRequest("/api/tool-flags", {}, signal);
