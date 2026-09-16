import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChartMetadata, ResultCell } from "../../api/types";

interface ChartViewProps {
  chart: ChartMetadata;
  rows: Array<Record<string, ResultCell>>;
}

export function ChartView({ chart, rows }: ChartViewProps) {
  if (!chart.x_axis || chart.y_axes.length === 0 || rows.length === 0) return null;
  const common = (
    <>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey={chart.x_axis} />
      <YAxis />
      <Tooltip />
    </>
  );
  if (chart.chart_type === "bar") {
    return (
      <div className="chart" role="img" aria-label={chart.title} data-testid="bar-chart">
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={rows}>
            {common}
            {chart.y_axes.map((axis) => <Bar dataKey={axis} fill="#2878a8" key={axis} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (chart.chart_type === "line") {
    return (
      <div className="chart" role="img" aria-label={chart.title} data-testid="line-chart">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={rows}>
            {common}
            {chart.y_axes.map((axis) => (
              <Line dataKey={axis} stroke="#2878a8" strokeWidth={2} key={axis} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (chart.chart_type === "scatter") {
    return (
      <div className="chart" role="img" aria-label={chart.title} data-testid="scatter-chart">
        <ResponsiveContainer width="100%" height={280}>
          <ScatterChart>
            {common}
            <Scatter data={rows} fill="#2878a8" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    );
  }
  return null;
}
