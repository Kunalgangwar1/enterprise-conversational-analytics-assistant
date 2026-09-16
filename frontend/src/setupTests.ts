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
