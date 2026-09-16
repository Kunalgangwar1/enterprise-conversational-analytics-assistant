import type { ChatResponse, SqlExecutionResult } from "../api/types";

export type TranscriptItem =
  | { id: string; kind: "user"; content: string }
  | { id: string; kind: "pending" }
  | { id: string; kind: "error"; content: string }
  | {
      id: string;
      kind: "assistant";
      response: ChatResponse;
      sqlResult?: SqlExecutionResult;
      executingSql?: boolean;
    };
