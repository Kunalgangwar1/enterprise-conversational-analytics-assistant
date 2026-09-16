import { render, screen } from "@testing-library/react";

import type { ForecastPayload, SqlExecutionResult } from "../api/types";
import { ChartView } from "../components/results/ChartView";
import { Citations } from "../components/results/Citations";
import { DiscoveryCard } from "../components/results/DiscoveryCard";
import { ForecastCard } from "../components/results/ForecastCard";
import { SqlResultCard } from "../components/results/SqlResultCard";

const rows = [{ category: "A", value: 2 }];
const baseChart = {
  x_axis: "category",
  y_axes: ["value"],
  title: "Values",
  selection_rule: "categorical_numeric",
};

test("renders bar and line charts only when declared by backend metadata", () => {
  const { rerender } = render(
    <ChartView chart={{ ...baseChart, chart_type: "bar" }} rows={rows} />,
  );
  expect(screen.getByTestId("bar-chart")).toBeInTheDocument();
  rerender(<ChartView chart={{ ...baseChart, chart_type: "line" }} rows={rows} />);
  expect(screen.getByTestId("line-chart")).toBeInTheDocument();
});

test("unsupported chart metadata safely renders no contradictory chart", () => {
  const { container } = render(
    <ChartView chart={{ ...baseChart, chart_type: "pie" }} rows={rows} />,
  );
  expect(container).toBeEmptyDOMElement();
});

test("SQL results render dynamic rows and truncation warning", () => {
  const result: SqlExecutionResult = {
    columns: ["category", "value", "active", "optional"],
    rows: [{ category: "A", value: 2, active: true, optional: null }],
    row_count: 1,
    truncated: true,
    execution_elapsed_ms: 4.2,
    summary: "One row returned.",
    summary_source: "llm",
    chart: { ...baseChart, chart_type: "table" },
  };
  render(<SqlResultCard result={result} />);
  expect(screen.getByText("Results are truncated")).toBeInTheDocument();
  expect(screen.getByText("True")).toBeInTheDocument();
  expect(screen.getByText("—")).toBeInTheDocument();
});

test("forecast card renders model, metrics, future values, intervals, and warning", () => {
  const forecast: ForecastPayload = {
    metric_label: "Monthly claims",
    frequency: "month",
    horizon_periods: 1,
    selected_model: "linear_trend",
    backtest_metrics: { mae: 1, rmse: 2, smape: 3 },
    historical_points: [{ period: "2025-12-01", value: 10 }],
    forecast_points: [{ period: "2026-01-01", predicted: 11, lower_bound: 7, upper_bound: 15 }],
    summary: "Aggregate projection.",
    summary_source: "llm",
    chart: { chart_type: "line", x_axis: "period", series: ["historical", "forecast"], title: "Claim forecast" },
    warnings: ["Approximate interval."],
  };
  render(<ForecastCard forecast={forecast} />);
  expect(screen.getByText("linear_trend")).toBeInTheDocument();
  expect(screen.getByText("2026-01-01")).toBeInTheDocument();
  expect(screen.getByText("Approximate interval.")).toBeInTheDocument();
  expect(screen.getByTestId("forecast-chart")).toBeInTheDocument();
});

test("RAG citations show safe provenance without an absolute path", () => {
  render(
    <Citations citations={[{ id: "c1", title: "Claims", section: "Meaning", source_path: "/secret/root/datasets/claims.md" }]} />,
  );
  expect(screen.getByText("Claims")).toBeInTheDocument();
  expect(screen.getByText("datasets/claims.md")).toBeInTheDocument();
  expect(screen.queryByText(/secret\/root/)).not.toBeInTheDocument();
});

test("Data Discovery renders structured dataset fields", () => {
  render(
    <DiscoveryCard payload={{ matches: [{
      dataset: "claims", repository: "synthetic-health", table: "claims", domain: "claims",
      description: "Synthetic claim facts", matched_fields: ["dataset"], score: 1,
    }] }} />,
  );
  expect(screen.getByText("synthetic-health")).toBeInTheDocument();
  expect(screen.getByText("Synthetic claim facts")).toBeInTheDocument();
});
