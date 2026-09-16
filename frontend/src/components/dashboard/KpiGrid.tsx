import type { DashboardKPI } from "../../api/types";
import { formatComparison, formatDashboardValue } from "../../utils/format";

interface KpiGridProps {
  kpis: DashboardKPI[];
}

export function KpiGrid({ kpis }: KpiGridProps) {
  return (
    <div className="dashboard-kpi-grid" aria-label="Dashboard key performance indicators">
      {kpis.map((kpi) => (
        <article className="dashboard-kpi" key={kpi.id}>
          <p>{kpi.label}</p>
          <strong>{formatDashboardValue(kpi.value, kpi.unit)}</strong>
          {kpi.comparison === null ? (
            <small>Previous-period comparison unavailable</small>
          ) : (
            <small className={kpi.comparison >= 0 ? "comparison-up" : "comparison-down"}>
              {kpi.comparison >= 0 ? "Increase " : "Decrease "}
              {formatComparison(kpi.comparison)} {kpi.comparison_label}
            </small>
          )}
        </article>
      ))}
    </div>
  );
}
