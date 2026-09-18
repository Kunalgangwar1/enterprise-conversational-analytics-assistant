# Reviewed performance baselines

Promote a JSON/Markdown pair from `artifacts/performance/runs/` only after reviewing the machine,
commit SHA, dataset size, profile, and dependency versions recorded by the run. No baseline numbers
are checked in yet: the Phase 29 workstation did not have the repository Compose stack running, so
publishing latency or throughput figures would be misleading. The first reviewed local baseline
should be named `local-baseline-v1.{json,md}` and must retain the raw Locust CSV as CI evidence.
