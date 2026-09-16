import { useCallback, useState } from "react";

import { executeSql, resetChat, sendChat } from "../api/chat";
import { ApiError } from "../api/client";
import type { ChatMode, SqlStrategy } from "../api/types";
import type { TranscriptItem } from "../state/chat";

function newId(prefix: string): string {
  return `${prefix}-${globalThis.crypto?.randomUUID?.() ?? Date.now().toString(36)}`;
}

function safeError(error: unknown): string {
  return error instanceof ApiError ? error.message : "The request could not be completed.";
}

export function useChat(selectedMode: ChatMode, sqlStrategy: SqlStrategy) {
  const [messages, setMessages] = useState<TranscriptItem[]>([]);
  const [isSending, setIsSending] = useState(false);

  const send = useCallback(
    async (content: string, customContext?: string): Promise<boolean> => {
      const trimmed = content.trim();
      if (!trimmed || isSending) return false;
      const userId = newId("user");
      const pendingId = newId("pending");
      setMessages((current) => [
        ...current,
        { id: userId, kind: "user", content: trimmed },
        { id: pendingId, kind: "pending" },
      ]);
      setIsSending(true);
      try {
        const response = await sendChat(
          trimmed,
          selectedMode === "sql" ? sqlStrategy : undefined,
          customContext,
        );
        setMessages((current) => [
          ...current.filter((message) => message.id !== pendingId),
          { id: response.message_id, kind: "assistant", response },
        ]);
        return true;
      } catch (error) {
        setMessages((current) => [
          ...current.filter((message) => message.id !== pendingId),
          { id: newId("error"), kind: "error", content: safeError(error) },
        ]);
        return false;
      } finally {
        setIsSending(false);
      }
    },
    [isSending, selectedMode, sqlStrategy],
  );

  const runSql = useCallback(async (messageId: string): Promise<void> => {
    setMessages((current) =>
      current.map((message) =>
        message.kind === "assistant" && message.id === messageId
          ? { ...message, executingSql: true }
          : message,
      ),
    );
    try {
      const result = await executeSql();
      setMessages((current) =>
        current.map((message) =>
          message.kind === "assistant" && message.id === messageId
            ? { ...message, executingSql: false, sqlResult: result }
            : message,
        ),
      );
    } catch (error) {
      setMessages((current) => [
        ...current.map((message) =>
          message.kind === "assistant" && message.id === messageId
            ? { ...message, executingSql: false }
            : message,
        ),
        { id: newId("error"), kind: "error", content: safeError(error) },
      ]);
    }
  }, []);

  const reset = useCallback(async (): Promise<boolean> => {
    try {
      await resetChat();
      setMessages([]);
      return true;
    } catch (error) {
      setMessages((current) => [
        ...current,
        { id: newId("error"), kind: "error", content: safeError(error) },
      ]);
      return false;
    }
  }, []);

  return { messages, isSending, send, runSql, reset };
}
