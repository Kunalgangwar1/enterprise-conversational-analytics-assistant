import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ForecastPayload } from "../../api/types";
import { formatMetric } from "../../utils/format";

export function ForecastCard({ forecast }: { forecast: ForecastPayload }) {
  const chartData = [
    ...forecast.historical_points.map((point) => ({
      period: point.period,
      historical: point.value,
    })),
    ...forecast.forecast_points.map((point) => ({
      period: point.period,
      forecast: point.predicted,
      lower: point.lower_bound,
      upper: point.upper_bound,
    })),
  ];
  return (
    <section className="result-card forecast-card" aria-label="Forecast result">
      <div className="card-heading">
        <h3>{forecast.metric_label}</h3>
        <span className="status-badge">Approximate forecast</span>
      </div>
      <p>{forecast.summary}</p>
      <dl className="metric-grid">
        <div><dt>Model</dt><dd>{forecast.selected_model}</dd></div>
        <div><dt>MAE</dt><dd>{formatMetric(forecast.backtest_metrics.mae)}</dd></div>
        <div><dt>RMSE</dt><dd>{formatMetric(forecast.backtest_metrics.rmse)}</dd></div>
        <div><dt>sMAPE</dt><dd>{formatMetric(forecast.backtest_metrics.smape)}%</dd></div>
      </dl>
      <div className="chart" role="img" aria-label={forecast.chart.title} data-testid="forecast-chart">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line dataKey="historical" name="Historical" stroke="#435f75" strokeWidth={2} />
            <Line dataKey="forecast" name="Forecast" stroke="#2878a8" strokeWidth={2} />
            <Line dataKey="lower" name="Lower interval" stroke="#8ca7b8" strokeDasharray="4 4" />
            <Line dataKey="upper" name="Upper interval" stroke="#8ca7b8" strokeDasharray="4 4" />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="table-scroll">
        <table>
          <caption>Future forecast periods</caption>
          <thead><tr><th>Period</th><th>Forecast</th><th>Lower</th><th>Upper</th></tr></thead>
          <tbody>
            {forecast.forecast_points.map((point) => (
              <tr key={point.period}>
                <td>{point.period}</td>
                <td>{formatMetric(point.predicted)}</td>
                <td>{formatMetric(point.lower_bound)}</td>
                <td>{formatMetric(point.upper_bound)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {forecast.warnings.length > 0 && (
        <ul className="warning-list">
          {forecast.warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      )}
    </section>
  );
}

export default ForecastCard;
