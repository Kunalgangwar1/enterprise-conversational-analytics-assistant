import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HashRouter } from "react-router-dom";

import App from "../App";
import type { ChatResponse, ToolFeatureFlags, UiFeatureFlags } from "../api/types";

const uiFlags: UiFeatureFlags = {
  follow_up_questions_show: true,
  context_button: true,
  chat_latency_badge: true,
  knowledge_graph_tools_show: false,
};
const toolFlags: ToolFeatureFlags = {
  sql: true,
  forecasting: true,
  group_access: false,
  data_discovery: true,
  knowledge_catalog: true,
  semantica: true,
  data_quality: true,
};

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function messageResponse(overrides: Partial<ChatResponse> = {}): ChatResponse {
  return {
    message_id: "message-1",
    selected_mode: "auto",
    route: "chat",
    response_type: "message",
    content: "Hello from the enterprise assistant.",
    follow_up_questions: [],
    latency_ms: 24,
    payload: null,
    ...overrides,
  } as ChatResponse;
}

interface FetchOptions {
  ui?: UiFeatureFlags;
  tools?: ToolFeatureFlags;
  chat?: ChatResponse | (() => Promise<Response>);
}

function installFetch(options: FetchOptions = {}) {
  return jest.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url === "/api/auth/me") {
      return jsonResponse({
        subject: "dev-user",
        email: "developer@example.invalid",
        display_name: "Local Developer",
        roles: ["analyst"],
        groups: [],
        permissions: [
          "chat.use", "dashboard.read", "data_discovery.read", "knowledge_catalog.read",
          "data_quality.read", "semantica.read", "group_access.read_self", "sql.generate",
          "sql.execute", "sql.advanced", "forecast.run",
        ],
        auth_method: "development",
      });
    }
    if (url === "/api/ui-feature-flags") return jsonResponse(options.ui ?? uiFlags);
    if (url === "/api/tool-flags") return jsonResponse(options.tools ?? toolFlags);
    if (url.startsWith("/api/chat-mode/welcome")) {
      const mode = new URL(url, "http://test").searchParams.get("mode") ?? "auto";
      return jsonResponse({
        mode,
        display_name: mode === "data_discovery" ? "Data Discovery" : "Enterprise AI",
        description: `Backend description for ${mode}`,
        welcome_message: `Backend welcome for ${mode}`,
      });
    }
    if (url === "/chat/select-mode") {
      const payload = JSON.parse(String(init?.body)) as { mode: string };
      return jsonResponse({ mode: payload.mode, display_name: payload.mode });
    }
    if (url === "/chat/reset") return jsonResponse({ status: "reset", mode: "auto" });
    if (url === "/chat/execute-sql") {
      return jsonResponse({
        columns: ["category", "value"],
        rows: [{ category: "A", value: 3 }],
        row_count: 1,
        truncated: true,
        execution_elapsed_ms: 2,
        summary: "Query complete.",
        summary_source: "deterministic",
        chart: {
          chart_type: "bar", x_axis: "category", y_axes: ["value"], title: "Values",
          selection_rule: "categorical_numeric",
        },
      });
    }
    if (url === "/chat") {
      if (typeof options.chat === "function") return options.chat();
      return jsonResponse(options.chat ?? messageResponse());
    }
    throw new Error(`Unexpected request: ${url}`);
  });
}

function renderApp() {
  window.location.hash = "#/";
  return render(
    <HashRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <App />
    </HashRouter>,
  );
}

describe("One UI", () => {
  beforeEach(() => {
    sessionStorage.clear();
    jest.restoreAllMocks();
  });

  test("renders through HashRouter with backend-enabled modes and welcome", async () => {
    installFetch();
    renderApp();
    expect(await screen.findByText("Backend welcome for auto")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Conversational Assistant" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Data Discovery" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Group Access" })).toBeDisabled();
    expect(window.location.hash).toBe("#/");
  });

  test("selecting a mode persists it and loads authoritative welcome content", async () => {
    const fetchMock = installFetch();
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Backend welcome for auto");
    await user.click(screen.getByRole("button", { name: "Data Discovery" }));
    expect(await screen.findByText("Backend welcome for data_discovery")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/chat/select-mode",
      expect.objectContaining({ method: "POST" }),
    );
  });

  test("composer rejects blank input and shows pending state during submission", async () => {
    let resolveChat: (response: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => { resolveChat = resolve; });
    installFetch({ chat: () => pending });
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Backend welcome for auto");
    const send = screen.getByRole("button", { name: "Send" });
    expect(send).toBeDisabled();
    await user.type(screen.getByLabelText("Message"), "Hello");
    await user.click(send);
    expect(screen.getByText("Analyzing request…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Working…" })).toBeDisabled();
    await act(async () => resolveChat(jsonResponse(messageResponse())));
    expect(await screen.findByText("Hello from the enterprise assistant.")).toBeInTheDocument();
  });

  test("safe backend error is shown without a raw stack trace", async () => {
    installFetch({
      chat: () => Promise.resolve(
        jsonResponse({ error: { code: "provider_unavailable", message: "Gemini is not configured for this environment." } }, 503),
      ),
    });
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Backend welcome for auto");
    await user.type(screen.getByLabelText("Message"), "Analyze claims");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Gemini is not configured");
    expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument();
  });

  test("SQL response is read-only in the UI and Run Query renders rows/chart/truncation", async () => {
    const sqlResponse: ChatResponse = {
      message_id: "sql-1", selected_mode: "sql", route: "sql", response_type: "sql",
      content: "SQL was generated and validated.", follow_up_questions: [], latency_ms: 5,
      payload: {
        sql: "SELECT category, value FROM claims", status: "ready_to_execute",
        selected_domains: ["claims"], selected_tables: ["claims"],
      },
    };
    const fetchMock = installFetch({ chat: sqlResponse });
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Backend welcome for auto");
    await user.click(screen.getByRole("button", { name: "Data Intelligence" }));
    await user.selectOptions(screen.getByLabelText("Analysis strategy"), "standard");
    await user.type(screen.getByLabelText("Message"), "Show claim values");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("SELECT category, value FROM claims")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /sql/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run query" }));
    expect(await screen.findByText("Query complete.")).toBeInTheDocument();
    expect(screen.getByText("Results are truncated")).toBeInTheDocument();
    expect(screen.getByTestId("bar-chart")).toBeInTheDocument();
    const executeCall = fetchMock.mock.calls.find(([url]) => url === "/chat/execute-sql");
    expect(executeCall?.[1]?.body).toBeUndefined();
  });

  test("current-turn context is feature gated and clears after successful send", async () => {
    installFetch();
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Backend welcome for auto");
    await user.click(screen.getByRole("button", { name: "Add context" }));
    const context = screen.getByLabelText("Context for this turn only");
    await user.type(context, "Temporary context");
    await user.type(screen.getByLabelText("Message"), "Hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Hello from the enterprise assistant.");
    expect(screen.queryByLabelText("Context for this turn only")).not.toBeInTheDocument();
  });

  test("latency and follow-ups require flags and actual data", async () => {
    installFetch({
      chat: messageResponse({ follow_up_questions: ["Show related datasets"] }),
    });
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Backend welcome for auto");
    await user.type(screen.getByLabelText("Message"), "Hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("24 ms")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show related datasets" })).toBeInTheDocument();
  });

  test("Reset calls the current-tab endpoint and clears transcript", async () => {
    const fetchMock = installFetch();
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Backend welcome for auto");
    await user.type(screen.getByLabelText("Message"), "Hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Hello from the enterprise assistant.");
    await user.click(screen.getByRole("button", { name: "New chat" }));
    await waitFor(() => expect(screen.queryByText("Hello from the enterprise assistant.")).not.toBeInTheDocument());
    expect(fetchMock.mock.calls.some(([url]) => url === "/chat/reset")).toBe(true);
    expect(screen.getByText("Backend welcome for auto")).toBeInTheDocument();
  });
});
