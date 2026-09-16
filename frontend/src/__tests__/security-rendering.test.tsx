import { render, screen } from "@testing-library/react";

import type { ChatResponse, UiFeatureFlags } from "../api/types";
import { Transcript } from "../components/chat/Transcript";
import type { TranscriptItem } from "../state/chat";

test("renders model-controlled text as inert React text rather than executable HTML", () => {
  const malicious = '<img src=x onerror="globalThis.pwned=true"><script>alert(1)</script>';
  const response = {
    message_id: "security-message",
    selected_mode: "auto",
    route: "chat",
    response_type: "message",
    content: malicious,
    follow_up_questions: ["<svg onload=alert(2)>"],
    latency_ms: 1,
    payload: null,
  } as ChatResponse;
  const messages: TranscriptItem[] = [{ id: "security-message", kind: "assistant", response }];
  const flags: UiFeatureFlags = {
    follow_up_questions_show: true,
    context_button: true,
    chat_latency_badge: true,
    knowledge_graph_tools_show: false,
  };

  const { container } = render(
    <Transcript messages={messages} flags={flags} onRunSql={jest.fn()} onFollowUp={jest.fn()} />,
  );

  expect(screen.getByText(malicious)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "<svg onload=alert(2)>" })).toBeInTheDocument();
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("img")).toBeNull();
  expect(container.querySelector("svg")).toBeNull();
});
