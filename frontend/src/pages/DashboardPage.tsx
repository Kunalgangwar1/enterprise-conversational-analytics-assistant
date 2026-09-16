import { useCallback, useEffect, useRef, useState } from "react";

import {
  type DashboardFilters,
  getClaimsDashboard,
  getDashboardOverview,
  getOperationsDashboard,
} from "../api/dashboard";
import { ApiError } from "../api/client";
import type { ClaimsDashboard, DashboardOverview, OperationsDashboard } from "../api/types";
import {
  CategoryBarChart,
  EmptyPanel,
  TimeSeriesChart,
} from "../components/dashboard/DashboardCharts";
import { KpiGrid } from "../components/dashboard/KpiGrid";

interface SectionState<T> {
  data: T | null;
  error: string | null;
}

const EMPTY_SECTION = { data: null, error: null };

function safeError(error: unknown): string {
  return error instanceof ApiError ? error.message : "This dashboard section could not be loaded.";
}

export default function DashboardPage() {
  const [overview, setOverview] = useState<SectionState<DashboardOverview>>(EMPTY_SECTION);
  const [claims, setClaims] = useState<SectionState<ClaimsDashboard>>(EMPTY_SECTION);
  const [operations, setOperations] = useState<SectionState<OperationsDashboard>>(EMPTY_SECTION);
  const [draftStart, setDraftStart] = useState("");
  const [draftEnd, setDraftEnd] = useState("");
  const [appliedFilters, setAppliedFilters] = useState<DashboardFilters>({});
  const [filterError, setFilterError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const activeRequest = useRef<AbortController | null>(null);

  const load = useCallback(async (filters: DashboardFilters) => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setIsLoading(true);
    setOverview((current) => ({ ...current, error: null }));
    setClaims((current) => ({ ...current, error: null }));
    setOperations((current) => ({ ...current, error: null }));

    const [overviewResult, claimsResult, operationsResult] = await Promise.allSettled([
      getDashboardOverview(filters, controller.signal),
      getClaimsDashboard(filters, controller.signal),
      getOperationsDashboard(filters, controller.signal),
    ]);
    if (controller.signal.aborted) return;

    if (overviewResult.status === "fulfilled") {
      setOverview({ data: overviewResult.value, error: null });
      setDraftStart(overviewResult.value.start_date);
      setDraftEnd(overviewResult.value.end_date);
    } else {
      setOverview((current) => ({ ...current, error: safeError(overviewResult.reason) }));
    }
    setClaims(
      claimsResult.status === "fulfilled"
        ? { data: claimsResult.value, error: null }
        : { data: null, error: safeError(claimsResult.reason) },
    );
    setOperations(
      operationsResult.status === "fulfilled"
        ? { data: operationsResult.value, error: null }
        : { data: null, error: safeError(operationsResult.reason) },
    );
    setIsLoading(false);
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => void load({}), 0);
    return () => {
      window.clearTimeout(initialLoad);
      activeRequest.current?.abort();
    };
  }, [load]);

  const applyDates = () => {
    if (draftStart && draftEnd && draftStart > draftEnd) {
      setFilterError("Start date must be on or before end date.");
      return;
    }
    const filters = {
      startDate: draftStart || undefined,
      endDate: draftEnd || undefined,
    };
    setFilterError(null);
    setAppliedFilters(filters);
    void load(filters);
  };

  const initialLoading = isLoading && !overview.data && !claims.data && !operations.data;
  if (initialLoading) return <DashboardSkeleton />;

  return (
    <main className="dashboard-page">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">Deterministic business intelligence</p>
          <h1>AI Dashboard</h1>
          <p>
            Aggregate synthetic healthcare analytics. No language model is used to calculate this page.
          </p>
        </div>
        {overview.data && (
          <div className="data-as-of">
            <span>Data as of</span>
            <strong>{overview.data.data_as_of}</strong>
          </div>
        )}
      </header>

      <section className="dashboard-filter" aria-label="Dashboard date filters">
        <label>
          <span>Start date</span>
          <input type="date" value={draftStart} onChange={(event) => setDraftStart(event.target.value)} />
        </label>
        <label>
          <span>End date</span>
          <input type="date" value={draftEnd} onChange={(event) => setDraftEnd(event.target.value)} />
        </label>
        <button type="button" className="primary-button" onClick={applyDates} disabled={isLoading}>
          Apply
        </button>
        <button
          type="button"
          className="secondary-button"
          onClick={() => void load(appliedFilters)}
          disabled={isLoading}
        >
          Refresh
        </button>
        {isLoading && <span className="dashboard-refreshing" role="status">Refreshing analytics…</span>}
        {filterError && <p className="dashboard-filter-error" role="alert">{filterError}</p>}
      </section>

      <section className="dashboard-section" aria-labelledby="overview-title">
        <div className="section-heading">
          <div><p className="eyebrow">Overview</p><h2 id="overview-title">Performance snapshot</h2></div>
          {overview.data && <span>{overview.data.start_date} – {overview.data.end_date}</span>}
        </div>
        {overview.error && <SectionError message={overview.error} />}
        {overview.data && <KpiGrid kpis={overview.data.kpis} />}
      </section>

      <section className="dashboard-section" aria-labelledby="claims-title">
        <div className="section-heading">
          <div><p className="eyebrow">Claims analytics</p><h2 id="claims-title">Financial and utilization trends</h2></div>
        </div>
        {claims.error && <SectionError message={claims.error} />}
        {claims.data && !claims.data.has_data ? <EmptyPanel /> : claims.data && (
          <div className="dashboard-panel-grid">
            <TimeSeriesChart
              title="Claims by month"
              description="Monthly aggregate claim volume"
              data={claims.data.monthly_trend.map((point) => ({ period: point.period, claim_count: point.claim_count }))}
              series={[{ key: "claim_count", label: "Claims", color: "#1876a3", unit: "count" }]}
              testId="claims-trend-chart"
            />
            <TimeSeriesChart
              title="Paid and allowed amounts"
              description="Monthly aggregate amounts from claim headers"
              data={claims.data.monthly_trend.map((point) => ({
                period: point.period,
                paid_amount: point.paid_amount,
                allowed_amount: point.allowed_amount,
              }))}
              series={[
                { key: "paid_amount", label: "Paid", color: "#1876a3", unit: "currency" },
                { key: "allowed_amount", label: "Allowed", color: "#7d5aa6", unit: "currency" },
              ]}
              testId="claims-amount-chart"
            />
            <CategoryBarChart
              title="Claim status distribution"
              description="Actual statuses represented in the selected synthetic data"
              data={claims.data.status_distribution}
              testId="claim-status-chart"
            />
            <CategoryBarChart
              title="Claims by provider specialty"
              description="Top specialties by aggregate claim count"
              data={claims.data.specialty_breakdown}
              horizontal
              testId="specialty-chart"
            />
            <CategoryBarChart
              title="Claims by facility type"
              description="Claims linked through valid encounter and facility relationships"
              data={claims.data.facility_breakdown}
              testId="facility-chart"
            />
          </div>
        )}
      </section>

      <section className="dashboard-section" aria-labelledby="operations-title">
        <div className="section-heading">
          <div><p className="eyebrow">Operations</p><h2 id="operations-title">Appointments and encounters</h2></div>
        </div>
        {operations.error && <SectionError message={operations.error} />}
        {operations.data && !operations.data.has_data ? <EmptyPanel /> : operations.data && (
          <div className="dashboard-panel-grid">
            <TimeSeriesChart
              title="Encounters by month"
              description="Monthly aggregate encounter volume"
              data={operations.data.encounters_by_month.map((point) => ({ ...point }))}
              series={[{ key: "value", label: "Encounters", color: "#1876a3", unit: "count" }]}
              testId="encounters-trend-chart"
            />
            <TimeSeriesChart
              title="Appointments by month"
              description="Monthly aggregate appointment volume"
              data={operations.data.appointments_by_month.map((point) => ({ ...point }))}
              series={[{ key: "value", label: "Appointments", color: "#2f7e62", unit: "count" }]}
              testId="appointments-trend-chart"
            />
            <CategoryBarChart
              title="Appointment status distribution"
              description="Scheduled, completed, cancelled, and no-show appointments present in data"
              data={operations.data.appointment_status_distribution}
              testId="appointment-status-chart"
            />
            <CategoryBarChart
              title="Encounters by type"
              description="Aggregate encounter mix"
              data={operations.data.encounter_type_distribution}
              testId="encounter-type-chart"
            />
            <CategoryBarChart
              title="Appointments by specialty"
              description="Top provider specialties by appointment count"
              data={operations.data.appointments_by_specialty}
              horizontal
              testId="appointment-specialty-chart"
            />
          </div>
        )}
      </section>
    </main>
  );
}

function DashboardSkeleton() {
  return (
    <main className="dashboard-page" aria-busy="true">
      <header className="dashboard-header"><div><p className="eyebrow">Dashboard</p><h1>AI Dashboard</h1></div></header>
      <p className="dashboard-loading" role="status">Loading aggregate analytics…</p>
      <div className="dashboard-kpi-grid" aria-hidden="true">
        {Array.from({ length: 4 }, (_, index) => <div className="dashboard-skeleton" key={index} />)}
      </div>
    </main>
  );
}

function SectionError({ message }: { message: string }) {
  return <div className="dashboard-section-error" role="alert">{message}</div>;
}
