# Aggregate healthcare operations forecasting

Phase 17 adds an internal `ForecastingAgent` under Data Intelligence. It forecasts aggregate
operational measures such as monthly claim volume or weekly appointment counts. It is not a
top-level chat mode, public endpoint, clinical prediction system, or individual risk model.

## Workflow

```text
privacy-safe question
  -> deterministic aggregate-scope check
  -> LLMClient -> typed ForecastPlan (metric, DAY/WEEK/MONTH, horizon, history question)
  -> standard NLP2SQLAgent -> require Phase 12 ACCEPT/final_sql
  -> current-request SQLTokenResolver -> existing bounded QueryExecutor
  -> exactly one temporal column + one finite numeric aggregate column
  -> regular-history validation
  -> deterministic holdout backtest and model selection
  -> refit winner on all history -> point forecast + approximate intervals
  -> protected history preview + immutable forecast -> LLMClient explanation
  -> typed ForecastResult + line-chart metadata
```

The planning model never produces SQL. The standard NLP-to-SQL graph remains the only SQL
generator and validator, and the Phase 4 executor remains the only database execution boundary.
There is no second database engine, parser workaround, direct driver path, or forecasting package
dependency.

## Deterministic computation

History is sorted and bounded to 120 points by default. At least eight points are required.
Periods must be unique, parseable, completed, and exactly regular; missing periods are rejected
rather than imputed. Supported frequencies are day, week, and calendar month.

Candidates are last-value naive, recursive moving average, ordinary least-squares linear trend,
and seasonal naive when training history supports periods 7, 52, or 12 respectively. The final
holdout is never supplied to model fitting. Selection minimizes MAE, then RMSE, then stable model
name. The winner is created fresh and fitted to all accepted history.

Intervals are an explicit approximation: `z × holdout RMSE × sqrt(step)`. Histories that are
nonnegative produce nonnegative central forecasts and lower bounds. This is not a calibrated
probabilistic or clinical confidence interval.

## Privacy and safety

`ForecastingAgent` accepts `safe_question`; it does not call `PrivacyProcessor`. Request
orchestration is responsible for that earlier boundary. Known tokens are restored only in SQL
literals at execution. Only a bounded `SQLSummaryPreviewBuilder` result reaches the explanation
model; raw database rows and generated SQL do not. Model-generated prose cannot modify typed
forecast values. Provider failure uses a deterministic explanation.

Requests for individual clinical outcomes are rejected before model planning. Returned warnings
state that the result is aggregate, operational, approximate, and not medical advice.

## Configuration and rollout

Environment settings define default/max horizon, min/max history, holdout points, moving-average
window, and interval multiplier. `tools.forecasting` remains false by default. When both the tool
flag and `AgentRegistry` route are enabled and an adapter is injected, Phase 16's
`AdvancedToolRegistry` may call the agent. No public forecasting API or full `/chat` orchestration
is added.

Normal tests use `FakeLLMClient`. A configured internal smoke is optional:

```bash
python -m app.forecasting.smoke "Forecast aggregate monthly claim volume for three months"
```

It requires existing provider, metadata-database, and read-only query settings. It prints no SQL,
credentials, privacy mappings, or prompts.
