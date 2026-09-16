import { apiRequest, getTabId } from "../api/client";
import { executeSql } from "../api/chat";

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("typed API client", () => {
  beforeEach(() => {
    sessionStorage.clear();
    jest.restoreAllMocks();
  });

  test("generates one stable per-tab identifier in sessionStorage", () => {
    const randomUUID = jest.spyOn(globalThis.crypto, "randomUUID");
    const first = getTabId();
    const second = getTabId();
    expect(first).toBe(second);
    expect(sessionStorage.getItem("eca_tab_id")).toBe(first);
    expect(randomUUID).toHaveBeenCalledTimes(1);
  });

  test("sends credentials and X-Tab-Id on every request", async () => {
    sessionStorage.setItem("eca_tab_id", "tab-browser-1");
    const fetchMock = jest.spyOn(globalThis, "fetch").mockResolvedValue(response({ ok: true }));
    await apiRequest<{ ok: boolean }>("/api/health");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/health",
      expect.objectContaining({
        credentials: "include",
        headers: expect.objectContaining({ "X-Tab-Id": "tab-browser-1" }),
      }),
    );
  });

  test("Run Query sends no browser-provided SQL", async () => {
    const fetchMock = jest.spyOn(globalThis, "fetch").mockResolvedValue(
      response({
        columns: [], rows: [], row_count: 0, truncated: false, execution_elapsed_ms: 1,
        summary: "No rows", summary_source: "deterministic",
        chart: { chart_type: "table", x_axis: null, y_axes: [], title: "Result", selection_rule: "empty" },
      }),
    );
    await executeSql();
    const [, request] = fetchMock.mock.calls[0];
    expect(fetchMock.mock.calls[0][0]).toBe("/chat/execute-sql");
    expect(request?.method).toBe("POST");
    expect(request?.body).toBeUndefined();
  });

  test("renders safe application errors from the backend envelope", async () => {
    jest.spyOn(globalThis, "fetch").mockResolvedValue(
      response({ error: { code: "provider_unavailable", message: "Provider is unavailable." } }, 503),
    );
    await expect(apiRequest("/chat")).rejects.toMatchObject({
      code: "provider_unavailable",
      message: "Provider is unavailable.",
    });
  });
});
