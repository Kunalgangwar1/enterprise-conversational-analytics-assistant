import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HashRouter } from "react-router-dom";

import App from "../App";
import type {
  ClaimsDashboard,
  DashboardOverview,
  OperationsDashboard,
  ToolFeatureFlags,
  UiFeatureFlags,
} from "../api/types";

const uiFlags: UiFeatureFlags = {
  follow_up_questions_show: false,
  context_button: false,
  chat_latency_badge: false,
  knowledge_graph_tools_show: false,
};
const toolFlags: ToolFeatureFlags = {
  sql: true,
  forecasting: false,
  group_access: false,
  data_discovery: false,
  knowledge_catalog: false,
  semantica: false,
  data_quality: false,
};

const metadata = {
  start_date: "2025-01-01",
  end_date: "2025-12-31",
  data_as_of: "2025-12-31",
  available_start_date: "2024-01-01",
  available_end_date: "2025-12-31",
  has_data: true,
};

const overview: DashboardOverview = {
  ...metadata,
  kpis: [
    {
      id: "total_claims",
      label: "Total claims",
      value: 2500,
      unit: "count",
      comparison: 8.4,
      comparison_label: "vs previous period",
    },
    {
      id: "total_paid_amount",
      label: "Total paid amount",
      value: 1250000,
      unit: "currency",
      comparison: -3.1,
      comparison_label: "vs previous period",
    },
  ],
};

const claims: ClaimsDashboard = {
  ...metadata,
  monthly_trend: [
    { period: "2025-01-01", claim_count: 12, paid_amount: 900, allowed_amount: 1200 },
  ],
  status_distribution: [
    { category: "paid", count: 10, amount: null, average_amount: null },
    { category: "denied", count: 2, amount: null, average_amount: null },
  ],
  specialty_breakdown: [
    { category: "Primary Care", count: 8, amount: 700, average_amount: 87.5 },
  ],
  facility_breakdown: [
    { category: "Clinic", count: 7, amount: 650, average_amount: 92.86 },
  ],
};

const operations: OperationsDashboard = {
  ...metadata,
  encounters_by_month: [{ period: "2025-01-01", value: 15 }],
  appointments_by_month: [{ period: "2025-01-01", value: 18 }],
  appointment_status_distribution: [
    { category: "completed", count: 14, amount: null, average_amount: null },
  ],
  encounter_type_distribution: [
    { category: "outpatient", count: 15, amount: null, average_amount: null },
  ],
  appointments_by_specialty: [
    { category: "Primary Care", count: 18, amount: null, average_amount: null },
  ],
};

function response(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

interface FetchOverrides {
  overview?: Response | Promise<Response>;
  claims?: Response | Promise<Response>;
  operations?: Response | Promise<Response>;
}

function installFetch(overrides: FetchOverrides = {}) {
  return jest.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/auth/me") {
      return response({
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
    if (url === "/api/ui-feature-flags") return response(uiFlags);
    if (url === "/api/tool-flags") return response(toolFlags);
    if (url.startsWith("/api/chat-mode/welcome")) {
      return response({
        mode: "auto",
        display_name: "Enterprise AI",
        description: "Backend description",
        welcome_message: "Backend welcome",
      });
    }
    if (url.startsWith("/api/dashboards/overview")) {
      return await (overrides.overview ?? response(overview));
    }
    if (url.startsWith("/api/dashboards/claims")) {
      return await (overrides.claims ?? response(claims));
    }
    if (url.startsWith("/api/dashboards/operations")) {
      return await (overrides.operations ?? response(operations));
    }
    if (url === "/chat") {
      return response({
        message_id: "chat-1",
        selected_mode: "auto",
        route: "chat",
        response_type: "message",
        content: "Persistent chat response",
        follow_up_questions: [],
        latency_ms: 1,
        payload: null,
      });
    }
    throw new Error(`Unexpected request: ${url}`);
  });
}

function renderApp(path = "/dashboard") {
  window.location.hash = `#${path}`;
  return render(
    <HashRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <App />
    </HashRouter>,
  );
}

describe("AI Dashboard", () => {
  beforeEach(() => {
    sessionStorage.clear();
    jest.restoreAllMocks();
  });

  test("dashboard route loads aggregate APIs without chat or forecasting", async () => {
    const fetchMock = installFetch();
    renderApp();

    expect(await screen.findByRole("heading", { name: "AI Dashboard" })).toBeInTheDocument();
    await screen.findByText("Total claims");
    const urls = fetchMock.mock.calls.map(([url]) => String(url));
    expect(urls).toEqual(expect.arrayContaining([
      "/api/dashboards/overview",
      "/api/dashboards/claims",
      "/api/dashboards/operations",
    ]));
    expect(urls).not.toContain("/chat");
    expect(urls.some((url) => url.includes("forecast"))).toBe(false);
  });

  test("renders KPI formatting, comparisons, and all primary chart panels", async () => {
    installFetch();
    renderApp();
    await screen.findByText("Total claims");

    expect(screen.getByText("2.5K")).toBeInTheDocument();
    expect(screen.getByText("$1.25M")).toBeInTheDocument();
    expect(screen.getByText(/Increase \+8.4% vs previous period/)).toBeInTheDocument();
    expect(screen.getByText(/Decrease -3.1% vs previous period/)).toBeInTheDocument();
    expect(screen.getByTestId("claims-trend-chart")).toBeInTheDocument();
    expect(screen.getByTestId("specialty-chart")).toBeInTheDocument();
    expect(screen.getByTestId("claim-status-chart")).toBeInTheDocument();
    expect(screen.getByTestId("appointments-trend-chart")).toBeInTheDocument();
  });

  test("date filters are validated locally and applied to all dashboard sections", async () => {
    const fetchMock = installFetch();
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("Total claims");

    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2025-03-01" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2025-06-30" } });
    await user.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes(
        "start_date=2025-03-01&end_date=2025-06-30",
      ))).toBe(true);
    });

    const dashboardCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes("/dashboards/")).length;
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2025-09-01" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2025-06-01" } });
    await user.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Start date must be on or before end date");
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/dashboards/")).length).toBe(dashboardCalls);
  });

  test("shows initial loading and valid empty-dashboard states", async () => {
    let resolveOverview: (value: Response) => void = () => undefined;
    const pendingOverview = new Promise<Response>((resolve) => { resolveOverview = resolve; });
    const emptyClaims = { ...claims, has_data: false, monthly_trend: [], status_distribution: [], specialty_breakdown: [], facility_breakdown: [] };
    const emptyOperations = { ...operations, has_data: false, encounters_by_month: [], appointments_by_month: [], appointment_status_distribution: [], encounter_type_distribution: [], appointments_by_specialty: [] };
    installFetch({
      overview: pendingOverview,
      claims: response(emptyClaims),
      operations: response(emptyOperations),
    });
    renderApp();
    expect(await screen.findByText("Loading aggregate analytics…")).toBeInTheDocument();
    resolveOverview(response({ ...overview, has_data: false, kpis: overview.kpis.map((item) => ({ ...item, value: 0 })) }));
    expect((await screen.findAllByText("No aggregate data is available for this date range.")).length).toBe(2);
  });

  test("one failed section shows a safe local error while other sections render", async () => {
    installFetch({
      claims: response({ error: { code: "dashboard_query_failed", message: "Claims analytics unavailable." } }, 500),
    });
    renderApp();
    expect(await screen.findByText("Total claims")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Claims analytics unavailable");
    expect(screen.getByTestId("appointments-trend-chart")).toBeInTheDocument();
  });

  test("Chat and Dashboard navigation preserves the in-tab chat transcript", async () => {
    installFetch();
    const user = userEvent.setup();
    renderApp("/");
    await screen.findByText("Backend welcome");
    await user.type(screen.getByLabelText("Message"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Persistent chat response")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Dashboard" }));
    expect(await screen.findByRole("heading", { name: "AI Dashboard" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/dashboard");
    await user.click(screen.getByRole("link", { name: "Chat" }));
    expect(window.location.hash).toBe("#/");
    expect(screen.getByText("Persistent chat response")).toBeInTheDocument();
  });
});
