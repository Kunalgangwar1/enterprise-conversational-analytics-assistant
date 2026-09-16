import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HashRouter } from "react-router-dom";

import App from "../App";
import type { AuthPrincipal, Permission } from "../api/types";

function response(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

const viewerPermissions: Permission[] = [
  "chat.use",
  "dashboard.read",
  "data_discovery.read",
  "knowledge_catalog.read",
  "data_quality.read",
  "semantica.read",
  "group_access.read_self",
];

const analystPermissions: Permission[] = [
  ...viewerPermissions,
  "sql.generate",
  "sql.execute",
  "sql.advanced",
  "forecast.run",
];

function identity(role: "viewer" | "analyst", permissions: Permission[]): AuthPrincipal {
  return {
    subject: `${role}-user`,
    email: `${role}@example.invalid`,
    display_name: `${role[0].toUpperCase()}${role.slice(1)} User`,
    roles: [role],
    groups: [],
    permissions,
    auth_method: "development",
  };
}

function installAuthenticatedFetch(principal: AuthPrincipal, chatStatus = 200) {
  return jest.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url === "/api/auth/me") return response(principal);
    if (url === "/api/ui-feature-flags") {
      return response({
        follow_up_questions_show: false,
        context_button: false,
        chat_latency_badge: false,
        knowledge_graph_tools_show: false,
      });
    }
    if (url === "/api/tool-flags") {
      return response({
        sql: true,
        forecasting: true,
        group_access: true,
        data_discovery: true,
        knowledge_catalog: true,
        semantica: true,
        data_quality: true,
      });
    }
    if (url.startsWith("/api/chat-mode/welcome")) {
      const mode = new URL(url, "http://test").searchParams.get("mode") ?? "auto";
      return response({
        mode,
        display_name: mode === "sql" ? "Data Intelligence" : "Enterprise AI",
        description: "Synthetic description",
        welcome_message: "Synthetic welcome",
      });
    }
    if (url === "/chat/select-mode") {
      const body = JSON.parse(String(init?.body)) as { mode: string };
      return response({ mode: body.mode, display_name: body.mode });
    }
    if (url === "/chat") {
      if (chatStatus === 403) {
        return response(
          { error: { code: "permission_denied", message: "You do not have permission to perform this action." } },
          403,
        );
      }
      return response({
        message_id: "message-1",
        selected_mode: "auto",
        route: "chat",
        response_type: "message",
        content: "Synthetic answer",
        follow_up_questions: [],
        latency_ms: 1,
        payload: null,
      });
    }
    if (url === "/chat/reset") return response({ status: "reset", mode: "auto" });
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

describe("authentication and permission-aware UI", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    jest.restoreAllMocks();
  });

  test("shows an authentication loading state", async () => {
    let resolveAuth: (value: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => { resolveAuth = resolve; });
    jest.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (String(input) === "/api/auth/me") return pending;
      throw new Error("No post-auth request expected");
    });
    renderApp();
    expect(screen.getByRole("status")).toHaveTextContent("Loading authentication");
    await act(async () => resolveAuth(response(identity("viewer", viewerPermissions))));
    expect(await screen.findByText("Viewer User")).toBeInTheDocument();
  });

  test("viewer identity is displayed and privileged navigation is absent", async () => {
    installAuthenticatedFetch(identity("viewer", viewerPermissions));
    renderApp();
    expect(await screen.findByText("Viewer User")).toBeInTheDocument();
    await screen.findByText("Synthetic welcome");
    expect(screen.queryByRole("button", { name: "Data Intelligence" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Group Access" })).toBeEnabled();
    expect(screen.queryByLabelText("Analysis strategy")).not.toBeInTheDocument();
  });

  test("analyst sees SQL, Advanced, Forecasting, and Dashboard", async () => {
    installAuthenticatedFetch(identity("analyst", analystPermissions));
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Analyst User");
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Data Intelligence" }));
    const strategy = await screen.findByLabelText("Analysis strategy");
    expect(strategy).toContainHTML("Advanced");
    expect(strategy).toContainHTML("Forecasting");
  });

  test("navigation and Group Access require their specific permissions", async () => {
    installAuthenticatedFetch(identity("viewer", ["chat.use"]));
    renderApp();
    await screen.findByText("Viewer User");
    await screen.findByText("Synthetic welcome");
    expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Group Access" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Data Discovery" })).not.toBeInTheDocument();
  });

  test("401 renders authentication-required state", async () => {
    jest.spyOn(globalThis, "fetch").mockResolvedValue(
      response({ error: { code: "authentication_required", message: "Authentication is required." } }, 401),
    );
    renderApp();
    expect(await screen.findByRole("heading", { name: "Authentication required" })).toBeInTheDocument();
  });

  test("403 chat response renders only the safe permission error", async () => {
    installAuthenticatedFetch(identity("analyst", analystPermissions), 403);
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Analyst User");
    await user.type(screen.getByLabelText("Message"), "Restricted operation");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You do not have permission to perform this action.",
    );
  });

  test("development auth stores no token in browser storage", async () => {
    installAuthenticatedFetch(identity("analyst", analystPermissions));
    renderApp();
    await screen.findByText("Analyst User");
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.getItem("access_token")).toBeNull();
    expect(sessionStorage.getItem("refresh_token")).toBeNull();
    expect(Array.from({ length: sessionStorage.length }, (_, index) => sessionStorage.key(index)))
      .toEqual(["eca_tab_id"]);
  });
});
