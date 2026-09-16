import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { CategoryMetric, DashboardUnit } from "../../api/types";
import { formatDashboardValue } from "../../utils/format";

interface SeriesDefinition {
  key: string;
  label: string;
  color: string;
  unit: DashboardUnit;
}

interface TimeSeriesChartProps {
  title: string;
  description: string;
  data: Array<Record<string, string | number>>;
  series: SeriesDefinition[];
  testId: string;
}

export function TimeSeriesChart({
  title,
  description,
  data,
  series,
  testId,
}: TimeSeriesChartProps) {
  return (
    <section className="dashboard-panel" aria-labelledby={`${testId}-title`}>
      <div className="panel-heading">
        <div>
          <h3 id={`${testId}-title`}>{title}</h3>
          <p>{description}</p>
        </div>
      </div>
      {data.length === 0 ? (
        <EmptyPanel />
      ) : (
        <>
          <div className="dashboard-chart" role="img" aria-label={`${title}. ${description}`} data-testid={testId}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#dce5ea" />
                <XAxis dataKey="period" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip
                  formatter={(value, name) => {
                    const definition = series.find((item) => item.key === String(name));
                    return [
                      formatDashboardValue(Number(value), definition?.unit ?? "count", false),
                      definition?.label ?? String(name),
                    ];
                  }}
                />
                <Legend />
                {series.map((item) => (
                  <Line
                    key={item.key}
                    type="monotone"
                    dataKey={item.key}
                    name={item.label}
                    stroke={item.color}
                    strokeWidth={2}
                    dot={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <AccessibleSeriesTable title={title} data={data} series={series} />
        </>
      )}
    </section>
  );
}

interface CategoryBarChartProps {
  title: string;
  description: string;
  data: CategoryMetric[];
  valueKey?: "count" | "amount" | "average_amount";
  unit?: DashboardUnit;
  horizontal?: boolean;
  testId: string;
}

export function CategoryBarChart({
  title,
  description,
  data,
  valueKey = "count",
  unit = "count",
  horizontal = false,
  testId,
}: CategoryBarChartProps) {
  const normalized = data.map((item) => ({ ...item, value: item[valueKey] ?? 0 }));
  return (
    <section className="dashboard-panel" aria-labelledby={`${testId}-title`}>
      <div className="panel-heading">
        <div>
          <h3 id={`${testId}-title`}>{title}</h3>
          <p>{description}</p>
        </div>
      </div>
      {normalized.length === 0 ? (
        <EmptyPanel />
      ) : (
        <>
          <div className="dashboard-chart" role="img" aria-label={`${title}. ${description}`} data-testid={testId}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={normalized}
                layout={horizontal ? "vertical" : "horizontal"}
                margin={{ top: 8, right: 12, left: horizontal ? 24 : 4, bottom: 4 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#dce5ea" />
                {horizontal ? (
                  <>
                    <XAxis type="number" tick={{ fontSize: 12 }} />
                    <YAxis type="category" dataKey="category" width={100} tick={{ fontSize: 12 }} />
                  </>
                ) : (
                  <>
                    <XAxis dataKey="category" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} />
                  </>
                )}
                <Tooltip formatter={(value) => formatDashboardValue(Number(value), unit, false)} />
                <Bar dataKey="value" name={title} fill="#1876a3" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="dashboard-summary-table">
            <caption className="sr-only">{title} accessible values</caption>
            <thead><tr><th>Category</th><th>Value</th></tr></thead>
            <tbody>
              {normalized.map((item) => (
                <tr key={item.category}>
                  <td>{item.category}</td>
                  <td>{formatDashboardValue(item.value, unit, false)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

function AccessibleSeriesTable({
  title,
  data,
  series,
}: Pick<TimeSeriesChartProps, "title" | "data" | "series">) {
  return (
    <table className="dashboard-summary-table">
      <caption className="sr-only">{title} accessible values</caption>
      <thead>
        <tr><th>Period</th>{series.map((item) => <th key={item.key}>{item.label}</th>)}</tr>
      </thead>
      <tbody>
        {data.map((row) => (
          <tr key={String(row.period)}>
            <td>{row.period}</td>
            {series.map((item) => (
              <td key={item.key}>
                {formatDashboardValue(Number(row[item.key]), item.unit, false)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function EmptyPanel() {
  return <p className="dashboard-empty">No aggregate data is available for this date range.</p>;
}
