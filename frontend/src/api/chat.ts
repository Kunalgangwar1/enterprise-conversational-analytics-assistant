import { apiRequest } from "./client";
import type {
  ChatMode,
  ChatResponse,
  ModeWelcome,
  SqlExecutionResult,
  SqlStrategy,
} from "./types";

export const selectMode = (mode: ChatMode): Promise<{ mode: ChatMode; display_name: string }> =>
  apiRequest("/chat/select-mode", { method: "POST", body: JSON.stringify({ mode }) });

export const getModeWelcome = (mode: ChatMode, signal?: AbortSignal): Promise<ModeWelcome> =>
  apiRequest(`/api/chat-mode/welcome?mode=${encodeURIComponent(mode)}`, {}, signal);

export const sendChat = (
  message: string,
  sqlStrategy?: SqlStrategy,
  customContext?: string,
): Promise<ChatResponse> =>
  apiRequest("/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      ...(sqlStrategy ? { sql_strategy: sqlStrategy } : {}),
      ...(customContext?.trim() ? { custom_context: customContext.trim() } : {}),
    }),
  });

export const executeSql = (): Promise<SqlExecutionResult> =>
  apiRequest("/chat/execute-sql", { method: "POST" });

export const resetChat = (): Promise<{ status: "reset"; mode: ChatMode }> =>
  apiRequest("/chat/reset", { method: "POST" });
