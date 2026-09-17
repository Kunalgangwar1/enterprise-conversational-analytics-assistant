import "@testing-library/jest-dom";
import { createElement as mockCreateElement, type ReactNode } from "react";

class ResizeObserverMock {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver = ResizeObserverMock;
Element.prototype.scrollIntoView = jest.fn();
(globalThis as typeof globalThis & { __API_BASE_URL__: string }).__API_BASE_URL__ = "";
(globalThis as typeof globalThis & { __AUTH_MODE__: string }).__AUTH_MODE__ = "development";
(globalThis as typeof globalThis & { __OIDC_AUTHORITY__: string }).__OIDC_AUTHORITY__ = "";
(globalThis as typeof globalThis & { __OIDC_CLIENT_ID__: string }).__OIDC_CLIENT_ID__ = "";
(globalThis as typeof globalThis & { __OIDC_REDIRECT_URI__: string }).__OIDC_REDIRECT_URI__ = "";
(globalThis as typeof globalThis & { __OIDC_POST_LOGOUT_REDIRECT_URI__: string })
  .__OIDC_POST_LOGOUT_REDIRECT_URI__ = "";
(globalThis as typeof globalThis & { __OIDC_MANAGED_LOGIN_DOMAIN__: string })
  .__OIDC_MANAGED_LOGIN_DOMAIN__ = "";

Object.defineProperty(globalThis, "fetch", {
  configurable: true,
  writable: true,
  value: jest.fn(),
});

Object.defineProperty(globalThis.crypto, "randomUUID", {
  configurable: true,
  value: jest.fn(() => "00000000-0000-4000-8000-000000000001"),
});

jest.mock("recharts", () => {
  const container = ({ children }: { children?: ReactNode }) =>
    mockCreateElement("div", null, children);
  const leaf = () => null;
  return {
    ResponsiveContainer: container,
    BarChart: container,
    LineChart: container,
    ScatterChart: container,
    CartesianGrid: leaf,
    XAxis: leaf,
    YAxis: leaf,
    Tooltip: leaf,
    Legend: leaf,
    Bar: leaf,
    Line: leaf,
    Scatter: leaf,
  };
});
