"""Backward-compatible CLI module alias."""

from app.evaluation.run import main

if __name__ == "__main__":
    raise SystemExit(main())
