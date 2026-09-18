# Local performance harness

This development-only Locust harness uses synthetic data and the `performance.fake_app` FakeLLM
target. It must never be used to load a paid provider. Profiles are defined in `profiles.py`, stable
scenario names in `workload.py`, gates in `thresholds.py`, and JSON/Markdown output in `report.py`.

Run from `backend/` after the documented PostgreSQL/Redis migration and synthetic seed setup:

```bash
uv run uvicorn performance.fake_app:app --host 127.0.0.1 --port 8000
uv run python -m performance.run --profile smoke
```

Run the printed Locust command and pass its `_stats.csv` file to `python -m performance.report`.
See `docs/performance.md` for methodology, profiles, interpretation, and safety boundaries.
