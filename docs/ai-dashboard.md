# AI Dashboard

Phase 19 adds a deterministic business-intelligence surface at `#/dashboard`. It is separate from
the conversational application at `#/` and never enters `ChatMode`, `SupervisorMultiAgent`, intent
routing, advanced reasoning, multi-hop SQL, or forecasting.

## Request flow

```text
React Dashboard
    -> GET /api/dashboards/{overview|claims|operations}
    -> DashboardService
    -> fixed aggregate-only SQL
    -> existing QueryExecutor
    -> read-only PostgreSQL
```

The dashboard needs no Gemini, Azure OpenAI, AWS account, or AWS credentials. All numbers, ratios,
trends, and previous-period comparisons are deterministic.

## Date policy

All endpoints accept optional `start_date` and `end_date` ISO dates. Reversed or malformed ranges
return a safe `invalid_dashboard_date_range` response. When dates are omitted, the backend finds
the latest date across claims, encounters, and appointments, uses it as `data_as_of`/`end_date`,
and selects the preceding 12 calendar months, bounded by the earliest available dated record.
This prevents a historical synthetic dataset from becoming empty as the machine clock advances.

The previous comparison period has the same inclusive day count and ends immediately before the
selected range. A zero previous value produces `null`, never an infinite percentage.

## Endpoints and metrics

- `GET /api/dashboards/overview` returns total claims, paid and allowed amounts, average paid per
  claim, members represented in claims, encounters, appointments, providers represented, and
  facilities represented.
- `GET /api/dashboards/claims` returns monthly claim count/paid/allowed trends, actual claim-status
  distribution, bounded provider-specialty aggregates, and facility type aggregates. Facilities
  are joined only through `claims.encounter_id -> encounters.facility_id`.
- `GET /api/dashboards/operations` returns monthly encounter and appointment counts, appointment
  statuses, encounter types, and bounded appointment counts by provider specialty.

`DASHBOARD_TOP_N` defaults to 10 and bounds specialty/facility category results. Monetary sums and
comparisons use PostgreSQL numeric values and Python `Decimal` before JSON serialization. Chart
types are fixed presentation decisions: time series use lines and categorical distributions use
bars. The dashboard does not invoke forecasting automatically.

## Privacy boundary

Responses contain aggregates only. No member names, member/provider external identifiers, email,
phone, individual claims, timelines, resolved SQL, or privacy mappings are returned. There is no
free-text dashboard input, so `PrivacyProcessor` is not involved. Dates are sent as bound query
parameters; arbitrary SQL is not an API contract.

Dashboard requests do not load or modify chat sessions. The shared frontend API client still sends
cookies and `X-Tab-Id` consistently, but filters are request-local dashboard state.

## Local testing

Start the existing FastAPI and webpack processes, then open
`http://localhost:5173/#/dashboard`. No additional service is required.

```bash
cd backend
pytest tests/dashboards
pytest tests/integration/test_dashboards.py -m integration

cd ../frontend
npm test -- --runTestsByPath src/__tests__/dashboard.test.tsx
```

All database examples and integration fixtures are synthetic.
